# Requirements Document

## Introduction

The algorithmic options trading system currently force-closes ALL option positions at 3:55 PM ET regardless of strategy type, profitability, or expiration date. This blanket `market_close_protection` rule was added after overnight holds caused catastrophic losses (-52% on AMD), but it fails to distinguish between day trades and swing trades, dumps profitable positions alongside losers, and leaves no room for positions entered mid-afternoon to play out. This feature replaces the one-size-fits-all EOD close with a strategy-aware, P&L-aware, configurable exit system that properly handles overnight risk while preserving profitable swing trade positions with multi-day expiration.

## Glossary

- **Position_Manager**: The ECS service (`services/position_manager/`) that monitors open positions, updates prices, evaluates exit conditions, and executes closes.
- **Dispatcher**: The ECS service (`services/dispatcher/`) that receives signals, evaluates risk gates, and opens new positions.
- **Market_Close_Protection**: The exit rule in `check_time_based_exits()` that force-closes option positions before market close to avoid overnight risk.
- **Strategy_Type**: A field on each position record indicating `day_trade` (must close same day) or `swing_trade` (may hold overnight if criteria met).
- **EOD_Exit_Engine**: The new logic component within Position_Manager that evaluates end-of-day exit decisions using strategy type, P&L, and expiration data.
- **SSM_Config**: JSON configuration stored in AWS SSM Parameter Store, used to tune thresholds without code deploys.
- **Entry_Cutoff_Gate**: The trading hours risk gate in the Dispatcher that blocks new position entries after a configurable hour.
- **DTE**: Days to expiration — the number of calendar days remaining until an option contract expires.
- **Overnight_Hold_Criteria**: The set of conditions a swing trade option must satisfy to be held overnight (minimum DTE, minimum P&L, maximum position size).
- **Theta_Score**: A numeric score representing the rate of theta (time) decay for an option position, derived from the option's theta greek value and DTE. Higher theta scores indicate faster premium erosion.
- **VIX_Regime**: The current volatility classification from the `vix_history` table — one of `complacent`, `normal`, `elevated`, `high`, or `extreme` — used to dynamically adjust overnight hold thresholds.
- **Earnings_Calendar_Provider**: An external data source (e.g., Alpaca corporate actions API or equivalent) that provides upcoming earnings announcement dates and timing (before market open or after market close) for a given ticker.
- **Graduated_Close_Window**: A time-based evaluation checkpoint (e.g., 2:30 PM, 3:00 PM, 3:30 PM, 3:55 PM ET) at which the EOD_Exit_Engine evaluates open positions with progressively stricter exit criteria.
- **Close_Urgency_Score**: A composite score combining P&L, DTE, theta score, and time remaining to market close, used to prioritize which positions to close at each Graduated_Close_Window.
- **Close_Loop**: The lifecycle of a position close attempt from `status=closing` through order execution to `status=closed`. A stuck close loop occurs when a position remains in `closing` state beyond the expected duration.

## Requirements

### Requirement 1: Strategy-Aware EOD Exit Logic

**User Story:** As a trader, I want the system to differentiate between day trades and swing trades at end of day, so that day trades are closed before market close while qualifying swing trades can be held overnight.

#### Acceptance Criteria

1. WHEN the current time reaches the day trade close time AND a position has `strategy_type` equal to `day_trade`, THE EOD_Exit_Engine SHALL trigger a market close exit for that position.
2. WHEN the current time reaches the day trade close time AND a position has `strategy_type` equal to `swing_trade`, THE EOD_Exit_Engine SHALL evaluate the position against the Overnight_Hold_Criteria before deciding to close or hold.
3. WHEN a swing trade option position meets all Overnight_Hold_Criteria (minimum DTE, minimum P&L percentage, maximum position size percentage), THE EOD_Exit_Engine SHALL allow the position to be held overnight.
4. WHEN a swing trade option position fails any single Overnight_Hold_Criteria condition, THE EOD_Exit_Engine SHALL trigger a market close exit for that position.
5. IF a position has no `strategy_type` value or an unrecognized value, THEN THE EOD_Exit_Engine SHALL treat the position as a day trade and close it before market close.

### Requirement 2: P&L-Aware EOD Closing

