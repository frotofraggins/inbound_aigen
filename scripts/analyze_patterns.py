#!/usr/bin/env python3
"""
Quick pattern analyzer using Lambda for database access
"""

import boto3
import json
from collections import defaultdict
from datetime import datetime, timedelta

client = boto3.client('lambda', region_name='us-west-2')

def query_db(sql):
    """Query database via Lambda"""
    response = client.invoke(
        FunctionName='ops-pipeline-db-query',
        Payload=json.dumps({'sql': sql})
    )
    result = json.loads(response['Payload'].read())
    return json.loads(result['body'])

print("=" * 80)
print("HISTORICAL PATTERN ANALYZER")
print("=" * 80)

# Fetch trades
print("\nFetching trade history...")
trades_data = query_db('''
    SELECT 
        id, ticker, pnl_pct, exit_reason, strategy_type,
        EXTRACT(EPOCH FROM (exit_time - entry_time))/60 as hold_minutes,
        best_unrealized_pnl_pct
    FROM position_history
    WHERE exit_time >= NOW() - INTERVAL '7 days'
    ORDER BY exit_time DESC
''')

if not trades_data.get('rows'):
    print("No trades found")
    exit(0)

trades = trades_data['rows']
print(f"Found {len(trades)} trades")

# Categorize
big_winners = []
good_winners = []
small_winners = []
small_losers = []
big_losers = []

for trade in trades:
    pnl = float(trade['pnl_pct'] or 0)
    if pnl >= 20:
        big_winners.append(trade)
    elif pnl >= 10:
        good_winners.append(trade)
    elif pnl > 0:
        small_winners.append(trade)
    elif pnl >= -20:
        small_losers.append(trade)
    else:
        big_losers.append(trade)

print("\n" + "=" * 80)
print("TRADE DISTRIBUTION")
print("=" * 80)
print(f"Big winners (>20%):      {len(big_winners)}")
print(f"Good winners (10-20%):   {len(good_winners)}")
print(f"Small winners (0-10%):   {len(small_winners)}")
print(f"Small losers (0 to -20%): {len(small_losers)}")
print(f"Big losers (<-20%):      {len(big_losers)}")

# Win rate
total = len(trades)
winners = len(big_winners) + len(good_winners) + len(small_winners)
win_rate = (winners / total * 100) if total > 0 else 0

print("\n" + "=" * 80)
print("KEY INSIGHTS")
print("=" * 80)
print(f"📊 Overall win rate: {win_rate:.1f}% ({winners}/{total} trades)")

# Analyze patterns
def analyze_category(trades_list, category_name):
    if not trades_list:
        return
    
    print(f"\n{category_name.upper()} ({len(trades_list)} trades):")
    
    # Tickers
    tickers = defaultdict(int)
    strategies = defaultdict(int)
    reasons = defaultdict(int)
    hold_times = []
    
    for t in trades_list:
        tickers[t['ticker']] += 1
        if t.get('strategy_type'):
            strategies[t['strategy_type']] += 1
        if t.get('exit_reason'):
            reasons[t['exit_reason']] += 1
        if t.get('hold_minutes'):
            hold_times.append(float(t['hold_minutes']))
    
    # Top ticker
    if tickers:
        top_ticker = max(tickers.items(), key=lambda x: x[1])
        print(f"  Top ticker: {top_ticker[0]} ({top_ticker[1]} trades)")
    
    # Top strategy
    if strategies:
        top_strategy = max(strategies.items(), key=lambda x: x[1])
        print(f"  Top strategy: {top_strategy[0]} ({top_strategy[1]} trades)")
    
    # Top exit reason
    if reasons:
        top_reason = max(reasons.items(), key=lambda x: x[1])
        print(f"  Main exit: {top_reason[0]} ({top_reason[1]} trades)")
    
    # Avg hold time
    if hold_times:
        avg_hold = sum(hold_times) / len(hold_times)
        print(f"  Avg hold time: {avg_hold:.0f} minutes")

analyze_category(big_winners, "Big Winners")
analyze_category(big_losers, "Big Losers")

# Compare winners vs losers
if big_winners and big_losers:
    winner_hold = sum(float(t.get('hold_minutes') or 0) for t in big_winners) / len(big_winners)
    loser_hold = sum(float(t.get('hold_minutes') or 0) for t in big_losers) / len(big_losers)
    print(f"\n⏱️  Winners held {winner_hold:.0f} min vs losers {loser_hold:.0f} min")

print("\n" + "=" * 80)
print("ANALYSIS COMPLETE")
print("=" * 80)
