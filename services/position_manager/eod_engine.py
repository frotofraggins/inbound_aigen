"""
EOD Exit Engine
Central orchestrator for all end-of-day exit decisions.
Replaces the blanket market_close_protection with strategy-aware,
P&L-aware, graduated close windows.
"""
import logging
from copy import deepcopy
from datetime import datetime, date, time, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple

from eod_config import EODConfig
from eod_models import (
    EODDecision, CriterionResult, VIXRegime, OvernightCriteria,
    EarningsInfo, GraduatedWindowCriteria, CloseAction,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Theta Scoring (R10)
# ---------------------------------------------------------------------------

def compute_theta_score(position: Dict[str, Any]) -> float:
    """
    Compute theta score = abs(theta) / current_premium.
    Falls back to 1.0 (max risk) if theta or premium is null/zero.

    R10.1: abs(theta) / premium
    R10.5: null theta → max risk (1.0)
    """
    theta = position.get('theta')
    premium = position.get('current_price') or position.get('entry_price')

    if theta is None or premium is None:
        return 1.0

    try:
        theta_val = abs(float(theta))
        premium_val = float(premium)
    except (ValueError, TypeError):
        return 1.0

    if premium_val <= 0:
        return 1.0

    return theta_val / premium_val


def apply_theta_adjustments(
    criteria: OvernightCriteria,
    theta_score: float,
    config: EODConfig,
) -> Tuple[OvernightCriteria, Optional[str]]:
    """
    Adjust overnight hold criteria based on theta score.

    R10.2: When theta_score > high_theta_threshold, lower min_pnl_pct by theta_pnl_penalty_pct.
    Returns (adjusted_criteria, adjustment_label_or_None).
    """
    if theta_score <= config.high_theta_threshold:
        return criteria, None

    adjusted = deepcopy(criteria)
    adjusted.min_pnl_pct = max(0.0, criteria.min_pnl_pct - config.theta_pnl_penalty_pct)
    return adjusted, 'theta_penalty'


def should_force_close_theta(
    position: Dict[str, Any],
    theta_score: float,
    config: EODConfig,
) -> bool:
    """
    R10.3: Force-close if DTE <= 2 AND theta_score > high_theta_threshold.
    """
    dte = position.get('dte', 0) or 0
    return dte <= 2 and theta_score > config.high_theta_threshold


# ---------------------------------------------------------------------------
# VIX Regime Adjustment (R11)
# ---------------------------------------------------------------------------

def get_vix_regime(db_conn) -> VIXRegime:
    """
    Query latest VIX regime from vix_history table.
    R11.7: Fallback to 'elevated' if stale (>24h) or unavailable.
    """
    try:
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT vix_value, regime, recorded_at
                FROM vix_history
                ORDER BY recorded_at DESC
                LIMIT 1
            """)
            row = cur.fetchone()
            if row:
                return VIXRegime(
                    vix_value=float(row[0]),
                    regime=row[1],
                    recorded_at=row[2],
                )
    except Exception as e:
        logger.warning(f"Failed to query VIX regime: {e}")

    # Fallback: elevated regime
    return VIXRegime(
        vix_value=25.0,
        regime='elevated',
        recorded_at=datetime.now(timezone.utc) - timedelta(hours=25),  # stale
    )


def apply_vix_adjustments(
    criteria: OvernightCriteria,
    vix_regime: VIXRegime,
    config: EODConfig,
) -> Tuple[OvernightCriteria, Optional[str]]:
    """
    Adjust overnight hold thresholds based on VIX regime.

    R11.2: elevated → P&L × vix_elevated_multiplier
    R11.3: high → P&L × vix_high_multiplier AND exposure ÷ 2
    R11.5: complacent/normal → no adjustment
    R11.7: stale → apply elevated multipliers
    """
    regime = vix_regime.effective_regime  # handles stale fallback

    if regime in ('complacent', 'normal'):
        return criteria, None

    adjusted = deepcopy(criteria)

    if regime == 'elevated':
        adjusted.min_pnl_pct = criteria.min_pnl_pct * config.vix_elevated_multiplier
        return adjusted, 'vix_elevated'

    if regime == 'high':
        adjusted.min_pnl_pct = criteria.min_pnl_pct * config.vix_high_multiplier
        adjusted.max_overnight_exposure = criteria.max_overnight_exposure * 0.5
        return adjusted, 'vix_high'

    # 'extreme' is handled separately (force-close all) — not an adjustment
    return criteria, None


def is_vix_extreme(vix_regime: VIXRegime) -> bool:
    """R11.4: VIX extreme → force-close all positions."""
    return vix_regime.effective_regime == 'extreme'

# ---------------------------------------------------------------------------
# Graduated Close Windows (R13)
# ---------------------------------------------------------------------------

def parse_window_times(config: EODConfig) -> List[time]:
    """Parse graduated_close_windows strings into time objects."""
    times = []
    for w in config.graduated_close_windows:
        try:
            h, m = int(w[:2]), int(w[3:])
            times.append(time(h, m))
        except (ValueError, IndexError):
            logger.warning(f"Invalid window time '{w}', skipping")
    if not times:
        # Fallback to defaults
        times = [time(14, 30), time(15, 0), time(15, 30), time(15, 55)]
    return times


def get_current_window(current_time_et: time, config: EODConfig) -> Optional[int]:
    """
    Determine which graduated window index applies based on current ET time.
    Returns the highest window index whose time has been reached, or None
    if no window has been reached yet.

    R13.1: Evaluate at configurable windows (default 14:30, 15:00, 15:30, 15:55).
    """
    windows = parse_window_times(config)
    active_window = None
    for i, wt in enumerate(windows):
        if current_time_et >= wt:
            active_window = i
    return active_window


def evaluate_day_trade_at_window(
    position: Dict[str, Any],
    window_index: int,
    total_windows: int,
    config: EODConfig,
) -> Optional[str]:
    """
    Apply window-specific criteria for day trades.
    Returns close reason string, or None if position stays open.

    R13.2: Window 0 — close if loss > window_1_max_loss_pct
    R13.3: Window 1 — close if loss > window_2_max_loss_pct
    R13.4: Window 2 — close all losing day trades
    R13.5: Window 3 (final) — close all remaining day trades
    """
    pnl_pct = float(position.get('current_pnl_percent', 0) or 0)
    final_window = total_windows - 1

    if window_index >= final_window:
        return f'graduated_window_{window_index}_final'

    if window_index == 0:
        if pnl_pct < config.window_1_max_loss_pct:
            return f'graduated_window_0_loss_{pnl_pct:.1f}pct'
        return None

    if window_index == 1:
        if pnl_pct < config.window_2_max_loss_pct:
            return f'graduated_window_1_loss_{pnl_pct:.1f}pct'
        return None

    if window_index == 2:
        if pnl_pct < 0:
            return f'graduated_window_2_any_loss_{pnl_pct:.1f}pct'
        return None

    # For any window beyond the defined ones, close
    return f'graduated_window_{window_index}'


def evaluate_swing_trade_at_window(
    position: Dict[str, Any],
    window_index: int,
    total_windows: int,
    overnight_results: Dict[str, CriterionResult],
    config: EODConfig,
) -> Optional[str]:
    """
    Apply window-specific criteria for swing trades.
    Returns close reason string, or None if position stays open.

    R13.3: Window 1 — close swing trades failing >1 criterion
    R13.4: Window 2 — close swing trades failing any criterion
    R13.5: Window 3 (final) — close all swings not meeting ALL criteria
    """
    final_window = total_windows - 1
    failures = sum(1 for cr in overnight_results.values() if not cr.passed)

    if window_index >= final_window:
        if failures > 0:
            return f'graduated_window_{window_index}_final_failed_{failures}_criteria'
        return None  # passes all criteria → hold

    if window_index == 0:
        # Window 0: no swing trade action
        return None

    if window_index == 1:
        if failures > 1:
            return f'graduated_window_1_swing_failed_{failures}_criteria'
        return None

    if window_index == 2:
        if failures > 0:
            return f'graduated_window_2_swing_failed_{failures}_criteria'
        return None

    return None


# ---------------------------------------------------------------------------
# Close Urgency Scoring (R13.8)
# ---------------------------------------------------------------------------

def compute_close_urgency(
    position: Dict[str, Any],
    theta_score: float,
    minutes_to_close: float,
    config: EODConfig,
) -> float:
    """
    Composite urgency score for prioritizing which positions close first.
    Higher score = more urgent to close.

    Components (all normalized to roughly 0-1 range, then summed):
    - P&L component: worse P&L → higher urgency (inverted)
    - DTE component: lower DTE → higher urgency (inverted)
    - Theta component: higher theta → higher urgency
    - Time component: less time to close → higher urgency (inverted)

    R13.8: Used to prioritize closes when multiple positions trigger at same window.
    """
    pnl_pct = float(position.get('current_pnl_percent', 0) or 0)
    dte = float(position.get('dte', 0) or 0)

    # P&L: map from [-100, +100] to [1, 0] — losses get high urgency
    pnl_component = max(0.0, min(1.0, (50.0 - pnl_pct) / 100.0))

    # DTE: 0 DTE → 1.0, 30+ DTE → 0.0
    dte_component = max(0.0, min(1.0, (30.0 - dte) / 30.0))

    # Theta: already 0-1 range (capped)
    theta_component = min(1.0, theta_score)

    # Time: 0 minutes left → 1.0, 60+ minutes → 0.0
    time_component = max(0.0, min(1.0, (60.0 - minutes_to_close) / 60.0))

    return pnl_component + dte_component + theta_component + time_component


# ---------------------------------------------------------------------------
# EOD Exit Engine — Core Orchestrator (R1, R2, R3, R5)
# ---------------------------------------------------------------------------

class EODExitEngine:
    """
    Evaluates end-of-day exit decisions for all open positions.
    Implements graduated close windows, theta scoring, VIX adjustment,
    earnings calendar checks, and overnight hold criteria.
    """

    def __init__(self, config: EODConfig, account_tier: str = 'large',
                 earnings_client=None, vix_regime: Optional[VIXRegime] = None):
        self.config = config
        self.account_tier = account_tier
        self.earnings_client = earnings_client
        self.vix_regime = vix_regime or VIXRegime(
            vix_value=20.0, regime='normal',
            recorded_at=datetime.now(timezone.utc),
        )
        self._window_times = parse_window_times(config)

    def evaluate_position(self, position: Dict[str, Any],
                          current_window: int,
                          account_equity: float = 100000.0) -> EODDecision:
        """
        Evaluate a single position at the current graduated window.
        Returns an EODDecision (hold, close, or skip).

        Decision flow:
        1. Skip if status=closing (R14.3)
        2. Check earnings → force close (R12)
        3. Check VIX extreme → force close all (R11.4)
        4. Compute theta score (R10)
        5. Route by strategy_type (R1)
        6. For swing: apply VIX/theta adjustments, evaluate overnight criteria
        """
        pos_id = position.get('id', 0)
        ticker = position.get('ticker', '')
        strategy = (position.get('strategy_type') or '').lower()
        pnl_pct = float(position.get('current_pnl_percent', 0) or 0)
        pnl_dollars = float(position.get('current_pnl_dollars', 0) or 0)
        dte = position.get('dte')
        total_windows = len(self._window_times)

        base_decision = EODDecision(
            position_id=pos_id, ticker=ticker, strategy_type=strategy or 'unknown',
            decision='hold', pnl_pct=pnl_pct, pnl_dollars=pnl_dollars,
            dte=dte, window_index=current_window, account_tier=self.account_tier,
            vix_regime=self.vix_regime.effective_regime,
        )

        # 1. Skip if already closing (R14.3)
        if position.get('status') == 'closing':
            base_decision.decision = 'skip'
            base_decision.close_reason = 'already_closing'
            return base_decision

        # 2. Check earnings (R12)
        earnings_info = self._check_earnings(ticker)
        if earnings_info:
            base_decision.decision = 'close'
            base_decision.close_reason = 'earnings_close'
            base_decision.earnings_info = earnings_info
            return base_decision

        # 3. VIX extreme → force close all (R11.4)
        if is_vix_extreme(self.vix_regime):
            base_decision.decision = 'close'
            base_decision.close_reason = 'vix_extreme'
            return base_decision

        # 4. Compute theta score (R10)
        theta_score = compute_theta_score(position)
        base_decision.theta_score = theta_score

        # Check theta force-close (R10.3)
        if should_force_close_theta(position, theta_score, self.config):
            base_decision.decision = 'close'
            base_decision.close_reason = 'theta_force_close'
            return base_decision

        # 5. Route by strategy_type (R1)
        if strategy == 'swing_trade':
            return self._evaluate_swing(position, base_decision, current_window,
                                         total_windows, theta_score, account_equity)
        else:
            # day_trade, unknown, or missing → treat as day trade (R1.5)
            return self._evaluate_day_trade(position, base_decision, current_window,
                                             total_windows, theta_score)

    def _check_earnings(self, ticker: str) -> Optional[EarningsInfo]:
        """Check earnings calendar if client available."""
        if self.earnings_client is None:
            return None
        try:
            return self.earnings_client.has_upcoming_earnings(ticker)
        except Exception as e:
            logger.warning(f"Earnings check failed for {ticker}: {e}")
            return None

    def _evaluate_day_trade(self, position: Dict[str, Any],
                             decision: EODDecision, current_window: int,
                             total_windows: int, theta_score: float) -> EODDecision:
        """Evaluate day trade at graduated window."""
        close_reason = evaluate_day_trade_at_window(
            position, current_window, total_windows, self.config
        )
        if close_reason:
            decision.decision = 'close'
            decision.close_reason = close_reason
            decision.close_urgency_score = compute_close_urgency(
                position, theta_score, self._minutes_to_final_window(), self.config
            )
        return decision

    def _evaluate_swing(self, position: Dict[str, Any],
                         decision: EODDecision, current_window: int,
                         total_windows: int, theta_score: float,
                         account_equity: float) -> EODDecision:
        """Evaluate swing trade: VIX/theta adjustments + overnight criteria."""
        # Build base overnight criteria from config
        criteria = OvernightCriteria(
            min_dte=self.config.min_dte_for_overnight,
            min_pnl_pct=self.config.min_pnl_pct_for_overnight,
            max_position_pct=self.config.max_position_pct_for_overnight,
            max_overnight_exposure=self.config.max_overnight_option_exposure,
        )

        # Apply VIX adjustments (R11)
        criteria, vix_label = apply_vix_adjustments(criteria, self.vix_regime, self.config)

        # Apply theta adjustments (R10)
        criteria, theta_label = apply_theta_adjustments(criteria, theta_score, self.config)

        # Evaluate overnight criteria (R3)
        results = criteria.evaluate(position, account_equity)
        decision.criteria_results = results

        # Apply adjustment labels to criteria results
        if vix_label and 'min_pnl_pct' in results:
            results['min_pnl_pct'].adjusted_by = vix_label
        if theta_label and 'min_pnl_pct' in results:
            results['min_pnl_pct'].adjusted_by = theta_label

        # Check graduated window criteria for swing trades
        close_reason = evaluate_swing_trade_at_window(
            position, current_window, total_windows, results, self.config
        )
        if close_reason:
            decision.decision = 'close'
            decision.close_reason = close_reason
            decision.close_urgency_score = compute_close_urgency(
                position, theta_score, self._minutes_to_final_window(), self.config
            )
        # else: decision stays 'hold'

        return decision

    def evaluate_all_positions(self, positions: List[Dict[str, Any]],
                                current_window: int,
                                account_equity: float = 100000.0) -> List[EODDecision]:
        """
        Evaluate all positions, compute urgency scores, order closes.
        Returns decisions sorted by urgency (most urgent first).
        """
        decisions = []
        for pos in positions:
            dec = self.evaluate_position(pos, current_window, account_equity)
            decisions.append(dec)

        # Sort close decisions by urgency (highest first)
        decisions.sort(
            key=lambda d: d.close_urgency_score if d.close_urgency_score else 0.0,
            reverse=True,
        )
        return decisions

    def enforce_exposure_limit(self, decisions: List[EODDecision],
                                positions: List[Dict[str, Any]]) -> List[EODDecision]:
        """
        R5: After individual evaluation, enforce aggregate overnight exposure limit.
        Close least profitable qualifying holds until within limit.
        """
        # Build criteria with VIX adjustments for exposure limit
        criteria = OvernightCriteria(
            max_overnight_exposure=self.config.max_overnight_option_exposure,
        )
        criteria, _ = apply_vix_adjustments(criteria, self.vix_regime, self.config)
        exposure_limit = criteria.max_overnight_exposure

        # Find positions being held overnight
        holds = [(d, p) for d, p in zip(decisions, positions)
                 if d.decision == 'hold' and d.strategy_type == 'swing_trade']

        if not holds:
            return decisions

        # Calculate total overnight notional
        total_notional = sum(float(p.get('notional', 0) or 0) for _, p in holds)

        if total_notional <= exposure_limit:
            return decisions

        # Sort holds by P&L ascending (least profitable first)
        holds.sort(key=lambda x: x[0].pnl_pct)

        # Close least profitable until within limit
        for dec, pos in holds:
            if total_notional <= exposure_limit:
                break
            notional = float(pos.get('notional', 0) or 0)
            dec.decision = 'close'
            dec.close_reason = 'overnight_exposure_limit'
            total_notional -= notional

        return decisions

    def _minutes_to_final_window(self) -> float:
        """Estimate minutes to final window (rough, for urgency scoring)."""
        if not self._window_times:
            return 30.0
        try:
            import zoneinfo
            et = zoneinfo.ZoneInfo('America/New_York')
        except ImportError:
            # Rough estimate
            return 30.0
        now_et = datetime.now(et).time()
        final = self._window_times[-1]
        now_minutes = now_et.hour * 60 + now_et.minute
        final_minutes = final.hour * 60 + final.minute
        return max(0.0, float(final_minutes - now_minutes))

