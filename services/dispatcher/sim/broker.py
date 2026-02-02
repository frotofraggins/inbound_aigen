"""
Simulated broker implementation for Phase 9 dry-run.
Implements Broker interface that can later be swapped for RealBroker.
"""
from typing import Dict, Any, Optional
from datetime import datetime
import json

class SimulatedBroker:
    """
    Simulated broker for Phase 9 dry-run.
    Records what WOULD happen without actual execution.
    
    Future: Swap this for RealBroker (Alpaca, etc.) with same interface.
    """
    
    def __init__(self, conn, config: Dict[str, Any]):
        """
        Initialize simulated broker.
        
        Args:
            conn: Database connection
            config: Configuration dict
        """
        self.conn = conn
        self.config = config
    
    def execute(
        self,
        recommendation: Dict[str, Any],
        run_id: str,
        entry_price: float,
        fill_model: str,
        slippage_bps: int,
        qty: float,
        notional: float,
        stop_loss: Optional[float],
        take_profit: Optional[float],
        max_hold_minutes: int,
        gate_results: Dict[str, Any],
        sizing_rationale: Dict[str, Any],
        stop_rationale: Dict[str, Any],
        bar: Dict[str, Any],
        features: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Simulate trade execution.
        
        Records complete execution plan to dispatch_executions table.
        This is the idempotent write - UNIQUE constraint on recommendation_id
        ensures we only execute once per recommendation.
        
        Args:
            recommendation: Original recommendation dict
            run_id: Current dispatcher run ID
            entry_price: Computed entry price
            fill_model: Fill model used
            slippage_bps: Slippage applied
            qty: Position size
            notional: Dollar value
            stop_loss: Stop loss price
            take_profit: Take profit price
            max_hold_minutes: Maximum hold time
            gate_results: Risk gate evaluation results
            sizing_rationale: Position sizing explanation
            stop_rationale: Stop computation explanation
            bar: Market bar used for pricing
            features: Technical features used
        
        Returns:
            Execution result dict
        """
        
        # Build execution action string
        action = f"{recommendation['action']}_{recommendation['instrument_type']}"
        
        # Build comprehensive sim_json
        sim_json = {
            'bar_used': {
                'ticker': bar['ticker'],
                'timestamp': bar['ts'].isoformat(),
                'open': float(bar['open']),
                'high': float(bar['high']),
                'low': float(bar['low']),
                'close': float(bar['close']),
                'volume': int(bar.get('volume', 0))
            },
            'features_used': {
                'timestamp': features['computed_at'].isoformat(),
                'close': float(features['close']),
                'sma20': float(features['sma20']),
                'sma50': float(features['sma50']),
                'vol_ratio': float(features['vol_ratio']),
                'recent_vol': float(features['recent_vol']),
                'trend_state': int(features['trend_state'])
            },
            'fill_model': fill_model,
            'slippage_bps': slippage_bps,
            'sizing_rationale': sizing_rationale,
            'stop_rationale': stop_rationale,
            'simulated_at': datetime.utcnow().isoformat() + 'Z'
        }
        
        # Build risk_json with all gate results
        risk_json = {
            'gates': gate_results,
            'all_gates_passed': all(g['passed'] for g in gate_results.values()),
            'evaluation_time': datetime.utcnow().isoformat() + 'Z'
        }
        
        # Build execution data
        execution_data = {
            'recommendation_id': str(recommendation['id']),
            'dispatcher_run_id': run_id,
            'ticker': recommendation['ticker'],
            'action': action,
            'decision_ts': recommendation['created_at'],
            'entry_price': entry_price,
            'fill_model': fill_model,
            'slippage_bps': slippage_bps,
            'qty': qty,
            'notional': notional,
            'stop_loss_price': stop_loss,
            'take_profit_price': take_profit,
            'max_hold_minutes': max_hold_minutes,
            'execution_mode': 'SIMULATED',
            'explain_json': recommendation['reason'],  # Copy from recommendation
            'risk_json': risk_json,
            'sim_json': sim_json,
            # Phase 15: Pass through options fields from recommendation
            'instrument_type': recommendation.get('instrument_type', 'STOCK'),
            'strategy_type': recommendation.get('strategy_type'),
            # Options metadata (NULL for stocks, will be filled by AlpacaBroker for real options)
            'strike_price': None,
            'expiration_date': None,
            'contracts': None,
            'premium_paid': None,
            'delta': None,
            'theta': None,
            'implied_volatility': None,
            'option_symbol': None
        }
        
        return execution_data
