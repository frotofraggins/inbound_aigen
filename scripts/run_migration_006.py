#!/usr/bin/env python3
"""Run migration 006 to fix dispatcher status constraint"""

import json
import boto3

def run_migration():
    # Read migration SQL
    with open('db/migrations/006_fix_dispatcher_status_constraint.sql', 'r') as f:
        sql = f.read()
    
    # Invoke migration lambda
    client = boto3.client('lambda', region_name='us-west-2')
    
    payload = {
        'migration_sql': sql,
        'migration_name': '006_fix_dispatcher_status_constraint'
    }
    
    print("Invoking migration lambda...")
    response = client.invoke(
        FunctionName='ops-pipeline-db-migrator',
        InvocationType='RequestResponse',
        Payload=json.dumps(payload)
    )
    
    result = json.loads(response['Payload'].read())
    print(json.dumps(result, indent=2))
    
    if result.get('statusCode') == 200:
        body = json.loads(result.get('body', '{}'))
        if body.get('success'):
            print("\n✅ Migration 006 completed successfully")
            return True
        else:
            print(f"\n❌ Migration failed: {body.get('error')}")
            return False
    else:
        print(f"\n❌ Lambda invocation failed: {result}")
        return False

if __name__ == '__main__':
    success = run_migration()
    exit(0 if success else 1)
