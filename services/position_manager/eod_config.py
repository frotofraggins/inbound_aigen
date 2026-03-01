"""
EOD Exit Engine Configuration
Loads and validates all EOD-related SSM parameters with safe defaults.
Supports account-tier-specific overrides (large vs tiny).
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Account-tier default overrides
TIER_DEFAULTS = {
    'tiny': {
        'max_overnight_option_exposure': 200.0,
        'min_pnl_pct_for_overnight': 15.0,
        'last_entry_hour_et_day_trade': 13,
        'last_entry_hour_et_swing_trade': 14,
    },
    'large': {},  # uses base defaults
}


@dataclass
class EODConfig:
    """All EOD exit engine parameters — loaded from SSM JSON with safe defaults."""

    # R1-R3: Overnight hold criteria
    min_dte_for_overnight: int = 3
    min_pnl_pct_for_overnight: float = 10.0
    max_position_pct_for_overnight: float = 5.0

    # R2: P&L-aware closing
    profit_delay_threshold_pct: float = 20.0
    profit_delay_minutes: int = 10

    # R5: Overnight exposure limit
    max_overnight_option_exposure: float = 5000.0

    # R4: Entry cutoffs
    last_entry_hour_et_day_trade: int = 14
    last_entry_hour_et_swing_trade: int = 15

    # R10: Theta scoring
    high_theta_threshold: float = 0.05
    theta_pnl_penalty_pct: float = 10.0

    # R11: VIX regime
    vix_elevated_multiplier: float = 1.5
    vix_high_multiplier: float = 2.0

    # R13: Graduated close windows
    graduated_close_windows: List[str] = field(
        default_factory=lambda: ["14:30", "15:00", "15:30", "15:55"]
    )
    window_1_max_loss_pct: float = -20.0
    window_2_max_loss_pct: float = -10.0

    # R14: Close-loop integrity
    max_closing_duration_minutes: int = 5
    max_positions_per_ticker: int = 3

    @classmethod
    def for_account_tier(cls, tier: str) -> 'EODConfig':
        """Create an EODConfig with tier-specific defaults applied."""
        overrides = TIER_DEFAULTS.get(tier, {})
        return cls(**overrides)

    @classmethod
    def from_ssm(cls, ssm_params: Dict[str, Any], account_tier: str = 'large') -> 'EODConfig':
        """
        Parse from SSM JSON dict with defaults for missing/invalid values.
        Applies account-tier defaults first, then SSM overrides on top.
        """
        base = cls.for_account_tier(account_tier)
        if not ssm_params:
            return base

        base.min_dte_for_overnight = _safe_int(
            ssm_params, 'min_dte_for_overnight', base.min_dte_for_overnight, min_val=0
        )
        base.min_pnl_pct_for_overnight = _safe_float(
            ssm_params, 'min_pnl_pct_for_overnight', base.min_pnl_pct_for_overnight, min_val=0, max_val=100
        )
        base.max_position_pct_for_overnight = _safe_float(
            ssm_params, 'max_position_pct_for_overnight', base.max_position_pct_for_overnight, min_val=0, max_val=100
        )
        base.profit_delay_threshold_pct = _safe_float(
            ssm_params, 'profit_delay_threshold_pct', base.profit_delay_threshold_pct, min_val=0, max_val=100
        )
        base.profit_delay_minutes = _safe_int(
            ssm_params, 'profit_delay_minutes', base.profit_delay_minutes, min_val=0
        )
        base.max_overnight_option_exposure = _safe_float(
            ssm_params, 'max_overnight_option_exposure', base.max_overnight_option_exposure, min_val=0
        )
        base.last_entry_hour_et_day_trade = _safe_int(
            ssm_params, 'last_entry_hour_et_day_trade', base.last_entry_hour_et_day_trade, min_val=0, max_val=23
        )
        base.last_entry_hour_et_swing_trade = _safe_int(
            ssm_params, 'last_entry_hour_et_swing_trade', base.last_entry_hour_et_swing_trade, min_val=0, max_val=23
        )
        base.high_theta_threshold = _safe_float(
            ssm_params, 'high_theta_threshold', base.high_theta_threshold, min_val=0, max_val=1
        )
        base.theta_pnl_penalty_pct = _safe_float(
            ssm_params, 'theta_pnl_penalty_pct', base.theta_pnl_penalty_pct, min_val=0, max_val=100
        )
        base.vix_elevated_multiplier = _safe_float(
            ssm_params, 'vix_elevated_multiplier', base.vix_elevated_multiplier, min_val=1.0
        )
        base.vix_high_multiplier = _safe_float(
            ssm_params, 'vix_high_multiplier', base.vix_high_multiplier, min_val=1.0
        )
        base.window_1_max_loss_pct = _safe_float(
            ssm_params, 'window_1_max_loss_pct', base.window_1_max_loss_pct, max_val=0
        )
        base.window_2_max_loss_pct = _safe_float(
            ssm_params, 'window_2_max_loss_pct', base.window_2_max_loss_pct, max_val=0
        )
        base.max_closing_duration_minutes = _safe_int(
            ssm_params, 'max_closing_duration_minutes', base.max_closing_duration_minutes, min_val=1
        )
        base.max_positions_per_ticker = _safe_int(
            ssm_params, 'max_positions_per_ticker', base.max_positions_per_ticker, min_val=1
        )

        # Graduated windows — validate as list of HH:MM strings
        raw_windows = ssm_params.get('graduated_close_windows')
        if isinstance(raw_windows, list) and len(raw_windows) > 0:
            valid = True
            for w in raw_windows:
                if not isinstance(w, str) or len(w) != 5 or w[2] != ':':
                    valid = False
                    break
                try:
                    h, m = int(w[:2]), int(w[3:])
                    if not (0 <= h <= 23 and 0 <= m <= 59):
                        valid = False
                        break
                except ValueError:
                    valid = False
                    break
            if valid:
                base.graduated_close_windows = raw_windows
            else:
                logger.warning(f"Invalid graduated_close_windows, using defaults: {raw_windows}")

        return base

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            'min_dte_for_overnight': self.min_dte_for_overnight,
            'min_pnl_pct_for_overnight': self.min_pnl_pct_for_overnight,
            'max_position_pct_for_overnight': self.max_position_pct_for_overnight,
            'profit_delay_threshold_pct': self.profit_delay_threshold_pct,
            'profit_delay_minutes': self.profit_delay_minutes,
            'max_overnight_option_exposure': self.max_overnight_option_exposure,
            'last_entry_hour_et_day_trade': self.last_entry_hour_et_day_trade,
            'last_entry_hour_et_swing_trade': self.last_entry_hour_et_swing_trade,
            'high_theta_threshold': self.high_theta_threshold,
            'theta_pnl_penalty_pct': self.theta_pnl_penalty_pct,
            'vix_elevated_multiplier': self.vix_elevated_multiplier,
            'vix_high_multiplier': self.vix_high_multiplier,
            'graduated_close_windows': self.graduated_close_windows,
            'window_1_max_loss_pct': self.window_1_max_loss_pct,
            'window_2_max_loss_pct': self.window_2_max_loss_pct,
            'max_closing_duration_minutes': self.max_closing_duration_minutes,
            'max_positions_per_ticker': self.max_positions_per_ticker,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EODConfig':
        """Deserialize from dict. Uses from_ssm logic for validation."""
        return cls.from_ssm(data)


def _safe_float(
    params: Dict, key: str, default: float,
    min_val: Optional[float] = None, max_val: Optional[float] = None
) -> float:
    """Extract a float from params with validation. Returns default on any issue."""
    val = params.get(key)
    if val is None:
        return default
    try:
        fval = float(val)
        if min_val is not None and fval < min_val:
            logger.warning(f"EODConfig: {key}={fval} below min {min_val}, using default {default}")
            return default
        if max_val is not None and fval > max_val:
            logger.warning(f"EODConfig: {key}={fval} above max {max_val}, using default {default}")
            return default
        return fval
    except (ValueError, TypeError):
        logger.warning(f"EODConfig: {key}={val!r} is not numeric, using default {default}")
        return default


def _safe_int(
    params: Dict, key: str, default: int,
    min_val: Optional[int] = None, max_val: Optional[int] = None
) -> int:
    """Extract an int from params with validation. Returns default on any issue."""
    val = params.get(key)
    if val is None:
        return default
    try:
        ival = int(val)
        if min_val is not None and ival < min_val:
            logger.warning(f"EODConfig: {key}={ival} below min {min_val}, using default {default}")
            return default
        if max_val is not None and ival > max_val:
            logger.warning(f"EODConfig: {key}={ival} above max {max_val}, using default {default}")
            return default
        return ival
    except (ValueError, TypeError):
        logger.warning(f"EODConfig: {key}={val!r} is not numeric, using default {default}")
        return default
