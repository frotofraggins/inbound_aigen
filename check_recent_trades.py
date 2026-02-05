#!/usr/bin/env python3
import boto3, json

client = boto3.client('lambda', region_name='us-west-2')
response = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({
        'sql': """
        SELECT 
            ticker,
            action,
            instrument_type,
            qty,
            notional,
            entry_price,
            execution_mode,
            simulated_ts
        FROM dispatch_executions
        WHERE simulated_ts > NOW() - INTERVAL '4 hours'
        ORDER BY simulated_ts DESC
        LIMIT 30
        """
    })
)
result = json.loads(json.load(response['Payload'])['body'])
print('Recent Trades (Last 4 Hours):')
print('='*100)
total_notional = 0
for row in result['rows']:
    notional = float(row.get('notional', 0) or 0)
    qty = float(row.get('qty', 0) or 0)
    total_notional += notional
    print(f"{row['simulated_ts'][:16]} {row['ticker']:6s} {row['action']:4s} {row['instrument_type'] or 'STOCK':5s} Qty:{qty:6.0f} ${notional:10,.2f} {row['execution_mode']:20s}")

print('='*100)
print(f"Total Notional: ${total_notional:,.2f}")
print(f"Average per trade: ${total_notional/len(result['rows']) if result['rows'] else 0:,.2f}")
