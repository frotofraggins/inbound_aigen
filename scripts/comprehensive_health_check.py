#!/usr/bin/env python3
"""
Comprehensive system health check
Verifies trading, monitoring, and learning systems
"""
import boto3
import json
from datetime import datetime, timedelta, timezone

def check_services():
    """Check ECS services status"""
    print("\n" + "="*80)
    print("SERVICES STATUS")
    print("="*80)
    
    ecs = boto3.client('ecs', region_name='us-west-2')
    
    services = [
        'position-manager-service',
        'position-manager-tiny-service',
        'dispatcher-service',
        'dispatcher-tiny-service',
        'signal-engine-service',
        'feature-computer-service'
    ]
    
    for service in services:
        try:
            resp = ecs.describe_services(
                cluster='ops-pipeline-cluster',
                services=[service]
            )
            if resp['services']:
                s = resp['services'][0]
                status = "✅" if s['runningCount'] == s['desiredCount'] else "⚠️"
                print(f"{status} {service}: {s['runningCount']}/{s['desiredCount']} running")
        except:
            print(f"❌ {service}: Not found")

def check_recent_activity():
    """Check recent logs for activity"""
    print("\n" + "="*80)
    print("RECENT ACTIVITY (Last 30 Minutes)")
    print("="*80)
    
    logs = boto3.client('logs', region_name='us-west-2')
    
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=30)
    
    try:
        events = logs.filter_log_events(
            logGroupName='/ecs/ops-pipeline/position-manager-service',
            startTime=int(start_time.timestamp() * 1000),
            endTime=int(end_time.timestamp() * 1000),
            limit=100
        )
        
        messages = [e['message'] for e in events['events']]
        
        # Count key activities
        starting = len([m for m in messages if 'Position Manager starting' in m])
        processing = len([m for m in messages if 'Processing position' in m])
        open_pos = [m for m in messages if 'Found' in m and 'open position' in m]
        
        print(f"Position manager cycles: {starting} (should be ~30)")
        print(f"Positions processed: {processing}")
        if open_pos:
            print(f"Latest: {open_pos[-1].split('INFO -')[-1].strip()}")
        
        # Check for closed positions
        closed = [m for m in messages if 'closed successfully' in m]
        if closed:
            print(f"\n✅ Positions closed: {len(closed)}")
            for c in closed[-3:]:
                print(f"   {c.split('INFO -')[-1].strip()}")
        else:
            print("\nNo positions closed in last 30 minutes")
            
    except Exception as e:
        print(f"Error checking logs: {e}")

def check_position_health():
    """Show current open positions"""
    print("\n" + "="*80)
    print("CURRENT OPEN POSITIONS")
    print("="*80)
    
    logs = boto3.client('logs', region_name='us-west-2')
    
    try:
        events = logs.filter_log_events(
            logGroupName='/ecs/ops-pipeline/position-manager-service',
            startTime=int((datetime.now(timezone.utc) - timedelta(minutes=2)).timestamp() * 1000),
            limit=50
        )
        
        messages = [e['message'] for e in events['events']]
        
        # Find position summary
        for msg in messages:
            if 'Found' in msg and 'open position' in msg:
                print(msg.split('INFO -')[-1].strip())
                break
        
        # Find recent processing
        processing = [m for m in messages if 'Processing position' in m][-5:]
        if processing:
            print("\nRecent processing:")
            for p in processing:
                pos_info = p.split('▶ Processing position')[-1].strip()
                print(f"  {pos_info}")
                
    except Exception as e:
        print(f"Error: {e}")

def main():
    print("\n" + "="*80)
    print("COMPREHENSIVE SYSTEM HEALTH CHECK")
    print(datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'))
    print("="*80)
    
    check_services()
    check_recent_activity()
    check_position_health()
    
    print("\n" + "="*80)
    print("HEALTH CHECK COMPLETE")
    print("="*80)
    print("\n✅ To verify learning data, check position_history table")
    print("✅ To check trailing stops, run: python3 scripts/apply_013_direct.py")
    print()

if __name__ == "__main__":
    main()
