"""
Earnings Calendar Client
Checks upcoming earnings announcements via Alpaca corporate actions API.
Caches results per trading day to minimize API calls.
"""
import logging
import requests
from datetime import date, datetime, timedelta
from typing import Dict, Optional

from eod_models import EarningsInfo

logger = logging.getLogger(__name__)


class EarningsCalendarClient:
    """
    Checks upcoming earnings announcements for tickers.
    R12.5: Caches results per trading day.
    R12.6: Graceful degradation on API failure.
    """

    ALPACA_DATA_URL = "https://data.alpaca.markets"

    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self._cache: Dict[str, Optional[EarningsInfo]] = {}
        self._cache_date: Optional[date] = None
        self._session = requests.Session()
        self._session.headers.update({
            'APCA-API-KEY-ID': api_key,
            'APCA-API-SECRET-KEY': api_secret,
        })

    def has_upcoming_earnings(self, ticker: str, today: Optional[date] = None) -> Optional[EarningsInfo]:
        """
        Check if ticker has earnings within 1 trading day.
        R12.1: Check for earnings after today's close or before next day's open.
        R12.2-12.3: Returns EarningsInfo if found, None otherwise.
        """
        if today is None:
            today = date.today()

        # Invalidate cache if day changed
        if self._cache_date != today:
            self.invalidate_cache()
            self._cache_date = today

        if ticker in self._cache:
            return self._cache[ticker]

        result = self._fetch_earnings(ticker, today)
        self._cache[ticker] = result
        return result

    def _fetch_earnings(self, ticker: str, today: date) -> Optional[EarningsInfo]:
        """
        Query Alpaca corporate actions API for earnings.
        Looks for earnings today after close or tomorrow before open.
        R12.6: Returns None on any API failure.
        """
        try:
            # Check today and next trading day
            tomorrow = today + timedelta(days=1)
            # Skip weekends for "next trading day"
            while tomorrow.weekday() >= 5:  # Saturday=5, Sunday=6
                tomorrow += timedelta(days=1)

            url = f"{self.ALPACA_DATA_URL}/v1/corporate-actions"
            params = {
                'symbols': ticker,
                'types': 'Earnings',
                'date_from': today.isoformat(),
                'date_to': tomorrow.isoformat(),
            }
            resp = self._session.get(url, params=params, timeout=10)

            if resp.status_code != 200:
                logger.warning(
                    f"Earnings API returned {resp.status_code} for {ticker}"
                )
                return None

            data = resp.json()
            earnings_list = data.get('earnings', [])

            for entry in earnings_list:
                earnings_date_str = entry.get('date') or entry.get('ex_date')
                if not earnings_date_str:
                    continue

                earnings_date = date.fromisoformat(earnings_date_str)
                timing_raw = (entry.get('timing') or '').lower()

                # Determine timing
                if earnings_date == today:
                    timing = 'after_close'
                elif earnings_date == tomorrow:
                    timing = 'before_open'
                else:
                    continue

                # Override with explicit timing if available
                if 'bmo' in timing_raw or 'before' in timing_raw:
                    timing = 'before_open'
                elif 'amc' in timing_raw or 'after' in timing_raw:
                    timing = 'after_close'

                return EarningsInfo(
                    ticker=ticker,
                    earnings_date=earnings_date,
                    timing=timing,
                )

            return None

        except Exception as e:
            logger.warning(f"Earnings calendar check failed for {ticker}: {e}")
            return None

    def invalidate_cache(self):
        """Clear cache (called at start of each trading day)."""
        self._cache.clear()
        self._cache_date = None
