"""
Market Data Stream - Historical IEX Polling
Uses FREE historical IEX bars API (15+ min delayed)

WORKS WITH FREE ACCOUNT!
Per Alpaca FAQ: Historical IEX data available if query is 15+ minutes old
"""
import asyncio
import logging
import sys
import json
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import config
import db
from rules import compute_signal
from gap_fade import integrate_gap_fade_with_momentum

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)

def log_event(event_type, data):
    event = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'event': event_type,
        'data': data
    }
    print(json.dumps(event, cls=DecimalEncoder), flush=True)

# Global state
db_conn = None
cfg = None
watchlist_tickers = []
last_signal_time = {}

def get_historical_iex_bars(tickers):
    """
    Get historical IEX bars using FREE endpoint.
    Must query data that is at least 15 minutes old.
    """
    import requests
    
    # Query data from 20 minutes ago (safely beyond 15 min requirement)
    end_time = datetime.now(timezone.utc) - timedelta(minutes=20)
    start_time = end_time - timedelta(minutes=5)  # Get last 5 minutes of data
    
    url = "https://data.alpaca.markets/v2/stocks/bars"
    params = {
        'symbols': ','.join(tickers),
        'timeframe': '1Min',
        'start': start_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'end': end_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'feed': 'iex',  # FREE IEX feed
        'limit': 1000
    }
    headers = {
        'APCA-API-KEY-ID': cfg['alpaca_api_key'],
        'APCA-API-SECRET-KEY': cfg['alpaca_api_secret']
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Convert to our bar format
        bars_by_ticker = {}
        for symbol, bars in data.get('bars', {}).items():
            if bars:
                # Get most recent bar for each ticker
                latest = bars[-1]
                bars_by_ticker[symbol] = {
                    'ticker': symbol,
                    'ts': datetime.fromisoformat(latest['t'].replace('Z', '+00:00')),
                    'open': float(latest['o']),
                    'high': float(latest['h']),
                    'low': float(latest['l']),
                    'close': float(latest['c']),
                    'volume': int(latest['v'])
                }
        
        return bars_by_ticker
        
    except Exception as e:
        logger.error(f"Error fetching IEX bars: {e}")
        return {}

async def poll_and_process():
    """
    Main polling loop - runs every 60 seconds.
    Gets delayed IEX bars, processes signals.
    """
    global watchlist_tickers, last_signal_time
    
    poll_count = 0
    bars_created = 0
    signals_created = 0
    
    while True:
        try:
            poll_count += 1
            now = datetime.now(timezone.utc)
            
            # Get historical IEX bars (15+ min delayed)
            bars = get_historical_iex_bars(watchlist_tickers)
            
            if not bars:
                log_event('poll_no_data', {
                    'poll_num': poll_count,
                    'reason': 'No IEX bars (market may be closed or low volume)'
                })
                await asyncio.sleep(60)
                continue
            
            log_event('bars_fetched', {
                'poll_num': poll_count,
                'bar_count': len(bars),
                'sample': {k: f"${v['close']:.2f}" for k, v in list(bars.items())[:3]},
                'delay_minutes': 20
            })
            
            # Process each bar
            for ticker, bar in bars.items():
                try:
                    # Insert bar into database
                    db.insert_bar(db_conn, bar)
                    bars_created += 1
                    
                    log_event('bar_stored', {
                        'ticker': ticker,
                        'price': round(bar['close'], 2),
                        'volume': bar['volume'],
                        'timestamp': bar['ts'].isoformat()
                    })
                    
                    # Check cooldown
                    if ticker in last_signal_time:
                        time_since_last = (now - last_signal_time[ticker]).total_seconds()
                        if time_since_last < (cfg['cooldown_minutes'] * 60):
                            continue
                    
                    # Get features
                    features_map = db.get_latest_features(db_conn, [ticker])
                    features = features_map.get(ticker)
                    
                    if not features:
                        continue
                    
                    # Update with current bar
                    features['close'] = bar['close']
                    features['volume_current'] = bar['volume']
                    
                    # Recalculate volume ratio
                    if features.get('volume_avg_20'):
                        features['volume_ratio'] = bar['volume'] / features['volume_avg_20']
                        features['volume_surge'] = features['volume_ratio'] > 2.0
                    
                    # Get sentiment
                    sentiment_map = db.get_recent_sentiment(
                        db_conn, [ticker], cfg['sentiment_window_minutes']
                    )
                    sentiment = sentiment_map.get(ticker)
                    
                    # Check gap fade
                    gap_fade_signal = integrate_gap_fade_with_momentum(ticker, features, db_conn)
                    
                    # Compute signal
                    if gap_fade_signal:
                        action = gap_fade_signal['action']
                        instrument_type = gap_fade_signal['instrument']
                        strategy_type = gap_fade_signal['strategy']
                        confidence = gap_fade_signal['confidence']
                        reason = gap_fade_signal
                    else:
                        action, instrument_type, strategy_type, confidence, reason = compute_signal(
                            ticker, features, sentiment
                        )
                    
                    # Log signal
                    log_event('signal_computed', {
                        'ticker': ticker,
                        'action': action,
                        'confidence': round(confidence, 3),
                        'source': 'iex_historical_delayed'
                    })
                    
                    # Insert actionable signals
                    if action != 'HOLD':
                        reason_json = json.dumps(reason, cls=DecimalEncoder)
                        features_json = json.dumps({
                            'v': 1, 'source': 'iex_delayed',
                            'close': features.get('close'),
                            'sma20': features.get('sma20'),
                            'sma50': features.get('sma50')
                        }, cls=DecimalEncoder)
                        sentiment_json = json.dumps(sentiment, cls=DecimalEncoder) if sentiment else None
                        
                        rec_id = db.insert_recommendation(
                            db_conn, ticker, action, instrument_type,
                            strategy_type, confidence, reason_json,
                            features_json, sentiment_json
                        )
                        
                        last_signal_time[ticker] = now
                        signals_created += 1
                        
                        log_event('recommendation_created', {
                            'id': rec_id,
                            'ticker': ticker,
                            'action': action,
                            'data_delay': '15-20_minutes'
                        })
                
                except Exception as e:
                    logger.error(f"Error processing {ticker}: {e}")
            
            # Log stats every 5 polls
            if poll_count % 5 == 0:
                log_event('stats', {
                    'polls': poll_count,
                    'bars_created': bars_created,
                    'signals_created': signals_created,
                    'watchlist_size': len(watchlist_tickers),
                    'data_source': 'IEX_historical_FREE'
                })
            
        except Exception as e:
            logger.error(f"Error in poll loop: {e}", exc_info=True)
        
        # Wait 60 seconds
        await asyncio.sleep(60)

async def watchlist_refresh():
    """Refresh watchlist every 5 minutes."""
    global watchlist_tickers
    
    while True:
        try:
            await asyncio.sleep(300)
            
            watchlist = db.get_watchlist_top30(db_conn)
            new_tickers = [row['ticker'] for row in watchlist]
            
            if new_tickers != watchlist_tickers:
                log_event('watchlist_updated', {
                    'old': len(watchlist_tickers),
                    'new': len(new_tickers)
                })
                watchlist_tickers = new_tickers
        
        except Exception as e:
            logger.error(f"Watchlist refresh error: {e}")

async def main():
    """Main entry point."""
    global db_conn, cfg, watchlist_tickers
    
    logger.info("=" * 80)
    logger.info("🚀 Market Data Stream - Historical IEX (FREE)")
    logger.info(f"   Started: {datetime.now(timezone.utc)}")
    logger.info(f"   Method: Historical IEX bars (15-20 min delayed)")
    logger.info(f"   Cost: $0/month - Works with FREE account!")
    logger.info("=" * 80)
    
    # Initialize
    log_event('service_start', {'service': 'market-data-iex-historical', 'cost': 'FREE'})
    
    cfg = config.load_config()
    log_event('config_loaded', {'region': cfg['region']})
    
    db_conn = db.get_connection(cfg)
    log_event('database_connected', {'db_host': cfg['db_host']})
    
    watchlist = db.get_watchlist_top30(db_conn)
    watchlist_tickers = [row['ticker'] for row in watchlist]
    log_event('watchlist_loaded', {
        'count': len(watchlist_tickers),
        'tickers': watchlist_tickers
    })
    
    if not watchlist_tickers:
        logger.error("❌ No watchlist tickers")
        sys.exit(1)
    
    logger.info(f"✅ Loaded {len(watchlist_tickers)} tickers")
    logger.info("🎯 Starting 60-second polling loop (15-20 min delayed data)...")
    logger.info("=" * 80)
    
    # Start tasks
    poll_task = asyncio.create_task(poll_and_process())
    watchlist_task = asyncio.create_task(watchlist_refresh())
    
    try:
        await asyncio.gather(poll_task, watchlist_task)
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down...")
    finally:
        if db_conn:
            db_conn.close()

if __name__ == "__main__":
    # Install requests if needed
    try:
        import requests
    except ImportError:
        import os
        logger.info("Installing requests library...")
        os.system("pip install requests")
        import requests
    
    asyncio.run(main())
