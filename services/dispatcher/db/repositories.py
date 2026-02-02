"""
Database repositories for Dispatcher.
Implements atomic claim-then-act pattern with FOR UPDATE SKIP LOCKED.
All operations are idempotent and concurrency-safe.
"""
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import uuid
import json

def get_connection(config: Dict[str, Any]):
    """Create database connection."""
    return psycopg2.connect(
        host=config['db_host'],
        port=config['db_port'],
        database=config['db_name'],
        user=config['db_user'],
        password=config['db_password']
    )

# ============================================================================
# DISPATCHER RUNS - Operational tracking
# ============================================================================

def create_run(conn, config: Dict[str, Any]) -> str:
    """
    Create a new dispatcher run record.
    Returns run_id (UUID string).
    """
    run_id = str(uuid.uuid4())
    
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO dispatcher_runs (
                run_id, started_at, run_config_json
            ) VALUES (
                %s, NOW(), %s::jsonb
            )
        """, (run_id, json.dumps({
            'max_signals_per_run': config['max_signals_per_run'],
            'confidence_min': config['confidence_min'],
            'lookback_window_minutes': config['lookback_window_minutes'],
            'allowed_actions': config['allowed_actions']
        })))
        conn.commit()
    
    return run_id

def finalize_run(conn, run_id: str, counts: Dict[str, int], summary: Dict[str, Any]):
    """Update dispatcher run with final counts and timing."""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE dispatcher_runs
            SET finished_at = NOW(),
                pulled_count = %s,
                processed_count = %s,
                simulated_count = %s,
                skipped_count = %s,
                failed_count = %s,
                run_summary_json = %s::jsonb
            WHERE run_id = %s
        """, (
            counts.get('pulled', 0),
            counts.get('processed', 0),
            counts.get('simulated', 0),
            counts.get('skipped', 0),
            counts.get('failed', 0),
            json.dumps(summary),
            run_id
        ))
        conn.commit()

# ============================================================================
# RECOMMENDATIONS - Atomic claim with FOR UPDATE SKIP LOCKED
# ============================================================================

def release_stuck_processing(conn, ttl_minutes: int) -> int:
    """
    Reaper: Reset stuck PROCESSING rows back to PENDING.
    Returns count of released rows.
    """
    cutoff = datetime.utcnow() - timedelta(minutes=ttl_minutes)
    
    with conn.cursor() as cur:
        cur.execute("""
        UPDATE dispatch_recommendations
        SET status = 'PENDING',
            dispatcher_run_id = NULL,
            failure_reason = 'Released from stuck PROCESSING state'
        WHERE status = 'PROCESSING'
          AND COALESCE(processed_at, ts) < %s
        RETURNING id
    """, (cutoff,))
        
        released_count = cur.rowcount
        conn.commit()
    
    return released_count

def claim_pending_recommendations(
    conn,
    run_id: str,
    limit: int,
    lookback_minutes: int
) -> List[Dict[str, Any]]:
    """
    Atomically claim pending recommendations using FOR UPDATE SKIP LOCKED.
    
    This is the CRITICAL pattern for idempotency:
    1. SELECT FOR UPDATE SKIP LOCKED (atomic lock, no duplicates)
    2. UPDATE to PROCESSING in same transaction
    3. COMMIT
    4. Only then do expensive work
    
    Returns list of claimed recommendation dicts.
    """
    cutoff = datetime.utcnow() - timedelta(minutes=lookback_minutes)
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Atomic claim: lock rows, update status, commit
        cur.execute("""
            WITH locked_rows AS (
                SELECT id
                FROM dispatch_recommendations
                WHERE status = 'PENDING'
                  AND ts >= %s
                ORDER BY ts ASC
                LIMIT %s
                FOR UPDATE SKIP LOCKED
            )
            UPDATE dispatch_recommendations
            SET status = 'PROCESSING',
                dispatcher_run_id = %s,
                processed_at = NOW()
            FROM locked_rows
            WHERE dispatch_recommendations.id = locked_rows.id
            RETURNING 
                dispatch_recommendations.id,
                dispatch_recommendations.ticker,
                dispatch_recommendations.action,
                dispatch_recommendations.instrument_type,
                dispatch_recommendations.strategy_type,
                dispatch_recommendations.confidence,
                dispatch_recommendations.reason,
                dispatch_recommendations.ts AS created_at
        """, (cutoff, limit, run_id))
        
        rows = cur.fetchall()
        conn.commit()
    
    return rows

