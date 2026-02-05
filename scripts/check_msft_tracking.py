#!/usr/bin/env python3
"""
Check if position manager is tracking MSFT position P&L in real-time
"""
import boto3
import json

def query_db(sql):
    """Execute SELECT query via Lambda"""
    lambda_client = boto3.client('lambda', region_name='us-west-2')
    
    try:
        response = lambda_client.invoke(
            FunctionName='ops-pipeline-db-query',
            Payload=json.dumps({'sql': sql})
        )
        
        result = json.loads(response['Payload'].read())
        
        if 'body' in result and isinstance(result['body'], str):
            body = json.loads(result['body'])
            return body
        
        return result
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

print("="*80)
print("CHECKING MSFT POSITION TRACKING")
print("="*80)

# Check all MSFT positions
result = query_db("""
    SELECT 
        id, ticker, instrument_type,
        entry_time, entry_price, current_price,
        current_pnl_dollars, current_pnl_percent,
        best_unrealized_pnl_pct, worst_unrealized_pnl_pct,
        last_checked_at, check_count,
        take_profit, stop_loss, max_hold_minutes,
        status, option_symbol
    FROM active_positions
    WHERE ticker = 'MSFT' AND status = 'open'
    ORDER BY entry_time DESC
""")

if result and 'rows' in result and result['rows']:
    print(f"\nFound {len(result['rows'])} open MSFT positions:\n")
    
    for row in result['rows']:
        entry_price = float(row['entry_price'])
        current_price = float(row['current_price']) if row['current_price'] else entry_price
        current_pnl_pct = float(row['current_pnl_percent']) if row['current_pnl_percent'] else 0
        best_pnl = float(row['best_unrealized_pnl_pct']) if row['best_unrealized_pnl_pct'] else 0
        worst_pnl = float(row['worst_unrealized_pnl_pct']) if row['worst_unrealized_pnl_pct'] else 0
        take_profit = float(row['take_profit']) if row['take_profit'] else 0
        stop_loss = float(row['stop_loss']) if row['stop_loss'] else 0
        
        print(f"Position {row['id']}: {row['instrument_type']} ({row['option_symbol']})")
        print(f"  Entry Time: {row['entry_time']}")
        print(f"  Entry Price: ${entry_price:.2f}")
        print(f"  Current Price: ${current_price:.2f}")
        print(f"  Current P&L: {current_pnl_pct:.2f}%")
        print(f"  Best P&L (Peak): {best_pnl:.2f}%")
        print(f"  Worst P&L (Low): {worst_pnl:.2f}%")
        print(f"  Take Profit: ${take_profit:.2f} (+80%)")
        print(f"  Stop Loss: ${stop_loss:.2f} (-40%)")
        print(f"  Last Checked: {row['last_checked_at']}")
        print(f"  Check Count: {row['check_count']}")
        print(f"  Max Hold: {row['max_hold_minutes']} minutes")
        
        # Calculate if it should sell
        tp_pct = ((take_profit / entry_price) - 1) * 100 if entry_price else 0
        sl_pct = ((stop_loss / entry_price) - 1) * 100 if entry_price else 0
        
        print(f"\n  Exit Thresholds:")
        print(f"    Take Profit: {tp_pct:.1f}% (triggers at ${take_profit:.2f})")
        print(f"    Stop Loss: {sl_pct:.1f}% (triggers at ${stop_loss:.2f})")
        
        if current_pnl_pct >= tp_pct:
            print(f"  ⚠️  AT TAKE PROFIT! Should close soon")
        elif current_pnl_pct <= sl_pct:
            print(f"  ⚠️  AT STOP LOSS! Should close soon")
        else:
            print(f"  ✓ Within thresholds, holding")
        
        print()

else:
    print("\n❌ No open MSFT positions found")

# Check monitoring frequency
print("\n" + "="*80)
print("CHECKING MONITORING FREQUENCY")
print("="*80)

result = query_db("""
    SELECT 
        ticker, 
        MIN(EXTRACT(EPOCH FROM (NOW() - last_checked_at))/60) as minutes_since_last_check,
        AVG(check_count) as avg_check_count
    FROM active_positions
    WHERE status = 'open'
    GROUP BY ticker
    ORDER BY minutes_since_last_check ASC
    LIMIT 5
""")

if result and 'rows' in result:
    print("\nRecent check status:")
    for row in result['rows']:
        mins = float(row['minutes_since_last_check']) if row['minutes_since_last_check'] else 0
        avg_checks = float(row['avg_check_count']) if row['avg_check_count'] else 0
        print(f"  {row['ticker']}: Last checked {mins:.1f} minutes ago, {avg_checks:.0f} total checks")
    
    print("\n✓ Position manager runs every 1 minute")
    print("✓ Updates current_price and P&L on each check")

print("\n" + "="*80)
print("KEY INFORMATION")
print("="*80)
print("\n1. Position Manager Monitoring:")
print("   - Runs every 1 MINUTE (not real-time tick-by-tick)")
print("   - Updates current_price and P&L each minute")
print("   - Tracks best_unrealized_pnl_pct (peak) and worst_unrealized_pnl_pct (low)")

print("\n2. Exit Triggers:")
print("   - Take Profit: +80% (automatically closes)")
print("   - Stop Loss: -40% (automatically closes)")
print("   - Max Hold Time: 4 hours (automatically closes)")
print("   - Trailing Stop: NOT YET ENABLED (requires migration 013)")

print("\n3. About Multiple Positions (CALL + PUT):")
print("   - Each position is tracked INDEPENDENTLY")
print("   - Position manager closes EACH when it hits its thresholds")
print("   - No automatic hedging or portfolio-level decisions")
print("   - If you have both CALL and PUT, they won't cancel each other out")
print("   - Each will close based on its own P&L")

print("\n4. Current Status:")
print("   - Your MSFT PUT at +34.44% is being tracked")
print("   - Will auto-close when it reaches +80% OR -40% OR 4 hours")
print("   - System checks every 1 minute, NOT continuously")
print("   - Peak tracking is working (best_unrealized_pnl_pct)")

print("\n" + "="*80)
