"""
Database storage for telemetry data
Implements bulk upsert with conflict resolution
"""

import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime
from typing import List, Dict, Any

class TelemetryStore:
    """Database client for telemetry storage"""
    
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
    
    def upsert_candles(self, candles: List[Dict]) -> int:
        """
        Bulk upsert candles into lane_telemetry table
        
        Args:
            candles: List of candle dictionaries with keys:
                ticker, ts, open, high, low, close, volume
        
        Returns:
            Number of rows upserted
        """
        if not candles:
            return 0
        
        self.connect()
        
        try:
            with self.conn.cursor() as cursor:
                # Prepare data for bulk insert
                values = [
                    (
                        candle['ticker'],
                        candle['ts'],
                        candle['open'],
                        candle['high'],
                        candle['low'],
                        candle['close'],
                        candle['volume']
                    )
                    for candle in candles
                ]
                
                # Use execute_values for efficient bulk insert
                # ON CONFLICT updates existing rows
                execute_values(
                    cursor,
                    """
                    INSERT INTO lane_telemetry (ticker, ts, open, high, low, close, volume)
                    VALUES %s
                    ON CONFLICT (ticker, ts) 
                    DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume
                    """,
                    values
                )
                
                rows_affected = cursor.rowcount
                
            self.conn.commit()
            return rows_affected
            
        except Exception as e:
            self.conn.rollback()
            raise e
    
    def get_latest_timestamp(self, ticker: str) -> datetime:
        """
        Get the most recent candle timestamp for a ticker
        
        Args:
            ticker: Stock symbol
            
        Returns:
            Latest timestamp or None
        """
        self.connect()
        
        with self.conn.cursor() as cursor:
            cursor.execute("""
                SELECT MAX(ts)
                FROM lane_telemetry
                WHERE ticker = %s
            """, (ticker,))
            
            result = cursor.fetchone()
            return result[0] if result else None
    
    def get_row_count(self, ticker: str, minutes: int = 120) -> int:
        """
        Get row count for ticker in last N minutes
        
        Args:
            ticker: Stock symbol
            minutes: Time window
            
        Returns:
            Row count
        """
        self.connect()
        
        with self.conn.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*)
                FROM lane_telemetry
                WHERE ticker = %s
                  AND ts >= NOW() - INTERVAL '%s minutes'
            """, (ticker, minutes))
            
            return cursor.fetchone()[0]
