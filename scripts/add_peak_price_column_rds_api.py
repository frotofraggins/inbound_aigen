#!/usr/bin/env python3
"""
Add peak_price column using RDS Data API (if available)
"""
import boto3
import json

print("🔧 Adding peak_price column via RDS Data API")

# Try RDS Data API
rds_data = boto3.client('rds-data', region_name='us-west-2')

# Get DB cluster ARN (if using Aurora Serverless)
# Otherwise, this won't work

sql = """
ALTER TABLE active_positions 
ADD COLUMN IF NOT EXISTS peak_price DECIMAL(12, 4),
ADD COLUMN IF NOT EXISTS trailing_stop_price DECIMAL(12, 4),
ADD COLUMN IF NOT EXISTS entry_underlying_price DECIMAL(12, 4),
ADD COLUMN IF NOT EXISTS original_quantity INTEGER;
"""

try:
    # This requires Aurora Serverless or RDS with Data API enabled
    # Likely won't work but worth trying
    response = rds_data.execute_statement(
        database='your_db_name',  # Would need actual value
        sql=sql
    )
    print("✅ Migration applied via RDS Data API!")
    print(json.dumps(response, indent=2, default=str))
except Exception as e:
    print(f"❌ RDS Data API not available: {e}")
    print("\nThis is expected if not using Aurora Serverless.")
    print("\nAlternative: Copy this SQL and run via SQL client:")
    print("-" * 60)
    print(sql)
    print("-" * 60)
    print("\nOr wait for machine with direct RDS access to run:")
    print("  python3 scripts/apply_013_direct.py")
