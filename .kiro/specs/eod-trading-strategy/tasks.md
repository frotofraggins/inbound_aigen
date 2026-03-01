# Implementation Plan: EOD Trading Strategy

## Overview

Replace the blanket 3:55 PM force-close with a strategy-aware, P&L-aware, configurable EOD exit engine. Implementation proceeds bottom-up: config/data models first, then core engine components (theta, VIX, earnings, graduated windows, close-loop), then integration into the existing Position Manager and Dispatcher services. All 14 requirements (R1-R14) are covered.

## Tasks

- [x] 1. EOD Config and Data Models
  - [x] 1.1 Create `services/position_manager/eod_config.py` with `EODConfig` dataclass
    - Implement `from_ssm()`, `to_dict()`, `from_dict()` with default fallbacks for missing/invalid params
    - Include all parameters: overnight hold, theta, VIX, graduated windows, close-loop
    - Account-tier defaults (tiny vs large) via `for_account_tier()` class method
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 7.1, 7.2, 7.3, 7.4, 9.1, 9.2_

  - [ ]* 1.2 Write property tests for EODConfig serialization round-trip and default fallbacks
    - **Property 9: EODConfig serialization round-trip**
    - **Property 5: Missing or invalid SSM parameters fall back to defaults**
    - **Validates: Requirements 3.3, 3.4, 9.1, 9.2, 9.3, 9.4**

  - [x] 1.3 Create data model classes in `services/position_manager/eod_models.py`
    - `EODDecision`, `CriterionResult`, `VIXRegime`, `OvernightCriteria`, `EarningsInfo`, `GraduatedWindowCriteria`, `CloseAction`
    - `EODDecision.to_event_payload()` serialization
    - `OvernightCriteria.evaluate()` method
    - `VIXRegime.is_stale` and `effective_regime` properties
    - _Requirements: 6.1, 6.3, 11.1_

- [x] 2. Theta Scoring
  - [x] 2.1 Implement `compute_theta_score()` in `services/position_manager/eod_engine.py`
    - `abs(theta) / premium`, fallback to 1.0 if theta or premium is null/zero
    - Implement `apply_theta_adjustments()` — lower P&L threshold by `theta_pnl_penalty_pct` when score > `high_theta_threshold`
    - Force-close logic when DTE ≤ 2 and high theta
    - _Requirements: 10.1, 10.2, 10.3, 10.5_

  - [x] 2.2 Write property tests for theta scoring
    - **Property 10: Theta score computation and threshold adjustment**
    - **Property 11: High theta + low DTE forces close**
    - **Validates: Requirements 10.1, 10.2, 10.3, 10.5**

- [x] 3. VIX Regime Adjustment
  - [x] 3.1 Implement `get_vix_regime()` and `apply_vix_adjustments()` in `eod_engine.py`
    - Query latest VIX regime from `vix_history` table
    - Apply multipliers: elevated → P&L × `vix_elevated_multiplier`, high → P&L × `vix_high_multiplier` + exposure ÷ 2, extreme → force-close all
    - Stale/unavailable data → fallback to `elevated`
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.7_

  - [x] 3.2 Write property tests for VIX regime adjustments
    - **Property 12: VIX regime adjusts overnight criteria correctly**
    - **Validates: Requirements 11.2, 11.3, 11.4, 11.5, 11.7**

- [x] 4. Earnings Calendar Client
  - [x] 4.1 Create `services/position_manager/earnings_client.py`
    - `EarningsCalendarClient` with `has_upcoming_earnings(ticker)` method
    - Query Alpaca corporate actions API for earnings within 1 trading day
    - Per-trading-day cache with `invalidate_cache()`
    - Graceful degradation: log warning and return None on API failure
    - _Requirements: 12.1, 12.2, 12.3, 12.5, 12.6_

  - [x] 4.2 Write unit tests for earnings client
    - Test after-close earnings detection, before-open earnings detection
    - Test cache behavior (same-day cache hit, next-day invalidation)
    - Test API failure graceful degradation
    - _Requirements: 12.1, 12.2, 12.3, 12.5, 12.6_

