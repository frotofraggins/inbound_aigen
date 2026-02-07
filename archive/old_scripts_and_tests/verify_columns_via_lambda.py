#!/usr/bin/env python3
"""
Verify account_name columns exist via Lambda
"""
import boto3
import json

lambda_client = boto3.client('lambda', region_name='us-west-2')

# Check active_positions
print("Checking active_positions table...")
payload = {
    'sql': """
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_name = 'active_positions' AND column_name = 'account_name'
    """
}

response = lambda_client.invoke(
    FunctionName='ops-pipeline-db-migration',
    InvocationType='RequestResponse',
    Payload=json.dumps(payload)
)

result = json.loads(response['Payload'].read())
print(json.dumps(result, indent=2))

# Check dispatch_executions
print("\n\nChecking dispatch_executions table...")
payload = {
    'sql': """
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_name = 'dispatch_executions' AND column_name = 'account_name'
    """
}

response = lambda_client.invoke(
    FunctionName='ops-pipeline-db-migration',
    InvocationType='RequestResponse',
    Payload=json.dumps(payload)
)

result = json.loads(response['Payload'].read())
print(json.dumps(result, indent=2))
