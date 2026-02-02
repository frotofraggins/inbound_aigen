#!/usr/bin/env python3
"""
Run migration 004 to add dispatcher execution tables.
"""
import json
import boto3
import psycopg2
import sys

def get_db_credentials():
    """Fetch DB connection details from AWS."""
    region = 'us-west-2'
    ssm = boto3.client('ssm', region_name=region)
    secrets = boto3.client('secretsmanager', region_name=region)
    
    # Get connection parameters
    db_host = ssm.get_parameter(Name='/ops-pipeline/db_host')['Parameter']['Value']
    db_port = ssm.get_parameter(Name='/ops-pipeline/db_port')['Parameter']['Value']
    db_name = ssm.get_parameter(Name='/ops-pipeline/db_name')['Parameter']['Value']
    
    # Get credentials
    secret_value = secrets.get_secret_value(SecretId='ops-pipeline/db')
    secret_data = json.loads(secret_value['SecretString'])
    
    return {
        'host': db_host,
        'port': int(db_port),
        'database': db_name,
        'user': secret_data['username'],
        'password': secret_data['password']
    }

def run_migration():
    """Execute migration 004."""
    print("Fetching DB credentials...")
    creds = get_db_credentials()
    
    print(f"Connecting to {creds['host']}:{creds['port']}/{creds['database']}...")
    conn = psycopg2.connect(**creds)
    conn.autocommit = False
    
    try:
        cur = conn.cursor()
        
        # Read migration file
        print("Reading migration file...")
        with open('db/migrations/004_add_dispatcher_execution.sql', 'r') as f:
            migration_sql = f.read()
        
        print("Executing migration 004...")
        cur.execute(migration_sql)
        
        # Record in migrations table
        cur.execute("""
            INSERT INTO schema_migrations (version, name, applied_at)
            VALUES (4, 'add_dispatcher_execution', NOW())
            ON CONFLICT (version) DO NOTHING
        """)
        
        conn.commit()
        print("✅ Migration 004 completed successfully!")
        
        # Verify tables were created
        cur.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('dispatch_executions', 'dispatcher_runs')
            ORDER BY table_name
        """)
        tables = cur.fetchall()
        print(f"\nVerified tables: {[t[0] for t in tables]}")
        
        cur.close()
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Migration failed: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == '__main__':
    run_migration()
