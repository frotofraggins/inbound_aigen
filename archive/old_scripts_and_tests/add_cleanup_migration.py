#!/usr/bin/env python3
"""
Add phantom position cleanup as a one-time migration to the Lambda.
This modifies the Lambda function code to include the cleanup migration.
"""

import json

# The cleanup migration
CLEANUP_MIGRATION = """
    '999_cleanup_phantom_positions': \"\"\"
-- Migration 999: One-time cleanup of phantom positions
-- These positions don't exist in Alpaca but are still open in database

UPDATE active_positions
SET 
    status = 'closed',
    close_reason = 'manual_reconciliation',
    closed_at = NOW(),
    exit_price = entry_price,
    current_pnl_dollars = 0,
    current_pnl_percent = 0
WHERE id IN (21, 16, 19, 24, 13, 37, 36)
AND status IN ('open', 'closing');

INSERT INTO schema_migrations (version) VALUES ('999_cleanup_phantom_positions') ON CONFLICT (version) DO NOTHING;
\"\"\",
"""

print("=" * 80)
print("ADD PHANTOM POSITION CLEANUP MIGRATION")
print("=" * 80)
print()
print("This script will show you how to add the cleanup as a migration.")
print()
print("STEPS:")
print()
print("1. Edit services/db_migration_lambda/lambda_function.py")
print()
print("2. Find the MIGRATIONS dictionary (around line 40)")
print()
print("3. Add this migration at the end (before the closing brace):")
print()
print(CLEANUP_MIGRATION)
print()
print("4. Deploy the updated Lambda:")
print()
print("   cd services/db_migration_lambda")
print("   rm -f migration_lambda.zip")
print("   cd package && zip -r ../migration_lambda.zip . && cd ..")
print("   zip migration_lambda.zip lambda_function.py")
print("   aws lambda update-function-code \\")
print("       --function-name ops-pipeline-db-migration \\")
print("       --zip-file fileb://migration_lambda.zip \\")
print("       --region us-west-2")
print()
print("5. Invoke the migration Lambda:")
print()
print("   aws lambda invoke \\")
print("       --function-name ops-pipeline-db-migration \\")
print("       --region us-west-2 \\")
print("       response.json")
print()
print("   cat response.json")
print()
print("=" * 80)
print()
print("ALTERNATIVE: Run SQL directly if you have psql access")
print()
print("See: close_phantom_positions.sql")
print()
