"""
Property-based tests for Close-Loop Monitor.
Feature: eod-trading-strategy, Property 16: Stuck closing positions are retried then skipped
Feature: eod-trading-strategy, Property 17: One position per ticker per account invariant
Feature: eod-trading-strategy, Property 18: Market-closed positions are not executed

Validates: Requirements 14.1, 14.3, 14.4, 14.5, 14.7
"""
import pytest
from datetime import datetime, timezone, timedelta, time
from hypothesis import given, assume, settings
from hypothesis import strategies as st

from services.position_manager.close_loop import CloseLoopMonitor, MARKET_OPEN, MARKET_CLOSE
from services.position_manager.eod_config import EODConfig


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

max_closing_minutes = st.integers(min_value=1, max_value=60)
tickers = st.sampled_from(['AAPL', 'MSFT', 'TSLA', 'GOOG', 'AMZN', 'META', 'NVDA'])
accounts = st.sampled_from(['tiny_account', 'large_account'])
instrument_types = st.sampled_from(['option', 'stock'])


def make_closing_position(pos_id, minutes_ago, retry_count=0, ticker='AAPL',
                           account='tiny_account', instrument_type='option'):
    """Build a position dict in 'closing' state."""
    return {
        'id': pos_id,
        'status': 'closing',
        'ticker': ticker,
        'account_name': account,
        'instrument_type': instrument_type,
        'closing_started_at': (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat(),
        'close_retry_count': retry_count,
        'created_at': (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
    }


def make_open_position(pos_id, ticker='AAPL', account='tiny_account',
                        instrument_type='option', created_minutes_ago=60):
    return {
        'id': pos_id,
        'status': 'open',
        'ticker': ticker,
        'account_name': account,
        'instrument_type': instrument_type,
        'created_at': (datetime.now(timezone.utc) - timedelta(minutes=created_minutes_ago)).isoformat(),
    }


# ---------------------------------------------------------------------------
# Property 16: Stuck closing positions are retried then skipped
# Validates: Requirements 14.1, 14.3
# ---------------------------------------------------------------------------

class TestStuckClosingRetry:
    """Property 16: Stuck closing positions are retried then skipped."""

    @given(
        max_minutes=max_closing_minutes,
        elapsed_minutes=st.integers(min_value=1, max_value=120),
    )
    @settings(max_examples=200)
    def test_stuck_position_gets_exactly_one_retry(self, max_minutes, elapsed_minutes):
        """R14.1: Positions stuck > max_closing_duration get one retry."""
        config = EODConfig(max_closing_duration_minutes=max_minutes)
        monitor = CloseLoopMonitor(config)
        # Force market open so we always get 'retry' not 'queue_for_open'
        monitor.is_market_open = lambda **kwargs: True

        now_utc = datetime.now(timezone.utc)
        pos = make_closing_position(1, minutes_ago=elapsed_minutes, retry_count=0)
        actions = monitor.check_stuck_positions([pos], now_utc=now_utc)

        if elapsed_minutes > max_minutes:
            assert len(actions) == 1
            assert actions[0].action == 'retry'
        else:
            assert len(actions) == 0

    def test_retry_exhausted_goes_to_manual_review(self):
        """R14.2: After retry fails, mark for manual review."""
        config = EODConfig(max_closing_duration_minutes=5)
        monitor = CloseLoopMonitor(config)
        # Force market open
        monitor.is_market_open = lambda **kwargs: True

        now_utc = datetime.now(timezone.utc)
        pos = make_closing_position(1, minutes_ago=10, retry_count=1)
        actions = monitor.check_stuck_positions([pos], now_utc=now_utc)

        assert len(actions) == 1
        assert actions[0].action == 'manual_review'

    def test_non_closing_positions_ignored(self):
        """R14.3: Only closing positions are checked."""
        config = EODConfig(max_closing_duration_minutes=5)
        monitor = CloseLoopMonitor(config)

        positions = [
            {'id': 1, 'status': 'open', 'updated_at': datetime.now(timezone.utc).isoformat()},
            {'id': 2, 'status': 'closed', 'updated_at': datetime.now(timezone.utc).isoformat()},
        ]
        actions = monitor.check_stuck_positions(positions)
        assert len(actions) == 0


# ---------------------------------------------------------------------------
# Property 17: One position per ticker per account invariant
# Validates: Requirements 14.5, 14.7
# ---------------------------------------------------------------------------

class TestDuplicateDetection:
    """Property 17: One position per ticker per account invariant."""

    @given(
        ticker=tickers,
        account=accounts,
        instrument=instrument_types,
        num_duplicates=st.integers(min_value=2, max_value=6),
    )
    @settings(max_examples=100)
    def test_duplicates_detected_and_most_recent_kept(
        self, ticker, account, instrument, num_duplicates
    ):
        """R14.5/14.7: Detect duplicates, keep most recent, close rest."""
        config = EODConfig()
        monitor = CloseLoopMonitor(config)

        positions = []
        for i in range(num_duplicates):
            positions.append(make_open_position(
                pos_id=i + 1,
                ticker=ticker,
                account=account,
                instrument_type=instrument,
                created_minutes_ago=(num_duplicates - i) * 10,  # most recent last
            ))

        actions = monitor.detect_duplicates(positions)

        # Should close all but one
        assert len(actions) == num_duplicates - 1
        # All actions should be close_duplicate
        assert all(a.action == 'close_duplicate' for a in actions)
        # The most recent position (highest created_at) should NOT be in actions
        closed_ids = {a.position_id for a in actions}
        assert num_duplicates not in closed_ids  # last one is most recent

    def test_no_duplicates_no_actions(self):
        """No duplicates → no actions."""
        config = EODConfig()
        monitor = CloseLoopMonitor(config)

        positions = [
            make_open_position(1, ticker='AAPL'),
            make_open_position(2, ticker='MSFT'),
            make_open_position(3, ticker='TSLA'),
        ]
        actions = monitor.detect_duplicates(positions)
        assert len(actions) == 0

    def test_different_accounts_not_duplicates(self):
        """Same ticker, different accounts → not duplicates."""
        config = EODConfig()
        monitor = CloseLoopMonitor(config)

        positions = [
            make_open_position(1, ticker='AAPL', account='tiny_account'),
            make_open_position(2, ticker='AAPL', account='large_account'),
        ]
        actions = monitor.detect_duplicates(positions)
        assert len(actions) == 0


# ---------------------------------------------------------------------------
# Property 18: Market-closed positions are not executed
# Validates: Requirements 14.4
# ---------------------------------------------------------------------------

class TestMarketClosedQueuing:
    """Property 18: Market-closed positions are not executed."""

    @given(
        hour=st.integers(min_value=0, max_value=23),
        minute=st.integers(min_value=0, max_value=59),
    )
    @settings(max_examples=100)
    def test_market_open_detection(self, hour, minute):
        """is_market_open correctly identifies market hours."""
        config = EODConfig()
        monitor = CloseLoopMonitor(config)
        t = time(hour, minute)

        expected = MARKET_OPEN <= t < MARKET_CLOSE
        assert monitor.is_market_open(now_et=t) == expected

    def test_stuck_position_queued_when_market_closed(self):
        """R14.4: Stuck positions queued when market closed."""
        config = EODConfig(max_closing_duration_minutes=5)
        monitor = CloseLoopMonitor(config)

        pos = make_closing_position(1, minutes_ago=10, retry_count=0)

        # Override is_market_open to return False
        monitor.is_market_open = lambda **kwargs: False

        actions = monitor.check_stuck_positions([pos])
        assert len(actions) == 1
        assert actions[0].action == 'queue_for_open'
