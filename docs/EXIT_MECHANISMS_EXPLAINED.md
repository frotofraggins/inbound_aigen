# Exit Mechanisms — How Positions Close
**Last Updated:** February 11, 2026  
**System Version:** v17 (EOD Engine)

---

## Overview

The system has two layers of exit logic:

1. **Standard exits** — run every minute, apply to all positions regardless of time of day
2. **EOD Exit Engine** — activates during graduated close windows (2:30–3:55 PM ET), strategy-aware and P&L-aware

---

## Standard Exit Mechanisms (Always Active)

### 1. Take Profit (+80%)
Position reaches +80% unrealized gain. Locks in big wins.

### 2. Stop Loss (-40%)
Position reaches -40% unrealized loss. Limits downside.

### 3. Trailing Stop (75% of peak)
Once a position reaches a new high, the trailing stop locks in 75% of peak gains. If price retraces past the trailing stop level, the position closes. Active since Feb 6.

### 4. Max Hold Time (4 hours default)
Position held longer than `max_hold_minutes` (default 240). Closes with whatever P&L exists. Prevents capital from sitting idle.

### 5. Options Expiration Emergency (< 24 hours)
Option within 24 hours of expiration. Force-closes to prevent worthless expiration.

### 6. Theta Decay Warning (< 7 days, < 30% profit)
Option within 7 days of expiry AND less than 30% profit. Exits before time decay erodes small gains.

### 7. Manual Close
Closed via Alpaca dashboard or API. Overrides everything.

---

## EOD Exit Engine (New — Feb 11)

Replaces the old blanket 3:55 PM force-close. The EOD engine is strategy-aware, meaning it treats day trades and swing trades differently.

### Graduated Close Windows

Four evaluation checkpoints with progressively stricter criteria:

| Window | Time (ET) | Day Trades | Swing Trades |
|--------|-----------|------------|--------------|
| 0 | 2:30 PM | Close if loss > 20% | No action |
| 1 | 3:00 PM | Close if loss > 10% | Close if failing >1 overnight criterion |
| 2 | 3:30 PM | Close all losing | Close if failing any criterion |
| 3 | 3:55 PM | Close ALL remaining | Close all that don't qualify for overnight |

### Strategy Routing

- **Day trades** (and unknown/missing strategy): Always closed by final window. Earlier windows close losers progressively.
- **Swing trades**: Evaluated against overnight hold criteria. Can hold overnight if they pass all checks.

### Overnight Hold Criteria (Swing Trades)

A swing trade can hold overnight only if ALL of these pass:

| Criterion | Large Account | Tiny Account |
|-----------|--------------|--------------|
| DTE (days to expiration) | ≥ 3 | ≥ 3 |
| Unrealized P&L | ≥ 10% | ≥ 15% |
| Position size (% of equity) | ≤ 5% | ≤ 5% |

These thresholds are adjusted by VIX regime and theta scoring (see below).

### Theta Scoring

Theta score = `abs(theta) / current_premium`. Measures how fast the option is decaying.

- If theta is unavailable: treated as maximum risk (score = 1.0)
- If theta score > 0.05 (high): P&L threshold for overnight hold is reduced by 10 percentage points
- If DTE ≤ 2 AND high theta: force-close regardless of P&L

### VIX Regime Adjustment

The system queries the latest VIX regime and adjusts overnight criteria:

| VIX Regime | P&L Threshold | Exposure Limit | Action |
|------------|---------------|----------------|--------|
| Complacent/Normal | No change | No change | — |
| Elevated | × 1.5 | No change | Tighter P&L bar |
| High | × 2.0 | ÷ 2 | Much tighter + reduced exposure |
| Extreme | — | — | Force-close ALL positions |

If VIX data is stale (>24h) or unavailable, the system defaults to "elevated" (conservative).

### Earnings Calendar

Positions with earnings within 1 trading day are force-closed, regardless of P&L or other criteria. The earnings client queries Alpaca corporate actions API and caches results per trading day.

### Overnight Exposure Limit

After individual position evaluation, the engine sums the notional value of all positions qualifying for overnight hold:

- Large account limit: $5,000
- Tiny account limit: $200

If over the limit, the least profitable positions are closed first until within the limit.

### Close-Loop Monitor

Detects positions stuck in "closing" state beyond 5 minutes:

1. Retries the close order once
2. If retry fails, logs `close_failed` event for manual review
3. If market is closed, queues the close for next market open
4. Also detects and cleans up duplicate positions (same ticker/account/instrument type)

### Close Urgency Score

When multiple positions need closing at the same window, they're prioritized by a composite urgency score:

- Worse P&L → higher urgency
- Lower DTE → higher urgency
- Higher theta score → higher urgency
- Less time to market close → higher urgency

---

## Entry Cutoff Gates (New — Feb 11)

These gates prevent new entries too close to market close:

| Gate | Large Account | Tiny Account |
|------|--------------|--------------|
| Day trade cutoff | 2:00 PM ET | 1:00 PM ET |
| Swing trade cutoff | 3:00 PM ET | 2:00 PM ET |
| After-hours block | Outside 9:30 AM – 4:00 PM ET | Same |
| Duplicate position | Blocked if ticker already open/closing | Same |

---

## Exit Priority Order

When multiple exit conditions trigger simultaneously:

1. **Priority 1:** EOD Engine decisions (earnings, VIX extreme, graduated window)
2. **Priority 2:** Expiration emergency (< 24 hours)
3. **Priority 3:** Max hold time / Stop loss / Take profit / Trailing stop
4. **Priority 4:** Theta decay warning

---

## Decision Logging

Every EOD decision is logged to `position_events` with full context:

- `eod_decision` — strategy type, P&L, DTE, theta score, VIX regime, window index, per-criterion pass/fail
- `overnight_hold` — ticker, option symbol, expiration, entry/current price, criteria snapshot
- `overnight_outcome` — next-day open price vs previous close, overnight P&L
- `close_retry` / `close_failed` — stuck position recovery events
- `duplicate_cleanup` — duplicate position cleanup

All events feed into the AI learning pipeline for future parameter tuning.

---

## Configuration

All EOD parameters are SSM-configurable (JSON in Parameter Store) per account tier. Key parameters:

```json
{
  "graduated_close_windows": ["14:30", "15:00", "15:30", "15:55"],
  "window_1_max_loss_pct": -20.0,
  "window_2_max_loss_pct": -10.0,
  "min_dte_for_overnight": 3,
  "min_pnl_pct_for_overnight": 10.0,
  "max_position_pct_for_overnight": 5.0,
  "max_overnight_option_exposure": 5000.0,
  "high_theta_threshold": 0.05,
  "theta_pnl_penalty_pct": 10.0,
  "vix_elevated_multiplier": 1.5,
  "vix_high_multiplier": 2.0,
  "max_closing_duration_minutes": 5,
  "last_entry_hour_et_day_trade": 14,
  "last_entry_hour_et_swing_trade": 15
}
```

Tiny account overrides: `max_overnight_option_exposure: 200`, `min_pnl_pct_for_overnight: 15`, `last_entry_hour_et_day_trade: 13`, `last_entry_hour_et_swing_trade: 14`.
