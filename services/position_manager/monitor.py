"""
Position monitoring logic
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetAssetsRequest
from alpaca.data.requests import StockLatestQuoteRequest
import pytz

from config import (
    ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_BASE_URL,
    DAY_TRADE_CLOSE_TIME, OPTIONS_EXPIRY_WARNING_HOURS,
    ACCOUNT_NAME,
)
import db
from bar_fetcher import OptionBarFetcher
from eod_config import EODConfig
from eod_engine import (
    EODExitEngine, get_current_window, get_vix_regime, compute_theta_score,
)
from eod_models import OvernightCriteria, VIXRegime
from close_loop import CloseLoopMonitor
from earnings_client import EarningsCalendarClient

logger = logging.getLogger(__name__)

# Phase 17: Global bar fetcher (initialized in main)
bar_fetcher = None

# EOD engine components (initialized per monitoring cycle)
_eod_engine: Optional[EODExitEngine] = None
_close_loop_monitor: Optional[CloseLoopMonitor] = None


def is_market_open() -> bool:
    """Check if US stock market is currently open (9:30 AM - 4:00 PM ET)."""
    et = get_eastern_time()
    from datetime import time
    market_open = time(9, 30)
    market_close = time(16, 0)
    # Weekday check (0=Mon, 6=Sun)
    if et.weekday() >= 5:
        return False
    return market_open <= et.time() <= market_close


def _init_eod_engine(db_conn=None) -> Optional[EODExitEngine]:
    """
    Initialize EOD engine for this monitoring cycle.
    Loads fresh config, VIX regime, and earnings cache.
    """
    try:
        account_tier = 'tiny' if ACCOUNT_NAME == 'tiny' else 'large'
        config = EODConfig.for_account_tier(account_tier)

        # Try to load VIX regime from DB
        vix_regime = None
        if db_conn:
            try:
                vix_regime = get_vix_regime(db_conn)
            except Exception as e:
                logger.warning(f"Could not load VIX regime: {e}")

        # Initialize earnings client
        earnings_client = None
        try:
            earnings_client = EarningsCalendarClient(ALPACA_API_KEY, ALPACA_API_SECRET)
        except Exception as e:
            logger.warning(f"Could not initialize earnings client: {e}")

        engine = EODExitEngine(
            config=config,
            account_tier=account_tier,
            earnings_client=earnings_client,
            vix_regime=vix_regime,
        )
        return engine
    except Exception as e:
        logger.error(f"Failed to initialize EOD engine: {e}")
        return None


def _log_eod_decision(decision) -> None:
    """Log an EOD decision event to position_events."""
    try:
        event_type = 'eod_decision'
        payload = decision.to_event_payload()
        db.log_position_event(decision.position_id, event_type, payload)

        if decision.decision == 'hold' and decision.strategy_type == 'swing_trade':
            db.log_position_event(decision.position_id, 'overnight_hold', payload)
    except Exception as e:
        logger.error(f"Failed to log EOD decision for position {decision.position_id}: {e}")

# Initialize Alpaca client
alpaca_client = TradingClient(
    api_key=ALPACA_API_KEY,
    secret_key=ALPACA_API_SECRET,
    paper=True if 'paper' in ALPACA_BASE_URL else False
)


def get_eastern_time() -> datetime:
    """Get current time in Eastern timezone"""
    eastern = pytz.timezone('America/New_York')
    return datetime.now(eastern)


def _get_option_quote(option_symbol: str) -> Optional[float]:
    """
    Get live option mid-price from Alpaca Market Data API.
    Uses /v1beta1/options/quotes/latest (NOT the positions API which returns stale data).
    """
    import requests as req
    url = f"https://data.alpaca.markets/v1beta1/options/quotes/latest"
    headers = {
        'APCA-API-KEY-ID': ALPACA_API_KEY,
        'APCA-API-SECRET-KEY': ALPACA_API_SECRET
    }
    resp = req.get(url, headers=headers, params={'symbols': option_symbol}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    quote = data.get('quotes', {}).get(option_symbol)
    if not quote:
        return None
    bid = float(quote.get('bp', 0))
    ask = float(quote.get('ap', 0))
    if bid > 0 and ask > 0:
        return (bid + ask) / 2
    # If no bid/ask, try last trade via bars
    return None


def get_current_price(position: Dict[str, Any]) -> Optional[float]:
    """
    Get current market price for a position.
    Stocks: SDK quote API (bid/ask mid).
    Options: Alpaca Market Data latest quote API (bid/ask mid).
    """
    try:
        if position['instrument_type'] == 'STOCK':
            request = StockLatestQuoteRequest(symbol_or_symbols=position['ticker'])
            latest_quote = alpaca_client.get_stock_latest_quote(request)
            if position['ticker'] in latest_quote:
                quote = latest_quote[position['ticker']]
                return (quote.bid_price + quote.ask_price) / 2
        else:  # OPTIONS (CALL or PUT)
            option_symbol = position.get('option_symbol') or position['ticker']
            price = _get_option_quote(option_symbol)
            if price is not None:
                last_price = position.get('current_price')
                logger.info(f"Position {position['id']} ({option_symbol}): ${last_price} → ${price:.2f}")
                return price
            # Fallback: latest bar close from bar_fetcher
            if bar_fetcher:
                bars = bar_fetcher.fetch_bars_for_symbol(option_symbol, minutes_back=5)
                if bars:
                    price = bars[-1]['close']
                    logger.info(f"Position {position['id']} ({option_symbol}): bar fallback ${price:.2f}")
                    return price
            logger.error(f"No option price available for {option_symbol}")
            return None
        return None
    except Exception as e:
        logger.error(f"Error fetching price for {position.get('ticker')}: {e}")
        return None


def update_position_price(position: Dict[str, Any]) -> bool:
    """
    Update position with current market price and calculate P&L
    Returns: True if successful, False otherwise
    """
    try:
        current_price = get_current_price(position)
        
        if current_price is None:
            logger.warning(f"Could not get price for position {position['id']}")
            return False
        
        # Ensure current_price is float (not Decimal)
        current_price = float(current_price)
        
        # Calculate P&L (side-aware)
        entry_price = float(position['entry_price'])
        quantity = float(position['quantity'])
        multiplier = 100 if position['instrument_type'] in ('CALL', 'PUT') else 1
        side = (position.get('side') or 'long').lower()
        
        if side in ('short', 'sell_short'):
            pnl_dollars = (entry_price - current_price) * quantity * multiplier
            pnl_percent = ((entry_price / current_price) - 1) * 100 if current_price else 0.0
        else:
            pnl_dollars = (current_price - entry_price) * quantity * multiplier
            pnl_percent = ((current_price / entry_price) - 1) * 100 if entry_price else 0.0

        # Update running MFE/MAE (unrealized path extremes)
        best_pnl_pct = float(position.get('best_unrealized_pnl_pct') or 0.0)
        worst_pnl_pct = float(position.get('worst_unrealized_pnl_pct') or 0.0)
        best_pnl_dollars = float(position.get('best_unrealized_pnl_dollars') or 0.0)
        worst_pnl_dollars = float(position.get('worst_unrealized_pnl_dollars') or 0.0)

        best_pnl_pct = max(best_pnl_pct, pnl_percent)
        worst_pnl_pct = min(worst_pnl_pct, pnl_percent)
        best_pnl_dollars = max(best_pnl_dollars, pnl_dollars)
        worst_pnl_dollars = min(worst_pnl_dollars, pnl_dollars)
        
        # Update database
        db.update_position_price(
            position['id'],
            current_price,
            pnl_dollars,
            pnl_percent,
            best_unrealized_pnl_pct=best_pnl_pct,
            worst_unrealized_pnl_pct=worst_pnl_pct,
            best_unrealized_pnl_dollars=best_pnl_dollars,
            worst_unrealized_pnl_dollars=worst_pnl_dollars,
            last_mark_price=current_price
        )
        
        # Phase 17: Capture option bars for AI learning
        if position['instrument_type'] in ('CALL', 'PUT') and bar_fetcher:
            try:
                option_symbol = position.get('option_symbol') or position['ticker']
                bars = bar_fetcher.fetch_bars_for_symbol(option_symbol, minutes_back=5)
                
                if bars:
                    bars_stored = db.store_option_bars(bars)
                    peak = max(b['high'] for b in bars)
                    lowest = min(b['low'] for b in bars)
                    
                    db.update_position_bar_metadata(
                        position['id'],
                        bars_count=bars_stored,
                        peak_premium=peak,
                        lowest_premium=lowest
                    )
                    logger.debug(f"Captured {bars_stored} bars for position {position['id']}")
            except Exception as e:
                # Don't fail position update if bar capture fails
                logger.warning(f"Bar capture failed for position {position['id']}: {e}")
        
        # Log the update
        db.log_position_event(
            position['id'],
            'price_update',
            {
                'price': current_price,
                'pnl_dollars': pnl_dollars,
                'pnl_percent': pnl_percent
            }
        )
        
        # Update position dict with new values
        position['current_price'] = current_price
        position['current_pnl_dollars'] = pnl_dollars
        position['current_pnl_percent'] = pnl_percent
        position['best_unrealized_pnl_pct'] = best_pnl_pct
        position['worst_unrealized_pnl_pct'] = worst_pnl_pct
        position['best_unrealized_pnl_dollars'] = best_pnl_dollars
        position['worst_unrealized_pnl_dollars'] = worst_pnl_dollars
        
        return True
        
    except Exception as e:
        logger.error(f"Error updating price for position {position['id']}: {e}")
        return False


def check_exit_conditions(position: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Check all exit conditions for a position
    Returns list of triggered exits sorted by priority
    """
    # Don't trigger exits when market is closed — orders won't fill
    # and we'll just create stuck 'closing' records
    if not is_market_open():
        logger.debug(f"Market closed, skipping exit checks for position {position['id']}")
        return []
    
    exits_to_trigger = []
    
    # NEW: Check trailing stops (Phase 3)
    trailing_exit = check_trailing_stop(position)
    if trailing_exit:
        exits_to_trigger.append(trailing_exit)
    
    # CRITICAL FIX: For options, use ONLY option-specific exit logic
    # to avoid duplicate exit checking (was causing premature exits)
    if position['instrument_type'] in ('CALL', 'PUT'):
        option_exits = check_exit_conditions_options(position)
        exits_to_trigger.extend(option_exits)
        
        # Still check time-based exits (not price-based)
        exits_to_trigger.extend(check_time_based_exits(position))
        
        # DISABLED 2026-02-05: Partial exits broken ("qty must be > 0" errors)
        # TODO: Fix partial exit logic before re-enabling
        # partial_exit = check_partial_exit(position)
        # if partial_exit:
        #     exits_to_trigger.append(partial_exit)
        
        # Sort and return - DON'T check price-based stops below
        return sorted(exits_to_trigger, key=lambda x: x['priority'])
    
    # For STOCKS: Use original price-based exit logic
    current_price = float(position['current_price'])
    stop_loss = float(position['stop_loss'])
    take_profit = float(position['take_profit'])
    
    # Check 1: Stop loss hit
    if current_price <= stop_loss:
        exits_to_trigger.append({
            'reason': 'stop_loss',
            'priority': 1,
            'message': f'Stop loss hit: ${current_price:.2f} <= ${stop_loss:.2f}'
        })
    
    # Check 2: Take profit hit
    if current_price >= take_profit:
        exits_to_trigger.append({
            'reason': 'take_profit',
            'priority': 1,
            'message': f'Take profit hit: ${current_price:.2f} >= ${take_profit:.2f}'
        })
    
    # DISABLED 2026-02-05: Partial exits broken  
    # partial_exit = check_partial_exit(position)
    # if partial_exit:
    #     exits_to_trigger.append(partial_exit)
    
    # Time-based exits (applies to both stocks and options)
    exits_to_trigger.extend(check_time_based_exits(position))
    
    # Check 6: Bracket order verification
    if not position['bracket_order_accepted']:
        # Check if bracket orders were placed after execution
        has_brackets = verify_bracket_orders(position)
        
        if not has_brackets:
            exits_to_trigger.append({
                'reason': 'missing_brackets',
                'priority': 1,
                'message': 'Bracket orders not found, forcing manual exit'
            })
        else:
            # Update DB that brackets are now accepted
            db.update_bracket_orders(
                position['id'],
                position.get('stop_order_id'),
                position.get('target_order_id'),
                True
            )
    
    # Sort by priority (1 = highest priority)
    return sorted(exits_to_trigger, key=lambda x: x['priority'])


