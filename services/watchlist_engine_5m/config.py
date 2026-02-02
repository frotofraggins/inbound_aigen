"""
Configuration loader for watchlist engine
"""

import json
import boto3
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
    
    # Get universe tickers
    universe_param = ssm.get_parameter(Name='/ops-pipeline/universe_tickers')
    tickers = [t.strip() for t in universe_param['Parameter']['Value'].split(',')]
    
    return {
        'db': {
            'host': db_host,
            'port': int(db_port),
            'database': db_name,
            'user': secret_data['username'],
            'password': secret_data['password']
        },
        'db_host': db_host,
        'db_port': db_port,
        'db_name': db_name,
        'db_user': secret_data['username'],
        'db_password': secret_data['password'],
        'tickers': tickers,
        'universe_tickers': tickers,
        'watchlist_size': 30,
        'entry_threshold': 0.6,
        'exit_threshold': 0.3,
        'min_retention_minutes': 30
    }
