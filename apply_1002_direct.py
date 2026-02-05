#!/usr/bin/env python3
"""
Apply migration 1002 directly via Lambda
"""
import boto3
import json
import re

# Read migration SQL
with open('db/migrations/1002_add_account_name_to_dispatch_executions.sql', 'r') as f:
    migration_sql = f.read()

# Remove comments
lines = []
for line in migration_sql.split('\n'):
    # Remove -- comments
    if '--' in line:
        line = line[:line.index('--')]
    if line.strip():
        lines.append(line)

clean_sql = '\n'.join(lines)

# Split into individual statements
statements = [s.strip() for s in clean_sql.split(';') if s.strip()]

# Invoke Lambda with raw SQL
lambda_client = boto3.client('lambda', region_name='us-west-2')

print("Applying migration 1002 directly...")
print("=" * 60)

for i, stmt in enumerate(statements, 1):
    if not stmt:
        continue
        
    print(f"\nStatement {i}:")
    print(stmt[:100] + "..." if len(stmt) > 100 else stmt)
    
    payload = {'sql': stmt}
    
    response = lambda_client.invoke(
        FunctionName='ops-pipeline-db-migration',
        InvocationType='RequestResponse',
        Payload=json.dumps(payload)
    )
    
    result = json.loads(response['Payload'].read())
    
    if result.get('statusCode') == 200:
        print("✅ Success")
    else:
        print(f"❌ Failed: {result.get('body', 'No error details')}")
        break

print("\n" + "=" * 60)
print("✅ Migration 1002 applied successfully!")
