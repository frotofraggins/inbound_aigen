"""
Signal Engine - Main orchestration.
Generates trading signals for top 30 watchlist stocks.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal
from config import load_config
from db import (
    get_connection,
    get_watchlist_top30,
    get_latest_features,
    get_recent_sentiment,
    check_cooldown,
    insert_recommendation
)
from rules import compute_signal

class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder to handle Decimal types."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)

def log_event(event_type, data):
    """Log structured JSON event."""
    event = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'event': event_type,
        'data': data
    }
    print(json.dumps(event, cls=DecimalEncoder), flush=True)

def main():
    """Main execution loop."""
    log_event('service_start', {'service': 'signal-engine-1m'})
    
    try:
        # Load configuration
        config = load_config()
        log_event('config_loaded', {
            'region': config['region'],
            'cooldown_minutes': config['cooldown_minutes'],
            'sentiment_window_minutes': config['sentiment_window_minutes']
        })
        
        # Connect to database
        conn = get_connection(config)
        log_event('database_connected', {'db_host': config['db_host']})
        
        # Get top 30 watchlist
        watchlist = get_watchlist_top30(conn)
        tickers = [row['ticker'] for row in watchlist]
        
        log_event('watchlist_loaded', {
            'count': len(watchlist),
            'tickers': tickers
        })
        
        if not tickers:
            log_event('no_watchlist', {'message': 'Watchlist is empty, nothing to process'})
            conn.close()
            return
        
        # Fetch features and sentiment for all watchlist tickers
        features_map = get_latest_features(conn, tickers)
        sentiment_map = get_recent_sentiment(
            conn, 
            tickers, 
            config['sentiment_window_minutes']
        )
        
        log_event('data_loaded', {
            'features_count': len(features_map),
            'sentiment_count': len(sentiment_map),
            'tickers_with_features': list(features_map.keys()),
            'tickers_with_sentiment': list(sentiment_map.keys())
        })
        
        # Generate signals
        signals_generated = 0
        signals_skipped_cooldown = 0
        signals_hold = 0
        
        for ticker in tickers:
            # Get features (required)
            features = features_map.get(ticker)
            if not features:
                log_event('skip_ticker', {
                    'ticker': ticker,
                    'reason': 'No features available'
                })
                continue
            
            # Get sentiment (optional - may not have recent news)
            sentiment = sentiment_map.get(ticker)
            
            # Check cooldown
            in_cooldown = check_cooldown(conn, ticker, config['cooldown_minutes'])
            if in_cooldown:
                log_event('skip_cooldown', {
                    'ticker': ticker,
                    'cooldown_minutes': config['cooldown_minutes']
                })
                signals_skipped_cooldown += 1
                continue
            
            # Compute signal (Phase 15: now returns strategy_type)
            action, instrument_type, strategy_type, confidence, reason = compute_signal(
                ticker,
                features,
                sentiment
            )
            
            # Log the signal decision
            log_event('signal_computed', {
                'ticker': ticker,
                'action': action,
                'instrument_type': instrument_type,
                'strategy_type': strategy_type,
                'confidence': round(confidence, 3),
                'rule': reason.get('rule')
            })
            
            # Only insert actionable signals (not HOLD)
            # HOLD signals should never be persisted, regardless of confidence
            if action != 'HOLD':
                # Convert reason dict to JSON string for JSONB insertion
                reason_json = json.dumps(reason, cls=DecimalEncoder)
                
                # Phase 16: Create feature snapshot (P0 for reproducible learning)
                features_snapshot_json = json.dumps({
                    'v': 1,
                    'ts': features.get('computed_at').isoformat() if features.get('computed_at') else None,
                    'ticker': ticker,
                    'close': features.get('close'),
                    'sma20': features.get('sma20'),
                    'sma50': features.get('sma50'),
                    'distance_sma20': features.get('distance_sma20'),
                    'distance_sma50': features.get('distance_sma50'),
                    'trend_state': features.get('trend_state'),
                    'vol_ratio': features.get('vol_ratio'),
                    'volume_ratio': features.get('volume_ratio'),
                    'volume_surge': features.get('volume_surge')
                }, cls=DecimalEncoder)
                
                # Phase 16: Create sentiment snapshot (P0 for reproducible learning)
                sentiment_snapshot_json = None
                if sentiment:
                    sentiment_snapshot_json = json.dumps({
                        'v': 1,
                        'window_hours': config['sentiment_window_minutes'] / 60,
                        'avg_score': sentiment.get('avg_score'),
                        'news_count': sentiment.get('news_count'),
                        'direction': 'bullish' if sentiment.get('avg_score', 0) > 0 else ('bearish' if sentiment.get('avg_score', 0) < 0 else 'neutral'),
                        'positive_count': sentiment.get('positive_count'),
                        'negative_count': sentiment.get('negative_count'),
                        'neutral_count': sentiment.get('neutral_count')
                    }, cls=DecimalEncoder)
                
                rec_id = insert_recommendation(
                    conn,
                    ticker,
                    action,
                    instrument_type or 'UNKNOWN',
                    strategy_type,
                    confidence,
                    reason_json,
                    features_snapshot_json,
                    sentiment_snapshot_json
                )
                
                signals_generated += 1
                
                log_event('recommendation_created', {
                    'id': rec_id,
                    'ticker': ticker,
                    'action': action,
                    'instrument_type': instrument_type,
                    'strategy_type': strategy_type,
                    'confidence': round(confidence, 3),
                    'reason_summary': reason.get('decision', reason.get('reason', 'N/A'))
                })
            else:
                signals_hold += 1
        
        # Summary
        log_event('run_complete', {
            'watchlist_count': len(tickers),
            'signals_generated': signals_generated,
            'signals_hold': signals_hold,
            'skipped_cooldown': signals_skipped_cooldown
        })
        
        conn.close()
        
    except Exception as e:
        log_event('error', {
            'error_type': type(e).__name__,
            'error_message': str(e),
            'traceback': str(e)
        })
        sys.exit(1)

if __name__ == '__main__':
    main()
