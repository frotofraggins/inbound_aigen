#!/usr/bin/env python3
"""
Analyze why UNH PUT was selected when stock was going up
"""
import boto3
import json

client = boto3.client('lambda', region_name='us-west-2')

print("="*80)
print("UNH PUT TRADE ANALYSIS")
print("="*80)

# Find the UNH PUT execution
response = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({
        'sql': '''
        SELECT 
            execution_id, recommendation_id, ticker, instrument_type,
            entry_price, simulated_ts, explain_json
        FROM dispatch_executions
        WHERE ticker = 'UNH'
          AND instrument_type = 'PUT'
        ORDER BY simulated_ts DESC
        LIMIT 1
        '''
    })
)

result = json.loads(json.loads(response['Payload'].read())['body'])
rows = result.get('rows', [])

if not rows:
    print("No UNH PUT execution found")
    exit(0)

exec_data = rows[0]
print(f"\nExecution Details:")
print(f"  Time: {exec_data['simulated_ts']}")
print(f"  Entry: ${float(exec_data['entry_price']):.2f}")
print(f"  Recommendation ID: {exec_data['recommendation_id']}")

# Get recommendation details
rec_id = exec_data['recommendation_id']

response2 = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({
        'sql': f"SELECT ticker, action, instrument_type, confidence, reason, features_snapshot FROM dispatch_recommendations WHERE id = {rec_id}"
    })
)

result2 = json.loads(json.loads(response2['Payload'].read())['body'])
rows2 = result2.get('rows', [])

if not rows2:
    print("Recommendation not found")
    exit(0)

rec = rows2[0]
print(f"\nSignal Details:")
print(f"  Action: {rec['action']}")
print(f"  Type: {rec['instrument_type']}")
print(f"  Confidence: {float(rec['confidence']):.3f}")

if rec.get('reason'):
    reason = json.loads(rec['reason']) if isinstance(rec['reason'], str) else rec['reason']
    print(f"\nSignal Reasoning:")
    if isinstance(reason, dict):
        rationale = reason.get('decision', {}).get('rationale', 'N/A')
        print(f"  {rationale}")

if rec.get('features_snapshot'):
    features = json.loads(rec['features_snapshot']) if isinstance(rec['features_snapshot'], str) else rec['features_snapshot']
    
    print(f"\nTechnical Indicators at Entry:")
    print(f"  Close: ${features.get('close', 'N/A'):.2f}")
    print(f"  SMA20: ${features.get('sma20', 'N/A'):.2f}")
    print(f"  SMA50: ${features.get('sma50', 'N/A'):.2f}")
    print(f"  Trend State: {features.get('trend_state', 'N/A')}")
    
    distance = float(features.get('distance_sma20', 0)) * 100
    print(f"  Price vs SMA20: {distance:+.2f}%")
    
    # Determine if price was above or below SMA20
    if distance > 0:
        print(f"\n  ⚠️  ANALYSIS: Price was ABOVE SMA20 by {abs(distance):.2f}%")
        print(f"      But system chose PUT (bearish)")
        print(f"      This is WRONG if stock was in uptrend!")
    else:
        print(f"\n  ✅ ANALYSIS: Price was BELOW SMA20 by {abs(distance):.2f}%")
        print(f"      System chose PUT (bearish) - correct for downtrend")
    
    trend = features.get('trend_state', 0)
    print(f"\n  Trend State: {trend}")
    if trend == 1:
        print(f"      +1 = Uptrend (SMA20 > SMA50)")
        print(f"      ⚠️  PUT on uptrend is WRONG")
    elif trend == -1:
        print(f"      -1 = Downtrend (SMA20 < SMA50)")
        print(f"      ✅ PUT on downtrend is CORRECT")
    else:
        print(f"      0 = No clear trend")

print("\n" + "="*80)
print("CONCLUSION:")
print("="*80)

if rows2:
    features = json.loads(rec['features_snapshot']) if isinstance(rec['features_snapshot'], str) else rec['features_snapshot']
    distance = float(features.get('distance_sma20', 0))
    trend = features.get('trend_state', 0)
    
    if trend == -1 and distance < 0:
        print("System correctly identified downtrend and bought PUT")
        print("The trade is losing because UNH reversed to upside")
        print("This is normal - not every trade wins")
    elif trend == 1 or distance > 0:
        print("⚠️  SIGNAL ERROR: System bought PUT on uptrend/upside")
        print("This indicates a bug in signal generation logic")
        print("System should not buy PUTs when:")
        print("  - Price above SMA20 (upside)")
        print("  - Trend state = +1 (uptrend)")
    else:
        print("Unclear - need more analysis")
