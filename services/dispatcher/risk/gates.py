"""
Risk gate evaluation functions.
Production-grade with robust error handling and comprehensive safety checks.
"""
from typing import Dict, Any, Tuple, Optional
from datetime import datetime, timedelta

GateResult = Tuple[bool, str, Any, Any]  # (passed, reason, observed, threshold)

# Action/Instrument normalization mappings
ACTION_ALIASES = {"LONG": "BUY", "SHORT": "SELL"}
INSTRUMENT_ALIASES = {"EQUITY": "STOCK", "SHARE": "STOCK", "SHARES": "STOCK", 
                      "PUTS": "PUT", "CALLS": "CALL", "OPTION": "CALL"}

def parse_datetime_safe(dt_value):
    """Safely parse datetime from string or datetime object."""
    if dt_value is None:
        return None
    if isinstance(dt_value, datetime):
        return dt_value
    if isinstance(dt_value, str):
        try:
            return datetime.fromisoformat(dt_value.replace('Z', '+00:00'))
        except:
            return None
    return None

def check_confidence_gate(
    recommendation: Dict[str, Any], 
    config: Dict[str, Any]
) -> GateResult:
    """
    Check if confidence meets minimum threshold (instrument-aware).
    
    Different instruments have different risk profiles:
    - Day trade options: Higher threshold (0.60)
    - Swing trade options: Medium threshold (0.45)
    - Stocks: Lower threshold (0.35)
    """
    # Robust field extraction
    confidence = float(recommendation.get('confidence', 0.0) or 0.0)
    instrument = (recommendation.get('instrument_type') or '').upper()
    strategy = (recommendation.get('strategy_type') or '').lower()
    
    # Determine appropriate threshold based on instrument and strategy
    if instrument in ('CALL', 'PUT'):
        if strategy == 'day_trade':
            threshold = config.get('confidence_min_options_daytrade', 0.60)
            threshold_name = "options_daytrade"
        elif strategy == 'swing_trade':
            threshold = config.get('confidence_min_options_swing', 0.45)
            threshold_name = "options_swing"
        else:
            # Default for options without strategy
            threshold = config.get('confidence_min_options', 0.55)
            threshold_name = "options_default"
    else:
        threshold = config.get('confidence_min_stock', 0.35)
        threshold_name = "stock"
    
    passed = confidence >= threshold
    reason = f"Confidence {confidence:.3f} {'≥' if passed else '<'} {threshold_name} threshold {threshold:.3f}"
    
    return (passed, reason, confidence, threshold)

def check_action_allowed(
    recommendation: Dict[str, Any], 
    config: Dict[str, Any]
) -> GateResult:
    """
    Check if action+instrument combination is allowed.
    Robust to format variations and missing fields.
    """
    # Robust extraction with defaults
    action = (recommendation.get('action') or '').upper()
    instrument = (recommendation.get('instrument_type') or '').upper()
    
    # Handle empty or invalid
    if not action or not instrument:
        return (False, f"Missing action ({action}) or instrument ({instrument})", None, None)
    
    # Normalize using aliases
    action = ACTION_ALIASES.get(action, action)
    instrument = INSTRUMENT_ALIASES.get(instrument, instrument)
    
    # Validate known values
    if action not in ('BUY', 'SELL'):
        return (False, f"Unknown action: {action}", action, None)
    
    if instrument not in ('CALL', 'PUT', 'STOCK'):
        return (False, f"Unknown instrument: {instrument}", instrument, None)
    
    # Build combined action
    combined_action = f"{action}_{instrument}"
    
    allowed = config.get('allowed_actions', [])
    passed = combined_action in allowed
    
    reason = f"Action {combined_action} {'allowed' if passed else 'blocked (not in allowed list)'}"
    
    return (passed, reason, combined_action, allowed)

def check_recommendation_freshness(
    recommendation: Dict[str, Any],
    config: Dict[str, Any]
) -> GateResult:
    """
    Check if recommendation is fresh enough.
    Prevents executing stale signals if dispatcher falls behind.
    """
    threshold_sec = config.get('max_recommendation_age_seconds', 300)  # 5 min default
    
    # Try to get timestamp (multiple field names possible)
    created_at = recommendation.get('created_at') or recommendation.get('ts')
    
    if not created_at:
        return (False, "No timestamp in recommendation", None, threshold_sec)
    
    # Parse datetime safely
    rec_time = parse_datetime_safe(created_at)
    if not rec_time:
        return (False, f"Could not parse recommendation time: {created_at}", None, threshold_sec)
    
    rec_age = (datetime.utcnow() - rec_time.replace(tzinfo=None)).total_seconds()
    passed = rec_age <= threshold_sec
    
    reason = f"Recommendation age {rec_age:.0f}s {'≤' if passed else '>'} threshold {threshold_sec}s"
    
    return (passed, reason, rec_age, threshold_sec)

