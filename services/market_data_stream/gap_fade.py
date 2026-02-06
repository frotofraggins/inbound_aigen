"""
Gap Fade Strategy - Trade morning reversals
Exploits pattern: Stocks that move strong one day often reverse at next open
"""
from datetime import time, datetime
import pytz

def should_trade_gap_fade(now_et):
    """
    Check if it's the right time for gap fade trades.
    Only trade first hour after market open (9:30-10:30 AM ET)
    
    Returns:
        Boolean - True if in gap fade window
    """
    return time(9, 30) <= now_et.time() < time(10, 30)


def detect_gap_fade_opportunity(ticker, current_price, prev_day_close, prev_day_direction, volume_ratio):
    """
    Detect if stock has gapped and is fading (reversal setup).
    
    Logic:
    - If yesterday UP and gaps UP at open → Fade with PUT (expect reversal down)
    - If yesterday DOWN and gaps DOWN at open → Fade with CALL (expect reversal up)
    
    Args:
        ticker: Stock symbol
        current_price: Today's open/current price
        prev_day_close: Yesterday's close price
        prev_day_direction: 'up' or 'down' (yesterday's direction)
        volume_ratio: Current volume vs average
    
    Returns:
        Dict with trade signal or None
    """
    if prev_day_close is None or prev_day_close <= 0:
        return None
    
    # Calculate gap percentage
    gap_pct = (current_price - prev_day_close) / prev_day_close
    
    # Need significant gap (>0.8%) to trade
    if abs(gap_pct) < 0.008:
        return None  # Gap too small
    
    # Gap UP (continuing yesterday's up move)
    if gap_pct > 0 and prev_day_direction == 'up':
        # Fade it with PUT (expect reversal down)
        return {
            'action': 'BUY',
            'instrument': 'PUT',
            'strategy': 'gap_fade',
            'confidence': 0.70,  # High confidence - proven strategy
            'reason': 'gap_fade_bearish',
            'gap_pct': round(gap_pct * 100, 2),
            'target_hold_minutes': 90,  # Exit by 11:00 AM
            'take_profit_pct': 0.40,  # +40% for gap fades (faster)
            'stop_loss_pct': -0.30,  # -30% tighter stop
            'rationale': f'{ticker} gapped up {gap_pct*100:.1f}%, fading with PUT (expect reversal)'
        }
    
    # Gap DOWN (continuing yesterday's down move)
    elif gap_pct < 0 and prev_day_direction == 'down':
        # Fade it with CALL (expect reversal up)
        return {
            'action': 'BUY',
            'instrument': 'CALL',
            'strategy': 'gap_fade',
            'confidence': 0.70,
            'reason': 'gap_fade_bullish',
            'gap_pct': round(gap_pct * 100, 2),
            'target_hold_minutes': 90,
            'take_profit_pct': 0.40,
            'stop_loss_pct': -0.30,
            'rationale': f'{ticker} gapped down {abs(gap_pct)*100:.1f}%, fading with CALL (expect reversal)'
        }
    
    return None


def get_previous_day_close_and_direction(ticker, db_conn):
    """
    Get yesterday's close price and direction for gap analysis.
    
    Query telemetry for yesterday's data:
    - Close price at 4:00 PM ET (21:00 UTC) yesterday
    - Direction: Was price up or down for the day?
    
    Args:
        ticker: Stock symbol
        db_conn: Database connection
    
    Returns:
        Tuple of (prev_close, direction) or (None, None)
    """
    try:
        # Get yesterday's close (last bar before 21:00 UTC yesterday)
        cursor = db_conn.cursor()
        cursor.execute("""
            SELECT 
                close,
                (close - open) / open as day_change_pct
            FROM lane_telemetry
            WHERE ticker = %s
              AND ts >= (NOW() - INTERVAL '24 hours')::date + TIME '20:30:00'  -- 3:30 PM ET yesterday
              AND ts < (NOW() - INTERVAL '24 hours')::date + TIME '21:00:00'   -- 4:00 PM ET yesterday
            ORDER BY ts DESC
            LIMIT 1
        """, (ticker,))
        
        result = cursor.fetchone()
        if result:
            prev_close = float(result[0])
            day_change = float(result[1]) if result[1] else 0
            
            # Determine direction (needs >0.5% move to count)
            if day_change > 0.005:
                direction = 'up'
            elif day_change < -0.005:
                direction = 'down'
            else:
                direction = 'flat'  # Not tradeable for gap fade
            
            return (prev_close, direction)
        
        return (None, None)
        
    except Exception as e:
        print(f"Error getting previous close for {ticker}: {e}")
        return (None, None)


def integrate_gap_fade_with_momentum(ticker, features, db_conn):
    """
    Combine gap fade (morning) with momentum (afternoon) strategies.
    
    Morning (9:30-10:30 AM): Check for gap fade opportunities FIRST
    Afternoon (10:30 AM-3:55 PM): Use momentum/trend following
    
    Args:
        ticker: Stock symbol
        features: Current technical features
        db_conn: Database connection
    
    Returns:
        Dict with gap fade signal or None (use normal momentum logic)
    """
    eastern = pytz.timezone('America/New_York')
    now_et = datetime.now(eastern)
    
    # Only check gap fades in first hour
    if not should_trade_gap_fade(now_et):
        return None  # Use normal momentum logic
    
    # Get yesterday's data
    prev_close, prev_direction = get_previous_day_close_and_direction(ticker, db_conn)
    
    if prev_close is None or prev_direction == 'flat':
        return None  # No gap fade opportunity
    
    # Check for gap fade setup
    current_price = features.get('close')
    volume_ratio = features.get('volume_ratio')
    
    gap_signal = detect_gap_fade_opportunity(
        ticker, current_price, prev_close, prev_direction, volume_ratio
    )
    
    return gap_signal


# =============================================================================
# USAGE IN MAIN SIGNAL ENGINE
# =============================================================================

"""
To integrate this in signal_engine_1m/main.py:

1. Import:
   from gap_fade import integrate_gap_fade_with_momentum

2. In process_ticker(), BEFORE calling compute_signal():
   
   # Check for gap fade opportunity (9:30-10:30 AM only)
   gap_fade_signal = integrate_gap_fade_with_momentum(ticker, features, conn)
   
   if gap_fade_signal:
       # Use gap fade signal instead of normal logic
       action = gap_fade_signal['action']
       instrument = gap_fade_signal['instrument']
       strategy = gap_fade_signal['strategy']
       confidence = gap_fade_signal['confidence']
       reason = gap_fade_signal
   else:
       # Use normal momentum/trend logic
       action, instrument, strategy, confidence, reason = compute_signal(...)

3. Gap fade positions need special exit handling in position_manager:
   - Max hold: 90 minutes (not 4 hours)
   - Take profit: +40% (not +80%)
   - Stop loss: -30% (not -40%)
   - Force exit at 11:00 AM if still open
"""