**User Story:** As a trader, I want the system to consider current profit or loss when making end-of-day close decisions, so that profitable positions are not dumped alongside losing ones.

#### Acceptance Criteria

1. WHEN the EOD_Exit_Engine evaluates a day trade position for market close AND the position has unrealized profit above a configurable profit threshold percentage, THE EOD_Exit_Engine SHALL delay the close by a configurable number of minutes to allow further profit capture.
2. WHEN the delayed close time is reached for a profitable day trade, THE EOD_Exit_Engine SHALL close the position regardless of current P&L.
3. WHEN the EOD_Exit_Engine evaluates a day trade position for market close AND the position has unrealized loss, THE EOD_Exit_Engine SHALL close the position immediately at the standard day trade close time.
4. THE EOD_Exit_Engine SHALL log the P&L percentage and dollar amount at the time of every EOD close decision.

### Requirement 3: Configurable Overnight Hold Criteria

**User Story:** As a trader, I want to configure the conditions under which swing trade options can be held overnight via SSM parameters, so that I can tune risk tolerance without deploying code.

#### Acceptance Criteria

1. THE Position_Manager SHALL load overnight hold criteria from SSM_Config at startup and on each monitoring cycle.
2. THE SSM_Config SHALL contain the following overnight hold parameters: `min_dte_for_overnight` (integer, default 3), `min_pnl_pct_for_overnight` (float, default 10.0), `max_position_pct_for_overnight` (float, default 5.0 representing percentage of account equity).
3. WHEN any overnight hold parameter is missing from SSM_Config, THE Position_Manager SHALL use the default value for that parameter.
4. WHEN any overnight hold parameter contains an invalid value (non-numeric, negative DTE, or percentage outside 0-100), THE Position_Manager SHALL use the default value and log a warning.
5. THE SSM_Config SHALL store all parameters as valid JSON.

### Requirement 4: Strategy-Specific Entry Cutoff Times

**User Story:** As a trader, I want separate entry cutoff times for day trades and swing trades, so that day trades stop entering earlier in the day while swing trades can still enter later.

#### Acceptance Criteria

1. WHEN a signal has `strategy_type` equal to `day_trade` AND the current time is past the day trade entry cutoff hour, THE Entry_Cutoff_Gate SHALL block the signal.
2. WHEN a signal has `strategy_type` equal to `swing_trade` AND the current time is past the swing trade entry cutoff hour, THE Entry_Cutoff_Gate SHALL block the signal.
3. WHEN a signal has `strategy_type` equal to `swing_trade` AND the current time is between the day trade cutoff and the swing trade cutoff, THE Entry_Cutoff_Gate SHALL allow the signal.
4. THE SSM_Config SHALL contain `last_entry_hour_et_day_trade` (integer, default 14) and `last_entry_hour_et_swing_trade` (integer, default 15) parameters.
5. IF a signal has no `strategy_type` or an unrecognized value, THEN THE Entry_Cutoff_Gate SHALL apply the day trade entry cutoff (the more restrictive cutoff).

### Requirement 5: Overnight Risk Guardrails

**User Story:** As a trader, I want hard limits on overnight option exposure, so that even qualifying swing trades cannot create excessive overnight risk.

#### Acceptance Criteria

1. THE EOD_Exit_Engine SHALL calculate total overnight option exposure as the sum of notional values of all swing trade option positions qualifying for overnight hold.
2. WHEN total overnight option exposure exceeds a configurable maximum dollar amount, THE EOD_Exit_Engine SHALL close the least profitable qualifying positions until exposure is within the limit.
3. THE SSM_Config SHALL contain `max_overnight_option_exposure` (float, default 5000.0) as a dollar amount.
4. WHEN the overnight exposure limit is reached, THE EOD_Exit_Engine SHALL log which positions were force-closed and the exposure amount before and after.
5. THE EOD_Exit_Engine SHALL evaluate overnight exposure limits after individual position hold criteria, closing positions that passed individual criteria but exceed the aggregate limit.

### Requirement 6: AI-Consumable EOD Decision Logging

**User Story:** As an AI learning pipeline, I want structured EOD decision data in `position_history` and `position_events`, so that the trade analyzer and learning applier can evaluate overnight hold performance and recommend threshold adjustments.

