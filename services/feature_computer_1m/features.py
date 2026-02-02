"""
Technical indicator calculations
Pure functions for SMA, volatility, and derived metrics
"""

import numpy as np
import pandas as pd
from typing import List, Tuple, Optional, Dict
from datetime import datetime

def compute_sma(closes: List[float], period: int) -> Optional[float]:
    """Compute Simple Moving Average"""
    if len(closes) < period:
        return None
    return float(np.mean(closes[-period:]))

def compute_volatility(closes: List[float]) -> Optional[float]:
    """
    Compute volatility as standard deviation of returns
    
    Args:
        closes: List of close prices
        
    Returns:
        Volatility (stddev of returns) or None if insufficient data
    """
    if len(closes) < 2:
        return None
    
    # Compute returns
    returns = pd.Series(closes).pct_change().dropna()
    
    if len(returns) == 0:
        return None
    
    return float(returns.std())

def calculate_iv_rank(current_iv: float, iv_history: List[float]) -> float:
    """
    Calculate IV Rank: where current IV sits in 52-week range
    
    IV Rank = (Current IV - 52-week Low) / (52-week High - 52-week Low)
    
    Args:
        current_iv: Current implied volatility
        iv_history: List of historical IV values (ideally 252 days)
    
    Returns:
        Float from 0.0 to 1.0 (0 = lowest IV, 1 = highest IV in year)
        Returns 0.5 if insufficient history (< 30 observations)
    """
    if not iv_history or len(iv_history) < 30:
        # Not enough history, assume mid-range
        return 0.5
    
    iv_high = max(iv_history)
    iv_low = min(iv_history)
    
    # Handle edge case where high == low
    if iv_high == iv_low:
        return 0.5
    
    # Calculate rank
    iv_rank = (current_iv - iv_low) / (iv_high - iv_low)
    
    # Clamp to [0, 1]
    return max(0.0, min(1.0, iv_rank))


def compute_volume_features(
    telemetry_data: List[Tuple[datetime, float, float, float, float, int]],
) -> Optional[Dict]:
    """
    Calculate volume-based features for signal confirmation.
    
    This is THE critical missing piece - 100% of professional day traders use volume.
    Volume confirms breakouts, reversals, and trend strength.
    
    Args:
        telemetry_data: List of (ts, open, high, low, close, volume) tuples
        
    Returns:
        Dictionary with volume features:
        - volume_current: Most recent bar volume
        - volume_avg_20: 20-period average volume
        - volume_ratio: current / average (>2.0 = surge, <0.5 = dry)
        - volume_surge: True if ratio > 2.0
        
        Returns None if insufficient data (< 20 bars)
    """
    # Need at least 20 bars for volume average
    if len(telemetry_data) < 20:
        return None
    
    # Extract volumes
    volumes = [row[5] for row in telemetry_data]
    
    # Current volume (most recent bar)
    current_vol = volumes[-1]
    
    # 20-period average volume
    avg_vol = sum(volumes[-20:]) / 20
    
    # Volume ratio (handles edge case of zero average)
    if avg_vol > 0:
        ratio = current_vol / avg_vol
    else:
        ratio = 0.0
    
    # Volume surge detection (>2x average is significant)
    surge = ratio > 2.0
    
    return {
        'volume_current': current_vol,
        'volume_avg_20': int(avg_vol),
        'volume_ratio': round(ratio, 4),
        'volume_surge': surge
    }


def compute_features(
    telemetry_data: List[Tuple[datetime, float, float, float, float, int]],
    ticker: str
) -> Optional[Dict]:
    """
    Compute all features from telemetry data
    
    Args:
        telemetry_data: List of (ts, open, high, low, close, volume) tuples
        ticker: Stock symbol
        
    Returns:
        Dictionary of computed features or None if insufficient data
    """
    
    # Need at least 50 points for SMA50
    if len(telemetry_data) < 50:
        return None
    
    # Extract closes and timestamps
    timestamps = [row[0] for row in telemetry_data]
    closes = [row[4] for row in telemetry_data]
    
    # Latest values
    latest_ts = timestamps[-1]
    latest_close = closes[-1]
    
    # Compute SMAs
    sma20 = compute_sma(closes, 20)
    sma50 = compute_sma(closes, 50)
    
    if sma20 is None or sma50 is None:
        return None
    
    # Compute volatilities
    # Recent: last 30 minutes
    recent_closes = closes[-30:] if len(closes) >= 30 else closes
    recent_vol = compute_volatility(recent_closes)
    
    # Baseline: full 120 minutes
    baseline_vol = compute_volatility(closes)
    
    # Vol ratio (handle divide by zero)
    vol_ratio = None
    if recent_vol is not None and baseline_vol is not None and baseline_vol > 0:
        vol_ratio = recent_vol / baseline_vol
    
    # Distance from SMAs
    distance_sma20 = (latest_close - sma20) / sma20 if sma20 > 0 else None
    distance_sma50 = (latest_close - sma50) / sma50 if sma50 > 0 else None
    
    # Trend state
    if sma20 > sma50:
        trend_state = 1  # Bullish
    elif sma20 < sma50:
        trend_state = -1  # Bearish
    else:
        trend_state = 0  # Neutral
    
    # Compute volume features (Phase 12 addition)
    volume_features = compute_volume_features(telemetry_data)
    
    # Build feature dictionary
    features = {
        'ticker': ticker,
        'ts': latest_ts,
        'sma20': sma20,
        'sma50': sma50,
        'recent_vol': recent_vol,
        'baseline_vol': baseline_vol,
        'vol_ratio': vol_ratio,
        'distance_sma20': distance_sma20,
        'distance_sma50': distance_sma50,
        'trend_state': trend_state,
        'close': latest_close
    }
    
    # Add volume features if available
    if volume_features:
        features.update(volume_features)
    
    return features
