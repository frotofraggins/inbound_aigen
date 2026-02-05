#!/usr/bin/env python3
"""
Check if account_name column exists in dispatch_executions table
"""
import boto3
import json
import psycopg2

def get_db_config():
    """Get database configuration from AWS"""
    region = 'us-west-2'
    ssm = boto3.client('ssm', region_name=region)
    secrets = boto3.client('secretsmanager', region_name=region)
    
    db_host = ssm.get_parameter(Name='/ops-pipeline/db_host')['Parameter']['Value']
    db_port = ssm.get_parameter(Name='/ops-pipeline/db_port')['Parameter']['Value']
    db_name = ssm.get_parameter(Name='/ops-pipeline/db_name')['Parameter']['Value']
    
    secret = secrets.get_secret_value(SecretId='ops-pipeline/db')
    secret_data = json.loads(secret['SecretString'])
    
    return {
        'host': db_host,
        'port': int(db_port),
        'dbname': db_name,
        'user': secret_data['username'],
        'password': secret_data['password']
    }

def main():
    print("Checking for account_name column in dispatch_executions...")
    
    config = get_db_config()
    conn = psycopg2.connect(**config)
    cur = conn.cursor()
    
    # Check if column exists
    cur.execute("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'dispatch_executions'
        AND column_name = 'account_name'
    """)
    
    result = cur.fetchone()
    
    if result:
        print(f"✓ Column exists: {result[0]} ({result[1]}, nullable: {result[2]})")
    else:
        print("✗ Column does NOT exist")
        print("\nAdding account_name column...")
        
        # Add the column with default value 'large'
        cur.execute("""
            ALTER TABLE dispatch_executions
            ADD COLUMN IF NOT EXISTS account_name VARCHAR(50) DEFAULT 'large'
        """)
        conn.commit()
        print("✓ Column added successfully")
        
        # Verify
        cur.execute("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'dispatch_executions'
            AND column_name = 'account_name'
        """)
        result = cur.fetchone()
        print(f"✓ Verified: {result[0]} ({result[1]}, nullable: {result[2]}, default: {result[3]})")
    
    cur.close()
    conn.close()
    print("\nDone!")

if __name__ == '__main__':
    main()
