#!/usr/bin/env python3
"""
Test Database Migration 008
Validates options columns, indexes, views, and constraints.

Run this AFTER applying migration 008 to verify it worked correctly.
"""

import sys
import os
import psycopg2
from psycopg2.extras import RealDictCursor

def get_db_connection():
    """Get database connection from environment"""
    return psycopg2.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        port=int(os.environ.get('DB_PORT', '5432')),
        database=os.environ.get('DB_NAME', 'ops_pipeline'),
        user=os.environ.get('DB_USER', 'ops_user'),
        password=os.environ.get('DB_PASSWORD', '')
    )

def test_columns_exist():
    """Test 1: Verify all new columns exist"""
    print("\n" + "="*60)
    print("TEST 1: New Columns Exist")
    print("="*60)
    
    expected_columns = [
        'instrument_type', 'strike_price', 'expiration_date',
        'contracts', 'premium_paid', 'delta', 'theta',
        'implied_volatility', 'option_symbol', 'strategy_type'
    ]
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT column_name, data_type, column_default
            FROM information_schema.columns
            WHERE table_name = 'dispatch_executions'
                AND column_name = ANY(%s)
            ORDER BY column_name;
        """, (expected_columns,))
        
        rows = cur.fetchall()
        found_columns = [row[0] for row in rows]
        
        if len(found_columns) == len(expected_columns):
            print(f"✅ PASS: All {len(expected_columns)} columns exist")
            for col_name, data_type, default in rows:
                print(f"  - {col_name}: {data_type} (default: {default})")
            conn.close()
            return True
        else:
            missing = set(expected_columns) - set(found_columns)
            print(f"❌ FAIL: Missing columns: {missing}")
            conn.close()
            return False
            
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False

def test_indexes_exist():
    """Test 2: Verify indexes created"""
    print("\n" + "="*60)
    print("TEST 2: Indexes Exist")
    print("="*60)
    
    expected_indexes = [
        'idx_dispatch_executions_instrument_type',
        'idx_dispatch_executions_expiration_date',
        'idx_dispatch_executions_strategy_type'
    ]
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT indexname
            FROM pg_indexes
            WHERE tablename = 'dispatch_executions'
                AND indexname = ANY(%s)
            ORDER BY indexname;
        """, (expected_indexes,))
        
        rows = cur.fetchall()
        found_indexes = [row[0] for row in rows]
        
        if len(found_indexes) == len(expected_indexes):
            print(f"✅ PASS: All {len(expected_indexes)} indexes exist")
            for idx in found_indexes:
                print(f"  - {idx}")
            conn.close()
            return True
        else:
            missing = set(expected_indexes) - set(found_indexes)
            print(f"❌ FAIL: Missing indexes: {missing}")
            conn.close()
            return False
            
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False

