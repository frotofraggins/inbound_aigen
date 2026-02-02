#!/usr/bin/env python3
"""Quick check if positions have been synced"""
import boto3
import json

def check_positions():
    client = boto3.client('lambda', region_name='us-west-2')
    
    response = client.invoke(
        FunctionName='ops-pipeline-db-query',
        Payload=json.dumps({
            'sql': "SELECT COUNT(*) as count FROM active_positions WHERE status = 'open'"
        })
    )
    
    body = json.loads(json.load(response['Payload'])['body'])
    count = body['rows'][0]['count']
    
    print(f"Active positions: {count}")
    
    if count == 3:
        print("✅ SUCCESS! All 3 positions synced from Alpaca")
        
        # Get position details
        response2 = client.invoke(
            FunctionName='ops-pipeline-db-query',
            Payload=json.dumps({
                'sql': """
                SELECT ticker, instrument_type, entry_price, current_price, 
                       stop_loss, take_profit, entry_time
                FROM active_positions 
                WHERE status = 'open'
                ORDER BY entry_time
                """
            })
        )
        
        body2 = json.loads(json.load(response2['Payload'])['body'])
        print("\nPosition Details:")
        for row in body2['rows']:
            print(f"  {row['ticker']} {row['instrument_type']}: "
                  f"Entry ${row['entry_price']:.2f}, "
                  f"Stop ${row['stop_loss']:.2f}")
    elif count == 0:
        from datetime import datetime
        current_time = datetime.now().strftime('%H:%M')
        print(f"⏳ Positions not synced yet (checked at {current_time})")
        print("   Schedulers updated at 10:10 PM - should have run by now")
        print("   Investigating...")
    else:
        print(f"⚠️  Partial sync: {count}/3 positions")

if __name__ == "__main__":
    check_positions()
