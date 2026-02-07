#!/usr/bin/env python3
"""
Test if account_name column exists by trying to SELECT it
"""
import boto3
import json

lambda_client = boto3.client('lambda', region_name='us-west-2')

# Try to select from active_positions
print("Testing active_positions.account_name...")
payload = {
    'sql': "SELECT account_name FROM active_positions LIMIT 1"
}

response = lambda_client.invoke(
    FunctionName='ops-pipeline-db-migration',
    InvocationType='RequestResponse',
    Payload=json.dumps(payload)
)

result = json.loads(response['Payload'].read())
if result.get('statusCode') == 200:
    print("✅ active_positions.account_name EXISTS")
else:
    print(f"❌ active_positions.account_name MISSING: {result.get('body', 'No error')}")

# Try to select from dispatch_executions
print("\nTesting dispatch_executions.account_name...")
payload = {
    'sql': "SELECT account_name FROM dispatch_executions LIMIT 1"
}

response = lambda_client.invoke(
    FunctionName='ops-pipeline-db-migration',
    InvocationType='RequestResponse',
    Payload=json.dumps(payload)
)

result = json.loads(response['Payload'].read())
if result.get('statusCode') == 200:
    print("✅ dispatch_executions.account_name EXISTS")
else:
    print(f"❌ dispatch_executions.account_name MISSING: {result.get('body', 'No error')}")
