"""
Property-based tests for EOD Exit Engine core logic.
Feature: eod-trading-strategy, Property 1: Day trade positions are always closed at final window
Feature: eod-trading-strategy, Property 2: Swing trade hold decision is equivalent to passing all overnight criteria
Feature: eod-trading-strategy, Property 3: Day trade close timing depends on P&L
Feature: eod-trading-strategy, Property 7: Overnight exposure limit closes least profitable first

Validates: Requirements 1.1, 1.3, 1.4, 1.5, 2.1, 2.3, 5.1, 5.2, 13.5
"""
import pytest
from datetime import datetime, timezone, timedelta
from hypothesis import given, assume, settings
from hypothesis import strategies as st

from services.position_manager.eod_engine import (
    EODExitEngine, evaluate_day_trade_at_window, compute_close_urgency,
)
from services.position_manager.eod_config import EODConfig
from services.position_manager.eod_models import VIXRegime, OvernightCriteria


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

pnl_pcts = st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False)
positive_floats = st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False)
dtes = st.integers(min_value=0, max_value=365)
strategy_types = st.sampled_from(['day_trade', 'swing_trade', '', None, 'unknown'])

NORMAL_VIX = VIXRegime(vix_value=15.0, regime='normal',
                        recorded_at=datetime.now(timezone.utc))


def make_position(strategy_type='day_trade', pnl_pct=0.0, dte=10,
                   notional=100.0, theta=-0.02, current_price=5.0,
                   status='open', pos_id=1):
    return {
        'id': pos_id,
        'ticker': 'AAPL',
        'strategy_type': strategy_type,
        'current_pnl_percent': pnl_pct,
        'current_pnl_dollars': pnl_pct * 10,
        'dte': dte,
        'notional': notional,
        'theta': theta,
        'current_price': current_price,
        'entry_price': current_price,
        'status': status,
    }


def make_engine(config=None, vix_regime=None):
    config = config or EODConfig()
    vix = vix_regime or NORMAL_VIX
    return EODExitEngine(config=config, account_tier='large', vix_regime=vix)


# ---------------------------------------------------------------------------
# Property 1: Day trade positions are always closed at final window
# Validates: Requirements 1.1, 1.5, 13.5
# ---------------------------------------------------------------------------

class TestDayTradeAlwaysClosedAtFinal:
    """Property 1: Day trade positions are always closed at final window."""

    @given(
        pnl_pct=pnl_pcts,
        dte=dtes,
    )
    @settings(max_examples=200)
    def test_day_trade_closed_at_final_window(self, pnl_pct, dte):
        """R1.1, R13.5: Day trades always close at final window regardless of P&L."""
        engine = make_engine()
        pos = make_position('day_trade', pnl_pct=pnl_pct, dte=dte)
        # Final window = index 3 (4 windows total)
        decision = engine.evaluate_position(pos, current_window=3)
        assert decision.decision == 'close'

    @given(pnl_pct=pnl_pcts, dte=dtes)
    @settings(max_examples=200)
    def test_unknown_strategy_treated_as_day_trade(self, pnl_pct, dte):
        """R1.5: Unknown/missing strategy → treated as day trade → closed at final."""
        engine = make_engine()
        for strat in ['', None, 'unknown', 'garbage']:
            pos = make_position(strat, pnl_pct=pnl_pct, dte=dte)
            decision = engine.evaluate_position(pos, current_window=3)
            assert decision.decision == 'close'


# ---------------------------------------------------------------------------
# Property 2: Swing trade hold ↔ passing all overnight criteria
# Validates: Requirements 1.3, 1.4
# ---------------------------------------------------------------------------

