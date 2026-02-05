#!/usr/bin/env python3
"""
Query database via Lambda function (ops-pipeline-db-query)
This Lambda is inside the VPC and can reach the RDS instance
"""
import boto3
import json
import sys

def query_db(sql):
    """Execute SELECT query via Lambda"""
    lambda_client = boto3.client('lambda', region_name='us-west-2')
    
    print(f"Executing query: {sql[:80]}...")
    
    try:
        response = lambda_client.invoke(
            FunctionName='ops-pipeline-db-query',
            Payload=json.dumps({'sql': sql})
        )
        
        result = json.loads(response['Payload'].read())
        
        # Lambda returns: {"statusCode": 200, "body": "{...}"}
        # Parse the body if it's a string
        if 'body' in result and isinstance(result['body'], str):
            body = json.loads(result['body'])
            return body
        
        return result
    except Exception as e:
        print(f"❌ Lambda invocation failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def check_position_history():
    """Check position_history table"""
    print("\n" + "="*80)
    print("1. CHECKING position_history TABLE")
    print("="*80)
    
    # Check if table exists and count records
    result = query_db("""
        SELECT COUNT(*) as count FROM position_history
    """)
    
    if result and 'rows' in result:
        # Rows are dictionaries, not arrays
        count = result['rows'][0]['count'] if result['rows'] else 0
        print(f"\n✓ position_history has {count} records")
        
        if count > 0:
            # Get recent records
            result = query_db("""
                SELECT 
                    id, ticker, instrument_type, side,
                    entry_time, exit_time, pnl_pct, exit_reason,
                    holding_seconds, created_at
                FROM position_history
                ORDER BY created_at DESC
                LIMIT 5
            """)
            
            if result and 'rows' in result:
                print("\nMost recent records:")
                for row in result['rows']:
                    print(f"\n  ID {row['id']}: {row['ticker']} {row['instrument_type']} {row['side']}")
                    print(f"    Entry: {row['entry_time']}")
                    print(f"    Exit:  {row['exit_time']}")
                    hold_min = float(row['holding_seconds']) / 60 if row['holding_seconds'] else 0
                    pnl = float(row['pnl_pct']) if row['pnl_pct'] else 0
                    print(f"    P&L: {pnl:.2f}% | Held: {hold_min:.1f} min | Reason: {row['exit_reason']}")
                    print(f"    Created: {row['created_at']}")
        else:
            print("\n⚠️  position_history table is EMPTY")
            print("    This is expected if no positions have closed since fix (16:17 UTC)")
    else:
        print(f"❌ Query failed: {result}")

def check_max_hold_minutes():
    """Check max_hold_minutes configuration"""
    print("\n" + "="*80)
    print("2. CHECKING max_hold_minutes CONFIGURATION")
    print("="*80)
    
    # Check open positions
    result = query_db("""
        SELECT 
            id, ticker, instrument_type, entry_time,
            max_hold_minutes, status,
            EXTRACT(EPOCH FROM (NOW() - entry_time))/60 as minutes_held
        FROM active_positions
        WHERE status = 'open'
        ORDER BY entry_time DESC
        LIMIT 10
    """)
    
    if result and 'rows' in result:
        if result['rows']:
            print(f"\n✓ Found {len(result['rows'])} open positions:")
            for row in result['rows']:
                max_hold = int(row['max_hold_minutes']) if row['max_hold_minutes'] else 240
                minutes_held = float(row['minutes_held']) if row['minutes_held'] else 0
                print(f"\n  Position {row['id']}: {row['ticker']} {row['instrument_type']}")
                print(f"    Entry: {row['entry_time']}")
                print(f"    Max hold: {max_hold} minutes ({max_hold/60:.1f} hours)")
                print(f"    Currently held: {minutes_held:.1f} minutes ({minutes_held/60:.1f} hours)")
                
                if max_hold == 240:
                    print(f"    ✓ Correct: 240 minutes = 4 hours")
                elif max_hold == 1200:
                    print(f"    ❌ WRONG: 1200 minutes = 20 hours (should be 240)")
                else:
                    print(f"    ⚠️  Unusual value: {max_hold} minutes")
        else:
            print("\n  No open positions currently")

def check_closed_positions():
    """Check recently closed positions"""
    print("\n" + "="*80)
    print("3. CHECKING RECENTLY CLOSED POSITIONS")
    print("="*80)
    
    # Check closed in last 48 hours
    result = query_db("""
        SELECT 
            id, ticker, instrument_type,
            entry_time, closed_at, close_reason,
            max_hold_minutes,
            EXTRACT(EPOCH FROM (closed_at - entry_time))/60 as minutes_held,
            current_pnl_percent
        FROM active_positions
        WHERE status = 'closed'
          AND closed_at >= NOW() - INTERVAL '48 hours'
        ORDER BY closed_at DESC
        LIMIT 10
    """)
    
    if result and 'rows' in result:
        if result['rows']:
            print(f"\n✓ Found {len(result['rows'])} positions closed in last 48 hours:")
            for row in result['rows']:
                minutes_held = float(row['minutes_held']) if row['minutes_held'] else 0
                max_hold = int(row['max_hold_minutes']) if row['max_hold_minutes'] else 240
                hours_held = minutes_held / 60
                expected_hours = max_hold / 60
                pnl = float(row['current_pnl_percent']) if row['current_pnl_percent'] else 0
                
                print(f"\n  Position {row['id']}: {row['ticker']} {row['instrument_type']}")
                print(f"    Entry:  {row['entry_time']}")
                print(f"    Closed: {row['closed_at']}")
                print(f"    Held: {hours_held:.1f} hours (expected max: {expected_hours:.1f} hours)")
                print(f"    P&L: {pnl:.2f}%")
                print(f"    Reason: {row['close_reason']}")
                
                if hours_held > expected_hours + 1:
                    print(f"    ⚠️  HELD TOO LONG: {hours_held:.1f}h > {expected_hours:.1f}h")
                else:
                    print(f"    ✓ Held time appropriate")
        else:
            print("\n  No positions closed in last 48 hours")
    
    # Check UNH/CSCO specifically
    print("\n  Checking UNH/CSCO trades:")
    result = query_db("""
        SELECT 
            id, ticker, instrument_type, entry_time, closed_at,
            close_reason, max_hold_minutes,
            EXTRACT(EPOCH FROM (closed_at - entry_time))/60 as minutes_held,
            current_pnl_percent
        FROM active_positions
        WHERE ticker IN ('UNH', 'CSCO')
          AND status = 'closed'
        ORDER BY closed_at DESC
        LIMIT 5
    """)
    
    if result and 'rows' in result and result['rows']:
        for row in result['rows']:
            minutes_held = float(row['minutes_held']) if row['minutes_held'] else 0
            hours_held = minutes_held / 60
            max_hold = int(row['max_hold_minutes']) if row['max_hold_minutes'] else 240
            pnl = float(row['current_pnl_percent']) if row['current_pnl_percent'] else 0
            print(f"\n  {row['ticker']} {row['instrument_type']} (Position {row['id']})")
            print(f"    Entry:  {row['entry_time']}")
            print(f"    Closed: {row['closed_at']}")
            print(f"    Held: {hours_held:.1f} hours (max_hold_minutes: {max_hold})")
            print(f"    P&L: {pnl:.2f}%")
            print(f"    Reason: {row['close_reason']}")

def main():
    """Run all checks"""
    print("="*80)
    print("DATABASE VERIFICATION VIA LAMBDA")
    print("="*80)
    
    try:
        check_position_history()
        check_max_hold_minutes()
        check_closed_positions()
        
        print("\n" + "="*80)
        print("VERIFICATION COMPLETE")
        print("="*80)
        
        print("\n📋 KEY FINDINGS:")
        print("1. Check if position_history has data since 16:17 UTC Feb 5")
        print("2. Verify max_hold_minutes is 240 (not 1200)")
        print("3. Understand why UNH/CSCO held 20 hours")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
