#!/usr/bin/env python3
"""
Data Quality Verification Script
Checks that pipeline is producing real, non-null data after scheduler fix
"""

import boto3
import json
from datetime import datetime, timedelta

# Database connection via Lambda
lambda_client = boto3.client('lambda', region_name='us-west-2')

def query_db(sql):
    """Execute SQL via db-query-lambda"""
    response = lambda_client.invoke(
        FunctionName='db-query-lambda',
        InvocationType='RequestResponse',
        Payload=json.dumps({'query': sql})
    )
    result = json.loads(response['Payload'].read())
    if result.get('statusCode') != 200:
        print(f"❌ Query failed: {result.get('body', 'Unknown error')}")
        return []
    return json.loads(result['body'])

print("=" * 80)
print("DATA QUALITY VERIFICATION - Post-Scheduler Fix")
print("=" * 80)
print()

# Check 1: Recent Telemetry Data
print("📊 CHECK 1: Recent Telemetry Data (Last 10 minutes)")
print("-" * 80)
telemetry_query = """
SELECT 
    ticker,
    timestamp,
    close_price,
    volume,
    high_price,
    low_price
FROM lane_telemetry 
WHERE timestamp >= NOW() - INTERVAL 10 MINUTE
ORDER BY timestamp DESC 
LIMIT 10
"""
telemetry = query_db(telemetry_query)
if telemetry:
    print(f"✅ Found {len(telemetry)} recent telemetry records")
    for row in telemetry[:5]:
        print(f"   {row['ticker']}: ${row['close_price']:.2f} vol={row['volume']:,} @ {row['timestamp']}")
        # Check for nulls or zeros
        if not row['close_price'] or row['close_price'] == 0:
            print(f"   ⚠️  WARNING: Zero/null price for {row['ticker']}")
        if not row['volume']:
            print(f"   ⚠️  WARNING: Null volume for {row['ticker']}")
else:
    print("❌ No recent telemetry data found")
print()

# Check 2: Recent Features
print("🔧 CHECK 2: Recent Features (Last 10 minutes)")
print("-" * 80)
features_query = """
SELECT 
    ticker,
    timestamp,
    rsi_14,
    macd,
    sma_20,
    volatility_10d
FROM lane_features 
WHERE timestamp >= NOW() - INTERVAL 10 MINUTE
ORDER BY timestamp DESC 
LIMIT 10
"""
features = query_db(features_query)
if features:
    print(f"✅ Found {len(features)} recent feature records")
    for row in features[:5]:
        print(f"   {row['ticker']}: RSI={row.get('rsi_14', 'NULL')} MACD={row.get('macd', 'NULL')} @ {row['timestamp']}")
        # Check for nulls
        null_count = sum(1 for k, v in row.items() if v is None and k not in ['ticker', 'timestamp'])
        if null_count > 2:
            print(f"   ⚠️  WARNING: {null_count} null features for {row['ticker']}")
else:
    print("❌ No recent feature data found")
print()

# Check 3: Recent Signals
print("🎯 CHECK 3: Recent Signals (Last 30 minutes)")
print("-" * 80)
signals_query = """
SELECT 
    sr.ticker,
    sr.created_at,
    sr.action,
    sr.confidence,
    sr.rationale
FROM signal_recommendations sr
WHERE sr.created_at >= NOW() - INTERVAL 30 MINUTE
ORDER BY sr.created_at DESC 
LIMIT 10
"""
signals = query_db(signals_query)
if signals:
    print(f"✅ Found {len(signals)} recent signals")
    for row in signals[:5]:
        print(f"   {row['ticker']}: {row['action']} conf={row['confidence']:.2f} @ {row['created_at']}")
else:
    print("⚠️  No signals in last 30 minutes (normal after hours)")
print()

# Check 4: Data Freshness by Service
print("⏰ CHECK 4: Data Freshness by Service")
print("-" * 80)

# Telemetry freshness
tel_fresh = query_db("""
    SELECT MAX(timestamp) as latest, COUNT(*) as count 
    FROM lane_telemetry 
    WHERE timestamp >= NOW() - INTERVAL 1 HOUR
""")
if tel_fresh:
    latest = tel_fresh[0]['latest']
    count = tel_fresh[0]['count']
    age_minutes = (datetime.utcnow() - datetime.fromisoformat(str(latest).replace('Z', '+00:00'))).seconds // 60
    print(f"📈 Telemetry: {count} records, latest {age_minutes}min ago")
    if age_minutes > 5:
        print(f"   ⚠️  WARNING: Data is {age_minutes} minutes old")

# Features freshness
feat_fresh = query_db("""
    SELECT MAX(timestamp) as latest, COUNT(*) as count 
    FROM lane_features 
    WHERE timestamp >= NOW() - INTERVAL 1 HOUR
""")
if feat_fresh:
    latest = feat_fresh[0]['latest']
    count = feat_fresh[0]['count']
    age_minutes = (datetime.utcnow() - datetime.fromisoformat(str(latest).replace('Z', '+00:00'))).seconds // 60
    print(f"🔧 Features: {count} records, latest {age_minutes}min ago")
    if age_minutes > 5:
        print(f"   ⚠️  WARNING: Data is {age_minutes} minutes old")

