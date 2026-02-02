#!/usr/bin/env python3
"""
Apply Migration 011 Directly to Database
Bypasses migration Lambda and applies SQL directly
"""

import os
import psycopg2

def apply_migration_direct():
    """Apply migration 011 directly via psycopg2"""
    
    # Get DB connection from environment
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        print("❌ DATABASE_URL not set")
        return False
    
    # Read migration SQL
    script_dir = os.path.dirname(os.path.abspath(__file__))
    migration_path = os.path.join(script_dir, '..', 'db', 'migrations', '011_add_learning_infrastructure.sql')
    
    with open(migration_path, 'r') as f:
        migration_sql = f.read()
    
    print(f"Applying Migration 011 directly...")
    print(f"Migration size: {len(migration_sql)} bytes")
    print()
    
    try:
        # Connect to database
        conn = psycopg2.connect(db_url)
        conn.autocommit = False
        
        cur = conn.cursor()
        
        # Execute migration
        cur.execute(migration_sql)
        
        # Commit
        conn.commit()
        
        print("✅ Migration 011 applied successfully!")
        print()
        
        # Verify
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'dispatch_recommendations' 
              AND column_name IN ('features_snapshot', 'sentiment_snapshot')
        """)
        
        columns = [row[0] for row in cur.fetchall()]
        print(f"Verified columns added: {columns}")
        
        cur.close()
        conn.close()
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return False

if __name__ == "__main__":
    import sys
    success = apply_migration_direct()
    sys.exit(0 if success else 1)
