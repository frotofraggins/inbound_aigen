#!/usr/bin/env python3
"""Check QCOM position details"""
import boto3, json

client = boto3.client('lambda', region_name='us-west-2')

print("=== QCOM Position Analysis ===\n")

# Check if QCOM is in our database
queries = [
    ("Executions", "SELECT * FROM dispatch_executions WHERE ticker = 'QCOM' LIMIT 5"),
    ("Active Positions", "SELECT * FROM active_positions WHERE ticker = 'QCOM'"),
    ("Recommendations", "SELECT * FROM dispatch_recommendations WHERE ticker = 'QCOM' ORDER BY created_at DESC LIMIT 3"),
]

for name, sql in queries:
    print(f"--- {name} ---")
    try:
        r = client.invoke(
            FunctionName='ops-pipeline-db-query',
            Payload=json.dumps({'sql': sql})
        )
        body = json.loads(json.load(r['Payload'])['body'])
        if 'rows' in body and body['rows']:
            print(f"Found {len(body['rows'])} row(s)")
            for row in body['rows'][:2]:
                print(f"  {row}")
        else:
            print("  No records found")
    except Exception as e:
        print(f"  Error: {e}")
    print()

print("=== CONCLUSION ===")
print("If no records found above, the QCOM PUT position is likely:")
print("1. A manual trade (not from our system)")
print("2. From before our system started tracking")
print("3. From a different account")
print("\nOur system only trades signals it generates through the AI pipeline.")
