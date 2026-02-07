#!/usr/bin/env python3
"""
Emergency fix for Position Manager
1. Add missing original_quantity column
2. Fix type error in monitor.py
"""
import boto3
import json
import psycopg2

# Get DB credentials
secrets = boto3.client('secretsmanager', region_name='us-west-2')
secret = secrets.get_secret_value(SecretId='ops-pipeline/db')
creds = json.loads(secret['SecretString'])

# Connect to database
conn = psycopg2.connect(
    host='ops-pipeline-db.cls4wuyg010k.us-west-2.rds.amazonaws.com',
    port=creds.get('port', 5432),
    dbname='ops_pipeline',
    user=creds['username'],
    password=creds['password']
)

cur = conn.cursor()

print("Checking for missing columns...")

# Check if original_quantity exists
cur.execute("""
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_name = 'active_positions' 
    AND column_name = 'original_quantity'
""")

if not cur.fetchone():
    print("Adding original_quantity column...")
    cur.execute("""
        ALTER TABLE active_positions 
        ADD COLUMN original_quantity INTEGER
    """)
    conn.commit()
    print("✓ Added original_quantity column")
else:
    print("✓ original_quantity column already exists")

# Check for other Phase 3 columns
for col in ['peak_price', 'trailing_stop_price', 'entry_underlying_price']:
    cur.execute(f"""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'active_positions' 
        AND column_name = '{col}'
    """)
    
    if not cur.fetchone():
        print(f"Adding {col} column...")
        cur.execute(f"""
            ALTER TABLE active_positions 
            ADD COLUMN {col} DECIMAL(12, 4)
        """)
        conn.commit()
        print(f"✓ Added {col} column")
    else:
        print(f"✓ {col} column already exists")

print("\nAll columns fixed!")

cur.close()
conn.close()