def verify_bracket_orders(position: Dict[str, Any]) -> bool:
    """
    Verify that bracket orders exist in Alpaca
    """
    try:
        # Get all open orders
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus
        request = GetOrdersRequest(status=QueryOrderStatus.OPEN)
        orders = alpaca_client.get_orders(filter=request)
        
        stop_order_id = position.get('stop_order_id')
        target_order_id = position.get('target_order_id')
        
        if not stop_order_id or not target_order_id:
            return False
        
        # Check if both orders exist
        order_ids = [order.id for order in orders]
        
        has_stop = stop_order_id in order_ids
        has_target = target_order_id in order_ids
        
        if has_stop and has_target:
            logger.info(f"Position {position['id']} bracket orders verified")
            return True
        
        if not has_stop:
            logger.warning(f"Position {position['id']} missing stop order {stop_order_id}")
        if not has_target:
            logger.warning(f"Position {position['id']} missing target order {target_order_id}")
        
        return False
        
    except Exception as e:
        logger.error(f"Error verifying bracket orders for position {position['id']}: {e}")
        return False


def check_partial_fill(position: Dict[str, Any]) -> Optional[float]:
    """
    Check if position has partial fill by querying Alpaca
    Returns actual quantity if different from expected, None otherwise
    """
    try:
        # Get position from Alpaca
        alpaca_position = alpaca_client.get_open_position(position['ticker'])
        
        if alpaca_position:
            actual_qty = float(alpaca_position.qty)
            expected_qty = float(position['quantity'])
            
            if abs(actual_qty - expected_qty) > 0.01:  # Allow for rounding
                logger.warning(
                    f"Partial fill detected for position {position['id']}: "
                    f"expected {expected_qty}, got {actual_qty}"
                )
                return actual_qty
        
        return None
        
    except Exception as e:
        # Position may not exist if fully filled then closed
        logger.debug(f"Could not check partial fill for position {position['id']}: {e}")
        return None


