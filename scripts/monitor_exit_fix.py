#!/usr/bin/env python3
"""
Monitor BMY and WMT positions to verify exit fix is working
Run this to watch if positions hold >30 minutes with new exit logic
"""
import boto3
import json
import time
from datetime import datetime

client = boto3.client('lambda', region_name='us-west-2')

def check_positions():
    """Check current positions and their hold times"""
    sql = """
    SELECT 
        id,
        ticker,
        option_symbol,
        entry_price,
        current_price,
        current_pnl_percent,
        stop_loss,
        take_profit,
        entry_time,
        status,
        EXTRACT(EPOCH FROM (NOW() - entry_time))/60 as hold_minutes
    FROM active_positions
    WHERE ticker IN ('BMY', 'WMT')
    AND status = 'open'
    """
    
    response = client.invoke(
        FunctionName='ops-pipeline-db-query',
        Payload=json.dumps({'sql': sql})
    )
    
    result = json.loads(json.load(response['Payload'])['body'])
    return result.get('rows', [])

def check_recent_closes():
    """Check if positions closed and why"""
    sql = """
    SELECT 
        ticker,
        instrument_symbol,
        holding_minutes,
        pnl_pct,
        exit_reason,
        exit_ts
    FROM position_history
    WHERE ticker IN ('BMY', 'WMT')
    AND exit_ts > NOW() - INTERVAL '30 minutes'
    ORDER BY exit_ts DESC
    """
    
    response = client.invoke(
        FunctionName='ops-pipeline-db-query',
        Payload=json.dumps({'sql': sql})
    )
    
    result = json.loads(json.load(response['Payload'])['body'])
    return result.get('rows', [])

print("=" * 80)
print("Exit Fix Monitor - Watching BMY and WMT Positions")
print("=" * 80)
print()
print("Expected behavior with fix:")
print("  ✅ Positions hold >= 30 minutes (not 1-2 minutes)")
print("  ✅ Stop loss at -40% (not -25%)")
print("  ✅ Take profit at +80% (not +50%)")
print("  ✅ 'Too early to exit' log messages in first 30 minutes")
print()
print("Press Ctrl+C to stop monitoring")
print()

try:
    while True:
        now = datetime.now().strftime("%H:%M:%S")
        
        # Check open positions
        positions = check_positions()
        
        if positions:
            print(f"\n[{now}] Open Positions:")
            for pos in positions:
                hold_min = pos['hold_minutes']
                pnl = pos['current_pnl_percent']
                
                status_icon = "🟢" if hold_min >= 30 else "🟡"
                print(f"  {status_icon} {pos['ticker']} #{pos['id']}: {hold_min:.1f} min, P&L {pnl:.1f}%")
                print(f"     Entry: ${pos['entry_price']:.2f}, Current: ${pos['current_price']:.2f}")
                print(f"     Stop: ${pos['stop_loss']:.2f} (-{((pos['entry_price']-pos['stop_loss'])/pos['entry_price']*100):.1f}%)")
                print(f"     Target: ${pos['take_profit']:.2f} (+{((pos['take_profit']-pos['entry_price'])/pos['entry_price']*100):.1f}%)")
                
                if hold_min >= 30:
                    print(f"     ✅ HOLDING WELL! New exit logic working!")
                elif hold_min < 10:
                    print(f"     ⚠️ May close soon if old logic still active")
        
        # Check recent closes
        closes = check_recent_closes()
        
        if closes:
            print(f"\n[{now}] Recent Closes:")
            for close in closes:
                hold_min = close['holding_minutes']
                
                if hold_min < 10:
                    icon = "❌"
                    verdict = "TOO FAST - old logic"
                elif hold_min >= 30:
                    icon = "✅"
                    verdict = "GOOD - new logic working!"
                else:
                    icon = "🟡"
                    verdict = "Borderline"
                
                print(f"  {icon} {close['ticker']}: {hold_min:.1f} min, P&L {close['pnl_pct']:.1f}%")
                print(f"     Exit reason: {close['exit_reason']}")
                print(f"     {verdict}")
        
        if not positions and not closes:
            print(f"[{now}] No BMY or WMT positions yet...")
            print("  Waiting for positions to be created and synced to database")
        
        time.sleep(30)  # Check every 30 seconds
        
except KeyboardInterrupt:
    print("\n\nMonitoring stopped")
    print("\nFinal check:")
    
    closes = check_recent_closes()
    if closes:
        print("\nResults:")
        for close in closes:
            hold_min = close['holding_minutes']
            if hold_min >= 30:
                print(f"  ✅ {close['ticker']}: {hold_min:.1f} min - NEW EXIT LOGIC WORKING!")
            else:
                print(f"  ❌ {close['ticker']}: {hold_min:.1f} min - Closed too fast")
    else:
        print("  No positions closed yet - still waiting")
