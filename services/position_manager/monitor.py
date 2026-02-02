"""
Position monitoring logic
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from alpaca.trading.client import TradingClient
from alpaca.data.requests import StockLatestQuoteRequest
import pytz

from config import (
    ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_BASE_URL,
    DAY_TRADE_CLOSE_TIME, OPTIONS_EXPIRY_WARNING_HOURS
)
import db
from bar_fetcher import OptionBarFetcher

logger = logging.getLogger(__name__)

# Phase 17: Global bar fetcher (initialized in main)
bar_fetcher = None

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


def get_current_price(position: Dict[str, Any]) -> Optional[float]:
    """
    Get current market price for a position
    """
    try:
        if position['instrument_type'] == 'STOCK':
            # Get latest stock quote
            request = StockLatestQuoteRequest(symbol_or_symbols=position['ticker'])
            latest_quote = alpaca_client.get_stock_latest_quote(request)
            
            if position['ticker'] in latest_quote:
                quote = latest_quote[position['ticker']]
                # Use mid-price between bid and ask
                return (quote.bid_price + quote.ask_price) / 2
            
        else:  # OPTIONS (CALL or PUT)
            # For options, we need to query the options API
            # This is more complex - use Alpaca's options data API
            try:
                # Get option position from Alpaca
                alpaca_position = alpaca_client.get_open_position(position['ticker'])
                if alpaca_position:
                    return float(alpaca_position.current_price)
            except Exception as e:
                logger.warning(f"Could not get option price from Alpaca position: {e}")
                # Fallback: use last known price or entry price
                return position.get('current_price', position['entry_price'])
        
        return None
        
    except Exception as e:
        logger.error(f"Error fetching price for {position['ticker']}: {e}")
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
        
        # Calculate P&L
        entry_price = float(position['entry_price'])
        quantity = float(position['quantity'])
        
        # For long positions (which is all we do currently)
        pnl_dollars = (current_price - entry_price) * quantity
        pnl_percent = ((current_price / entry_price) - 1) * 100
        
        # Update database
        db.update_position_price(
            position['id'],
            current_price,
            pnl_dollars,
            pnl_percent
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
        
        return True
        
    except Exception as e:
        logger.error(f"Error updating price for position {position['id']}: {e}")
        return False


def check_exit_conditions(position: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Check all exit conditions for a position
    Returns list of triggered exits sorted by priority
    """
    exits_to_trigger = []
    
    # NEW: Check trailing stops (Phase 3)
    trailing_exit = check_trailing_stop(position)
    if trailing_exit:
        exits_to_trigger.append(trailing_exit)
    
    # NEW: Check option-specific exits if this is an options position (Phase 3)
    if position['instrument_type'] in ('CALL', 'PUT'):
        option_exits = check_exit_conditions_options(position)
        exits_to_trigger.extend(option_exits)
    
    # NEW: Check for partial exits (Phase 4)
    partial_exit = check_partial_exit(position)
    if partial_exit:
        exits_to_trigger.append(partial_exit)
    
    # Original exits (still check these)
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
    
    # Check 3: Day trade time limit (must close by 3:55 PM ET)
    if position['strategy_type'] == 'day_trade':
        now_et = get_eastern_time()
        close_time = DAY_TRADE_CLOSE_TIME
        
        if now_et.time() >= close_time:
            exits_to_trigger.append({
                'reason': 'day_trade_close',
                'priority': 2,
                'message': f'Day trade must close by {close_time.strftime("%H:%M")} ET'
            })
    
    # Check 4: Max hold time exceeded
    if position['max_hold_minutes']:
        entry_time = position['entry_time']
        if entry_time.tzinfo is None:
            entry_time = entry_time.replace(tzinfo=timezone.utc)
        
        now_utc = datetime.now(timezone.utc)
        hold_minutes = (now_utc - entry_time).total_seconds() / 60
        
        if hold_minutes >= position['max_hold_minutes']:
            exits_to_trigger.append({
                'reason': 'max_hold_time',
                'priority': 3,
                'message': f'Max hold time exceeded: {hold_minutes:.0f} >= {position["max_hold_minutes"]} minutes'
            })
    
    # Check 5: Options expiration risk (close 1 day before expiry)
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
            exits_to_trigger.append({
                'reason': 'expiration_risk',
                'priority': 2,
                'message': f'Options expiring in {hours_to_expiry:.1f} hours'
            })
    
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
        orders = alpaca_client.get_orders(status='open')
        
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


