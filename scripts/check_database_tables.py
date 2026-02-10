#!/usr/bin/env python3
"""
Check all database tables and their row counts
Uses Lambda for database access (recommended method)
"""

import boto3
import json
import sys

def query_db(sql):
    """Query database via Lambda"""
    client = boto3.client('lambda', region_name='us-west-2')
    
    try:
        response = client.invoke(
            FunctionName='ops-pipeline-db-query',
            Payload=json.dumps({'sql': sql})
        )
        
        result = json.loads(response['Payload'].read())
        if result.get('statusCode') == 200:
            body = json.loads(result['body'])
            # Lambda returns: {"success": true, "rows": [...], "count": N}
            return body.get('rows', [])
        else:
            print(f"Error: {result}")
            return None
    except Exception as e:
        print(f"Lambda invocation failed: {e}")
        return None

def main():
    print("=" * 80)
    print("DATABASE TABLES CHECK")
    print("=" * 80)
    
    # Get all tables
    print("\n1. Fetching all tables...")
    tables_query = """
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public'
    ORDER BY table_name
    """
    
    tables = query_db(tables_query)
    
    if not tables:
        print("❌ Failed to fetch tables")
        return 1
    
    print(f"✅ Found {len(tables)} tables")
    
    # Handle different response formats
    table_names = []
    if isinstance(tables, list):
        if len(tables) > 0:
            if isinstance(tables[0], dict):
                # List of dicts: [{'table_name': 'x'}, ...]
                table_names = [t['table_name'] for t in tables]
            elif isinstance(tables[0], str):
                # List of strings: ['x', 'y', ...]
                table_names = tables
            else:
                print(f"Unexpected format: {type(tables[0])}")
                print(f"First item: {tables[0]}")
                return 1
    
    for name in table_names:
        print(f"   - {name}")
    
    # Get row counts for each table
    print("\n2. Checking row counts...")
    print("-" * 80)
    
    for table_name in table_names:
        count_query = f"SELECT COUNT(*) as count FROM {table_name}"
        result = query_db(count_query)
        
        if result:
            count = result[0]['count']
            status = "✅" if count > 0 else "⚠️ "
            print(f"{status} {table_name:30s} {count:>10,} rows")
        else:
            print(f"❌ {table_name:30s} Failed to query")
    
    # Check key tables health
    print("\n3. Key Tables Health Check...")
    print("-" * 80)
    
    # Active positions
    active_query = """
    SELECT 
        COUNT(*) as total,
        COUNT(*) FILTER (WHERE status = 'open') as open_positions,
        COUNT(*) FILTER (WHERE status = 'closed') as closed_today
    FROM active_positions
    """
    result = query_db(active_query)
    if result:
        r = result[0]
        print(f"Active Positions: {r['total']} total, {r['open_positions']} open, {r['closed_today']} closed today")
    
    # Position history (learning data)
    history_query = """
    SELECT 
        COUNT(*) as total_trades,
        COUNT(*) FILTER (WHERE pnl_pct > 0) as winners,
        AVG(pnl_pct) as avg_pnl,
        MAX(exit_time) as last_close
    FROM position_history
    """
    result = query_db(history_query)
    if result and len(result) > 0:
        r = result[0]
        if r['total_trades'] and r['total_trades'] > 0:
            win_rate = (r['winners'] / r['total_trades'] * 100)
            avg_pnl = float(r['avg_pnl']) if r['avg_pnl'] else 0.0
            print(f"Position History: {r['total_trades']} trades, {win_rate:.1f}% win rate, avg PnL: {avg_pnl:.1f}%")
            print(f"                  Last close: {r['last_close']}")
        else:
            print("Position History: No trades yet")
    
    # Recent signals
    signals_query = """
    SELECT COUNT(*) as count
    FROM dispatch_recommendations
    WHERE generated_at > NOW() - INTERVAL '1 hour'
    """
    result = query_db(signals_query)
    if result:
        count = result[0]['count']
        print(f"Recent Signals: {count} in last hour")
    
    # Recent telemetry
    telemetry_query = """
    SELECT 
        COUNT(DISTINCT ticker) as tickers,
        MAX(timestamp) as latest
    FROM lane_telemetry
    WHERE timestamp > NOW() - INTERVAL '1 hour'
    """
    result = query_db(telemetry_query)
    if result:
        r = result[0]
        print(f"Market Data: {r['tickers']} tickers, latest: {r['latest']}")
    
    print("\n" + "=" * 80)
    print("DATABASE CHECK COMPLETE ✅")
    print("=" * 80)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
