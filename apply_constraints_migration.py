#!/usr/bin/env python3
"""
Apply Constraints Migration (2026_02_02_0003_add_constraints_no_do)
Re-adds constraints that were removed when DO blocks were stripped
"""
import json
import boto3
import sys

def apply_migration():
    """Apply migration via Lambda"""
    
    # Read migration SQL
    with open('db/migrations/2026_02_02_0003_add_constraints_no_do.sql', 'r') as f:
        migration_sql = f.read()
    
    print("=" * 80)
    print("Constraints Migration: Re-add Missing Constraints")
    print("=" * 80)
    print("\nMigration SQL:")
    print("-" * 80)
    print(migration_sql)
    print("-" * 80)
    
    # Invoke migration Lambda
    lambda_client = boto3.client('lambda', region_name='us-west-2')
    
    payload = {
        'migration_name': '2026_02_02_0003_add_constraints_no_do',
        'migration_sql': migration_sql
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
    """Verify constraints were added"""
    
    lambda_client = boto3.client('lambda', region_name='us-west-2')
    
    # Check for constraints
    check_query = """
    SELECT 
        conname AS constraint_name,
        conrelid::regclass AS table_name,
        pg_get_constraintdef(oid) AS constraint_definition
    FROM pg_constraint
    WHERE conname IN (
        'chk_active_positions_side',
        'chk_active_positions_strategy_type',
        'chk_position_history_side',
        'chk_position_history_strategy_type'
    )
    ORDER BY table_name, constraint_name;
    """
    
    print("\n🔍 Verifying constraints...")
    
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
            print(f"   {row['table_name']}.{row['constraint_name']}")
            print(f"      {row['constraint_definition']}")
        
        # Verify migration was recorded
        migration_check = lambda_client.invoke(
            FunctionName='ops-pipeline-db-query',
            InvocationType='RequestResponse',
            Payload=json.dumps({
                'sql': "SELECT version FROM schema_migrations WHERE version = '2026_02_02_0003_add_constraints_no_do'"
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
        print("\n❌ Verification failed - constraints not found")
        return False


if __name__ == '__main__':
    print("\n🚀 Starting Constraints Migration Application\n")
    
    if apply_migration():
        if verify_migration():
            print("\n" + "=" * 80)
            print("✅ Constraints Migration Complete!")
            print("=" * 80)
            print("\nConstraints Added:")
            print("1. active_positions.side CHECK (side IN ('long', 'short'))")
            print("2. active_positions.strategy_type CHECK (strategy_type IN (...))")
            print("3. position_history.side CHECK (side IN ('long', 'short'))")
            print("4. position_history.strategy_type CHECK (strategy_type IN (...))")
            print("\nNote: Constraints are NOT VALID (won't check existing data)")
            sys.exit(0)
        else:
            print("\n⚠️ Migration applied but verification failed")
            sys.exit(1)
    else:
        print("\n❌ Migration failed")
        sys.exit(1)
