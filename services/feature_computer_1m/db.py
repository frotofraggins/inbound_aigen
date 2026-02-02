"""
Database operations for feature computer
Handles telemetry queries and feature upserts
"""

import psycopg2
from typing import List, Tuple, Dict, Any
from datetime import datetime

class FeatureDB:
    """Database client for feature computation"""
    
    def __init__(self, db_config: Dict[str, Any]):
        self.db_config = db_config
        self.conn = None
    
    def connect(self):
        """Establish database connection"""
        if self.conn is None or self.conn.closed:
            self.conn = psycopg2.connect(**self.db_config, connect_timeout=10)
    
    def close(self):
        """Close database connection"""
        if self.conn and not self.conn.closed:
            self.conn.close()
    
    def get_last_telemetry(
        self,
        ticker: str,
        min_bars: int = 50
    ) -> List[Tuple[datetime, float, float, float, float, int]]:
        """
        Get sufficient telemetry for a ticker using adaptive lookback.
        Tries progressively longer windows until min_bars found or exhausted.
        
        Args:
            ticker: Stock symbol
            min_bars: Minimum bars needed (default 50 for SMA50)
            
        Returns:
            List of (ts, open, high, low, close, volume) tuples ordered ascending
        """
        self.connect()
        
        # Progressive lookback windows: 2h, 6h, 12h, 24h, 3d, all available
        lookback_minutes = [120, 360, 720, 1440, 4320, None]
        
        for minutes in lookback_minutes:
            with self.conn.cursor() as cursor:
                if minutes is None:
                    # Final attempt: get all available data
                    cursor.execute("""
                        SELECT ts, open, high, low, close, volume
                        FROM lane_telemetry
                        WHERE ticker = %s
                        ORDER BY ts ASC
                    """, (ticker,))
                else:
                    cursor.execute("""
                        SELECT ts, open, high, low, close, volume
                        FROM lane_telemetry
                        WHERE ticker = %s
                          AND ts >= NOW() - INTERVAL '%s minutes'
                        ORDER BY ts ASC
                    """, (ticker, minutes))
                
                rows = cursor.fetchall()
                
                # Return if we have enough bars
                if len(rows) >= min_bars:
                    return rows
        
        # Return whatever we found, even if insufficient
        return rows if 'rows' in locals() else []
    
    def get_iv_history(self, ticker: str, days: int = 252) -> List[float]:
        """
        Get historical IV values for IV rank calculation
        
        Args:
            ticker: Stock symbol
            days: Number of days to look back (default 252 = 1 year)
            
        Returns:
            List of IV values from most recent 'days' days
        """
        self.connect()
        
        with self.conn.cursor() as cursor:
            cursor.execute("""
                SELECT implied_volatility
                FROM iv_history
                WHERE ticker = %s
                  AND recorded_at >= NOW() - INTERVAL '%s days'
                ORDER BY recorded_at DESC
            """, (ticker, days))
            
            results = cursor.fetchall()
            return [float(row[0]) for row in results if row[0] is not None]
    
    def store_iv_value(self, ticker: str, implied_volatility: float) -> bool:
        """
        Store an IV observation for future IV rank calculations
        
        Args:
            ticker: Stock symbol
            implied_volatility: IV value to store
            
        Returns:
            True if successful
        """
        self.connect()
        
        try:
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO iv_history (ticker, implied_volatility, recorded_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (ticker, recorded_at) DO UPDATE
                    SET implied_volatility = EXCLUDED.implied_volatility
                """, (ticker, implied_volatility))
                
            self.conn.commit()
            return True
            
        except Exception as e:
            self.conn.rollback()
            print(f"Error storing IV for {ticker}: {e}")
            return False
    
    def upsert_lane_features(self, features: Dict[str, Any]) -> bool:
        """
        Upsert computed features into lane_features table
        
        Args:
            features: Dictionary with keys matching lane_features columns
            
        Returns:
            True if successful
        """
        self.connect()
        
        try:
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO lane_features 
                        (ticker, ts, sma20, sma50, recent_vol, baseline_vol, 
                         vol_ratio, distance_sma20, distance_sma50, trend_state, 
                         close, computed_at,
                         volume_current, volume_avg_20, volume_ratio, volume_surge)
                    VALUES 
                        (%(ticker)s, %(ts)s, %(sma20)s, %(sma50)s, %(recent_vol)s,
                         %(baseline_vol)s, %(vol_ratio)s, %(distance_sma20)s, 
                         %(distance_sma50)s, %(trend_state)s, %(close)s, NOW(),
                         %(volume_current)s, %(volume_avg_20)s, %(volume_ratio)s, %(volume_surge)s)
                    ON CONFLICT (ticker, ts)
                    DO UPDATE SET
                        sma20 = EXCLUDED.sma20,
                        sma50 = EXCLUDED.sma50,
                        recent_vol = EXCLUDED.recent_vol,
                        baseline_vol = EXCLUDED.baseline_vol,
                        vol_ratio = EXCLUDED.vol_ratio,
                        distance_sma20 = EXCLUDED.distance_sma20,
                        distance_sma50 = EXCLUDED.distance_sma50,
                        trend_state = EXCLUDED.trend_state,
                        close = EXCLUDED.close,
                        computed_at = NOW(),
                        volume_current = EXCLUDED.volume_current,
                        volume_avg_20 = EXCLUDED.volume_avg_20,
                        volume_ratio = EXCLUDED.volume_ratio,
                        volume_surge = EXCLUDED.volume_surge
                """, features)
                
            self.conn.commit()
            return True
            
        except Exception as e:
            self.conn.rollback()
            print(f"Error upserting features for {features.get('ticker')}: {e}")
            return False
