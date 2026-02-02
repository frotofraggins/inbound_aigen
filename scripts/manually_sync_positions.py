#!/usr/bin/env python3
"""
Manually sync positions from dispatch_executions to active_positions
USE THIS to force-sync when Position Manager hasn't run yet
"""
import boto3
import json

client = boto3.client('lambda', region_name='us-west-2')

print("=== Manual Position Sync ===\n")

# Get the 3 options trades
print("1. Finding untracked options trades...")
result = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'sql': '''
        SELECT 
            de.execution_id,
            de.ticker,
            de.instrument_type,
            de.action,
            de.entry_price,
            de.qty,
            de.strike_price,
            de.expiration_date,
            de.stop_loss_price,
            de.take_profit_price,
            de.max_hold_minutes,
            de.option_symbol,
            de.simulated_ts
        FROM dispatch_executions de
        LEFT JOIN active_positions ap ON ap.execution_id = de.execution_id
        WHERE de.execution_mode = 'ALPACA_PAPER'
        AND de.instrument_type IN ('CALL', 'PUT')
        AND ap.id IS NULL
        ORDER BY de.simulated_ts DESC
    '''})
)
body = json.loads(json.load(result['Payload'])['body'])

if not body.get('rows'):
    print("   No untracked positions found - all synced!")
    exit(0)

trades = body['rows']
print(f"   Found {len(trades)} untracked options trades\n")

# Create active_position for each
print("2. Creating active_position records...")
for trade in trades:
    print(f"\n   {trade['ticker']} {trade['instrument_type']} @ ${trade['entry_price']}")
    
    # Determine strategy_type (day_trade if no data, swing_trade otherwise)
    strategy_type = 'swing_trade'  # Default for options
    
    sql = f"""
        INSERT INTO active_positions (
            execution_id, ticker, instrument_type, strategy_type,
            side, quantity, entry_price, entry_time,
            strike_price, expiration_date,
            stop_loss, take_profit, max_hold_minutes,
            bracket_order_accepted, current_price, status,
            original_quantity
        ) VALUES (
            '{trade['execution_id']}',
            '{trade['ticker']}',
            '{trade['instrument_type']}',
            '{strategy_type}',
            'long',
            {trade['qty']},
            {trade['entry_price']},
            '{trade['simulated_ts']}',
            {trade['strike_price']},
            '{trade['expiration_date']}',
            {trade['stop_loss_price'] or 'NULL'},
            {trade['take_profit_price'] or 'NULL'},
            {trade['max_hold_minutes'] or 240},
            false,
            {trade['entry_price']},
            'open',
            {trade['qty']}
        )
        ON CONFLICT (execution_id) DO NOTHING
        RETURNING id
    """
    
    result = client.invoke(
        FunctionName='ops-pipeline-db-query',
        Payload=json.dumps({'sql': sql})
    )
    body = json.loads(json.load(result['Payload'])['body'])
    
    if 'rows' in body and body['rows']:
        position_id = body['rows'][0]['id']
        print(f"   ✓ Created position ID {position_id}")
    else:
        print(f"   ℹ️  Already exists or error: {body.get('error', 'Unknown')}")

print("\n3. Verification...")
result = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'sql': "SELECT COUNT(*) as count FROM active_positions WHERE status = 'open'"})
)
body = json.loads(json.load(result['Payload'])['body'])
count = body['rows'][0]['count'] if 'rows' in body else 0
print(f"   Active positions: {count}")

print("\n✅ SYNC COMPLETE")
print("Your positions are now being monitored by Position Manager!")
print("\nNext Position Manager run (every 1 min) will:")
print("  - Update current prices")
print("  - Check trailing stops")
print("  - Apply exit logic")
