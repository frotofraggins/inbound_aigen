"""
IV history access for dispatcher (kept local to avoid cross-service imports).
Provides minimal read/write access needed for IV rank checks.
"""

from typing import List, Dict, Any
import psycopg2


class IVHistoryDB:
    """Minimal IV history DB client for dispatcher."""

    def __init__(self, db_config: Dict[str, Any]):
        self.db_config = db_config
        self.conn = None

    def connect(self):
        if self.conn is None or self.conn.closed:
            self.conn = psycopg2.connect(
                host=self.db_config['db_host'],
                port=self.db_config['db_port'],
                database=self.db_config['db_name'],
                user=self.db_config['db_user'],
                password=self.db_config['db_password'],
                connect_timeout=10,
            )

    def close(self):
        if self.conn and not self.conn.closed:
            self.conn.close()

    def get_iv_history(self, ticker: str, days: int = 252) -> List[float]:
        self.connect()
        with self.conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT implied_volatility
                FROM iv_history
                WHERE ticker = %s
                  AND recorded_at >= NOW() - INTERVAL '%s days'
                ORDER BY recorded_at DESC
                """,
                (ticker, days),
            )
            results = cursor.fetchall()
        return [float(row[0]) for row in results if row[0] is not None]

    def store_iv_value(self, ticker: str, implied_volatility: float) -> bool:
        self.connect()
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO iv_history (ticker, implied_volatility, recorded_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (ticker, recorded_at) DO UPDATE
                    SET implied_volatility = EXCLUDED.implied_volatility
                    """,
                    (ticker, implied_volatility),
                )
            self.conn.commit()
            return True
        except Exception:
            self.conn.rollback()
            return False