class TestSwingTradeHoldEquivalence:
    """Property 2: Swing trade hold decision is equivalent to passing all overnight criteria."""

    @given(
        pnl_pct=st.floats(min_value=-50.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        dte=st.integers(min_value=0, max_value=30),
        notional=st.floats(min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        equity=st.floats(min_value=1000.0, max_value=500000.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=300)
    def test_swing_hold_iff_all_criteria_pass(self, pnl_pct, dte, notional, equity):
        """R1.3/R1.4: Swing hold ↔ all overnight criteria pass at final window."""
        config = EODConfig()
        engine = make_engine(config=config, vix_regime=NORMAL_VIX)

        pos = make_position('swing_trade', pnl_pct=pnl_pct, dte=dte,
                             notional=notional, theta=-0.01, current_price=5.0)

        # Evaluate at final window (index 3)
        decision = engine.evaluate_position(pos, current_window=3, account_equity=equity)

        # Independently compute what criteria should say
        criteria = OvernightCriteria(
            min_dte=config.min_dte_for_overnight,
            min_pnl_pct=config.min_pnl_pct_for_overnight,
            max_position_pct=config.max_position_pct_for_overnight,
        )
        results = criteria.evaluate(pos, equity)
        all_pass = all(cr.passed for cr in results.values())

        # At final window with normal VIX and low theta:
        # hold ↔ all criteria pass
        theta_score = abs(-0.01) / 5.0  # 0.002, below default threshold 0.05
        assert theta_score <= config.high_theta_threshold  # confirm no theta adjustment

        if all_pass:
            assert decision.decision == 'hold', f"Expected hold but got {decision.decision} ({decision.close_reason})"
        else:
            assert decision.decision == 'close', f"Expected close but got {decision.decision}"


# ---------------------------------------------------------------------------
# Property 3: Day trade close timing depends on P&L
# Validates: Requirements 2.1, 2.3
# ---------------------------------------------------------------------------

class TestDayTradeCloseTimingPnL:
    """Property 3: Day trade close timing depends on P&L."""

    @given(pnl_pct=st.floats(min_value=-100.0, max_value=-0.01, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_losing_day_trade_closed_at_window_0_if_big_loss(self, pnl_pct):
        """R2.3: Day trades with loss > window_1_max_loss_pct close at window 0."""
        config = EODConfig(window_1_max_loss_pct=-20.0)
        result = evaluate_day_trade_at_window(
            {'current_pnl_percent': pnl_pct}, window_index=0, total_windows=4, config=config
        )
        if pnl_pct < -20.0:
            assert result is not None
        else:
            assert result is None

    @given(pnl_pct=st.floats(min_value=0.01, max_value=100.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_profitable_day_trade_not_closed_early(self, pnl_pct):
        """R2.1: Profitable day trades are not closed at early windows."""
        config = EODConfig()
        for window in [0, 1, 2]:
            result = evaluate_day_trade_at_window(
                {'current_pnl_percent': pnl_pct}, window_index=window,
                total_windows=4, config=config
            )
            assert result is None, f"Profitable day trade closed at window {window}"


# ---------------------------------------------------------------------------
# Property 7: Overnight exposure limit closes least profitable first
# Validates: Requirements 5.1, 5.2
# ---------------------------------------------------------------------------

class TestOvernightExposureLimit:
    """Property 7: Overnight exposure limit closes least profitable first."""

    def test_exposure_limit_closes_least_profitable(self):
        """R5.1/R5.2: When over limit, close least profitable first."""
        config = EODConfig(max_overnight_option_exposure=500.0,
                           min_pnl_pct_for_overnight=5.0)  # low bar so all pass
        engine = make_engine(config=config)

        positions = [
            make_position('swing_trade', pnl_pct=30.0, dte=10, notional=200.0, pos_id=1),
            make_position('swing_trade', pnl_pct=10.0, dte=10, notional=200.0, pos_id=2),
            make_position('swing_trade', pnl_pct=50.0, dte=10, notional=200.0, pos_id=3),
        ]

        # All pass criteria individually → all hold
        decisions = engine.evaluate_all_positions(positions, current_window=3, account_equity=100000.0)

        # Total notional = 600, limit = 500 → need to close 1
        decisions = engine.enforce_exposure_limit(decisions, positions)

        holds = [d for d in decisions if d.decision == 'hold']
        closes = [d for d in decisions if d.decision == 'close' and d.close_reason == 'overnight_exposure_limit']

        # The least profitable (10.0%) should be closed
        assert len(closes) >= 1
        closed_pnls = [d.pnl_pct for d in closes]
        held_pnls = [d.pnl_pct for d in holds if d.strategy_type == 'swing_trade']

        # All closed positions should have lower P&L than all held positions
        if closed_pnls and held_pnls:
            assert max(closed_pnls) <= min(held_pnls)

    def test_within_limit_no_closes(self):
        """R5.5: If within limit, no positions force-closed."""
        config = EODConfig(max_overnight_option_exposure=10000.0)
        engine = make_engine(config=config)

        positions = [
            make_position('swing_trade', pnl_pct=20.0, dte=10, notional=200.0, pos_id=1),
            make_position('swing_trade', pnl_pct=15.0, dte=10, notional=200.0, pos_id=2),
        ]

        decisions = engine.evaluate_all_positions(positions, current_window=3, account_equity=100000.0)
        decisions = engine.enforce_exposure_limit(decisions, positions)

        exposure_closes = [d for d in decisions if d.close_reason == 'overnight_exposure_limit']
        assert len(exposure_closes) == 0

    @given(
        num_positions=st.integers(min_value=2, max_value=8),
        exposure_limit=st.floats(min_value=100.0, max_value=5000.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_exposure_limit_preserves_most_profitable(self, num_positions, exposure_limit):
        """R5.2: Least profitable closed first, most profitable preserved."""
        config = EODConfig(
            max_overnight_option_exposure=exposure_limit,
            min_pnl_pct_for_overnight=5.0,  # low bar so generated positions pass
        )
        engine = make_engine(config=config)

        positions = []
        for i in range(num_positions):
            pnl = 10.0 + i * 5.0  # ascending P&L, all above 5.0 threshold
            positions.append(make_position(
                'swing_trade', pnl_pct=pnl, dte=10, notional=200.0, pos_id=i + 1
            ))

        decisions = engine.evaluate_all_positions(positions, current_window=3, account_equity=100000.0)
        decisions = engine.enforce_exposure_limit(decisions, positions)

        closed = [d for d in decisions if d.close_reason == 'overnight_exposure_limit']
        held = [d for d in decisions if d.decision == 'hold' and d.strategy_type == 'swing_trade']

        # Closed positions should have lower P&L than held positions
        if closed and held:
            assert max(d.pnl_pct for d in closed) <= min(d.pnl_pct for d in held)