# Signals freshness
sig_fresh = query_db("""
    SELECT MAX(created_at) as latest, COUNT(*) as count 
    FROM signal_recommendations 
    WHERE created_at >= NOW() - INTERVAL 1 HOUR
""")
if sig_fresh and sig_fresh[0]['latest']:
    latest = sig_fresh[0]['latest']
    count = sig_fresh[0]['count']
    age_minutes = (datetime.utcnow() - datetime.fromisoformat(str(latest).replace('Z', '+00:00'))).seconds // 60
    print(f"🎯 Signals: {count} records, latest {age_minutes}min ago")
print()

# Check 5: Null Value Analysis
print("🔍 CHECK 5: Null Value Analysis")
print("-" * 80)
null_check = query_db("""
    SELECT 
        COUNT(*) as total_records,
        SUM(CASE WHEN close_price IS NULL OR close_price = 0 THEN 1 ELSE 0 END) as null_price,
        SUM(CASE WHEN volume IS NULL THEN 1 ELSE 0 END) as null_volume,
        SUM(CASE WHEN high_price IS NULL THEN 1 ELSE 0 END) as null_high,
        SUM(CASE WHEN low_price IS NULL THEN 1 ELSE 0 END) as null_low
    FROM lane_telemetry 
    WHERE timestamp >= NOW() - INTERVAL 1 HOUR
""")
if null_check:
    row = null_check[0]
    total = row['total_records']
    print(f"📊 Analyzed {total} telemetry records from last hour:")
    if total > 0:
        null_pct = (row['null_price'] / total * 100) if total > 0 else 0
        print(f"   Null/Zero Prices: {row['null_price']} ({null_pct:.1f}%)")
        print(f"   Null Volume: {row['null_volume']} ({row['null_volume']/total*100:.1f}%)")
        print(f"   Null High: {row['null_high']} ({row['null_high']/total*100:.1f}%)")
        print(f"   Null Low: {row['null_low']} ({row['null_low']/total*100:.1f}%)")
        
        if null_pct > 10:
            print(f"   ❌ CRITICAL: >10% null prices detected!")
        elif null_pct > 0:
            print(f"   ⚠️  WARNING: Some null prices detected")
        else:
            print(f"   ✅ No null prices - data looks good!")
    else:
        print("   ⚠️  No data in last hour (system just restarted)")
print()

# Check 6: Price Sanity Check
print("💰 CHECK 6: Price Sanity Check")
print("-" * 80)
price_sanity = query_db("""
    SELECT 
        ticker,
        MIN(close_price) as min_price,
        MAX(close_price) as max_price,
        AVG(close_price) as avg_price,
        COUNT(*) as samples
    FROM lane_telemetry 
    WHERE timestamp >= NOW() - INTERVAL 1 HOUR
    GROUP BY ticker
    HAVING COUNT(*) >= 5
    ORDER BY ticker
    LIMIT 10
""")
if price_sanity:
    print(f"✅ Price ranges for active tickers:")
    for row in price_sanity:
        ticker = row['ticker']
        min_p = row['min_price']
        max_p = row['max_price']
        avg_p = row['avg_price']
        samples = row['samples']
        range_pct = ((max_p - min_p) / avg_p * 100) if avg_p > 0 else 0
        
        print(f"   {ticker}: ${min_p:.2f}-${max_p:.2f} (avg ${avg_p:.2f}, {samples} samples)")
        
        # Sanity checks
        if min_p <= 0:
            print(f"      ❌ INVALID: Price <= 0")
        elif max_p > 10000:
            print(f"      ⚠️  Suspiciously high price")
        elif range_pct > 50:
            print(f"      ⚠️  Large price swing ({range_pct:.1f}%)")
else:
    print("⚠️  Not enough data for price analysis yet")
print()

# Summary
print("=" * 80)
print("SUMMARY")
print("=" * 80)
has_telemetry = len(telemetry) > 0 if telemetry else False
has_features = len(features) > 0 if features else False
null_issue = False
if null_check and null_check[0]['total_records'] > 0:
    null_pct = (null_check[0]['null_price'] / null_check[0]['total_records'] * 100)
    null_issue = null_pct > 5

if has_telemetry and has_features and not null_issue:
    print("✅ DATA QUALITY: GOOD")
    print("   - Real price data flowing")
    print("   - Features being computed")
    print("   - Minimal null values")
    print("   - System operational")
elif has_telemetry and null_issue:
    print("⚠️  DATA QUALITY: ACCEPTABLE BUT WITH ISSUES")
    print("   - Data is flowing but has null values")
    print("   - May need to investigate data sources")
elif not has_telemetry:
    print("⏳ DATA QUALITY: PENDING")
    print("   - System just restarted")
    print("   - Allow 5-10 minutes for data to accumulate")
    print("   - Re-run this check in a few minutes")
else:
    print("❌ DATA QUALITY: ISSUES DETECTED")
    print("   - Review warnings above")
    print("   - Check service logs for errors")

print()
print("💡 Next Steps:")
print("   1. If data pending: Wait 5 minutes and re-run")
print("   2. If null values: Check telemetry ingestor logs")
print("   3. If no features: Check feature computer logs")
print("   4. Monitor: aws logs tail /ecs/ops-pipeline/telemetry-1m --region us-west-2 --follow")
print("=" * 80)
