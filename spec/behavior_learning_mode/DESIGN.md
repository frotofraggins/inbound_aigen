# Behavior Learning Mode — Design

## Current Behavior Reference
- `SYSTEM_BEHAVIOR_AUDIT.md`
- `spec/system_change_template/CURRENT_STATE.md`

## Overview
Add **observability only** for trade outcomes. No changes to signal logic, thresholds, sizing, or exit decisions.

## Data Flow
```
position_manager.monitor
    -> compute mark price each loop
    -> update running MFE/MAE for open positions
    -> on close: write a single row to position_history

nightly_stats_job (scheduled)
    -> read position_history
    -> compute per‑ticker/strategy distributions
    -> write strategy_stats
```

## Mark Price Rules
- **Stocks:** use last trade price; if quote available, use mid (bid+ask)/2.
- **Options:** use mid if bid/ask available; otherwise fallback to last trade.
- **Spread at entry (options):** (ask - bid) / mid.

## PnL Definition (Unified)
- pnl_pct = (mark_price - entry_price) / entry_price
- pnl_dollars = (mark_price - entry_price) * qty * multiplier
  - multiplier = 1 (stocks)
  - multiplier = 100 (options)

## Exit Reason Normalization
Store a normalized label (string) for analytics:
- tp, sl, trail, time_stop, expiry_risk, theta_decay, manual, forced_close_missing_bracket, risk_gate_daily_loss, risk_gate_exposure

## Tables

### 1) position_history (raw outcomes)
One row per closed position.

Key columns:
- id (bigserial)
- position_id (active_positions.id)
- execution_id (UUID; from dispatch_executions.execution_id)
- ticker
- strategy_type (day|swing|stock)
- asset_type (stock|option)
- side (long/call/put)
- qty
- entry_ts, exit_ts
- entry_price, exit_price
- pnl_dollars, pnl_pct
- holding_minutes
- mfe_pct, mae_pct
- mfe_dollars, mae_dollars (optional)
- iv_rank_at_entry (nullable)
- spread_at_entry_pct (nullable)
- entry_features_json (jsonb)
- exit_reason
- created_at

### 2) position_path_marks (optional)
Low‑frequency path marks for debugging and future analysis.

Columns:
- position_id
- ts
- mark_price
- unrealized_pnl_pct
- unrealized_pnl_dollars

### 3) strategy_stats (aggregated)
Nightly/batch output.

Columns:
- as_of_date
- ticker
- strategy_type
- asset_type
- n_trades
- win_rate
- avg_return
- avg_mae, avg_mfe
- mae_p50/p70/p80/p90
- mfe_p50/p70/p80/p90
- avg_hold_win_min
- avg_hold_loss_min
- sharpe (nullable until n>=30)
- max_drawdown
- updated_at

## Integration Points

### position_manager/monitor.py
- During each price update, compute unrealized PnL% and update in‑memory extremes:
  - best_unrealized_pnl_pct (MFE)
  - worst_unrealized_pnl_pct (MAE)
- On close, write to `position_history` with final MFE/MAE and holding time.

### position_manager/exits.py
- Use normalized exit reason labels.
- When close succeeds, record exit metadata (price, reason, time).

### nightly_stats_job (new)
- Scheduled ECS task or Lambda.
- Read `position_history` and compute grouped stats.
- Enforce minimum n before Sharpe.

## Schema Notes
- DB is PostgreSQL.
- `dispatch_executions.execution_id` is UUID. `position_history.execution_id` should be UUID.
- Add `active_positions.execution_uuid` to bridge existing integer `execution_id` mismatch.
- Apply FK constraints only after schema alignment.

## Rollback
- Observability only. Rollback by dropping new tables.
- No trading behavior impacted.
