#!/usr/bin/env python3
"""
Apply Behavior Learning Migration (2026_02_02_0001_position_telemetry)
Uses ops-pipeline-db-migration Lambda for DDL statements
"""

import boto3
import json
import sys

def apply_migration():
    """Apply migration via db-migration Lambda"""
    
    # Read migration SQL
    print("Reading migration file...")
    with open('db/migrations/2026_02_02_0001_position_telemetry.sql', 'r') as f:
        migration_sql = f.read()
    
    print(f"Migration SQL size: {len(migration_sql)} bytes")
    print()
    
    # Invoke Lambda with correct payload format
    client = boto3.client('lambda', region_name='us-west-2')
    
    payload = {
        'migration_sql': migration_sql,
        'migration_name': '2026_02_02_0001_position_telemetry'
    }
    
    print("Applying Migration: 2026_02_02_0001_position_telemetry")
    print("- Adding execution_uuid to active_positions")
    print("- Adding entry_features_json and telemetry fields")
    print("- Adding MFE/MAE tracking columns")
    print("- Creating position_history table")
    print("- Adding constraints (NOT VALID)")
    print()
    print("Invoking ops-pipeline-db-migration Lambda...")
    
    try:
        response = client.invoke(
            FunctionName='ops-pipeline-db-migration',
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        
        # Parse response
        response_payload = json.loads(response['Payload'].read())
        
        print(f"Lambda StatusCode: {response['StatusCode']}")
        print(f"Response: {json.dumps(response_payload, indent=2)}")
        print()
        
        # Check HTTP status code
        if response['StatusCode'] != 200:
            print(f"❌ Lambda invocation failed with HTTP status {response['StatusCode']}")
            return False
        
        # Check for Lambda execution errors (FunctionError in response metadata)
        if 'FunctionError' in response:
            print(f"❌ Lambda execution error: {response['FunctionError']}")
            return False
        
        # Check for errorMessage in payload (unhandled exceptions)
        if 'errorMessage' in response_payload:
            print(f"❌ Migration failed: {response_payload['errorMessage']}")
            if 'errorType' in response_payload:
                print(f"   Error type: {response_payload['errorType']}")
            return False
        
        # Parse body and check success flag
        if 'statusCode' in response_payload:
            if response_payload['statusCode'] != 200:
                print(f"❌ Lambda returned non-200 status: {response_payload['statusCode']}")
                return False
        
        if 'body' in response_payload:
            body = json.loads(response_payload['body'])
            if not body.get('success'):
                print(f"❌ Migration failed: {body.get('error', 'Unknown error')}")
                return False
        
        # Verify migration was recorded in schema_migrations
        print("Verifying migration was recorded...")
        verify_client = boto3.client('lambda', region_name='us-west-2')
        verify_response = verify_client.invoke(
            FunctionName='ops-pipeline-db-query',
            InvocationType='RequestResponse',
            Payload=json.dumps({
                'sql': "SELECT version FROM schema_migrations WHERE version = '2026_02_02_0001_position_telemetry'"
            })
        )
        
        verify_payload = json.loads(verify_response['Payload'].read())
        verify_body = json.loads(verify_payload.get('body', '{}'))
        
        if not verify_body.get('rows') or len(verify_body['rows']) == 0:
            print("❌ Migration not found in schema_migrations table!")
            return False
        
        print("✅ Migration applied successfully!")
        print("✅ Migration verified in schema_migrations table")
        print()
        print("Next steps:")
        print("1. Run check_migration_status.py to verify schema changes")
        print("2. Update spec/behavior_learning_mode/TASKS.md")
        print("3. System is now ready for behavior learning mode")
        return True
            
    except Exception as e:
        print(f"❌ Error invoking Lambda: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = apply_migration()
    sys.exit(0 if success else 1)
