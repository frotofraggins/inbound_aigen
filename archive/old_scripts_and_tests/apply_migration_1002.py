#!/usr/bin/env python3
"""
Apply migration 1002: Add account_name to dispatch_executions
"""
import boto3
import json

# Read migration SQL
with open('db/migrations/1002_add_account_name_to_dispatch_executions.sql', 'r') as f:
    migration_sql = f.read()

# Invoke Lambda
lambda_client = boto3.client('lambda', region_name='us-west-2')

payload = {
    'sql': migration_sql
}

print("Applying migration 1002...")
print("=" * 60)

response = lambda_client.invoke(
    FunctionName='ops-pipeline-db-migration',
    InvocationType='RequestResponse',
    Payload=json.dumps(payload)
)

result = json.loads(response['Payload'].read())
print(json.dumps(result, indent=2))

if result.get('statusCode') == 200:
    body = json.loads(result['body'])
    print("\n✅ Migration 1002 applied successfully!")
    print(f"Rows affected: {body.get('rows_affected', 'N/A')}")
else:
    print("\n❌ Migration failed!")
    print(result.get('body', 'No error details'))
