#!/usr/bin/env python3
"""
EMERGENCY: Manually close all open option positions
Use when market close protection fails
"""
import boto3
import json
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import ClosePositionRequest
from alpaca.trading.enums import OrderSide

# Get Alpaca credentials from Secrets Manager
secrets = boto3.client('secretsmanager', region_name='us-west-2')

# Large account
large_secret = secrets.get_secret_value(SecretId='ops-pipeline/alpaca')
large_data = json.loads(large_secret['SecretString'])

# Tiny account  
tiny_secret = secrets.get_secret_value(SecretId='ops-pipeline/alpaca/tiny')
tiny_data = json.loads(tiny_secret['SecretString'])

# Create clients
large_client = TradingClient(
    api_key=large_data['api_key'],
    secret_key=large_data['api_secret'],
    paper=True
)

tiny_client = TradingClient(
    api_key=tiny_data['api_key'],
    secret_key=tiny_data['api_secret'],
    paper=True
)

def close_all_options(client, account_name):
    """Close all option positions for an account"""
    try:
        positions = list(client.get_all_positions())
        closed_count = 0
        
        for pos in positions:
            symbol = pos.symbol
            # Options have long symbols like META260209C00722500
            if len(symbol) > 10:  # It's an option
                print(f"Closing {account_name} option: {symbol}")
                try:
                    # Close position at market
                    client.close_position(symbol)
                    closed_count += 1
                    print(f"  ✓ Closed {symbol}")
                except Exception as e:
                    print(f"  ✗ Failed to close {symbol}: {e}")
        
        return closed_count
    except Exception as e:
        print(f"Error closing {account_name} positions: {e}")
        return 0

print("=" * 80)
print("EMERGENCY OPTION CLOSE")
print("=" * 80)
print()

print("Closing large account options...")
large_closed = close_all_options(large_client, "large")
print()

print("Closing tiny account options...")
tiny_closed = close_all_options(tiny_client, "tiny")
print()

print("=" * 80)
print(f"COMPLETE: Closed {large_closed + tiny_closed} option positions")
print("=" * 80)
