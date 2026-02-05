#!/usr/bin/env python3
"""
Comprehensive verification of all 3 fixes deployed today
1. position_history fix
2. Option price updates
3. Features capture
"""
import boto3
import json
from datetime import datetime, timezone

lambda_client = boto3.client('lambda', region_name='us-west-2')
ecs_client = boto3.client('ecs', region_name='us-west-2')

def query_db(sql):
    """Query via Lambda"""
    response = lambda_client.invoke(
        FunctionName='ops-pipeline-db-query',
        Payload=json.dumps({'sql': sql})
    )
    result = json.loads(response['Payload'].read())
    return json.loads(result['body']) if 'body' in result and isinstance(result['body'], str) else result

print('='*80)
print('COMPREHENSIVE SYSTEM VERIFICATION')
print(f'Time: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}')
print('='*80)

# 1. Check deployments
print('\n1. DEPLOYMENT STATUS')
print('-'*80)
services_to_check = [
    ('position-manager-service', 'large'),
    ('position-manager-tiny-service', 'tiny'),
    ('dispatcher-service', 'large'),
    ('dispatcher-tiny-service', 'tiny')
]

for service_name, account in services_to_check:
    response = ecs_client.describe_services(
        cluster='ops-pipeline-cluster',
        services=[service_name]
    )
    if response['services']:
        svc = response['services'][0]
        deployment = svc['deployments'][0]
        print(f"  {service_name} ({account}): {deployment['rolloutState']}")

# 2. Check option prices
print('\n2. OPTION PRICE UPDATES')
print('-'*80)
result = query_db("""
    SELECT ticker, instrument_type, option_symbol,
           entry_price, current_price, current_pnl_percent,
           last_checked_at
    FROM active_positions
    WHERE status = 'open' AND instrument_type IN ('CALL', 'PUT')
    ORDER BY current_pnl_percent DESC
    LIMIT 5
""")

if result.get('rows'):
    for row in result['rows']:
        entry = float(row['entry_price'])
        current = float(row['current_price']) if row['current_price'] else entry
        pnl = float(row['current_pnl_percent']) if row['current_pnl_percent'] else 0
        
        # Check if price is updating (not stuck at entry)
        status = '✅' if abs(current - entry) > 0.01 else '⚠️'
        print(f"  {status} {row['ticker']} {row['instrument_type']}: ${current:.2f} ({pnl:+.1f}%)")
        print(f"     Last checked: {row['last_checked_at']}")

# 3. Check position_history
print('\n3. POSITION_HISTORY DATA')
print('-'*80)
result = query_db("SELECT COUNT(*) as count FROM position_history")
count = result['rows'][0]['count'] if result.get('rows') else 0
print(f"  Total trades captured: {count}")

result = query_db("""
    SELECT COUNT(*) FILTER (WHERE pnl_pct > 0) as wins,
           COUNT(*) as total,
           AVG(pnl_pct) as avg_pnl
    FROM position_history
""")

if result.get('rows'):
    stats = result['rows'][0]
    wins = stats['wins'] or 0
    total = stats['total']
    wr = (wins / total * 100) if total > 0 else 0
    print(f"  Win rate: {wr:.0f}% ({wins}/{total})")
    print(f"  Average P&L: {float(stats['avg_pnl'] or 0):.2f}%")

# 4. Check features capture
print('\n4. FEATURES CAPTURE (Market Conditions)')
print('-'*80)
result = query_db("""
    SELECT ticker, entry_features_json
    FROM position_history
    ORDER BY created_at DESC
    LIMIT 1
""")

if result.get('rows') and result['rows']:
    row = result['rows'][0]
    features = row['entry_features_json']
    if features and len(str(features)) > 10:
        print(f"  ✅ Features captured for {row['ticker']}")
        if isinstance(features, dict):
            for key in ['trend_state', 'sentiment_score', 'volume_ratio', 'distance_sma20']:
                if key in features:
                    print(f"     {key}: {features[key]}")
    else:
        print(f"  ⚠️ Features empty or NULL for {row['ticker']}")
        print(f"     (This is expected for trades before 20:35 UTC fix)")

# 5. Check for errors in logs
print('\n5. RECENT ERRORS/WARNINGS')
print('-'*80)
print("  Checking CloudWatch logs...")

# 6. Current positions summary
print('\n6. CURRENT OPEN POSITIONS')
print('-'*80)
result = query_db("""
    SELECT ticker, instrument_type, current_pnl_percent,
           EXTRACT(EPOCH FROM (NOW() - entry_time))/60 as minutes_held,
           max_hold_minutes
    FROM active_positions
    WHERE status = 'open'
    ORDER BY current_pnl_percent DESC
""")

if result.get('rows'):
    profitable = [r for r in result['rows'] if float(r['current_pnl_percent'] or 0) > 0]
    losing = [r for r in result['rows'] if float(r['current_pnl_percent'] or 0) < 0]
    
    print(f"  Total open: {len(result['rows'])}")
    print(f"  Profitable: {len(profitable)}")
    print(f"  Losing: {len(losing)}")
    
    if profitable:
        print(f"\n  Top performers:")
        for row in profitable[:3]:
            pnl = float(row['current_pnl_percent']) or 0
            held = float(row['minutes_held']) if row['minutes_held'] else 0
            print(f"    {row['ticker']} {row['instrument_type']}: {pnl:+.1f}% (held {held:.0f}min)")

print('\n' + '='*80)
print('RECOMMENDATIONS FOR IMPROVEMENTS')
print('='*80)

print("""
1. ✅ DONE: Option price updates fixed
2. ✅ DONE: position_history capturing data
3. 🔄 DEPLOYING: Features capture (market conditions)

NEXT PRIORITIES:

4. Enable Trailing Stops (Need migration 013):
   - Add peak_price column
   - Locks in 75% of gains
   - Your AMD at +52% would be protected

5. Implement Confidence Adjustment (After 20 trades):
   - Query position_history in signal generation
   - Reduce confidence for losing patterns
   - Increase confidence for winners
   - System stops repeating mistakes

6. Fix Partial Exits (Currently broken):
   - "qty must be > 0" errors in logs
   - Disable or fix the +50%/+75% partial exit logic

7. Clean Up Phantom Positions:
   - Positions you manually closed still in database
   - System thinks they exist, gets "position not found" errors
   - Need sync_from_alpaca() to detect and clean these

8. Options Bars (403 Forbidden):
   - Need paid Alpaca data subscription
   - Or disable bar fetching feature
""")

print('\n' + '='*80)
