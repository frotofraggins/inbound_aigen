#!/bin/bash
# Enable Trailing Stops Feature
# 1. Apply migration 013 (adds peak_price column)
# 2. Enable trailing stops in monitor.py
# 3. Rebuild and deploy position manager

set -e

echo "🔧 Enabling Trailing Stops Feature"
echo "This addresses the 'exit at bad timing' problem"
echo ""

# Step 1: Check if migration 013 is already applied
echo "Step 1: Checking if migration 013 applied..."

# We'll apply it via direct SQL since we can't easily check
# The migration uses IF NOT EXISTS so it's safe to run multiple times

echo "Step 2: Applying migration 013..."
echo "Note: Uses IF NOT EXISTS, safe to run even if already applied"

# Apply migration using AWS RDS Data API or direct connection
# For now, create a Python script to apply it

cat > /tmp/apply_migration_013.py << 'EOF'
import boto3
import psycopg2
import json

# Get DB credentials
secrets = boto3.client('secretsmanager', region_name='us-west-2')
db_secret = secrets.get_secret_value(SecretId='ops-pipeline/db')
secret_data = json.loads(db_secret['SecretString'])

ssm = boto3.client('ssm', region_name='us-west-2')
response = ssm.get_parameters_by_path(Path='/ops-pipeline/db', WithDecryption=True)
param_dict = {p['Name'].split('/')[-1]: p['Value'] for p in response['Parameters']}

# Read migration file
with open('db/migrations/013_phase3_improvements.sql', 'r') as f:
    migration_sql = f.read()

# Connect and apply
conn = psycopg2.connect(
    host=param_dict.get('host', param_dict.get('endpoint', '')),
    port=int(param_dict.get('port', 5432)),
    dbname=param_dict.get('name', param_dict.get('database', '')),
    user=secret_data['username'],
    password=secret_data['password']
)

cur = conn.cursor()
cur.execute(migration_sql)
conn.commit()
cur.close()
conn.close()

print("✅ Migration 013 applied successfully")
EOF

python3 /tmp/apply_migration_013.py

echo ""
echo "✅ Migration 013 applied (adds peak_price, trailing_stop_price columns)"
echo ""

# Step 3: Enable trailing stops in monitor.py
echo "Step 3: Enabling trailing stops in monitor.py..."
echo "This will be done manually - see instructions below"
echo ""

echo "=" * 80
echo "MANUAL STEP REQUIRED:"
echo "=" * 80
echo ""
echo "Edit services/position_manager/monitor.py:"
echo "Find line ~380 with:"
echo '  # TODO: Re-enable after running migration 013'
echo '  return None'
echo ""
echo "Change to:"
echo '  # Enabled 2026-02-04 - trailing stops active'
echo '  # (remove or comment the return None line)'
echo ""
echo "This will activate trailing stops that:"
echo "- Lock in 75% of peak gains"
echo "- Exit when price drops 25% from peak"
echo "- Solve the 'exit at bad timing' problem"
echo ""
echo "Then run:"
echo "  ./scripts/rebuild_and_deploy_position_manager.sh"
echo ""
