#!/usr/bin/env python3
"""
Run database migration 002
Adds lane_features table for volatility and technical indicators
"""
import json
import boto3
import psycopg2

# Get DB config from AWS
ssm = boto3.client('ssm', region_name='us-west-2')
secrets = boto3.client('secretsmanager', region_name='us-west-2')

db_host = ssm.get_parameter(Name='/ops-pipeline/db_host')['Parameter']['Value']
db_port = ssm.get_parameter(Name='/ops-pipeline/db_port')['Parameter']['Value']
db_name = ssm.get_parameter(Name='/ops-pipeline/db_name')['Parameter']['Value']

secret_value = secrets.get_secret_value(SecretId='ops-pipeline/db')
secret_data = json.loads(secret_value['SecretString'])

# Connect to database
print(f"Connecting to {db_host}...")
conn = psycopg2.connect(
    host=db_host,
    port=int(db_port),
    database=db_name,
    user=secret_data['username'],
    password=secret_data['password']
)

# Read and execute migration
print("Reading migration 002...")
with open('db/migrations/002_add_volatility_features.sql', 'r') as f:
    migration_sql = f.read()

print("Applying migration...")
with conn.cursor() as cursor:
    cursor.execute(migration_sql)
    conn.commit()

print("Migration 002 applied successfully!")

# Verify
with conn.cursor() as cursor:
    cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"Tables: {tables}")
    
    cursor.execute("SELECT version FROM schema_migrations ORDER BY applied_at")
    migrations = [row[0] for row in cursor.fetchall()]
    print(f"Applied migrations: {migrations}")

conn.close()
print("Done!")
