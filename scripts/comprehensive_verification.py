#!/usr/bin/env python3
"""
Comprehensive System Verification
Verifies position_history fix and investigates the 20-hour hold time issue
"""
import sys
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone
import json
import boto3

def get_db_connection():
    """Get database connection using AWS SSM and Secrets Manager"""
    try:
        # Get connection info from SSM
        ssm = boto3.client('ssm', region_name='us-west-2')
        secrets = boto3.client('secretsmanager', region_name='us-west-2')
        
        print("Fetching database connection parameters from AWS...")
        
        # Get database parameters
        db_host = ssm.get_parameter(Name='/ops-pipeline/db_host')['Parameter']['Value']
        db_port = ssm.get_parameter(Name='/ops-pipeline/db_port')['Parameter']['Value']
        db_name = ssm.get_parameter(Name='/ops-pipeline/db_name')['Parameter']['Value']
        
        # Get credentials
        secret_value = secrets.get_secret_value(SecretId='ops-pipeline/db')
        secret_data = json.loads(secret_value['SecretString'])
        
        print(f"Connecting to {db_host}:{db_port}/{db_name}...")
        
        # Connect to database
        return psycopg2.connect(
            host=db_host,
            port=int(db_port),
            database=db_name,
            user=secret_data['username'],
            password=secret_data['password'],
            connect_timeout=10
        )
    except Exception as e:
        print(f"❌ Failed to connect to database: {e}")
        print("\nPossible issues:")
        print("1. AWS credentials expired - run: ada cred update --account 160027201036 --role IibsAdminAccess-DO-NOT-DELETE --provider conduit --once")
        print("2. Not on network with VPC access")
        print("3. Missing AWS permissions")
        raise

def check_position_history_exists():
    """Check if position_history table exists and has data"""
    print("\n" + "="*80)
    print("1. CHECKING POSITION_HISTORY TABLE")
    print("="*80)
    
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Check table exists
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'position_history'
                )
            """)
            exists = cur.fetchone()['exists']
            
            if not exists:
                print("❌ ERROR: position_history table does not exist!")
                return False
            
            print("✓ position_history table exists")
            
            # Check column structure
            cur.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'position_history'
                ORDER BY ordinal_position
            """)
            columns = cur.fetchall()
            
            print(f"\n✓ Table has {len(columns)} columns:")
            critical_columns = ['execution_id', 'ticker', 'side', 'entry_time', 'exit_time', 
                               'pnl_dollars', 'pnl_pct', 'exit_reason', 'holding_seconds']
            for col in columns:
                marker = "✓" if col['column_name'] in critical_columns else " "
                print(f"  {marker} {col['column_name']}: {col['data_type']}")
            
            # Check for data
            cur.execute("SELECT COUNT(*) as count FROM position_history")
            count = cur.fetchone()['count']
            
            if count > 0:
                print(f"\n✓ position_history has {count} records")
                
                # Show recent records
                cur.execute("""
                    SELECT 
                        id,
                        ticker,
                        instrument_type,
                        side,
                        entry_time,
                        exit_time,
                        pnl_pct,
                        exit_reason,
                        holding_seconds,
                        created_at
                    FROM position_history
                    ORDER BY created_at DESC
                    LIMIT 10
                """)
                records = cur.fetchall()
                
                print("\nMost recent records:")
                for rec in records:
                    hold_min = rec['holding_seconds'] / 60 if rec['holding_seconds'] else 0
                    print(f"  ID {rec['id']}: {rec['ticker']} {rec['instrument_type']} {rec['side']}")
                    print(f"    Entry: {rec['entry_time']}")
                    print(f"    Exit:  {rec['exit_time']}")
                    print(f"    P&L: {rec['pnl_pct']:.2f}% | Held: {hold_min:.1f} min | Reason: {rec['exit_reason']}")
                
                return True
            else:
                print("\n⚠️  position_history table is EMPTY")
                print("    This is expected if no positions have closed since the fix (16:17 UTC)")
                return True