def mark_skipped(
    conn,
    recommendation_id: str,
    run_id: str,
    reason: str,
    gate_json: Dict[str, Any]
):
    """Mark recommendation as SKIPPED with reason."""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE dispatch_recommendations
            SET status = 'SKIPPED',
                failure_reason = %s,
                risk_gate_json = %s::jsonb
            WHERE id = %s
              AND dispatcher_run_id = %s
        """, (reason, json.dumps(gate_json), recommendation_id, run_id))
        conn.commit()

def mark_simulated(
    conn,
    recommendation_id: str,
    run_id: str,
    gate_json: Dict[str, Any]
):
    """Mark recommendation as SIMULATED successfully."""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE dispatch_recommendations
            SET status = 'SIMULATED',
                risk_gate_json = %s::jsonb
            WHERE id = %s
              AND dispatcher_run_id = %s
        """, (json.dumps(gate_json), recommendation_id, run_id))
        conn.commit()

def mark_executed(
    conn,
    recommendation_id: str,
    run_id: str,
    gate_json: Dict[str, Any]
):
    """Mark recommendation as EXECUTED successfully."""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE dispatch_recommendations
            SET status = 'EXECUTED',
                risk_gate_json = %s::jsonb
            WHERE id = %s
              AND dispatcher_run_id = %s
        """, (json.dumps(gate_json), recommendation_id, run_id))
        conn.commit()

def mark_failed(
    conn,
    recommendation_id: str,
    run_id: str,
    reason: str
):
    """Mark recommendation as FAILED with error reason."""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE dispatch_recommendations
            SET status = 'FAILED',
                failure_reason = %s
            WHERE id = %s
              AND dispatcher_run_id = %s
        """, (reason, recommendation_id, run_id))
        conn.commit()

# ============================================================================
# EXECUTIONS - Idempotent execution ledger
# ============================================================================

