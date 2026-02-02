"""
Watch score computation
Combines sentiment, volatility, trend, and setup quality
"""

from typing import Dict, Any, Tuple

def clamp01(x: float) -> float:
    """Clamp value to 0-1 range"""
    return max(0.0, min(1.0, x))

def compute_watch_score(
    features: Dict[str, Any],
    news: Dict[str, Any]
) -> Tuple[float, Dict[str, Any]]:
    """
    Compute watch score and reasoning
    
    Returns: (score, reasons_dict)
    """
    
    # Sentiment pressure (news activity + strength)
    news_count = float(news.get("news_count", 0) or 0)
    count_score = clamp01(news_count / 5.0)  # Saturate at 5 events
    
    abs_sent = float(news.get("avg_abs_sentiment_score", 0.0) or 0.0)
    abs_sent_score = clamp01(abs_sent)
    
    age_s = float(news.get("most_recent_event_age_seconds", 3600.0) or 3600.0)
    recency_score = clamp01(1.0 - (age_s / 3600.0))
    
    sentiment_pressure = clamp01(
        0.50 * abs_sent_score +
        0.30 * count_score +
        0.20 * recency_score
    )
    
    # Setup quality (not overextended)
    dist20 = abs(float(features.get("distance_sma20", 0.0) or 0.0))
    setup_quality = clamp01(1.0 - (dist20 / 0.01))
    
    # Volatility score
    vol_ratio = float(features.get("vol_ratio", 1.0) or 1.0)
    vol_score = clamp01((vol_ratio - 0.7) / (1.5 - 0.7))
    
    # Trend alignment
    trend_state = int(features.get("trend_state", 0) or 0)
    avg_sent = float(news.get("avg_sentiment_score", 0.0) or 0.0)
    
    sent_dir = 0
    if avg_sent > 0.05:
        sent_dir = 1
    elif avg_sent < -0.05:
        sent_dir = -1
    
    if trend_state == 0 or sent_dir == 0:
        trend_alignment = 0.5
    else:
        trend_alignment = 1.0 if (trend_state == sent_dir) else 0.0
    
    # Combined score
    watch_score = clamp01(
        0.35 * sentiment_pressure +
        0.25 * setup_quality +
        0.20 * vol_score +
        0.20 * trend_alignment
    )
    
    reasons = {
        "news_count": news_count,
        "avg_sentiment": avg_sent,
        "sentiment_pressure": round(sentiment_pressure, 3),
        "setup_quality": round(setup_quality, 3),
        "vol_ratio": vol_ratio,
        "vol_score": round(vol_score, 3),
        "trend_state": trend_state,
        "trend_alignment": trend_alignment,
        "close": features.get("close"),
        "sma20": features.get("sma20"),
        "sma50": features.get("sma50")
    }
    
    return watch_score, reasons