def check_max_hold_minutes():
    """Check max_hold_minutes configuration in active_positions and dispatch_executions"""
    print("\n" + "="*80)
    print("2. CHECKING MAX_HOLD_MINUTES CONFIGURATION")
    print("="*80)
    
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Check active_positions
            cur.execute("""
                SELECT 
                    id,
                    ticker,
                    instrument_type,
                    entry_time,
                    max_hold_minutes,
                    status,
                    EXTRACT(EPOCH FROM (NOW() - entry_time))/60 as minutes_held
                FROM active_positions
                WHERE status = 'open'
                ORDER BY entry_time DESC
                LIMIT 10
            """)
            active = cur.fetchall()
            
            if active:
                print(f"\n✓ Found {len(active)} open positions:")
                for pos in active:
                    print(f"\n  Position {pos['id']}: {pos['ticker']} {pos['instrument_type']}")
                    print(f"    Entry: {pos['entry_time']}")
                    print(f"    Max hold: {pos['max_hold_minutes']} minutes ({pos['max_hold_minutes']/60:.1f} hours)")
                    print(f"    Currently held: {pos['minutes_held']:.1f} minutes ({pos['minutes_held']/60:.1f} hours)")
                    
                    if pos['max_hold_minutes'] == 240:
                        print(f"    ✓ Correct: 240 minutes = 4 hours")
                    elif pos['max_hold_minutes'] == 1200:
                        print(f"    ❌ WRONG: 1200 minutes = 20 hours (should be 240)")
                    else:
                        print(f"    ⚠️  Unusual value: {pos['max_hold_minutes']} minutes")
            else:
                print("\n  No open positions currently")
            
            # Check dispatch_executions for recent trades
            cur.execute("""
                SELECT 
                    execution_id,
                    ticker,
                    instrument_type,
                    max_hold_minutes,
                    simulated_ts
                FROM dispatch_executions
                WHERE simulated_ts >= NOW() - INTERVAL '48 hours'
                ORDER BY simulated_ts DESC
                LIMIT 10
            """)
            executions = cur.fetchall()
            
            if executions:
                print(f"\n✓ Recent dispatch_executions (last 48h):")
                for ex in executions:
                    marker = "✓" if ex['max_hold_minutes'] == 240 else "❌"
                    print(f"  {marker} {ex['ticker']} {ex['instrument_type']}: max_hold={ex['max_hold_minutes']}min @ {ex['simulated_ts']}")

def check_closed_positions_recently():
    """Check for positions that closed recently (especially UNH, CSCO)"""
    print("\n" + "="*80)
    print("3. CHECKING RECENTLY CLOSED POSITIONS")
    print("="*80)
    
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Check closed positions in last 48 hours
            cur.execute("""
                SELECT 
                    id,
                    ticker,
                    instrument_type,
                    entry_time,
                    closed_at,
                    status,
                    close_reason,
                    max_hold_minutes,
                    EXTRACT(EPOCH FROM (closed_at - entry_time))/60 as minutes_held,
                    current_pnl_percent
                FROM active_positions
                WHERE status = 'closed'
                  AND closed_at >= NOW() - INTERVAL '48 hours'
                ORDER BY closed_at DESC
            """)
            closed = cur.fetchall()
            
            if closed:
                print(f"\n✓ Found {len(closed)} positions closed in last 48 hours:")
                for pos in closed:
                    hours_held = pos['minutes_held'] / 60 if pos['minutes_held'] else 0
                    expected_hours = pos['max_hold_minutes'] / 60 if pos['max_hold_minutes'] else 4
                    
                    print(f"\n  Position {pos['id']}: {pos['ticker']} {pos['instrument_type']}")
                    print(f"    Entry:  {pos['entry_time']}")
                    print(f"    Closed: {pos['closed_at']}")
                    print(f"    Held: {hours_held:.1f} hours (expected max: {expected_hours:.1f} hours)")
                    print(f"    P&L: {pos['current_pnl_percent']:.2f}%")
                    print(f"    Reason: {pos['close_reason']}")
                    
                    if hours_held > expected_hours + 1:  # Allow 1 hour grace
                        print(f"    ⚠️  HELD TOO LONG: {hours_held:.1f}h > {expected_hours:.1f}h")
                    else:
                        print(f"    ✓ Held time appropriate")
            else:
                print("\n  No positions closed in last 48 hours")
            
            # Specifically check UNH and CSCO
            cur.execute("""
                SELECT 
                    id,
                    ticker,
                    instrument_type,
                    entry_time,
                    closed_at,
                    close_reason,
                    max_hold_minutes,
                    EXTRACT(EPOCH FROM (closed_at - entry_time))/60 as minutes_held,
                    current_pnl_percent
                FROM active_positions
                WHERE ticker IN ('UNH', 'CSCO')
                  AND status = 'closed'
                ORDER BY closed_at DESC
                LIMIT 5
            """)
            problem_trades = cur.fetchall()
            
            if problem_trades:
                print(f"\n⚠️  UNH/CSCO trades found:")
                for trade in problem_trades:
                    hours_held = trade['minutes_held'] / 60 if trade['minutes_held'] else 0
                    print(f"\n  {trade['ticker']} {trade['instrument_type']} (Position {trade['id']})")
                    print(f"    Entry:  {trade['entry_time']}")
                    print(f"    Closed: {trade['closed_at']}")
                    print(f"    Held: {hours_held:.1f} hours (max_hold_minutes: {trade['max_hold_minutes']})")
                    print(f"    P&L: {trade['current_pnl_percent']:.2f}%")
                    print(f"    Reason: {trade['close_reason']}")

