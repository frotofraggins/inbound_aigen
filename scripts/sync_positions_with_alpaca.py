#!/usr/bin/env python3
"""
Sync Position Manager Database with Alpaca Reality

This script:
1. Queries Alpaca for actual open positions
2. Queries database for tracked positions
3. Reconciles differences
4. Closes positions in DB that don't exist in Alpaca
5. Adds positions from Alpaca that aren't in DB
6. Verifies account balances

Run this daily or after any manual position changes.
"""

import boto3
import json
import sys
from datetime import datetime

# Configuration
REGION = "us-west-2"
ACCOUNTS = {
    'large': 'ops-pipeline/alpaca',
    'tiny': 'ops-pipeline/alpaca/tiny'
}

def get_alpaca_credentials(secret_name):
    """Get Alpaca credentials from Secrets Manager"""
    secrets = boto3.client('secretsmanager', region_name=REGION)
    secret = secrets.get_secret_value(SecretId=secret_name)
    return json.loads(secret['SecretString'])

def get_alpaca_positions(api_key, api_secret):
    """Get positions from Alpaca"""
    import requests
    response = requests.get(
        "https://paper-api.alpaca.markets/v2/positions",
        headers={
            'APCA-API-KEY-ID': api_key,
            'APCA-API-SECRET-KEY': api_secret
        }
    )
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error getting Alpaca positions: {response.status_code}")
        return []

def get_alpaca_account(api_key, api_secret):
    """Get account info from Alpaca"""
    import requests
    response = requests.get(
        "https://paper-api.alpaca.markets/v2/account",
        headers={
            'APCA-API-KEY-ID': api_key,
            'APCA-API-SECRET-KEY': api_secret
        }
    )
    if response.status_code == 200:
        return response.json()
    else:
        return None

def get_database_positions():
    """Get open positions from database"""
    lambda_client = boto3.client('lambda', region_name=REGION)
    response = lambda_client.invoke(
        FunctionName='ops-pipeline-db-query',
        Payload=json.dumps({
            'sql': """
                SELECT id, ticker, option_symbol, instrument_type, 
                       quantity, entry_price, stop_loss, take_profit,
                       current_price, current_pnl_dollars, status
                FROM active_positions
                WHERE status IN ('open', 'closing')
                ORDER BY id
            """
        })
    )
    result = json.loads(json.load(response['Payload'])['body'])
    return result.get('rows', [])

def close_position_in_database(position_id, reason='manual_reconciliation'):
    """Mark position as closed in database"""
    lambda_client = boto3.client('lambda', region_name=REGION)
    # Note: db-query Lambda only allows SELECT, so we'd need db-migration Lambda
    # For now, return the SQL to run
    sql = f"""
        UPDATE active_positions
        SET status = 'closed',
            close_reason = '{reason}',
            closed_at = NOW()
        WHERE id = {position_id}
    """
    return sql

def sync_positions(account_name, alpaca_positions, db_positions):
    """Sync database with Alpaca reality"""
    print(f"\n{'='*80}")
    print(f"SYNCING: {account_name}")
    print(f"{'='*80}\n")
    
    # Create lookup maps
    alpaca_map = {p['symbol']: p for p in alpaca_positions}
    db_map = {(p['option_symbol'] or p['ticker']): p for p in db_positions}
    
    # Find discrepancies
    in_db_not_alpaca = set(db_map.keys()) - set(alpaca_map.keys())
    in_alpaca_not_db = set(alpaca_map.keys()) - set(db_map.keys())
    in_both = set(db_map.keys()) & set(alpaca_map.keys())
    
    print(f"Alpaca positions: {len(alpaca_positions)}")
    print(f"Database positions: {len(db_positions)}")
    print(f"Matched: {len(in_both)}")
    print(f"In DB but not Alpaca: {len(in_db_not_alpaca)}")
    print(f"In Alpaca but not DB: {len(in_alpaca_not_db)}")
    print()
    
    # Positions to close in DB (don't exist in Alpaca)
    if in_db_not_alpaca:
        print("⚠️  Positions to CLOSE in database (don't exist in Alpaca):")
        for symbol in in_db_not_alpaca:
            pos = db_map[symbol]
            print(f"  {symbol:30s} (DB ID: {pos['id']}, status: {pos['status']})")
            print(f"    SQL: {close_position_in_database(pos['id'])}")
        print()
    
    # Positions to ADD to DB (exist in Alpaca but not tracked)
    if in_alpaca_not_db:
        print("⚠️  Positions to ADD to database (exist in Alpaca but not tracked):")
        for symbol in in_alpaca_not_db:
            pos = alpaca_map[symbol]
            print(f"  {symbol:30s} Qty: {pos['qty']}, Value: ${pos['market_value']}")
            print(f"    These should be tracked by Position Manager")
        print()
    
    # Matched positions
    if in_both:
        print("✅ Matched positions (exist in both):")
        for symbol in in_both:
            alpaca_pos = alpaca_map[symbol]
            db_pos = db_map[symbol]
            print(f"  {symbol:30s} Alpaca Qty: {alpaca_pos['qty']:8s} | DB Qty: {db_pos['quantity']}")
        print()

def main():
    print("="*80)
    print("POSITION RECONCILIATION TOOL")
    print("="*80)
    print()
    
    for account_name, secret_name in ACCOUNTS.items():
        try:
            # Get credentials
            creds = get_alpaca_credentials(secret_name)
            api_key = creds.get('api_key') or creds.get('APCA_API_KEY_ID')
            api_secret = creds.get('api_secret') or creds.get('APCA_API_SECRET_KEY')
            
            # Get Alpaca positions
            alpaca_positions = get_alpaca_positions(api_key, api_secret)
            
            # Get account info
            account = get_alpaca_account(api_key, api_secret)
            if account:
                print(f"\n{account_name.upper()} ACCOUNT:")
                print(f"  Account: {account['account_number']}")
                print(f"  Buying Power: ${float(account['buying_power']):,.2f}")
                print(f"  Cash: ${float(account['cash']):,.2f}")
                print(f"  Portfolio Value: ${float(account['portfolio_value']):,.2f}")
                print(f"  Open Positions: {len(alpaca_positions)}")
            
            # Sync positions
            db_positions = get_database_positions()
            sync_positions(account_name, alpaca_positions, db_positions)
            
        except Exception as e:
            print(f"Error syncing {account_name} account: {e}")
    
    print("\n" + "="*80)
    print("RECONCILIATION COMPLETE")
    print("="*80)
    print()
    print("Next steps:")
    print("1. Run the UPDATE SQL commands above to close phantom positions")
    print("2. Add missing positions if needed")
    print("3. Verify account balances match")
    print()

if __name__ == '__main__':
    main()
