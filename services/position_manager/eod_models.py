"""
EOD Exit Engine Data Models
Dataclasses for EOD decisions, criteria evaluation, VIX regime, earnings info,
and close-loop actions.
"""
from dataclasses import dataclass, field
from datetime import datetime, date, timezone
from typing import Dict, Any, Optional, List


@dataclass
class CriterionResult:
    """Result of evaluating a single overnight hold criterion."""
    name: str           # e.g., 'min_dte', 'min_pnl_pct', 'max_position_pct'
    observed: float     # actual value
    threshold: float    # required value (after VIX/theta adjustments)
    passed: bool
    adjusted_by: Optional[str] = None  # 'vix_elevated', 'theta_penalty', etc.

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'observed': self.observed,
            'threshold': self.threshold,
            'passed': self.passed,
            'adjusted_by': self.adjusted_by,
        }


@dataclass
class EarningsInfo:
    """Upcoming earnings announcement for a ticker."""
    ticker: str
    earnings_date: date
    timing: str  # 'after_close' or 'before_open'

    def to_dict(self) -> Dict[str, Any]:
        return {
            'ticker': self.ticker,
            'earnings_date': self.earnings_date.isoformat(),
            'timing': self.timing,
        }


@dataclass
class VIXRegime:
    """Current VIX regime classification from vix_history table."""
    vix_value: float
    regime: str  # 'complacent', 'normal', 'elevated', 'high', 'extreme'
    recorded_at: datetime

    @property
    def is_stale(self) -> bool:
        """True if data is older than 24 hours."""
        now = datetime.now(timezone.utc)
        if self.recorded_at.tzinfo is None:
            recorded = self.recorded_at.replace(tzinfo=timezone.utc)
        else:
            recorded = self.recorded_at
        return (now - recorded).total_seconds() > 86400

    @property
    def effective_regime(self) -> str:
        """Returns 'elevated' if stale, otherwise actual regime."""
        return 'elevated' if self.is_stale else self.regime


@dataclass
class OvernightCriteria:
    """Overnight hold thresholds — may be adjusted by VIX and theta."""
    min_dte: int = 3
    min_pnl_pct: float = 10.0
    max_position_pct: float = 5.0
    max_overnight_exposure: float = 5000.0

    def evaluate(self, position: Dict[str, Any], account_equity: float) -> Dict[str, CriterionResult]:
        """Evaluate position against all individual criteria. Returns dict of results."""
        results = {}

        # DTE check
        dte = position.get('dte', 0) or 0
        results['min_dte'] = CriterionResult(
            'min_dte', float(dte), float(self.min_dte), dte >= self.min_dte
        )

        # P&L check
        pnl_pct = float(position.get('current_pnl_percent', 0) or 0)
        results['min_pnl_pct'] = CriterionResult(
            'min_pnl_pct', pnl_pct, self.min_pnl_pct, pnl_pct >= self.min_pnl_pct
        )

        # Position size check
        notional = float(position.get('notional', 0) or 0)
        position_pct = (notional / account_equity * 100) if account_equity > 0 else 100.0
        results['max_position_pct'] = CriterionResult(
            'max_position_pct', position_pct, self.max_position_pct,
            position_pct <= self.max_position_pct
        )

        return results

    def all_passed(self, results: Dict[str, CriterionResult]) -> bool:
        """True if every criterion passed."""
        return all(cr.passed for cr in results.values())

    def count_failures(self, results: Dict[str, CriterionResult]) -> int:
        """Count how many criteria failed."""
        return sum(1 for cr in results.values() if not cr.passed)


@dataclass
class EODDecision:
    """Result of evaluating a single position for EOD exit."""
    position_id: int
    ticker: str
    strategy_type: str
    decision: str  # 'hold', 'close', 'skip'
    close_reason: Optional[str] = None
    pnl_pct: float = 0.0
    pnl_dollars: float = 0.0
    dte: Optional[int] = None
    theta_score: Optional[float] = None
    vix_regime: Optional[str] = None
    window_index: Optional[int] = None
    close_urgency_score: Optional[float] = None
    criteria_results: Dict[str, CriterionResult] = field(default_factory=dict)
    earnings_info: Optional[EarningsInfo] = None
    account_tier: str = 'large'

    def to_event_payload(self) -> Dict[str, Any]:
        """Serialize to JSON for position_events logging (R6)."""
        payload = {
            'position_id': self.position_id,
            'strategy_type': self.strategy_type,
            'decision': self.decision,
            'pnl_pct': self.pnl_pct,
            'pnl_dollars': self.pnl_dollars,
            'dte': self.dte,
            'theta_score': self.theta_score,
            'vix_regime': self.vix_regime,
            'window_index': self.window_index,
            'close_urgency_score': self.close_urgency_score,
            'criteria': {k: v.to_dict() for k, v in self.criteria_results.items()},
            'account_tier': self.account_tier,
        }
        if self.close_reason:
            payload['close_reason'] = self.close_reason
        if self.earnings_info:
            payload['earnings'] = self.earnings_info.to_dict()
        return payload


@dataclass
class GraduatedWindowCriteria:
    """Criteria that apply at a specific graduated close window."""
    window_time: str   # "HH:MM" format
    window_index: int  # 0-based


@dataclass
class CloseAction:
    """Action to take for a stuck or duplicate position."""
    position_id: int
    action: str  # 'retry', 'queue_for_open', 'close_duplicate', 'manual_review'
    reason: str
