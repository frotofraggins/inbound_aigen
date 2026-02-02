"""
Yahoo Finance 1-minute candle fetcher
Implements retries, backoff, and rate limit protection
"""

import yfinance as yf
import time
import random
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple

def fetch_1m_candles(
    ticker: str,
    lookback_minutes: int = 120,
    max_retries: int = 3
) -> Optional[List[Dict]]:
    """
    Fetch 1-minute OHLCV candles for a ticker with retries
    
    Args:
        ticker: Stock symbol (e.g., 'AAPL')
        lookback_minutes: How many minutes of history to fetch
        max_retries: Maximum retry attempts
        
    Returns:
        List of candle dictionaries or None if failed
    """
    
    for attempt in range(max_retries):
        try:
            # Create ticker object
            stock = yf.Ticker(ticker)
            
            # Fetch data for last N minutes
            # yfinance accepts period like '1d', '7d' or start/end dates
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(minutes=lookback_minutes)
            
            # Download 1-minute data
            df = stock.history(
                start=start_time,
                end=end_time,
                interval='1m',
                actions=False  # Don't include dividends/splits
            )
            
            # Check if we got data
            if df is None or len(df) == 0:
                if attempt < max_retries - 1:
                    # Exponential backoff with jitter
                    sleep_time = (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(sleep_time)
                    continue
                return None
            
            # Convert DataFrame to list of dictionaries
            candles = []
            for index, row in df.iterrows():
                # Normalize timestamp to UTC
                ts = index.to_pydatetime()
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                else:
                    ts = ts.astimezone(timezone.utc)
                
                # Validate numeric fields
                if not all([
                    isinstance(row['Open'], (int, float)),
                    isinstance(row['High'], (int, float)),
                    isinstance(row['Low'], (int, float)),
                    isinstance(row['Close'], (int, float))
                ]):
                    continue  # Skip invalid rows
                
                candle = {
                    'ticker': ticker,
                    'ts': ts,
                    'open': float(row['Open']),
                    'high': float(row['High']),
                    'low': float(row['Low']),
                    'close': float(row['Close']),
                    'volume': int(row['Volume']) if 'Volume' in row and row['Volume'] is not None else None
                }
                
                candles.append(candle)
            
            return candles
            
        except Exception as e:
            if attempt < max_retries - 1:
                # Exponential backoff with jitter
                sleep_time = (2 ** attempt) + random.uniform(0, 1)
                time.sleep(sleep_time)
                continue
            
            # Final retry failed
            return None
    
    return None

def fetch_with_pacing(
    tickers: List[str],
    lookback_minutes: int = 120
) -> Dict[str, Tuple[Optional[List[Dict]], Optional[str]]]:
    """
    Fetch candles for multiple tickers with pacing between requests
    
    Args:
        tickers: List of ticker symbols
        lookback_minutes: Minutes of history to fetch
        
    Returns:
        Dictionary mapping ticker to (candles, error)
    """
    results = {}
    
    for i, ticker in enumerate(tickers):
        # Add pacing between requests (0.2-0.6 seconds)
        if i > 0:
            time.sleep(random.uniform(0.2, 0.6))
        
        try:
            candles = fetch_1m_candles(ticker, lookback_minutes)
            
            if candles is None:
                results[ticker] = (None, "No data returned or all retries failed")
            else:
                results[ticker] = (candles, None)
                
        except Exception as e:
            results[ticker] = (None, str(e))
    
    return results
