#!/usr/bin/env python3
import json
import boto3

lambda_client = boto3.client('lambda', region_name='us-west-2')

# Test the telemetry query
payload = {"sql": """
    SELECT COUNT(*) as total, 
           COUNT(DISTINCT ticker) as tickers,
           MAX(bar_time) as latest,
           MIN(bar_time) as earliest
    FROM lane_telemetry 
    WHERE bar_time >= NOW() - INTERVAL '1 hour'
"""}

print("Testing telemetry query...")
response = lambda_client.invoke(
    FunctionName='ops-pipeline-db-query',
    InvocationType='RequestResponse',
    Payload=json.dumps(payload)
)

result = json.loads(response['Payload'].read())
print(json.dumps(result, indent=2))

# Also check total count
payload2 = {"sql": "SELECT COUNT(*) as total, MAX(bar_time) as latest FROM lane_telemetry"}
print("\nTotal telemetry count...")
response2 = lambda_client.invoke(
    FunctionName='ops-pipeline-db-query',
    InvocationType='RequestResponse',
    Payload=json.dumps(payload2)
)
result2 = json.loads(response2['Payload'].read())
print(json.dumps(result2, indent=2))