- [x] 5. Checkpoint — Core components
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Graduated Close Windows
  - [x] 6.1 Implement graduated window evaluation in `eod_engine.py`
    - `get_current_window()` — determine which window index applies based on current ET time
    - `evaluate_at_window()` — apply window-specific criteria (loss thresholds per window, progressively stricter)
    - Window 0: close day trades with loss > `window_1_max_loss_pct`
    - Window 1: close day trades with loss > `window_2_max_loss_pct`, swing trades failing >1 criterion
    - Window 2: close all losing day trades, swing trades failing any criterion
    - Window 3: close all remaining day trades, all non-qualifying swing trades
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5_

  - [x] 6.2 Implement `compute_close_urgency()` in `eod_engine.py`
    - Composite score from P&L (inverted), DTE (inverted), theta_score, minutes_to_close (inverted)
    - Used to prioritize which positions close first at each window
    - _Requirements: 13.8_

  - [ ]* 6.3 Write property tests for graduated windows and urgency scoring
    - **Property 14: Graduated window criteria are monotonically stricter**
    - **Property 15: Close urgency score orders positions correctly**
    - **Validates: Requirements 13.2, 13.3, 13.4, 13.5, 13.8**

- [x] 7. Close-Loop Monitor
  - [x] 7.1 Create `services/position_manager/close_loop.py`
    - `CloseLoopMonitor` with `check_stuck_positions()` — detect positions in `closing` > `max_closing_duration_minutes`
    - `detect_duplicates()` — find duplicate positions per (ticker, account, instrument_type)
    - `is_market_open()` — check 9:30-16:00 ET
    - Retry logic: one retry for stuck positions, log `close_retry` / `close_failed` events
    - Market-closed queuing: skip execution, queue for next open
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.7_

  - [x] 7.2 Write property tests for close-loop monitor
    - **Property 16: Stuck closing positions are retried then skipped**
    - **Property 17: One position per ticker per account invariant**
    - **Property 18: Market-closed positions are not executed**
    - **Validates: Requirements 14.1, 14.3, 14.4, 14.5, 14.7**

- [x] 8. EOD Exit Engine — Core Orchestrator
  - [x] 8.1 Create `EODExitEngine` class in `services/position_manager/eod_engine.py`
    - `__init__` with EODConfig, account_tier, earnings_cache, vix_regime
    - `evaluate_position()` — main decision flow per position per window:
      1. Skip if `status=closing` (R14.3)
      2. Check earnings → force close (R12)
      3. Check VIX extreme → force close all (R11.4)
      4. Compute theta score (R10)
      5. Route by strategy_type (R1): day_trade → window criteria, swing_trade → overnight eval, unknown → day_trade
      6. For swing: apply VIX adjustments (R11), theta adjustments (R10), evaluate overnight criteria (R3)
      7. Check aggregate exposure limit (R5)
    - `evaluate_all_positions()` — iterate positions, compute urgency scores, order closes
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 5.1, 5.2, 5.5_

  - [x] 8.2 Implement overnight exposure limit enforcement
    - After individual position evaluation, sum notional of qualifying holds
    - If over limit, close least profitable first until within limit
    - Log exposure before/after
    - _Requirements: 5.1, 5.2, 5.4, 5.5_

  - [x] 8.3 Write property tests for EOD exit engine core logic
    - **Property 1: Day trade positions are always closed at final window**
    - **Property 2: Swing trade hold decision is equivalent to passing all overnight criteria**
    - **Property 3: Day trade close timing depends on P&L**
    - **Property 7: Overnight exposure limit closes least profitable first**
    - **Validates: Requirements 1.1, 1.3, 1.4, 1.5, 2.1, 2.3, 5.1, 5.2, 13.5**

  - [ ]* 8.4 Write property test for EOD decision event completeness
    - **Property 4: EOD decision events contain all required fields**
    - **Validates: Requirements 2.4, 6.1, 6.2, 6.3**

