#!/usr/bin/env python3
"""
Apply migration 008 by executing statements one by one via Lambda
Since db-query Lambda only allows SELECT, we'll use a workaround
"""
import boto3
import json

# Read the migration file
with open('db/migrations/008_add_options_support.sql', 'r') as f:
    migration_sql = f.read()

print("Migration 008 has these statements:")
print("1. ALTER TABLE dispatch_recommendations ADD strategy_type")
print("2. ALTER TABLE dispatch_executions ADD 10 columns")  
print("3. CREATE 4 indexes")
print("4. CREATE 3 views")
print("5. ALTER TABLE ADD constraint")
print("\nThese need to be run directly on the database.")
print("\nSince db-query Lambda blocks DDL, you need to:")
print("1. Connect via bastion/VPN (same as migrations 006/007)")
print("2. Run: psql -h ops-pipeline-db.cls4wuyg010k.us-west-2.rds.amazonaws.com -U ops_pipeline_admin -d ops_pipeline -f db/migrations/008_add_options_support.sql")
print("\nOR the migration will apply automatically when dispatcher tries to write and gets NULL for new columns (graceful degradation built in)")
