"""
Options Bar Fetcher for Position Manager
Fetches historical option bars from Alpaca during position monitoring
"""

import requests
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class OptionBarFetcher:
    """
    Fetches option bars from Alpaca for position tracking and AI learning.
    Integrates with position_manager to capture bars during monitoring.
    """
    
    def __init__(self, api_key: str, api_secret: str):
        """
        Initialize bar fetcher with Alpaca credentials.
        
        Args:
            api_key: Alpaca API key
            api_secret: Alpaca API secret
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = "https://data.alpaca.markets"
        
        self.headers = {
            'APCA-API-KEY-ID': api_key,
            'APCA-API-SECRET-KEY': api_secret
        }
    
    def fetch_bars_for_symbol(
        self,
        symbol: str,
        minutes_back: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Fetch recent 1-minute bars for an option symbol.
        
        Args:
            symbol: Option symbol (e.g., SPY260130C00609000)
            minutes_back: How many minutes of history to fetch (default 5)
        
        Returns:
            List of bar dicts with timestamp, OHLCV data
            Empty list if no bars available or error occurs
        """
        url = f"{self.base_url}/v1beta1/options/bars"
        
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=minutes_back)
        
        params = {
            'symbols': symbol,
            'start': start_time.isoformat(),
            'end': end_time.isoformat(),
            'timeframe': '1Min',
            'limit': minutes_back + 2  # Small buffer
        }
        
        try:
            response = requests.get(
                url,
                headers=self.headers,
                params=params,
                timeout=10
            )
            
            # 404 is normal - no bars available for this contract yet
            if response.status_code == 404:
                logger.debug(f"No bars available for {symbol}")
                return []
            
            response.raise_for_status()
            data = response.json()
            
            # Parse response format: {'bars': {'SYMBOL': [{...}]}}
            bars_data = data.get('bars', {}).get(symbol, [])
            
            bars = []
            for bar in bars_data:
                bars.append({
                    'symbol': symbol,
                    'timestamp': bar['t'],
                    'open': float(bar['o']),
                    'high': float(bar['h']),
                    'low': float(bar['l']),
                    'close': float(bar['c']),
                    'volume': int(bar.get('v', 0)),
                    'trade_count': int(bar.get('n', 0)),
                    'vwap': float(bar.get('vw', 0)) if 'vw' in bar else None
                })
            
            if bars:
                logger.info(f"Fetched {len(bars)} bars for {symbol}")
            
            return bars
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"Error fetching bars for {symbol}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching bars for {symbol}: {e}")
            return []
    
    def fetch_bars_batch(
        self,
        symbols: List[str],
        minutes_back: int = 5
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetch bars for multiple symbols in one API call.
        
        Args:
            symbols: List of option symbols (max 100 per API limit)
            minutes_back: How many minutes of history
        
        Returns:
            Dict mapping symbol -> list of bars
        """
        if not symbols:
            return {}
        
        # Limit to 100 symbols per Alpaca API constraint
        symbols = symbols[:100]
        
        url = f"{self.base_url}/v1beta1/options/bars"
        
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=minutes_back)
        
        params = {
            'symbols': ','.join(symbols),
            'start': start_time.isoformat(),
            'end': end_time.isoformat(),
            'timeframe': '1Min',
            'limit': 1000  # Total limit across all symbols
        }
        
        try:
            response = requests.get(
                url,
                headers=self.headers,
                params=params,
                timeout=15
            )
            
            if response.status_code == 404:
                return {}
            
            response.raise_for_status()
            data = response.json()
            
            # Parse response
            bars_by_symbol = data.get('bars', {})
            
            result = {}
            for symbol, bars_data in bars_by_symbol.items():
                bars = []
                for bar in bars_data:
                    bars.append({
                        'symbol': symbol,
                        'timestamp': bar['t'],
                        'open': float(bar['o']),
                        'high': float(bar['h']),
                        'low': float(bar['l']),
                        'close': float(bar['c']),
                        'volume': int(bar.get('v', 0)),
                        'trade_count': int(bar.get('n', 0)),
                        'vwap': float(bar.get('vw', 0)) if 'vw' in bar else None
                    })
                result[symbol] = bars
            
            logger.info(f"Fetched bars for {len(result)}/{len(symbols)} symbols")
            return result
            
        except Exception as e:
            logger.error(f"Error fetching batch bars: {e}")
            return {}
