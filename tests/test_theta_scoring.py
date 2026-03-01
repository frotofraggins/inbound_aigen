"""
Property-based tests for theta scoring.
Feature: eod-trading-strategy, Property 10: Theta score computation and threshold adjustment
Feature: eod-trading-strategy, Property 11: High theta + low DTE forces close

Validates: Requirements 10.1, 10.2, 10.3, 10.5
"""
import pytest
from hypothesis import given, assume, settings
from hypothesis import strategies as st

from services.position_manager.eod_engine import compute_theta_score, apply_theta_adjustments, should_force_close_theta
from services.position_manager.eod_config import EODConfig
from services.position_manager.eod_models import OvernightCriteria


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

positive_floats = st.floats(min_value=0.01, max_value=1000.0, allow_nan=False, allow_infinity=False)
non_negative_floats = st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False)
theta_values = st.floats(min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False)


def position_with_theta(theta, premium):
    """Build a minimal position dict with theta and premium."""
    return {'theta': theta, 'current_price': premium}


# ---------------------------------------------------------------------------
# Property 10: Theta score computation and threshold adjustment
# Validates: Requirements 10.1, 10.2, 10.5
# ---------------------------------------------------------------------------

class TestThetaScoreComputation:
    """Property 10: Theta score computation and threshold adjustment."""

    @given(theta=theta_values, premium=positive_floats)
    @settings(max_examples=200)
    def test_theta_score_equals_abs_theta_over_premium(self, theta, premium):
        """R10.1: theta_score = abs(theta) / premium for valid inputs."""
        pos = position_with_theta(theta, premium)
        score = compute_theta_score(pos)
        expected = abs(theta) / premium
        assert abs(score - expected) < 1e-9

    @given(premium=positive_floats)
    @settings(max_examples=100)
    def test_null_theta_returns_max_risk(self, premium):
        """R10.5: null theta → max risk (1.0)."""
        pos = {'theta': None, 'current_price': premium}
        assert compute_theta_score(pos) == 1.0

    @given(theta=theta_values)
    @settings(max_examples=100)
    def test_null_premium_returns_max_risk(self, theta):
        """R10.5: null premium → max risk (1.0)."""
        pos = {'theta': theta, 'current_price': None}
        assert compute_theta_score(pos) == 1.0

    @given(theta=theta_values)
    @settings(max_examples=100)
    def test_zero_premium_returns_max_risk(self, theta):
        """R10.1: zero premium → max risk (1.0)."""
        pos = {'theta': theta, 'current_price': 0.0}
        assert compute_theta_score(pos) == 1.0

    def test_missing_theta_key_returns_max_risk(self):
        """R10.5: missing theta key → max risk."""
        assert compute_theta_score({'current_price': 5.0}) == 1.0

    def test_missing_premium_key_returns_max_risk(self):
        """R10.5: missing premium key → max risk."""
        assert compute_theta_score({'theta': -0.05}) == 1.0

    @given(
        theta=theta_values,
        premium=positive_floats,
        high_theta_threshold=st.floats(min_value=0.01, max_value=0.5, allow_nan=False, allow_infinity=False),
        penalty=st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False),
        base_pnl=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200)
    def test_theta_adjustment_lowers_pnl_when_above_threshold(
        self, theta, premium, high_theta_threshold, penalty, base_pnl
    ):
        """R10.2: When theta_score > threshold, min_pnl_pct is reduced by penalty."""
        pos = position_with_theta(theta, premium)
        score = compute_theta_score(pos)

        config = EODConfig(high_theta_threshold=high_theta_threshold, theta_pnl_penalty_pct=penalty)
        criteria = OvernightCriteria(min_pnl_pct=base_pnl)

        adjusted, label = apply_theta_adjustments(criteria, score, config)

        if score > high_theta_threshold:
            assert label == 'theta_penalty'
            assert adjusted.min_pnl_pct == max(0.0, base_pnl - penalty)
        else:
            assert label is None
            assert adjusted.min_pnl_pct == base_pnl


# ---------------------------------------------------------------------------
# Property 11: High theta + low DTE forces close
# Validates: Requirements 10.3
# ---------------------------------------------------------------------------

class TestHighThetaLowDTEForceClose:
    """Property 11: High theta + low DTE forces close."""

    @given(
        dte=st.integers(min_value=0, max_value=2),
        theta=theta_values,
        premium=positive_floats,
        threshold=st.floats(min_value=0.001, max_value=0.5, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200)
    def test_low_dte_high_theta_forces_close(self, dte, theta, premium, threshold):
        """R10.3: DTE <= 2 AND theta_score > threshold → force close."""
        pos = {'theta': theta, 'current_price': premium, 'dte': dte}
        score = compute_theta_score(pos)
        config = EODConfig(high_theta_threshold=threshold)

        result = should_force_close_theta(pos, score, config)

        if dte <= 2 and score > threshold:
            assert result is True
        else:
            assert result is False

    @given(
        dte=st.integers(min_value=3, max_value=365),
        theta=theta_values,
        premium=positive_floats,
        threshold=st.floats(min_value=0.001, max_value=0.5, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_high_dte_never_forces_close(self, dte, theta, premium, threshold):
        """R10.3: DTE > 2 → never force close via theta alone."""
        pos = {'theta': theta, 'current_price': premium, 'dte': dte}
        score = compute_theta_score(pos)
        config = EODConfig(high_theta_threshold=threshold)

        assert should_force_close_theta(pos, score, config) is False
