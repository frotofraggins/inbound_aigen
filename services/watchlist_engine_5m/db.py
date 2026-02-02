"""
Database operations for watchlist engine
Queries features, sentiment, and manages watchlist state
"""

import psycopg2
import psycopg2.extras
from typing import Dict, List, Any
from datetime import datetime, timezone

class WatchlistDB:
    """Database client for watchlist operations"""
    
    def __init__(self, db_config: Dict[str, Any]):
        self.db_config = db_config
        self.conn = None
    
    def connect(self):
        """Establish database connection"""
        if self.conn is None or self.conn.closed:
            self.conn = psycopg2.connect(**self.db_config, connect_timeout=10)
            self.conn.autocommit = True
    
    def close(self):
        """Close database connection"""
        if self.conn and not self.conn.closed:
            self.conn.close()
    
    def fetch_latest_features(self, tickers: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get latest lane_features row per ticker"""
        if not tickers:
            return {}
        
        sql = """
        SELECT DISTINCT ON (ticker)
            ticker, ts, close,
            sma20, sma50,
            recent_vol, baseline_vol, vol_ratio,
            distance_sma20, distance_sma50,
            trend_state,
            computed_at
        FROM lane_features_clean
        WHERE ticker = ANY(%s)
        ORDER BY ticker, computed_at DESC
        """
        
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (tickers,))
            rows = cur.fetchall()
        
        return {r["ticker"]: dict(r) for r in rows}
    
    def fetch_news_agg(
        self,
        tickers: List[str],
        lookback_minutes: int
    ) -> Dict[str, Dict[str, Any]]:
        """Aggregate sentiment data for tickers"""
        if not tickers:
            return {}
        
        sql = """
        WITH recent AS (
          SELECT
            c.tickers,
            c.sentiment_score,
            c.created_at
          FROM inbound_events_classified c
          WHERE c.created_at >= NOW() - (%s || ' minutes')::interval
        ),
        exploded AS (
          SELECT
            UNNEST(tickers) AS ticker,
            sentiment_score,
            created_at
          FROM recent
        ),
        filtered AS (
          SELECT *
          FROM exploded
          WHERE ticker = ANY(%s)
        )
        SELECT
          ticker,
          COUNT(*)::int AS news_count,
          AVG(sentiment_score)::float AS avg_sentiment_score,
          ABS(AVG(sentiment_score))::float AS avg_abs_sentiment_score,
          EXTRACT(EPOCH FROM (NOW() - MAX(created_at)))::float AS most_recent_event_age_seconds
        FROM filtered
        GROUP BY ticker
        """
        
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (lookback_minutes, tickers))
            rows = cur.fetchall()
        
        out = {r["ticker"]: dict(r) for r in rows}
        
        # Default values for tickers with no news
        for t in tickers:
            if t not in out:
                out[t] = {
                    "ticker": t,
                    "news_count": 0,
                    "avg_sentiment_score": 0.0,
                    "avg_abs_sentiment_score": 0.0,
                    "most_recent_event_age_seconds": float(lookback_minutes * 60)
                }
        
        return out
    
    def fetch_current_watchlist(self) -> Dict[str, Dict[str, Any]]:
        """Get current active watchlist"""
        sql = """
        SELECT ticker, watch_score, rank, reasons, in_watchlist AS active, computed_at
        FROM watchlist_state
        WHERE in_watchlist = TRUE
        ORDER BY rank ASC
        """
        
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            rows = cur.fetchall()
        
        return {r["ticker"]: dict(r) for r in rows}
    
    def upsert_watchlist_state(self, rows: List[Dict[str, Any]]):
        """Bulk upsert watchlist state"""
        if not rows:
            return
        
        sql = """
        INSERT INTO watchlist_state 
            (ticker, watch_score, rank, reasons, in_watchlist, computed_at)
        VALUES %s
        ON CONFLICT (ticker) DO UPDATE SET
            watch_score = EXCLUDED.watch_score,
            rank = EXCLUDED.rank,
            reasons = EXCLUDED.reasons,
            in_watchlist = EXCLUDED.in_watchlist,
            computed_at = EXCLUDED.computed_at,
            last_score_update = EXCLUDED.computed_at
        """
        
        tuples = [
            (
                r["ticker"],
                float(r["watch_score"]),
                int(r["rank"]),
                psycopg2.extras.Json(r.get("reasons", {})),
                bool(r.get("active", True)),
                r.get("computed_at") or datetime.now(timezone.utc)
            )
            for r in rows
        ]
        
        with self.conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, sql, tuples, page_size=200)
