"""
Database operations for classifier worker
Implements SKIP LOCKED pattern for concurrent workers
"""

import psycopg2
from typing import List, Dict, Any, Optional
from datetime import datetime

class DatabaseClient:
    """Database client with transaction management"""
    
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
    
    def claim_unprocessed_batch(self, batch_size: int) -> List[Dict[str, Any]]:
        """
        Claim a batch of unprocessed events using SKIP LOCKED
        Returns list of events to process
        """
        self.connect()
        
        with self.conn.cursor() as cursor:
            # Use FOR UPDATE SKIP LOCKED to claim rows for processing
            # This prevents multiple workers from grabbing the same rows
            cursor.execute("""
                SELECT 
                    id,
                    event_uid,
                    title,
                    summary,
                    source,
                    published_at
                FROM inbound_events_raw
                WHERE processed_at IS NULL
                ORDER BY fetched_at ASC
                LIMIT %s
                FOR UPDATE SKIP LOCKED
            """, (batch_size,))
            
            rows = cursor.fetchall()
            
            # Convert to list of dictionaries
            events = []
            for row in rows:
                events.append({
                    'id': row[0],
                    'event_uid': row[1],
                    'title': row[2],
                    'summary': row[3],
                    'source': row[4],
                    'published_at': row[5]
                })
            
            return events
    
    def save_classification(
        self,
        raw_event_id: int,
        sentiment: str,
        sentiment_score: float,
        extracted_tickers: List[str],
        error: Optional[str] = None
    ) -> bool:
        """
        Save classification result and mark raw event as processed
        Returns True if successful, False if duplicate
        """
        try:
            with self.conn.cursor() as cursor:
                # Insert into classified table (idempotent via UNIQUE constraint)
                cursor.execute("""
                    INSERT INTO inbound_events_classified 
                        (raw_event_id, sentiment_label, sentiment_score, tickers)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (raw_event_id) DO NOTHING
                """, (raw_event_id, sentiment, sentiment_score, extracted_tickers))
                
                inserted = cursor.rowcount > 0
                
                # Mark raw event as processed
                cursor.execute("""
                    UPDATE inbound_events_raw
                    SET processed_at = NOW()
                    WHERE id = %s
                """, (raw_event_id,))
                
                return inserted
                
        except Exception as e:
            # Log error but don't fail the whole batch
            print(f"Error saving classification for event {raw_event_id}: {e}")
            return False
    
    def commit(self):
        """Commit current transaction"""
        if self.conn and not self.conn.closed:
            self.conn.commit()
    
    def rollback(self):
        """Rollback current transaction"""
        if self.conn and not self.conn.closed:
            self.conn.rollback()
    
    def get_unprocessed_count(self) -> int:
        """Get count of unprocessed events"""
        self.connect()
        
        with self.conn.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) 
                FROM inbound_events_raw 
                WHERE processed_at IS NULL
            """)
            return cursor.fetchone()[0]
