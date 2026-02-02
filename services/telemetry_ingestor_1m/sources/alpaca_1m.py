"""
Alpaca Market Data API fetcher
Free tier with paper trading account - much more reliable than yfinance
"""

import requests
import time
import random
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple

# Alpaca API base URLs
ALPACA_DATA_BASE_URL = "https://data.alpaca.markets/v2"

def fetch_alpaca_bars(
    ticker: str,
    api_key: str,
    secret_key: str,
    lookback_minutes: int = 120,
    interval: str = "1Min",
    max_retries: int = 3
) -> Optional[List[Dict]]:
    """
    Fetch bars from Alpaca Market Data API
    
    Args:
        ticker: Stock symbol (e.g., 'AAPL')
        api_key: Alpaca API key ID
        secret_key: Alpaca secret key
        lookback_minutes: How many minutes of history
        interval: Bar interval ('1Min', '5Min', '15Min', '1Hour', '1Day')
        max_retries: Maximum retry attempts
        
    Returns:
        List of candle dictionaries or None if failed
    """
    
    # Calculate time range
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=lookback_minutes)
    
    # Format timestamps for Alpaca (RFC3339)
    start_str = start_time.strftime('%Y-%m-%dT%H:%M:%SZ')
    end_str = end_time.strftime('%Y-%m-%dT%H:%M:%SZ')
    
    # Alpaca API endpoint
    url = f"{ALPACA_DATA_BASE_URL}/stocks/{ticker}/bars"
    
    # Headers for authentication
    headers = {
        'APCA-API-KEY-ID': api_key,
        'APCA-API-SECRET-KEY': secret_key
    }
    
    # Query parameters
    params = {
        'timeframe': interval,
        'start': start_str,
        'end': end_str,
        'limit': 10000,  # Max bars to return
        'adjustment': 'raw',  # Raw prices (no splits/dividends)
        'feed': 'iex'  # Use IEX feed (free tier) instead of SIP
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=10
            )
            
            # Check for errors
            if response.status_code != 200:
                error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                print(f"Alpaca API error for {ticker}: {error_msg}")
                
                if attempt < max_retries - 1:
                    # Exponential backoff with jitter
                    sleep_time = (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(sleep_time)
                    continue
                return None
            
            data = response.json()
            
            # Check if we got bars
            if 'bars' not in data or len(data['bars']) == 0:
                if attempt < max_retries - 1:
                    sleep_time = (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(sleep_time)
                    continue
                return None
            
            # Convert to our standard format
            candles = []
            for bar in data['bars']:
                # Parse timestamp (Alpaca returns RFC3339)
                ts = datetime.fromisoformat(bar['t'].replace('Z', '+00:00'))
                
                candle = {
                    'ticker': ticker,
                    'ts': ts,
                    'open': float(bar['o']),
                    'high': float(bar['h']),
                    'low': float(bar['l']),
                    'close': float(bar['c']),
                    'volume': int(bar['v']) if bar.get('v') else None
                }
                
                candles.append(candle)
            
            return candles
            
        except Exception as e:
            print(f"Alpaca fetch exception for {ticker} (attempt {attempt+1}): {str(e)}")
            if attempt < max_retries - 1:
                sleep_time = (2 ** attempt) + random.uniform(0, 1)
                time.sleep(sleep_time)
                continue
            return None
    
    return None

def fetch_with_pacing(
    tickers: List[str],
    api_key: str,
    secret_key: str,
    lookback_minutes: int = 120,
    interval: str = "1Min"
) -> Dict[str, Tuple[Optional[List[Dict]], Optional[str]]]:
    """
    Fetch bars for multiple tickers with pacing
    
    Args:
        tickers: List of ticker symbols
        api_key: Alpaca API key ID
        secret_key: Alpaca secret key
        lookback_minutes: Minutes of history
        interval: Bar interval
        
    Returns:
        Dictionary mapping ticker to (candles, error)
    """
    results = {}
    
    for i, ticker in enumerate(tickers):
        # Add pacing between requests (0.2-0.6 seconds)
        if i > 0:
            time.sleep(random.uniform(0.2, 0.6))
        
        try:
            candles = fetch_alpaca_bars(
                ticker,
                api_key,
                secret_key,
                lookback_minutes,
                interval
            )
            
            if candles is None:
                results[ticker] = (None, "No data returned or all retries failed")
            else:
                results[ticker] = (candles, None)
                
        except Exception as e:
            results[ticker] = (None, str(e))
    
    return results
