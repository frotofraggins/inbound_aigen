"""
Configuration loader for Dispatcher service.
Reads from AWS SSM Parameter Store and Secrets Manager.
All risk gates and limits are config-driven for easy tuning.
"""
import json
import boto3
import os
from typing import Dict, Any, Tuple

# Account size tiers for dynamic risk management
ACCOUNT_TIERS = {
    'tiny': {
        'max_size': 2000,
        'risk_pct_day': 0.15,      # 15% - balanced for small accounts
        'risk_pct_swing': 0.08,    # 8%
        'max_contracts': 1,
        'min_confidence': 0.45,    # Align with swing threshold to allow tiny to trade
        'min_volume_ratio': 2.0     # Volume surge required
    },
    'small': {
        'max_size': 5000,
        'risk_pct_day': 0.12,      # 12%
        'risk_pct_swing': 0.08,    # 8%
        'max_contracts': 3,
        'min_confidence': 0.65,
        'min_volume_ratio': 1.8
    },
    'medium': {
        'max_size': 25000,
        'risk_pct_day': 0.04,      # 4%
        'risk_pct_swing': 0.06,    # 6%
        'max_contracts': 5,
        'min_confidence': 0.55,
        'min_volume_ratio': 1.5
    },
    'large': {
        'max_size': 999999999,
        'risk_pct_day': 0.01,      # 1% - professional
        'risk_pct_swing': 0.02,    # 2%
        'max_contracts': 10,
        'min_confidence': 0.45,
        'min_volume_ratio': 1.2
    }
}

def get_account_tier(buying_power: float) -> Tuple[str, Dict[str, Any]]:
    """
    Determine account tier based on buying power.
    Returns: (tier_name, tier_config)
    """
    for tier_name in ['tiny', 'small', 'medium', 'large']:
        tier_config = ACCOUNT_TIERS[tier_name]
        if buying_power <= tier_config['max_size']:
            return tier_name, tier_config
    
    # Default to large
    return 'large', ACCOUNT_TIERS['large']

