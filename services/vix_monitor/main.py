"""
VIX Regime Monitor - Track market volatility and fear
Runs daily to fetch VIX values and classify market regime
Helps system avoid high-risk periods

VIX Levels (Professional interpretation):
- VIX < 12: Complacency (market too calm, reversals likely)
- VIX 12-20: Normal (healthy trading environment)
- VIX 20-30: Elevated (caution, reduce size)
- VIX 30-40: High (defensive, minimal trading)
- VIX > 40: Extreme (halt new trades, close positions)
"""
import json
import sys
from datetime import datetime, timedelta
import logging
import yfinance as yf
import boto3
import psycopg2
from psycopg2.extras import RealDictCursor

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def log_event(event_type, data):
    """Log structured JSON event"""
    event = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'event': event_type,
        'data': data
    }
    print(json.dumps(event), flush=True)

def load_config():
    """Load configuration from AWS SSM and Secrets Manager"""
    region = 'us-west-2'
    ssm = boto3.client('ssm', region_name=region)
    secrets = boto3.client('secretsmanager', region_name=region)
    
    # Database connection
    db_host = ssm.get_parameter(Name='/ops-pipeline/db_host')['Parameter']['Value']
    db_port = ssm.get_parameter(Name='/ops-pipeline/db_port')['Parameter']['Value']
    db_name = ssm.get_parameter(Name='/ops-pipeline/db_name')['Parameter']['Value']
    
    secret = secrets.get_secret_value(SecretId='ops-pipeline/db')
    db_data = json.loads(secret['SecretString'])
    
    return {
        'db_host': db_host,
        'db_port': int(db_port),
        'db_name': db_name,
        'db_user': db_data['username'],
        'db_password': db_data['password']
    }

def get_db_connection(config):
    """Create database connection"""
    return psycopg2.connect(
        host=config['db_host'],
        port=config['db_port'],
        dbname=config['db_name'],
        user=config['db_user'],
        password=config['db_password']
    )

def fetch_vix_current():
    """
    Fetch current VIX value from Yahoo Finance
    Returns: (vix_value, timestamp)
    """
    try:
        vix = yf.Ticker("^VIX")
        
        # Get latest intraday data
        hist = vix.history(period="1d", interval="1m")
        
        if hist.empty:
            # Fallback to daily data
            hist = vix.history(period="5d")
            
        if not hist.empty:
            latest_close = float(hist['Close'].iloc[-1])
            latest_time = hist.index[-1]
            
            return latest_close, latest_time
        
        return None, None
        
    except Exception as e:
        logger.error(f"Error fetching VIX: {e}")
        return None, None

def classify_regime(vix_value):
    """
    Classify market regime based on VIX level
    
    Returns:
        regime: 'complacent', 'normal', 'elevated', 'high', 'extreme'
        risk_multiplier: 0.0 (halt) to 1.0 (normal)
        position_size_multiplier: How much to reduce position size
    """
    if vix_value < 12:
        return {
            'regime': 'complacent',
            'risk_level': 2,  # Medium risk (reversals likely)
            'position_size_multiplier': 0.8,
            'new_trades_allowed': True,
            'confidence_adjustment': 0.9,
            'message': 'VIX too low - market complacency, reversals likely'
        }
    elif vix_value < 20:
        return {
            'regime': 'normal',
            'risk_level': 1,  # Low risk
            'position_size_multiplier': 1.0,
            'new_trades_allowed': True,
            'confidence_adjustment': 1.0,
            'message': 'VIX normal - healthy trading environment'
        }
    elif vix_value < 30:
        return {
            'regime': 'elevated',
            'risk_level': 3,  # Elevated risk
            'position_size_multiplier': 0.5,  # Half size
            'new_trades_allowed': True,
            'confidence_adjustment': 0.8,
            'message': 'VIX elevated - reduce size, increase caution'
        }
    elif vix_value < 40:
        return {
            'regime': 'high',
            'risk_level': 4,  # High risk
            'position_size_multiplier': 0.25,  # Quarter size
            'new_trades_allowed': True,
            'confidence_adjustment': 0.6,
            'message': 'VIX high - defensive mode, minimal trading'
        }
    else:
        return {
            'regime': 'extreme',
            'risk_level': 5,  # Extreme risk
            'position_size_multiplier': 0.0,  # No new positions
            'new_trades_allowed': False,
            'confidence_adjustment': 0.0,
            'message': 'VIX extreme - halt new trades, close positions'
        }