def check_bar_freshness(
    bar: Optional[Dict[str, Any]], 
    config: Dict[str, Any]
) -> GateResult:
    """Check if bar data is fresh enough."""
    threshold_sec = config.get('max_bar_age_seconds', 120)
    
    if not bar:
        return (False, "No bar data available", None, threshold_sec)
    
    # Parse timestamp safely
    bar_ts = parse_datetime_safe(bar.get('ts'))
    if not bar_ts:
        return (False, "Could not parse bar timestamp", None, threshold_sec)
    
    bar_age = (datetime.utcnow() - bar_ts.replace(tzinfo=None)).total_seconds()
    passed = bar_age <= threshold_sec
    
    reason = f"Bar age {bar_age:.0f}s {'≤' if passed else '>'} threshold {threshold_sec}s"
    
    return (passed, reason, bar_age, threshold_sec)

def check_feature_freshness(
    features: Optional[Dict[str, Any]], 
    config: Dict[str, Any]
) -> GateResult:
    """Check if feature data is fresh enough."""
    threshold_sec = config.get('max_feature_age_seconds', 300)
    
    if not features:
        return (False, "No feature data available", None, threshold_sec)
    
    # Parse timestamp safely
    computed_at = parse_datetime_safe(features.get('computed_at'))
    if not computed_at:
        return (False, "Could not parse feature timestamp", None, threshold_sec)
    
    feature_age = (datetime.utcnow() - computed_at.replace(tzinfo=None)).total_seconds()
    passed = feature_age <= threshold_sec
    
    reason = f"Feature age {feature_age:.0f}s {'≤' if passed else '>'} threshold {threshold_sec}s"
    
    return (passed, reason, feature_age, threshold_sec)

def check_ticker_daily_limit(
    ticker: str,
    today_count: int,
    config: Dict[str, Any]
) -> GateResult:
    """Check if ticker hasn't exceeded daily trade limit."""
    threshold = config.get('max_trades_per_ticker_per_day', 2)
    passed = today_count < threshold
    
    reason = f"Ticker {ticker} has {today_count} trades today {'<' if passed else '≥'} limit {threshold}"
    
    return (passed, reason, today_count, threshold)

def check_ticker_cooldown(
    ticker: str,
    last_trade_time: Optional[datetime],
    config: Dict[str, Any]
) -> GateResult:
    """
    Check if ticker cooldown period has elapsed.
    Prevents whipsaw trades on same ticker.
    """
    cooldown_minutes = config.get('ticker_cooldown_minutes', 15)
    
    if not last_trade_time:
        # No previous trade - cooldown passed
        return (True, f"No recent trade for {ticker}", None, cooldown_minutes)
    
    # Parse safely
    last_time = parse_datetime_safe(last_trade_time)
    if not last_time:
        # Can't parse - be conservative and allow
        return (True, "Could not parse last trade time (allowing)", None, cooldown_minutes)
    
    minutes_since = (datetime.utcnow() - last_time.replace(tzinfo=None)).total_seconds() / 60
    passed = minutes_since >= cooldown_minutes
    
    reason = f"Ticker {ticker} last traded {minutes_since:.1f} min ago {'≥' if passed else '<'} cooldown {cooldown_minutes} min"
    
    return (passed, reason, minutes_since, cooldown_minutes)

def check_sell_stock_has_position(
    ticker: str,
    action: str,
    instrument: str,
    has_open_position: bool,
    allow_shorting: bool = False
) -> GateResult:
    """
    For SELL_STOCK, verify an open long position exists.
    Prevents accidental short selling if not supported.
    """
    if action != 'SELL' or instrument != 'STOCK':
        # Not a sell stock signal - gate doesn't apply
        return (True, "Not a SELL_STOCK signal", None, None)

    if allow_shorting:
        return (True, "SELL_STOCK allowed (shorting enabled)", True, True)

    passed = has_open_position
    reason = f"SELL_STOCK requires open long position: {'exists' if passed else 'NONE (blocked)'}"

    return (passed, reason, has_open_position, True)

def check_daily_loss_limit(
    daily_pnl: float,
    config: Dict[str, Any]
) -> GateResult:
    """
    CRITICAL: Max daily loss kill switch.
    Stops all trading if daily loss exceeds threshold.
    """
    max_loss = config.get('max_daily_loss', 500)  # $500 default for paper
    
    if daily_pnl < -max_loss:
        return (False, f"KILL SWITCH: Daily loss ${abs(daily_pnl):.0f} exceeds limit ${max_loss}", daily_pnl, max_loss)
    
    return (True, f"Daily P&L ${daily_pnl:.2f} within limit ${max_loss}", daily_pnl, max_loss)

def check_max_positions(
    active_position_count: int,
    config: Dict[str, Any]
) -> GateResult:
    """
    Max concurrent positions limit.
    Prevents over-concentration of capital.
    """
    max_positions = config.get('max_open_positions', 5)
    
    if active_position_count >= max_positions:
        return (False, f"At position limit: {active_position_count}/{max_positions}", active_position_count, max_positions)
    
    return (True, f"Positions {active_position_count}/{max_positions}", active_position_count, max_positions)

