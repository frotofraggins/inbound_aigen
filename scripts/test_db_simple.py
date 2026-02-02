#!/usr/bin/env python3
import json
import boto3

lambda_client = boto3.client('lambda', region_name='us-west-2')

# Simple count query
payload = {"sql": "SELECT COUNT(*) as count FROM lane_telemetry"}
print("Querying lane_telemetry count...")

response = lambda_client.invoke(
    FunctionName='ops-pipeline-db-query',
    InvocationType='RequestResponse',
    Payload=json.dumps(payload)
)

result = json.loads(response['Payload'].read())
print(json.dumps(result, indent=2))
