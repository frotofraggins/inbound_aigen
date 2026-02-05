#!/usr/bin/env python3
"""
Complete End-to-End Verification for Both Accounts
Checks all services, data flow, and readiness
"""
import boto3
import json
from datetime import datetime

client = boto3.client('lambda', region_name='us-west-2')
ecs = boto3.client('ecs', region_name='us-west-2')

print("=" * 80)
print("COMPLETE SYSTEM VERIFICATION - BOTH ACCOUNTS")
print("=" * 80)
print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print()

# Phase 1: Check Services
print("Phase 1: ECS Services")
print("-" * 80)

services_check = {
    'dispatcher-service': 'Large account dispatcher',
    'dispatcher-tiny-service': 'Tiny account dispatcher',
    'position-manager-service': 'Large account position manager',
    'position-manager-tiny-service': 'Tiny account position manager',
    'telemetry-service': 'Market data ingestion',
    'trade-stream': 'Real-time updates'
}

for service_name, description in services_check.items():
    try:
        response = ecs.describe_services(
            cluster='ops-pipeline-cluster',
            services=[service_name]
        )
        if response['services']:
            service = response['services'][0]
            running = service['runningCount']
            desired = service['desiredCount']
            status = "✅" if running == desired else "⚠️ "
            print(f"{status} {service_name}: {running}/{desired} running")
            print(f"   → {description}")
        else:
            print(f"❌ {service_name}: NOT FOUND")
    except Exception as e:
        print(f"❌ {service_name}: Error - {str(e)[:50]}")

print()

# Phase 2: Data Pipeline
print("Phase 2: Data Pipeline Health")
print("-" * 80)

data_checks = [
    ("Telemetry Bars (6h)", "SELECT COUNT(*) as c FROM lane_telemetry WHERE ts > NOW() - INTERVAL '6 hours'"),
    ("Features (6h)", "SELECT COUNT(*) as c FROM lane_features WHERE computed_at > NOW() - INTERVAL '6 hours'"),
    ("Signals (24h)", "SELECT COUNT(*) as c FROM dispatch_recommendations WHERE created_at > NOW() - INTERVAL '24 hours'"),
    ("Classified News (24h)", "SELECT COUNT(*) as c FROM inbound_events_classified WHERE created_at > NOW() - INTERVAL '24 hours'"),
]

for name, sql in data_checks:
    try:
        response = client.invoke(
            FunctionName='ops-pipeline-db-query',
            Payload=json.dumps({'sql': sql})
        )
        result = json.loads(json.load(response['Payload'])['body'])
        count = result.get('rows', [{}])[0].get('c', 0)
        status = "✅" if count > 0 else "❌"
        print(f"{status} {name}: {count}")
    except Exception as e:
        print(f"❌ {name}: Error")

print()

# Phase 3: Account-Specific Checks
print("Phase 3: Account-Specific Status")
print("-" * 80)

for account in ['large', 'tiny']:
    print(f"\n{account.upper()} ACCOUNT:")
    
    # Check recent recommendations
    sql = f"""
    SELECT 
        COUNT(*) as pending,
        COUNT(CASE WHEN status = 'EXECUTED' THEN 1 END) as executed,
        COUNT(CASE WHEN status = 'SKIPPED' THEN 1 END) as skipped
    FROM dispatch_recommendations dr
    LEFT JOIN dispatch_executions de ON dr.id = de.recommendation_id
    WHERE dr.created_at > NOW() - INTERVAL '2 hours'
    AND (de.account_name = '{account}' OR de.account_name IS NULL)
    """
    
    try:
        response = client.invoke(
            FunctionName='ops-pipeline-db-query',
            Payload=json.dumps({'sql': sql})
        )
        result = json.loads(json.load(response['Payload'])['body'])
        if result.get('rows'):
            row = result['rows'][0]
            print(f"  Recent signals: {row.get('pending', 0)} total")
            print(f"  Executed: {row.get('executed', 0)}")
            print(f"  Skipped: {row.get('skipped', 0)}")
    except:
        print(f"  ⚠️  Could not check signals")
    
    # Check open positions
    sql2 = f"""
    SELECT COUNT(*) as count
    FROM active_positions
    WHERE status = 'open'
    AND account_name = '{account}'
    """
    
    try:
        response = client.invoke(
            FunctionName='ops-pipeline-db-query',
            Payload=json.dumps({'sql': sql2})
        )
        result = json.loads(json.load(response['Payload'])['body'])
        count = result.get('rows', [{}])[0].get('count', 0)
        print(f"  Open positions: {count}")
    except:
        print(f"  ⚠️  Could not check positions")

print()

# Phase 4: Learning System
print("Phase 4: Learning System")
print("-" * 80)

learning_tables = {
    'position_history': 'Trade outcomes',
    'option_bars': 'Price history',
    'position_events': 'Lifecycle events'
}

for table, desc in learning_tables.items():
    sql = f"SELECT COUNT(*) as c FROM {table}"
    try:
        response = client.invoke(
            FunctionName='ops-pipeline-db-query',
            Payload=json.dumps({'sql': sql})
        )
        result = json.loads(json.load(response['Payload'])['body'])
        count = result.get('rows', [{}])[0].get('c', 0)
        status = "✅" if count > 0 else "❌"
        print(f"{status} {table}: {count} records - {desc}")
    except:
        print(f"❌ {table}: Error")

print()
print("=" * 80)
print("VERIFICATION COMPLETE")
print("=" * 80)
print()
print("Next: Monitor for new positions with:")
print("  python3 scripts/monitor_exit_fix.py")
