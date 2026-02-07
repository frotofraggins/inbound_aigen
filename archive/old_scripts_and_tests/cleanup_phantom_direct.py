#!/usr/bin/env python3
"""
Direct database cleanup of phantom positions.
Uses direct psycopg2 connection to execute UPDATE query.
"""

import boto3
import json
import psycopg2
from datetime import datetime

def get_db_config():
    """Load database configuration from AWS"""
    ssm = boto3.client('ssm', region_name='us-west-2')
    secrets = boto3.client('secretsmanager', region_name='us-west-2')
    
    db_host = ssm.get_parameter(Name='/ops-pipeline/db_host')['Parameter']['Value']
    db_port = ssm.get_parameter(Name='/ops-pipeline/db_port')['Parameter']['Value']
    db_name = ssm.get_parameter(Name='/ops-pipeline/db_name')['Parameter']['Value']
    
    secret_value = secrets.get_secret_value(SecretId='ops-pipeline/db')
    secret_data = json.loads(secret_value['SecretString'])
    
    return {
        'host': db_host,
        'port': int(db_port),
        'database': db_name,
        'user': secret_data['username'],
        'password': secret_data['password']
    }

def cleanup_phantom_positions():
    """Close phantom positions directly in database"""
    
    print("=" * 80)
    print("PHANTOM POSITION CLEANUP - DIRECT DATABASE")
    print("=" * 80)
    print("\nPhantom positions to close:")
    print("  - Large account: 4 positions (IDs: 16, 24, 13, 21)")
    print("  - Tiny account: 3 positions (IDs: 19, 32, 33)")
    print("\n" + "=" * 80)
    
    # Get database config
    print("\nLoading database configuration...")
    try:
        db_config = get_db_config()
        print(f"✅ Config loaded: {db_config['host']}:{db_config['port']}/{db_config['database']}")
    except Exception as e:
        print(f"❌ ERROR loading config: {e}")
        return False
    
    # Connect to database
    print("\nConnecting to database...")
    try:
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()
        print("✅ Database connection established")
    except Exception as e:
        print(f"❌ ERROR connecting to database: {e}")
        return False
    
    try:
        # Close phantom positions
        sql = """
        UPDATE active_positions
        SET 
            status = 'closed',
            close_reason = 'manual_reconciliation',
            closed_at = NOW(),
            exit_price = entry_price,
            current_pnl_dollars = 0,
            current_pnl_percent = 0
        WHERE status IN ('open', 'closing')
        AND id IN (16, 24, 13, 21, 19, 32, 33)
        RETURNING id, ticker, option_symbol, status, close_reason;
        """
        
        print("\nExecuting UPDATE query...")
        print(f"SQL: {sql[:100]}...")
        cursor.execute(sql)
        results = cursor.fetchall()
        conn.commit()
        print(f"✅ Query executed, {len(results)} rows affected")
        
        if len(results) == 0:
            print("\n⚠️ WARNING: No positions were updated!")
            print("This could mean:")
            print("  1. Positions were already closed")
            print("  2. Position IDs don't exist")
            print("  3. Positions have different status")
            
            # Check what positions actually exist
            print("\nChecking current position status...")
            cursor.execute("""
                SELECT id, ticker, option_symbol, status 
                FROM active_positions 
                WHERE id IN (16, 24, 13, 21, 19, 32, 33)
                ORDER BY id;
            """)
            existing = cursor.fetchall()
            
            if existing:
                print(f"\nFound {len(existing)} positions with these IDs:")
                for row in existing:
                    pos_id, ticker, option_symbol, status = row
                    symbol = option_symbol or ticker
                    print(f"  - ID {pos_id}: {symbol} (status: {status})")
            else:
                print("\n⚠️ None of the specified position IDs exist in the database!")
            
            return False
        
        print(f"\n✅ SUCCESS! Closed {len(results)} phantom positions:")
        for row in results:
            pos_id, ticker, option_symbol, status, close_reason = row
            symbol = option_symbol or ticker
            print(f"  - ID {pos_id}: {symbol} → {status} ({close_reason})")
        
        # Verify cleanup
        print("\n" + "=" * 80)
        print("VERIFICATION")
        print("=" * 80)
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total_open,
                COUNT(CASE WHEN option_symbol IS NOT NULL THEN 1 END) as options_open,
                COUNT(CASE WHEN option_symbol IS NULL THEN 1 END) as stocks_open
            FROM active_positions
            WHERE status IN ('open', 'closing');
        """)
        
        stats = cursor.fetchone()
        total_open, options_open, stocks_open = stats
        
        print(f"\n✅ Current open positions:")
        print(f"  - Total: {total_open}")
        print(f"  - Options: {options_open}")
        print(f"  - Stocks: {stocks_open}")
        
        if total_open <= 3:
            print("\n✅ Database is clean! Only real positions remain.")
        else:
            print(f"\n⚠️ Still have {total_open} open positions (expected 3)")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        conn.rollback()
        return False
        
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    success = cleanup_phantom_positions()
    
    if success:
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
