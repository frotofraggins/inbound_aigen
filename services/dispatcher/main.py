"""
Dispatcher - Main orchestration.
Production-grade dry-run execution with idempotency guarantees.

Implements proven patterns:
1. Claim-then-act with FOR UPDATE SKIP LOCKED
2. Idempotency enforced by database UNIQUE constraint
3. Immutable execution ledger + separate mutable status
4. Explicit finite state machine (PENDING → PROCESSING → EXECUTED/SIMULATED/SKIPPED/FAILED)
5. Config-driven risk gates with logged facts
"""
import json
import sys
from datetime import datetime
from typing import Dict, Any

from config import load_config
from db.repositories import (
    get_connection,
    create_run,
    finalize_run,
    release_stuck_processing,
    claim_pending_recommendations,
    mark_skipped,
    mark_simulated,
    mark_executed,
    mark_failed,
    insert_execution,
    get_ticker_executions_today,
    get_total_executions_today,
    get_last_trade_for_ticker,
    check_open_position,
    get_account_state,
    get_latest_bar,
    get_latest_features
)
from risk.gates import evaluate_all_gates
from sim.pricing import compute_entry_price, compute_position_size, compute_stops
from sim.broker import SimulatedBroker
from alpaca.broker import AlpacaPaperBroker
import os
import boto3

def log_event(event_type: str, data: Dict[str, Any]):
    """Log structured JSON event."""
    event = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'event': event_type,
        'data': data
    }
    print(json.dumps(event), flush=True)

