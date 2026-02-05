BEGIN;

-- ============================================================
-- 2026_02_02_0001_position_telemetry.sql
-- Adds execution_uuid bridge + entry telemetry + position_history
-- No behavior changes; schema only.
-- Postgres assumed.
-- ============================================================

-- ----------------------------
-- 1) active_positions additions
-- ----------------------------

ALTER TABLE IF EXISTS active_positions
  ADD COLUMN IF NOT EXISTS execution_uuid UUID;

ALTER TABLE IF EXISTS active_positions
  ADD COLUMN IF NOT EXISTS entry_features_json JSONB;

ALTER TABLE IF EXISTS active_positions
  ADD COLUMN IF NOT EXISTS entry_iv_rank NUMERIC(18,8);

ALTER TABLE IF EXISTS active_positions
  ADD COLUMN IF NOT EXISTS entry_spread_pct NUMERIC(18,8);

ALTER TABLE IF EXISTS active_positions
  ADD COLUMN IF NOT EXISTS best_unrealized_pnl_pct NUMERIC(18,8);

ALTER TABLE IF EXISTS active_positions
  ADD COLUMN IF NOT EXISTS worst_unrealized_pnl_pct NUMERIC(18,8);

ALTER TABLE IF EXISTS active_positions
  ADD COLUMN IF NOT EXISTS best_unrealized_pnl_dollars NUMERIC(18,8);

ALTER TABLE IF EXISTS active_positions
  ADD COLUMN IF NOT EXISTS worst_unrealized_pnl_dollars NUMERIC(18,8);

ALTER TABLE IF EXISTS active_positions
  ADD COLUMN IF NOT EXISTS last_mark_price NUMERIC(18,8);

ALTER TABLE IF EXISTS active_positions
  ADD COLUMN IF NOT EXISTS strategy_type TEXT;

ALTER TABLE IF EXISTS active_positions
  ADD COLUMN IF NOT EXISTS side TEXT;

ALTER TABLE IF EXISTS active_positions
  ADD COLUMN IF NOT EXISTS status TEXT;

-- Set defaults AFTER column exists (safer across PG versions)
ALTER TABLE IF EXISTS active_positions
  ALTER COLUMN best_unrealized_pnl_pct SET DEFAULT 0;

ALTER TABLE IF EXISTS active_positions
  ALTER COLUMN worst_unrealized_pnl_pct SET DEFAULT 0;

ALTER TABLE IF EXISTS active_positions
  ALTER COLUMN best_unrealized_pnl_dollars SET DEFAULT 0;

ALTER TABLE IF EXISTS active_positions
  ALTER COLUMN worst_unrealized_pnl_dollars SET DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_active_positions_execution_uuid
  ON active_positions (execution_uuid);

-- ----------------------------
-- 2) position_history table
-- ----------------------------
CREATE TABLE IF NOT EXISTS position_history (
  id BIGSERIAL PRIMARY KEY,

  execution_id UUID,
  execution_uuid UUID,

  ticker TEXT,
  instrument_type TEXT,
  strategy_type TEXT,

  side TEXT,
  quantity NUMERIC(18,8),
  entry_price NUMERIC(18,8),
  exit_price NUMERIC(18,8),

  entry_time TIMESTAMPTZ,
  exit_time TIMESTAMPTZ,

  pnl_dollars NUMERIC(18,8),
  pnl_pct NUMERIC(18,8),

  strike_price NUMERIC(18,8),
  expiration_date DATE,

  option_symbol TEXT,
  implied_volatility NUMERIC(18,8),

  max_hold_minutes INTEGER,
  holding_seconds INTEGER,
  multiplier INTEGER,

  exit_reason TEXT,
  exit_order_id TEXT,

  entry_features_json JSONB,
  entry_iv_rank NUMERIC(18,8),
  entry_spread_pct NUMERIC(18,8),

  best_unrealized_pnl_pct NUMERIC(18,8),
  worst_unrealized_pnl_pct NUMERIC(18,8),
  best_unrealized_pnl_dollars NUMERIC(18,8),
  worst_unrealized_pnl_dollars NUMERIC(18,8),

  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_position_history_execution_uuid
  ON position_history (execution_uuid);

CREATE INDEX IF NOT EXISTS idx_position_history_ticker_exit_time
  ON position_history (ticker, exit_time DESC);

-- ----------------------------
-- 3) Constraints (NOT VALID)
--     - canonical strategy_type: day_trade|swing_trade|stock
--     - side allows: long|short|call|put
-- ----------------------------

DO $$
BEGIN
  -- position_history.strategy_type
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'chk_position_history_strategy_type'
  ) THEN
    ALTER TABLE position_history
      ADD CONSTRAINT chk_position_history_strategy_type
      CHECK (strategy_type IS NULL OR strategy_type IN ('day_trade','swing_trade','stock'))
      NOT VALID;
  END IF;

  -- position_history.side
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'chk_position_history_side'
  ) THEN
    ALTER TABLE position_history
      ADD CONSTRAINT chk_position_history_side
      CHECK (side IS NULL OR side IN ('long','short','call','put'))
      NOT VALID;
  END IF;

  -- active_positions.strategy_type
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'chk_active_positions_strategy_type'
  ) THEN
    ALTER TABLE active_positions
      ADD CONSTRAINT chk_active_positions_strategy_type
      CHECK (strategy_type IS NULL OR strategy_type IN ('day_trade','swing_trade','stock'))
      NOT VALID;
  END IF;

  -- active_positions.side
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'chk_active_positions_side'
  ) THEN
    ALTER TABLE active_positions
      ADD CONSTRAINT chk_active_positions_side
      CHECK (side IS NULL OR side IN ('long','short','call','put'))
      NOT VALID;
  END IF;

  -- strategy_stats.strategy_type (only if table exists)
  IF EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'strategy_stats'
  ) THEN
    IF NOT EXISTS (
      SELECT 1 FROM pg_constraint
      WHERE conname = 'chk_strategy_stats_strategy_type'
    ) THEN
      ALTER TABLE strategy_stats
        ADD CONSTRAINT chk_strategy_stats_strategy_type
        CHECK (strategy_type IS NULL OR strategy_type IN ('day_trade','swing_trade','stock'))
        NOT VALID;
    END IF;
  END IF;
END
$$;

COMMIT;

-- ============================================================
-- OPTIONAL (run later when ready)
--
-- ALTER TABLE active_positions VALIDATE CONSTRAINT chk_active_positions_side;
-- ALTER TABLE active_positions VALIDATE CONSTRAINT chk_active_positions_strategy_type;
-- ALTER TABLE position_history VALIDATE CONSTRAINT chk_position_history_side;
-- ALTER TABLE position_history VALIDATE CONSTRAINT chk_position_history_strategy_type;
-- ALTER TABLE strategy_stats VALIDATE CONSTRAINT chk_strategy_stats_strategy_type;
-- ============================================================
