#!/usr/bin/env python3
"""
Test Alpaca option pricing API to diagnose MSFT price issue
Manual verification of what Alpaca returns
"""
import boto3
import json
from alpaca.trading.client import TradingClient
from alpaca.data.historical import OptionHistoricalDataClient
from alpaca.data.requests import OptionLatestQuoteRequest

# Get credentials
secrets = boto3.client('secretsmanager', region_name='us-west-2')
secret = secrets.get_secret_value(SecretId='ops-pipeline/alpaca')
creds = json.loads(secret['SecretString'])

# Create clients
trading_client = TradingClient(
    api_key=creds['api_key'],
    secret_key=creds['api_secret'],
    paper=True
)

data_client = OptionHistoricalDataClient(
    api_key=creds['api_key'],
    secret_key=creds['api_secret']
)

print('=' * 80)
print('TESTING ALPACA OPTION PRICING APIS')
print('=' * 80)
print()

# Test 1: Get position from positions API (what position manager uses)
print('Test 1: Positions API (current method)')
print('-' * 80)
try:
    position = trading_client.get_open_position('MSFT260220P00410000')
    print(f"✅ Position found via positions API")
    print(f"   Symbol: {position.symbol}")
    print(f"   Qty: {position.qty}")
    print(f"   Avg Entry: ${float(position.avg_entry_price):.2f}")
    print(f"   Current Price: ${float(position.current_price):.2f}")
    print(f"   Market Value: ${float(position.market_value):.2f}")
    print(f"   Unrealized P&L: ${float(position.unrealized_pl):.2f}")
    print(f"   Unrealized P&L %: {float(position.unrealized_plpc)*100:.2f}%")
    print()
    
    current_from_positions = float(position.current_price)
except Exception as e:
    print(f"❌ Positions API failed: {e}")
    current_from_positions = None
    print()

# Test 2: Get latest quote (recommended method)
print('Test 2: Latest Quote API (recommended method)')
print('-' * 80)
try:
    request = OptionLatestQuoteRequest(symbol_or_symbols='MSFT260220P00410000')
    quotes = data_client.get_option_latest_quote(request)
    
    if 'MSFT260220P00410000' in quotes:
        quote = quotes['MSFT260220P00410000']
        bid = float(quote.bid_price)
        ask = float(quote.ask_price)
        mid = (bid + ask) / 2
        
        print(f"✅ Quote found via latest quote API")
        print(f"   Bid: ${bid:.2f}")
        print(f"   Ask: ${ask:.2f}")
        print(f"   Mid (recommended): ${mid:.2f}")
        print(f"   Bid Size: {quote.bid_size}")
        print(f"   Ask Size: {quote.ask_size}")
        print()
        
        current_from_quotes = mid
    else:
        print(f"❌ Symbol not found in quotes")
        current_from_quotes = None
except Exception as e:
    print(f"❌ Latest Quote API failed: {e}")
    current_from_quotes = None
    print()

# Test 3: Get all positions and compare
print('Test 3: All Positions Check')
print('-' * 80)
try:
    all_positions = list(trading_client.get_all_positions())
    print(f"Total open positions: {len(all_positions)}")
    print()
    print("All option positions:")
    for pos in all_positions:
        if len(pos.symbol) > 10:  # It's an option
            pnl_pct = float(pos.unrealized_plpc) * 100
            print(f"  {pos.symbol}: ${float(pos.current_price):.2f} ({pnl_pct:+.1f}%)")
    print()
except Exception as e:
    print(f"❌ Failed: {e}")
    print()

# Summary
print('=' * 80)
print('PRICING COMPARISON')
print('=' * 80)
print()
if current_from_positions:
    print(f"Positions API: ${current_from_positions:.2f}")
if current_from_quotes:
    print(f"Quotes API:    ${current_from_quotes:.2f}")
print(f"Database:      $5.90")
print(f"Your Alpaca Dashboard: $11.15")
print()

print('RECOMMENDATION:')
if current_from_positions and abs(current_from_positions - 11.15) < 0.50:
    print('✅ Positions API returning correct price')
    print('   Issue is likely in position manager update logic')
elif current_from_quotes and abs(current_from_quotes - 11.15) < 0.50:
    print('✅ Quotes API returning correct price')
    print('   Recommendation: Switch from positions API to quotes API')
    print('   Use mid-price: (bid + ask) / 2')
else:
    print('⚠️ Both APIs not matching Alpaca dashboard')
    print('   May be timing issue or cache')
