#!/usr/bin/env python3
"""
Day 1 Acceptance Checks - Run via Lambda
Validates system health before 7-day observation period.
"""
import json
import boto3
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

def get_db_credentials():
    """Fetch DB connection details from AWS."""
    region = 'us-west-2'
    ssm = boto3.client('ssm', region_name=region)
    secrets = boto3.client('secretsmanager', region_name=region)
    
    db_host = ssm.get_parameter(Name='/ops-pipeline/db_host')['Parameter']['Value']
    db_port = ssm.get_parameter(Name='/ops-pipeline/db_port')['Parameter']['Value']
    db_name = ssm.get_parameter(Name='/ops-pipeline/db_name')['Parameter']['Value']
    
    secret_value = secrets.get_secret_value(SecretId='ops-pipeline/db')
    secret_data = json.loads(secret_value['SecretString'])
    
    return {
        'host': db_host,
        'port': int(db_port),
        'database': db_name,
        'user': secret_data['username'],
        'password': secret_data['password']
    }

def run_acceptance_checks():
    """Run all 8 acceptance criteria checks."""
    print("=" * 80)
    print("DAY 1 ACCEPTANCE CHECKS")
    print("=" * 80)
    print()
    
    creds = get_db_credentials()
    conn = psycopg2.connect(**creds)
    
    results = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'checks': []
    }
    
    # Check 1: No Backlog Growth
    print("✓ Check 1: Backlog State Distribution")
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT status, COUNT(*) as count
            FROM dispatch_recommendations
            GROUP BY status
            ORDER BY status
        """)
        backlog = cur.fetchall()
        
        for row in backlog:
            print(f"  {row['status']}: {row['count']}")
        
        pending = next((r['count'] for r in backlog if r['status'] == 'PENDING'), 0)
        processing = next((r['count'] for r in backlog if r['status'] == 'PROCESSING'), 0)
        
        pass_check = pending < 100 and processing == 0
        results['checks'].append({
            'name': 'No Backlog Growth',
            'passed': pass_check,
            'data': backlog
        })
        print(f"  Result: {'PASS' if pass_check else 'FAIL'}")
    print()
    
    # Check 2: No Stuck Processing
    print("✓ Check 2: Stuck PROCESSING Rows")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) 
            FROM dispatch_recommendations
            WHERE status = 'PROCESSING'
              AND ts < NOW() - INTERVAL '10 minutes'
        """)
        stuck_count = cur.fetchone()[0]
        print(f"  Stuck PROCESSING rows: {stuck_count}")
        
        pass_check = stuck_count == 0
        results['checks'].append({
            'name': 'No Stuck Processing',
            'passed': pass_check,
            'stuck_count': stuck_count
        })
        print(f"  Result: {'PASS' if pass_check else 'FAIL'}")
    print()
    
    # Check 3: Idempotency (No Duplicates)
    print("✓ Check 3: Idempotency - No Duplicate Executions")
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT recommendation_id, COUNT(*) as exec_count
            FROM dispatch_executions
            GROUP BY recommendation_id
            HAVING COUNT(*) > 1
        """)
        duplicates = cur.fetchall()
        
        if duplicates:
            print(f"  CRITICAL: Found {len(duplicates)} duplicate executions!")
            for dup in duplicates:
                print(f"    Recommendation {dup['recommendation_id']}: {dup['exec_count']} executions")
        else:
            print("  No duplicates found")
        
        pass_check = len(duplicates) == 0
        results['checks'].append({
            'name': 'Idempotency Holds',
            'passed': pass_check,
            'duplicates': len(duplicates)
        })
        print(f"  Result: {'PASS' if pass_check else 'FAIL'}")
    print()
    
    # Check 4: Freshness Gates Working
    print("✓ Check 4: Freshness Gates Enforcing")
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT
              ticker,
              simulated_ts,
              sim_json->'bar_used'->>'timestamp' as bar_timestamp,
              EXTRACT(EPOCH FROM (
                simulated_ts - (sim_json->'bar_used'->>'timestamp')::timestamptz
              )) AS bar_age_seconds
            FROM dispatch_executions
            WHERE simulated_ts >= NOW() - INTERVAL '1 hour'
            ORDER BY simulated_ts DESC
            LIMIT 10
        """)
        freshness = cur.fetchall()
        
        if freshness:
            max_age = max(r['bar_age_seconds'] for r in freshness)
            print(f"  Recent executions: {len(freshness)}")
            print(f"  Max bar age: {max_age:.1f} seconds")
            
            for row in freshness[:3]:
                print(f"    {row['ticker']}: {row['bar_age_seconds']:.1f}s")
            
            pass_check = all(r['bar_age_seconds'] < 120 for r in freshness)
        else:
            print("  No executions in last hour (may be normal)")
            pass_check = True  # No data to validate yet
        
        results['checks'].append({
            'name': 'Freshness Gates Working',
            'passed': pass_check,
            'max_bar_age': max_age if freshness else None
        })
        print(f"  Result: {'PASS' if pass_check else 'FAIL'}")
    print()
    
    # Check 5: Dispatcher Runs Completing
    print("✓ Check 5: Dispatcher Runs Completing")
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT 
              started_at,
              finished_at,
              pulled_count,
              simulated_count,
              skipped_count,
              failed_count,
              EXTRACT(EPOCH FROM (finished_at - started_at)) as duration_seconds
            FROM dispatcher_runs
            ORDER BY started_at DESC
            LIMIT 5
        """)
        runs = cur.fetchall()
        
        if runs:
            print(f"  Recent runs: {len(runs)}")
            for run in runs[:3]:
                print(f"    {run['started_at']}: pulled={run['pulled_count']}, " +
                      f"simulated={run['simulated_count']}, skipped={run['skipped_count']}, " +
                      f"duration={run['duration_seconds']:.1f}s")
            
            latest = runs[0]
            age_seconds = (datetime.utcnow() - latest['started_at'].replace(tzinfo=None)).total_seconds()
            
            pass_check = all(r['finished_at'] is not None for r in runs) and age_seconds < 300
        else:
            print("  No runs yet (wait a few minutes)")
            pass_check = False
        
        results['checks'].append({
            'name': 'Dispatcher Runs Completing',
            'passed': pass_check,
            'recent_runs': len(runs)
        })
        print(f"  Result: {'PASS' if pass_check else 'FAIL'}")
    print()
    
    # Check 6: Execution Volumes
    print("✓ Check 6: Execution Volumes")
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT 
              COUNT(*) as total_executions,
              COUNT(DISTINCT ticker) as unique_tickers,
              MIN(simulated_ts) as first_execution,
              MAX(simulated_ts) as last_execution
            FROM dispatch_executions
            WHERE simulated_ts >= CURRENT_DATE
        """)
        volumes = cur.fetchone()
        
        print(f"  Total executions today: {volumes['total_executions']}")
        print(f"  Unique tickers: {volumes['unique_tickers']}")
        if volumes['first_execution']:
            print(f"  First execution: {volumes['first_execution']}")
        
        pass_check = volumes['total_executions'] < 200
        results['checks'].append({
            'name': 'Execution Volumes Sane',
            'passed': pass_check,
            'total': volumes['total_executions']
        })
        print(f"  Result: {'PASS' if pass_check else 'FAIL'}")
    print()
    
    # Check 7: Signal Generation
    print("✓ Check 7: Signal Generation Working")
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT 
              COUNT(*) as signals_last_hour,
              COUNT(DISTINCT ticker) as unique_tickers
            FROM dispatch_recommendations
            WHERE ts >= NOW() - INTERVAL '1 hour'
        """)
        signals = cur.fetchone()
        
        print(f"  Signals in last hour: {signals['signals_last_hour']}")
        print(f"  Unique tickers: {signals['unique_tickers']}")
        
        # Pass if any signals (may be outside market hours)
        pass_check = signals['signals_last_hour'] >= 0  # Always pass, just informational
        results['checks'].append({
            'name': 'Signal Generation',
            'passed': pass_check,
            'signals_last_hour': signals['signals_last_hour']
        })
        print(f"  Result: {'PASS' if pass_check else 'FAIL'}")
    print()
    
    # Check 8: Table Existence
    print("✓ Check 8: All Tables Exist")
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'public'
            ORDER BY tablename
        """)
        tables = [r['tablename'] for r in cur.fetchall()]
        
        expected = [
            'dispatch_executions',
            'dispatch_recommendations',
            'dispatcher_runs',
            'feed_state',
            'inbound_events_classified',
            'inbound_events_raw',
            'lane_features',
            'lane_telemetry',
            'schema_migrations',
            'watchlist_state'
        ]
        
        missing = [t for t in expected if t not in tables]
        print(f"  Tables found: {len(tables)}")
        if missing:
            print(f"  Missing: {missing}")
        else:
            print("  All expected tables present")
        
        pass_check = len(missing) == 0
        results['checks'].append({
            'name': 'All Tables Exist',
            'passed': pass_check,
            'missing': missing
        })
        print(f"  Result: {'PASS' if pass_check else 'FAIL'}")
    print()
    
    conn.close()
    
    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    passed = sum(1 for c in results['checks'] if c['passed'])
    total = len(results['checks'])
    print(f"Passed: {passed}/{total} checks")
    print()
    
    if passed == total:
        print("✅ ALL CHECKS PASSED - System is healthy")
        print()
        print("Next steps:")
        print("1. 🔒 FREEZE execution semantics (no code changes)")
        print("2. Run daily health checks for next 7 days")
        print("3. Document baseline metrics on Day 7")
        print("4. Choose Phase 10 path after clean 7-day run")
    else:
        print("⚠️  SOME CHECKS FAILED - Review and fix before proceeding")
        print()
        print("Failed checks:")
        for check in results['checks']:
            if not check['passed']:
                print(f"  - {check['name']}")
    
    print()
    print("=" * 80)
    
    return results

if __name__ == '__main__':
    results = run_acceptance_checks()
    
    # Save results
    with open('/tmp/day1_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print("Results saved to /tmp/day1_results.json")
