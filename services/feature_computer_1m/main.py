#!/usr/bin/env python3
"""
Feature Computer - 1-Minute Technical Indicators
Computes SMA, volatility, and derived metrics from telemetry
Designed to run as scheduled ECS task (every 1 minute)
"""

import json
import time
import sys
from datetime import datetime, timezone

from config import load_config
from db import FeatureDB
from features import compute_features

def log(event: str, **kwargs):
    """Structured JSON logging"""
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **kwargs
    }
    print(json.dumps(log_entry), flush=True)

def main():
    """Main entry point - compute features for all tickers"""
    
    run_start = time.time()
    log("feature_run_start")
    
    try:
        # Load configuration
        config = load_config()
        log("config_loaded", tickers_count=len(config['tickers']))
        
        # Initialize database
        db = FeatureDB(config['db'])
        db.connect()
        log("db_connected")
        
        # Process each ticker
        tickers_computed = 0
        tickers_skipped = 0
        tickers_failed = 0
        
        for ticker in config['tickers']:
            try:
                # Get telemetry data (adaptive lookback handles min_bars internally)
                telemetry = db.get_last_telemetry(ticker, min_bars=50)
                
                if len(telemetry) < 50:
                    tickers_skipped += 1
                    log("ticker_skipped_insufficient_points",
                        ticker=ticker,
                        points=len(telemetry))
                    continue
                
                # Compute features
                features = compute_features(telemetry, ticker)
                
                if features is None:
                    tickers_skipped += 1
                    log("ticker_skipped_computation_failed", ticker=ticker)
                    continue
                
                # Upsert to database
                success = db.upsert_lane_features(features)
                
                if success:
                    tickers_computed += 1
                    log("ticker_features_computed",
                        ticker=ticker,
                        sma20=round(features['sma20'], 2),
                        sma50=round(features['sma50'], 2),
                        vol_ratio=round(features['vol_ratio'], 3) if features['vol_ratio'] else None,
                        trend_state=features['trend_state'],
                        # Phase 12: Volume features
                        volume_ratio=round(features['volume_ratio'], 4) if features.get('volume_ratio') else None,
                        volume_surge=features.get('volume_surge', False))
                else:
                    tickers_failed += 1
                    
            except Exception as e:
                tickers_failed += 1
                log("ticker_features_failed",
                    ticker=ticker,
                    error=str(e),
                    error_type=type(e).__name__)
        
        # Close database
        db.close()
        
        # Final summary
        run_duration_ms = (time.time() - run_start) * 1000
        
        result = {
            "success": tickers_failed == 0,
            "tickers_total": len(config['tickers']),
            "tickers_computed": tickers_computed,
            "tickers_skipped": tickers_skipped,
            "tickers_failed": tickers_failed,
            "duration_ms": round(run_duration_ms, 2)
        }
        
        log("feature_run_complete", **result)
        
        sys.exit(0)
        
    except Exception as e:
        log("feature_run_failed",
            error=str(e),
            error_type=type(e).__name__)
        sys.exit(1)

if __name__ == '__main__':
    main()
