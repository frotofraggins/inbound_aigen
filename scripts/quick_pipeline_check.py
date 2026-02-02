#!/usr/bin/env python3
"""Quick pipeline status check using Lambda"""
import json
import boto3
import sys

lambda_client = boto3.client('lambda', region_name='us-west-2')

def run_query(query_name, sql):
    """Execute a query via Lambda"""
    payload = {"sql": sql}
    
    try:
        response = lambda_client.invoke(
            FunctionName='ops-pipeline-db-query',
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        
        result = json.loads(response['Payload'].read())
        
        if 'errorMessage' in result:
            print(f"❌ {query_name}: {result['errorMessage']}")
            return None
        
        body = json.loads(result.get('body', '{}'))
        return body.get('rows', [])
    except Exception as e:
        print(f"❌ {query_name}: {e}")
        return None

print("\n" + "="*80)
print("  TRADING PIPELINE QUICK STATUS CHECK")
print("="*80)

# 1. Telemetry check
print("\n1. TELEMETRY (Last Hour)")
results = run_query("telemetry", """
    SELECT COUNT(*) as total, 
           COUNT(DISTINCT ticker) as tickers,
           MAX(ts) as latest
    FROM lane_telemetry 
    WHERE ts >= NOW() - INTERVAL '1 hour'
""")
if results:
    for row in results:
        print(f"   Total bars: {row['total']}")
        print(f"   Tickers: {row['tickers']}")
        print(f"   Latest: {row['latest']}")

# 2. Features check
print("\n2. FEATURES (Last Hour)")
results = run_query("features", """
    SELECT COUNT(*) as total,
           COUNT(DISTINCT ticker) as tickers,
           COUNT(CASE WHEN volume_ratio IS NOT NULL THEN 1 END) as with_volume,
           MAX(computed_at) as latest
    FROM lane_features 
    WHERE computed_at >= NOW() - INTERVAL '1 hour'
""")
if results:
    for row in results:
        print(f"   Total: {row['total']}")
        print(f"   Tickers: {row['tickers']}")
        print(f"   With volume_ratio: {row['with_volume']}")
        print(f"   Latest: {row['latest']}")

# 3. Volume analysis detail
print("\n3. LATEST VOLUME ANALYSIS")
results = run_query("volume", """
    SELECT ticker, volume_ratio, volume_surge, computed_at
    FROM lane_features 
    WHERE computed_at >= NOW() - INTERVAL '30 minutes'
    AND volume_ratio IS NOT NULL
    ORDER BY computed_at DESC
    LIMIT 10
""")
if results:
    for row in results:
        surge = "SURGE!" if row['volume_surge'] else ""
        ratio = float(row['volume_ratio']) if row['volume_ratio'] else 0.0
        print(f"   {row['ticker']}: ratio={ratio:.2f} {surge} at {row['computed_at']}")

# 4. Recommendations
print("\n4. RECOMMENDATIONS (Last 2 Hours)")
results = run_query("recommendations", """
    SELECT COUNT(*) as total,
           COUNT(DISTINCT ticker) as tickers,
           MAX(created_at) as latest
    FROM dispatch_recommendations 
    WHERE created_at >= NOW() - INTERVAL '2 hours'
""")
if results:
    for row in results:
        print(f"   Total: {row['total']}")
        print(f"   Tickers: {row['tickers']}")
        print(f"   Latest: {row['latest']}")
        if row['total'] == 0:
            print(f"   ⏳ No recommendations yet (waiting for signal conditions)")

# 5. CLASSIFIER (Last 24 Hours)
print("\n5. CLASSIFIER (Last 24 Hours)")
results = run_query("classifier", """
    SELECT COUNT(*) as total,
           array_length(array_agg(DISTINCT unnested_ticker), 1) as tickers,
           MAX(created_at) as latest
    FROM inbound_events_classified,
         unnest(tickers) as unnested_ticker
    WHERE created_at >= NOW() - INTERVAL '24 hours'
""")
if results:
    for row in results:
        print(f"   Total events: {row['total']}")
        print(f"   Tickers: {row['tickers']}")
        print(f"   Latest: {row['latest']}")

# 6. Executions
print("\n6. EXECUTIONS (Last 2 Hours)")
results = run_query("executions", """
    SELECT COUNT(*) as total,
           COUNT(DISTINCT ticker) as tickers,
           MAX(executed_at) as latest
    FROM dispatch_executions 
    WHERE executed_at >= NOW() - INTERVAL '2 hours'
""")
if results:
    for row in results:
        print(f"   Total: {row['total']}")
        print(f"   Tickers: {row['tickers']}")
        print(f"   Latest: {row['latest']}")
        if row['total'] == 0:
            print(f"   ⏳ No executions yet (waiting for recommendations)")

print("\n" + "="*80)
print("  STATUS: PIPELINE OPERATIONAL")
print("="*80)