#### Acceptance Criteria

1. WHEN the EOD_Exit_Engine makes a hold-or-close decision for any position, THE Position_Manager SHALL log a position event with event type `eod_decision` containing a JSON payload with: position ID, strategy type, decision (`hold` or `close`), P&L percentage, P&L dollars, DTE, account tier, each overnight hold criterion name with its observed value and threshold, and a boolean pass/fail for each criterion.
2. WHEN a position is closed due to EOD logic, THE Position_Manager SHALL set the `exit_reason_norm` field in `position_history` to `EOD_EXIT` and include the specific failing criterion name in the exit reason detail.
3. WHEN a position is held overnight, THE Position_Manager SHALL log a position event with event type `overnight_hold` containing: position ID, ticker, option symbol, expiration date, entry price, current price, P&L percentage at hold time, DTE at hold time, and the overnight hold criteria snapshot (all parameter names, observed values, and thresholds).
4. THE EOD_Exit_Engine SHALL record the next-day opening P&L for positions held overnight by logging a position event with event type `overnight_outcome` on the next trading day containing: position ID, close price at previous EOD, open price next day, overnight P&L percentage, and overnight P&L dollars.
5. WHEN the trade analyzer runs, THE trade_analyzer SHALL query `position_events` for `eod_decision` and `overnight_outcome` events to compute overnight hold win rate, average overnight P&L, and per-criterion pass rates, and generate `learning_recommendations` for overnight hold threshold adjustments.

### Requirement 7: Account-Specific EOD Behavior

**User Story:** As a trader running two accounts (large ~$121K, tiny ~$1K), I want EOD behavior tuned per account, so that the tiny account uses tighter risk controls while the large account can take more measured overnight positions.

#### Acceptance Criteria

1. THE EOD_Exit_Engine SHALL load account-specific EOD configuration from the account-tier-specific SSM parameter (`/ops-pipeline/dispatcher_config_{account_tier}`).
2. WHEN the account tier is `tiny`, THE EOD_Exit_Engine SHALL use a lower default `max_overnight_option_exposure` (default 200.0 dollars) compared to the large account (default 5000.0 dollars).
3. WHEN the account tier is `tiny`, THE SSM_Config SHALL default `min_pnl_pct_for_overnight` to 15.0 (higher bar for overnight holds on small accounts).
4. WHEN the account tier is `tiny`, THE Entry_Cutoff_Gate SHALL default `last_entry_hour_et_day_trade` to 13 (1 PM ET) and `last_entry_hour_et_swing_trade` to 14 (2 PM ET), giving positions more time to play out before close.
5. THE Position_Manager SHALL identify its account tier from the `ACCOUNT_NAME` environment variable and apply the corresponding default configuration.

### Requirement 8: After-Hours Trade Prevention

**User Story:** As a trader, I want the system to enforce market hours strictly for both accounts, so that no positions are opened outside regular trading hours (9:30 AM - 4:00 PM ET).

#### Acceptance Criteria

1. WHEN the current time is outside regular market hours (before 9:30 AM ET or at/after 4:00 PM ET), THE Entry_Cutoff_Gate SHALL block all new position entries regardless of account or strategy type.
2. WHEN the Entry_Cutoff_Gate blocks a signal due to after-hours timing, THE Dispatcher SHALL log the blocked signal with the current time and the reason `outside_market_hours`.
3. THE Entry_Cutoff_Gate SHALL use timezone-aware datetime comparisons in US/Eastern timezone to prevent UTC offset errors.
4. WHEN the Dispatcher processes a signal, THE Dispatcher SHALL verify the ticker does not already have an open or closing position in the same account before opening a new position.
5. WHEN a duplicate position is detected for the same ticker, account, and instrument type, THE Dispatcher SHALL block the signal and log the reason `duplicate_position_blocked`.

### Requirement 9: SSM Configuration Serialization

**User Story:** As a developer, I want all EOD-related configuration to be stored as valid JSON in SSM Parameter Store, so that configuration is machine-parseable and consistent with the rest of the system.

#### Acceptance Criteria

