"""
Trade Alert Lambda
Monitors dispatch_executions and sends SNS alerts when new trades occur.

Triggered: Every 1 minute during market hours
Alerts on: Any new execution (stock or options)
"""

import json
import boto3
import psycopg2
from datetime import datetime, timedelta
import os

sns = boto3.client('sns', region_name='us-west-2')
ssm = boto3.client('ssm', region_name='us-west-2')
secrets = boto3.client('secretsmanager', region_name='us-west-2')

def get_db_connection():
    """Get database connection from AWS"""
    db_host = ssm.get_parameter(Name='/ops-pipeline/db_host')['Parameter']['Value']
    db_port = ssm.get_parameter(Name='/ops-pipeline/db_port')['Parameter']['Value']
    db_name = ssm.get_parameter(Name='/ops-pipeline/db_name')['Parameter']['Value']
    
    secret = secrets.get_secret_value(SecretId='ops-pipeline/db')
    secret_data = json.loads(secret['SecretString'])
    
    return psycopg2.connect(
        host=db_host,
        port=int(db_port),
        database=db_name,
        user=secret_data['username'],
        password=secret_data['password']
    )

def lambda_handler(event, context):
    """Check for new trades and send alerts"""
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get topic ARN from environment
        topic_arn = os.environ.get('TRADE_ALERT_TOPIC_ARN')
        
        if not topic_arn:
            print("No TRADE_ALERT_TOPIC_ARN configured, skipping alerts")
            return {'statusCode': 200, 'body': 'No topic configured'}
        
        # Check for executions in last 2 minutes
        # (Lambda runs every minute, so 2min window catches recent trades)
        cur.execute("""
            SELECT 
                execution_id,
                ticker,
                action,
                instrument_type,
                strategy_type,
                entry_price,
                qty,
                notional,
                strike_price,
                expiration_date,
                contracts,
                premium_paid,
                simulated_ts
            FROM dispatch_executions
            WHERE simulated_ts > NOW() - INTERVAL '2 minutes'
            ORDER BY simulated_ts DESC;
        """)
        
        recent_trades = cur.fetchall()
        
        if len(recent_trades) == 0:
            print("No recent trades")
            conn.close()
            return {'statusCode': 200, 'body': 'No recent trades'}
        
        # Build alert message
        for trade in recent_trades:
            execution_id = trade[0]
            ticker = trade[1]
            action = trade[2]
            instrument_type = trade[3]
            strategy_type = trade[4]
            entry_price = float(trade[5])
            qty = float(trade[6])
            notional = float(trade[7])
            strike = trade[8]
            expiration = trade[9]
            contracts = trade[10]
            premium = trade[11]
            timestamp = trade[12]
            
            # Format message based on instrument type
            if instrument_type in ('CALL', 'PUT'):
                # Options trade
                subject = f"🔔 OPTIONS TRADE: {action} {ticker} {instrument_type}"
                
                message = f"""
OPTIONS TRADE EXECUTED

Ticker: {ticker}
Action: {action} {instrument_type}
Strategy: {strategy_type}

Option Details:
- Strike: ${strike:.2f}
- Expiration: {expiration}
- Contracts: {contracts}
- Premium: ${premium:.2f}
- Total Cost: ${contracts * premium * 100:.2f}

Underlying: ${entry_price:.2f}
Time: {timestamp}
Execution ID: {execution_id}

This is a paper trade (Alpaca Paper Trading Account).
"""
            else:
                # Stock trade
                subject = f"📈 STOCK TRADE: {action} {ticker}"
                
                message = f"""
STOCK TRADE EXECUTED

Ticker: {ticker}
Action: {action} {instrument_type}

Trade Details:
- Price: ${entry_price:.2f}
- Quantity: {qty:.0f} shares
- Notional: ${notional:.2f}

Time: {timestamp}
Execution ID: {execution_id}

This is a paper trade (Alpaca Paper Trading Account).
"""
            
            # Send SNS notification
            response = sns.publish(
                TopicArn=topic_arn,
                Subject=subject,
                Message=message
            )
            
            print(f"Alert sent for {ticker} {instrument_type} trade: {response['MessageId']}")
        
        conn.close()
        
        return {
            'statusCode': 200,
            'body': json.dumps(f'Sent {len(recent_trades)} trade alert(s)')
        }
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error: {str(e)}')
        }
