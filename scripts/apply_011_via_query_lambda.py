#!/usr/bin/env python3
"""
Apply Migration 011 via DB Query Lambda
Uses the query Lambda which already has DB access
"""

import boto3
import json

# Read migration and split into individual statements
import os
script_dir = os.path.dirname(os.path.abspath(__file__))
migration_path = os.path.join(script_dir, '..', 'db', 'migrations', '011_add_learning_infrastructure.sql')

with open(migration_path, 'r') as f:
    migration_sql = f.read()

# Remove comments and split into statements
statements = []
for line in migration_sql.split('\n'):
    line = line.strip()
    if line and not line.startswith('--') and not line.startswith('/*'):
        statements.append(line)

# Join and split by semicolons
full_sql = ' '.join(statements)
commands = [cmd.strip() + ';' for cmd in full_sql.split(';') if cmd.strip()]

print(f"Applying Migration 011 via Query Lambda...")
print(f"Total commands: {len(commands)}")
print()

lambda_client = boto3.client('lambda', region_name='us-west-2')

# Apply key statements one by one
key_alters = [
    "ALTER TABLE dispatch_recommendations ADD COLUMN IF NOT EXISTS features_snapshot JSONB, ADD COLUMN IF NOT EXISTS sentiment_snapshot JSONB",
    "ALTER TABLE dispatcher_execution ADD COLUMN IF NOT EXISTS features_snapshot JSONB, ADD COLUMN IF NOT EXISTS sentiment_snapshot JSONB",
    "ALTER TABLE position_history ADD COLUMN IF NOT EXISTS win_loss_label SMALLINT, ADD COLUMN IF NOT EXISTS r_multiple NUMERIC(8,4), ADD COLUMN IF NOT EXISTS mae_pct NUMERIC(8,4), ADD COLUMN IF NOT EXISTS mfe_pct NUMERIC(8,4), ADD COLUMN IF NOT EXISTS holding_minutes INT, ADD COLUMN IF NOT EXISTS exit_reason_norm VARCHAR(32)"
]

success_count = 0
for i, stmt in enumerate(key_alters, 1):
    print(f"Executing statement {i}/{len(key_alters)}...")
    try:
        response = lambda_client.invoke(
            FunctionName='ops-pipeline-db-query',
            Payload=json.dumps({'query': stmt})
        )
        result = json.loads(response['Payload'].read())
        
        if result.get('statusCode') == 200:
            print(f"  ✅ Success")
            success_count += 1
        else:
            print(f"  ❌ Failed: {result}")
    except Exception as e:
        print(f"  ❌ Error: {e}")

print()
print(f"✅ Applied {success_count}/{len(key_alters)} statements")

# Verify
print("\nVerifying columns...")
verify_query = """
SELECT table_name, column_name 
FROM information_schema.columns 
WHERE table_name IN ('dispatch_recommendations', 'dispatcher_execution', 'position_history')
  AND column_name IN ('features_snapshot', 'sentiment_snapshot', 'win_loss_label', 'r_multiple')
ORDER BY table_name, column_name
"""

response = lambda_client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'query': verify_query})
)
result = json.loads(response['Payload'].read())

if result.get('statusCode') == 200:
    body = json.loads(result['body'])
    results = body.get('results', [])
    print(f"Found {len(results)} new columns:")
    for row in results:
        print(f"  • {row['table_name']}.{row['column_name']}")
