#!/usr/bin/env python3
"""
Run database migration via Lambda
"""
import boto3
import json

lambda_client = boto3.client('lambda', region_name='us-west-2')

# SQL to add missing columns
sql = """
ALTER TABLE active_positions ADD COLUMN IF NOT EXISTS original_quantity INTEGER;
ALTER TABLE active_positions ADD COLUMN IF NOT EXISTS peak_price DECIMAL(12, 4);
ALTER TABLE active_positions ADD COLUMN IF NOT EXISTS trailing_stop_price DECIMAL(12, 4);
ALTER TABLE active_positions ADD COLUMN IF NOT EXISTS entry_underlying_price DECIMAL(12, 4);
"""

payload = {
    'sql': sql
}

print("Invoking Lambda to add missing columns...")
response = lambda_client.invoke(
    FunctionName='ops-pipeline-db-migration',
    InvocationType='RequestResponse',
    Payload=json.dumps(payload)
)

result = json.loads(response['Payload'].read())
print("\nLambda response:")
print(json.dumps(result, indent=2))

if response['StatusCode'] == 200:
    print("\n✓ Migration completed successfully!")
else:
    print(f"\n✗ Migration failed with status {response['StatusCode']}")