def load_config() -> Dict[str, Any]:
    """
    Load configuration from AWS SSM and Secrets Manager.
    MULTI-ACCOUNT SUPPORT: Reads account-specific credentials based on ACCOUNT_TIER env var.
    Returns dict with all necessary connection parameters and risk limits.
    """
    region = os.environ.get('AWS_REGION', 'us-west-2')
    ssm = boto3.client('ssm', region_name=region)
    secrets = boto3.client('secretsmanager', region_name=region)
    
    # Load database connection parameters from SSM
    db_host = ssm.get_parameter(Name='/ops-pipeline/db_host')['Parameter']['Value']
    db_port = ssm.get_parameter(Name='/ops-pipeline/db_port')['Parameter']['Value']
    db_name = ssm.get_parameter(Name='/ops-pipeline/db_name')['Parameter']['Value']
    
    # Load database credentials from Secrets Manager
    secret_value = secrets.get_secret_value(SecretId='ops-pipeline/db')
    secret_data = json.loads(secret_value['SecretString'])
    
    # MULTI-ACCOUNT: Load account-specific Alpaca credentials
    account_tier = os.environ.get('ACCOUNT_TIER', 'large')  # tiny/small/medium/large
    tier_config = dict(ACCOUNT_TIERS.get(account_tier, ACCOUNT_TIERS['large']))
    
    try:
        # Try to load tier-specific credentials
        secret_name = f'ops-pipeline/alpaca/{account_tier}'
        alpaca_secret = secrets.get_secret_value(SecretId=secret_name)
        alpaca_creds = json.loads(alpaca_secret['SecretString'])
        print(f"Loaded {account_tier} account credentials: {alpaca_creds.get('account_name', 'unknown')}")
    except:
        # Fallback to default secret for backwards compatibility
        alpaca_secret = secrets.get_secret_value(SecretId='ops-pipeline/alpaca')
        alpaca_creds = json.loads(alpaca_secret['SecretString'])
        alpaca_creds['account_name'] = 'large-default'
        print(f"Using default Alpaca credentials (no tier-specific secret found)")
    
    # Try to load dispatcher-specific config from SSM (tier-specific)
    # MULTI-ACCOUNT: Load tier-specific config based on ACCOUNT_TIER env var
    try:
        config_name = f'/ops-pipeline/dispatcher_config_{account_tier}'
        dispatcher_config_str = ssm.get_parameter(Name=config_name)['Parameter']['Value']
        dispatcher_config = json.loads(dispatcher_config_str)
        print(f"Loaded tier-specific config: {config_name}")
    except:
        # Fallback to default config for backwards compatibility
        try:
            dispatcher_config_str = ssm.get_parameter(
                Name='/ops-pipeline/dispatcher_config'
            )['Parameter']['Value']
            dispatcher_config = json.loads(dispatcher_config_str)
            print(f"Using default config (no tier-specific config found)")
        except:
            # Use sensible defaults
            dispatcher_config = {}
            print(f"Using hardcoded defaults (no SSM config found)")

    # Paper trading sizing overrides (optional)
    paper_ignore_buying_power = dispatcher_config.get('paper_ignore_buying_power', False)
    paper_buying_power_override = dispatcher_config.get('paper_buying_power_override')
    paper_risk_pct_day = dispatcher_config.get('paper_risk_pct_day')
    paper_risk_pct_swing = dispatcher_config.get('paper_risk_pct_swing')
    paper_max_contracts = dispatcher_config.get('paper_max_contracts')

    if paper_ignore_buying_power:
        # Override tier risk limits for paper training if provided
        if paper_risk_pct_day is not None:
            tier_config['risk_pct_day'] = paper_risk_pct_day
        if paper_risk_pct_swing is not None:
            tier_config['risk_pct_swing'] = paper_risk_pct_swing
        if paper_max_contracts is not None:
            tier_config['max_contracts'] = paper_max_contracts
    
    return {
        # Database connection
        'db_host': db_host,
        'db_port': int(db_port),
        'db_name': db_name,
        'db_user': secret_data['username'],
        'db_password': secret_data['password'],
        'region': region,
        
        # MULTI-ACCOUNT: Alpaca credentials (tier-specific)
        'alpaca_api_key': alpaca_creds.get('api_key'),
        'alpaca_api_secret': alpaca_creds.get('api_secret'),
        'account_name': alpaca_creds.get('account_name', 'unknown'),
        'account_tier': account_tier,
        'account_tier_config': tier_config,
        'paper_ignore_buying_power': paper_ignore_buying_power,
        'paper_buying_power_override': paper_buying_power_override,
        
        # Global risk gates (config-driven)
        'max_signals_per_run': dispatcher_config.get('max_signals_per_run', 10),
        'max_trades_per_ticker_per_day': dispatcher_config.get('max_trades_per_ticker_per_day', 2),
        'confidence_min': dispatcher_config.get('confidence_min', 0.70),
        'lookback_window_minutes': dispatcher_config.get('lookback_window_minutes', 60),
        'processing_ttl_minutes': dispatcher_config.get('processing_ttl_minutes', 10),
        'max_open_positions': dispatcher_config.get('max_open_positions', 5),
        'max_notional_exposure': dispatcher_config.get('max_notional_exposure', 10000),
        'max_daily_loss': dispatcher_config.get('max_daily_loss', 500),
        
        # Data freshness gates
        'max_bar_age_seconds': dispatcher_config.get('max_bar_age_seconds', 120),
        'max_feature_age_seconds': dispatcher_config.get('max_feature_age_seconds', 300),
        
        # Allowed actions (block certain types in production)
        'allowed_actions': dispatcher_config.get('allowed_actions', [
            'BUY_CALL', 'BUY_PUT', 'BUY_STOCK'
            # 'SELL_PREMIUM' blocked until we add proper risk controls
        ]),
        'allow_shorting': dispatcher_config.get('allow_shorting', False),

        # Confidence gates (tier-aware for options)
        'confidence_min_options_daytrade': max(
            dispatcher_config.get('confidence_min_options_daytrade', 0.60),
            tier_config['min_confidence']
        ),
        'confidence_min_options_swing': max(
            dispatcher_config.get('confidence_min_options_swing', 0.45),
            tier_config['min_confidence']
        ),
        'confidence_min_options': max(
            dispatcher_config.get('confidence_min_options', 0.55),
            tier_config['min_confidence']
        ),
        'confidence_min_stock': dispatcher_config.get('confidence_min_stock', 0.35),
        
        # Simulation parameters
        'paper_equity': dispatcher_config.get('paper_equity', 100000.0),
        'max_risk_per_trade_pct': dispatcher_config.get('max_risk_per_trade_pct', 0.02),  # 2%
        'default_slippage_bps': dispatcher_config.get('default_slippage_bps', 5),
        'fill_model': dispatcher_config.get('fill_model', 'close+slip'),
        
        # Stop loss / Take profit parameters
        'stop_loss_atr_mult': dispatcher_config.get('stop_loss_atr_mult', 2.0),
        'take_profit_risk_reward': dispatcher_config.get('take_profit_risk_reward', 2.0),
        'max_hold_minutes': dispatcher_config.get('max_hold_minutes', 240),  # 4 hours default
    }
