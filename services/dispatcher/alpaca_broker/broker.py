"""
Alpaca Paper Trading Broker
Connects to Alpaca Paper Trading API to execute real (simulated) trades

Now supports:
- Stock trading (existing)
- Options trading (Phase 15)
"""

import requests
import json
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import sys
import os

# Alpaca SDK imports
from alpaca.trading.enums import PositionIntent

# Add parent directory to path for options module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from options import (
    AlpacaOptionsAPI,
    get_option_chain_for_strategy,
    calculate_position_size as calc_option_position_size,
    format_option_symbol
)

class AlpacaPaperBroker:
    """
    Real Alpaca Paper Trading broker.
    
    Uses Alpaca Paper Trading API to:
    - Place actual orders (on paper account)
    - Track real positions
    - Get real fills with market slippage
    - Monitor paper account balance
    
    This is MORE REALISTIC than pure simulation because:
    - Orders go through Alpaca's order routing
    - Fills based on real market conditions
    - Slippage is actual, not simulated
    - Position tracking by Alpaca
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Alpaca paper trading broker.
        
        Args:
            config: Must contain alpaca_key_id and alpaca_secret_key
        """
        self.config = config  # Store for IV/Kelly features
        self.api_key = config['alpaca_key_id']
        self.api_secret = config['alpaca_secret_key']
        self.base_url = "https://paper-api.alpaca.markets"
        
        # Initialize options API client
        self.options_api = AlpacaOptionsAPI(
            api_key=self.api_key,
            api_secret=self.api_secret,
            paper_trading=True
        )
        
        # Test connection
        self._verify_connection()
    
    def _verify_connection(self):
        """Verify we can connect to Alpaca"""
        headers = {
            'APCA-API-KEY-ID': self.api_key,
            'APCA-API-SECRET-KEY': self.api_secret
        }
        response = requests.get(f"{self.base_url}/v2/account", headers=headers)
        if response.status_code != 200:
            raise Exception(f"Alpaca connection failed: {response.text}")
        
        account = response.json()
        
        # Get account tier configuration for logging
        account_name = self.config.get('account_name', 'unknown')
        account_tier = self.config.get('account_tier', 'unknown')
        tier_config = self.config.get('account_tier_config', {})
        
        print(f"Connected to Alpaca Paper Trading")
        print(f"  Account Name: {account_name}")
        print(f"  Account Tier: {account_tier}")
        print(f"  Account Number: {account['account_number']}")
        print(f"  Buying power: ${float(account['buying_power']):.2f}")
        print(f"  Cash: ${float(account['cash']):.2f}")
        print(f"  Risk Limits:")
        print(f"    - Max contracts: {tier_config.get('max_contracts', 'N/A')}")
        print(f"    - Risk % (day): {tier_config.get('risk_pct_day', 0) * 100:.1f}%")
        print(f"    - Risk % (swing): {tier_config.get('risk_pct_swing', 0) * 100:.1f}%")
        print(f"    - Min confidence: {tier_config.get('min_confidence', 'N/A')}")
        print(f"    - Min volume ratio: {tier_config.get('min_volume_ratio', 'N/A')}x")
    
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
        max_hold_minutes: Optional[int],
        **kwargs  # Accept additional parameters from dispatcher
    ) -> Dict[str, Any]:
        """
        Execute trade on Alpaca Paper Trading API.
        
        Places actual order through Alpaca's paper trading system.
        Returns execution details including actual fill price from Alpaca.
        """
        
        ticker = recommendation['ticker']
        action = recommendation['action']
        instrument_type = recommendation.get('instrument_type', 'STOCK')
        
        # Determine order side
        if action == 'BUY':
            side = 'buy'
        elif action == 'SELL':
            side = 'sell'
        else:
            raise ValueError(f"Invalid action: {action}")
        
        # Extract additional parameters from kwargs
        explain_json = kwargs.get('explain_json', {})
        risk_json = kwargs.get('risk_json', {})
        
        # CRITICAL FIX 2026-02-05: Extract features_snapshot for learning
        # This captures market conditions at entry time
        features_snapshot = recommendation.get('features_snapshot', {})
        
        # Route to appropriate execution method
        if instrument_type in ('CALL', 'PUT'):
            return self._execute_option(
                recommendation, run_id, entry_price, fill_model,
                slippage_bps, qty, notional, stop_loss, take_profit,
                max_hold_minutes, explain_json, risk_json, side, features_snapshot
            )
        else:
            return self._execute_stock(
                recommendation, run_id, entry_price, fill_model,
                slippage_bps, qty, notional, stop_loss, take_profit,
                max_hold_minutes, explain_json, risk_json, side, ticker, features_snapshot
            )
    
    def _execute_stock(
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
        max_hold_minutes: Optional[int],
        explain_json: Dict[str, Any],
        risk_json: Dict[str, Any],
        side: str,
        ticker: str,
        features_snapshot: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute stock trade on Alpaca.
        
        Existing stock trading logic (unchanged from before).
        """
        
        # Extract action from recommendation
        action = recommendation['action']
        
        # Round prices to 2 decimal places (Alpaca rejects sub-penny prices)
        entry_price = round(entry_price, 2)
        if stop_loss:
            stop_loss = round(stop_loss, 2)
        if take_profit:
            take_profit = round(take_profit, 2)
        
        # Prepare order
        order_data = {
            "symbol": ticker,
            "qty": int(qty),  # Alpaca requires integer shares
            "side": side,
            "type": "market",  # Start with market orders (limit orders in Phase 13)
            "time_in_force": "day"
        }
        
        # CRITICAL FIX 2026-02-04: Don't set bracket orders on Alpaca
        # Let our position manager handle all exits with proper timing and logic
        # Alpaca brackets were closing positions in 4 min before position manager could monitor (checks every 5 min, now 1 min)
        order_data["order_class"] = "simple"
        # Store stop/profit in database only - position manager will enforce them
        
        # Submit order to Alpaca
        headers = {
            'APCA-API-KEY-ID': self.api_key,
            'APCA-API-SECRET-KEY': self.api_secret,
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/v2/orders",
                headers=headers,
                data=json.dumps(order_data),
                timeout=10
            )
            
            if response.status_code != 200:
                # Order rejected - fall back to simulation
                return self._simulate_execution(
                    recommendation, run_id, entry_price, fill_model,
                    slippage_bps, qty, notional, stop_loss, take_profit,
                    max_hold_minutes, explain_json, risk_json,
                    reason=f"Alpaca rejected: {response.text[:100]}",
                    features_snapshot=features_snapshot
                )
            
            order = response.json()
            
            # Wait briefly for fill (Alpaca paper trading is instant for market orders)
            import time
            time.sleep(0.5)
            
            # Get order status
            order_id = order['id']
            response = requests.get(
                f"{self.base_url}/v2/orders/{order_id}",
                headers=headers
            )
            order_status = response.json()
            
            # Extract fill details
            filled_qty = float(order_status.get('filled_qty', 0))
            filled_avg_price = float(order_status.get('filled_avg_price', entry_price))
            
            return {
                'execution_id': None,  # Will be generated by caller
                'recommendation_id': recommendation['id'],
                'dispatcher_run_id': run_id,
                'ticker': ticker,
                'action': action,
                'decision_ts': recommendation['created_at'],
                'simulated_ts': datetime.now(timezone.utc),
                'entry_price': filled_avg_price,  # Actual fill from Alpaca
                'fill_model': 'ALPACA_PAPER',
                'slippage_bps': int((filled_avg_price - entry_price) / entry_price * 10000),
                'qty': filled_qty,
                'notional': filled_qty * filled_avg_price,
                'stop_loss_price': stop_loss,
                'take_profit_price': take_profit,
                'max_hold_minutes': max_hold_minutes,
                'execution_mode': 'ALPACA_PAPER',
                'account_name': self.config.get('account_name', 'large-default'),  # MULTI-ACCOUNT
                'explain_json': {
                    **explain_json,
                    'alpaca_order_id': order_id,
                    'alpaca_status': order_status['status'],
                    'filled_at': order_status.get('filled_at')
                },
                'risk_json': risk_json,
                'sim_json': {
                    'broker': 'alpaca_paper',
                    'order_id': order_id,
                    'order_type': order_data['type'],
                    'time_in_force': order_data['time_in_force'],
                    'submitted_at': order['submitted_at'],
                    'filled_at': order_status.get('filled_at'),
                    'filled_qty': filled_qty,
                    'filled_avg_price': filled_avg_price
                },
                # CRITICAL: Pass features for learning
                'entry_features_json': features_snapshot
            }
            
        except Exception as e:
            # Connection error - fall back to simulation
            return self._simulate_execution(
                recommendation, run_id, entry_price, fill_model,
                slippage_bps, qty, notional, stop_loss, take_profit,
                max_hold_minutes, explain_json, risk_json,
                reason=f"Alpaca stock error: {str(e)}",
                features_snapshot=features_snapshot
            )
    
    def _execute_option(
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
        max_hold_minutes: Optional[int],
        explain_json: Dict[str, Any],
        risk_json: Dict[str, Any],
        side: str,
        features_snapshot: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute options trade on Alpaca.
        
        New in Phase 15: Options trading support.
        
        NOTE: We construct option symbols directly without pre-fetching contracts
        because the Alpaca data API (v1beta1/options/contracts) requires paid subscription.
        This is acceptable because:
        1. Order placement API will validate the symbol
        2. We use sensible defaults (7 DTE, ATM strikes)
        3. Failed orders fall back to simulation safely
        """
        ticker = recommendation['ticker']
        instrument_type = recommendation['instrument_type']
        strategy_type = recommendation.get('strategy_type', 'day_trade')
        
        try:
            # Get account info for position sizing
            account = self.get_account()
            buying_power = float(account['buying_power'])

            # Paper trading override: ignore actual buying power if configured
            if self.config.get('paper_ignore_buying_power'):
                override = self.config.get('paper_buying_power_override')
                if override is not None:
                    buying_power = float(override)
                    print(f"Paper override buying power: ${buying_power:.2f}")
                else:
                    buying_power = 1_000_000_000.0
                    print("Paper override buying power: unlimited (1e9)")
            
            # Get option chain and select optimal contract using REAL API
            option_type = 'call' if instrument_type == 'CALL' else 'put'
            
            best_contract = get_option_chain_for_strategy(
                api=self.options_api,
                ticker=ticker,
                current_price=entry_price,
                strategy=strategy_type,
                option_type=option_type
            )
            
            if not best_contract:
                return self._simulate_execution(
                    recommendation, run_id, entry_price, fill_model,
                    slippage_bps, qty, notional, stop_loss, take_profit,
                    max_hold_minutes, explain_json, risk_json,
                    reason="No suitable option contract found via Alpaca API",
                    features_snapshot=features_snapshot
                )
            
            # Extract contract details from real API response
            strike_price = float(best_contract['strike_price'])
            expiration_str = best_contract['expiration_date']
            option_symbol = best_contract['symbol']

            # PHASE 3-4: Validate IV Rank before trading
            from options import validate_iv_rank
            from db.iv_history import IVHistoryDB

            iv_db = IVHistoryDB(self.config)
            iv_passed, iv_reason = validate_iv_rank(best_contract, ticker, iv_db)
            iv_db.close()
            
            if not iv_passed:
                return self._simulate_execution(
                    recommendation, run_id, entry_price, fill_model,
                    slippage_bps, qty, notional, stop_loss, take_profit,
                    max_hold_minutes, explain_json, risk_json,
                    reason=f"IV validation failed: {iv_reason}",
                    features_snapshot=features_snapshot
                )
            
            print(f"✓ IV validation passed: {iv_reason}")

            # Get real option price from API
            bid = float(best_contract.get('bid', 0))
            ask = float(best_contract.get('ask', 0))
            option_price = (bid + ask) / 2 if bid > 0 and ask > 0 else 0

            if option_price <= 0:
                return self._simulate_execution(
                    recommendation, run_id, entry_price, fill_model,
                    slippage_bps, qty, notional, stop_loss, take_profit,
                    max_hold_minutes, explain_json, risk_json,
                    reason=f"Invalid option price from API: ${option_price}",
                    features_snapshot=features_snapshot
                )

            # PHASE 4: Calculate position size with Kelly Criterion (if enough history)
            from options import calculate_kelly_criterion_size

            # Get historical stats for Kelly (optional; skip if module unavailable in this container)
            stats = {"total_trades": 0, "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0}
            try:
                from position_manager.db import get_historical_trade_stats
                account_tier = self.config.get('account_tier', 'unknown')
                stats = get_historical_trade_stats(account_tier, days=30) or stats
            except Exception as e:
                print(f"Kelly stats unavailable, skipping Kelly sizing: {e}")
            
            # Use Kelly if we have enough trade history
            if stats['total_trades'] >= 20:
                kelly_contracts, kelly_rationale = calculate_kelly_criterion_size(
                    win_rate=stats['win_rate'],
                    avg_win_pct=stats['avg_win'],
                    avg_loss_pct=abs(stats['avg_loss']),
                    account_buying_power=buying_power,
                    option_price=option_price
                )
                
                print(f"Kelly sizing: {kelly_rationale}")
                
                # Compare Kelly vs tier-based sizing
                tier_contracts, tier_cost, tier_rationale = calc_option_position_size(
                    option_price=option_price,
                    account_buying_power=buying_power,
                    max_risk_pct=5.0,
                    strategy=strategy_type
                )
                
                # Use whichever is more conservative (lower contracts)
                num_contracts = min(kelly_contracts, tier_contracts)
                total_cost = num_contracts * option_price * 100
                sizing_rationale = f"Kelly: {kelly_contracts}, Tier: {tier_contracts}, Using: {num_contracts} (more conservative)"
                
                print(f"✓ Final sizing (Kelly+Tier): {num_contracts} contracts")
            else:
                # Not enough history, use tier-based sizing
                num_contracts, total_cost, sizing_rationale = calc_option_position_size(
                    option_price=option_price,
                    account_buying_power=buying_power,
                    max_risk_pct=5.0,
                    strategy=strategy_type
                )
                print(f"✓ Tier-based sizing (insufficient history): {num_contracts} contracts")
            
            if num_contracts == 0:
                return self._simulate_execution(
                    recommendation, run_id, entry_price, fill_model,
                    slippage_bps, qty, notional, stop_loss, take_profit,
                    max_hold_minutes, explain_json, risk_json,
                    reason=f"Insufficient buying power: ${buying_power:.2f}, need ${option_price * 100:.2f}",
                    features_snapshot=features_snapshot
                )
            
            # Determine position intent (dispatcher only OPENS positions, never closes)
            # CRITICAL: Must specify position_intent for options to avoid unintended positions
            
            if recommendation['action'] == 'BUY':
                position_intent = PositionIntent.BUY_TO_OPEN  # Opening long position
            elif recommendation['action'] == 'SELL':
                position_intent = PositionIntent.SELL_TO_OPEN  # Opening short position
            else:
                raise ValueError(f"Invalid action: {recommendation['action']}")
            
            # Prepare option order
            order_data = {
                "symbol": option_symbol,
                "qty": str(num_contracts),
                "side": side,
                "type": "market",
                "time_in_force": "day",
                "order_class": "simple",  # Options don't support bracket orders in same way
                "position_intent": position_intent.value  # CRITICAL: Specify we're opening, not closing
            }
            
            # Submit order to Alpaca
            headers = {
                'APCA-API-KEY-ID': self.api_key,
                'APCA-API-SECRET-KEY': self.api_secret,
                'Content-Type': 'application/json'
            }
            
            response = requests.post(
                f"{self.base_url}/v2/orders",
                headers=headers,
                data=json.dumps(order_data),
                timeout=10
            )
            
            if response.status_code != 200:
                return self._simulate_execution(
                    recommendation, run_id, entry_price, fill_model,
                    slippage_bps, qty, notional, stop_loss, take_profit,
                    max_hold_minutes, explain_json, risk_json,
                    reason=f"Alpaca rejected option order: {response.text[:100]}",
                    features_snapshot=features_snapshot
                )
            
            order = response.json()
            
            # Wait briefly for fill
            import time
            time.sleep(0.5)
            
            # Get order status
            order_id = order['id']
            response = requests.get(
                f"{self.base_url}/v2/orders/{order_id}",
                headers=headers
            )
            order_status = response.json()
            
            # Extract fill details
            filled_qty = int(order_status.get('filled_qty', 0))
            filled_avg_price = float(order_status.get('filled_avg_price', option_price))
            
            # Calculate actual notional
            actual_notional = filled_qty * filled_avg_price * 100  # contracts × premium × 100 shares
            
            # Get Greeks from contract
            delta = float(best_contract.get('delta', 0))
            theta = float(best_contract.get('theta', 0))
            implied_vol = float(best_contract.get('implied_volatility', 0))
            
            return {
                'execution_id': None,
                'recommendation_id': recommendation['id'],
                'dispatcher_run_id': run_id,
                'ticker': ticker,
                'action': recommendation['action'],
                'decision_ts': recommendation['created_at'],
                'simulated_ts': datetime.now(timezone.utc),
                'entry_price': filled_avg_price,
                'fill_model': 'ALPACA_PAPER_OPTIONS',
                'slippage_bps': int((filled_avg_price - option_price) / option_price * 10000) if option_price > 0 else 0,
                'qty': filled_qty,
                'notional': actual_notional,
                'stop_loss_price': stop_loss,
                'take_profit_price': take_profit,
                'max_hold_minutes': max_hold_minutes,
                'execution_mode': 'ALPACA_PAPER',
                'account_name': self.config.get('account_name', 'large-default'),  # MULTI-ACCOUNT
                'explain_json': {
                    **explain_json,
                    'alpaca_order_id': order_id,
                    'alpaca_status': order_status['status'],
                    'filled_at': order_status.get('filled_at'),
                    'sizing_rationale': sizing_rationale,
                    'api_bid': bid,
                    'api_ask': ask,
                    'api_mid_price': option_price
                },
                'risk_json': risk_json,
                'sim_json': {
                    'broker': 'alpaca_paper_options',
                    'order_id': order_id,
                    'option_symbol': option_symbol,
                    'order_type': order_data['type'],
                    'time_in_force': order_data['time_in_force'],
                    'submitted_at': order['submitted_at'],
                    'filled_at': order_status.get('filled_at'),
                    'filled_contracts': filled_qty,
                    'filled_avg_price': filled_avg_price,
                    'api_price': option_price,
                    'api_bid': bid,
                    'api_ask': ask
                },
                # CRITICAL: Pass features for learning
                'entry_features_json': features_snapshot,
                # Options-specific fields
                'instrument_type': instrument_type,
                'strike_price': strike_price,
                'expiration_date': expiration_str,
                'contracts': filled_qty,
                'premium_paid': filled_avg_price,
                'delta': delta,
                'theta': theta,
                'implied_volatility': implied_vol,
                'option_symbol': option_symbol,
                'strategy_type': strategy_type
            }
            
        except Exception as e:
            # Connection error - fall back to simulation
            return self._simulate_execution(
                recommendation, run_id, entry_price, fill_model,
                slippage_bps, qty, notional, stop_loss, take_profit,
                max_hold_minutes, explain_json, risk_json,
                reason=f"Alpaca options error: {str(e)}",
                features_snapshot=features_snapshot
            )
    
    def _simulate_execution(
        self, recommendation, run_id, entry_price, fill_model,
        slippage_bps, qty, notional, stop_loss, take_profit,
        max_hold_minutes, explain_json, risk_json, reason: str,
        features_snapshot: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Fallback to simulation if Alpaca fails.
        
        This ensures system keeps working even if Alpaca has issues.
        """
        print(f"Falling back to simulation: {reason}")
        
        # Apply simulated slippage
        if recommendation['action'] == 'BUY':
            fill_price = entry_price * (1 + slippage_bps / 10000)
        else:
            fill_price = entry_price * (1 - slippage_bps / 10000)
        
        return {
            'execution_id': None,
            'recommendation_id': recommendation['id'],
            'dispatcher_run_id': run_id,
            'ticker': recommendation['ticker'],
            'action': recommendation['action'],
            'decision_ts': recommendation['created_at'],
            'simulated_ts': datetime.now(timezone.utc),
            'entry_price': fill_price,
            'fill_model': fill_model,
            'slippage_bps': slippage_bps,
            'qty': qty,
            'notional': notional,
            'stop_loss_price': stop_loss,
            'take_profit_price': take_profit,
            'max_hold_minutes': max_hold_minutes,
            'execution_mode': 'SIMULATED_FALLBACK',
            'account_name': self.config.get('account_name', 'large-default'),  # MULTI-ACCOUNT
            'explain_json': {
                **explain_json,
                'fallback_reason': reason
            },
            'risk_json': risk_json,
            'sim_json': {
                'broker': 'simulated_fallback',
                'model': fill_model,
                'slippage_bps': slippage_bps
            },
            # CRITICAL: Pass features even in simulation
            'entry_features_json': features_snapshot or {}
        }
    
    def get_account(self) -> Dict[str, Any]:
        """Get current Alpaca paper account status"""
        headers = {
            'APCA-API-KEY-ID': self.api_key,
            'APCA-API-SECRET-KEY': self.api_secret
        }
        response = requests.get(f"{self.base_url}/v2/account", headers=headers)
        return response.json()
    
    def get_positions(self) -> list:
        """Get current open positions"""
        headers = {
            'APCA-API-KEY-ID': self.api_key,
            'APCA-API-SECRET-KEY': self.api_secret
        }
        response = requests.get(f"{self.base_url}/v2/positions", headers=headers)
        return response.json()
    
    def close_position(self, ticker: str) -> Dict[str, Any]:
        """Close a position"""
        headers = {
            'APCA-API-KEY-ID': self.api_key,
            'APCA-API-SECRET-KEY': self.api_secret
        }
        response = requests.delete(
            f"{self.base_url}/v2/positions/{ticker}",
            headers=headers
        )
        return response.json() if response.status_code == 200 else None
