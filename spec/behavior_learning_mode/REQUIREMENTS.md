# Behavior Learning Mode — Requirements

## Purpose
Instrument trade outcomes without changing trading behavior.

## Current Behavior Reference
- `SYSTEM_BEHAVIOR_AUDIT.md`
- `spec/system_change_template/CURRENT_STATE.md`

## Requirements (Must)

### Per Closed Trade (raw outcomes)
Store:
- entry_price
- exit_price
- pnl_dollars
- pnl_pct
- holding_minutes
- max_favorable_excursion_pct (MFE)
- max_adverse_excursion_pct (MAE)
- iv_rank_at_entry (options; nullable)
- spread_at_entry_pct (options; nullable)
- entry_features_json (JSONB snapshot)
- exit_reason (normalized label)

### Aggregated Stats (nightly/batch)
Group by:
- ticker
- strategy_type (day/swing/stock)
- asset_type (stock/option)

Store:
- n_trades
- win_rate
- avg_return
- avg_mae
- avg_mfe
- mae_p50/p70/p80/p90
- mfe_p50/p70/p80/p90
- avg_hold_win_min
- avg_hold_loss_min
- sharpe (nullable until n>=30)
- max_drawdown

### Non‑Goals (Must NOT change)
- signal logic
- thresholds
- exits
- sizing
- execution routing

## Acceptance Criteria
- Every closed trade inserts one row into `position_history`.
- `holding_minutes`, `mfe_pct`, `mae_pct` are non‑null for closed trades.
- `entry_features_json` exists for every closed trade.
- `strategy_stats` populated nightly with monotonic percentiles.
- No change in trade decisions or execution behavior.

## Constraints
- Target database: PostgreSQL.
- Do not require new external data sources.