def process_recommendation(
    conn,
    recommendation: Dict[str, Any],
    run_id: str,
    broker: SimulatedBroker,
    config: Dict[str, Any]
) -> str:
    """
    Process a single recommendation through risk gates and simulation.
    
    Returns status: 'SIMULATED' | 'SKIPPED' | 'FAILED'
    """
    ticker = recommendation['ticker']
    rec_id = str(recommendation['id'])
    
    try:
        # Load latest market data
        bar = get_latest_bar(conn, ticker, config['max_bar_age_seconds'])
        features = get_latest_features(conn, ticker, config['max_feature_age_seconds'])
        
        # Get ticker execution count for daily limit
        ticker_count_today = get_ticker_executions_today(conn, ticker)
        
        # Get ticker's last trade time for cooldown gate
        last_trade = get_last_trade_for_ticker(conn, ticker)
        last_trade_time = last_trade['executed_at'] if last_trade else None
        
        # Check if ticker has open long position (for SELL_STOCK gate)
        has_open_position = check_open_position(conn, ticker)
        
        # Get account-level state for kill switch gates
        account_state = get_account_state(conn)
        
        # Evaluate all risk gates (including account-level kill switches)
        gates_passed, gate_results = evaluate_all_gates(
            recommendation,
            bar,
            features,
            ticker_count_today,
            last_trade_time,
            has_open_position,
            config,
            daily_pnl=account_state['daily_pnl'],
            active_position_count=account_state['active_position_count'],
            total_notional=account_state['total_notional']
        )
        
        log_event('gates_evaluated', {
            'recommendation_id': rec_id,
            'ticker': ticker,
            'gates_passed': gates_passed,
            'gate_results': gate_results
        })
        
        if not gates_passed:
            # Find first failed gate for reason
            failed_gates = [
                name for name, result in gate_results.items()
                if not result['passed']
            ]
            reason = f"Risk gates failed: {', '.join(failed_gates)}"
            
            mark_skipped(conn, rec_id, run_id, reason, gate_results)
            
            log_event('recommendation_skipped', {
                'recommendation_id': rec_id,
                'ticker': ticker,
                'reason': reason,
                'failed_gates': failed_gates
            })
            
            return 'SKIPPED'
        
        # All gates passed - compute execution plan
        entry_price, slippage_bps, fill_model = compute_entry_price(bar, config)
        
        # Phase 15: Build combined action for compute_stops (needs BUY_CALL format)
        combined_action = f"{recommendation['action']}_{recommendation['instrument_type']}"
        
        stop_loss, take_profit, max_hold, stop_rationale = compute_stops(
            entry_price,
            combined_action,
            features,
            config
        )
        qty, notional, sizing_rationale = compute_position_size(
            entry_price,
            stop_loss,
            features,
            config
        )
        
        # Build execution data via simulated broker
        execution_data = broker.execute(
            recommendation=recommendation,
            run_id=run_id,
            entry_price=entry_price,
            fill_model=fill_model,
            slippage_bps=slippage_bps,
            qty=qty,
            notional=notional,
            stop_loss=stop_loss,
            take_profit=take_profit,
            max_hold_minutes=max_hold,
            gate_results=gate_results,
            sizing_rationale=sizing_rationale,
            stop_rationale=stop_rationale,
            bar=bar,
            features=features
        )
        
        # Write execution record (idempotent - UNIQUE on recommendation_id)
        execution_id = insert_execution(conn, execution_data)
        
        if execution_id:
            execution_mode = execution_data.get('execution_mode', 'SIMULATED')
            is_simulated = str(execution_mode).startswith('SIMULATED')

            if is_simulated:
                # Successfully inserted - mark recommendation as SIMULATED
                mark_simulated(conn, rec_id, run_id, gate_results)

                log_event('execution_simulated', {
                    'execution_id': execution_id,
                    'recommendation_id': rec_id,
                    'ticker': ticker,
                    'action': execution_data['action'],
                    'entry_price': entry_price,
                    'qty': qty,
                    'notional': notional,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'execution_mode': execution_mode
                })

                return 'SIMULATED'

            # ALPACA_PAPER (real) execution
            mark_executed(conn, rec_id, run_id, gate_results)

            log_event('execution_executed', {
                'execution_id': execution_id,
                'recommendation_id': rec_id,
                'ticker': ticker,
                'action': execution_data['action'],
                'entry_price': entry_price,
                'qty': qty,
                'notional': notional,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'execution_mode': execution_mode
            })

            return 'EXECUTED'
        else:
            # Already processed (UNIQUE constraint conflict) - idempotency in action
            log_event('execution_duplicate', {
                'recommendation_id': rec_id,
                'ticker': ticker,
                'message': 'Already executed (idempotency)'
            })
            
            # Mark based on current execution_mode
            execution_mode = execution_data.get('execution_mode', 'SIMULATED')
            if str(execution_mode).startswith('SIMULATED'):
                mark_simulated(conn, rec_id, run_id, gate_results)
                return 'SIMULATED'

            mark_executed(conn, rec_id, run_id, gate_results)
            return 'EXECUTED'
    
    except Exception as e:
        # Processing error - mark as FAILED
        error_msg = f"{type(e).__name__}: {str(e)}"
        mark_failed(conn, rec_id, run_id, error_msg)
        
        log_event('processing_error', {
            'recommendation_id': rec_id,
            'ticker': ticker,
            'error': error_msg
        })
        
        return 'FAILED'

