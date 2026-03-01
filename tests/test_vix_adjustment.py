"""
Property-based tests for VIX regime adjustments.
Feature: eod-trading-strategy, Property 12: VIX regime adjusts overnight criteria correctly

Validates: Requirements 11.2, 11.3, 11.4, 11.5, 11.7
"""
import pytest
from datetime import datetime, timezone, timedelta
from hypothesis import given, settings
from hypothesis import strategies as st

from services.position_manager.eod_engine import apply_vix_adjustments, is_vix_extreme
from services.position_manager.eod_config import EODConfig
from services.position_manager.eod_models import OvernightCriteria, VIXRegime


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

regimes = st.sampled_from(['complacent', 'normal', 'elevated', 'high', 'extreme'])
positive_floats = st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False)
multipliers = st.floats(min_value=1.0, max_value=10.0, allow_nan=False, allow_infinity=False)


def fresh_vix(regime: str, stale: bool = False) -> VIXRegime:
    """Build a VIXRegime with controllable staleness."""
    if stale:
        recorded = datetime.now(timezone.utc) - timedelta(hours=25)
    else:
        recorded = datetime.now(timezone.utc) - timedelta(minutes=5)
    return VIXRegime(vix_value=25.0, regime=regime, recorded_at=recorded)


# ---------------------------------------------------------------------------
# Property 12: VIX regime adjusts overnight criteria correctly
# Validates: Requirements 11.2, 11.3, 11.4, 11.5, 11.7
# ---------------------------------------------------------------------------

class TestVIXRegimeAdjustments:
    """Property 12: VIX regime adjusts overnight criteria correctly."""

    @given(
        base_pnl=positive_floats,
        base_exposure=positive_floats,
        elevated_mult=multipliers,
        high_mult=multipliers,
    )
    @settings(max_examples=200)
    def test_complacent_normal_no_adjustment(self, base_pnl, base_exposure, elevated_mult, high_mult):
        """R11.5: complacent/normal → no adjustment."""
        config = EODConfig(vix_elevated_multiplier=elevated_mult, vix_high_multiplier=high_mult)
        criteria = OvernightCriteria(min_pnl_pct=base_pnl, max_overnight_exposure=base_exposure)

        for regime in ('complacent', 'normal'):
            vix = fresh_vix(regime)
            adjusted, label = apply_vix_adjustments(criteria, vix, config)
            assert label is None
            assert adjusted.min_pnl_pct == base_pnl
            assert adjusted.max_overnight_exposure == base_exposure

    @given(
        base_pnl=positive_floats,
        base_exposure=positive_floats,
        elevated_mult=multipliers,
    )
    @settings(max_examples=200)
    def test_elevated_multiplies_pnl(self, base_pnl, base_exposure, elevated_mult):
        """R11.2: elevated → P&L threshold × vix_elevated_multiplier."""
        config = EODConfig(vix_elevated_multiplier=elevated_mult)
        criteria = OvernightCriteria(min_pnl_pct=base_pnl, max_overnight_exposure=base_exposure)
        vix = fresh_vix('elevated')

        adjusted, label = apply_vix_adjustments(criteria, vix, config)

        assert label == 'vix_elevated'
        assert abs(adjusted.min_pnl_pct - base_pnl * elevated_mult) < 1e-6
        assert adjusted.max_overnight_exposure == base_exposure  # exposure unchanged

    @given(
        base_pnl=positive_floats,
        base_exposure=positive_floats,
        high_mult=multipliers,
    )
    @settings(max_examples=200)
    def test_high_multiplies_pnl_and_halves_exposure(self, base_pnl, base_exposure, high_mult):
        """R11.3: high → P&L × vix_high_multiplier AND exposure ÷ 2."""
        config = EODConfig(vix_high_multiplier=high_mult)
        criteria = OvernightCriteria(min_pnl_pct=base_pnl, max_overnight_exposure=base_exposure)
        vix = fresh_vix('high')

        adjusted, label = apply_vix_adjustments(criteria, vix, config)

        assert label == 'vix_high'
        assert abs(adjusted.min_pnl_pct - base_pnl * high_mult) < 1e-6
        assert abs(adjusted.max_overnight_exposure - base_exposure * 0.5) < 1e-6

    @given(regime=regimes)
    @settings(max_examples=50)
    def test_extreme_forces_close(self, regime):
        """R11.4: extreme → force-close all (detected via is_vix_extreme)."""
        vix = fresh_vix(regime)
        if regime == 'extreme':
            assert is_vix_extreme(vix) is True
        else:
            assert is_vix_extreme(vix) is False

    @given(
        regime=regimes,
        base_pnl=positive_floats,
        elevated_mult=multipliers,
    )
    @settings(max_examples=200)
    def test_stale_data_applies_elevated(self, regime, base_pnl, elevated_mult):
        """R11.7: stale VIX data → apply elevated multipliers."""
        config = EODConfig(vix_elevated_multiplier=elevated_mult)
        criteria = OvernightCriteria(min_pnl_pct=base_pnl)
        vix = fresh_vix(regime, stale=True)

        # Stale data should always use 'elevated' effective regime
        assert vix.effective_regime == 'elevated'

        adjusted, label = apply_vix_adjustments(criteria, vix, config)
        assert label == 'vix_elevated'
        assert abs(adjusted.min_pnl_pct - base_pnl * elevated_mult) < 1e-6
