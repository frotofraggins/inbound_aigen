#!/usr/bin/env python3
"""
Apply Migration 013: Phase 3 Improvements
Adds trailing stops, IV rank, and partial exit support
"""

import boto3
import json
import sys

def apply_migration():
    """Apply migration 013 via Lambda"""
    
    # Read migration SQL
    with open('db/migrations/013_phase3_improvements.sql', 'r') as f:
        migration_sql = f.read()
    
    # Invoke Lambda
    client = boto3.client('lambda', region_name='us-west-2')
    
    payload = {
        'sql': migration_sql
    }
    
    print("Applying Migration 013: Phase 3 Improvements...")
    print("- Adding trailing stop columns")
    print("- Adding IV rank tracking")
    print("- Creating IV history table")
    print("- Adding partial exit support")
    print()
    
    response = client.invoke(
        FunctionName='ops-pipeline-db-query',
        InvocationType='RequestResponse',
        Payload=json.dumps(payload)
    )
    
    result = json.loads(response['Payload'].read())
    
    if response['StatusCode'] == 200:
        print("✅ Migration 013 applied successfully!")
        print()
        print("Verify with:")
        print("  SELECT column_name FROM information_schema.columns")
        print("  WHERE table_name = 'active_positions'")
        print("  AND column_name IN ('peak_price', 'trailing_stop_price');")
        return True
    else:
        print(f"❌ Migration failed: {result}")
        return False

if __name__ == '__main__':
    success = apply_migration()
    sys.exit(0 if success else 1)
