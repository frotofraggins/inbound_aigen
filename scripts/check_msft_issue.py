#!/usr/bin/env python3
"""Investigate MSFT position price discrepancy"""
import boto3
import json

client = boto3.client('lambda', region_name='us-west-2')

# Get MSFT position from database
response = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({
        'sql': "SELECT id, ticker, instrument_type, option_symbol, entry_price, current_price, last_checked_at, check_count FROM active_positions WHERE ticker = 'MSFT' AND status = 'open'"
    })
)

result = json.loads(json.loads(response['Payload'].read())['body'])
rows = result.get('rows', [])

print('=' * 80)
print('MSFT POSITION INVESTIGATION')
print('=' * 80)
print()

if not rows:
    print('No MSFT position found in database')
else:
    row = rows[0]
    print('Database Record:')
    print(f"  Position ID: {row['id']}")
    print(f"  Ticker: {row['ticker']}")
    print(f"  Type: {row['instrument_type']}")
    print(f"  Option Symbol: {row.get('option_symbol', 'NULL')}")
    print(f"  Entry Price: ${float(row['entry_price']):.2f}")
    print(f"  Current Price (DB): ${float(row['current_price']):.2f}")
    print(f"  Last Checked: {row.get('last_checked_at')}")
    print(f"  Check Count: {row.get('check_count')}")
    print()
    print('Alpaca Reality:')
    print(f"  Contract: MSFT260220P00410000")
    print(f"  Current Price (Alpaca): $11.15")
    print(f"  Actual P&L: +129.9% = $6,300")
    print()
    print('=' * 80)
    print('CRITICAL ISSUE:')
    print('=' * 80)
    print()
    
    db_price = float(row['current_price'])
    alpaca_price = 11.15
    entry = float(row['entry_price'])
    
    db_pnl = ((db_price - entry) / entry) * 100
    real_pnl = ((alpaca_price - entry) / entry) * 100
    
    print(f"Database thinks: ${db_price:.2f} = +{db_pnl:.1f}% profit")
    print(f"Reality is: ${alpaca_price:.2f} = +{real_pnl:.1f}% profit")
    print()
    print(f"Take Profit Target: ${entry * 1.80:.2f} (+80%)")
    print()
    
    if real_pnl >= 80:
        print('🚨 POSITION SHOULD HAVE CLOSED AT +80% TARGET!')
        print('   But position manager does not have correct price')
        print()
    
    if not row.get('option_symbol') or row.get('option_symbol') == 'NULL':
        print('ROOT CAUSE: option_symbol is NULL or missing')
        print()
        print('Position manager code (monitor.py line ~55):')
        print('  option_symbol = position.get(\"option_symbol\") or position[\"ticker\"]')
        print()
        print('If option_symbol is NULL, it falls back to ticker \"MSFT\"')
        print('But Alpaca API needs full symbol: MSFT260220P00410000')
        print()
        print('SOLUTION: Update option_symbol in database with correct value')
        print()
        print(f"UPDATE active_positions SET option_symbol = 'MSFT260220P00410000' WHERE id = {row['id']};")
    else:
        print('Option symbol exists, investigating other causes...')
