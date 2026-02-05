#!/usr/bin/env python3
"""
Comprehensive investigation of why exit fix is not working
Checks:
1. Position manager service status and logs
2. Recent position closures and timing
3. Alpaca API state vs our database
4. Instrument type detection issues
5. Position history insert failures
"""

import boto3
import json
from datetime import datetime, timedelta, timezone
import os
import sys
import psycopg2
import psycopg2.extras

def print_section(title):
    """Print a formatted section header"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")

def check_ecs_services():
    """Check status of both position manager services"""
    print_section("ECS SERVICE STATUS")
    
    ecs = boto3.client('ecs', region_name='us-west-2')
    cluster = 'ops-pipeline-cluster'
    
    services = [
        'position-manager-service',
        'position-manager-tiny-service'
    ]
    
    for service_name in services:
        try:
            response = ecs.describe_services(
                cluster=cluster,
                services=[service_name]
            )
            
            if response['services']:
                service = response['services'][0]
                print(f"Service: {service_name}")
                print(f"  Status: {service['status']}")
                print(f"  Running Count: {service['runningCount']}")
                print(f"  Desired Count: {service['desiredCount']}")
                print(f"  Pending Count: {service['pendingCount']}")
                
                if service.get('deployments'):
                    deployment = service['deployments'][0]
                    print(f"  Latest Deployment:")
                    print(f"    Status: {deployment['status']}")
                    print(f"    Created: {deployment['createdAt']}")
                    print(f"    Updated: {deployment['updatedAt']}")
                
                # Get task details
                if service['runningCount'] > 0:
                    tasks_response = ecs.list_tasks(
                        cluster=cluster,
                        serviceName=service_name
                    )
                    
                    if tasks_response['taskArns']:
                        task_details = ecs.describe_tasks(
                            cluster=cluster,
                            tasks=tasks_response['taskArns']
                        )
                        
                        for task in task_details['tasks']:
                            print(f"  Task: {task['taskArn'].split('/')[-1]}")
                            print(f"    Status: {task['lastStatus']}")
                            print(f"    Health: {task.get('healthStatus', 'N/A')}")
                            print(f"    Started: {task.get('startedAt', 'N/A')}")
                
                print()
            else:
                print(f"❌ Service {service_name} not found\n")
        
        except Exception as e:
            print(f"❌ Error checking {service_name}: {e}\n")

def get_recent_logs(log_group, minutes=30):
    """Get recent logs from CloudWatch"""
    logs = boto3.client('logs', region_name='us-west-2')
    
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=minutes)
    
    try:
        # Get log streams
        streams_response = logs.describe_log_streams(
            logGroupName=log_group,
            orderBy='LastEventTime',
            descending=True,
            limit=5
        )
        
        if not streams_response['logStreams']:
            print(f"  No log streams found in {log_group}")
            return []
        
        all_events = []
        
        for stream in streams_response['logStreams'][:2]:  # Check last 2 streams
            stream_name = stream['logStreamName']
            
            try:
                events_response = logs.get_log_events(
                    logGroupName=log_group,
                    logStreamName=stream_name,
                    startTime=int(start_time.timestamp() * 1000),
                    endTime=int(end_time.timestamp() * 1000),
                    limit=100
                )
                
                all_events.extend(events_response['events'])
            
            except Exception as e:
                print(f"  Warning: Could not read stream {stream_name}: {e}")
        
        return all_events
    
    except Exception as e:
        print(f"  Error reading logs: {e}")
        return []

def check_position_manager_logs():
    """Check logs for both position manager services"""
    print_section("POSITION MANAGER LOGS (Last 30 Minutes)")
    
    log_groups = {
        'Large Account': '/ecs/ops-pipeline/position-manager',
        'Tiny Account': '/ecs/ops-pipeline/position-manager-tiny'
    }
    
    for account, log_group in log_groups.items():
        print(f"\n{account} ({log_group}):")
        print("-" * 80)
        
        events = get_recent_logs(log_group, minutes=30)
        
        if not events:
            print("  ❌ NO LOGS FOUND IN LAST 30 MINUTES!")
            print("  This suggests service may have crashed or stopped")
        else:
            print(f"  ✓ Found {len(events)} log entries")
            
            # Show last 10 entries
            print("\n  Last 10 log entries:")
            for event in sorted(events, key=lambda x: x['timestamp'])[-10:]:
                timestamp = datetime.fromtimestamp(event['timestamp'] / 1000, tz=timezone.utc)
                message = event['message'].strip()
                print(f"    [{timestamp.strftime('%H:%M:%S')}] {message}")
            
            # Look for specific patterns
            print("\n  Pattern Analysis:")
            
            sleeping_count = sum(1 for e in events if 'Sleeping' in e['message'])
            print(f"    'Sleeping' messages: {sleeping_count}")
            
            starting_count = sum(1 for e in events if 'Position Manager starting' in e['message'])
            print(f"    'Starting' messages: {starting_count}")
            
            too_early_count = sum(1 for e in events if 'Too early to exit' in e['message'])
            print(f"    'Too early to exit' messages: {too_early_count}")
            
            exit_triggered = sum(1 for e in events if 'EXIT TRIGGERED' in e['message'])
            print(f"    'EXIT TRIGGERED' messages: {exit_triggered}")
            
            positions_closed = sum(1 for e in events if 'closed successfully' in e['message'])
            print(f"    Positions closed: {positions_closed}")

def get_db_connection():
    """Get database connection from SSM parameters"""
    ssm = boto3.client('ssm', region_name='us-west-2')
    
    # Get all db parameters
    response = ssm.get_parameters_by_path(
        Path='/ops-pipeline/db',
        WithDecryption=True
    )
    
    param_dict = {}
    for param in response['Parameters']:
        key = param['Name'].split('/')[-1]
        param_dict[key] = param['Value']
    
    return psycopg2.connect(
        host=param_dict.get('host', param_dict.get('endpoint', '')),
        port=int(param_dict.get('port', 5432)),
        dbname=param_dict.get('name', param_dict.get('database', '')),
        user=param_dict.get('user', param_dict.get('username', '')),
        password=param_dict.get('password', '')
    )

def check_recent_positions():
    """Check recent positions and their closure times"""
    print_section("RECENT POSITION CLOSURES")
    
    query = """
    SELECT 
        id,
        ticker,
        instrument_type,
        account_name,
        entry_time,
        exit_time,
        EXTRACT(EPOCH FROM (exit_time - entry_time))/60 as hold_minutes,
        entry_price,
        exit_price,
        quantity,
        exit_reason
    FROM active_positions
    WHERE exit_time IS NOT NULL
    AND entry_time > NOW() - INTERVAL '2 hours'
    ORDER BY exit_time DESC
    LIMIT 20
    """
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(query)
    results = cur.fetchall()
    cur.close()
    conn.close()
    
    if not results:
        print("No closed positions in last 2 hours")
        return
    
    print(f"Found {len(results)} closed positions:")
    print()
    
    for pos in results:
        hold_minutes = float(pos['hold_minutes'])
        
        # Flag positions closed too fast
        warning = ""
        if hold_minutes < 30:
            warning = " ⚠️ TOO FAST!"
        
        print(f"  {pos['ticker']} ({pos['instrument_type']}) - Account: {pos['account_name']}")
        print(f"    Hold time: {hold_minutes:.1f} minutes{warning}")
        print(f"    Entry: {pos['entry_time'].strftime('%H:%M:%S')}")
        print(f"    Exit:  {pos['exit_time'].strftime('%H:%M:%S')}")
        print(f"    Reason: {pos['exit_reason']}")
        print(f"    P&L: {pos['quantity']} @ ${pos['entry_price']:.2f} → ${pos['exit_price']:.2f}")
        print()

def check_instrument_types():
    """Check for options being logged as STOCK"""
    print_section("INSTRUMENT TYPE ISSUES")
    
    query = """
    SELECT 
        ticker,
        instrument_type,
        COUNT(*) as count
    FROM active_positions
    WHERE entry_time > NOW() - INTERVAL '2 hours'
    AND (
        ticker LIKE '%P%' OR 
        ticker LIKE '%C%'
    )
    GROUP BY ticker, instrument_type
    ORDER BY ticker
    """
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(query)
    results = cur.fetchall()
    cur.close()
    conn.close()
    
    if not results:
        print("No option-like tickers found")
        return
    
    print("Option symbols and their logged instrument types:")
    print()
    
    issues_found = False
    for row in results:
        ticker = row['ticker']
        inst_type = row['instrument_type']
        count = row['count']
        
        # Check if looks like an option but logged as STOCK
        if len(ticker) > 10 and ('C0' in ticker or 'P0' in ticker):
            if inst_type != 'OPTION':
                print(f"  ❌ {ticker}: logged as '{inst_type}' but appears to be OPTION ({count} times)")
                issues_found = True
            else:
                print(f"  ✓ {ticker}: correctly logged as OPTION ({count} times)")
        else:
            print(f"  {ticker}: {inst_type} ({count} times)")
    
    if issues_found:
        print("\n⚠️  CRITICAL: Options are being logged as wrong instrument type!")
        print("   This means they will use STOCK exit logic instead of OPTION exit logic")

def check_position_history():
    """Check if position_history table is being populated"""
    print_section("POSITION HISTORY TABLE")
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    # Count total closed positions
    closed_query = """
    SELECT COUNT(*) as count
    FROM active_positions
    WHERE exit_time IS NOT NULL
    AND entry_time > NOW() - INTERVAL '1 day'
    """
    
    cur.execute(closed_query)
    closed_results = cur.fetchall()
    closed_count = closed_results[0]['count'] if closed_results else 0
    
    # Count position_history entries
    history_query = """
    SELECT COUNT(*) as count
    FROM position_history
    WHERE created_at > NOW() - INTERVAL '1 day'
    """
    
    cur.execute(history_query)
    history_results = cur.fetchall()
    history_count = history_results[0]['count'] if history_results else 0
    
    cur.close()
    conn.close()
    
    print(f"Closed positions (last 24h): {closed_count}")
    print(f"Position history entries:    {history_count}")
    
    if closed_count > 0 and history_count == 0:
        print("\n❌ CRITICAL: Closed positions are NOT being saved to position_history!")
        print("   This means no learning data is being collected")
        print("   Check exits.py for insert failures")
    elif history_count < closed_count:
        print(f"\n⚠️  WARNING: Missing {closed_count - history_count} history entries")
    else:
        print("\n✓ Position history is being saved correctly")

def check_open_positions():
    """Check current open positions"""
    print_section("CURRENT OPEN POSITIONS")
    
    query = """
    SELECT 
        id,
        ticker,
        instrument_type,
        account_name,
        entry_time,
        EXTRACT(EPOCH FROM (NOW() - entry_time))/60 as age_minutes,
        entry_price,
        current_price,
        quantity,
        stop_loss,
        take_profit
    FROM active_positions
    WHERE exit_time IS NULL
    ORDER BY entry_time DESC
    """
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(query)
    results = cur.fetchall()
    cur.close()
    conn.close()
    
    if not results:
        print("No open positions")
        return
    
    print(f"Found {len(results)} open positions:")
    print()
    
    for pos in results:
        age_minutes = float(pos['age_minutes'])
        
        pnl_pct = 0
        if pos['entry_price'] and pos['current_price']:
            pnl_pct = ((pos['current_price'] - pos['entry_price']) / pos['entry_price']) * 100
        
        print(f"  {pos['ticker']} ({pos['instrument_type']}) - Account: {pos['account_name']}")
        print(f"    Age: {age_minutes:.1f} minutes")
        print(f"    Entry: ${pos['entry_price']:.2f} @ {pos['entry_time'].strftime('%H:%M:%S')}")
        print(f"    Current: ${pos['current_price']:.2f if pos['current_price'] else 'N/A'} ({pnl_pct:+.1f}%)")
        print(f"    Stop: ${pos['stop_loss']:.2f}, Target: ${pos['take_profit']:.2f}")
        print()

def main():
    """Run all investigations"""
    print("\n" + "=" * 80)
    print("  EXIT FIX INVESTIGATION")
    print("  " + datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'))
    print("=" * 80)
    
    try:
        # 1. Check ECS service status
        check_ecs_services()
        
        # 2. Check position manager logs
        check_position_manager_logs()
        
        # 3. Check recent position closures
        check_recent_positions()
        
        # 4. Check instrument type issues
        check_instrument_types()
        
        # 5. Check position history
        check_position_history()
        
        # 6. Check open positions
        check_open_positions()
        
        print_section("INVESTIGATION COMPLETE")
        print("Review findings above to determine next steps")
        
    except Exception as e:
        print(f"\n❌ Investigation failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
