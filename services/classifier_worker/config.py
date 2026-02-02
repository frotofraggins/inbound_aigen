"""
Configuration loader for classifier worker
Loads settings from AWS SSM and Secrets Manager
"""

import json
import boto3
from typing import Dict, Any

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
    
    # Get ticker whitelist
    tickers_param = ssm.get_parameter(Name='/ops-pipeline/tickers')
    tickers = tickers_param['Parameter']['Value'].split(',')
    
    return {
        'db': {
            'host': db_host,
            'port': int(db_port),
            'database': db_name,
            'user': secret_data['username'],
            'password': secret_data['password']
        },
        'tickers': [t.strip() for t in tickers],
        'batch_size': 10,  # Process 10 items per transaction
        'poll_seconds': 5,  # Sleep 5s if no work
        'model_name': 'ProsusAI/finbert'
    }
