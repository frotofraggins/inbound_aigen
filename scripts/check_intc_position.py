#!/usr/bin/env python3
"""Check if INTC position is being tracked and monitor it"""
import boto3
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone

def get_db_connection():
    """Get database connection from SSM"""
    ssm = boto3.client('ssm', region_name='us-west-2')
    response = ssm.get_parameters_by_path(
        Path='/ops-pipeline/db',
        WithDecryption=True
    )
    
    param_dict = {}
    for param in response['Parameters']:
        key = param['Name'].split('/')[-1]
        param_dict[key] = param['Value']
    
    secrets = boto3.client('secretsmanager', region_name='us-west-2')
    db_secret = secrets.get_secret_value(SecretId='ops-pipeline/db')
    import json
    secret_data = json.loads(db_secret['SecretString'])
    
    return psycopg2.connect(
        host=param_dict.get('host', param_dict.get('endpoint', '')),
        port=int(param_dict.get('port', 5432)),
        dbname=param_dict.get('name', param_dict.get('database', '')),
        user=secret_data['username'],
        password=secret_data['password']
    )

def check_intc_position():
    """Check if INTC position is tracked"""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    # Check active_positions
    query = """
    SELECT 
        id,
        ticker,
        option_symbol,
        instrument_type,
        account_name,
        quantity,
        entry_price,
        entry_time,
        EXTRACT(EPOCH FROM (NOW() - entry_time))/60 as age_minutes,
        current_price,
        current_pnl_dollars,
        current_pnl_percent,
        stop_loss,
        take_profit,
        status
    FROM active_positions
    WHERE (ticker LIKE 'INTC%' OR option_symbol LIKE 'INTC%')
    AND entry_time > NOW() - INTERVAL '30 minutes'
    ORDER BY entry_time DESC
    """
    
    cur.execute(query)
    results = cur.fetchall()
    
    print("=" * 80)
    print("INTC POSITION CHECK")
    print("=" * 80)
    print()
    
    if not results:
        print("❌ NO INTC POSITION FOUND IN DATABASE")
        print("   Position may not be synced yet (sync runs every minute)")
        print("   Or execution may not have been logged")
    else:
        for pos in results:
            print(f"✅ FOUND INTC POSITION!")
            print(f"   ID: {pos['id']}")
            print(f"   Ticker: {pos['ticker']}")
            print(f"   Option Symbol: {pos['option_symbol']}")
            print(f"   Instrument Type: {pos['instrument_type']}")
            print(f"   Account: {pos['account_name']}")
            print(f"   Quantity: {pos['quantity']}")
            print(f"   Entry Price: ${pos['entry_price']:.2f}")
            print(f"   Entry Time: {pos['entry_time']}")
            print(f"   Age: {pos['age_minutes']:.1f} minutes")
            print(f"   Current Price: ${pos['current_price']:.2f if pos['current_price'] else 'N/A'}")
            print(f"   P&L: ${pos['current_pnl_dollars']:.2f if pos['current_pnl_dollars'] else 'N/A'} ({pos['current_pnl_percent']:.1f}% if pos['current_pnl_percent'] else 'N/A')")
            print(f"   Stop Loss: ${pos['stop_loss']:.2f}")
            print(f"   Take Profit: ${pos['take_profit']:.2f}")
            print(f"   Status: {pos['status']}")
            print()
            
            if pos['age_minutes'] < 30:
                print(f"   ⏱️  TOO YOUNG TO EXIT (only {pos['age_minutes']:.1f} min old, need 30)")
                print("   Position should be protected by 'Too early to exit' logic")
            else:
                print(f"   ✅ OLD ENOUGH TO EXIT (can exit at -40% or +80%)")
    
    # Check account balance info
    balance_query = """
    SELECT 
        account_name,
        COUNT(*) as position_count,
        SUM(quantity * entry_price) as total_deployed
    FROM active_positions
    WHERE status = 'open'
    GROUP BY account_name
    """
    
    cur.execute(balance_query)
    balances = cur.fetchall()
    
    print("\n" + "=" * 80)
    print("ACCOUNT BALANCE USAGE")
    print("=" * 80)
    print()
    
    for bal in balances:
        print(f"{bal['account_name']} account:")
        print(f"   Open positions: {bal['position_count']}")
        print(f"   Total deployed: ${bal['total_deployed']:.2f}")
        print()
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    check_intc_position()
