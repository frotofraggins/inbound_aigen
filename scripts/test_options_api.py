#!/usr/bin/env python3
"""
Test Options API Module
Validates Alpaca Options API integration and core functionality.

Run this BEFORE deploying to verify:
1. Can connect to Alpaca Options API
2. Can fetch option chains
3. Strike selection works correctly
4. Position sizing calculations are accurate
5. Liquidity validation functions properly
"""

import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services', 'dispatcher'))

from alpaca.options import (
    AlpacaOptionsAPI,
    select_optimal_strike,
    validate_option_liquidity,
    calculate_position_size,
    format_option_symbol,
    get_option_chain_for_strategy
)

def test_api_connection():
    """Test 1: Verify API connection"""
    print("\n" + "="*60)
    print("TEST 1: API Connection")
    print("="*60)
    
    try:
        api_key = os.environ.get('ALPACA_KEY_ID')
        api_secret = os.environ.get('ALPACA_SECRET_KEY')
        
        if not api_key or not api_secret:
            print("❌ FAIL: Missing ALPACA_KEY_ID or ALPACA_SECRET_KEY environment variables")
            return False
        
        api = AlpacaOptionsAPI(api_key, api_secret, paper_trading=True)
        print("✅ PASS: Successfully initialized Alpaca Options API")
        return True
        
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False

