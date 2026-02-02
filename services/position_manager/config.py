"""
Position Manager Configuration
Loads from AWS SSM/Secrets Manager like dispatcher
"""
import os
import json
import boto3
from datetime import time

def load_config():
    """Load configuration from AWS SSM and Secrets Manager"""
    region = os.environ.get('AWS_REGION', 'us-west-2')
    ssm = boto3.client('ssm', region_name=region)
    secrets = boto3.client('secretsmanager', region_name=region)
    
    # Load database connection
    db_host = ssm.get_parameter(Name='/ops-pipeline/db_host')['Parameter']['Value']
    db_port = ssm.get_parameter(Name='/ops-pipeline/db_port')['Parameter']['Value']
    db_name = ssm.get_parameter(Name='/ops-pipeline/db_name')['Parameter']['Value']
    
    secret_value = secrets.get_secret_value(SecretId='ops-pipeline/db')
    secret_data = json.loads(secret_value['SecretString'])
    
    # Load Alpaca credentials from Secrets Manager
    alpaca_secret = secrets.get_secret_value(SecretId='ops-pipeline/alpaca')
    alpaca_data = json.loads(alpaca_secret['SecretString'])
    
    return {
        'db_host': db_host,
        'db_port': int(db_port),
        'db_name': db_name,
        'db_user': secret_data['username'],
        'db_password': secret_data['password'],
        'alpaca_api_key': alpaca_data['api_key'],
        'alpaca_api_secret': alpaca_data['api_secret'],
        'alpaca_base_url': alpaca_data.get('base_url', 'https://paper-api.alpaca.markets')
    }

# Load config on import
_config = load_config()

# Database
DB_HOST = _config['db_host']
DB_PORT = _config['db_port']
DB_NAME = _config['db_name']
DB_USER = _config['db_user']
DB_PASSWORD = _config['db_password']

# Alpaca
ALPACA_API_KEY = _config['alpaca_api_key']
ALPACA_API_SECRET = _config['alpaca_api_secret']
ALPACA_BASE_URL = _config['alpaca_base_url']

# Exit rules
DAY_TRADE_CLOSE_TIME = time(15, 55)  # 3:55 PM ET
OPTIONS_EXPIRY_WARNING_HOURS = 24
MAX_HOLD_MINUTES_DEFAULT = 240  # 4 hours

# Monitoring
CHECK_INTERVAL_SECONDS = 60
PRICE_UPDATE_TIMEOUT = 10

# Alerts
ALERT_EMAIL = os.getenv('ALERT_EMAIL', 'nsflournoy@gmail.com')

# Logging
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
