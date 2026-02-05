#!/usr/bin/env python3
"""
Apply Behavior Learning Mode Migration (2026_02_02_0001)
Adds execution_uuid bridge + entry telemetry + position_history
"""

import psycopg2
import boto3
import json
import sys

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
    print("\n" + "="*80)
    print("  BEHAVIOR LEARNING MODE MIGRATION")
    print("="*80 + "\n")
    
    print("1. Getting database credentials...")
    db_user, db_pass, db_host, db_port, db_name = get_db_credentials()
    
    print(f"2. Connecting to database at {db_host}...")
    conn = psycopg2.connect(
        host=db_host,
        port=int(db_port),
        database=db_name,
        user=db_user,
        password=db_pass
    )
    
    try:
        with conn.cursor() as cur:
            print("3. Reading migration SQL...")
            with open('db/migrations/2026_02_02_0001_position_telemetry.sql', 'r') as f:
                migration_sql = f.read()
            
            print("4. Executing migration...")
            print("   - Adding execution_uuid to active_positions")
            print("   - Adding entry telemetry fields (entry_features_json, entry_iv_rank, etc.)")
            print("   - Adding MFE/MAE tracking fields")
            print("   - Creating position_history table")
            print("   - Adding constraints (NOT VALID)")
            
            cur.execute(migration_sql)
            
        conn.commit()
        print("\n✅ Migration applied successfully!")
        
        # Verify tables and columns
        print("\n5. Verifying migration...")
        
        with conn.cursor() as cur:
            # Check active_positions columns
            cur.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'active_positions'
                  AND column_name IN (
                    'execution_uuid', 'entry_features_json', 'entry_iv_rank',
                    'best_unrealized_pnl_pct', 'worst_unrealized_pnl_pct'
                  )
                ORDER BY column_name
            """)
            
            ap_cols = cur.fetchall()
            print(f"\n   active_positions: {len(ap_cols)} new columns")
            for col_name, col_type in ap_cols:
                print(f"     ✓ {col_name}: {col_type}")
            
            # Check position_history table
            cur.execute("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_name = 'position_history'
            """)
            
            ph_exists = cur.fetchone()[0]
            if ph_exists:
                print(f"\n   position_history: ✓ Table created")
                
                cur.execute("""
                    SELECT COUNT(*) FROM information_schema.columns
                    WHERE table_name = 'position_history'
                """)
                col_count = cur.fetchone()[0]
                print(f"     {col_count} columns")
            else:
                print(f"\n   position_history: ✗ Table NOT created")
                return False
            
            # Record migration
            cur.execute("""
                INSERT INTO schema_migrations (version, applied_at)
                VALUES ('2026_02_02_0001_position_telemetry', NOW())
                ON CONFLICT (version) DO NOTHING
            """)
            conn.commit()
            print(f"\n   ✓ Migration recorded in schema_migrations")
        
        print("\n" + "="*80)
        print("  MIGRATION COMPLETE")
        print("="*80 + "\n")
        
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        conn.close()

if __name__ == '__main__':
    success = run_migration()
    sys.exit(0 if success else 1)