def test_views_exist():
    """Test 3: Verify views created"""
    print("\n" + "="*60)
    print("TEST 3: Views Exist")
    print("="*60)
    
    expected_views = [
        'active_options_positions',
        'options_performance_by_strategy',
        'daily_options_summary'
    ]
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT table_name
            FROM information_schema.views
            WHERE table_schema = 'public'
                AND table_name = ANY(%s)
            ORDER BY table_name;
        """, (expected_views,))
        
        rows = cur.fetchall()
        found_views = [row[0] for row in rows]
        
        if len(found_views) == len(expected_views):
            print(f"✅ PASS: All {len(expected_views)} views exist")
            for view in found_views:
                print(f"  - {view}")
            conn.close()
            return True
        else:
            missing = set(expected_views) - set(found_views)
            print(f"❌ FAIL: Missing views: {missing}")
            conn.close()
            return False
            
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False

def test_constraint_works():
    """Test 4: Verify options constraint enforced"""
    print("\n" + "="*60)
    print("TEST 4: Options Constraint Works")
    print("="*60)
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Try to insert CALL without strike_price (should fail)
        try:
            cur.execute("""
                INSERT INTO dispatch_executions (
                    recommendation_id, dispatcher_run_id, ticker, action,
                    decision_ts, simulated_ts, entry_price, fill_model,
                    slippage_bps, qty, notional, execution_mode, instrument_type
                ) VALUES (
                    999999, 'test-run-999', 'TEST', 'BUY',
                    NOW(), NOW(), 100.0, 'TEST', 0, 1, 100, 'TEST', 'CALL'
                );
            """)
            conn.commit()
            print("❌ FAIL: Constraint not working - invalid data accepted")
            conn.close()
            return False
        except psycopg2.IntegrityError:
            conn.rollback()
            print("✅ PASS: Constraint rejected CALL without strike_price")
        
        # Try to insert valid CALL with strike_price (should succeed)
        try:
            cur.execute("""
                INSERT INTO dispatch_executions (
                    recommendation_id, dispatcher_run_id, ticker, action,
                    decision_ts, simulated_ts, entry_price, fill_model,
                    slippage_bps, qty, notional, execution_mode, instrument_type,
                    strike_price, expiration_date
                ) VALUES (
                    999998, 'test-run-998', 'TEST', 'BUY',
                    NOW(), NOW(), 100.0, 'TEST', 0, 1, 100, 'TEST', 'CALL',
                    150.00, CURRENT_DATE + INTERVAL '1 day'
                );
            """)
            conn.commit()
            print("✅ PASS: Constraint accepted valid CALL with strike_price")
            
            # Clean up test data
            cur.execute("DELETE FROM dispatch_executions WHERE recommendation_id IN (999998, 999999);")
            conn.commit()
            
        except psycopg2.IntegrityError as e:
            conn.rollback()
            print(f"❌ FAIL: Valid CALL was rejected: {e}")
            conn.close()
            return False
        
        conn.close()
        return True
            
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False

def test_views_query():
    """Test 5: Verify views can be queried"""
    print("\n" + "="*60)
    print("TEST 5: Views Can Be Queried")
    print("="*60)
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Test each view
        views_to_test = [
            'active_options_positions',
            'options_performance_by_strategy',
            'daily_options_summary'
        ]
        
        for view in views_to_test:
            try:
                cur.execute(f"SELECT * FROM {view} LIMIT 1;")
                print(f"✅ PASS: Can query {view}")
            except Exception as e:
                print(f"❌ FAIL: Cannot query {view}: {e}")
                conn.close()
                return False
        
        conn.close()
        return True
            
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False

def test_backward_compatibility():
    """Test 6: Verify stock trading still works"""
    print("\n" + "="*60)
    print("TEST 6: Backward Compatibility (Stock Trading)")
    print("="*60)
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Insert a stock trade (no options fields)
        try:
            cur.execute("""
                INSERT INTO dispatch_executions (
                    recommendation_id, dispatcher_run_id, ticker, action,
                    decision_ts, simulated_ts, entry_price, fill_model,
                    slippage_bps, qty, notional, execution_mode
                ) VALUES (
                    999997, 'test-run-997', 'TEST', 'BUY',
                    NOW(), NOW(), 100.0, 'TEST', 0, 10, 1000, 'TEST'
                );
            """)
            conn.commit()
            print("✅ PASS: Can still insert stock trades")
            
            # Verify instrument_type defaults to STOCK
            cur.execute("""
                SELECT instrument_type 
                FROM dispatch_executions 
                WHERE recommendation_id = 999997;
            """)
            instrument_type = cur.fetchone()[0]
            
            if instrument_type == 'STOCK':
                print("✅ PASS: instrument_type defaults to STOCK")
            else:
                print(f"❌ FAIL: Expected STOCK, got {instrument_type}")
                conn.close()
                return False
            
            # Clean up
            cur.execute("DELETE FROM dispatch_executions WHERE recommendation_id = 999997;")
            conn.commit()
            
        except Exception as e:
            conn.rollback()
            print(f"❌ FAIL: Cannot insert stock trade: {e}")
            conn.close()
            return False
        
        conn.close()
        return True
            
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False

def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("DATABASE MIGRATION 008 TEST SUITE")
    print("=" * 60)
    print("\nTesting options trading database schema...")
    print("Make sure migration 008 has been applied!")
    
    tests = [
        ("New Columns Exist", test_columns_exist),
        ("Indexes Exist", test_indexes_exist),
        ("Views Exist", test_views_exist),
        ("Options Constraint Works", test_constraint_works),
        ("Views Can Be Queried", test_views_query),
        ("Backward Compatibility", test_backward_compatibility),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            passed = test_func()
            results.append((test_name, passed))
        except Exception as e:
            print(f"\n❌ FATAL ERROR in {test_name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed_count}/{total_count} tests passed")
    
    if passed_count == total_count:
        print("\n🎉 ALL TESTS PASSED! Migration 008 applied successfully.")
        return 0
    else:
        print(f"\n⚠️  {total_count - passed_count} test(s) failed. Check migration.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