1. THE Position_Manager SHALL parse EOD configuration from SSM_Config using JSON deserialization.
2. THE Position_Manager SHALL serialize EOD configuration to SSM_Config using JSON serialization.
3. FOR ALL valid EOD configuration objects, serializing then deserializing SHALL produce an equivalent configuration object (round-trip property).
4. IF the SSM_Config value is not valid JSON, THEN THE Position_Manager SHALL log an error and fall back to default configuration values.


### Requirement 10: Theta-Weighted Exit Scoring

**User Story:** As a trader, I want the EOD exit engine to factor theta decay rate into close decisions, so that positions with high theta burn are closed more aggressively while positions with low theta decay get more room to run.

#### Acceptance Criteria

1. WHEN the EOD_Exit_Engine evaluates a position for exit, THE EOD_Exit_Engine SHALL compute a Theta_Score by dividing the absolute value of the position's theta greek by the current option premium (entry-time theta from `dispatch_executions` or live theta from the Alpaca options snapshot API).
2. WHEN a position's Theta_Score exceeds a configurable `high_theta_threshold` (default 0.05 representing 5% daily premium decay), THE EOD_Exit_Engine SHALL lower the minimum P&L threshold required for overnight hold by a configurable `theta_pnl_penalty_pct` (default 10.0 percentage points).
3. WHEN a position has DTE less than or equal to 2 AND a Theta_Score above `high_theta_threshold`, THE EOD_Exit_Engine SHALL force-close the position regardless of P&L.
4. THE SSM_Config SHALL contain `high_theta_threshold` (float, default 0.05) and `theta_pnl_penalty_pct` (float, default 10.0) parameters.
5. IF the theta greek value is unavailable or null for a position, THEN THE EOD_Exit_Engine SHALL treat the position as having maximum theta risk and apply the penalty.

### Requirement 11: VIX-Aware Overnight Hold Criteria

**User Story:** As a trader, I want overnight hold thresholds to adjust dynamically based on the current VIX regime, so that the system applies tighter criteria in high-volatility environments and looser criteria in low-volatility environments.

#### Acceptance Criteria

1. WHEN the EOD_Exit_Engine evaluates overnight hold criteria, THE EOD_Exit_Engine SHALL query the latest VIX_Regime from the `vix_history` table.
2. WHEN the VIX_Regime is `elevated` (VIX 20-30), THE EOD_Exit_Engine SHALL multiply the `min_pnl_pct_for_overnight` threshold by a configurable `vix_elevated_multiplier` (default 1.5).
3. WHEN the VIX_Regime is `high` (VIX 30-40), THE EOD_Exit_Engine SHALL multiply the `min_pnl_pct_for_overnight` threshold by a configurable `vix_high_multiplier` (default 2.0) AND reduce `max_overnight_option_exposure` by 50%.
4. WHEN the VIX_Regime is `extreme` (VIX above 40), THE EOD_Exit_Engine SHALL force-close all option positions before market close regardless of strategy type or P&L.
5. WHEN the VIX_Regime is `complacent` or `normal` (VIX below 20), THE EOD_Exit_Engine SHALL use the base overnight hold thresholds without adjustment.
6. THE SSM_Config SHALL contain `vix_elevated_multiplier` (float, default 1.5) and `vix_high_multiplier` (float, default 2.0) parameters.
7. IF the VIX_Regime data is unavailable or stale (older than 24 hours), THEN THE EOD_Exit_Engine SHALL apply the `elevated` regime multipliers as a conservative fallback.

### Requirement 12: Earnings Calendar Integration

**User Story:** As a trader, I want the system to check if a ticker has an upcoming earnings announcement, so that positions are force-closed before earnings to avoid gap risk from post-earnings price moves.

#### Acceptance Criteria

