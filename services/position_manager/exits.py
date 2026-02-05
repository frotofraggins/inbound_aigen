"""
Exit enforcement logic
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, ClosePositionRequest
from alpaca.trading.enums import OrderSide, TimeInForce

from config import ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_BASE_URL
import db

logger = logging.getLogger(__name__)

# Initialize Alpaca client
alpaca_client = TradingClient(
    api_key=ALPACA_API_KEY,
    secret_key=ALPACA_API_SECRET,
    paper=True if 'paper' in ALPACA_BASE_URL else False
)

EXIT_REASON_MAP = {
    'take_profit': 'tp',
    'option_profit_target': 'tp',
    'stop_loss': 'sl',
    'option_stop_loss': 'sl',
    'trailing_stop': 'trail',
    'day_trade_close': 'time_stop',
    'max_hold_time': 'time_stop',
    'expiration_risk': 'expiry_risk',
    'theta_decay_risk': 'theta_decay',
    'missing_brackets': 'forced_close_missing_bracket',
    'manual_close': 'manual'
}


def normalize_exit_reason(reason: str) -> str:
    """Normalize exit reason to a fixed label set."""
    return EXIT_REASON_MAP.get(reason, 'manual')


def force_close_position(
    position: Dict[str, Any],
    reason: str,
    priority: int
) -> bool:
    """
    Force close a position immediately using market order
    
    Args:
        position: Position dictionary from database
        reason: Reason for closing (stop_loss, take_profit, etc.)
        priority: Priority level of the exit trigger
    
    Returns:
        True if successful, False otherwise
    """
    try:
        logger.warning(
            f"Forcing close of position {position['id']} "
            f"({position['ticker']} {position['instrument_type']}): {reason}"
        )
        
        # Log the exit trigger
        db.log_position_event(
            position['id'],
            'exit_triggered',
            {
                'reason': reason,
                'priority': priority,
                'current_price': float(position['current_price']),
                'pnl_dollars': float(position.get('current_pnl_dollars', 0)),
                'pnl_percent': float(position.get('current_pnl_percent', 0))
            }
        )
        
        # Update status to closing
        db.update_position_status(position['id'], 'closing')
        
        # Cancel existing bracket orders if they exist
        cancel_bracket_orders(position)
        
        # Submit market order to close position
        order_result = submit_close_order(position)
        
        if order_result:
            # Insert outcome into position_history before closing
            try:
                now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
                entry_time = position.get('entry_time')
                if entry_time and entry_time.tzinfo is None:
                    entry_time = entry_time.replace(tzinfo=timezone.utc)

                entry_price = float(position['entry_price'])
                exit_price = float(position.get('current_price') or entry_price)
                qty = float(position['quantity'])
                multiplier = 100 if position['instrument_type'] in ('CALL', 'PUT') else 1
                side = (position.get('side') or 'long').lower()

                if side in ('short', 'sell_short'):
                    pnl_dollars = (entry_price - exit_price) * qty * multiplier
                    pnl_pct = ((entry_price / exit_price) - 1) * 100 if exit_price else 0.0
                else:
                    pnl_dollars = (exit_price - entry_price) * qty * multiplier
                    pnl_pct = ((exit_price / entry_price) - 1) * 100 if entry_price else 0.0

                holding_seconds = 0
                holding_minutes = 0.0
                if entry_time:
                    holding_seconds = int((now_utc - entry_time).total_seconds())
                    holding_minutes = holding_seconds / 60.0

                best_pnl_pct = float(position.get('best_unrealized_pnl_pct') or 0.0)
                worst_pnl_pct = float(position.get('worst_unrealized_pnl_pct') or 0.0)
                best_pnl_dollars = float(position.get('best_unrealized_pnl_dollars') or 0.0)
                worst_pnl_dollars = float(position.get('worst_unrealized_pnl_dollars') or 0.0)

                instrument_symbol = position.get('option_symbol') or position.get('ticker')
                asset_type = 'option' if position['instrument_type'] in ('CALL', 'PUT') else 'stock'
                if position['instrument_type'] == 'CALL':
                    side_label = 'call'
                elif position['instrument_type'] == 'PUT':
                    side_label = 'put'
                else:
                    side_label = side

                db.insert_position_history({
                    'execution_id': position.get('execution_id'),
                    'execution_uuid': position.get('execution_uuid'),
                    'ticker': position.get('ticker'),
                    'instrument_type': position.get('instrument_type'),
                    'strategy_type': position.get('strategy_type'),
                    'side_label': side_label,
                    'qty': qty,
                    'multiplier': multiplier,
                    'entry_ts': entry_time or now_utc,
                    'exit_ts': now_utc,
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'pnl_dollars': pnl_dollars,
                    'pnl_pct': pnl_pct,
                    'holding_seconds': holding_seconds,
                    'best_pnl_pct': best_pnl_pct,
                    'worst_pnl_pct': worst_pnl_pct,
                    'best_pnl_dollars': best_pnl_dollars,
                    'worst_pnl_dollars': worst_pnl_dollars,
                    'iv_rank_at_entry': position.get('entry_iv_rank'),
                    'spread_at_entry_pct': position.get('entry_spread_pct'),
                    'entry_features_json': position.get('entry_features_json') or {},
                    'exit_reason': normalize_exit_reason(reason)
                })
                logger.info(f"✓ Position history saved for position {position.get('id')}")
            except Exception as e:
                logger.error(f"❌ Position history insert failed: {e}", exc_info=True)
                logger.error(f"   Position ID: {position.get('id')}")
                logger.error(f"   Ticker: {position.get('ticker')}")
                logger.error(f"   Data attempted: {instrument_symbol}, {asset_type}, {side_label}")

            # Mark position as closed
            db.close_position(
                position['id'],
                reason,
                float(position['current_price'])
            )
            
            # Log successful close
            db.log_position_event(
                position['id'],
                'closed',
                {
                    'order_id': order_result.get('order_id'),
                    'reason': reason,
                    'final_price': float(position['current_price']),
                    'final_pnl': float(position.get('current_pnl_dollars', 0))
                }
            )
            
            logger.info(f"Position {position['id']} closed successfully: {reason}")
            return True
        else:
            logger.error(f"Failed to close position {position['id']}")
            return False
            
    except Exception as e:
        logger.error(f"Error force closing position {position['id']}: {e}")
        
        # Log the failure
        db.log_position_event(
            position['id'],
            'close_failed',
            {
                'reason': reason,
                'error': str(e)
            }
        )
        
        return False


def submit_close_order(position: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Submit market order to close a position
    
    Returns:
        Dictionary with order details if successful, None otherwise
    """
    try:
        ticker = position['ticker']
        quantity = abs(float(position['quantity']))
        
        if position['instrument_type'] == 'STOCK':
            # Close stock position
            logger.info(f"Submitting market order to close {quantity} shares of {ticker}")
            
            # For stocks, use ClosePositionRequest for simplicity
            close_request = ClosePositionRequest()
            order = alpaca_client.close_position(ticker)
            
            return {
                'order_id': order.id if hasattr(order, 'id') else None,
                'status': order.status if hasattr(order, 'status') else 'submitted',
                'filled_qty': order.filled_qty if hasattr(order, 'filled_qty') else quantity
            }
            
        else:  # OPTIONS (CALL or PUT)
            # For options, use Alpaca's close_position API
            # This API is specifically designed for closing positions and won't trigger buying power checks
            symbol_to_close = position.get('option_symbol') or ticker
            
            logger.info(
                f"Closing option position via Alpaca close_position API: {symbol_to_close} "
                f"({quantity} contracts of {ticker} {position['instrument_type']})"
            )
            
            try:
                # This API automatically handles closing long/short positions
                # No buying power checks, no position_intent confusion
                result = alpaca_client.close_position(symbol_to_close)
                
                return {
                    'order_id': str(result.id) if hasattr(result, 'id') else None,
                    'status': 'submitted',
                    'filled_qty': quantity
                }
            except Exception as e:
                logger.error(f"Error closing position {symbol_to_close}: {e}")
                return None
            
    except Exception as e:
        logger.error(f"Error submitting close order for position {position['id']}: {e}")
        return None


