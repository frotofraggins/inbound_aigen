#!/usr/bin/env python3
"""
Add missing columns directly via SSM/Secrets Manager
"""
import boto3
import json
import psycopg2

# Get config from AWS
ssm = boto3.client('ssm', region_name='us-west-2')
secrets = boto3.client('secretsmanager', region_name='us-west-2')

db_host = ssm.get_parameter(Name='/ops-pipeline/db_host')['Parameter']['Value']
db_port = ssm.get_parameter(Name='/ops-pipeline/db_port')['Parameter']['Value']
db_name = ssm.get_parameter(Name='/ops-pipeline/db_name')['Parameter']['Value']

secret_value = secrets.get_secret_value(SecretId='ops-pipeline/db')
secret_data = json.loads(secret_value['SecretString'])

print(f"Connecting to {db_host}:{db_port}/{db_name}...")

# Connect
conn = psycopg2.connect(
    host=db_host,
    port=int(db_port),
    database=db_name,
    user=secret_data['username'],
    password=secret_data['password']
)

cur = conn.cursor()

# Add columns
columns_to_add = [
    ('original_quantity', 'INTEGER'),
    ('peak_price', 'DECIMAL(12, 4)'),
    ('trailing_stop_price', 'DECIMAL(12, 4)'),
    ('entry_underlying_price', 'DECIMAL(12, 4)')
]

for col_name, col_type in columns_to_add:
    try:
        print(f"Adding {col_name}...")
        cur.execute(f"""
            ALTER TABLE active_positions 
            ADD COLUMN IF NOT EXISTS {col_name} {col_type}
        """)
        conn.commit()
        print(f"  ✓ {col_name} added")
    except Exception as e:
        print(f"  ✗ {col_name} failed: {e}")
        conn.rollback()

# Verify
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'active_positions' 
    AND column_name IN ('original_quantity', 'peak_price', 'trailing_stop_price', 'entry_underlying_price')
    ORDER BY column_name
""")

print("\nColumns now in database:")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]}")

cur.close()
conn.close()

print("\n✓ Migration complete!")
