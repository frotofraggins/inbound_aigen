"""
Configuration loader for Market Data Stream service.
Reads from AWS SSM Parameter Store and Secrets Manager.
Includes Alpaca API keys for WebSocket connection.
"""
import json
import boto3
import os

def load_config():
    """
    Load configuration from AWS SSM and Secrets Manager.
    Returns dict with all necessary connection parameters.
    """
    region = os.environ.get('AWS_REGION', 'us-west-2')
    ssm = boto3.client('ssm', region_name=region)
    secrets = boto3.client('secretsmanager', region_name=region)
    
    # Load database connection parameters from SSM
    db_host = ssm.get_parameter(Name='/ops-pipeline/db_host')['Parameter']['Value']
    db_port = ssm.get_parameter(Name='/ops-pipeline/db_port')['Parameter']['Value']
    db_name = ssm.get_parameter(Name='/ops-pipeline/db_name')['Parameter']['Value']
    
    # Load database credentials from Secrets Manager
    db_secret = secrets.get_secret_value(SecretId='ops-pipeline/db')
    db_data = json.loads(db_secret['SecretString'])
    
    # Load Alpaca API keys from Secrets Manager
    alpaca_secret = secrets.get_secret_value(SecretId='ops-pipeline/alpaca')
    alpaca_data = json.loads(alpaca_secret['SecretString'])
    
    return {
        # Database
        'db_host': db_host,
        'db_port': int(db_port),
        'db_name': db_name,
        'db_user': db_data['username'],
        'db_password': db_data['password'],
        
        # Alpaca API
        'alpaca_api_key': alpaca_data['api_key'],
        'alpaca_api_secret': alpaca_data['api_secret'],
        
        # Signal generation parameters
        'cooldown_minutes': 15,  # Don't re-signal same ticker within 15 min
        'sentiment_window_minutes': 30,  # Look at sentiment from last 30 min
        
        # AWS
        'region': region
    }