def cancel_bracket_orders(position: Dict[str, Any]) -> None:
    """
    Cancel existing bracket orders (stop loss and take profit)
    """
    try:
        stop_order_id = position.get('stop_order_id')
        target_order_id = position.get('target_order_id')
        
        if stop_order_id:
            try:
                alpaca_client.cancel_order_by_id(stop_order_id)
                logger.info(f"Cancelled stop order {stop_order_id}")
            except Exception as e:
                logger.warning(f"Could not cancel stop order {stop_order_id}: {e}")
        
        if target_order_id:
            try:
                alpaca_client.cancel_order_by_id(target_order_id)
                logger.info(f"Cancelled target order {target_order_id}")
            except Exception as e:
                logger.warning(f"Could not cancel target order {target_order_id}: {e}")
                
    except Exception as e:
        logger.error(f"Error canceling bracket orders for position {position['id']}: {e}")


def handle_partial_fill(position: Dict[str, Any], actual_qty: float) -> bool:
    """
    Handle partial fill by updating quantity and resubmitting bracket orders
    
    Args:
        position: Position dictionary
        actual_qty: Actual filled quantity from Alpaca
    
    Returns:
        True if successfully handled, False otherwise
    """
    try:
        logger.info(
            f"Handling partial fill for position {position['id']}: "
            f"expected {position['quantity']}, got {actual_qty}"
        )
        
        # Log the partial fill event
        db.log_position_event(
            position['id'],
            'partial_fill',
            {
                'expected_qty': float(position['quantity']),
                'actual_qty': actual_qty,
                'difference': actual_qty - float(position['quantity'])
            }
        )
        
        # Update position quantity in database
        db.update_position_quantity(position['id'], actual_qty)
        
        # Cancel old bracket orders
        cancel_bracket_orders(position)
        
        # Resubmit bracket orders with correct quantity
        success = resubmit_bracket_orders(position, actual_qty)
        
        if success:
            logger.info(f"Successfully resubmitted bracket orders for position {position['id']}")
        else:
            logger.warning(f"Failed to resubmit bracket orders for position {position['id']}")
        
        return success
        
    except Exception as e:
        logger.error(f"Error handling partial fill for position {position['id']}: {e}")
        return False


