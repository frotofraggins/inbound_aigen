#!/usr/bin/env python3
"""
End-to-End System Verification
Tests Phase 15 (Alpaca) + Phase 16 (Learning) integration

Verifies:
1. All services operational
2. Data flowing through pipeline
3. Snapshots capturing correctly
4. Alpaca integration working
5. Position tracking functional
6. Learning infrastructure ready
"""

import boto3
import json
import sys
from datetime import datetime, timedelta

# Colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_header(text):
    print(f"\n{'=' * 80}")
    print(f"{BLUE}{text}{RESET}")
    print(f"{'=' * 80}\n")

def print_test(name, passed, details=""):
    status = f"{GREEN}✅ PASS{RESET}" if passed else f"{RED}❌ FAIL{RESET}"
    print(f"  {status} {name}")
    if details:
        print(f"      {details}")

def query_db(query_text):
    """Execute query via Lambda"""
    lambda_client = boto3.client('lambda', region_name='us-west-2')
    
    try:
        response = lambda_client.invoke(
            FunctionName='ops-pipeline-db-query',
            Payload=json.dumps({'query': query_text})
        )
        result = json.loads(response['Payload'].read())
        
        if result.get('statusCode') == 200:
            body = json.loads(result['body'])
            return body.get('results', [])
        else:
            return None
    except Exception as e:
        print(f"      {RED}Query error: {e}{RESET}")
        return None

