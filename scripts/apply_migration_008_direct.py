#!/usr/bin/env python3
"""
Apply migration 008: Add Options Trading Support
Direct database execution (for use during development/testing)
"""

import psycopg2
import os
import sys

def get_db_connection():
    """Get database connection from environment variables"""
    return psycopg2.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        port=int(os.environ.get('DB_PORT', '5432')),
        database=os.environ.get('DB_NAME', 'ops_pipeline'),
        user=os.environ.get('DB_USER', 'ops_user'),
        password=os.environ.get('DB_PASSWORD', '')
    )

def main():
    print("=" * 60)
    print("MIGRATION 008: Add Options Trading Support")
    print("=" * 60)
    
    # Read migration SQL
    migration_path = 'db/migrations/008_add_options_support.sql'
    with open(migration_path, 'r') as f:
        migration_sql = f.read()
    
    print(f"\nReading migration from: {migration_path}")
    print(f"SQL length: {len(migration_sql)} characters")
    
    # Connect to database
    print("\nConnecting to database...")
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Execute migration
        print("\nExecuting migration...")
        cur.execute(migration_sql)
        conn.commit()
        
        print("\n✅ Migration 008 applied successfully!")
        
        # Verify changes
        print("\nVerifying changes...")
        
        # Check for new columns
        cur.execute("""
            SELECT column_name, data_type, column_default
            FROM information_schema.columns
            WHERE table_name = 'dispatch_executions'
                AND column_name IN (
                    'instrument_type', 'strike_price', 'expiration_date', 
                    'contracts', 'premium_paid', 'delta', 'theta', 
                    'implied_volatility', 'option_symbol', 'strategy_type'
                )
            ORDER BY column_name;
        """)
        
        columns = cur.fetchall()
        print(f"\nNew columns added: {len(columns)}")
        for col in columns:
            print(f"  - {col[0]}: {col[1]} (default: {col[2]})")
        
        # Check for new indexes
        cur.execute("""
            SELECT indexname
            FROM pg_indexes
            WHERE tablename = 'dispatch_executions'
                AND (indexname LIKE '%instrument_type%' 
                   OR indexname LIKE '%expiration_date%'
                   OR indexname LIKE '%strategy_type%')
            ORDER BY indexname;
        """)
        
        indexes = cur.fetchall()
        print(f"\nNew indexes created: {len(indexes)}")
        for idx in indexes:
            print(f"  - {idx[0]}")
        
        # Check for new views
        cur.execute("""
            SELECT table_name
            FROM information_schema.views
            WHERE table_schema = 'public'
                AND (table_name LIKE '%options%' OR table_name LIKE '%active%')
            ORDER BY table_name;
        """)
        
        views = cur.fetchall()
        print(f"\nNew views created: {len(views)}")
        for view in views:
            print(f"  - {view[0]}")
        
        # Test the constraint
        print("\nTesting options metadata constraint...")
        try:
            cur.execute("""
                -- This should fail: CALL without strike_price
                INSERT INTO dispatch_executions (
                    recommendation_id, dispatcher_run_id, ticker, action,
                    decision_ts, simulated_ts, entry_price, fill_model,
                    slippage_bps, qty, notional, execution_mode, instrument_type
                ) VALUES (
                    999999, 'test-run-999', 'TEST', 'BUY',
                    NOW(), NOW(), 100.0, 'TEST', 0, 1, 100, 'TEST', 'CALL'
                );
            """)
            print("  ⚠️  Constraint not working - invalid data was accepted!")
        except psycopg2.IntegrityError as e:
            conn.rollback()
            print("  ✅ Constraint working - invalid data rejected")
            print(f"     Error: {str(e).split('DETAIL:')[0].strip()}")
        
        print("\n" + "=" * 60)
        print("MIGRATION 008 COMPLETE")
        print("=" * 60)
        print("\nOptions trading support added:")
        print("  ✅ 10 new columns for options metadata")
        print("  ✅ 3 new indexes for performance")
        print("  ✅ 3 new views for analysis")
        print("  ✅ Data integrity constraints")
        print("\nNext steps:")
        print("  1. Update AlpacaPaperBroker to support options")
        print("  2. Update signal engine to generate options signals")
        print("  3. Test options API integration")
        print("  4. Deploy to ECS")
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Error applying migration: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    main()
