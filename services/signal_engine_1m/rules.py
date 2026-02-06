"""
Signal generation rules for trading recommendations.
Production-grade implementation with sentiment as confidence scaler, not gate.

Key principles:
1. Direction from price action + trend (NOT sentiment)
2. Sentiment as confidence modifier (boost/penalty)
3. Volume confirmation (hard gate)
4. Price move confirmation (breakout/momentum)
5. Adaptive thresholds by volatility
"""
from datetime import time
import pytz

# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================

# SMA tolerance for support/resistance zones
SMA_TOLERANCE = 0.005  # ±0.5% from SMA20

# Volume thresholds
# LEARNING MODE 2026-02-06: Moderate thresholds to generate learning data
VOLUME_KILL_THRESHOLD = 0.5    # <0.5x = kill signal
VOLUME_MIN_FOR_TRADE = 1.5     # Minimum for any trade (balance: not too loose, not too tight)
VOLUME_SURGE_THRESHOLD = 2.0   # 2.0x+ confirms strong move

# Confidence thresholds
# LEARNING MODE 2026-02-06: Balanced for data generation + quality
# Paper trading = maximize learning, but not garbage signals
CONFIDENCE_DAY_TRADE = 0.65    # Raised from 0.60 (filter worst, keep learning data)
CONFIDENCE_SWING_TRADE = 0.50  # Raised from 0.45 (slight improvement)
CONFIDENCE_STOCK = 0.40        # Raised from 0.35 (filter noise)

# Trend requirements
TREND_REQUIRED_FOR_OPTIONS = True  # Require trend_state = ±1 for options
TREND_BULL = 1   # Uptrend
TREND_BEAR = -1  # Downtrend
TREND_NONE = 0   # No trend

# Breakout thresholds
BREAKOUT_THRESHOLD = 0.01  # 1% move from SMA20 for breakout

# Options-specific gates (TODO: implement when greeks available)
IV_PERCENTILE_MAX = 80    # Don't buy when IV > 80th percentile
BID_ASK_SPREAD_MAX = 0.10 # 10% max spread
MIN_OPTION_VOLUME = 100   # Minimum daily volume
MIN_OPEN_INTEREST = 100   # Minimum OI

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_volume_multiplier(volume_ratio):
    """
    Volume confirmation filter - professional traders use this.
    
    Args:
        volume_ratio: Current volume / 20-bar average (or None)
        
    Returns:
        Tuple of (multiplier, reason_text)
    """
    if volume_ratio is None:
        # Missing volume data - be conservative
        return (0.5, "NO_VOLUME_DATA (reduced to 50%)")
    
    # HARD BLOCK: No trades on extremely low volume
    if volume_ratio < VOLUME_KILL_THRESHOLD:
        return (0.0, f"VOLUME_TOO_LOW (ratio {volume_ratio:.2f} < {VOLUME_KILL_THRESHOLD}x)")
    
    # Weak volume: drastically reduce
    if volume_ratio < VOLUME_MIN_FOR_TRADE:
        return (0.3, f"WEAK_VOLUME (ratio {volume_ratio:.2f}, reduced 70%)")
    
    # Below average: reduce moderately
    if volume_ratio < 1.5:
        return (0.6, f"BELOW_AVG_VOLUME (ratio {volume_ratio:.2f}, reduced 40%)")
    
    # Good volume: no adjustment
    if volume_ratio < VOLUME_SURGE_THRESHOLD:
        return (1.0, f"GOOD_VOLUME (ratio {volume_ratio:.2f})")
    
    # Strong volume: boost confidence
    if volume_ratio < 3.0:
        return (1.15, f"STRONG_VOLUME (ratio {volume_ratio:.2f}, boosted 15%)")
    
    # Volume surge: significant boost
    if volume_ratio < 5.0:
        return (1.25, f"VOLUME_SURGE (ratio {volume_ratio:.2f}, boosted 25%)")
    
    # Extreme surge: max boost
    return (1.35, f"EXTREME_SURGE (ratio {volume_ratio:.2f}, boosted 35%)")


