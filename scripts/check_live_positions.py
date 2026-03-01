#!/usr/bin/env python3
"""Check current open positions with live P&L"""
import boto3
import json

client = boto3.client('lambda', region_name='us-west-2')

# Get current open positions with P&L
response = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({
        'sql': '''
        SELECT 
            id,
            ticker,
            instrument_type,
            account_name,
            entry_price,
            current_price,
            CASE 
                WHEN entry_price > 0 
                THEN ((current_price - entry_price) / entry_price) * 100 
                ELSE 0 
            END as pnl_pct,
            current_pnl_dollars,
            EXTRACT(EPOCH FROM (NOW() - entry_time))/60 as age_minutes,
            entry_time,
            stop_loss,
            take_profit,
            lifecycle_state,
            peak_price
        FROM active_positions 
        WHERE status = 'open'
        ORDER BY pnl_pct DESC
        '''
    })
)

result = json.loads(json.loads(response['Payload'].read())['body'])
rows = result.get('rows', [])

print('=' * 90)
print('CURRENT OPEN POSITIONS - LIVE P&L')
print('=' * 90)
print()

if not rows:
    print('No open positions')
else:
    winners = [r for r in rows if float(r['pnl_pct']) > 0]
    losers = [r for r in rows if float(r['pnl_pct']) < 0]
    
    print(f'Total Open: {len(rows)} positions')
    print(f'Winners: {len(winners)} positions')
    print(f'Losers: {len(losers)} positions')
    print()
    print('-' * 90)
    
    for row in rows:
        pnl_pct = float(row['pnl_pct'])
        pnl_dollars = float(row.get('current_pnl_dollars') or 0)
        age_min = int(float(row['age_minutes']))
        age_hours = age_min // 60
        age_min_remainder = age_min % 60
        
        status_icon = '🟢' if pnl_pct > 0 else '🔴'
        
        print(f"{status_icon} {row['ticker']:6s} {row['instrument_type']:5s} ({row['account_name']:5s})")
        print(f"   Entry: ${float(row['entry_price']):.2f} → Current: ${float(row['current_price']):.2f}")
        print(f"   P&L: {pnl_pct:+.1f}% (${pnl_dollars:+,.0f})")
        
        # Show peak if available
        peak = row.get('peak_price')
        if peak and float(peak) > float(row['entry_price']):
            peak_pct = ((float(peak) - float(row['entry_price'])) / float(row['entry_price'])) * 100
            print(f"   Peak: ${float(peak):.2f} (+{peak_pct:.1f}%)")
        
        print(f"   Age: {age_hours}h {age_min_remainder}m | State: {row.get('lifecycle_state', 'N/A')}")
        print(f"   Stop: ${float(row['stop_loss']):.2f} | Target: ${float(row['take_profit']):.2f}")
        print()
    
    # Summary stats
    total_pnl = sum(float(r.get('current_pnl_dollars') or 0) for r in rows)
    avg_pnl_pct = sum(float(r['pnl_pct']) for r in rows) / len(rows)
    best_pnl = max(float(r['pnl_pct']) for r in rows)
    worst_pnl = min(float(r['pnl_pct']) for r in rows)
    
    print('=' * 90)
    print(f'SUMMARY: {len(winners)} winners, {len(losers)} losers')
    print(f'Total Unrealized P&L: ${total_pnl:+,.0f}')
    print(f'Average P&L: {avg_pnl_pct:+.1f}%')
    print(f'Best: +{best_pnl:.1f}% | Worst: {worst_pnl:.1f}%')
    print('=' * 90)
