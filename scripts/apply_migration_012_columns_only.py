#!/usr/bin/env python3
"""
Create and apply Migration 012: Just the Phase 16 columns
Safe - uses IF NOT EXISTS, won't break anything
"""

import boto3
import json

# Migration 012: Just add columns, learning_recommendations table already exists
MIGRATION_012 = """
-- Migration 012: Phase 16 Columns Only (learning_recommendations already exists from 011)

-- Add snapshot columns to dispatch_recommendations
ALTER TABLE dispatch_recommendations 
ADD COLUMN IF NOT EXISTS features_snapshot JSONB,
ADD COLUMN IF NOT EXISTS sentiment_snapshot JSONB;

-- Add snapshot columns to dispatch_executions  
ALTER TABLE dispatch_executions
ADD COLUMN IF NOT EXISTS features_snapshot JSONB,
ADD COLUMN IF NOT EXISTS sentiment_snapshot JSONB;

-- Add outcome columns to active_positions
ALTER TABLE active_positions
ADD COLUMN IF NOT EXISTS win_loss_label SMALLINT,
ADD COLUMN IF NOT EXISTS r_multiple NUMERIC(8,4),
ADD COLUMN IF NOT EXISTS mae_pct NUMERIC(8,4),
ADD COLUMN IF NOT EXISTS mfe_pct NUMERIC(8,4),
ADD COLUMN IF NOT EXISTS holding_minutes INT,
ADD COLUMN IF NOT EXISTS exit_reason_norm VARCHAR(32);

-- Add indexes
CREATE INDEX IF NOT EXISTS idx_dispatch_recs_features_gin
    ON dispatch_recommendations USING GIN (features_snapshot);

CREATE INDEX IF NOT EXISTS idx_dispatch_recs_sentiment_gin
    ON dispatch_recommendations USING GIN (sentiment_snapshot);

CREATE INDEX IF NOT EXISTS idx_dispatch_exec_features_gin
    ON dispatch_executions USING GIN (features_snapshot);

CREATE INDEX IF NOT EXISTS idx_dispatch_exec_sentiment_gin
    ON dispatch_executions USING GIN (sentiment_snapshot);

CREATE INDEX IF NOT EXISTS idx_active_positions_win_loss ON active_positions(win_loss_label);
CREATE INDEX IF NOT EXISTS idx_active_positions_r_multiple ON active_positions(r_multiple);

-- Record migration
INSERT INTO schema_migrations (version) VALUES ('012_phase16_columns_only') ON CONFLICT (version) DO NOTHING;
"""

print("=" * 80)
print("APPLYING MIGRATION 012: Phase 16 Columns")
print("=" * 80)
print("Safe - uses IF NOT EXISTS, won't break existing data\n")

lambda_client = boto3.client('lambda', region_name='us-west-2')

# Apply via migration Lambda
payload = {
    'migration_sql': MIGRATION_012,
    'migration_version': 12,
    'migration_name': 'phase16_columns_only'
}

print("Invoking ops-pipeline-db-migration Lambda...")

try:
    response = lambda_client.invoke(
        FunctionName='ops-pipeline-db-migration',
        InvocationType='RequestResponse',
        Payload=json.dumps(payload)
    )
    
    result = json.loads(response['Payload'].read())
    
    if response['StatusCode'] == 200:
        body = json.loads(result['body'])
        
        if body.get('success'):
            print("✅ Migration 012 applied successfully!")
            print(f"\nMigrations applied: {body.get('migrations_applied', [])}")
            print(f"Tables: {len(body.get('tables', []))} total")
        else:
            print(f"❌ Migration failed: {body.get('error', 'Unknown error')}")
    else:
        print(f"❌ Lambda returned status {response['StatusCode']}")
        print(json.dumps(result, indent=2))

except Exception as e:
    print(f"❌ Error: {e}")

print("\n" + "=" * 80)
print("VERIFYING...")
print("=" * 80)

# Verify columns were added
response = lambda_client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'query': """
        SELECT table_name, column_name
        FROM information_schema.columns 
        WHERE table_name IN ('dispatch_recommendations', 'dispatch_executions', 'active_positions')
          AND column_name IN ('features_snapshot', 'sentiment_snapshot', 'win_loss_label', 'r_multiple')
        ORDER BY table_name, column_name
    """})
)

result = json.loads(response['Payload'].read())
body = json.loads(result['body'])
results = body.get('results', [])

if results:
    print(f"✅ Found {len(results)} Phase 16 columns:")
    for row in results:
        print(f"   • {row['table_name']}.{row['column_name']}")
else:
    print("❌ No Phase 16 columns found - migration didn't work")
