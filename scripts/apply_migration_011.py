#!/usr/bin/env python3
"""
Apply Migration 011 via Lambda
Adds learning infrastructure: feature snapshots + normalized outcomes
"""

import boto3
import json
import sys

def apply_migration_011():
    """Apply Migration 011 via DB Migration Lambda"""
    
    # Read migration SQL (handle path from scripts/ directory)
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    migration_path = os.path.join(script_dir, '..', 'db', 'migrations', '011_add_learning_infrastructure.sql')
    
    with open(migration_path, 'r') as f:
        migration_sql = f.read()
    
    # Create Lambda payload
    payload = {
        'migration_sql': migration_sql,
        'migration_version': 11,
        'migration_name': 'add_learning_infrastructure'
    }
    
    # Invoke Lambda
    lambda_client = boto3.client('lambda', region_name='us-west-2')
    
    print("Applying Migration 011 via Lambda...")
    print(f"Migration size: {len(migration_sql)} bytes")
    print()
    
    try:
        response = lambda_client.invoke(
            FunctionName='ops-pipeline-db-migration',
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        
        result = json.loads(response['Payload'].read())
        
        if response['StatusCode'] == 200:
            print("✅ Migration 011 applied successfully!")
            print()
            print("Response:", json.dumps(result, indent=2))
            return True
        else:
            print(f"❌ Migration failed with status {response['StatusCode']}")
            print("Response:", json.dumps(result, indent=2))
            return False
            
    except Exception as e:
        print(f"❌ Error applying migration: {e}")
        return False

if __name__ == "__main__":
    success = apply_migration_011()
    sys.exit(0 if success else 1)
