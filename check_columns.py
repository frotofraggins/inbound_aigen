#!/usr/bin/env python3
"""
Check if account_name columns exist in both tables
"""
import boto3
import json
import psycopg2

# Get DB credentials from SSM
ssm = boto3.client('ssm', region_name='us-west-2')

db_host = ssm.get_parameter(Name='/ops-pipeline/db_host')['Parameter']['Value']
db_name = ssm.get_parameter(Name='/ops-pipeline/db_name')['Parameter']['Value']
db_user = ssm.get_parameter(Name='/ops-pipeline/db_user')['Parameter']['Value']
db_password = ssm.get_parameter(Name='/ops-pipeline/db_password', WithDecryption=True)['Parameter']['Value']

# Connect to database
conn = psycopg2.connect(
    host=db_host,
    database=db_name,
    user=db_user,
    password=db_password
)

cur = conn.cursor()

# Check active_positions
print("Checking active_positions table...")
cur.execute("""
    SELECT column_name, data_type, is_nullable, column_default
    FROM information_schema.columns
    WHERE table_name = 'active_positions' AND column_name = 'account_name'
""")
result = cur.fetchone()
if result:
    print(f"✅ active_positions.account_name exists: {result}")
else:
    print("❌ active_positions.account_name does NOT exist")

# Check dispatch_executions
print("\nChecking dispatch_executions table...")
cur.execute("""
    SELECT column_name, data_type, is_nullable, column_default
    FROM information_schema.columns
    WHERE table_name = 'dispatch_executions' AND column_name = 'account_name'
""")
result = cur.fetchone()
if result:
    print(f"✅ dispatch_executions.account_name exists: {result}")
else:
    print("❌ dispatch_executions.account_name does NOT exist")

conn.close()
