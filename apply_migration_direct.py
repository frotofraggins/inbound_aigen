#!/usr/bin/env python3
"""Apply behavior learning migration directly via query Lambda"""
import json
import boto3

lambda_client = boto3.client('lambda', region_name='us-west-2')

def execute_sql(sql):
    """Execute SQL via query Lambda"""
    response = lambda_client.invoke(
        FunctionName='ops-pipeline-db-query',
        InvocationType='RequestResponse',
        Payload=json.dumps({"sql": sql})
    )
    result = json.loads(response['Payload'].read())
    return result

print("\n" + "="*80)
print("  APPLYING BEHAVIOR LEARNING MODE MIGRATION (DIRECT)")
print("="*80)

# Read the migration file
print("\n1. Reading migration file...")
with open('db/migrations/2026_02_02_0001_position_telemetry.sql', 'r') as f:
    migration_sql = f.read()

print(f"   Migration size: {len(migration_sql)} bytes")

# Split into individual statements (simple approach - split on semicolon outside of DO blocks)
print("\n2. Executing migration...")

try:
    result = execute_sql(migration_sql)
    
    status_code = result.get('statusCode', 500)
    body = json.loads(result.get('body', '{}'))
    
    if status_code == 200:
        print("   ✅ Migration executed successfully!")
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

print("\n3. Recording migration in schema_migrations...")
try:
    result = execute_sql("""
        INSERT INTO schema_migrations (version, applied_at) 
        VALUES ('2026_02_02_0001_position_telemetry', NOW())
        ON CONFLICT (version) DO NOTHING
    """)
    print("   ✅ Migration recorded")
except Exception as e:
    print(f"   ⚠️  Could not record migration: {e}")

print("\n4. Verifying migration...")
print("   Run: python3 check_migration_status.py")

print("\n" + "="*80 + "\n")
