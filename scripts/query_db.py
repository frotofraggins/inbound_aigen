#!/usr/bin/env python3
"""Quick script to query the database"""
import json
import boto3
import psycopg2

def get_db_connection():
    """Get database connection from AWS"""
    ssm = boto3.client('ssm', region_name='us-west-2')
    secrets = boto3.client('secretsmanager', region_name='us-west-2')
    
    db_host = ssm.get_parameter(Name='/ops-pipeline/db_host')['Parameter']['Value']
    db_port = ssm.get_parameter(Name='/ops-pipeline/db_port')['Parameter']['Value']
    db_name = ssm.get_parameter(Name='/ops-pipeline/db_name')['Parameter']['Value']
    
    secret_value = secrets.get_secret_value(SecretId='ops-pipeline/db')
    secret_data = json.loads(secret_value['SecretString'])
    
    return psycopg2.connect(
        host=db_host,
        port=int(db_port),
        database=db_name,
        user=secret_data['username'],
        password=secret_data['password']
    )

conn = get_db_connection()
cursor = conn.cursor()

print("\n=== Database Summary ===")
cursor.execute("SELECT COUNT(*) as total_events, MAX(fetched_at) as latest_fetch, MIN(fetched_at) as earliest_fetch FROM inbound_events_raw")
row = cursor.fetchone()
print(f"Total events: {row[0]}")
print(f"Latest fetch: {row[1]}")
print(f"Earliest fetch: {row[2]}")

print("\n=== Recent Events (Top 10) ===")
cursor.execute("SELECT id, source, title, fetched_at FROM inbound_events_raw ORDER BY fetched_at DESC LIMIT 10")
for row in cursor.fetchall():
    print(f"ID: {row[0]}, Source: {row[1][:40]}, Title: {row[2][:60]}, Fetched: {row[3]}")

cursor.close()
conn.close()