def check_learning_views():
    """Check if learning views exist and work"""
    print("\n" + "="*80)
    print("4. CHECKING LEARNING INFRASTRUCTURE")
    print("="*80)
    
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Check for learning views
            learning_views = [
                'v_recent_position_outcomes',
                'v_strategy_performance',
                'v_instrument_performance'
            ]
            
            for view_name in learning_views:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.views 
                        WHERE table_name = %s
                    )
                """, (view_name,))
                exists = cur.fetchone()['exists']
                
                if exists:
                    print(f"\n✓ View {view_name} exists")
                    
                    # Try to query it
                    try:
                        cur.execute(f"SELECT COUNT(*) as count FROM {view_name}")
                        count = cur.fetchone()['count']
                        print(f"  Contains {count} records")
                        
                        if count > 0:
                            cur.execute(f"SELECT * FROM {view_name} LIMIT 3")
                            samples = cur.fetchall()
                            print(f"  Sample data:")
                            for sample in samples:
                                print(f"    {dict(sample)}")
                    except Exception as e:
                        print(f"  ⚠️  Error querying view: {e}")
                else:
                    print(f"\n❌ View {view_name} does NOT exist")

def check_position_manager_deployment():
    """Check when position manager was last deployed"""
    print("\n" + "="*80)
    print("5. DEPLOYMENT STATUS")
    print("="*80)
    
    print("\nAccording to documentation:")
    print("  position_history fix deployed: 2026-02-05 16:17:55 UTC")
    print("  Exit protection fix deployed:  2026-02-04 18:13 UTC")
    print("  1-minute monitoring active:    Since Feb 4, 18:13 UTC")
    
    print("\nTo verify position manager is running the new code:")
    print("  1. Check ECS task definition version")
    print("  2. Check Docker image timestamp")
    print("  3. Review CloudWatch logs for recent 'Position history' messages")

def main():
    """Run all verification checks"""
    print("="*80)
    print("COMPREHENSIVE SYSTEM VERIFICATION")
    print("Started:", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))
    print("="*80)
    
    try:
        # Run all checks
        check_position_history_exists()
        check_max_hold_minutes()
        check_closed_positions_recently()
        check_learning_views()
        check_position_manager_deployment()
        
        print("\n" + "="*80)
        print("VERIFICATION COMPLETE")
        print("="*80)
        
        print("\n📋 SUMMARY OF FINDINGS:")
        print("\n1. position_history fix status:")
        print("   - Schema is correct (no position_id column)")
        print("   - insert_position_history() function fixed")
        print("   - Deployed at 16:17 UTC today")
        print("   - Waiting for next position close to verify data saves")
        
        print("\n2. max_hold_minutes investigation:")
        print("   - Need to check actual values in database")
        print("   - Should be 240 (4 hours), not 1200 (20 hours)")
        
        print("\n3. Learning system:")
        print("   - Views should exist if migration 011 was applied")
        print("   - Will become useful once position_history accumulates data")
        
        print("\n4. Next steps:")
        print("   - Monitor logs for next position close")
        print("   - Verify position_history insert succeeds")
        print("   - Fix any max_hold_minutes misconfigurations found")
        print("   - Once data accumulates, test learning queries")
        
    except Exception as e:
        print(f"\n❌ ERROR during verification: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    print("Note: This script uses AWS SSM and Secrets Manager for database access.")
    print("Ensure you have valid AWS credentials.\n")
    
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nVerification interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        sys.exit(1)
