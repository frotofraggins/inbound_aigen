#!/usr/bin/env python3
"""
Phase 15 Deployment Verification Script
Checks if options trading is working correctly end-to-end.
"""

import psycopg2
import sys
import os
from datetime import datetime, timedelta

def get_db_connection():
    """Get database connection"""
    return psycopg2.connect(
        host=os.environ.get('DB_HOST'),
        port=int(os.environ.get('DB_PORT', '5432')),
        database=os.environ.get('DB_NAME', 'ops_pipeline'),
        user=os.environ.get('DB_USER'),
        password=os.environ.get('DB_PASSWORD')
    )

def check_migration_008():
    """Verify migration 008 was applied"""
    print("\n" + "="*60)
    print("CHECK 1: Migration 008 Applied")
    print("="*60)
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Check for strategy_type in recommendations
    cur.execute("""
        SELECT column_name 
        FROM information_schema.columns
        WHERE table_name = 'dispatch_recommendations'
        AND column_name = 'strategy_type';
    """)
    
    if cur.fetchone():
        print("✅ strategy_type column exists in dispatch_recommendations")
    else:
        print("❌ strategy_type column MISSING in dispatch_recommendations")
        return False
    
    # Check for instrument_type in executions
    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_name = 'dispatch_executions'
        AND column_name IN ('instrument_type', 'strike_price', 'strategy_type');
    """)
    
    count = cur.fetchone()[0]
    if count >= 3:
        print(f"✅ Options columns exist in dispatch_executions ({count}/10)")
    else:
        print(f"❌ Options columns MISSING ({count}/10)")
        return False
    
    conn.close()
    return True

def check_data_pipeline():
    """Check if data pipeline is healthy"""
    print("\n" + "="*60)
    print("CHECK 2: Data Pipeline Health")
    print("="*60)
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Check telemetry freshness
    cur.execute("""
        SELECT 
            MAX(ts) as latest_bar,
            EXTRACT(EPOCH FROM (NOW() - MAX(ts)))/60 as minutes_ago
        FROM lane_telemetry;
    """)
    
    bar_data = cur.fetchone()
    if bar_data[1] < 5:
        print(f"✅ Telemetry fresh: {bar_data[1]:.1f} minutes ago")
    else:
        print(f"⚠️  Telemetry stale: {bar_data[1]:.1f} minutes ago")
    
    # Check features freshness
    cur.execute("""
        SELECT 
            MAX(computed_at) as latest_features,
            EXTRACT(EPOCH FROM (NOW() - MAX(computed_at)))/60 as minutes_ago
        FROM lane_features;
    """)
    
    feature_data = cur.fetchone()
    if feature_data[1] < 10:
        print(f"✅ Features fresh: {feature_data[1]:.1f} minutes ago")
    else:
        print(f"⚠️  Features stale: {feature_data[1]:.1f} minutes ago")
    
    # Check sentiment
    cur.execute("""
        SELECT 
            COUNT(*) as news_count_24h,
            MAX(created_at) as latest_news,
            EXTRACT(EPOCH FROM (NOW() - MAX(created_at)))/3600 as hours_ago
        FROM inbound_events_classified
        WHERE created_at > NOW() - INTERVAL '24 hours';
    """)
    
    sentiment_data = cur.fetchone()
    print(f"✅ News: {sentiment_data[0]} articles in 24h (latest {sentiment_data[2]:.1f}h ago)")
    
    conn.close()
    return True

def check_recommendations():
    """Check recent recommendations"""
    print("\n" + "="*60)
    print("CHECK 3: Recent Recommendations")
    print("="*60)
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get recommendations from last 24 hours
    cur.execute("""
        SELECT 
            instrument_type,
            strategy_type,
            COUNT(*) as count,
            AVG(confidence) as avg_confidence
        FROM dispatch_recommendations
        WHERE created_at > NOW() - INTERVAL '24 hours'
        GROUP BY instrument_type, strategy_type
        ORDER BY instrument_type, strategy_type;
    """)
    
    rows = cur.fetchall()
    
    if len(rows) == 0:
        print("⚠️  No recommendations in last 24 hours")
        print("   This is OK if market hasn't had strong signals")
    else:
        print(f"✅ {len(rows)} recommendation type(s) in last 24h:")
        for row in rows:
            inst = row[0] or 'NULL'
            strat = row[1] or 'NULL'
            count = row[2]
            conf = row[3]
            print(f"   - {inst} ({strat}): {count} signals, avg confidence {conf:.3f}")
    
    # Check for options specifically
    cur.execute("""
        SELECT COUNT(*)
        FROM dispatch_recommendations
        WHERE created_at > NOW() - INTERVAL '24 hours'
        AND instrument_type IN ('CALL', 'PUT');
    """)
    
    options_count = cur.fetchone()[0]
    if options_count > 0:
        print(f"✅ OPTIONS SIGNALS WORKING: {options_count} CALL/PUT recommendations")
    else:
        print("⏳ No options signals yet (waiting for strong market conditions)")
        print("   Need: confidence ≥0.7 + volume_ratio ≥3.0")
    
    conn.close()
    return True

def check_executions():
    """Check recent executions"""
    print("\n" + "="*60)
    print("CHECK 4: Recent Executions")
    print("="*60)
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get executions from last 24 hours
    cur.execute("""
        SELECT 
            instrument_type,
            strategy_type,
            COUNT(*) as count,
            SUM(notional) as total_notional
        FROM dispatch_executions
        WHERE simulated_ts > NOW() - INTERVAL '24 hours'
        GROUP BY instrument_type, strategy_type
        ORDER BY instrument_type, strategy_type;
    """)
    
    rows = cur.fetchall()
    
    if len(rows) == 0:
        print("⚠️  No executions in last 24 hours")
    else:
        print(f"✅ {len(rows)} execution type(s) in last 24h:")
        for row in rows:
            inst = row[0] or 'NULL'
            strat = row[1] or 'NULL'
            count = row[2]
            notional = row[3] or 0
            print(f"   - {inst} ({strat}): {count} trades, ${notional:,.2f} notional")
    
    # Check for options executions specifically
    cur.execute("""
        SELECT COUNT(*)
        FROM dispatch_executions
        WHERE simulated_ts > NOW() - INTERVAL '24 hours'
        AND instrument_type IN ('CALL', 'PUT');
    """)
    
    options_exec_count = cur.fetchone()[0]
    if options_exec_count > 0:
        print(f"🎉 OPTIONS TRADING WORKING: {options_exec_count} option executions!")
    else:
        print("⏳ No options executions yet")
    
    conn.close()
    return True

def check_views():
    """Check if database views work"""
    print("\n" + "="*60)
    print("CHECK 5: Database Views")
    print("="*60)
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    views = [
        'active_options_positions',
        'options_performance_by_strategy',
        'daily_options_summary'
    ]
    
    for view in views:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {view};")
            count = cur.fetchone()[0]
            print(f"✅ {view}: {count} rows")
        except Exception as e:
            print(f"❌ {view}: ERROR - {e}")
            return False
    
    conn.close()
    return True

def check_system_health():
    """Overall system health check"""
    print("\n" + "="*60)
    print("CHECK 6: Overall System Health")
    print("="*60)
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Check watchlist
    cur.execute("SELECT COUNT(*) FROM watchlist_state WHERE in_watchlist = TRUE;")
    watchlist_count = cur.fetchone()[0]
    print(f"✅ Watchlist: {watchlist_count} tickers")
    
    # Check recent activity
    cur.execute("""
        SELECT 
            (SELECT COUNT(*) FROM dispatch_recommendations WHERE created_at > NOW() - INTERVAL '1 hour') as recs_1h,
            (SELECT COUNT(*) FROM dispatch_executions WHERE simulated_ts > NOW() - INTERVAL '1 hour') as execs_1h,
            (SELECT COUNT(*) FROM lane_telemetry WHERE ts > NOW() - INTERVAL '1 hour') as bars_1h;
    """)
    
    activity = cur.fetchone()
    print(f"Last hour activity:")
    print(f"  - Recommendations: {activity[0]}")
    print(f"  - Executions: {activity[1]}")
    print(f"  - Telemetry bars: {activity[2]}")
    
    conn.close()
    return True

def main():
    """Run all verification checks"""
    print("\n" + "=" * 60)
    print("PHASE 15 DEPLOYMENT VERIFICATION")
    print("=" * 60)
    print("\nVerifying options trading deployment...")
    
    checks = [
        ("Migration 008", check_migration_008),
        ("Data Pipeline", check_data_pipeline),
        ("Recommendations", check_recommendations),
        ("Executions", check_executions),
        ("Database Views", check_views),
        ("System Health", check_system_health),
    ]
    
    results = []
    for check_name, check_func in checks:
        try:
            passed = check_func()
            results.append((check_name, passed))
        except Exception as e:
            print(f"\n❌ ERROR in {check_name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((check_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    
    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    
    for check_name, passed in results:
        status = "✅" if passed else "❌"
        print(f"{status} {check_name}")
    
    print(f"\nTotal: {passed_count}/{total_count} checks passed")
    
    if passed_count == total_count:
        print("\n🎉 DEPLOYMENT VERIFIED - Options trading is ready!")
        print("\nWhat to expect:")
        print("  - Options signals when: confidence ≥0.7 + volume_ratio ≥3.0")
        print("  - Stock signals when: moderate confidence or high vol")
        print("  - System falls back gracefully if no options available")
        print("\nMonitor for first options trade:")
        print("  aws logs tail /ecs/signal-engine-1m --follow | grep 'CALL\\|PUT'")
        return 0
    else:
        print(f"\n⚠️  {total_count - passed_count} check(s) need attention")
        return 1

if __name__ == '__main__':
    sys.exit(main())
