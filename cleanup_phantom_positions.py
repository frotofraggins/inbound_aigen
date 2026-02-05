#!/usr/bin/env python3
"""
Cleanup phantom positions in database that don't exist in Alpaca.

This script closes all positions in the database that were manually closed
in Alpaca but never updated in the database.
"""

import boto3
import json
from datetime import datetime

def cleanup_phantom_positions():
    """Close phantom positions via Lambda"""
    
    # SQL to close phantom positions
    sql = """
    -- Close phantom positions that don't exist in Alpaca
    UPDATE active_positions
    SET 
        status = 'closed',
        close_reason = 'manual_reconciliation',
        closed_at = NOW(),
        exit_price = entry_price,  -- Use entry price since we don't have exit price
        current_pnl_dollars = 0,
        current_pnl_percent = 0
    WHERE status IN ('open', 'closing')
    AND id IN (
        -- Phantom positions identified by sync script
        16,  -- QCOM (large account phantom)
        24,  -- CRM260227P00200000 (large account phantom)
        13,  -- NOW (large account phantom)
        21,  -- ORCL260213C00155000 (large account phantom)
        19,  -- SPY (tiny account phantom)
        32,  -- NOW260220P00110000 (tiny account phantom)
        33   -- QCOM260220P00145000 (tiny account phantom)
    )
    RETURNING id, ticker, option_symbol, status, close_reason;
    """
    
    # Prepare Lambda payload
    payload = {
        'sql': sql,
        'operation': 'query'
    }
    
    print("Invoking db-query lambda to close phantom positions...")
    print(f"SQL: {sql[:200]}...")
    
    # Invoke Lambda
    lambda_client = boto3.client('lambda', region_name='us-west-2')
    
    try:
        response = lambda_client.invoke(
            FunctionName='ops-pipeline-db-query',
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        
        result = json.loads(response['Payload'].read())
        
        if response['StatusCode'] == 200:
            print("\n✅ SUCCESS!")
            print(f"Response: {json.dumps(result, indent=2)}")
            
            if 'body' in result:
                body = json.loads(result['body']) if isinstance(result['body'], str) else result['body']
                if 'results' in body:
                    print(f"\n✅ Closed {len(body['results'])} phantom positions:")
                    for pos in body['results']:
                        symbol = pos.get('option_symbol') or pos.get('ticker')
                        print(f"  - ID {pos['id']}: {symbol} → {pos['status']} ({pos['close_reason']})")
            
            return True
        else:
            print(f"\n❌ ERROR: Lambda returned status {response['StatusCode']}")
            print(f"Result: {result}")
            return False
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        return False


def verify_cleanup():
    """Verify that phantom positions are closed"""
    
    sql = """
    SELECT 
        COUNT(*) as total_open,
        COUNT(CASE WHEN option_symbol IS NOT NULL THEN 1 END) as options_open,
        COUNT(CASE WHEN option_symbol IS NULL THEN 1 END) as stocks_open
    FROM active_positions
    WHERE status IN ('open', 'closing');
    """
    
    payload = {
        'sql': sql,
        'operation': 'query'
    }
    
    print("\n\nVerifying cleanup...")
    
    lambda_client = boto3.client('lambda', region_name='us-west-2')
    
    try:
        response = lambda_client.invoke(
            FunctionName='ops-pipeline-db-query',
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        
        result = json.loads(response['Payload'].read())
        
        if response['StatusCode'] == 200 and 'body' in result:
            body = json.loads(result['body']) if isinstance(result['body'], str) else result['body']
            if 'results' in body and body['results']:
                stats = body['results'][0]
                print(f"\n✅ Current open positions:")
                print(f"  - Total: {stats['total_open']}")
                print(f"  - Options: {stats['options_open']}")
                print(f"  - Stocks: {stats['stocks_open']}")
                
                if stats['total_open'] <= 3:
                    print("\n✅ Database is clean! Only real positions remain.")
                    return True
                else:
                    print(f"\n⚠️ Still have {stats['total_open']} open positions (expected 3)")
                    return False
        
        return False
        
    except Exception as e:
        print(f"\n❌ ERROR verifying: {e}")
        return False


if __name__ == '__main__':
    print("=" * 80)
    print("PHANTOM POSITION CLEANUP")
    print("=" * 80)
    print("\nThis script will close phantom positions in the database that were")
    print("manually closed in Alpaca but never updated in the database.")
    print("\nPhantom positions to close:")
    print("  - Large account: 4 positions (IDs: 16, 24, 13, 21)")
    print("  - Tiny account: 3 positions (IDs: 19, 32, 33)")
    print("\nReal positions to keep:")
    print("  - Large account: 3 positions (QCOM PUT, SPY, NOW PUT)")
    print("  - Tiny account: 0 positions (all manually closed)")
    print("\n" + "=" * 80)
    
    input("\nPress Enter to continue or Ctrl+C to cancel...")
    
    # Execute cleanup
    success = cleanup_phantom_positions()
    
    if success:
        # Verify cleanup
        verify_cleanup()
        
        print("\n" + "=" * 80)
        print("✅ CLEANUP COMPLETE!")
        print("=" * 80)
        print("\nNext steps:")
        print("1. Run sync script to verify: python3 scripts/sync_positions_with_alpaca.py")
        print("2. Monitor Position Manager logs for clean operation")
        print("3. Verify no more 'position does not exist' errors")
    else:
        print("\n" + "=" * 80)
        print("❌ CLEANUP FAILED")
        print("=" * 80)
        print("\nPlease check the error messages above and try again.")
