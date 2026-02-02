#!/usr/bin/env python3
"""
Telemetry Ingestor - 1-Minute Candles
Fetches OHLCV data from yfinance and stores in database
Designed to run as scheduled ECS task (every 1 minute)
"""

import json
import time
import sys
from datetime import datetime, timezone
from typing import Dict

from config import load_config
from store import TelemetryStore

def log(event: str, **kwargs):
    """Structured JSON logging"""
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **kwargs
    }
    print(json.dumps(log_entry), flush=True)

def main():
    """
    Main entry point
    Fetches candles for all tickers and stores them
    """
    run_start = time.time()
    log("telemetry_run_start")
    
    try:
        # Load configuration
        config = load_config()
        log("config_loaded",
            tickers_count=len(config['tickers']),
            lookback_minutes=config['lookback_minutes'],
            interval=config['interval'])
        
        # Initialize database store
        store = TelemetryStore(config['db'])
        store.connect()
        log("db_connected")
        
        # Fetch candles for all tickers with pacing
        log("fetching_candles", 
            tickers=config['tickers'],
            data_source=config['data_source'])
        fetch_start = time.time()
        
        # Select data source
        if config['data_source'] == 'alpaca':
            from sources.alpaca_1m import fetch_with_pacing
            
            if config['alpaca'] is None:
                raise Exception("Alpaca credentials not configured")
            
            # Map interval format (1m -> 1Min for Alpaca)
            interval_map = {'1m': '1Min', '5m': '5Min', '1d': '1Day'}
            alpaca_interval = interval_map.get(config['interval'], '1Min')
            
            results = fetch_with_pacing(
                config['tickers'],
                config['alpaca']['key_id'],
                config['alpaca']['secret_key'],
                config['lookback_minutes'],
                alpaca_interval
            )
        else:
            # Fallback to yfinance
            from sources.yfinance_1m import fetch_with_pacing
            
            results = fetch_with_pacing(
                config['tickers'],
                config['lookback_minutes']
            )
        
        fetch_duration_ms = (time.time() - fetch_start) * 1000
        log("fetch_complete", duration_ms=round(fetch_duration_ms, 2))
        
        # Process results
        tickers_ok = 0
        tickers_failed = 0
        total_rows_upserted = 0
        
        for ticker, (candles, error) in results.items():
            if error:
                tickers_failed += 1
                log("ticker_fetch_fail",
                    ticker=ticker,
                    error=error)
                continue
            
            if not candles or len(candles) == 0:
                tickers_failed += 1
                log("ticker_fetch_fail",
                    ticker=ticker,
                    error="No candles returned")
                continue
            
            # Store candles
            try:
                upsert_start = time.time()
                rows_upserted = store.upsert_candles(candles)
                upsert_duration_ms = (time.time() - upsert_start) * 1000
                
                tickers_ok += 1
                total_rows_upserted += rows_upserted
                
                log("ticker_fetch_success",
                    ticker=ticker,
                    rows_fetched=len(candles),
                    rows_upserted=rows_upserted,
                    duration_ms=round(upsert_duration_ms, 2))
                
            except Exception as e:
                tickers_failed += 1
                log("ticker_store_fail",
                    ticker=ticker,
                    rows_fetched=len(candles),
                    error=str(e),
                    error_type=type(e).__name__)
        
        # Close connection
        store.close()
        
        # Calculate totals
        run_duration_ms = (time.time() - run_start) * 1000
        
        # Final summary
        result = {
            "success": tickers_failed == 0,
            "tickers_total": len(config['tickers']),
            "tickers_ok": tickers_ok,
            "tickers_failed": tickers_failed,
            "total_rows_upserted": total_rows_upserted,
            "duration_ms": round(run_duration_ms, 2)
        }
        
        log("telemetry_run_complete", **result)
        
        # Check for rate limit warning
        if tickers_failed >= 3:
            log("rate_limit_suspected",
                tickers_failed=tickers_failed,
                tickers_total=len(config['tickers']))
        
        # Exit with success
        sys.exit(0)
        
    except Exception as e:
        error_msg = str(e)
        log("telemetry_run_failed",
            error=error_msg,
            error_type=type(e).__name__)
        
        # Exit with failure
        sys.exit(1)

if __name__ == '__main__':
    import time
    import os
    
    # Run mode: ONCE (for testing) or LOOP (for ECS Service)
    run_mode = os.getenv('RUN_MODE', 'LOOP')
    
    if run_mode == 'ONCE':
        log("telemetry_mode", mode="ONCE")
        main()
    else:
        log("telemetry_mode", mode="LOOP")
        log("telemetry_interval", interval="60 seconds")
        
        while True:
            try:
                main()
                log("telemetry_sleep", seconds=60)
                time.sleep(60)  # 1 minute
            except KeyboardInterrupt:
                log("telemetry_shutdown", reason="keyboard_interrupt")
                break
            except Exception as e:
                log("telemetry_loop_error", error=str(e), error_type=type(e).__name__)
                time.sleep(30)  # Wait before retry
