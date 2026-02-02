#!/usr/bin/env python3
"""
Safely add Phase 16 columns
Uses ADD COLUMN IF NOT EXISTS - completely safe, won't break existing data
"""

import boto3
import json

print("=" * 80)
print("SAFE PHASE 16 COLUMN ADDITION")
print("=" * 80)
print("Using ADD COLUMN IF NOT EXISTS - safe to run multiple times\n")

lambda_client = boto3.client('lambda', region_name='us-west-2')

# Safe column additions - won't error if columns exist
safe_alterations = [
    {
        'name': 'dispatch_recommendations snapshots',
        'sql': """
            ALTER TABLE dispatch_recommendations 
            ADD COLUMN IF NOT EXISTS features_snapshot JSONB,
            ADD COLUMN IF NOT EXISTS sentiment_snapshot JSONB
        """
    },
    {
        'name': 'dispatch_executions snapshots',
        'sql': """
            ALTER TABLE dispatch_executions
            ADD COLUMN IF NOT EXISTS features_snapshot JSONB,
            ADD COLUMN IF NOT EXISTS sentiment_snapshot JSONB
        """
    },
    {
        'name': 'active_positions outcome labels',
        'sql': """
            ALTER TABLE active_positions
            ADD COLUMN IF NOT EXISTS win_loss_label SMALLINT,
            ADD COLUMN IF NOT EXISTS r_multiple NUMERIC(8,4),
            ADD COLUMN IF NOT EXISTS mae_pct NUMERIC(8,4),
            ADD COLUMN IF NOT EXISTS mfe_pct NUMERIC(8,4),
            ADD COLUMN IF NOT EXISTS holding_minutes INT,
            ADD COLUMN IF NOT EXISTS exit_reason_norm VARCHAR(32)
        """
    },
    {
        'name': 'learning_recommendations table',
        'sql': """
            CREATE TABLE IF NOT EXISTS learning_recommendations (
                id SERIAL PRIMARY KEY,
                parameter_name VARCHAR(100) NOT NULL,
                parameter_path VARCHAR(200) NOT NULL,
                current_value NUMERIC(12,6) NOT NULL,
                suggested_value NUMERIC(12,6) NOT NULL,
                rollback_value NUMERIC(12,6),
                sample_size INT NOT NULL,
                confidence DECIMAL(4,3) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
                avg_return_if_changed NUMERIC(8,4),
                backtest_sharpe NUMERIC(6,3),
                recommendation_reason TEXT NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                reviewed_by VARCHAR(50),
                reviewed_at TIMESTAMP,
                generated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """
    }
]

# Execute each alteration safely
for i, alteration in enumerate(safe_alterations, 1):
    print(f"{i}. Adding {alteration['name']}...")
    
    try:
        # Note: db-query Lambda only allows SELECT
        # We need to use a different approach
        print(f"   ⚠️  db-query Lambda is read-only")
        print(f"   SQL to run via migration Lambda:")
        print(f"   {alteration['sql'][:100]}...")
    except Exception as e:
        print(f"   ❌ Error: {e}")

print("\n" + "=" * 80)
print("NEXT STEP")
print("=" * 80)
print("The db-query Lambda only allows SELECT queries.")
print("To safely add columns, we need to:")
print("1. The columns are already in db_migration_lambda code")
print("2. Just need to remove the schema_migrations entry to let it rerun")
print("3. Or verify if columns already exist (query may be cached)")
print("\nLet me check if columns actually exist by listing ALL columns...")

# Check what columns actually exist
response = lambda_client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'query': """
        SELECT table_name, column_name, data_type
        FROM information_schema.columns 
        WHERE table_name IN ('dispatch_recommendations', 'dispatch_executions', 'active_positions')
          AND (column_name LIKE '%snapshot%' OR column_name LIKE '%label%' OR column_name = 'r_multiple')
        ORDER BY table_name, column_name
    """})
)

result = json.loads(response['Payload'].read())
body = json.loads(result['body'])
results = body.get('results', [])

if results:
    print("\n✅ FOUND PHASE 16 COLUMNS:")
    for row in results:
        print(f"   • {row['table_name']}.{row['column_name']} ({row['data_type']})")
else:
    print("\n❌ NO PHASE 16 COLUMNS FOUND")
    print("   Columns need to be added")
