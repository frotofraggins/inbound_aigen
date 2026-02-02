#!/usr/bin/env python3
"""Directly apply migration 006 to fix dispatcher status constraint"""

import psycopg2
import boto3
import json

def get_db_credentials():
    """Get database credentials from SSM and Secrets Manager"""
    ssm = boto3.client('ssm', region_name='us-west-2')
    secrets = boto3.client('secretsmanager', region_name='us-west-2')
    
    db_host = ssm.get_parameter(Name='/ops-pipeline/db_host')['Parameter']['Value']
    db_port = ssm.get_parameter(Name='/ops-pipeline/db_port')['Parameter']['Value']
    db_name = ssm.get_parameter(Name='/ops-pipeline/db_name')['Parameter']['Value']
    
    secret_value = secrets.get_secret_value(SecretId='ops-pipeline/db')
    secret_data = json.loads(secret_value['SecretString'])
    
    return secret_data['username'], secret_data['password'], db_host, db_port, db_name

def run_migration():
    print("Getting database credentials...")
    db_user, db_pass, db_host, db_port, db_name = get_db_credentials()
    
    print(f"Connecting to database at {db_host}...")
    conn = psycopg2.connect(
        host=db_host,
        port=int(db_port),
        database=db_name,
        user=db_user,
        password=db_pass
    )
    
    try:
        with conn.cursor() as cur:
            print("Dropping old constraint...")
            cur.execute("""
                ALTER TABLE dispatch_recommendations 
                DROP CONSTRAINT IF EXISTS dispatch_recommendations_status_check;
            """)
            
            print("Adding new constraint with all status values...")
            cur.execute("""
                ALTER TABLE dispatch_recommendations
                ADD CONSTRAINT dispatch_recommendations_status_check 
                CHECK (status IN ('PENDING', 'PROCESSING', 'SIMULATED', 'SKIPPED', 'FAILED', 'EXECUTED', 'CANCELLED'));
            """)
            
            print("Adding comment...")
            cur.execute("""
                COMMENT ON COLUMN dispatch_recommendations.status IS 
                'State machine: PENDING → PROCESSING → (SIMULATED | SKIPPED | FAILED | EXECUTED | CANCELLED)';
            """)
            
            conn.commit()
            print("\n✅ Migration 006 applied successfully!")
            return True
            
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Migration failed: {e}")
        return False
    finally:
        conn.close()

if __name__ == '__main__':
    success = run_migration()
    exit(0 if success else 1)
