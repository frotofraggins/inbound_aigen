# Behavior Learning Mode Spec

## Purpose
Teach the system what "normal" looks like before making statistical decisions.

The system must collect and store outcome behavior for every trade so that:
- exits can become distribution-based
- stops can adapt per ticker
- confidence can be statistically validated
- strategies can be enabled/disabled based on evidence

No new trading logic is added in this phase.
This phase is OBSERVATION ONLY.

--------------------------------------------------

## Current Behavior Reference
- SYSTEM_BEHAVIOR_AUDIT.md
- spec/system_change_template/CURRENT_STATE.md

--------------------------------------------------

## Requirements

### Must Collect (per closed trade)
- entry_price
- exit_price
- pnl_dollars
- pnl_pct
- holding_minutes
- max_favorable_excursion_pct (MFE)
- max_adverse_excursion_pct (MAE)
- iv_rank_at_entry (options)
- spread_at_entry (options)
- feature snapshot at entry
- exit_reason

### Must Compute (nightly or batch)
For each:
- ticker
- strategy type (day/swing/stock)
- option vs stock

Store:
- win rate
- avg return
- avg MAE
- avg MFE
- MAE percentiles (50/70/80/90)
- MFE percentiles
- average holding time (wins)
- average holding time (losses)
- Sharpe
- max drawdown

### Must NOT change
- signal logic
- thresholds
- exits
- sizing

This phase does NOT alter trading behavior.

--------------------------------------------------

## Design

### Data flow

position_manager
    -> capture price updates during trade
    -> update running MFE/MAE
    -> on close -> write to position_history

nightly_stats_job
    -> read position_history
    -> compute distributions
    -> write strategy_stats

### Tables

position_history (raw outcomes)
strategy_stats (aggregated distributions)

--------------------------------------------------

## Acceptance Criteria

- Every closed trade has MAE/MFE populated
- Holding time recorded
- Stats table populated nightly
- No trading behavior changed
- Dashboard shows distributions per ticker/strategy

--------------------------------------------------

## Success Definition

System can answer:

"What is normal behavior for this ticker?"

"What does a loser look like?"

"How long do winners usually take?"

If those questions cannot be answered, this phase is incomplete.
