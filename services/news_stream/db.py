"""
Database operations for News Stream
"""
import psycopg2
import psycopg2.extras
import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime

from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """Database connection manager"""
    
    def __init__(self):
        self.conn = None
        
    def connect(self):
        """Establish database connection"""
        try:
            self.conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                dbname=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                connect_timeout=10
            )
            logger.info("Database connection established")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def store_news_item(news: Dict[str, Any]) -> Optional[int]:
    """
    Store a news item in the database.
    Uses external_id for deduplication.
    
    Returns:
        News ID if inserted/updated, None if duplicate
    """
    query = """
    INSERT INTO inbound_news (
        source, title, summary, content, author, url,
        published_at, tickers, external_id, source_type
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
    )
    ON CONFLICT (external_id) DO NOTHING
    RETURNING id
    """
    
    try:
        with DatabaseConnection() as db:
            with db.conn.cursor() as cur:
                cur.execute(query, (
                    news.get('source', 'Alpaca'),
                    news.get('title'),
                    news.get('summary', ''),
                    news.get('content', ''),
                    news.get('author', 'Unknown'),
                    news.get('url'),
                    news.get('published_at'),
                    news.get('tickers', []),
                    news.get('external_id'),
                    news.get('source_type', 'alpaca_websocket')
                ))
                
                result = cur.fetchone()
                if result:
                    news_id = result[0]
                    db.conn.commit()
                    return news_id
                else:
                    # Duplicate - external_id already exists
                    return None
                    
    except Exception as e:
        logger.error(f"Error storing news item: {e}")
        return None