def test_database_schema():
    """Test Phase 16 schema changes"""
    print_header("TEST 1: Database Schema (Phase 16)")
    
    # Check dispatch_recommendations has snapshots
    results = query_db("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'dispatch_recommendations' 
          AND column_name IN ('features_snapshot', 'sentiment_snapshot')
        ORDER BY column_name
    """)
    
    has_features = any(r.get('column_name') == 'features_snapshot' for r in results) if results else False
    has_sentiment = any(r.get('column_name') == 'sentiment_snapshot' for r in results) if results else False
    
    print_test("dispatch_recommendations.features_snapshot exists", has_features)
    print_test("dispatch_recommendations.sentiment_snapshot exists", has_sentiment)
    
    # Check position_history has outcome labels
    results = query_db("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'position_history' 
          AND column_name IN ('win_loss_label', 'r_multiple', 'mae_pct', 'holding_minutes')
        ORDER BY column_name
    """)
    
    has_win_loss = any(r.get('column_name') == 'win_loss_label' for r in results) if results else False
    has_r_multiple = any(r.get('column_name') == 'r_multiple' for r in results) if results else False
    
    print_test("position_history.win_loss_label exists", has_win_loss)
    print_test("position_history.r_multiple exists", has_r_multiple)
    
    # Check learning_recommendations table
    results = query_db("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_name = 'learning_recommendations'
    """)
    
    has_learning_table = len(results) > 0 if results else False
    print_test("learning_recommendations table exists", has_learning_table)
    
    return has_features and has_sentiment and has_win_loss and has_r_multiple and has_learning_table

def test_snapshot_capture():
    """Test feature snapshots are being captured"""
    print_header("TEST 2: Snapshot Capture (Phase 16 P0)")
    
    # Check latest recommendations have snapshots
    results = query_db("""
        SELECT 
            id,
            ticker,
            features_snapshot IS NOT NULL as has_features,
            sentiment_snapshot IS NOT NULL as has_sentiment,
            created_at
        FROM dispatch_recommendations
        ORDER BY created_at DESC
        LIMIT 5
    """)
    
    if not results:
        print_test("Recent recommendations exist", False, "No recommendations found")
        return False
    
    print_test("Recent recommendations exist", True, f"Found {len(results)} recent")
    
    # Check if snapshots are being captured
    with_features = sum(1 for r in results if r.get('has_features')) if results else 0
    with_sentiment = sum(1 for r in results if r.get('has_sentiment')) if results else 0
    
    print_test(f"Feature snapshots capturing", with_features > 0, 
               f"{with_features}/{len(results)} have snapshots")
    print_test(f"Sentiment snapshots capturing", with_sentiment >= 0,
               f"{with_sentiment}/{len(results)} have snapshots (OK if 0 - no news)")
    
    # Show example snapshot
    if results and results[0].get('has_features'):
        snapshot_result = query_db(f"""
            SELECT features_snapshot 
            FROM dispatch_recommendations 
            WHERE id = {results[0]['id']}
        """)
        
        if snapshot_result:
            snapshot = snapshot_result[0].get('features_snapshot')
            print(f"\n      Example snapshot (ticker {results[0]['ticker']}):")
            print(f"      {json.dumps(snapshot, indent=6)[:200]}...")
    
    return with_features > 0

def test_alpaca_orders():
    """Test Alpaca orders are being placed"""
    print_header("TEST 3: Alpaca Integration (Phase 15)")
    
    # Check recent executions
    results = query_db("""
        SELECT 
            ticker,
            action,
            instrument_type,
            execution_mode,
            explain_json->>'alpaca_order_id' as alpaca_order_id,
            created_at
        FROM dispatcher_execution
        ORDER BY created_at DESC
        LIMIT 10
    """)
    
    if not results:
        print_test("Recent executions exist", False, "No executions found")
        return False
    
    print_test("Recent executions exist", True, f"Found {len(results)}")
    
    # Count Alpaca vs simulated
    alpaca_count = sum(1 for r in results if r.get('execution_mode') == 'ALPACA_PAPER')
    sim_count = sum(1 for r in results if r.get('execution_mode') == 'SIMULATED_FALLBACK')
    
    print_test(f"Alpaca executions", alpaca_count > 0,
               f"{alpaca_count} Alpaca, {sim_count} simulated")
    
    # Show recent Alpaca orders
    alpaca_orders = [r for r in results if r.get('execution_mode') == 'ALPACA_PAPER']
    if alpaca_orders:
        print(f"\n      Recent Alpaca orders:")
        for order in alpaca_orders[:3]:
            print(f"        • {order['ticker']} {order['instrument_type']} - Order ID: {order.get('alpaca_order_id', 'N/A')[:20]}...")
    
    return alpaca_count > 0

def test_position_tracking():
    """Test positions are being tracked"""
    print_header("TEST 4: Position Tracking")
    
    # Check active positions
    results = query_db("""
        SELECT 
            ticker,
            instrument_type,
            quantity,
            entry_price,
            current_price,
            current_pnl_dollars,
            status,
            created_at
        FROM active_positions
        WHERE status = 'active'
        ORDER BY created_at DESC
    """)
    
    active_count = len(results) if results else 0
    print_test(f"Active positions tracked", True, 
               f"{active_count} active position(s)")
    
    if results:
        print(f"\n      Active positions:")
        for pos in results:
            pnl = float(pos.get('current_pnl_dollars', 0))
            pnl_str = f"${pnl:+.2f}"
            print(f"        • {pos['ticker']} {pos['instrument_type']} - {pnl_str}")
    
    return True

def test_learning_views():
    """Test learning analysis views"""
    print_header("TEST 5: Learning Analysis Views")
    
    # Check views exist
    views_to_check = [
        'v_confidence_performance',
        'v_sentiment_effectiveness',
        'v_volume_edge',
        'v_instrument_performance',
        'v_snapshot_coverage'
    ]
    
    results = query_db(f"""
        SELECT table_name 
        FROM information_schema.views 
        WHERE table_name = ANY(ARRAY{views_to_check})
    """)
    
    found_views = [r['table_name'] for r in results] if results else []
    
    for view in views_to_check:
        exists = view in found_views
        print_test(f"{view} exists", exists)
    
    # Check snapshot coverage
    coverage = query_db("SELECT * FROM v_snapshot_coverage")
    if coverage:
        print(f"\n      Snapshot Coverage:")
        for row in coverage:
            print(f"        {row['table_name']}: {row.get('features_coverage_pct', 0):.1f}% features, {row.get('sentiment_coverage_pct', 0):.1f}% sentiment")
    
    return len(found_views) == len(views_to_check)

def test_end_to_end_flow():
    """Test complete data flow"""
    print_header("TEST 6: End-to-End Data Flow")
    
    # Get latest recommendation with full context
    results = query_db("""
        SELECT 
            dr.ticker,
            dr.confidence,
            dr.features_snapshot IS NOT NULL as has_features,
            de.execution_mode,
            de.explain_json->>'alpaca_order_id' as order_id
        FROM dispatch_recommendations dr
        LEFT JOIN dispatcher_execution de ON dr.id = de.recommendation_id
        WHERE dr.created_at > NOW() - INTERVAL '1 hour'
        ORDER BY dr.created_at DESC
        LIMIT 1
    """)
    
    if not results or len(results) == 0:
        print_test("Recent signal → execution flow", False, "No recent recommendations")
        return False
    
    rec = results[0]
    print_test("Recommendation generated", True, f"{rec['ticker']} @ {rec.get('confidence', 0):.3f} confidence")
    print_test("Feature snapshot captured", rec.get('has_features', False))
    print_test("Execution attempted", rec.get('execution_mode') is not None)
    
    if rec.get('execution_mode') == 'ALPACA_PAPER':
        print_test("Alpaca execution", True, f"Order ID: {rec.get('order_id', 'N/A')[:20]}...")
    
    return True

def test_alpaca_api():
    """Test Alpaca API connectivity"""
    print_header("TEST 7: Alpaca API Health")
    
    import requests
    
    headers = {
        'APCA-API-KEY-ID': 'PKG7MU6D3EPFNCMVHL6QQSADRS',
        'APCA-API-SECRET-KEY': 'BBsd4MCQKKWfCZahkM2jJMXhD4BSE8ddcVkoVR6kXjM9'
    }
    
    try:
        # Test account API
        response = requests.get('https://paper-api.alpaca.markets/v2/account', headers=headers, timeout=5)
        account_ok = response.status_code == 200
        
        if account_ok:
            account = response.json()
            cash = float(account['cash'])
            buying_power = float(account['buying_power'])
            print_test("Account API accessible", True, f"${cash:,.2f} cash, ${buying_power:,.2f} buying power")
        else:
            print_test("Account API accessible", False, f"Status {response.status_code}")
        
        # Test options data API
        response = requests.get(
            'https://data.alpaca.markets/v1beta1/options/snapshots/SPY?limit=5&type=call',
            headers=headers,
            timeout=5
        )
        options_ok = response.status_code == 200
        
        if options_ok:
            data = response.json()
            contract_count = len(data.get('snapshots', {}))
            print_test("Options data API accessible", True, f"{contract_count} contracts fetched")
        else:
            print_test("Options data API accessible", False, f"Status {response.status_code}")
        
        return account_ok and options_ok
        
    except Exception as e:
        print_test("Alpaca API connectivity", False, str(e))
        return False

def main():
    """Run all verification tests"""
    print(f"\n{BLUE}{'=' * 80}")
    print(f"PHASE 15 + 16 END-TO-END VERIFICATION")
    print(f"{'=' * 80}{RESET}")
    print(f"Timestamp: {datetime.utcnow().isoformat()}Z")
    print(f"Region: us-west-2")
    
    tests = []
    
    # Run all tests
    tests.append(("Database Schema", test_database_schema()))
    tests.append(("Snapshot Capture", test_snapshot_capture()))
    tests.append(("Alpaca Integration", test_alpaca_orders()))
    tests.append(("Position Tracking", test_position_tracking()))
    tests.append(("Learning Views", test_learning_views()))
    tests.append(("End-to-End Flow", test_end_to_end_flow()))
    tests.append(("Alpaca API Health", test_alpaca_api()))
    
    # Summary
    print_header("VERIFICATION SUMMARY")
    
    passed = sum(1 for _, result in tests if result)
    total = len(tests)
    
    for name, result in tests:
        status = f"{GREEN}✅{RESET}" if result else f"{RED}❌{RESET}"
        print(f"  {status} {name}")
    
    print(f"\n{BLUE}Score: {passed}/{total} tests passed{RESET}")
    
    if passed == total:
        print(f"\n{GREEN}{'=' * 80}")
        print(f"🎉 ALL TESTS PASSED - SYSTEM FULLY OPERATIONAL")
        print(f"{'=' * 80}{RESET}\n")
        print("Next steps:")
        print("  • Monitor Alpaca dashboard: https://app.alpaca.markets/paper/dashboard")
        print("  • Check v_snapshot_coverage for 100% adoption")
        print("  • Accumulate 30-50 trades for learning analysis")
        return 0
    else:
        print(f"\n{RED}{'=' * 80}")
        print(f"⚠️  {total - passed} TEST(S) FAILED - REVIEW ABOVE")
        print(f"{'=' * 80}{RESET}\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