def check_max_exposure(
    total_notional: float,
    config: Dict[str, Any]
) -> GateResult:
    """
    Max notional exposure limit.
    Prevents excessive capital deployment.
    """
    max_notional = config.get('max_notional_exposure', 10000)  # $10k default
    
    if total_notional >= max_notional:
        return (False, f"At exposure limit: ${total_notional:.0f}/${max_notional}", total_notional, max_notional)
    
    return (True, f"Exposure ${total_notional:.0f}/${max_notional}", total_notional, max_notional)

def check_trading_hours(
    config: Dict[str, Any]
) -> GateResult:
    """
    Time-of-day restrictions to prevent trading at open/close.
    - Block: First 5 minutes after open (9:30-9:35 AM ET)
    - Block: Last 15 minutes before close (3:45-4:00 PM ET)
    """
    # Get current time in ET
    from datetime import datetime
    import pytz
    
    try:
        et = pytz.timezone('US/Eastern')
        now_et = datetime.now(et)
        
        # Market hours: 9:30 AM - 4:00 PM ET
        market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
        opening_window_end = now_et.replace(hour=9, minute=35, second=0, microsecond=0)
        closing_window_start = now_et.replace(hour=15, minute=45, second=0, microsecond=0)
        market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
        
        # Check if in opening window
        if market_open <= now_et < opening_window_end:
            return (False, f"BLOCKED: In opening window ({now_et.strftime('%H:%M')} ET)", now_et.strftime('%H:%M'), "9:30-9:35")
        
        # Check if in closing window
        if closing_window_start <= now_et < market_close:
            return (False, f"BLOCKED: In closing window ({now_et.strftime('%H:%M')} ET)", now_et.strftime('%H:%M'), "3:45-4:00")
        
        # Check if outside market hours
        if now_et < market_open or now_et >= market_close:
            return (False, f"BLOCKED: Outside market hours ({now_et.strftime('%H:%M')} ET)", now_et.strftime('%H:%M'), "9:30-16:00")
        
        return (True, f"Trading hours OK ({now_et.strftime('%H:%M')} ET)", now_et.strftime('%H:%M'), "9:30-16:00")
    
    except:
        # If timezone fails, be conservative and allow (log warning)
        return (True, "Trading hours check failed (allowing)", None, None)

def evaluate_all_gates(
    recommendation: Dict[str, Any],
    bar: Optional[Dict[str, Any]],
    features: Optional[Dict[str, Any]],
    ticker_count_today: int,
    last_trade_time: Optional[datetime],
    has_open_position: bool,
    config: Dict[str, Any],
    # Account-level state (optional for backward compatibility)
    daily_pnl: float = 0.0,
    active_position_count: int = 0,
    total_notional: float = 0.0
) -> Tuple[bool, Dict[str, Any]]:
    """
    Evaluate all risk gates for a recommendation.
    
    Includes both ticker-level and account-level gates.
    
    Args:
        recommendation: Signal from signal_engine
        bar: Latest price bar
        features: Latest computed features
        ticker_count_today: Number of trades today for this ticker
        last_trade_time: Timestamp of last trade for this ticker (for cooldown)
        has_open_position: Whether ticker has open long position (for SELL_STOCK)
        config: Dispatcher configuration
        daily_pnl: Today's P&L (for daily loss limit)
        active_position_count: Number of open positions (for max positions)
        total_notional: Total position value (for max exposure)
    
    Returns:
        (all_passed: bool, gate_results: dict)
    """
    # Extract action/instrument early
    action = (recommendation.get('action') or '').upper()
    instrument = (recommendation.get('instrument_type') or '').upper()
    action = ACTION_ALIASES.get(action, action)
    instrument = INSTRUMENT_ALIASES.get(instrument, instrument)
    
    gates = {
        # Recommendation-level gates
        'confidence': check_confidence_gate(recommendation, config),
        'action_allowed': check_action_allowed(recommendation, config),
        'recommendation_freshness': check_recommendation_freshness(recommendation, config),
        
        # Data freshness gates
        'bar_freshness': check_bar_freshness(bar, config),
        'feature_freshness': check_feature_freshness(features, config),
        
        # Ticker-level gates
        'ticker_daily_limit': check_ticker_daily_limit(
            recommendation.get('ticker', 'UNKNOWN'),
            ticker_count_today,
            config
        ),
        'ticker_cooldown': check_ticker_cooldown(
            recommendation.get('ticker', 'UNKNOWN'),
            last_trade_time,
            config
        ),
        'sell_stock_position': check_sell_stock_has_position(
            recommendation.get('ticker', 'UNKNOWN'),
            action,
            instrument,
            has_open_position,
            config.get('allow_shorting', False)
        ),
        
        # Account-level gates (CRITICAL for risk management)
        'daily_loss_limit': check_daily_loss_limit(daily_pnl, config),
        'max_positions': check_max_positions(active_position_count, config),
        'max_exposure': check_max_exposure(total_notional, config),
        'trading_hours': check_trading_hours(config)
    }
    
    # Build gate results dict
    gate_results = {}
    all_passed = True
    
    for gate_name, (passed, reason, observed, threshold) in gates.items():
        gate_results[gate_name] = {
            'passed': passed,
            'reason': reason,
            'observed': observed,
            'threshold': threshold
        }
        if not passed:
            all_passed = False
    
    return (all_passed, gate_results)
