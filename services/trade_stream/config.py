"""
Trade-stream Configuration
Loads from environment variables injected by ECS/Secrets Manager.
"""
import os
from datetime import time

def load_config():
    """Load configuration from environment variables."""
    required = [
        'DB_HOST',
        'DB_NAME',
        'DB_USER',
        'DB_PASSWORD',
        'ALPACA_API_KEY',
        'ALPACA_API_SECRET',
    ]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

    return {
        'db_host': os.getenv('DB_HOST'),
        'db_port': int(os.getenv('DB_PORT', '5432')),
        'db_name': os.getenv('DB_NAME'),
        'db_user': os.getenv('DB_USER'),
        'db_password': os.getenv('DB_PASSWORD'),
        'alpaca_api_key': os.getenv('ALPACA_API_KEY'),
        'alpaca_api_secret': os.getenv('ALPACA_API_SECRET'),
        'alpaca_base_url': os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets'),
        'account_name': os.getenv('ACCOUNT_NAME', 'unknown'),
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
ACCOUNT_NAME = _config['account_name']
IS_PAPER_TRADING = 'paper' in ALPACA_BASE_URL

# Exit rules
DAY_TRADE_CLOSE_TIME = time(15, 55)  # 3:55 PM ET
OPTIONS_EXPIRY_WARNING_HOURS = 24
MAX_HOLD_MINUTES_DEFAULT = 240  # 4 hours

# Monitoring
CHECK_INTERVAL_SECONDS = 60
PRICE_UPDATE_TIMEOUT = 10
ACCOUNT_ACTIVITY_POLL_SECONDS = int(os.getenv('ACCOUNT_ACTIVITY_POLL_SECONDS', '120'))
ACCOUNT_ACTIVITY_LOOKBACK_DAYS = int(os.getenv('ACCOUNT_ACTIVITY_LOOKBACK_DAYS', '7'))
ACCOUNT_ACTIVITY_PAGE_SIZE = int(os.getenv('ACCOUNT_ACTIVITY_PAGE_SIZE', '100'))

# Alerts
ALERT_EMAIL = os.getenv('ALERT_EMAIL', 'nsflournoy@gmail.com')

# Logging
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
