#!/usr/bin/env python3
"""
Database Migration Runner for ops-pipeline
Applies SQL migrations idempotently with transaction safety
"""

import json
import os
import sys
import boto3
import psycopg2
from psycopg2 import sql
from pathlib import Path
from datetime import datetime

def log(event, **kwargs):
    """Structured JSON logging"""
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "event": event,
        **kwargs
    }
    print(json.dumps(log_entry), flush=True)

def get_db_config():
    """Load database configuration from AWS services"""
    log("config_load_start", message="Loading configuration from AWS")
    
    # Initialize AWS clients
    ssm = boto3.client('ssm', region_name='us-west-2')
    secrets = boto3.client('secretsmanager', region_name='us-west-2')
    
    try:
        # Read SSM parameters
        log("ssm_read_start")
        db_host = ssm.get_parameter(Name='/ops-pipeline/db_host')['Parameter']['Value']
        db_port = ssm.get_parameter(Name='/ops-pipeline/db_port')['Parameter']['Value']
        db_name = ssm.get_parameter(Name='/ops-pipeline/db_name')['Parameter']['Value']
        
        log("ssm_read_success", db_host=db_host, db_port=db_port, db_name=db_name)
        
        # Read Secrets Manager
        log("secrets_read_start")
        secret_value = secrets.get_secret_value(SecretId='ops-pipeline/db')
        secret_data = json.loads(secret_value['SecretString'])
        
        db_user = secret_data['username']
        db_password = secret_data['password']
        
        log("secrets_read_success", username=db_user)
        
        return {
            'host': db_host,
            'port': int(db_port),
            'database': db_name,
            'user': db_user,
            'password': db_password
        }
    except Exception as e:
        log("config_load_failed", error=str(e), error_type=type(e).__name__)
        raise

def connect_db(config):
    """Establish database connection"""
    log("db_connect_start", host=config['host'], database=config['database'])
    
    try:
        conn = psycopg2.connect(
            host=config['host'],
            port=config['port'],
            database=config['database'],
            user=config['user'],
            password=config['password'],
            connect_timeout=10
        )
        log("db_connect_success")
        return conn
    except Exception as e:
        log("db_connect_failed", error=str(e), error_type=type(e).__name__)
        raise

def ensure_migration_table(conn):
    """Create schema_migrations table if it doesn't exist"""
    log("migration_table_check")
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            conn.commit()
        
        log("migration_table_ready")
    except Exception as e:
        log("migration_table_failed", error=str(e))
        raise

def get_applied_migrations(conn):
    """Get list of already applied migrations"""
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT version FROM schema_migrations ORDER BY version")
            applied = [row[0] for row in cursor.fetchall()]
        
        log("applied_migrations_fetched", count=len(applied), versions=applied)
        return set(applied)
    except Exception as e:
        log("applied_migrations_fetch_failed", error=str(e))
        raise

def apply_migration(conn, migration_file):
    """Apply a single migration file within a transaction"""
    version = migration_file.stem  # e.g., "001_init"
    
    log("migration_start", version=version, file=str(migration_file))
    
    try:
        # Read migration SQL
        with open(migration_file, 'r') as f:
            migration_sql = f.read()
        
        log("migration_sql_loaded", version=version, size_bytes=len(migration_sql))
        
        # Apply migration in transaction
        with conn.cursor() as cursor:
            # Execute the migration SQL
            cursor.execute(migration_sql)
            
            # Record migration as applied
            cursor.execute(
                "INSERT INTO schema_migrations (version) VALUES (%s) ON CONFLICT (version) DO NOTHING",
                (version,)
            )
            
            conn.commit()
        
        log("migration_success", version=version)
        return True
        
    except Exception as e:
        conn.rollback()
        log("migration_failed", version=version, error=str(e), error_type=type(e).__name__)
        raise

def run_migrations(migrations_dir='/migrations'):
    """Main migration runner"""
    log("migrator_start", migrations_dir=migrations_dir)
    
    try:
        # Load configuration
        config = get_db_config()
        
        # Connect to database
        conn = connect_db(config)
        
        # Ensure migration tracking table exists
        ensure_migration_table(conn)
        
        # Get already applied migrations
        applied_migrations = get_applied_migrations(conn)
        
        # Find migration files
        migrations_path = Path(migrations_dir)
        if not migrations_path.exists():
            log("migrations_dir_not_found", path=str(migrations_path))
            sys.exit(1)
        
        migration_files = sorted(migrations_path.glob('*.sql'))
        log("migrations_discovered", count=len(migration_files), files=[f.name for f in migration_files])
        
        if not migration_files:
            log("no_migrations_found")
            sys.exit(1)
        
        # Apply pending migrations
        applied_count = 0
        skipped_count = 0
        
        for migration_file in migration_files:
            version = migration_file.stem
            
            if version in applied_migrations:
                log("migration_skip", version=version, reason="already_applied")
                skipped_count += 1
                continue
            
            apply_migration(conn, migration_file)
            applied_count += 1
        
        # Close connection
        conn.close()
        
        log("migrator_complete", 
            applied=applied_count, 
            skipped=skipped_count, 
            total=len(migration_files))
        
        # Exit with success
        sys.exit(0)
        
    except Exception as e:
        log("migrator_failed", error=str(e), error_type=type(e).__name__)
        sys.exit(1)

if __name__ == '__main__':
    run_migrations()
