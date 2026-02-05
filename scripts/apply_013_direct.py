#!/usr/bin/env python3
"""
Apply migration 013 directly - adds trailing stops columns
Based on successful add_columns_direct.py approach
"""
import boto3
import json
import psycopg2

print("🔧 Applying Migration 013: Trailing Stops Support")
print("=" * 60)

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
print("✓ Connected!\n")

# Step 1: Add columns to active_positions
print("Step 1: Adding columns to active_positions...")
columns_to_add = [
    ('peak_price', 'DECIMAL(12, 4)'),
    ('trailing_stop_price', 'DECIMAL(12, 4)'),
    ('entry_underlying_price', 'DECIMAL(12, 4)'),
    ('original_quantity', 'INTEGER')
]

for col_name, col_type in columns_to_add:
    try:
        cur.execute(f"""
            ALTER TABLE active_positions 
            ADD COLUMN IF NOT EXISTS {col_name} {col_type}
        """)
        conn.commit()
        print(f"  ✓ {col_name} ({col_type})")
    except Exception as e:
        print(f"  ✗ {col_name} failed: {e}")
        conn.rollback()

# Step 2: Add iv_rank to ticker_features
print("\nStep 2: Adding iv_rank to ticker_features_1m...")
try:
    cur.execute("""
        ALTER TABLE ticker_features_1m
        ADD COLUMN IF NOT EXISTS iv_rank DECIMAL(5, 4)
    """)
    conn.commit()
    print("  ✓ iv_rank added")
except Exception as e:
    print(f"  ✗ iv_rank failed: {e}")
    conn.rollback()

# Step 3: Create iv_history table
print("\nStep 3: Creating iv_history table...")
try:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS iv_history (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(10) NOT NULL,
            implied_volatility DECIMAL(8, 6),
            recorded_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(ticker, recorded_at)
        )
    """)
    conn.commit()
    print("  ✓ iv_history table created")
except Exception as e:
    print(f"  ✗ iv_history failed: {e}")
    conn.rollback()

# Step 4: Create index
print("\nStep 4: Creating index on iv_history...")
try:
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_iv_history_ticker_date 
        ON iv_history(ticker, recorded_at DESC)
    """)
    conn.commit()
    print("  ✓ Index created")
except Exception as e:
    print(f"  ✗ Index failed: {e}")
    conn.rollback()

# Step 5: Add partial exit columns to position_events
print("\nStep 5: Adding partial exit tracking to position_events...")
partial_cols = [
    ('partial_quantity', 'INTEGER'),
    ('remaining_quantity', 'INTEGER')
]

for col_name, col_type in partial_cols:
    try:
        cur.execute(f"""
            ALTER TABLE position_events
            ADD COLUMN IF NOT EXISTS {col_name} {col_type}
        """)
        conn.commit()
        print(f"  ✓ {col_name}")
    except Exception as e:
        print(f"  ✗ {col_name} failed: {e}")
        conn.rollback()

# Verify
print("\n" + "=" * 60)
print("VERIFICATION")
print("=" * 60)

cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'active_positions' 
    AND column_name IN ('peak_price', 'trailing_stop_price', 'entry_underlying_price', 'original_quantity')
    ORDER BY column_name
""")

print("\nColumns in active_positions:")
for row in cur.fetchall():
    print(f"  ✓ {row[0]}: {row[1]}")

cur.close()
conn.close()

print("\n" + "=" * 60)
print("✅ MIGRATION 013 COMPLETE!")
print("=" * 60)
print("\nTrailing stops can now be enabled!")
print("\nNext step:")
print("  Edit services/position_manager/monitor.py line 394")
print("  Remove: return None")
print("  Then: Rebuild and deploy")
