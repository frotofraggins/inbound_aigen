"""
Market Data Stream - POLLING VERSION (No WebSocket)
Gets current prices every 60 seconds via REST API
Creates synthetic 1-minute bars for technical analysis

WHY: Paper account WebSocket doesn't deliver bars
SOLUTION: Poll prices, create bars, feed to system
"""
import asyncio
import logging
import sys
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from collections import defaultdict

import config
import db
from rules import compute_signal
from gap_fade import integrate_gap_fade_with_momentum

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder for Decimal types."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)

def log_event(event_type, data):
    """Log structured JSON event."""
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
price_history = defaultdict(list)  # Track OHLCV per minute

def get_current_prices_rest(tickers):
    """
    Get current prices using REST API (no WebSocket needed).
    Uses requests library for simple HTTP calls.
    """
    import requests
    
    # Use Trading API - quotes endpoint
    url = f"https://paper-api.alpaca.markets/v2/stocks/quotes/latest"
    params = {'symbols': ','.join(tickers)}
    headers = {
        'APCA-API-KEY-ID': cfg['alpaca_api_key'],
        'APCA-API-SECRET-KEY': cfg['alpaca_api_secret']
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        prices = {}
        for symbol, quote_data in data.get('quotes', {}).items():
            # Use midpoint of bid/ask as current price
            bid = quote_data.get('bp', 0)
            ask = quote_data.get('ap', 0)
            if bid > 0 and ask > 0:
                prices[symbol] = (bid + ask) / 2
            elif ask > 0:
                prices[symbol] = ask
            elif bid > 0:
                prices[symbol] = bid
        
        return prices
        
    except Exception as e:
        logger.error(f"Error fetching prices: {e}")
        return {}

def create_synthetic_bar(ticker, price, timestamp):
    """
    Create a 1-minute bar from current price.
    Aggregates multiple price updates into OHLCV.
    """
    global price_history
    
    # Add to price history for this minute
    minute_key = timestamp.replace(second=0, microsecond=0)
    price_history[ticker].append({
        'price': price,
        'time': timestamp
    })
    
    # Get all prices for this minute
    minute_prices = [p['price'] for p in price_history[ticker] 
                     if p['time'].replace(second=0, microsecond=0) == minute_key]
    
    if not minute_prices:
        return None
    
    # Create OHLCV bar
    bar = {
        'ticker': ticker,
        'ts': minute_key,
        'open': minute_prices[0],
        'high': max(minute_prices),
        'low': min(minute_prices),
        'close': minute_prices[-1],  # Last price
        'volume': 1000  # Synthetic volume (not accurate but needed for features)
    }
    
    # Clean up old history (keep last 2 minutes only)
    cutoff = timestamp.replace(second=0, microsecond=0)
    price_history[ticker] = [p for p in price_history[ticker] 
                             if (cutoff - p['time'].replace(second=0, microsecond=0)).total_seconds() < 120]
    
    return bar

async def poll_and_process():
    """
    Main polling loop - runs every 60 seconds.
    Gets prices, creates bars, generates signals.
    """
    global watchlist_tickers, last_signal_time
    
    poll_count = 0
    bars_created = 0
    signals_created = 0
    
    while True:
        try:
            poll_count += 1
            now = datetime.now(timezone.utc)
            
            # Get current prices for all watchlist tickers
            prices = get_current_prices_rest(watchlist_tickers)
            
            if not prices:
                log_event('poll_failed', {
                    'poll_num': poll_count,
                    'reason': 'No prices returned'
                })
                await asyncio.sleep(60)
                continue
            
            log_event('prices_fetched', {
                'poll_num': poll_count,
                'ticker_count': len(prices),
                'sample': {k: round(v, 2) for k, v in list(prices.items())[:3]}
            })
            
            # Process each ticker
            for ticker, price in prices.items():
                try:
                    # Create synthetic bar
                    bar = create_synthetic_bar(ticker, price, now)
                    
                    if bar:
                        # Insert bar into database
                        db.insert_bar(db_conn, bar)
                        bars_created += 1
                        
                        log_event('bar_created', {
                            'ticker': ticker,
                            'price': round(price, 2),
                            'bar': {k: round(float(v), 2) if k != 'ts' and k != 'ticker' else v 
                                   for k, v in bar.items()}
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
                            'confidence': round(confidence, 3)
                        })
                        
                        # Insert actionable signals
                        if action != 'HOLD':
                            reason_json = json.dumps(reason, cls=DecimalEncoder)
                            features_json = json.dumps({
                                'v': 1, 'source': 'polling',
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
                            
                            log_event('signal_created', {
                                'id': rec_id,
                                'ticker': ticker,
                                'action': action
                            })
                
                except Exception as e:
                    logger.error(f"Error processing {ticker}: {e}")
            
            # Log stats every 5 polls
            if poll_count % 5 == 0:
                log_event('stats', {
                    'polls': poll_count,
                    'bars_created': bars_created,
                    'signals_created': signals_created,
                    'watchlist_size': len(watchlist_tickers)
                })
            
        except Exception as e:
            logger.error(f"Error in poll loop: {e}", exc_info=True)
        
        # Wait 60 seconds until next poll
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
    logger.info("🚀 Market Data Stream - POLLING VERSION")
    logger.info(f"   Started: {datetime.now(timezone.utc)}")
    logger.info(f"   Method: REST API polling (60 sec intervals)")
    logger.info(f"   Reason: Paper account WebSocket has no bar data")
    logger.info("=" * 80)
    
    # Initialize
    log_event('service_start', {'service': 'market-data-polling'})
    
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
    logger.info("🎯 Starting 60-second polling loop...")
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
    # Install requests if not available
    try:
        import requests
    except ImportError:
        logger.info("Installing requests library...")
        os.system("pip install requests")
        import requests
    
    asyncio.run(main())