def check_time_based_exits(position: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Check time-based exit conditions (applies to both stocks and options)
    Separated from price-based exits to avoid duplication
    """
    exits = []
    
    try:
        # EOD Exit Engine: Strategy-aware, P&L-aware graduated close windows
        # Replaces the blanket market_close_protection rule
        if position['instrument_type'] in ('CALL', 'PUT'):
            now_et = get_eastern_time()
            config = EODConfig.for_account_tier('tiny' if ACCOUNT_NAME == 'tiny' else 'large')
            current_window = get_current_window(now_et.time(), config)

            if current_window is not None and _eod_engine is not None:
                decision = _eod_engine.evaluate_position(position, current_window)
                _log_eod_decision(decision)

                if decision.decision == 'close':
                    exits.append({
                        'reason': decision.close_reason or 'EOD_EXIT',
                        'priority': 1,
                        'message': f'EOD exit: {decision.close_reason} '
                                   f'(window {decision.window_index}, '
                                   f'P&L {decision.pnl_pct:.1f}%)',
                        'exit_reason_norm': 'EOD_EXIT',
                    })
            elif current_window is not None:
                # Fallback: engine not initialized, use legacy close at final window
                total_windows = len(config.graduated_close_windows)
                if current_window >= total_windows - 1:
                    exits.append({
                        'reason': 'market_close_protection',
                        'priority': 1,
                        'message': 'Closing option before market close (EOD engine unavailable, fallback)',
                    })
        
        # Check 1: Day trade time limit (must close by 3:55 PM ET)
        if position['strategy_type'] == 'day_trade':
            now_et = get_eastern_time()
            close_time = DAY_TRADE_CLOSE_TIME
            
            if now_et.time() >= close_time:
                exits.append({
                    'reason': 'day_trade_close',
                    'priority': 2,
                    'message': f'Day trade must close by {close_time.strftime("%H:%M")} ET'
                })
        
        # Check 2: Max hold time exceeded
        if position['max_hold_minutes']:
            entry_time = position['entry_time']
            if entry_time.tzinfo is None:
                entry_time = entry_time.replace(tzinfo=timezone.utc)
            
            now_utc = datetime.now(timezone.utc)
            hold_minutes = (now_utc - entry_time).total_seconds() / 60
            
            if hold_minutes >= position['max_hold_minutes']:
                exits.append({
                    'reason': 'max_hold_time',
                    'priority': 3,
                    'message': f'Max hold time exceeded: {hold_minutes:.0f} >= {position["max_hold_minutes"]} minutes'
                })
        
        # Check 3: Options expiration risk (close 1 day before expiry)
        if position['expiration_date']:
            exp_date = position['expiration_date']
            if isinstance(exp_date, str):
                exp_date = datetime.strptime(exp_date, '%Y-%m-%d').date()
            
            # Convert to datetime at market close (4 PM ET = 21:00 UTC)
            exp_datetime = datetime.combine(exp_date, datetime.min.time()).replace(
                hour=21, minute=0, tzinfo=timezone.utc
            )
            
            now_utc = datetime.now(timezone.utc)
            hours_to_expiry = (exp_datetime - now_utc).total_seconds() / 3600
            
            if hours_to_expiry <= OPTIONS_EXPIRY_WARNING_HOURS:
                exits.append({
                    'reason': 'expiration_risk',
                    'priority': 2,
                    'message': f'Options expiring in {hours_to_expiry:.1f} hours'
                })
        
        return exits
        
    except Exception as e:
        logger.error(f"Error checking time-based exits for position {position['id']}: {e}")
        return []


def check_trailing_stop(position: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Trailing stop: Lock in 75% of peak gains
    Updates peak price as position moves up
    
    NOTE: Disabled until peak_price column is added to database
    """
    # Enabled 2026-02-04 - Trailing stops active!
    # If peak_price column doesn't exist, will get clear error
    
    try:
        current_price = float(position['current_price'])
        entry_price = float(position['entry_price'])
        peak_price = position.get('peak_price')
        
        # Initialize peak if not set
        if peak_price is None:
            peak_price = current_price
            db.update_position_peak(position['id'], peak_price)
        else:
            peak_price = float(peak_price)
        
        # Update peak if new high
        if current_price > peak_price:
            peak_price = current_price
            db.update_position_peak(position['id'], peak_price)
            logger.info(f"Position {position['id']} new peak: ${peak_price:.2f}")
        
        # Calculate trailing stop (lock in 75% of gains from peak)
        peak_gain = peak_price - entry_price
        
        if peak_gain > 0:
            trailing_stop = peak_price - (peak_gain * 0.25)  # Keep 75%
            
            # Update DB with trailing stop price
            db.update_position_trailing_stop(position['id'], trailing_stop)
            
            # Check if trailing stop hit
            if current_price <= trailing_stop:
                locked_gain = current_price - entry_price
                locked_pct = (locked_gain / entry_price) * 100
                
                return {
                    'reason': 'trailing_stop',
                    'priority': 1,
                    'message': f'Trailing stop hit: ${current_price:.2f} <= ${trailing_stop:.2f}, locked {locked_pct:.1f}% gain'
                }
        
        return None
        
    except Exception as e:
        logger.error(f"Error checking trailing stop for position {position['id']}: {e}")
        return None


def check_exit_conditions_options(position: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Option-specific exit conditions
    Uses option premium P&L instead of underlying stock price
    
    CRITICAL FIX (2026-02-04): Widened stops from -25%/+50% to -40%/+80%
    and added 30-minute minimum hold time to prevent premature exits
    """
    exits = []
    
    try:
        current_price = float(position['current_price'])
        entry_price = float(position['entry_price'])
        
        # Calculate option P&L percentage
        option_pnl_pct = ((current_price / entry_price) - 1) * 100
        
        # Calculate hold time
        entry_time = position['entry_time']
        if entry_time.tzinfo is None:
            entry_time = entry_time.replace(tzinfo=timezone.utc)
        now_utc = datetime.now(timezone.utc)
        hold_minutes = (now_utc - entry_time).total_seconds() / 60
        
        # MINIMUM HOLD TIME: Don't exit options in first 30 minutes
        # Options premiums are volatile - give them room to breathe
        # Exception: Allow exit if catastrophic loss (>50%)
        if hold_minutes < 30:
            if option_pnl_pct > -50:
                logger.debug(
                    f"Position {position['id']}: Too early to exit "
                    f"(held {hold_minutes:.1f} min, P&L {option_pnl_pct:.1f}%)"
                )
                return []  # Don't exit yet - too early
            else:
                logger.warning(
                    f"Position {position['id']}: Catastrophic loss {option_pnl_pct:.1f}%, "
                    f"exiting early at {hold_minutes:.1f} minutes"
                )
        
        # Exit 1: Option profit target (+80%, was +50%)
        # Widened to account for option premium volatility
        if option_pnl_pct >= 80:
            exits.append({
                'reason': 'option_profit_target',
                'priority': 1,
                'message': f'Option +{option_pnl_pct:.1f}% profit (target +80%)'
            })
        
        # Exit 2: Option stop loss (-60%, was -40%)
        # UPDATED 2026-02-07: Widened based on backtest showing premature exits
        # Analysis: 5 trades stopped at -40% then recovered to positive within 60 min
        if option_pnl_pct <= -60:
            exits.append({
                'reason': 'option_stop_loss',
                'priority': 1,
                'message': f'Option {option_pnl_pct:.1f}% loss (stop -60%)'
            })
        
        # Exit 3: Time decay risk (theta burn) - only for very near expiry with losses
        # UPDATED 2026-02-13: Relaxed from 7 DTE to 2 DTE. The old 7-day threshold
        # was closing almost every weekly option immediately, locking in small losses.
        # Now only triggers when expiry is imminent (<=2 days) and position is losing.
        if position['expiration_date']:
            exp_date = position['expiration_date']
            if isinstance(exp_date, str):
                from datetime import date
                exp_date = datetime.strptime(exp_date, '%Y-%m-%d').date()
            
            days_to_expiry = (exp_date - datetime.now().date()).days
            
            # Only force-close for theta if:
            # - 2 days or less to expiry AND not profitable (< 0%)
            # - OR 1 day to expiry AND less than +10% profit
            if days_to_expiry <= 1 and option_pnl_pct < 10:
                exits.append({
                    'reason': 'theta_decay_risk',
                    'priority': 2,
                    'message': f'{days_to_expiry} days to expiry, P&L {option_pnl_pct:.1f}% (close imminent)'
                })
            elif days_to_expiry <= 2 and option_pnl_pct < 0:
                exits.append({
                    'reason': 'theta_decay_risk',
                    'priority': 2,
                    'message': f'{days_to_expiry} days to expiry, losing {option_pnl_pct:.1f}%'
                })
        
        return exits
        
    except Exception as e:
        logger.error(f"Error checking option exits for position {position['id']}: {e}")
        return []


def check_partial_exit(position: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Check for partial profit-taking opportunities
    - Take 50% off at +50% profit
    - Take 25% more at +75% profit
    - Let final 25% ride
    """
    try:
        pnl_pct = float(position.get('current_pnl_percent', 0))
        quantity = float(position['quantity'])
        original_qty = position.get('original_quantity', quantity)
        
        if original_qty is None:
            original_qty = quantity
        else:
            original_qty = float(original_qty)
        
        # Calculate percentage remaining
        pct_remaining = quantity / original_qty if original_qty > 0 else 1.0
        
        # First partial: 50% at +50% profit
        if pnl_pct >= 50 and pct_remaining > 0.75:
            return {
                'type': 'partial',
                'quantity': int(original_qty * 0.50),
                'reason': 'first_profit_target',
                'priority': 1,
                'message': f'Taking 50% off at +{pnl_pct:.1f}% profit'
            }
        
        # Second partial: 25% more at +75% profit
        if pnl_pct >= 75 and pct_remaining > 0.35:
            return {
                'type': 'partial',
                'quantity': int(original_qty * 0.25),
                'reason': 'second_profit_target',
                'priority': 1,
                'message': f'Taking 25% more off at +{pnl_pct:.1f}% profit'
            }
        
        return None
        
    except Exception as e:
        logger.error(f"Error checking partial exit for position {position['id']}: {e}")
        return None


def sync_from_alpaca_positions() -> int:
    """
    Sync positions directly from Alpaca API (NEW - Phase 3)
    This catches ALL positions including manual trades and logging gaps

    ALSO closes phantom positions (in DB but not in Alpaca)

    Returns: Number of positions synced
    """
    try:
        logger.info("Syncing positions from Alpaca API...")

        # Get all open positions from Alpaca
        alpaca_positions = list(alpaca_client.get_all_positions())

        # Get current account name
        from config import ACCOUNT_NAME

        # Build set of symbols in Alpaca
        alpaca_symbols = {pos.symbol for pos in alpaca_positions}

        if not alpaca_positions:
            logger.info("No positions found in Alpaca")
        else:
            logger.info(f"Found {len(alpaca_positions)} position(s) in Alpaca")

        # Check for phantom positions (in DB but not in Alpaca)
        db_positions = db.get_open_positions(account_name=ACCOUNT_NAME)
        phantoms_closed = 0

        for db_pos in db_positions:
            # Get the symbol to compare (option_symbol for options, ticker for stocks)
            db_symbol = db_pos.get('option_symbol') or db_pos['ticker']

            if db_symbol not in alpaca_symbols:
                # Phantom position - exists in DB but not in Alpaca
                logger.warning(
                    f"⚠ Phantom position detected: {db_symbol} (ID {db_pos['id']}) "
                    f"exists in DB but not in Alpaca - closing"
                )

                # Close the phantom position
                try:
                    db.close_position(
                        db_pos['id'],
                        close_reason='phantom_reconciliation',
                        exit_price=db_pos.get('current_price', db_pos['entry_price'])
                    )

                    db.log_position_event(
                        db_pos['id'],
                        'phantom_closed',
                        {
                            'reason': 'Position exists in DB but not in Alpaca',
                            'symbol': db_symbol,
                            'account_name': ACCOUNT_NAME
                        }
                    )

                    phantoms_closed += 1
                    logger.info(f"✓ Closed phantom position {db_symbol} (ID {db_pos['id']})")

                except Exception as e:
                    logger.error(f"Failed to close phantom position {db_symbol}: {e}")

        if phantoms_closed > 0:
            logger.warning(f"⚠ Closed {phantoms_closed} phantom position(s)")

        # Now sync positions FROM Alpaca TO database
        synced_count = 0
        for alpaca_pos in alpaca_positions:
            try:
                symbol = alpaca_pos.symbol

                # Check if already tracked FOR THIS ACCOUNT
                # CRITICAL: Must filter by account_name to avoid cross-account collisions
                # Without this, tiny PM sees large account's AMZN and skips syncing tiny's AMZN
                existing = db.get_position_by_symbol(symbol, account_name=ACCOUNT_NAME)

                if existing:
                    logger.debug(f"Position {symbol} already tracked (ID {existing['id']})")
                    continue

                # Determine if stock or option
                is_option = len(symbol) > 10  # Options have long symbols like META260209C00722500

                if is_option:
                    # Parse option symbol (e.g., META260209C00722500)
                    # Format: TICKER + YYMMDD + C/P + 00000000 (strike * 1000)
                    strike_str = symbol[-8:]
                    opt_type = symbol[-9]
                    exp_str = symbol[-15:-9]
                    ticker = symbol[:-15].strip()

                    strike_price = int(strike_str) / 1000.0
                    exp_date = f"20{exp_str[0:2]}-{exp_str[2:4]}-{exp_str[4:6]}"
                    instrument_type = 'CALL' if opt_type == 'C' else 'PUT'
                else:
                    ticker = symbol
                    strike_price = None
                    exp_date = None
                    instrument_type = 'STOCK'

                # Get position details from Alpaca
                qty = float(alpaca_pos.qty)
                entry_price = float(alpaca_pos.avg_entry_price)
                current_price = float(alpaca_pos.current_price)

                # Calculate stops
                # UPDATED 2026-02-07: Widened to -60% based on backtest analysis
                # Backtest showed: 5 trades stopped at -40% then recovered to positive
                if is_option:
                    stop_loss = entry_price * 0.40  # -60% for options (was 0.60 = -40%)
                    take_profit = entry_price * 1.80  # +80% for options
                else:
                    stop_loss = entry_price * 0.98  # -2% for stock
                    take_profit = entry_price * 1.03  # +3% for stock

                # Create active_position with correct account name
                position_id = db.create_position_from_alpaca(
                    ticker=ticker,
                    instrument_type=instrument_type,
                    side='long',  # All our positions are long
                    quantity=qty,
                    entry_price=entry_price,
                    current_price=current_price,
                    strike_price=strike_price,
                    expiration_date=exp_date,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    option_symbol=symbol if is_option else None,
                    account_name=ACCOUNT_NAME  # Pass correct account name
                )

                logger.info(
                    f"✓ Synced from Alpaca: {symbol} "
                    f"({instrument_type} @ ${entry_price:.2f}, qty {qty}) "
                    f"- position ID {position_id}"
                )
                synced_count += 1

                # Log creation event
                db.log_position_event(
                    position_id,
                    'synced_from_alpaca',
                    {
                        'ticker': ticker,
                        'instrument_type': instrument_type,
                        'entry_price': entry_price,
                        'quantity': qty,
                        'current_price': current_price
                    }
                )

            except Exception as e:
                logger.error(f"Error syncing position {alpaca_pos.symbol}: {e}", exc_info=True)
                continue

        if synced_count > 0:
            logger.info(f"✓ Synced {synced_count} position(s) from Alpaca API")
        elif not phantoms_closed:
            logger.info("All positions in sync")

        return synced_count

    except Exception as e:
        logger.error(f"Error syncing from Alpaca API: {e}", exc_info=True)
        return 0



def sync_new_positions(since_time: datetime, account_name: str = 'large') -> int:
    """
    Sync new positions from filled executions
    
    Args:
        since_time: Only sync executions after this time
        account_name: Filter by account name (e.g., 'large', 'tiny')
    
    Returns: Number of positions created
    """
    try:
        # Get filled executions that aren't tracked yet
        # CRITICAL: Pass account_name to filter by this instance's account
        new_executions = db.get_filled_executions_since(since_time, account_name)
        
        count = 0
        for execution in new_executions:
            try:
                position_id = db.create_active_position(execution)
                logger.info(
                    f"Created active position {position_id} for "
                    f"{execution['ticker']} {execution['instrument_type']} "
                    f"(account: {account_name})"
                )
                count += 1
                
                # Log creation event
                db.log_position_event(
                    position_id,
                    'created',
                    {
                        'execution_id': execution['id'],
                        'ticker': execution['ticker'],
                        'instrument_type': execution['instrument_type'],
                        'entry_price': float(execution['entry_price']),
                        'quantity': float(execution['quantity']),
                        'account_name': account_name
                    }
                )
                
            except Exception as e:
                logger.error(f"Failed to create position for execution {execution['id']}: {e}")
        
        return count
        
    except Exception as e:
        logger.error(f"Error syncing new positions: {e}")
        return 0


def log_overnight_outcomes(positions: List[Dict[str, Any]]) -> int:
    """
    R6.4: On first monitoring cycle of each trading day, log overnight outcomes.
    Compares previous EOD price to current open price for positions held overnight.
    Returns number of outcomes logged.
    """
    count = 0
    for pos in positions:
        try:
            # Only positions that were held overnight (have overnight_hold event)
            # and haven't had an outcome logged yet today
            pos_id = pos.get('id', 0)
            entry_price = float(pos.get('entry_price', 0) or 0)
            current_price = float(pos.get('current_price', 0) or 0)

            if entry_price <= 0 or current_price <= 0:
                continue

            # Check if this position has an overnight_hold event (was held overnight)
            # We approximate by checking if the position was created before today
            created_at = pos.get('created_at')
            if created_at is None:
                continue

            if isinstance(created_at, str):
                try:
                    created_at = datetime.fromisoformat(created_at)
                except ValueError:
                    continue

            now_utc = datetime.now(timezone.utc)
            if created_at.date() >= now_utc.date():
                continue  # Created today, not an overnight hold

            # Calculate overnight P&L (approximate: entry → current open)
            overnight_pnl_pct = ((current_price - entry_price) / entry_price) * 100
            overnight_pnl_dollars = (current_price - entry_price) * float(pos.get('quantity', 1) or 1)

            db.log_position_event(pos_id, 'overnight_outcome', {
                'position_id': pos_id,
                'close_price_eod': entry_price,  # approximate
                'open_price_next_day': current_price,
                'overnight_pnl_pct': round(overnight_pnl_pct, 2),
                'overnight_pnl_dollars': round(overnight_pnl_dollars, 2),
            })
            count += 1

        except Exception as e:
            logger.error(f"Failed to log overnight outcome for position {pos.get('id')}: {e}")

    return count