def store_vix_value(conn, vix_value, regime_data):
    """Store VIX value and regime classification in database"""
    query = """
    INSERT INTO vix_history (
        vix_value, regime, risk_level,
        position_size_multiplier, new_trades_allowed,
        confidence_adjustment, regime_message,
        recorded_at
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
    """
    
    with conn.cursor() as cur:
        cur.execute(query, (
            vix_value,
            regime_data['regime'],
            regime_data['risk_level'],
            regime_data['position_size_multiplier'],
            regime_data['new_trades_allowed'],
            regime_data['confidence_adjustment'],
            regime_data['message']
        ))
        conn.commit()

def get_latest_regime(conn):
    """Get most recent VIX regime assessment"""
    query = """
    SELECT vix_value, regime, risk_level,
           position_size_multiplier, new_trades_allowed,
           confidence_adjustment, regime_message,
           recorded_at
    FROM vix_history
    ORDER BY recorded_at DESC
    LIMIT 1
    """
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query)
        result = cur.fetchone()
        return dict(result) if result else None

def main():
    """Main execution - fetch VIX and update regime"""
    log_event('service_start', {'service': 'vix-monitor'})
    
    try:
        # Load config
        config = load_config()
        log_event('config_loaded', {'db_host': config['db_host']})
        
        # Connect to database
        conn = get_db_connection(config)
        log_event('database_connected', {})
        
        # Fetch current VIX
        vix_value, vix_time = fetch_vix_current()
        
        if vix_value is None:
            logger.error("Failed to fetch VIX value")
            sys.exit(1)
        
        log_event('vix_fetched', {
            'vix_value': round(vix_value, 2),
            'timestamp': str(vix_time)
        })
        
        # Classify regime
        regime_data = classify_regime(vix_value)
        
        log_event('regime_classified', {
            'vix': round(vix_value, 2),
            'regime': regime_data['regime'],
            'risk_level': regime_data['risk_level'],
            'position_size_mult': regime_data['position_size_multiplier'],
            'new_trades_allowed': regime_data['new_trades_allowed'],
            'message': regime_data['message']
        })
        
        # Store in database
        store_vix_value(conn, vix_value, regime_data)
        
        log_event('vix_stored', {'regime': regime_data['regime']})
        
        # Get historical context
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    AVG(vix_value) as avg_vix_7d,
                    MAX(vix_value) as max_vix_7d,
                    MIN(vix_value) as min_vix_7d
                FROM vix_history
                WHERE recorded_at > NOW() - INTERVAL '7 days'
            """)
            stats = cur.fetchone()
            
            if stats and stats[0]:
                log_event('vix_context', {
                    'current': round(vix_value, 2),
                    'avg_7d': round(float(stats[0]), 2),
                    'max_7d': round(float(stats[1]), 2),
                    'min_7d': round(float(stats[2]), 2),
                    'trend': 'rising' if vix_value > float(stats[0]) else 'falling'
                })
        
        conn.close()
        
        log_event('service_complete', {
            'regime': regime_data['regime'],
            'action': 'halt_trades' if not regime_data['new_trades_allowed'] else 'reduce_size' if regime_data['position_size_multiplier'] < 1.0 else 'normal'
        })
        
        logger.info("✅ VIX monitoring complete")
        
    except Exception as e:
        log_event('error', {
            'error_type': type(e).__name__,
            'error_message': str(e)
        })
        logger.error(f"VIX monitor failed: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