def insert_execution(
    conn,
    execution_data: Dict[str, Any]
) -> Optional[str]:
    """
    Insert execution record with idempotency guarantee.
    
    The UNIQUE constraint on recommendation_id ensures exactly one
    execution per recommendation. If we try to insert twice, we treat
    the conflict as "already processed" and return None.
    
    Supports both stock and options trading (Phase 15).
    
    Returns execution_id if inserted, None if already exists.
    """
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO dispatch_executions (
                    recommendation_id,
                    dispatcher_run_id,
                    ticker,
                    action,
                    decision_ts,
                    entry_price,
                    fill_model,
                    slippage_bps,
                    qty,
                    notional,
                    stop_loss_price,
                    take_profit_price,
                    max_hold_minutes,
                    execution_mode,
                    explain_json,
                    risk_json,
                    sim_json,
                    instrument_type,
                    strike_price,
                    expiration_date,
                    contracts,
                    premium_paid,
                    delta,
                    theta,
                    implied_volatility,
                    option_symbol,
                    strategy_type
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                RETURNING execution_id
            """, (
                execution_data['recommendation_id'],
                execution_data['dispatcher_run_id'],
                execution_data['ticker'],
                execution_data['action'],
                execution_data['decision_ts'],
                execution_data['entry_price'],
                execution_data['fill_model'],
                execution_data['slippage_bps'],
                execution_data['qty'],
                execution_data['notional'],
                execution_data.get('stop_loss_price'),
                execution_data.get('take_profit_price'),
                execution_data.get('max_hold_minutes'),
                execution_data.get('execution_mode', 'SIMULATED'),
                json.dumps(execution_data['explain_json']),
                json.dumps(execution_data['risk_json']),
                json.dumps(execution_data['sim_json']),
                # Options-specific fields (NULL for stocks)
                execution_data.get('instrument_type', 'STOCK'),
                execution_data.get('strike_price'),
                execution_data.get('expiration_date'),
                execution_data.get('contracts'),
                execution_data.get('premium_paid'),
                execution_data.get('delta'),
                execution_data.get('theta'),
                execution_data.get('implied_volatility'),
                execution_data.get('option_symbol'),
                execution_data.get('strategy_type')
            ))
            
            execution_id = cur.fetchone()[0]
            conn.commit()
            return str(execution_id)
            
    except psycopg2.errors.UniqueViolation:
        # Already processed - idempotency in action
        conn.rollback()
        return None

# ============================================================================
# LIMITS - Daily counts and ticker cooldowns
# ============================================================================

def get_ticker_executions_today(conn, ticker: str) -> int:
    """Count how many times ticker was executed today."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*)
            FROM dispatch_executions
            WHERE ticker = %s
              AND simulated_ts >= CURRENT_DATE
        """, (ticker,))
        
        return cur.fetchone()[0]

def get_total_executions_today(conn) -> int:
    """Count total executions today."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*)
            FROM dispatch_executions
            WHERE simulated_ts >= CURRENT_DATE
        """)
        
        return cur.fetchone()[0]

def get_last_trade_for_ticker(conn, ticker: str) -> Optional[Dict[str, Any]]:
    """
    Get most recent execution for ticker (for cooldown gate).
    Returns dict with executed_at timestamp, or None if no trades.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT 
                execution_id,
                ticker,
                simulated_ts AS executed_at,
                action,
                instrument_type
            FROM dispatch_executions
            WHERE ticker = %s
            ORDER BY simulated_ts DESC
            LIMIT 1
        """, (ticker,))
        
        row = cur.fetchone()
        return dict(row) if row else None

def check_open_position(conn, ticker: str) -> bool:
    """
    Check if ticker has an open long position.
    Used for SELL_STOCK gate (only sell if we own it).
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT EXISTS (
                SELECT 1
                FROM active_positions
                WHERE ticker = %s
                  AND status IN ('open', 'OPEN')
                  AND quantity > 0
            )
        """, (ticker,))
        
        return cur.fetchone()[0]

def get_account_state(conn) -> Dict[str, Any]:
    """
    Get account-level state for kill switch gates.
    
    Returns:
        Dict with daily_pnl, active_position_count, total_notional
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Get today's P&L from executions
        cur.execute("""
            SELECT COALESCE(SUM(notional), 0) as total_traded_today
            FROM dispatch_executions
            WHERE simulated_ts >= CURRENT_DATE
        """)
        result = cur.fetchone()
        total_traded = float(result['total_traded_today']) if result else 0.0
        
        # Get active position count and total notional
        cur.execute("""
            SELECT 
                COUNT(*) as position_count,
                COALESCE(SUM(ABS(quantity * entry_price)), 0) as total_notional
            FROM active_positions
            WHERE status IN ('open', 'OPEN')
        """)
        result = cur.fetchone()
        
        position_count = int(result['position_count']) if result else 0
        total_notional = float(result['total_notional']) if result else 0.0
        
        # For now, daily P&L is approximated (real P&L needs mark-to-market)
        # This is conservative - will implement proper P&L tracking later
        daily_pnl = 0.0  # TODO: Calculate from position_events
        
        return {
            'daily_pnl': daily_pnl,
            'active_position_count': position_count,
            'total_notional': total_notional,
            'total_traded_today': total_traded
        }

# ============================================================================
# TELEMETRY - Latest market data for pricing
# ============================================================================

def get_latest_bar(conn, ticker: str, max_age_seconds: int) -> Optional[Dict[str, Any]]:
    """
    Get most recent 1-minute bar for ticker.
    Returns None if no bar within max_age_seconds.
    """
    cutoff = datetime.utcnow() - timedelta(seconds=max_age_seconds)
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT 
                ticker,
                ts,
                open,
                high,
                low,
                close,
                volume
            FROM lane_telemetry
            WHERE ticker = %s
              AND ts >= %s
            ORDER BY ts DESC
            LIMIT 1
        """, (ticker, cutoff))
        
        row = cur.fetchone()
        return dict(row) if row else None

def get_latest_features(conn, ticker: str, max_age_seconds: int) -> Optional[Dict[str, Any]]:
    """
    Get most recent computed features for ticker.
    Returns None if no features within max_age_seconds.
    """
    cutoff = datetime.utcnow() - timedelta(seconds=max_age_seconds)
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT 
                ticker,
                close,
                sma20,
                sma50,
                distance_sma20,
                distance_sma50,
                recent_vol,
                baseline_vol,
                vol_ratio,
                trend_state,
                computed_at
            FROM lane_features_clean
            WHERE ticker = %s
              AND computed_at >= %s
            ORDER BY computed_at DESC
            LIMIT 1
        """, (ticker, cutoff))
        
        row = cur.fetchone()
        return dict(row) if row else None
