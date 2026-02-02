"""
Configuration loader for telemetry ingestor
"""

import json
import boto3
import os
from typing import Dict, List, Any

def load_config() -> Dict[str, Any]:
    """Load configuration from AWS services"""
    
    ssm = boto3.client('ssm', region_name='us-west-2')
    secrets = boto3.client('secretsmanager', region_name='us-west-2')
    
    # Database configuration
    db_host = ssm.get_parameter(Name='/ops-pipeline/db_host')['Parameter']['Value']
    db_port = ssm.get_parameter(Name='/ops-pipeline/db_port')['Parameter']['Value']
    db_name = ssm.get_parameter(Name='/ops-pipeline/db_name')['Parameter']['Value']
    
    # Get database credentials
    secret_value = secrets.get_secret_value(SecretId='ops-pipeline/db')
    secret_data = json.loads(secret_value['SecretString'])
    
    # Get tickers list
    tickers_param = ssm.get_parameter(Name='/ops-pipeline/tickers')
    tickers = [t.strip() for t in tickers_param['Parameter']['Value'].split(',')]
    
    # Get configuration from environment variables (with defaults)
    lookback_minutes = int(os.environ.get('LOOKBACK_MINUTES', '120'))
    interval = os.environ.get('INTERVAL', '1m')
    data_source = os.environ.get('DATA_SOURCE', 'alpaca')
    
    # Get Alpaca API keys from Secrets Manager (like dispatcher)
    alpaca_key_id = None
    alpaca_secret_key = None
    
    if data_source == 'alpaca':
        # Use same secret as dispatcher
        secret_name = 'ops-pipeline/alpaca'
        alpaca_secret = secrets.get_secret_value(SecretId=secret_name)
        alpaca_creds = json.loads(alpaca_secret['SecretString'])
        
        alpaca_key_id = alpaca_creds['api_key']
        alpaca_secret_key = alpaca_creds['api_secret']
    
    return {
        'db': {
            'host': db_host,
            'port': int(db_port),
            'database': db_name,
            'user': secret_data['username'],
            'password': secret_data['password']
        },
        'tickers': tickers,
        'lookback_minutes': lookback_minutes,
        'interval': interval,
        'data_source': data_source,
        'alpaca': {
            'key_id': alpaca_key_id,
            'secret_key': alpaca_secret_key
        } if data_source == 'alpaca' else None
    }
