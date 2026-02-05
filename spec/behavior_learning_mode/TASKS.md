# Behavior Learning Mode — Tasks

## Phase 1: Database Schema & Migration
- [x] Confirm DB engine = PostgreSQL (expected)
- [x] Apply database migration `2026_02_02_0001_position_telemetry.sql`
  - [x] 1.1 Create migration status check script (`check_migration_status.py`)
  - [x] 1.2 Run migration status check (Result: NOT applied, missing execution_uuid & position_history)
  - [x] 1.3 Apply migration via Lambda or ECS task
    - **Solution:** Added migration to db-migration Lambda MIGRATIONS dict
    - **Deployed:** Lambda updated with migration 2026_02_02_0001_position_telemetry
    - **Applied:** Migration successfully applied at 2026-02-02 23:07:14 UTC
  - [x] 1.4 Verify migration success
    - **Verified:** All 12 columns added to active_positions
    - **Verified:** position_history table created with 31 columns
    - **Verified:** Migration recorded in schema_migrations

## Phase 2: Telemetry Implementation (Already Done)
- [x] Implement MFE/MAE tracking in `position_manager/monitor.py` (in‑memory per open position)
- [x] Persist final outcomes to `position_history` on close (in `exits.py` or close path)
- [x] Add execution_uuid bridge in position creation

## Phase 3: Bug Fixes & Hardening
- [x] Fix entry features capture bug in `position_manager/db.py`
  - [x] 3.1 Verify features_snapshot field name in dispatch tables
    - **Verified:** Field exists in dispatch_recommendations table
    - **Verified:** JOIN correctly pulls dr.features_snapshot as entry_features_json
  - [x] 3.2 Update create_active_position() to capture features
    - **Status:** Already implemented correctly in db.py line 68
    - **Note:** Features captured from dispatch_recommendations.features_snapshot
  - [x] 3.3 Rebuild and redeploy position-manager service
    - **Status:** No changes needed - already correct
  - [x] 3.4 Verify features are captured in new positions
    - **Status:** Will verify after next position creation
- [x] Implement websocket idempotency
  - [x] 3.5 Create alpaca_event_dedupe table migration
    - **Created:** db/migrations/2026_02_02_0002_websocket_idempotency.sql
  - [x] 3.6 Add partial unique index on active_positions.execution_uuid
    - **Added:** idx_active_positions_execution_uuid_unique (WHERE NOT NULL)
  - [x] 3.7 Add dedupe check in trade_stream/main.py
    - **Added:** check_event_processed() before position creation
  - [x] 3.8 Update create_position_from_alpaca() to use UPSERT pattern
    - **Added:** create_position_from_alpaca_with_order_id() with order_id tracking
    - **Added:** get_position_by_order_id() for duplicate detection
  - [x] 3.9 Fix production foot-guns
    - [x] Fix false success reporting in migration scripts
      - **Fixed:** apply_behavior_learning_migration.py
      - **Fixed:** apply_phase3_migration.py
      - **Created:** apply_constraints_migration.py (with correct pattern)
    - [x] Re-add missing constraints without DO blocks
      - **Created:** db/migrations/2026_02_02_0003_add_constraints_no_do.sql
      - **Adds:** chk_active_positions_side, chk_active_positions_strategy_type
      - **Adds:** chk_position_history_side, chk_position_history_strategy_type
    - [x] Update Lambda with new migrations
      - **Updated:** services/db_migration_lambda/lambda_function.py
      - **Added:** 2026_02_02_0002_websocket_idempotency to MIGRATIONS dict
      - **Added:** 2026_02_02_0003_add_constraints_no_do to MIGRATIONS dict
  - [-] 3.10 Deploy Phase 3 complete
    - [ ] Rebuild and redeploy db-migration Lambda
    - [ ] Apply Phase 3 migration (2026_02_02_0002_websocket_idempotency)
    - [ ] Apply constraints migration (2026_02_02_0003_add_constraints_no_do)
    - [ ] Rebuild and redeploy trade-stream service
    - [ ] Verify no duplicate positions created
  - [ ] 3.11 Test with duplicate event scenarios

## Phase 4: Nightly Statistics
- [ ] Schedule nightly stats job
  - [ ] 4.1 Review learning_stats_job scaffold
  - [ ] 4.2 Verify compute_strategy_stats.sql completeness
  - [ ] 4.3 Create ECS task definition or Lambda
  - [ ] 4.4 Create EventBridge schedule (daily 2 AM UTC)
  - [ ] 4.5 Test manual execution
  - [ ] 4.6 Verify strategy_stats population

## Phase 5: Data Quality & Validation
- [ ] Normalize exit reasons to fixed label set
- [ ] Add validation checks (MFE/MAE bounds, monotonic percentiles, non‑null entry_features_json)

## Phase 6: Documentation
- [ ] Update docs: `SYSTEM_BEHAVIOR_AUDIT.md`, `spec/system_change_template/CURRENT_STATE.md` if behavior changes
- [ ] Record results in `CURRENT_SYSTEM_STATUS.md`

