"""
Close-Loop Monitor
Detects and recovers from stuck closing attempts.
Prevents duplicate close attempts and queues closes for market open.
"""
import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta, time
from typing import Dict, Any, List, Optional

from eod_config import EODConfig
from eod_models import CloseAction

logger = logging.getLogger(__name__)

# US market hours in ET
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)


class CloseLoopMonitor:
    """
    Monitors positions in 'closing' state and handles recovery.
    R14.1: Retry stuck positions once.
    R14.2: Log close_failed on retry failure.
    R14.3: Skip closing positions from new exit evaluations.
    R14.4: Queue closes when market is closed.
    R14.5: Enforce one position per ticker/account/instrument_type.
    R14.7: Close duplicates exceeding max_positions_per_ticker.
    """

    def __init__(self, config: EODConfig):
        self.config = config

    def is_market_open(self, now_et: Optional[datetime] = None) -> bool:
        """
        Check if market is currently open (9:30 AM - 4:00 PM ET).
        R14.4: Market-closed positions are not executed.
        """
        if now_et is None:
            try:
                import zoneinfo
                et = zoneinfo.ZoneInfo('America/New_York')
            except ImportError:
                import pytz
                et = pytz.timezone('US/Eastern')
            now_et = datetime.now(et)

        current_time = now_et.time() if isinstance(now_et, datetime) else now_et
        return MARKET_OPEN <= current_time < MARKET_CLOSE

    def check_stuck_positions(
        self,
        positions: List[Dict[str, Any]],
        now_utc: Optional[datetime] = None,
    ) -> List[CloseAction]:
        """
        Find positions stuck in 'closing' state beyond max_closing_duration_minutes.
        Returns list of recovery actions.

        R14.1: One retry for stuck positions.
        R14.2: Mark for manual review on retry failure.
        R14.4: Queue for next open if market closed.
        """
        if now_utc is None:
            now_utc = datetime.now(timezone.utc)

        max_duration = timedelta(minutes=self.config.max_closing_duration_minutes)
        actions = []

        for pos in positions:
            if pos.get('status') != 'closing':
                continue

            # Determine how long it's been closing
            closing_since = pos.get('closing_started_at') or pos.get('updated_at')
            if closing_since is None:
                continue

            if isinstance(closing_since, str):
                try:
                    closing_since = datetime.fromisoformat(closing_since)
                except ValueError:
                    continue

            if closing_since.tzinfo is None:
                closing_since = closing_since.replace(tzinfo=timezone.utc)

            elapsed = now_utc - closing_since
            if elapsed <= max_duration:
                continue

            # Position is stuck
            pos_id = pos.get('id', 0)
            retry_count = pos.get('close_retry_count', 0) or 0

            if not self.is_market_open():
                actions.append(CloseAction(
                    position_id=pos_id,
                    action='queue_for_open',
                    reason=f'Market closed, queuing stuck position (closing for {elapsed})',
                ))
            elif retry_count < 1:
                actions.append(CloseAction(
                    position_id=pos_id,
                    action='retry',
                    reason=f'Stuck closing for {elapsed}, retrying (attempt {retry_count + 1})',
                ))
            else:
                actions.append(CloseAction(
                    position_id=pos_id,
                    action='manual_review',
                    reason=f'Stuck closing for {elapsed}, retry exhausted, needs manual review',
                ))

        return actions

    def detect_duplicates(
        self,
        positions: List[Dict[str, Any]],
    ) -> List[CloseAction]:
        """
        Find duplicate positions (same ticker, account, instrument_type).
        Returns CloseActions for all but the most recent position per group.

        R14.5: Max one open/closing position per ticker/account/instrument_type.
        R14.7: Close all but most recent when exceeding max_positions_per_ticker.
        """
        groups: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)

        for pos in positions:
            if pos.get('status') not in ('open', 'closing'):
                continue
            key = (
                pos.get('ticker', ''),
                pos.get('account_name', ''),
                pos.get('instrument_type', ''),
            )
            groups[key].append(pos)

        actions = []
        for key, group in groups.items():
            if len(group) <= 1:
                continue

            # Sort by created_at descending — keep most recent
            group.sort(
                key=lambda p: p.get('created_at', '') or '',
                reverse=True,
            )

            # Close all but the first (most recent)
            for dup in group[1:]:
                actions.append(CloseAction(
                    position_id=dup.get('id', 0),
                    action='close_duplicate',
                    reason=f'Duplicate position for {key[0]} in {key[1]} ({key[2]}), '
                           f'keeping most recent, closing {len(group) - 1} duplicates',
                ))

        return actions
