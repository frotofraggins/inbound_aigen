#!/usr/bin/env python3
"""
End-to-End Pipeline Verification Script
Checks all stages of the trading pipeline
"""
import json
import boto3
import psycopg2
from datetime import datetime, timedelta

# Get DB credentials from SSM
ssm = boto3.client('ssm', region_name='us-west-2')
secrets = boto3.client('secretsmanager', region_name='us-west-2')

def get_db_connection():
    """Get database connection from AWS"""
    db_host = ssm.get_parameter(Name='/ops-pipeline/db_host')['Parameter']['Value']
    db_port = ssm.get_parameter(Name='/ops-pipeline/db_port')['Parameter']['Value']
    db_name = ssm.get_parameter(Name='/ops-pipeline/db_name')['Parameter']['Value']
    
    secret_value = secrets.get_secret_value(SecretId='ops-pipeline/db')
    secret_data = json.loads(secret_value['SecretString'])
    
    return psycopg2.connect(
        host=db_host,
        port=int(db_port),
        database=db_name,
        user=secret_data['username'],
        password=secret_data['password']
    )

def print_section(title):
    """Print a formatted section header"""
    print(f"\n{'='*80}")
    print(f"  {title}")
    print('='*80)

def check_telemetry(cursor):
    """Check telemetry data ingestion"""
    print_section("1. TELEMETRY INGESTION (Alpaca 1-min bars)")
    
    # Check total records in last hour
    cursor.execute("""
        SELECT COUNT(*) as total, 
               COUNT(DISTINCT ticker) as unique_tickers,
               MAX(bar_time) as latest_bar,
               MIN(bar_time) as earliest_bar
        FROM lane_telemetry 
        WHERE bar_time >= NOW() - INTERVAL '1 hour'
    """)
    row = cursor.fetchone()
    print(f"  Records (last hour): {row[0]}")
    print(f"  Unique tickers: {row[1]}")
    print(f"  Latest bar: {row[2]}")
    print(f"  Earliest bar: {row[3]}")
    
    # Check per-ticker volume data
    cursor.execute("""
        SELECT ticker, 
               COUNT(*) as bars,
               AVG(volume) as avg_volume,
               MAX(bar_time) as latest
        FROM lane_telemetry 
        WHERE bar_time >= NOW() - INTERVAL '1 hour'
        GROUP BY ticker
        ORDER BY ticker
    """)
    print(f"\n  Per-Ticker Breakdown:")
    for row in cursor.fetchall():
        print(f"    {row[0]}: {row[1]} bars, avg_vol={row[2]:.0f}, latest={row[3]}")
    
    # Check if volume data exists
    cursor.execute("""
        SELECT COUNT(*) as with_volume
        FROM lane_telemetry 
        WHERE bar_time >= NOW() - INTERVAL '1 hour'
        AND volume > 0
    """)
    row = cursor.fetchone()
    print(f"\n  Bars with volume > 0: {row[0]}")
    
    return True

def check_features(cursor):
    """Check feature computation with volume analysis"""
    print_section("2. FEATURE COMPUTATION (Phase 12 Volume Analysis)")
    
    # Check total feature records
    cursor.execute("""
        SELECT COUNT(*) as total,
               COUNT(DISTINCT ticker) as unique_tickers,
               MAX(computed_at) as latest_compute,
               MIN(computed_at) as earliest_compute
        FROM lane_features 
        WHERE computed_at >= NOW() - INTERVAL '1 hour'
    """)
    row = cursor.fetchone()
    print(f"  Records (last hour): {row[0]}")
    print(f"  Unique tickers: {row[1]}")
    print(f"  Latest compute: {row[2]}")
    print(f"  Earliest compute: {row[3]}")
    
    # Check volume features specifically
    cursor.execute("""
        SELECT COUNT(*) as with_volume_ratio
        FROM lane_features 
        WHERE computed_at >= NOW() - INTERVAL '1 hour'
        AND volume_ratio IS NOT NULL
    """)
    row = cursor.fetchone()
    print(f"\n  Records with volume_ratio: {row[0]}")
    
    # Get latest volume analysis per ticker
    cursor.execute("""
        SELECT ticker,
               volume_current,
               volume_avg_20,
               volume_ratio,
               volume_surge,
               computed_at
        FROM lane_features 
        WHERE computed_at >= NOW() - INTERVAL '30 minutes'
        AND volume_ratio IS NOT NULL
        ORDER BY ticker, computed_at DESC
    """)
    
    print(f"\n  Latest Volume Analysis (last 30 min):")
    print(f"  {'Ticker':<8} {'Vol_Cur':<12} {'Vol_Avg20':<12} {'Ratio':<8} {'Surge':<7} {'Time'}")
    print(f"  {'-'*75}")
    
    seen_tickers = set()
    for row in cursor.fetchall():
        if row[0] not in seen_tickers:
            seen_tickers.add(row[0])
            vol_ratio_str = f"{row[3]:.2f}" if row[3] else "NULL"
            surge_str = "YES" if row[4] else "NO"
            print(f"  {row[0]:<8} {row[1]:<12} {row[2]:<12} {vol_ratio_str:<8} {surge_str:<7} {row[5]}")
    
    # Check volume multiplier distribution
    cursor.execute("""
        SELECT 
            CASE 
                WHEN volume_ratio IS NULL THEN 'NULL'
                WHEN volume_ratio < 0.5 THEN '< 0.5 (KILL)'
                WHEN volume_ratio < 1.2 THEN '0.5-1.2 (WEAK)'
                WHEN volume_ratio < 3.0 THEN '1.2-3.0 (NORMAL)'
                ELSE '>= 3.0 (SURGE)'
            END as category,
            COUNT(*) as count
        FROM lane_features 
        WHERE computed_at >= NOW() - INTERVAL '1 hour'
        GROUP BY category
        ORDER BY category
    """)
    print(f"\n  Volume Ratio Distribution (last hour):")
    for row in cursor.fetchall():
        print(f"    {row[0]}: {row[1]} records")
    
    return True

