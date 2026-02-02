#!/usr/bin/env python3
"""
Direct test of Phase 16 columns
Checks if columns were actually added
"""

import boto3
import json

print("Phase 16 Column Verification Test")
print("=" * 80)

lambda_client = boto3.client('lambda', region_name='us-west-2')

# Test 1: Check all columns on dispatch_recommendations
print("\n1. dispatch_recommendations columns:")
response = lambda_client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'query': """
        SELECT column_name, data_type
        FROM information_schema.columns 
        WHERE table_name = 'dispatch_recommendations'
        ORDER BY ordinal_position
    """})
)
result = json.loads(response['Payload'].read())
body = json.loads(result['body'])
columns = body.get('results', [])

has_features = any(c['column_name'] == 'features_snapshot' for c in columns)
has_sentiment = any(c['column_name'] == 'sentiment_snapshot' for c in columns)

for col in columns:
    marker = " 🆕" if col['column_name'] in ('features_snapshot', 'sentiment_snapshot') else ""
    print(f"   {col['column_name']}: {col['data_type']}{marker}")

print(f"\n   ✅ features_snapshot: {has_features}")
print(f"   ✅ sentiment_snapshot: {has_sentiment}")

# Test 2: Check learning_recommendations table
print("\n2. learning_recommendations table:")
response = lambda_client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'query': """
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_name = 'learning_recommendations'
    """})
)
result = json.loads(response['Payload'].read())
body = json.loads(result['body'])
exists = len(body.get('results', [])) > 0

print(f"   {'✅' if exists else '❌'} Table exists: {exists}")

# Test 3: Check active_positions outcome columns
print("\n3. active_positions outcome columns:")
response = lambda_client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'query': """
        SELECT column_name
        FROM information_schema.columns 
        WHERE table_name = 'active_positions'
          AND column_name IN ('win_loss_label', 'r_multiple', 'mae_pct', 'mfe_pct', 'holding_minutes', 'exit_reason_norm')
        ORDER BY column_name
    """})
)
result = json.loads(response['Payload'].read())
body = json.loads(result['body'])
outcome_cols = body.get('results', [])

for col in outcome_cols:
    print(f"   ✅ {col['column_name']}")

print(f"\n   Total outcome columns: {len(outcome_cols)}/6")

# Test 4: Check schema_migrations
print("\n4. schema_migrations table:")
response = lambda_client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'query': """
        SELECT version, applied_at 
        FROM schema_migrations 
        WHERE version IN ('010_add_ai_learning_tables', '011_add_learning_infrastructure')
        ORDER BY version
    """})
)
result = json.loads(response['Payload'].read())
body = json.loads(result['body'])
migrations = body.get('results', [])

for mig in migrations:
    print(f"   ✅ {mig['version']}: {mig['applied_at'][:19]}")

# Summary
print("\n" + "=" * 80)
print("PHASE 16 VERIFICATION SUMMARY")
print("=" * 80)

if has_features and has_sentiment and exists and len(outcome_cols) == 6:
    print("✅ ALL Phase 16 schema changes verified!")
    print("   Next: Wait for signal engine to generate recommendation with snapshots")
elif has_features and has_sentiment:
    print("⚠️  Partial success - snapshot columns exist!")
    print(f"   Missing: {6 - len(outcome_cols)} outcome columns")
elif exists:
    print("⚠️  learning_recommendations table exists but snapshot columns missing")
    print("   Migration may need manual column add")
else:
    print("❌ Migration 011 did not apply correctly")
    print("   Need to investigate why columns weren't added")