def test_fetch_option_chain():
    """Test 2: Fetch real option chain"""
    print("\n" + "="*60)
    print("TEST 2: Fetch Option Chain")
    print("="*60)
    
    try:
        api_key = os.environ['ALPACA_KEY_ID']
        api_secret = os.environ['ALPACA_SECRET_KEY']
        api = AlpacaOptionsAPI(api_key, api_secret, paper_trading=True)
        
        # Fetch AAPL call options expiring in next 2 days
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        day_after = (datetime.now() + timedelta(days=2)).strftime('%Y-%m-%d')
        
        contracts = api.get_option_chain(
            ticker='AAPL',
            expiration_date_gte=tomorrow,
            expiration_date_lte=day_after,
            option_type='call'
        )
        
        if len(contracts) == 0:
            print("⚠️  WARN: No contracts found (market may be closed or no options available)")
            print("    This is OK if testing outside market hours")
            return True
        
        print(f"✅ PASS: Fetched {len(contracts)} option contracts")
        
        # Display sample contracts
        print("\nSample contracts:")
        for i, c in enumerate(contracts[:3]):
            print(f"  {i+1}. {c.get('symbol', 'N/A')}")
            print(f"     Strike: ${c.get('strike_price', 0)}")
            print(f"     Expiry: {c.get('expiration_date', 'N/A')}")
            print(f"     Bid/Ask: ${c.get('bid', 0)} / ${c.get('ask', 0)}")
            print(f"     Volume: {c.get('open_interest', 0)}")
        
        return True
        
    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_strike_selection():
    """Test 3: Strike selection logic"""
    print("\n" + "="*60)
    print("TEST 3: Strike Selection")
    print("="*60)
    
    # Mock contracts
    current_price = 150.0
    contracts = [
        {'strike_price': 145.0, 'type': 'call'},  # ITM
        {'strike_price': 150.0, 'type': 'call'},  # ATM
        {'strike_price': 152.0, 'type': 'call'},  # Slightly OTM
        {'strike_price': 155.0, 'type': 'call'},  # OTM
        {'strike_price': 160.0, 'type': 'call'},  # Far OTM
    ]
    
    try:
        # Test day_trade strategy (should pick OTM ~1.5% out)
        selected = select_optimal_strike(current_price, 'call', 'day_trade', contracts)
        expected_strike = 152.0  # Closest to 150 * 1.015 = 152.25
        
        if selected and selected['strike_price'] == expected_strike:
            print(f"✅ PASS: Day trade selected strike ${expected_strike} (OTM)")
        else:
            print(f"❌ FAIL: Expected ${expected_strike}, got ${selected.get('strike_price') if selected else None}")
            return False
        
        # Test swing_trade strategy (should pick ATM)
        selected = select_optimal_strike(current_price, 'call', 'swing_trade', contracts)
        expected_strike = 150.0
        
        if selected and selected['strike_price'] == expected_strike:
            print(f"✅ PASS: Swing trade selected strike ${expected_strike} (ATM)")
        else:
            print(f"❌ FAIL: Expected ${expected_strike}, got ${selected.get('strike_price') if selected else None}")
            return False
        
        # Test conservative strategy (should pick ITM)
        selected = select_optimal_strike(current_price, 'call', 'conservative', contracts)
        expected_strike = 145.0  # Closest to 150 * 0.97 = 145.5
        
        if selected and selected['strike_price'] == expected_strike:
            print(f"✅ PASS: Conservative selected strike ${expected_strike} (ITM)")
        else:
            print(f"❌ FAIL: Expected ${expected_strike}, got ${selected.get('strike_price') if selected else None}")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_liquidity_validation():
    """Test 4: Liquidity validation"""
    print("\n" + "="*60)
    print("TEST 4: Liquidity Validation")
    print("="*60)
    
    try:
        # Test 1: Good liquidity
        good_contract = {
            'open_interest': 150,
            'bid': 2.00,
            'ask': 2.10,
            'expiration_date': (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        }
        
        is_valid, reason = validate_option_liquidity(good_contract)
        if is_valid:
            print("✅ PASS: Accepted contract with good liquidity")
        else:
            print(f"❌ FAIL: Rejected good contract: {reason}")
            return False
        
        # Test 2: Low volume
        low_volume_contract = {
            'open_interest': 50,  # Below minimum 100
            'bid': 2.00,
            'ask': 2.10,
            'expiration_date': (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        }
        
        is_valid, reason = validate_option_liquidity(low_volume_contract)
        if not is_valid and 'open interest' in reason.lower():
            print("✅ PASS: Rejected contract with low volume")
        else:
            print(f"❌ FAIL: Should have rejected low volume contract")
            return False
        
        # Test 3: Wide spread
        wide_spread_contract = {
            'open_interest': 150,
            'bid': 2.00,
            'ask': 2.50,  # 25% spread
            'expiration_date': (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        }
        
        is_valid, reason = validate_option_liquidity(wide_spread_contract)
        if not is_valid and 'spread' in reason.lower():
            print("✅ PASS: Rejected contract with wide spread")
        else:
            print(f"❌ FAIL: Should have rejected wide spread contract")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_position_sizing():
    """Test 5: Position sizing calculations"""
    print("\n" + "="*60)
    print("TEST 5: Position Sizing")
    print("="*60)
    
    try:
        # Test 1: Day trade with $100,000 account
        option_price = 2.50
        buying_power = 100000.0
        
        contracts, total_cost, rationale = calculate_position_size(
            option_price, buying_power, max_risk_pct=5.0, strategy='day_trade'
        )
        
        # Expected: 5% of $100K = $5,000 / $250 per contract = 20 contracts
        expected_contracts = 20
        expected_cost = 20 * 250  # $5,000
        
        if contracts == expected_contracts and abs(total_cost - expected_cost) < 1:
            print(f"✅ PASS: Day trade sizing: {contracts} contracts, ${total_cost:.2f} total")
        else:
            print(f"❌ FAIL: Expected {expected_contracts} contracts, got {contracts}")
            return False
        
        # Test 2: Swing trade with $100,000 account (allows more risk)
        contracts, total_cost, rationale = calculate_position_size(
            option_price, buying_power, max_risk_pct=5.0, strategy='swing_trade'
        )
        
        # Expected: 10% of $100K (capped at 20%) = $10,000 / $250 = 40 contracts
        expected_contracts = 40
        
        if contracts == expected_contracts:
            print(f"✅ PASS: Swing trade sizing: {contracts} contracts (2x day trade)")
        else:
            print(f"❌ FAIL: Expected {expected_contracts} contracts, got {contracts}")
            return False
        
        # Test 3: Small account (insufficient capital)
        contracts, total_cost, rationale = calculate_position_size(
            option_price, 100.0, max_risk_pct=5.0, strategy='day_trade'
        )
        
        # Expected: 5% of $100 = $5 / $250 = 0 contracts (but min 1 if affordable)
        # Since 1 contract costs $250 and we only have $100, should be 0
        if contracts == 0:
            print(f"✅ PASS: Correctly returns 0 contracts for insufficient capital")
        else:
            print(f"❌ FAIL: Should return 0 contracts, got {contracts}")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_option_symbol_formatting():
    """Test 6: OCC symbol formatting"""
    print("\n" + "="*60)
    print("TEST 6: Option Symbol Formatting")
    print("="*60)
    
    try:
        # Test case: AAPL Jan 31 2026 $150 Call
        symbol = format_option_symbol('AAPL', '2026-01-31', 'call', 150.0)
        expected = 'AAPL  260131C00150000'
        
        if symbol == expected:
            print(f"✅ PASS: Generated correct OCC symbol: {symbol}")
        else:
            print(f"❌ FAIL: Expected {expected}, got {symbol}")
            return False
        
        # Test case: SPY Feb 14 2026 $450.50 Put
        symbol = format_option_symbol('SPY', '2026-02-14', 'put', 450.50)
        expected = 'SPY   260214P00450500'
        
        if symbol == expected:
            print(f"✅ PASS: Generated correct OCC symbol: {symbol}")
        else:
            print(f"❌ FAIL: Expected {expected}, got {symbol}")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("OPTIONS API MODULE TEST SUITE")
    print("=" * 60)
    print("\nTesting Alpaca Options API integration...")
    print("Make sure ALPACA_KEY_ID and ALPACA_SECRET_KEY are set!")
    
    tests = [
        ("API Connection", test_api_connection),
        ("Fetch Option Chain", test_fetch_option_chain),
        ("Strike Selection", test_strike_selection),
        ("Liquidity Validation", test_liquidity_validation),
        ("Position Sizing", test_position_sizing),
        ("Symbol Formatting", test_option_symbol_formatting),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            passed = test_func()
            results.append((test_name, passed))
        except Exception as e:
            print(f"\n❌ FATAL ERROR in {test_name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed_count}/{total_count} tests passed")
    
    if passed_count == total_count:
        print("\n🎉 ALL TESTS PASSED! Options API module is ready for use.")
        return 0
    else:
        print(f"\n⚠️  {total_count - passed_count} test(s) failed. Fix issues before deploying.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
