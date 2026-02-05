#!/usr/bin/env python3
"""Check dispatch_recommendations table"""
import boto3
import json

client = boto3.client('lambda', region_name='us-west-2')

# Check recent recommendations
query = """
SELECT 
    id,
    ticker,
    action,
    instrument_type,
    confidence,
    status,
    created_at,
    processed_at
FROM dispatch_recommendations
WHERE created_at > NOW() - INTERVAL '2 hours'
ORDER BY created_at DESC
LIMIT 20;
"""

response = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'sql': query})
)

result = json.loads(response['Payload'].read())
print(json.dumps(result, indent=2, default=str))
