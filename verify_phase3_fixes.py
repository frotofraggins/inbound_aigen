#!/usr/bin/env python3
"""
Verify Phase 3 Fixes Applied Correctly
Checks all three production foot-guns are resolved
"""
import boto3
import json
import sys

def check_migrations():
    """Verify all Phase 3 migrations applied"""
    print("=" * 80)
    print("Checking Migrations")
    print("=" * 80)
    
    lambda_client = boto3.client('lambda', region_name='us-west-2')
    
    response = lambda_client.invoke(
        FunctionName='ops-pipeline-db-query',
        InvocationType='RequestResponse',
        Payload=json.dumps({
            'sql': """
                SELECT version, applied_at 
                FROM schema_migrations 
                WHERE version LIKE '2026_02_02%'
                ORDER BY version;
            """
        })
    )
    
    result = json.loads(response['Payload'].read())
    body = json.loads(result.get('body', '{}'))
    
    expected_migrations = [
        '2026_02_02_0001_position_telemetry',
        '2026_02_02_0002_websocket_idempotency',
        '2026_02_02_0003_add_constraints_no_do'
    ]
    
    found_migrations = [row['version'] for row in body.get('rows', [])]
    
    all_found = True
    for migration in expected_migrations:
        if migration in found_migrations:
            print(f"✅ {migration}")
        else:
            print(f"❌ {migration} - NOT FOUND")
            all_found = False
    
    return all_found


def check_constraints():
    """Verify constraints were added"""
    print("\n" + "=" * 80)
    print("Checking Constraints")
    print("=" * 80)
    
    lambda_client = boto3.client('lambda', region_name='us-west-2')
    
    response = lambda_client.invoke(
        FunctionName='ops-pipeline-db-query',
        InvocationType='RequestResponse',
        Payload=json.dumps({
            'sql': """
                SELECT 
                    conname AS constraint_name,
                    conrelid::regclass AS table_name,
                    convalidated
                FROM pg_constraint
                WHERE conname IN (
                    'chk_active_positions_side',
                    'chk_active_positions_strategy_type',
                    'chk_position_history_side',
                    'chk_position_history_strategy_type'
                )
                ORDER BY table_name, constraint_name;
            """
        })
    )
    
    result = json.loads(response['Payload'].read())
    body = json.loads(result.get('body', '{}'))
    
    expected_constraints = [
        'chk_active_positions_side',
        'chk_active_positions_strategy_type',
        'chk_position_history_side',
        'chk_position_history_strategy_type'
    ]
    
    found_constraints = [row['constraint_name'] for row in body.get('rows', [])]
    
    all_found = True
    for constraint in expected_constraints:
        if constraint in found_constraints:
            row = next(r for r in body['rows'] if r['constraint_name'] == constraint)
            validated = "VALIDATED" if row['convalidated'] else "NOT VALID"
            print(f"✅ {constraint} ({validated})")
        else:
            print(f"❌ {constraint} - NOT FOUND")
            all_found = False
    
    return all_found


def check_idempotency_schema():
    """Verify idempotency schema exists"""
    print("\n" + "=" * 80)
    print("Checking Idempotency Schema")
    print("=" * 80)
    
    lambda_client = boto3.client('lambda', region_name='us-west-2')
    
    response = lambda_client.invoke(
        FunctionName='ops-pipeline-db-query',
        InvocationType='RequestResponse',
        Payload=json.dumps({
            'sql': """
                SELECT 
                    table_name,
                    column_name,
                    data_type
                FROM information_schema.columns
                WHERE (table_name = 'alpaca_event_dedupe' AND column_name = 'event_id')
                   OR (table_name = 'active_positions' AND column_name = 'alpaca_order_id')
                ORDER BY table_name, column_name;
            """
        })
    )
    
    result = json.loads(response['Payload'].read())
    body = json.loads(result.get('body', '{}'))
    
    expected = [
        ('active_positions', 'alpaca_order_id'),
        ('alpaca_event_dedupe', 'event_id')
    ]
    
    found = [(row['table_name'], row['column_name']) for row in body.get('rows', [])]
    
    all_found = True
    for table, column in expected:
        if (table, column) in found:
            print(f"✅ {table}.{column}")
        else:
            print(f"❌ {table}.{column} - NOT FOUND")
            all_found = False
    
    return all_found


def check_trade_stream_service():
    """Verify trade-stream service is running"""
    print("\n" + "=" * 80)
    print("Checking Trade-Stream Service")
    print("=" * 80)
    
    ecs_client = boto3.client('ecs', region_name='us-west-2')
    
    response = ecs_client.describe_services(
        cluster='ops-pipeline',
        services=['trade-stream']
    )
    
    if not response['services']:
        print("❌ trade-stream service not found")
        return False
    
    service = response['services'][0]
    
    print(f"Status: {service['status']}")
    print(f"Running: {service['runningCount']}/{service['desiredCount']}")
    
    if service['status'] == 'ACTIVE' and service['runningCount'] > 0:
        print("✅ Service is running")
        return True
    else:
        print("❌ Service is not running properly")
        return False


def main():
    print("\n🔍 Phase 3 Fixes Verification\n")
    
    results = {
        'migrations': check_migrations(),
        'constraints': check_constraints(),
        'idempotency': check_idempotency_schema(),
        'trade_stream': check_trade_stream_service()
    }
    
    print("\n" + "=" * 80)
    print("Summary")
    print("=" * 80)
    
    all_passed = all(results.values())
    
    for check, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {check}")
    
    if all_passed:
        print("\n🎉 All Phase 3 fixes verified successfully!")
        print("\nNext steps:")
        print("1. Monitor trade-stream logs for duplicate event messages")
        print("2. Verify no duplicate positions created")
        print("3. Proceed to Phase 4: Nightly Statistics Job")
        sys.exit(0)
    else:
        print("\n⚠️ Some checks failed - review output above")
        sys.exit(1)


if __name__ == '__main__':
    main()