- [x] 9. Checkpoint — Engine complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. Integrate into Position Manager
  - [x] 10.1 Modify `services/position_manager/monitor.py`
    - Replace `market_close_protection` block in `check_time_based_exits()` with call to `EODExitEngine.evaluate_position()`
    - Initialize `EODExitEngine` at start of monitoring cycle with fresh config, VIX regime, earnings cache
    - Wire `CloseLoopMonitor` into the monitoring cycle (check stuck positions before exit evaluation)
    - Log `eod_decision`, `overnight_hold` events to `position_events` table
    - Set `exit_reason_norm = 'EOD_EXIT'` with detail on close
    - _Requirements: 1.1, 1.2, 2.4, 6.1, 6.2, 6.3, 6.4, 13.7, 14.1, 14.3_

  - [x] 10.2 Modify `services/position_manager/config.py`
    - Load EOD config from account-tier-specific SSM parameter
    - Replace `DAY_TRADE_CLOSE_TIME` constant with graduated window config
    - Add `ACCOUNT_TIER` derived from `ACCOUNT_NAME`
    - _Requirements: 3.1, 7.1, 7.5_

  - [ ] 10.3 Write unit tests for Position Manager integration
    - Test monitoring cycle with mixed position types (day/swing/unknown)
    - Test event logging to position_events
    - Test close-loop recovery during monitoring cycle
    - _Requirements: 1.1, 1.5, 6.1, 14.1, 14.3_

- [ ] 11. Integrate into Dispatcher
  - [x] 11.1 Modify `services/dispatcher/risk/gates.py`
    - Update `check_trading_hours()` → `check_trading_hours_v2()` with strategy-specific cutoffs
    - Add `check_duplicate_position()` gate
    - Wire both into `evaluate_all_gates()`
    - _Requirements: 4.1, 4.2, 4.3, 4.5, 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ]* 11.2 Write property tests for entry gates
    - **Property 6: Strategy-specific entry cutoff gate**
    - **Property 8: After-hours and duplicate position blocking**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.5, 8.1, 8.2, 8.4, 8.5**

  - [x] 11.3 Modify `services/dispatcher/config.py`
    - Add `last_entry_hour_et_day_trade` and `last_entry_hour_et_swing_trade` to config loading
    - Account-tier defaults for tiny account
    - _Requirements: 4.4, 7.4_

- [ ] 12. Overnight Outcome Logging
  - [x] 12.1 Add `overnight_outcome` event logging to Position Manager
    - On first monitoring cycle of each trading day, query positions held overnight
    - Compare previous EOD price to current open price
    - Log `overnight_outcome` event with overnight P&L
    - _Requirements: 6.4_

  - [ ] 12.2 Write unit tests for overnight outcome logging
    - Test overnight P&L calculation with known price pairs
    - Test that only positions held overnight get outcome events
    - _Requirements: 6.4_

- [ ] 13. Account-Tier Configuration
  - [x] 13.1 Update SSM parameter defaults for tiny account tier
    - `max_overnight_option_exposure`: 200.0
    - `min_pnl_pct_for_overnight`: 15.0
    - `last_entry_hour_et_day_trade`: 13
    - `last_entry_hour_et_swing_trade`: 14
    - Ensure `EODConfig.for_account_tier('tiny')` applies these defaults
    - _Requirements: 7.2, 7.3, 7.4_

  - [ ] 13.2 Write unit tests for account-tier configuration
    - Test tiny vs large default values
    - Test SSM override of tier defaults
    - _Requirements: 7.2, 7.3, 7.4, 7.5_

- [x] 14. Final checkpoint — Full integration
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples, edge cases, and integration points
- Checkpoints at tasks 5, 9, and 14 ensure incremental validation
- The existing `market_close_protection` block in `check_time_based_exits()` is replaced in task 10.1