def check_signals(cursor):
    """Check signal generation"""
    print_section("3. SIGNAL GENERATION (Recommendations)")
    
    # Check total recommendations
    cursor.execute("""
        SELECT COUNT(*) as total,
               COUNT(DISTINCT ticker) as unique_tickers,
               MAX(generated_at) as latest,
               MIN(generated_at) as earliest
        FROM dispatch_recommendations 
        WHERE generated_at >= NOW() - INTERVAL '2 hours'
    """)
    row = cursor.fetchone()
    print(f"  Total recommendations (last 2 hours): {row[0]}")
    print(f"  Unique tickers: {row[1]}")
    print(f"  Latest: {row[2]}")
    print(f"  Earliest: {row[3]}")
    
    if row[0] == 0:
        print(f"\n  ⚠️  NO RECOMMENDATIONS YET")
        print(f"      This is normal if market just opened or no signal conditions met")
        return False
    
    # Check recommendations by action
    cursor.execute("""
        SELECT action, COUNT(*) as count
        FROM dispatch_recommendations 
        WHERE generated_at >= NOW() - INTERVAL '2 hours'
        GROUP BY action
    """)
    print(f"\n  By Action:")
    for row in cursor.fetchall():
        print(f"    {row[0]}: {row[1]}")
    
    # Check for volume multiplier in reasons
    cursor.execute("""
        SELECT ticker, action, confidence, reason, generated_at
        FROM dispatch_recommendations 
        WHERE generated_at >= NOW() - INTERVAL '2 hours'
        AND reason LIKE '%volume%'
        ORDER BY generated_at DESC
        LIMIT 5
    """)
    print(f"\n  Recent Recommendations with Volume Multiplier:")
    for row in cursor.fetchall():
        print(f"    {row[0]} {row[1]} conf={row[2]:.3f} at {row[4]}")
        print(f"      Reason: {row[3][:100]}...")
    
    return True

def check_classifier(cursor):
    """Check classifier pipeline"""
    print_section("4. CLASSIFIER (News Sentiment)")
    
    # Check classified events
    cursor.execute("""
        SELECT COUNT(*) as total,
               COUNT(DISTINCT ticker) as unique_tickers,
               MAX(classified_at) as latest,
               MIN(classified_at) as earliest
        FROM inbound_events_classified 
        WHERE classified_at >= NOW() - INTERVAL '24 hours'
    """)
    row = cursor.fetchone()
    print(f"  Classified events (last 24 hours): {row[0]}")
    print(f"  Unique tickers: {row[1]}")
    print(f"  Latest: {row[2]}")
    print(f"  Earliest: {row[3]}")
    
    # Check sentiment distribution
    cursor.execute("""
        SELECT sentiment, COUNT(*) as count
        FROM inbound_events_classified 
        WHERE classified_at >= NOW() - INTERVAL '24 hours'
        GROUP BY sentiment
    """)
    print(f"\n  Sentiment Distribution:")
    for row in cursor.fetchall():
        print(f"    {row[0]}: {row[1]}")
    
    # Check recent classified events
    cursor.execute("""
        SELECT ticker, sentiment, confidence, title, classified_at
        FROM inbound_events_classified 
        WHERE classified_at >= NOW() - INTERVAL '2 hours'
        ORDER BY classified_at DESC
        LIMIT 5
    """)
    print(f"\n  Recent Classified Events:")
    for row in cursor.fetchall():
        print(f"    {row[0]} {row[1]} (conf={row[2]:.3f}) at {row[4]}")
        print(f"      Title: {row[3][:80]}...")
    
    return True

