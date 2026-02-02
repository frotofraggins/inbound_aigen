#!/usr/bin/env python3
"""
Data Integrity Verification
Checks that trades are being saved and can be retrieved correctly
"""
import boto3
import json
from datetime import datetime

client = boto3.client('lambda', region_name='us-west-2')

def query(sql):
    """Execute query via Lambda"""
    r = client.invoke(
        FunctionName='ops-pipeline-db-query',
        Payload=json.dumps({'sql': sql})
    )
    return json.loads(json.load(r['Payload'])['body'])

print("="*80)
print("DATA INTEGRITY VERIFICATION")
print("="*80)

# Test 1: Check table exists
print("\n1. Verify dispatch_executions table exists")
result = query("SELECT COUNT(*) as count FROM dispatch_executions")
total = result['rows'][0]['count'] if 'rows' in result else 0
print(f"   ✓ Table exists with {total} total records")

# Test 2: Check instrument_type values
print("\n2. Check instrument_type values in database")
result = query("""
    SELECT DISTINCT instrument_type, COUNT(*) as count
    FROM dispatch_executions
    GROUP BY instrument_type
    ORDER BY count DESC
""")
if 'rows' in result:
    print("   Instrument types found:")
    for row in result['rows']:
        print(f"     - {row['instrument_type']}: {row['count']} records")

# Test 3: Check today's trades by execution_mode
print("\n3. Today's trades by execution_mode")
result = query("""
    SELECT execution_mode, COUNT(*) as count
    FROM dispatch_executions
    WHERE simulated_ts::date = CURRENT_DATE
    GROUP BY execution_mode
""")
if 'rows' in result:
    for row in result['rows']:
        print(f"   {row['execution_mode']}: {row['count']} trades")

# Test 4: Get recent options trades (NO date filter)
print("\n4. Recent options trades (any date)")
result = query("""
    SELECT ticker, instrument_type, entry_price, simulated_ts::text as time
    FROM dispatch_executions
    WHERE instrument_type IN ('CALL', 'PUT')
    ORDER BY simulated_ts DESC
    LIMIT 5
""")
if 'rows' in result and result['rows']:
    print(f"   Found {len(result['rows'])} options trades:")
    for row in result['rows']:
        print(f"     {row['time'][:19]}: {row['ticker']} {row['instrument_type']} @ ${row['entry_price']}")
else:
    print("   ⚠️  NO options trades found!")

# Test 5: Check if strike_price and expiration_date are populated
print("\n5. Check options-specific fields")
result = query("""
    SELECT 
        COUNT(*) as total,
        COUNT(strike_price) as with_strike,
        COUNT(expiration_date) as with_exp,
        COUNT(option_symbol) as with_symbol
    FROM dispatch_executions
    WHERE instrument_type IN ('CALL', 'PUT')
""")
if 'rows' in result and result['rows']:
    row = result['rows'][0]
    print(f"   Total options: {row['total']}")
    print(f"   With strike_price: {row['with_strike']}")
    print(f"   With expiration_date: {row['with_exp']}")
    print(f"   With option_symbol: {row['with_symbol']}")

# Test 6: Sample one options trade
print("\n6. Sample options trade (full details)")
result = query("""
    SELECT *
    FROM dispatch_executions
    WHERE instrument_type IN ('CALL', 'PUT')
    ORDER BY simulated_ts DESC
    LIMIT 1
""")
if 'rows' in result and result['rows']:
    row = result['rows'][0]
    print(f"   Ticker: {row.get('ticker', 'NULL')}")
    print(f"   Type: {row.get('instrument_type', 'NULL')}")
    print(f"   Strike: {row.get('strike_price', 'NULL')}")
    print(f"   Exp: {row.get('expiration_date', 'NULL')}")
    print(f"   Symbol: {row.get('option_symbol', 'NULL')}")
    print(f"   Mode: {row.get('execution_mode', 'NULL')}")
    print(f"   Time: {row.get('simulated_ts', 'NULL')}")
else:
    print("   ⚠️  NO options trades to sample!")

# Test 7: Check active_positions table
print("\n7. Check active_positions table")
result = query("SELECT COUNT(*) as count FROM active_positions")
active_count = result['rows'][0]['count'] if 'rows' in result else 0
print(f"   Total positions: {active_count}")

if active_count > 0:
    result = query("""
        SELECT ticker, instrument_type, status, entry_price
        FROM active_positions
        ORDER BY entry_time DESC
        LIMIT 3
    """)
    if 'rows' in result:
        for row in result['rows']:
            print(f"     {row['ticker']}: {row.get('instrument_type', 'NULL')} - {row['status']}")

print("\n" + "="*80)
print("VERIFICATION COMPLETE")
print("="*80)