def resubmit_bracket_orders(position: Dict[str, Any], quantity: float) -> bool:
    """
    Resubmit bracket orders with updated quantity
    
    Args:
        position: Position dictionary
        quantity: Quantity to use for new bracket orders
    
    Returns:
        True if successful, False otherwise
    """
    try:
        ticker = position['ticker']
        symbol_to_use = position.get('option_symbol') or ticker  # Use option symbol for options
        quantity = float(position['quantity'])
        stop_price = float(position['stop_loss'])
        target_price = float(position['take_profit'])
        
        logger.info(
            f"Resubmitting bracket orders for {symbol_to_use}: "
            f"qty={quantity}, stop=${stop_price:.2f}, target=${target_price:.2f}"
        )
        
        # Submit stop loss order
        from alpaca.trading.requests import StopOrderRequest
        stop_order_data = StopOrderRequest(
            symbol=symbol_to_use,
            qty=quantity,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
            stop_price=stop_price
        )
        stop_order = alpaca_client.submit_order(stop_order_data)
        
        # Submit take profit order  
        from alpaca.trading.requests import LimitOrderRequest
        target_order_data = LimitOrderRequest(
            symbol=symbol_to_use,
            qty=quantity,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
            limit_price=target_price
        )
        target_order = alpaca_client.submit_order(target_order_data)
        
        # Update database with new order IDs
        db.update_bracket_orders(
            position['id'],
            stop_order.id,
            target_order.id,
            True
        )
        
        logger.info(
            f"Bracket orders resubmitted: "
            f"stop={stop_order.id}, target={target_order.id}"
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Error resubmitting bracket orders for position {position['id']}: {e}")
        return False


def execute_partial_exit(
    position: Dict[str, Any],
    quantity_to_close: int,
    reason: str
) -> bool:
    """
    Execute a partial exit - close part of position, keep rest
    
    Args:
        position: Position dictionary
        quantity_to_close: Number of contracts/shares to close
        reason: Reason for partial exit
    
    Returns:
        True if successful, False otherwise
    """
    try:
        ticker = position['ticker']
        symbol_to_use = position.get('option_symbol') or ticker  # Use option symbol for options
        current_qty = float(position['quantity'])
        
        logger.info(
            f"Executing partial exit for position {position['id']}: "
            f"closing {quantity_to_close} of {current_qty} {position['instrument_type']}"
        )
        
        # Log partial exit event
        db.log_position_event(
            position['id'],
            'partial_exit_triggered',
            {
                'reason': reason,
                'quantity_closing': quantity_to_close,
                'quantity_remaining': current_qty - quantity_to_close,
                'current_price': float(position['current_price']),
                'pnl_percent': float(position.get('current_pnl_percent', 0))
            }
        )
        
        # Submit market order to close partial quantity
        order_data = MarketOrderRequest(
            symbol=symbol_to_use,
            qty=quantity_to_close,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY
        )
        
        order = alpaca_client.submit_order(order_data)
        
        # Update position quantity
        new_qty = current_qty - quantity_to_close
        db.update_position_quantity(position['id'], new_qty)
        
        # Log successful partial exit
        db.log_position_event(
            position['id'],
            'partial_exit_executed',
            {
                'order_id': order.id,
                'quantity_closed': quantity_to_close,
                'quantity_remaining': new_qty,
                'reason': reason
            }
        )
        
        logger.info(
            f"Partial exit executed for position {position['id']}: "
            f"closed {quantity_to_close}, remaining {new_qty}"
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Error executing partial exit for position {position['id']}: {e}")
        
        db.log_position_event(
            position['id'],
            'partial_exit_failed',
            {
                'reason': reason,
                'error': str(e)
            }
        )
        
        return False


def verify_position_closed(position: Dict[str, Any]) -> bool:
    """
    Verify that a position is actually closed in Alpaca
    
    Returns:
        True if closed, False if still open
    """
    try:
        ticker = position['ticker']
        
        # Try to get the position from Alpaca
        try:
            alpaca_position = alpaca_client.get_open_position(ticker)
            
            # If we can get it, position is still open
            if alpaca_position:
                logger.warning(
                    f"Position {position['id']} ({ticker}) still open in Alpaca after close attempt"
                )
                return False
                
        except Exception:
            # If we get an error, position likely doesn't exist (closed)
            logger.info(f"Position {position['id']} ({ticker}) confirmed closed")
            return True
        
        return True
        
    except Exception as e:
        logger.error(f"Error verifying position closed for {position['id']}: {e}")
        return False