def main():
    """Main dispatcher execution loop."""
    log_event('dispatcher_start', {'service': 'dispatcher'})
    
    try:
        # Load configuration
        config = load_config()
        log_event('config_loaded', {
            'max_signals_per_run': config['max_signals_per_run'],
            'confidence_min': config['confidence_min'],
            'lookback_window_minutes': config['lookback_window_minutes'],
            'allowed_actions': config['allowed_actions']
        })
        
        # Connect to database
        conn = get_connection(config)
        log_event('database_connected', {'db_host': config['db_host']})
        
        # Create dispatcher run record
        run_id = create_run(conn, config)
        log_event('run_created', {'run_id': run_id})
        
        # PATTERN 1: Reaper - release stuck PROCESSING rows
        released_count = release_stuck_processing(
            conn,
            config['processing_ttl_minutes']
        )
        
        if released_count > 0:
            log_event('stuck_processing_released', {
                'count': released_count,
                'ttl_minutes': config['processing_ttl_minutes']
            })
        
        # PATTERN 2: Atomic claim with FOR UPDATE SKIP LOCKED
        recommendations = claim_pending_recommendations(
            conn,
            run_id,
            config['max_signals_per_run'],
            config['lookback_window_minutes']
        )
        
        log_event('recommendations_claimed', {
            'count': len(recommendations),
            'tickers': [r['ticker'] for r in recommendations]
        })
        
        if not recommendations:
            log_event('no_pending_recommendations', {
                'message': 'No pending recommendations to process'
            })
            finalize_run(conn, run_id, {
                'pulled': 0,
                'processed': 0,
                'executed': 0,
                'simulated': 0,
                'skipped': 0,
                'failed': 0
            }, {})
            conn.close()
            return
        
        # Initialize broker based on execution mode
        execution_mode = os.environ.get('EXECUTION_MODE', 'SIMULATED')
        
        if execution_mode == 'ALPACA_PAPER':
            # MULTI-ACCOUNT: Log which account we're initializing
            account_name = config.get('account_name', 'unknown')
            account_tier = config.get('account_tier', 'unknown')
            
            log_event('initializing_alpaca_paper_broker', {
                'mode': 'ALPACA_PAPER',
                'account_name': account_name,
                'account_tier': account_tier,
                'base_url': 'https://paper-api.alpaca.markets'
            })
            
            # MULTI-ACCOUNT: Use credentials from config (tier-specific)
            alpaca_config = {
                **config,
                'alpaca_key_id': config['alpaca_api_key'],
                'alpaca_secret_key': config['alpaca_api_secret']
            }
            
            broker = AlpacaPaperBroker(alpaca_config)
            log_event('alpaca_paper_broker_ready', {
                'mode': 'ALPACA_PAPER',
                'account_name': account_name
            })
        else:
            log_event('initializing_simulated_broker', {'mode': 'SIMULATED'})
            broker = SimulatedBroker(conn, config)
        
        # Process each claimed recommendation
        counts = {
            'pulled': len(recommendations),
            'processed': 0,
            'executed': 0,
            'simulated': 0,
            'skipped': 0,
            'failed': 0
        }
        
        processed_tickers = []
        
        for recommendation in recommendations:
            status = process_recommendation(
                conn,
                recommendation,
                run_id,
                broker,
                config
            )
            
            counts['processed'] += 1
            counts[status.lower()] += 1
            processed_tickers.append({
                'ticker': recommendation['ticker'],
                'status': status
            })
        
        # Finalize run with summary
        summary = {
            'processed_tickers': processed_tickers,
            'lookback_window_minutes': config['lookback_window_minutes'],
            'total_executions_today': get_total_executions_today(conn)
        }
        
        finalize_run(conn, run_id, counts, summary)
        
        log_event('run_complete', {
            'run_id': run_id,
            'counts': counts,
            'total_executions_today': summary['total_executions_today']
        })
        
        conn.close()
        
    except Exception as e:
        log_event('dispatcher_error', {
            'error_type': type(e).__name__,
            'error_message': str(e)
        })
        sys.exit(1)

if __name__ == '__main__':
    import time
    import os
    
    # Run mode: ONCE (for testing) or LOOP (for ECS Service)
    run_mode = os.getenv('RUN_MODE', 'LOOP')
    
    if run_mode == 'ONCE':
        log_event('dispatcher_mode', {'mode': 'ONCE'})
        main()
    else:
        log_event('dispatcher_mode', {'mode': 'LOOP', 'interval': '60 seconds'})
        
        while True:
            try:
                main()
                log_event('dispatcher_sleep', {'seconds': 60})
                time.sleep(60)  # 1 minute
            except KeyboardInterrupt:
                log_event('dispatcher_shutdown', {'reason': 'keyboard_interrupt'})
                break
            except Exception as e:
                log_event('dispatcher_loop_error', {
                    'error': str(e),
                    'error_type': type(e).__name__
                })
                time.sleep(30)  # Wait before retry
