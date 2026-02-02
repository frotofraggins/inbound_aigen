"""
Exit enforcement logic
"""
import logging
from typing import Dict, Any, Optional
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
            # For options, need to sell to close
            logger.info(
                f"Submitting market order to close {quantity} contracts of "
                f"{ticker} {position['instrument_type']}"
            )
            
            # Submit market sell order for options
            order_data = MarketOrderRequest(
                symbol=ticker,
                qty=quantity,
                side=OrderSide.SELL,  # Sell to close long position
                time_in_force=TimeInForce.DAY
            )
            
            order = alpaca_client.submit_order(order_data)
            
            return {
                'order_id': order.id,
                'status': order.status,
                'filled_qty': order.filled_qty if hasattr(order, 'filled_qty') else 0
            }
            
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
        stop_price = float(position['stop_loss'])
        target_price = float(position['take_profit'])
        
        logger.info(
            f"Resubmitting bracket orders for {ticker}: "
            f"qty={quantity}, stop=${stop_price:.2f}, target=${target_price:.2f}"
        )
        
        # Submit stop loss order
        from alpaca.trading.requests import StopOrderRequest
        stop_order_data = StopOrderRequest(
            symbol=ticker,
            qty=quantity,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
            stop_price=stop_price
        )
        stop_order = alpaca_client.submit_order(stop_order_data)
        
        # Submit take profit order  
        from alpaca.trading.requests import LimitOrderRequest
        target_order_data = LimitOrderRequest(
            symbol=ticker,
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
            symbol=ticker,
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
