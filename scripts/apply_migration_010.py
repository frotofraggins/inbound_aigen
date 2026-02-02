#!/usr/bin/env python3
"""
Apply Migration 010: AI Learning Tables
"""
import boto3
import json

def apply_migration():
    """Apply migration 010 via Lambda"""
    
    # Read migration SQL
    with open('db/migrations/010_add_ai_learning_tables.sql', 'r') as f:
        migration_sql = f.read()
    
    # Create payload
    payload = {
        'migration_file': '010_add_ai_learning_tables.sql',
        'migration_sql': migration_sql
    }
    
    # Invoke Lambda
    lambda_client = boto3.client('lambda', region_name='us-west-2')
    
    print("Applying migration 010...")
    response = lambda_client.invoke(
        FunctionName='ops-db-migrator',
        InvocationType='RequestResponse',
        Payload=json.dumps(payload)
    )
    
    # Parse response
    result = json.loads(response['Payload'].read())
    print(json.dumps(result, indent=2))
    
    return result

if __name__ == '__main__':
    apply_migration()
