"""
Simulation pricing and position sizing.
Deterministic fill models for backtesting consistency.
"""
from typing import Dict, Any, Tuple, Optional
from decimal import Decimal

def compute_entry_price(
    bar: Dict[str, Any],
    config: Dict[str, Any]
) -> Tuple[float, int, str]:
    """
    Compute simulated entry price based on fill model.
    
    Returns:
        (entry_price, slippage_bps, model_name)
    
    Fill models:
    - "close+slip": Use close price + configured slippage
    - "mid+slip": Use (high+low)/2 + slippage
    - "vwap+slip": Future - use VWAP when available
    """
    model = config['fill_model']
    slippage_bps = config['default_slippage_bps']
    
    close = float(bar['close'])
    high = float(bar['high'])
    low = float(bar['low'])
    
    if model == 'mid+slip':
        base_price = (high + low) / 2
        model_name = 'mid+slip'
    else:
        # Default to close+slip
        base_price = close
        model_name = 'close+slip'
    
    # Apply slippage (positive = pay more for buys, get less for sells)
    slippage_multiplier = 1 + (slippage_bps / 10000.0)
    entry_price = base_price * slippage_multiplier
    
    return (round(entry_price, 4), slippage_bps, model_name)

def compute_position_size(
    entry_price: float,
    stop_loss_price: float,
    features: Dict[str, Any],
    config: Dict[str, Any]
) -> Tuple[float, float, Dict[str, Any]]:
    """
    Compute position size based on risk per trade.
    
    Uses Kelly-style sizing: risk fixed $ amount based on stop distance.
    
    Args:
        entry_price: Simulated entry price
        stop_loss_price: Computed stop loss level
        features: Latest technical features
        config: Configuration with paper_equity and max_risk_per_trade_pct
    
    Returns:
        (qty, notional, sizing_rationale_dict)
    """
    paper_equity = config['paper_equity']
    max_risk_pct = config['max_risk_per_trade_pct']
    
    # Maximum risk in dollars
    max_risk_dollars = paper_equity * max_risk_pct
    
    # Risk per share (distance to stop)
    risk_per_share = abs(entry_price - stop_loss_price)
    
    if risk_per_share == 0 or risk_per_share > entry_price * 0.5:
        # Stop too tight or too wide - use minimum position
        qty = 1.0
        notional = qty * entry_price
        
        sizing_rationale = {
            'method': 'minimum_position',
            'reason': 'Stop distance invalid',
            'risk_per_share': round(risk_per_share, 4),
            'entry_price': round(entry_price, 4)
        }
    else:
        # Standard sizing: risk_dollars / risk_per_share
        qty = max_risk_dollars / risk_per_share
        
        # Round to reasonable lot size
        if entry_price < 50:
            # Low-priced stocks: round to whole shares
            qty = max(1, round(qty))
        else:
            # Higher-priced: can use fractional (or round to whole)
            qty = max(1, round(qty))
        
        notional = qty * entry_price
        
        # Cap notional at some reasonable % of equity
        max_notional = paper_equity * 0.25  # Max 25% per position
        if notional > max_notional:
            qty = max_notional / entry_price
            qty = max(1, round(qty))
            notional = qty * entry_price
        
        sizing_rationale = {
            'method': 'risk_based',
            'paper_equity': paper_equity,
            'max_risk_pct': max_risk_pct,
            'max_risk_dollars': round(max_risk_dollars, 2),
            'risk_per_share': round(risk_per_share, 4),
            'entry_price': round(entry_price, 4),
            'stop_price': round(stop_loss_price, 4),
            'qty_calculated': round(max_risk_dollars / risk_per_share, 2),
            'qty_final': qty
        }
    
    return (qty, round(notional, 2), sizing_rationale)

def compute_stops(
    entry_price: float,
    action: str,
    features: Dict[str, Any],
    config: Dict[str, Any]
) -> Tuple[Optional[float], Optional[float], int, Dict[str, Any]]:
    """
    Compute stop loss and take profit levels.
    
    Uses ATR (approximated via recent_vol) for stop distance.
    
    Args:
        entry_price: Entry price
        action: BUY_CALL, BUY_PUT, BUY_STOCK, etc.
        features: Technical features with recent_vol
        config: Configuration with stop_loss_atr_mult, take_profit_risk_reward
    
    Returns:
        (stop_loss_price, take_profit_price, max_hold_minutes, rationale_dict)
    """
    recent_vol = features.get('recent_vol', 0.02)  # Default 2% if missing
    atr_mult = config['stop_loss_atr_mult']
    rr_ratio = config['take_profit_risk_reward']
    max_hold = config['max_hold_minutes']
    
    # Stop distance based on recent volatility
    stop_distance = entry_price * recent_vol * atr_mult
    
    # Direction-dependent stops
    is_long = action in ['BUY_CALL', 'BUY_STOCK']
    is_short = action in ['BUY_PUT', 'SELL']  # PUT is bearish = short exposure
    
    if is_long:
        stop_loss = entry_price - stop_distance
        take_profit = entry_price + (stop_distance * rr_ratio)
    elif is_short:
        stop_loss = entry_price + stop_distance
        take_profit = entry_price - (stop_distance * rr_ratio)
    else:
        # Premium or unknown - use symmetric stops
        stop_loss = entry_price - stop_distance
        take_profit = entry_price + stop_distance
    
    rationale = {
        'method': 'atr_based',
        'recent_vol': round(recent_vol, 4),
        'atr_multiplier': atr_mult,
        'stop_distance': round(stop_distance, 4),
        'risk_reward_ratio': rr_ratio,
        'direction': 'long' if is_long else ('short' if is_short else 'neutral'),
        'max_hold_minutes': max_hold
    }
    
    return (
        round(stop_loss, 4),
        round(take_profit, 4),
        max_hold,
        rationale
    )
