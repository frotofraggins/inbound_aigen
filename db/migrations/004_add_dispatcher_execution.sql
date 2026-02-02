-- Migration 004: Add Dispatcher Execution Tables and Status Fields
-- Adds production-grade execution tracking with idempotency guarantees

-- 1. Add status and processing fields to dispatch_recommendations
ALTER TABLE dispatch_recommendations
  ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'PENDING',
  ADD COLUMN IF NOT EXISTS processed_at TIMESTAMPTZ NULL,
  ADD COLUMN IF NOT EXISTS dispatcher_run_id UUID NULL,
  ADD COLUMN IF NOT EXISTS failure_reason TEXT NULL,
  ADD COLUMN IF NOT EXISTS risk_gate_json JSONB NULL;

-- Index for efficient polling of pending recommendations
CREATE INDEX IF NOT EXISTS idx_dispatch_reco_pending
  ON dispatch_recommendations (status, ts)
  WHERE status = 'PENDING';

-- Index for finding recommendations by run
CREATE INDEX IF NOT EXISTS idx_dispatch_reco_run
  ON dispatch_recommendations (dispatcher_run_id)
  WHERE dispatcher_run_id IS NOT NULL;

-- 2. Create immutable execution ledger
CREATE TABLE IF NOT EXISTS dispatch_executions (
  execution_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  recommendation_id BIGINT NOT NULL REFERENCES dispatch_recommendations(id),
  dispatcher_run_id UUID NOT NULL,
  ticker            TEXT NOT NULL,
  action            TEXT NOT NULL, -- BUY_CALL|BUY_PUT|BUY_STOCK|SELL_PREMIUM
  decision_ts       TIMESTAMPTZ NOT NULL, -- from recommendation created_at
  simulated_ts      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  -- Simulation pricing and sizing
  entry_price       NUMERIC(18,8) NOT NULL,
  fill_model        TEXT NOT NULL, -- e.g., "mid+slip_bps", "close+slip"
  slippage_bps      INT NOT NULL DEFAULT 0,
  qty               NUMERIC(18,8) NOT NULL,
  notional          NUMERIC(18,8) NOT NULL,
  
  -- Risk controls output
  stop_loss_price   NUMERIC(18,8) NULL,
  take_profit_price NUMERIC(18,8) NULL,
  max_hold_minutes  INT NULL,
  
  -- Execution mode
  execution_mode    TEXT NOT NULL DEFAULT 'SIMULATED', -- SIMULATED | REAL
  
  -- Traceability (JSONB for flexibility)
  explain_json      JSONB NOT NULL,  -- copy of recommendation reasoning
  risk_json         JSONB NOT NULL,  -- gates + sizing rationale
  sim_json          JSONB NOT NULL   -- telemetry used + assumptions
);

-- CRITICAL: Idempotency constraint - exactly one execution per recommendation
CREATE UNIQUE INDEX IF NOT EXISTS ux_dispatch_execution_reco
  ON dispatch_executions (recommendation_id);

-- Index for querying executions by run
CREATE INDEX IF NOT EXISTS idx_dispatch_exec_run
  ON dispatch_executions (dispatcher_run_id);

-- Index for querying executions by ticker
CREATE INDEX IF NOT EXISTS idx_dispatch_exec_ticker
  ON dispatch_executions (ticker, simulated_ts DESC);

-- Index for time-based queries
CREATE INDEX IF NOT EXISTS idx_dispatch_exec_time
  ON dispatch_executions (simulated_ts DESC);

-- 3. Create dispatcher run tracking table (operational visibility)
CREATE TABLE IF NOT EXISTS dispatcher_runs (
  run_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  started_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  finished_at    TIMESTAMPTZ NULL,
  pulled_count   INT NOT NULL DEFAULT 0,
  processed_count INT NOT NULL DEFAULT 0,
  simulated_count INT NOT NULL DEFAULT 0,
  skipped_count  INT NOT NULL DEFAULT 0,
  failed_count   INT NOT NULL DEFAULT 0,
  run_config_json JSONB NULL,
  run_summary_json JSONB NULL
);

-- Index for finding recent runs
CREATE INDEX IF NOT EXISTS idx_dispatcher_runs_time
  ON dispatcher_runs (started_at DESC);

-- 4. Add comments for documentation
COMMENT ON TABLE dispatch_executions IS 
  'Immutable ledger of simulated and real trade executions. One row per recommendation, enforced by unique constraint.';

COMMENT ON COLUMN dispatch_executions.execution_mode IS 
  'SIMULATED for Phase 9 dry-run, REAL for future live trading';

COMMENT ON COLUMN dispatch_recommendations.status IS 
  'State machine: PENDING → PROCESSING → (SKIPPED | SIMULATED | FAILED)';

COMMENT ON TABLE dispatcher_runs IS 
  'Operational tracking of dispatcher invocations for monitoring and debugging';