def check_breakout(features):
    """
    Check if price is breaking out of recent range.
    Uses SMA distance as proxy until we add recent high/low tracking.
    
    Returns:
        Tuple of (breakout_up, breakout_down, move_confirmed, reason)
    """
    distance_sma20 = features.get('distance_sma20', 0)
    
    # Breakout = price beyond 1% from SMA20
    breakout_up = distance_sma20 > BREAKOUT_THRESHOLD
    breakout_down = distance_sma20 < -BREAKOUT_THRESHOLD
    
    # At least one breakout confirmed
    move_confirmed = breakout_up or breakout_down
    
    if breakout_up:
        reason = f"Bullish breakout: {distance_sma20*100:.2f}% above SMA20"
    elif breakout_down:
        reason = f"Bearish breakout: {abs(distance_sma20)*100:.2f}% below SMA20"
    else:
        reason = f"No breakout: {abs(distance_sma20)*100:.2f}% from SMA20 (need >{BREAKOUT_THRESHOLD*100:.1f}%)"
    
    return (breakout_up, breakout_down, move_confirmed, reason)


def calculate_adaptive_confidence_threshold(vol_ratio):
    """
    Adaptive confidence requirement based on volatility.
    When vol is high (options expensive), require higher confidence.
    
    Slower ramp than original to avoid shutting off system.
    
    Args:
        vol_ratio: Current volatility / baseline
        
    Returns:
        Required confidence for day trade
    """
    base_threshold = CONFIDENCE_DAY_TRADE
    
    # Slower ramp: Add 5% for each 0.2 above 1.2 (was 10%)
    if vol_ratio > 1.2:
        adjustment = 0.05 * ((vol_ratio - 1.2) / 0.2)
        return min(base_threshold + adjustment, 0.75)  # Cap at 0.75 (was 0.85)
    
    return base_threshold


def calculate_sentiment_boost(sentiment_score, sentiment_direction, primary_direction, news_count):
    """
    Calculate sentiment boost/penalty as confidence multiplier.
    
    Improvements:
    - Weight by news_count (more news = more confidence)
    - Check alignment with primary direction
    - Boost if aligns, penalty if opposes, neutral if no news
    
    Args:
        sentiment_score: -1 to +1 directional score
        sentiment_direction: 1 (bullish), -1 (bearish), 0 (neutral)
        primary_direction: "BULL" or "BEAR"
        news_count: Number of news articles
        
    Returns:
        Tuple of (boost_multiplier, aligns, reason)
    """
    sentiment_strength = abs(sentiment_score)  # 0 to 1
    
    # No news or neutral = no adjustment
    if news_count == 0 or sentiment_direction == 0:
        return (1.0, False, f"No sentiment impact ({news_count} news)")
    
    # Check alignment
    sentiment_aligns = (
        (primary_direction == "BULL" and sentiment_direction > 0) or
        (primary_direction == "BEAR" and sentiment_direction < 0)
    )
    
    # Weight by news count (more news = higher impact, cap at 5 articles)
    news_weight = min(news_count / 5.0, 1.0)
    
    if sentiment_aligns:
        # Boost when sentiment confirms (up to +25%)
        boost = 1 + (0.25 * sentiment_strength * news_weight)
        reason = f"Sentiment confirms ({news_count} news, +{(boost-1)*100:.0f}%)"
    else:
        # Penalty when sentiment opposes (up to -20%)
        boost = 1 - (0.20 * sentiment_strength * news_weight)
        reason = f"Sentiment opposes ({news_count} news, -{(1-boost)*100:.0f}%)"
    
    return (boost, sentiment_aligns, reason)


# =============================================================================
# MAIN SIGNAL COMPUTATION
# =============================================================================