1. WHEN the EOD_Exit_Engine evaluates a position for overnight hold, THE EOD_Exit_Engine SHALL check the Earnings_Calendar_Provider for the position's ticker to determine if earnings are scheduled within the next 1 trading day.
2. WHEN a ticker has earnings scheduled after market close today, THE EOD_Exit_Engine SHALL force-close all positions in that ticker before market close regardless of P&L or overnight hold criteria.
3. WHEN a ticker has earnings scheduled before market open on the next trading day, THE EOD_Exit_Engine SHALL force-close all positions in that ticker before market close regardless of P&L or overnight hold criteria.
4. WHEN the EOD_Exit_Engine force-closes a position due to earnings, THE Position_Manager SHALL log a position event with event type `eod_decision` containing `earnings_close` as the decision reason, the earnings date, and the earnings timing (before open or after close).
5. THE EOD_Exit_Engine SHALL cache earnings calendar data for the current trading day to avoid repeated API calls during each monitoring cycle.
6. IF the Earnings_Calendar_Provider is unavailable or returns an error, THEN THE EOD_Exit_Engine SHALL log a warning and proceed with normal overnight hold evaluation without earnings data.

### Requirement 13: Graduated Close Timing

**User Story:** As a trader, I want positions evaluated at multiple time windows with increasingly strict criteria, so that the system can capture more profit on strong positions while still ensuring all positions are resolved before market close.

#### Acceptance Criteria

1. THE EOD_Exit_Engine SHALL evaluate open option positions at configurable Graduated_Close_Windows (default: 14:30, 15:00, 15:30, 15:55 ET).
2. WHEN the first Graduated_Close_Window is reached (default 14:30 ET), THE EOD_Exit_Engine SHALL close day trade positions with unrealized loss exceeding a configurable `window_1_max_loss_pct` (default -20.0%).
3. WHEN the second Graduated_Close_Window is reached (default 15:00 ET), THE EOD_Exit_Engine SHALL close day trade positions with unrealized loss exceeding a configurable `window_2_max_loss_pct` (default -10.0%) AND swing trade positions failing overnight hold criteria by more than one criterion.
4. WHEN the third Graduated_Close_Window is reached (default 15:30 ET), THE EOD_Exit_Engine SHALL close all day trade positions with any unrealized loss AND swing trade positions failing any single overnight hold criterion.
5. WHEN the final Graduated_Close_Window is reached (default 15:55 ET), THE EOD_Exit_Engine SHALL close all remaining day trade positions AND all swing trade positions that do not meet every overnight hold criterion.
6. THE SSM_Config SHALL contain `graduated_close_windows` (JSON array of time strings in HH:MM format, default ["14:30", "15:00", "15:30", "15:55"]) and per-window loss thresholds `window_1_max_loss_pct` (default -20.0), `window_2_max_loss_pct` (default -10.0).
7. WHEN a position is closed at a Graduated_Close_Window, THE Position_Manager SHALL log the window time, the criteria applied at that window, and the specific criterion that triggered the close.
8. THE EOD_Exit_Engine SHALL compute a Close_Urgency_Score for each position at each window, combining P&L, DTE, Theta_Score, and time remaining, to prioritize which positions to close first when multiple positions trigger at the same window.


### Requirement 14: Position Close-Loop Integrity

**User Story:** As a trader, I want the system to detect and recover from stuck closing attempts, so that positions do not remain in a `closing` state indefinitely and duplicate positions are not created for the same ticker.

#### Acceptance Criteria

1. WHEN the Position_Manager detects a position with `status=closing` for longer than a configurable `max_closing_duration_minutes` (default 5), THE Position_Manager SHALL retry the close order once and log a position event with event type `close_retry`.
2. WHEN a close retry fails, THE Position_Manager SHALL log a position event with event type `close_failed` containing the error details and mark the position for manual review.
3. WHEN the Position_Manager starts a monitoring cycle, THE Position_Manager SHALL skip positions that are already in `status=closing` from new exit evaluations to prevent duplicate close attempts.
4. WHEN the market is closed AND positions exist with `status=closing`, THE Position_Manager SHALL not attempt to execute close orders and SHALL queue them for the next market open.
5. THE Position_Manager SHALL enforce a maximum of one open or closing position per ticker per account per instrument type, rejecting any sync or creation that would create a duplicate.
6. THE SSM_Config SHALL contain `max_closing_duration_minutes` (integer, default 5) parameter.
7. WHEN the Position_Manager detects more than a configurable `max_positions_per_ticker` (default 3) open positions for the same ticker in the same account, THE Position_Manager SHALL log a critical alert and close all but the most recent position.
