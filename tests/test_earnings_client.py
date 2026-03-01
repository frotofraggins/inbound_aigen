"""
Unit tests for EarningsCalendarClient.
Validates: Requirements 12.1, 12.2, 12.3, 12.5, 12.6

Tests:
- After-close earnings detection
- Before-open earnings detection
- Cache behavior (same-day hit, next-day invalidation)
- API failure graceful degradation
"""
import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from services.position_manager.earnings_client import EarningsCalendarClient
from services.position_manager.eod_models import EarningsInfo


@pytest.fixture
def client():
    return EarningsCalendarClient(api_key='test-key', api_secret='test-secret')


def _mock_response(status_code, json_data):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    return resp


class TestAfterCloseEarnings:
    """R12.2: Earnings after today's close → force close."""

    def test_detects_after_close_earnings_today(self, client):
        today = date(2026, 2, 11)  # Wednesday
        earnings_data = {
            'earnings': [{
                'date': '2026-02-11',
                'timing': 'amc',
            }]
        }
        client._session.get = MagicMock(return_value=_mock_response(200, earnings_data))

        result = client.has_upcoming_earnings('AAPL', today=today)

        assert result is not None
        assert result.ticker == 'AAPL'
        assert result.earnings_date == today
        assert result.timing == 'after_close'


class TestBeforeOpenEarnings:
    """R12.3: Earnings before next day's open → force close."""

    def test_detects_before_open_earnings_tomorrow(self, client):
        today = date(2026, 2, 11)
        tomorrow = date(2026, 2, 12)
        earnings_data = {
            'earnings': [{
                'date': '2026-02-12',
                'timing': 'bmo',
            }]
        }
        client._session.get = MagicMock(return_value=_mock_response(200, earnings_data))

        result = client.has_upcoming_earnings('MSFT', today=today)

        assert result is not None
        assert result.ticker == 'MSFT'
        assert result.earnings_date == tomorrow
        assert result.timing == 'before_open'

    def test_skips_weekend_for_next_trading_day(self, client):
        """Friday → next trading day is Monday."""
        friday = date(2026, 2, 13)  # Friday
        monday = date(2026, 2, 16)  # Monday
        earnings_data = {
            'earnings': [{
                'date': '2026-02-16',
                'timing': 'bmo',
            }]
        }
        client._session.get = MagicMock(return_value=_mock_response(200, earnings_data))

        result = client.has_upcoming_earnings('TSLA', today=friday)

        assert result is not None
        assert result.earnings_date == monday
        assert result.timing == 'before_open'


class TestNoEarnings:
    """No earnings within window → returns None."""

    def test_no_earnings_returns_none(self, client):
        earnings_data = {'earnings': []}
        client._session.get = MagicMock(return_value=_mock_response(200, earnings_data))

        result = client.has_upcoming_earnings('GOOG', today=date(2026, 2, 11))
        assert result is None


class TestCacheBehavior:
    """R12.5: Per-trading-day cache."""

    def test_same_day_cache_hit(self, client):
        today = date(2026, 2, 11)
        earnings_data = {
            'earnings': [{
                'date': '2026-02-11',
                'timing': 'amc',
            }]
        }
        client._session.get = MagicMock(return_value=_mock_response(200, earnings_data))

        # First call fetches
        result1 = client.has_upcoming_earnings('AAPL', today=today)
        assert result1 is not None
        assert client._session.get.call_count == 1

        # Second call uses cache
        result2 = client.has_upcoming_earnings('AAPL', today=today)
        assert result2 is not None
        assert client._session.get.call_count == 1  # no additional call

    def test_next_day_invalidates_cache(self, client):
        today = date(2026, 2, 11)
        tomorrow = date(2026, 2, 12)
        earnings_data = {'earnings': []}
        client._session.get = MagicMock(return_value=_mock_response(200, earnings_data))

        # Day 1
        client.has_upcoming_earnings('AAPL', today=today)
        assert client._cache_date == today

        # Day 2 — cache should be invalidated
        client.has_upcoming_earnings('AAPL', today=tomorrow)
        assert client._cache_date == tomorrow
        assert client._session.get.call_count == 2  # fetched again

    def test_invalidate_cache_clears_all(self, client):
        client._cache = {'AAPL': None, 'MSFT': None}
        client._cache_date = date(2026, 2, 11)

        client.invalidate_cache()

        assert client._cache == {}
        assert client._cache_date is None


class TestAPIFailureGracefulDegradation:
    """R12.6: API failure → log warning, return None."""

    def test_non_200_returns_none(self, client):
        client._session.get = MagicMock(return_value=_mock_response(500, {}))

        result = client.has_upcoming_earnings('AAPL', today=date(2026, 2, 11))
        assert result is None

    def test_network_error_returns_none(self, client):
        client._session.get = MagicMock(side_effect=Exception("Connection timeout"))

        result = client.has_upcoming_earnings('AAPL', today=date(2026, 2, 11))
        assert result is None

    def test_malformed_json_returns_none(self, client):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.side_effect = ValueError("Invalid JSON")
        client._session.get = MagicMock(return_value=resp)

        result = client.has_upcoming_earnings('AAPL', today=date(2026, 2, 11))
        assert result is None
