#!/usr/bin/env python3
"""
Test Options Validation System
Demonstrates how we determine if an option trade is GOOD or BAD

This test:
1. Fetches real option chain from Alpaca
2. Runs validation gates
3. Shows which contracts pass/fail and WHY
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services', 'dispatcher'))

import requests
from datetime import datetime, timedelta, timezone
from alpaca.options import (
    AlpacaOptionsAPI,
    get_option_chain_for_strategy,
    select_optimal_strike,
    validate_option_liquidity
)

# Alpaca credentials
API_KEY = "PKG7MU6D3EPFNCMVHL6QQSADRS"
API_SECRET = "BBsd4MCQKKWfCZahkM2jJMXhD4BSE8ddcVkoVR6kXjM9"

def test_option_validation():
    """
    Full end-to-end test of options validation system
    """
    print("=" * 80)
    print("OPTIONS VALIDATION TEST")
    print("=" * 80)
    print()
    
    # Initialize API
    api = AlpacaOptionsAPI(
        api_key=API_KEY,
        api_secret=API_SECRET,
        paper_trading=True
    )
    
    # Test parameters
    ticker = "SPY"
    current_price = 600.0  # Approximate SPY price
    strategy = "day_trade"
    option_type = "call"
    
    print(f"Test Parameters:")
    print(f"  Ticker: {ticker}")
    print(f"  Stock Price: ${current_price:.2f}")
    print(f"  Strategy: {strategy}")
    print(f"  Option Type: {option_type}")
    print()
    
    # Step 1: Fetch option chain
    print("-" * 80)
    print("STEP 1: Fetch Real Option Chain from Alpaca API")
    print("-" * 80)
    
    today = datetime.now(timezone.utc).date()
    min_date = today.strftime('%Y-%m-%d')
    max_date = (today + timedelta(days=7)).strftime('%Y-%m-%d')
    
    strike_min = current_price * 0.95
    strike_max = current_price * 1.05
    
    print(f"  API Request:")
    print(f"    Expiration: {min_date} to {max_date} (next 7 days)")
    print(f"    Strike Range: ${strike_min:.2f} to ${strike_max:.2f}")
    print(f"    Type: {option_type}")
    print()
    
    contracts = api.get_option_chain(
        ticker=ticker,
        expiration_date_gte=min_date,
        expiration_date_lte=max_date,
        option_type=option_type,
        strike_price_gte=strike_min,
        strike_price_lte=strike_max
    )
    
    print(f"  ✅ Fetched {len(contracts)} contracts")
    print()
    
    if not contracts:
        print("  ❌ NO CONTRACTS FOUND - Would fall back to simulation")
        return
    
    # Step 2: Show sample contracts
    print("-" * 80)
    print("STEP 2: Sample Contracts Returned")
    print("-" * 80)
    
    for i, contract in enumerate(contracts[:5]):
        symbol = contract['symbol']
        strike = contract['strike_price']
        bid = contract['bid']
        ask = contract['ask']
        exp = contract['expiration_date']
        
        print(f"  Contract {i+1}:")
        print(f"    Symbol: {symbol}")
        print(f"    Strike: ${strike:.2f}")
        print(f"    Bid/Ask: ${bid:.2f} / ${ask:.2f}")
        print(f"    Expiration: {exp}")
        print()
    
    # Step 3: Select optimal strike
    print("-" * 80)
    print("STEP 3: Select Optimal Strike")
    print("-" * 80)
    
    best_contract = select_optimal_strike(
        current_price=current_price,
        option_type=option_type,
        strategy=strategy,
        contracts=contracts
    )
    
    if not best_contract:
        print("  ❌ NO SUITABLE STRIKE FOUND")
        return
    
    print(f"  Selected Contract:")
    print(f"    Symbol: {best_contract['symbol']}")
    print(f"    Strike: ${best_contract['strike_price']:.2f}")
    print(f"    Bid: ${best_contract['bid']:.2f}")
    print(f"    Ask: ${best_contract['ask']:.2f}")
    print(f"    Expiration: {best_contract['expiration_date']}")
    
    if 'delta' in best_contract and best_contract['delta'] != 0:
        print(f"    Greeks:")
        print(f"      Delta: {best_contract['delta']:.3f}")
        print(f"      Theta: {best_contract.get('theta', 0):.4f}")
        print(f"      IV: {best_contract.get('implied_volatility', 0):.2%}")
    print()
    
    # Step 4: Run validation gates
    print("-" * 80)
    print("STEP 4: Run Quality Gates")
    print("-" * 80)
    
    bid = float(best_contract['bid'])
    ask = float(best_contract['ask'])
    
    # Gate 1: Bid/Ask exists
    print(f"  Gate 1: Bid/Ask Price Check")
    if bid > 0 and ask > 0:
        print(f"    ✅ PASS: Bid ${bid:.2f} / Ask ${ask:.2f}")
    else:
        print(f"    ❌ FAIL: Invalid prices (Bid: ${bid:.2f}, Ask: ${ask:.2f})")
        print(f"    → Would fall back to SIMULATION")
        return
    
    # Gate 2: Spread check
    print(f"  Gate 2: Bid/Ask Spread Check")
    mid = (bid + ask) / 2
    spread_pct = (ask - bid) / mid * 100
    max_spread = 10.0
    
    if spread_pct <= max_spread:
        print(f"    ✅ PASS: Spread {spread_pct:.2f}% < {max_spread:.0f}%")
    else:
        print(f"    ❌ FAIL: Spread {spread_pct:.2f}% > {max_spread:.0f}%")
        print(f"    → Spread too wide, would fall back to SIMULATION")
        return
    
    # Gate 3: Expiration check
    print(f"  Gate 3: Expiration Check")
    exp_date = datetime.strptime(best_contract['expiration_date'], '%Y-%m-%d').replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    
    if exp_date > now:
        days_left = (exp_date - now).days
        print(f"    ✅ PASS: {days_left} days until expiration")
    else:
        print(f"    ❌ FAIL: Contract expired")
        return
    
    print()
    print("  " + "=" * 76)
    print(f"  ✅ ALL GATES PASSED - This contract is TRADEABLE!")
    print("  " + "=" * 76)
    print()
    
    # Step 5: Show what would be executed
    print("-" * 80)
    print("STEP 5: Execution Preview")
    print("-" * 80)
    
    # Position sizing
    account_buying_power = 100000.0  # Your account
    max_risk_pct = 5.0
    
    option_price = mid
    cost_per_contract = option_price * 100
    max_risk_dollars = account_buying_power * (max_risk_pct / 100)
    num_contracts = int(max_risk_dollars / cost_per_contract)
    
    if num_contracts == 0:
        num_contracts = 1
    
    total_cost = num_contracts * cost_per_contract
    
    print(f"  Position Sizing:")
    print(f"    Account Buying Power: ${account_buying_power:,.2f}")
    print(f"    Max Risk ({max_risk_pct}%): ${max_risk_dollars:,.2f}")
    print(f"    Option Price (mid): ${option_price:.2f}")
    print(f"    Cost per Contract: ${cost_per_contract:.2f}")
    print(f"    Number of Contracts: {num_contracts}")
    print(f"    Total Cost: ${total_cost:.2f}")
    print()
    
    print(f"  Order That Would Be Placed:")
    print(f"    POST https://paper-api.alpaca.markets/v2/orders")
    print(f"    {{")
    print(f'      "symbol": "{best_contract["symbol"]}",')
    print(f'      "qty": "{num_contracts}",')
    print(f'      "side": "buy",')
    print(f'      "type": "market",')
    print(f'      "time_in_force": "day"')
    print(f"    }}")
    print()
    
    # Step 6: Actually test placing the order
    print("-" * 80)
    print("STEP 6: Test Actual Order Placement")
    print("-" * 80)
    
    order_data = {
        "symbol": best_contract['symbol'],
        "qty": str(num_contracts),
        "side": "buy",
        "type": "market",
        "time_in_force": "day"
    }
    
    headers = {
        'APCA-API-KEY-ID': API_KEY,
        'APCA-API-SECRET-KEY': API_SECRET,
        'Content-Type': 'application/json'
    }
    
    print(f"  Placing order for {num_contracts} contract(s) of {best_contract['symbol']}...")
    
    try:
        response = requests.post(
            "https://paper-api.alpaca.markets/v2/orders",
            headers=headers,
            json=order_data,
            timeout=10
        )
        
        if response.status_code == 200:
            order = response.json()
            print(f"  ✅ ORDER PLACED SUCCESSFULLY!")
            print(f"    Order ID: {order['id']}")
            print(f"    Status: {order['status']}")
            print(f"    Submitted At: {order['submitted_at']}")
            print()
            print(f"  🎯 CHECK YOUR ALPACA DASHBOARD:")
            print(f"     https://app.alpaca.markets/paper/dashboard")
            print()
            return order['id']
        else:
            print(f"  ❌ ORDER REJECTED BY ALPACA")
            print(f"    Status: {response.status_code}")
            print(f"    Response: {response.text[:200]}")
            print(f"    → System would fall back to SIMULATION")
            
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        print(f"    → System would fall back to SIMULATION")

if __name__ == "__main__":
    test_option_validation()
