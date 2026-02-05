#!/usr/bin/env python3
"""Check if behavior learning migration has been applied"""
import json
import boto3

lambda_client = boto3.client('lambda', region_name='us-west-2')

def query(sql):
    response = lambda_client.invoke(
        FunctionName='ops-pipeline-db-query',
        InvocationType='RequestResponse',
        Payload=json.dumps({"sql": sql})
    )
    result = json.loads(response['Payload'].read())
    body = json.loads(result.get('body', '{}'))
    rows = body.get('rows', [])
    # Debug: print structure of first row if exists
    # if rows and len(rows) > 0:
    #     print(f"DEBUG: First row type: {type(rows[0])}, content: {rows[0]}")
    return rows

print("\n" + "="*80)
print("  BEHAVIOR LEARNING MODE - MIGRATION STATUS CHECK")
print("="*80)

# Check if new columns exist in active_positions
print("\n1. Checking active_positions columns...")
results = query("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'active_positions' 
    AND column_name IN (
        'execution_uuid', 'entry_features_json', 'entry_iv_rank', 'entry_spread_pct',
        'best_unrealized_pnl_pct', 'worst_unrealized_pnl_pct',
        'best_unrealized_pnl_dollars', 'worst_unrealized_pnl_dollars',
        'last_mark_price', 'strategy_type', 'side', 'status'
    )
    ORDER BY column_name
""")

if results:
    print(f"✅ Found {len(results)} new columns in active_positions:")
    for row in results:
        col_name = row[0] if isinstance(row, (list, tuple)) else row.get('column_name', row)
        data_type = row[1] if isinstance(row, (list, tuple)) else row.get('data_type', '')
        print(f"   - {col_name}: {data_type}")
else:
    print("❌ No new columns found - migration NOT applied")

# Check if position_history table exists
print("\n2. Checking position_history table...")
results = query("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name = 'position_history'
""")

if results:
    print("✅ position_history table exists")
    
    # Check columns
    results = query("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'position_history'
        ORDER BY ordinal_position
    """)
    print(f"   Columns: {len(results)}")
    for row in results[:10]:  # Show first 10
        print(f"   - {row['column_name']}: {row['data_type']}")
    if len(results) > 10:
        print(f"   ... and {len(results) - 10} more")
else:
    print("❌ position_history table NOT found - migration NOT applied")

# Check if strategy_stats table exists
print("\n3. Checking strategy_stats table...")
results = query("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name = 'strategy_stats'
""")

if results:
    print("✅ strategy_stats table exists")
else:
    print("⚠️  strategy_stats table NOT found (will be created by nightly job)")

# Check if migration was recorded
print("\n4. Checking schema_migrations...")
results = query("""
    SELECT version, applied_at 
    FROM schema_migrations 
    WHERE version LIKE '2026_02_02%'
    ORDER BY version
""")

if results:
    print(f"✅ Found {len(results)} migration(s) from 2026-02-02:")
    for row in results:
        print(f"   - {row['version']} applied at {row['applied_at']}")
else:
    print("❌ No migrations from 2026-02-02 found")

print("\n" + "="*80)
print("  SUMMARY")
print("="*80)

# Final verdict
results_ap = query("SELECT COUNT(*) FROM information_schema.columns WHERE table_name = 'active_positions' AND column_name = 'execution_uuid'")
results_ph = query("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'position_history'")

# Handle different result formats (dict or list)
def get_count(results):
    if not results or len(results) == 0:
        return 0
    row = results[0]
    if isinstance(row, dict):
        return int(row.get('count', 0))
    elif isinstance(row, (list, tuple)):
        return int(row[0]) if len(row) > 0 else 0
    else:
        return 0

ap_count = get_count(results_ap)
ph_count = get_count(results_ph)

if ap_count > 0 and ph_count > 0:
    print("✅ Migration APPLIED - Behavior Learning Mode schema is ready")
else:
    print("❌ Migration NOT APPLIED - Need to run migration")
    if ap_count == 0:
        print("   Missing: execution_uuid column in active_positions")
    if ph_count == 0:
        print("   Missing: position_history table")

print("="*80 + "\n")