def compute_signal(ticker, features, sentiment):
    """
    Generate trading signal using production-grade logic.
    
    Critical fixes implemented:
    1. Sentiment is confidence scaler, NOT gate
    2. Direction from price + trend (NOT sentiment)
    3. Strict trend requirement for options (trend_state = ±1)
    4. volume_ratio defaults to None (not 1.0) - catches missing data
    5. Breakout confirmation required
    6. Adaptive confidence with slower ramp
    7. News count weighting in sentiment
    
    Args:
        ticker: Stock symbol
        features: Dict with technicals
        sentiment: Dict with sentiment data (or None)
    
    Returns:
        Tuple of (action, instrument_type, strategy_type, confidence, reason_dict)
    """
    
    # =========================================================================
    # 1. EXTRACT AND VALIDATE FEATURES
    # =========================================================================
    
    close = features.get('close')
    sma20 = features.get('sma20')
    sma50 = features.get('sma50')
    distance_sma20 = features.get('distance_sma20', 0)
    distance_sma50 = features.get('distance_sma50', 0)
    vol_ratio = features.get('vol_ratio', 1.0)
    trend_state = features.get('trend_state', 0)
    volume_ratio = features.get('volume_ratio', None)  # Default None, not 1.0!
    
    # Handle missing features
    if None in [close, sma20, sma50]:
        return ('HOLD', None, None, 0.0, {
            'rule': 'NO_FEATURES',
            'reason': 'Missing technical indicators'
        })
    
    # LEARNING MODE 2026-02-06: Allow first hour but with extra caution
    # We WANT to learn from morning volatility in paper trading
    # But mark these trades so AI can learn "morning trades risky"
    eastern = pytz.timezone('America/New_York')
    from datetime import datetime
    now_et = datetime.now(eastern)
    is_first_hour = time(9, 30) <= now_et.time() < time(10, 30)
    
    # Don't block, but we'll reduce confidence for first hour trades
    # This generates data showing "first hour = losses" which AI learns from
    
    # =========================================================================
    # 2. EXTRACT SENTIMENT (Optional - confidence modifier only)
    # =========================================================================
    
    sentiment_score = sentiment.get('avg_score', 0.0) if sentiment else 0.0
    news_count = sentiment.get('news_count', 0) if sentiment else 0
    sentiment_strength = abs(sentiment_score)  # 0 to 1
    sentiment_direction = 1 if sentiment_score > 0 else (-1 if sentiment_score < 0 else 0)
    
    # =========================================================================
    # 3. DETERMINE PRIMARY DIRECTION (Price + Trend, NOT Sentiment!)
    # =========================================================================
    
    # Position relative to SMAs
    above_sma20 = distance_sma20 > SMA_TOLERANCE
    below_sma20 = distance_sma20 < -SMA_TOLERANCE
    at_sma20 = abs(distance_sma20) <= SMA_TOLERANCE
    not_stretched = abs(distance_sma20) < 0.02  # Within 2%
    
    # STRICT TREND REQUIREMENT for directional bias
    # Options require trend_state = ±1 (clear trend)
    # Stocks can trade on trend_state >= 0 (uptrend or flat with confirmation)
    
    if (above_sma20 or at_sma20) and trend_state == TREND_BULL and not_stretched:
        primary_direction = "BULL"
        can_trade_options = True
    elif (above_sma20 or at_sma20) and trend_state >= 0 and not_stretched:
        # Weak uptrend or flat - stocks only
        primary_direction = "BULL"
        can_trade_options = False
    elif (below_sma20 or at_sma20) and trend_state == TREND_BEAR and not_stretched:
        primary_direction = "BEAR"
        can_trade_options = True
    elif (below_sma20 or at_sma20) and trend_state <= 0 and not_stretched:
        # Weak downtrend or flat - stocks only
        primary_direction = "BEAR"
        can_trade_options = False
    else:
        primary_direction = "NONE"
        can_trade_options = False
    
    # No tradeable setup
    if primary_direction == "NONE":
        return ('HOLD', None, None, 0.0, {
            'rule': 'NO_SETUP',
            'reason': 'No clear directional bias from price/trend',
            'technicals': {
                'close': round(close, 2),
                'sma20': round(sma20, 2),
                'distance_sma20': round(distance_sma20, 4),
                'trend_state': trend_state,
                'stretched': not not_stretched
            }
        })
    
    # =========================================================================
    # 4. PRICE MOVE CONFIRMATION (Filter chop)
    # =========================================================================
    
    breakout_up, breakout_down, move_confirmed, breakout_reason = check_breakout(features)
    
    # Require breakout in direction of trade
    if primary_direction == "BULL" and not breakout_up:
        move_confirmed = False
        move_penalty = 0.5  # 50% reduction without confirmation
        move_reason = f"No bullish breakout (confidence reduced 50%): {breakout_reason}"
    elif primary_direction == "BEAR" and not breakout_down:
        move_confirmed = False
        move_penalty = 0.5
        move_reason = f"No bearish breakout (confidence reduced 50%): {breakout_reason}"
    else:
        move_confirmed = True
        move_penalty = 1.0
        move_reason = breakout_reason
    
    # =========================================================================
    # 5. VOLUME CONFIRMATION (Critical hard gate)
    # =========================================================================
    
    volume_mult, volume_reason = get_volume_multiplier(volume_ratio)
    
    # HARD BLOCK on low volume
    if volume_mult == 0.0:
        return ('HOLD', None, None, 0.0, {
            'rule': 'VOLUME_TOO_LOW',
            'reason': volume_reason,
            'volume_ratio': round(volume_ratio, 2) if volume_ratio else None
        })
    
    # =========================================================================
    # 6. COMPUTE BASE CONFIDENCE (From technicals + setup)
    # =========================================================================
    
    # Trend alignment (stronger trend = higher confidence)
    if primary_direction == "BULL":
        if trend_state == TREND_BULL:
            trend_alignment = 1.0  # Strong uptrend
        else:
            trend_alignment = 0.5  # Weak/flat uptrend
    else:  # BEAR
        if trend_state == TREND_BEAR:
            trend_alignment = 1.0  # Strong downtrend
        else:
            trend_alignment = 0.5  # Weak/flat downtrend
    
    # Setup quality (closer to SMA20 = better entry)
    setup_quality = 1.0 - min(abs(distance_sma20) / 0.02, 1.0)
    
    # Volatility appropriateness
    vol_normal = 0.8 <= vol_ratio <= 1.3
    vol_compressed = vol_ratio < 0.8
    vol_high = vol_ratio > 1.3
    vol_appropriateness = 1.0 if vol_normal else (0.7 if vol_compressed else 0.5)
    
    # Base confidence from price action (NO sentiment here)
    base_confidence = (
        0.35 * trend_alignment +      # Trend strength
        0.25 * setup_quality +         # Entry quality
        0.20 * vol_appropriateness +   # Vol regime
        0.20 * 1.0                     # Base conviction
    )
    
    # =========================================================================
    # 7. APPLY SENTIMENT AS CONFIDENCE SCALER (Not Gate!)
    # =========================================================================
    
    sentiment_boost, sentiment_aligns, sentiment_reason = calculate_sentiment_boost(
        sentiment_score, sentiment_direction, primary_direction, news_count
    )
    
    # =========================================================================
    # 8. FINAL CONFIDENCE = Base × Sentiment × Volume × Move
    # =========================================================================
    
    confidence = base_confidence * sentiment_boost * volume_mult * move_penalty
    confidence = min(max(confidence, 0.0), 1.0)
    
    # =========================================================================
    # 9. INSTRUMENT SELECTION & STRATEGY TYPE
    # =========================================================================
    
    adaptive_threshold = None  # Initialize outside scope
    
    # Determine if options are appropriate
    if can_trade_options and (vol_normal or vol_compressed):
        # Options are reasonable/cheap AND we have a strong trend
        instrument = 'CALL' if primary_direction == "BULL" else 'PUT'
        
        # Adaptive confidence threshold
        adaptive_threshold = calculate_adaptive_confidence_threshold(vol_ratio)
        
        # Strategy type based on confidence and volume
        if confidence >= adaptive_threshold and volume_ratio and volume_ratio >= VOLUME_SURGE_THRESHOLD:
            strategy_type = 'day_trade'  # 0-1 DTE
        elif confidence >= CONFIDENCE_SWING_TRADE:
            strategy_type = 'swing_trade'  # 7-30 DTE
        else:
            # Confidence too low for options
            instrument = 'STOCK'
            strategy_type = None
    else:
        # No options: weak trend, high vol, or other reason
        instrument = 'STOCK'
        strategy_type = None
    
    # Set action based on final instrument
    if instrument in ('CALL', 'PUT'):
        action = 'BUY'  # Always BUY for options
    else:
        action = 'BUY' if primary_direction == "BULL" else 'SELL'
    
    # Check if confidence meets minimum threshold
    if instrument in ('CALL', 'PUT'):
        if strategy_type == 'day_trade':
            min_confidence = adaptive_threshold if adaptive_threshold else CONFIDENCE_DAY_TRADE
        elif strategy_type == 'swing_trade':
            min_confidence = CONFIDENCE_SWING_TRADE
        else:
            min_confidence = CONFIDENCE_STOCK
    else:
        min_confidence = CONFIDENCE_STOCK
    
    # Below threshold = HOLD
    if confidence < min_confidence:
        return ('HOLD', None, None, confidence, {
            'rule': 'CONFIDENCE_TOO_LOW',
            'reason': f'Confidence {confidence:.3f} below {min_confidence:.3f} threshold',
            'direction': primary_direction,
            'can_trade_options': can_trade_options,
            'trend_state': trend_state,
            'confidence': round(confidence, 3),
            'required': round(min_confidence, 3)
        })
    
    # =========================================================================
    # 10. BUILD COMPREHENSIVE REASON DICT
    # =========================================================================
    
    reason = {
        'rule': f'{primary_direction}_ENTRY',
        'direction': 'LONG' if primary_direction == "BULL" else 'SHORT',
        'version': '2.0-production',
        
        'sentiment': {
            'score': round(sentiment_score, 3),
            'strength': round(sentiment_strength, 3),
            'direction': 'bullish' if sentiment_direction > 0 else ('bearish' if sentiment_direction < 0 else 'neutral'),
            'news_count': news_count,
            'aligns': sentiment_aligns,
            'boost': round(sentiment_boost, 3),
            'reason': sentiment_reason,
            'note': 'Sentiment is confidence scaler, NOT gate'
        },
        
        'technicals': {
            'close': round(close, 2),
            'sma20': round(sma20, 2),
            'sma50': round(sma50, 2),
            'distance_sma20': round(distance_sma20, 4),
            'distance_sma50': round(distance_sma50, 4),
            'trend_state': trend_state,
            'trend_alignment': round(trend_alignment, 3),
            'setup_quality': round(setup_quality, 3)
        },
        
        'price_move': {
            'confirmed': move_confirmed,
            'breakout_up': breakout_up,
            'breakout_down': breakout_down,
            'penalty': round(move_penalty, 2),
            'reason': move_reason
        },
        
        'volume': {
            'volume_ratio': round(volume_ratio, 3) if volume_ratio else None,
            'volume_mult': round(volume_mult, 2),
            'assessment': volume_reason,
            'surge': (volume_ratio >= VOLUME_SURGE_THRESHOLD) if volume_ratio else False
        },
        
        'volatility': {
            'vol_ratio': round(vol_ratio, 3),
            'regime': 'normal' if vol_normal else ('high' if vol_high else 'compressed'),
            'appropriateness': round(vol_appropriateness, 2),
            'adaptive_threshold': round(adaptive_threshold, 3) if adaptive_threshold else None
        },
        
        'confidence_breakdown': {
            'base': round(base_confidence, 3),
            'after_sentiment': round(base_confidence * sentiment_boost, 3),
            'after_volume': round(base_confidence * sentiment_boost * volume_mult, 3),
            'final': round(confidence, 3),
            'components': {
                'trend_alignment': round(trend_alignment, 3),
                'setup_quality': round(setup_quality, 3),
                'vol_appropriateness': round(vol_appropriateness, 3)
            },
            'multipliers': {
                'sentiment': round(sentiment_boost, 3),
                'volume': round(volume_mult, 2),
                'move': round(move_penalty, 2)
            }
        },
        
        'decision': {
            'instrument': instrument,
            'strategy': strategy_type,
            'can_trade_options': can_trade_options,
            'rationale': (
                f'{primary_direction} setup: '
                f'Price {"above" if primary_direction == "BULL" else "below"} SMA20, '
                f'trend {"strong" if can_trade_options else "weak"} (state={trend_state}), '
                f'{move_reason.lower()}, '
                f'volume {volume_reason.split("(")[0].strip().lower()}, '
                f'sentiment {sentiment_reason.lower()}'
            )
        },
        
        'options_note': (
            f'Day trade (0-1 DTE): High confidence ({adaptive_threshold:.2f}) + volume surge' if strategy_type == 'day_trade'
            else 'Swing trade (7-30 DTE): Moderate confidence' if strategy_type == 'swing_trade'
            else 'Stock: Lower risk (weak trend or high vol)' if instrument == 'STOCK'
            else None
        )
    }
    
    return (action, instrument, strategy_type, confidence, reason)


# =============================================================================
# FUTURE ENHANCEMENTS
# =============================================================================

def check_options_gates(ticker, features, greeks=None):
    """
    Options-specific gates to implement when greeks data available.
    
    CRITICAL for live options trading:
    1. IV percentile < 80 (don't buy expensive options)
    2. Bid/ask spread < 10%
    3. Option volume >= 100
    4. Open interest >= 100
    
    These should be HARD GATES enforced at execution time in dispatcher.
    
    Returns:
        Tuple of (pass, reason)
    """
    # TODO: Implement when greeks table exists
    # For now, this returns True but should be implemented before live trading
    return (True, "Options gates not yet implemented - REQUIRED before live trading")
