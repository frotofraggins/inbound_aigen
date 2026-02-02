"""
Database operations for Signal Engine.
Handles queries for watchlist, features, sentiment, and recommendations.
"""
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from decimal import Decimal

def convert_decimals(data):
    """
    Recursively convert Decimal objects to float for JSON serialization.
    Handles dicts, lists, and nested structures.
    """
    if isinstance(data, dict):
        return {k: convert_decimals(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [convert_decimals(item) for item in data]
    elif isinstance(data, Decimal):
        return float(data)
    else:
        return data

def get_connection(config):
    """Create database connection."""
    return psycopg2.connect(
        host=config['db_host'],
        port=config['db_port'],
        database=config['db_name'],
        user=config['db_user'],
        password=config['db_password']
    )

def get_watchlist_top30(conn):
    """
    Get current top 30 stocks from watchlist.
    Returns list of dicts with ticker and rank.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT ticker, watch_score, rank
            FROM watchlist_state
            WHERE in_watchlist = TRUE
            ORDER BY rank
            LIMIT 30
        """)
        return cur.fetchall()

def get_latest_features(conn, tickers):
    """
    Get latest computed features for given tickers.
    Returns dict keyed by ticker.
    
    Phase 12: Now includes volume features (volume_ratio, volume_surge, etc.)
    """
    if not tickers:
        return {}
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT DISTINCT ON (ticker)
                ticker,
                close,
                sma20,
                sma50,
                distance_sma20,
                distance_sma50,
                recent_vol,
                baseline_vol,
                vol_ratio,
                trend_state,
                computed_at,
                volume_current,
                volume_avg_20,
                volume_ratio,
                volume_surge
            FROM lane_features
            WHERE ticker = ANY(%s)
            ORDER BY ticker, computed_at DESC
        """, (tickers,))
        
        rows = cur.fetchall()
        # Convert Decimals to floats for JSON serialization
        return {row['ticker']: convert_decimals(dict(row)) for row in rows}

def get_recent_sentiment(conn, tickers, window_minutes=30):
    """
    Get aggregated sentiment for tickers from recent news.
    Returns dict keyed by ticker with sentiment direction and confidence.
    
    NOTE: sentiment_score in DB is CONFIDENCE (0-1), not direction.
    sentiment_label ('positive'/'negative'/'neutral') indicates direction.
    """
    if not tickers:
        return {}
    
    cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            WITH confident_news AS (
                SELECT 
                    UNNEST(tickers) as ticker,
                    sentiment_label,
                    sentiment_score,
                    created_at,
                    -- Convert label+confidence to directional score
                    CASE 
                        WHEN sentiment_label = 'positive' THEN sentiment_score
                        WHEN sentiment_label = 'negative' THEN -sentiment_score
                        ELSE 0
                    END as directional_score
                FROM inbound_events_classified
                WHERE created_at > %s
                  AND tickers && %s
                  AND sentiment_score > 0.65  -- Only use confident classifications
            )
            SELECT 
                ticker,
                COUNT(*) as news_count,
                -- Average directional score: +1 = very bullish, -1 = very bearish
                AVG(directional_score) as avg_score,
                MAX(created_at) as latest_at,
                COUNT(*) FILTER (WHERE sentiment_label = 'positive') as positive_count,
                COUNT(*) FILTER (WHERE sentiment_label = 'negative') as negative_count,
                COUNT(*) FILTER (WHERE sentiment_label = 'neutral') as neutral_count
            FROM confident_news
            WHERE ticker = ANY(%s)
            GROUP BY ticker
        """, (cutoff, tickers, tickers))
        
        rows = cur.fetchall()
        # Convert Decimals to floats for JSON serialization
        return {row['ticker']: convert_decimals(dict(row)) for row in rows}

def check_cooldown(conn, ticker, cooldown_minutes=15):
    """
    Check if ticker is in cooldown period (recent recommendation exists).
    Returns True if in cooldown, False if okay to signal.
    """
    cutoff = datetime.utcnow() - timedelta(minutes=cooldown_minutes)
    
    with conn.cursor() as cur:
        cur.execute("""
            SELECT EXISTS (
                SELECT 1
                FROM dispatch_recommendations
                WHERE ticker = %s
                  AND created_at > %s
            )
        """, (ticker, cutoff))
        
        return cur.fetchone()[0]

def insert_recommendation(conn, ticker, action, instrument_type, strategy_type, confidence, reason, features_snapshot=None, sentiment_snapshot=None):
    """
    Insert a new trading recommendation.
    
    Phase 15: Now includes strategy_type for options trading.
    Phase 16: Now includes feature and sentiment snapshots for reproducible learning.
    
    Args:
        ticker: Stock symbol
        action: 'BUY' or 'SELL' (or 'HOLD')
        instrument_type: 'CALL', 'PUT', 'STOCK', 'PREMIUM'
        strategy_type: 'day_trade', 'swing_trade', 'conservative' (or None for stocks)
        confidence: 0.0-1.0
        reason: dict with explanation (stored as JSONB)
        features_snapshot: dict with frozen technical indicators at decision time (Phase 16)
        sentiment_snapshot: dict with frozen sentiment data at decision time (Phase 16)
    
    Returns: recommendation_id
    """
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO dispatch_recommendations (
                ticker,
                action,
                instrument_type,
                strategy_type,
                confidence,
                reason,
                features_snapshot,
                sentiment_snapshot,
                status,
                created_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, 'PENDING', NOW()
            )
            RETURNING id
        """, (ticker, action, instrument_type, strategy_type, confidence, reason, features_snapshot, sentiment_snapshot))
        
        recommendation_id = cur.fetchone()[0]
        conn.commit()
        return recommendation_id