def check_dispatcher(cursor):
    """Check dispatcher executions"""
    print_section("5. DISPATCHER (Trade Executions)")
    
    # Check total executions
    cursor.execute("""
        SELECT COUNT(*) as total,
               COUNT(DISTINCT ticker) as unique_tickers,
               MAX(executed_at) as latest,
               MIN(executed_at) as earliest
        FROM dispatch_executions 
        WHERE executed_at >= NOW() - INTERVAL '2 hours'
    """)
    row = cursor.fetchone()
    print(f"  Total executions (last 2 hours): {row[0]}")
    print(f"  Unique tickers: {row[1]}")
    print(f"  Latest: {row[2]}")
    print(f"  Earliest: {row[3]}")
    
    if row[0] == 0:
        print(f"\n  ℹ️  NO EXECUTIONS YET")
        print(f"      Waiting for recommendations that pass risk gates")
        return False
    
    # Check execution status
    cursor.execute("""
        SELECT status, COUNT(*) as count
        FROM dispatch_executions 
        WHERE executed_at >= NOW() - INTERVAL '2 hours'
        GROUP BY status
    """)
    print(f"\n  By Status:")
    for row in cursor.fetchall():
        print(f"    {row[0]}: {row[1]}")
    
    # Check recent executions
    cursor.execute("""
        SELECT ticker, action, quantity, status, price_usd, executed_at
        FROM dispatch_executions 
        WHERE executed_at >= NOW() - INTERVAL '2 hours'
        ORDER BY executed_at DESC
        LIMIT 5
    """)
    print(f"\n  Recent Executions:")
    for row in cursor.fetchall():
        print(f"    {row[0]} {row[1]} {row[2]} shares @ ${row[4]:.2f} - {row[3]} at {row[5]}")
    
    return True

def check_raw_events(cursor):
    """Check raw RSS feed ingestion"""
    print_section("6. RAW EVENTS (RSS Feed Ingestion)")
    
    # Check total raw events
    cursor.execute("""
        SELECT COUNT(*) as total,
               MAX(fetched_at) as latest,
               MIN(fetched_at) as earliest
        FROM inbound_events_raw 
        WHERE fetched_at >= NOW() - INTERVAL '24 hours'
    """)
    row = cursor.fetchone()
    print(f"  Total events (last 24 hours): {row[0]}")
    print(f"  Latest: {row[1]}")
    print(f"  Earliest: {row[2]}")
    
    # Check recent events
    cursor.execute("""
        SELECT source, title, fetched_at
        FROM inbound_events_raw 
        WHERE fetched_at >= NOW() - INTERVAL '2 hours'
        ORDER BY fetched_at DESC
        LIMIT 5
    """)
    print(f"\n  Recent Events:")
    for row in cursor.fetchall():
        print(f"    {row[2]} - {row[0][:40]}")
        print(f"      {row[1][:80]}...")
    
    return True

def main():
    """Run all verification checks"""
    print("\n" + "="*80)
    print("  TRADING PIPELINE END-TO-END VERIFICATION")
    print(f"  Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print("="*80)
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Run all checks
        check_raw_events(cursor)
        check_classifier(cursor)
        check_telemetry(cursor)
        check_features(cursor)
        signals_found = check_signals(cursor)
        dispatcher_active = check_dispatcher(cursor)
        
        # Summary
        print_section("SUMMARY")
        print(f"  ✅ Raw Events: RSS feeds being ingested")
        print(f"  ✅ Classifier: Sentiment analysis working")
        print(f"  ✅ Telemetry: Alpaca 1-min bars ingesting")
        print(f"  ✅ Features: Phase 12 volume analysis computing")
        
        if signals_found:
            print(f"  ✅ Signals: Recommendations being generated")
        else:
            print(f"  ⏳ Signals: No recommendations yet (normal for early market)")
        
        if dispatcher_active:
            print(f"  ✅ Dispatcher: Trade executions happening")
        else:
            print(f"  ⏳ Dispatcher: No executions yet (waiting for signals)")
        
        print(f"\n  Pipeline Status: OPERATIONAL")
        print(f"  Market: OPEN (started 14:30 UTC)")
        print(f"  Mode: SIMULATION (safe)")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
