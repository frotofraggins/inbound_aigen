#!/usr/bin/env python3
"""Apply behavior learning migration via Lambda"""
import json
import boto3

lambda_client = boto3.client('lambda', region_name='us-west-2')

print("\n" + "="*80)
print("  APPLYING BEHAVIOR LEARNING MODE MIGRATION")
print("="*80)

# Read the migration file
print("\n1. Reading migration file...")
with open('db/migrations/2026_02_02_0001_position_telemetry.sql', 'r') as f:
    migration_sql = f.read()

print(f"   Migration size: {len(migration_sql)} bytes")

# Apply via Lambda
print("\n2. Invoking ops-pipeline-db-migration Lambda...")
try:
    response = lambda_client.invoke(
        FunctionName='ops-pipeline-db-migration',
        InvocationType='RequestResponse',
        Payload=json.dumps({
            "version": "2026_02_02_0001_position_telemetry",
            "sql": migration_sql
        })
    )
    
    result = json.loads(response['Payload'].read())
    print(f"   Status Code: {result.get('statusCode')}")
    
    body = json.loads(result.get('body', '{}'))
    
    if result.get('statusCode') == 200:
        print("   ✅ Migration applied successfully!")
        if 'message' in body:
            print(f"   Message: {body['message']}")
    else:
        print("   ❌ Migration failed!")
        if 'error' in body:
            print(f"   Error: {body['error']}")
        print(f"   Full response: {json.dumps(body, indent=2)}")
        
except Exception as e:
    print(f"   ❌ Exception: {e}")
    import traceback
    traceback.print_exc()

print("\n3. Verifying migration...")
print("   Run: python3 check_migration_status.py")

print("\n" + "="*80 + "\n")