def check_trailing_stop(position: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Trailing stop: Lock in 75% of peak gains
    Updates peak price as position moves up
    """
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
    """
    exits = []
    
    try:
        current_price = float(position['current_price'])
        entry_price = float(position['entry_price'])
        
        # Calculate option P&L percentage
        option_pnl_pct = ((current_price / entry_price) - 1) * 100
        
        # Exit 1: Option profit target (+50%)
        if option_pnl_pct >= 50:
            exits.append({
                'reason': 'option_profit_target',
                'priority': 1,
                'message': f'Option +{option_pnl_pct:.1f}% profit (target +50%)'
            })
        
        # Exit 2: Option stop loss (-25%)
        if option_pnl_pct <= -25:
            exits.append({
                'reason': 'option_stop_loss',
                'priority': 1,
                'message': f'Option {option_pnl_pct:.1f}% loss (stop -25%)'
            })
        
        # Exit 3: Time decay risk (theta burn)
        if position['expiration_date']:
            exp_date = position['expiration_date']
            if isinstance(exp_date, str):
                from datetime import date
                exp_date = datetime.strptime(exp_date, '%Y-%m-%d').date()
            
            days_to_expiry = (exp_date - datetime.now().date()).days
            
            # If < 7 days to expiry and not profitable, exit to avoid theta decay
            if days_to_expiry <= 7 and option_pnl_pct < 20:
                exits.append({
                    'reason': 'theta_decay_risk',
                    'priority': 2,
                    'message': f'{days_to_expiry} days to expiry, only +{option_pnl_pct:.1f}% profit'
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
    
    Returns: Number of positions synced
    """
    try:
        logger.info("Syncing positions from Alpaca API...")
        
        # Get all open positions from Alpaca
        alpaca_positions = alpaca_client.get_all_positions()
        
        if not alpaca_positions:
            logger.info("No positions found in Alpaca")
            return 0
        
        logger.info(f"Found {len(alpaca_positions)} position(s) in Alpaca")
        
        synced_count = 0
        for alpaca_pos in alpaca_positions:
            try:
                symbol = alpaca_pos.symbol
                
                # Check if already tracked
                existing = db.get_position_by_symbol(symbol)
                
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
                
                # Calculate stops (use 25% for options, 2% for stock)
                if is_option:
                    stop_loss = entry_price * 0.75  # -25% for options
                    take_profit = entry_price * 1.50  # +50% for options
                else:
                    stop_loss = entry_price * 0.98  # -2% for stock
                    take_profit = entry_price * 1.03  # +3% for stock
                
                # Create active_position
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
                    option_symbol=symbol if is_option else None
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
        else:
            logger.info("All Alpaca positions already tracked")
        
        return synced_count
        
    except Exception as e:
        logger.error(f"Error syncing from Alpaca API: {e}", exc_info=True)
        return 0


def sync_new_positions(since_time: datetime) -> int:
    """
    Sync new positions from filled executions
    Returns number of positions created
    """
    try:
        # Get filled executions that aren't tracked yet
        new_executions = db.get_filled_executions_since(since_time)
        
        count = 0
        for execution in new_executions:
            try:
                position_id = db.create_active_position(execution)
                logger.info(
                    f"Created active position {position_id} for "
                    f"{execution['ticker']} {execution['instrument_type']}"
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
                        'quantity': float(execution['quantity'])
                    }
                )
                
            except Exception as e:
                logger.error(f"Failed to create position for execution {execution['id']}: {e}")
        
        return count
        
    except Exception as e:
        logger.error(f"Error syncing new positions: {e}")
        return 0
