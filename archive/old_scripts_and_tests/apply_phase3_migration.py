#!/usr/bin/env python3
"""
Apply Phase 3 WebSocket Idempotency Migration
Migration: 2026_02_02_0002_websocket_idempotency
"""
import json
import boto3
import sys

def apply_migration():
    """Apply migration via Lambda"""
    
    # Read migration SQL
    with open('db/migrations/2026_02_02_0002_websocket_idempotency.sql', 'r') as f:
        migration_sql = f.read()
    
    print("=" * 80)
    print("Phase 3: WebSocket Idempotency Migration")
    print("=" * 80)
    print("\nMigration SQL:")
    print("-" * 80)
    print(migration_sql)
    print("-" * 80)
    
    # Invoke migration Lambda
    lambda_client = boto3.client('lambda', region_name='us-west-2')
    
    payload = {
        'migration_name': '2026_02_02_0002_websocket_idempotency',
        'sql': migration_sql
    }
    
    print("\n📤 Invoking ops-pipeline-db-migration Lambda...")
    
    response = lambda_client.invoke(
        FunctionName='ops-pipeline-db-migration',
        InvocationType='RequestResponse',
        Payload=json.dumps(payload)
    )
    
    result = json.loads(response['Payload'].read())
    
    print("\n📥 Lambda Response:")
    print(json.dumps(result, indent=2))
    
    # Check HTTP status code
    if response['ResponseMetadata']['HTTPStatusCode'] != 200:
        print(f"\n❌ Lambda invocation failed with HTTP status {response['ResponseMetadata']['HTTPStatusCode']}")
        return False
    
    # Check for Lambda execution errors
    if 'FunctionError' in response:
        print(f"\n❌ Lambda execution error: {response['FunctionError']}")
        return False
    
    # Check for errorMessage in payload (unhandled exceptions)
    if 'errorMessage' in result:
        print(f"\n❌ Migration failed: {result['errorMessage']}")
        if 'errorType' in result:
            print(f"   Error type: {result['errorType']}")
        return False
    
    # Parse body and check success flag
    if result.get('statusCode') == 200:
        body = json.loads(result.get('body', '{}'))
        if not body.get('success'):
            print(f"\n❌ Migration failed: {body.get('error', 'Unknown error')}")
            return False
        
        print("\n✅ Migration applied successfully!")
        print(f"   Message: {body.get('message', 'Migration completed')}")
        return True
    else:
        print(f"\n❌ Lambda returned non-200 status: {result.get('statusCode')}")
        return False


def verify_migration():
    """Verify migration was applied"""
    
    lambda_client = boto3.client('lambda', region_name='us-west-2')
    
    # Check for new table and column
    check_query = """
    SELECT 
        table_name,
        column_name,
        data_type
    FROM information_schema.columns
    WHERE table_name IN ('alpaca_event_dedupe', 'active_positions')
      AND column_name IN ('event_id', 'alpaca_order_id')
    ORDER BY table_name, column_name;
    """
    
    print("\n🔍 Verifying migration...")
    
    response = lambda_client.invoke(
        FunctionName='ops-pipeline-db-query',
        InvocationType='RequestResponse',
        Payload=json.dumps({'sql': check_query})
    )
    
    result = json.loads(response['Payload'].read())
    
    # Check for errors
    if 'errorMessage' in result:
        print(f"\n❌ Verification query failed: {result['errorMessage']}")
        return False
    
    body = json.loads(result.get('body', '{}'))
    
    if body.get('rows'):
        print("\n✅ Verification Results:")
        for row in body['rows']:
            print(f"   {row['table_name']}.{row['column_name']}: {row['data_type']}")
        
        # Verify migration was recorded
        migration_check = lambda_client.invoke(
            FunctionName='ops-pipeline-db-query',
            InvocationType='RequestResponse',
            Payload=json.dumps({
                'sql': "SELECT version FROM schema_migrations WHERE version = '2026_02_02_0002_websocket_idempotency'"
            })
        )
        
        migration_result = json.loads(migration_check['Payload'].read())
        migration_body = json.loads(migration_result.get('body', '{}'))
        
        if not migration_body.get('rows') or len(migration_body['rows']) == 0:
            print("\n❌ Migration not found in schema_migrations table!")
            return False
        
        print("✅ Migration verified in schema_migrations table")
        return True
    else:
        print("\n❌ Verification failed - columns not found")
        return False


if __name__ == '__main__':
    print("\n🚀 Starting Phase 3 Migration Application\n")
    
    if apply_migration():
        if verify_migration():
            print("\n" + "=" * 80)
            print("✅ Phase 3 Migration Complete!")
            print("=" * 80)
            print("\nNext Steps:")
            print("1. Rebuild and redeploy trade-stream service")
            print("2. Test with duplicate WebSocket events")
            print("3. Verify no duplicate positions created")
            sys.exit(0)
        else:
            print("\n⚠️ Migration applied but verification failed")
            sys.exit(1)
    else:
        print("\n❌ Migration failed")
        sys.exit(1)
