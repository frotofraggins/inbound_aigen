-- Draft migration: Behavior Learning Mode
-- NOTE: Draft only. Review FK types against live schema before applying.

BEGIN;

-- 1) position_history (raw outcomes)
CREATE TABLE IF NOT EXISTS position_history (
    id BIGSERIAL PRIMARY KEY,
    position_id BIGINT NULL,
    execution_id UUID NULL,
    ticker TEXT NOT NULL,
    instrument_symbol TEXT NULL, -- actual traded symbol (option contract or stock)
    strategy_type TEXT NULL,
    asset_type TEXT NOT NULL, -- stock|option
    side TEXT NULL,           -- long|call|put
    qty NUMERIC(18,8) NOT NULL,
    multiplier INT NOT NULL DEFAULT 1,
    entry_ts TIMESTAMPTZ NOT NULL,
    exit_ts TIMESTAMPTZ NOT NULL,
    entry_price NUMERIC(18,8) NOT NULL,
    exit_price NUMERIC(18,8) NOT NULL,
    pnl_dollars NUMERIC(18,8) NOT NULL,
    pnl_pct NUMERIC(18,8) NOT NULL,
    holding_seconds INT NOT NULL,
    holding_minutes NUMERIC(12,4) NOT NULL,
    mfe_pct NUMERIC(18,8) NOT NULL,
    mae_pct NUMERIC(18,8) NOT NULL,
    mfe_dollars NUMERIC(18,8) NULL,
    mae_dollars NUMERIC(18,8) NULL,
    iv_rank_at_entry NUMERIC(8,4) NULL,
    spread_at_entry_pct NUMERIC(8,4) NULL,
    entry_features_json JSONB NOT NULL,
    exit_reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_position_history_exit_ts
    ON position_history(exit_ts DESC);

CREATE INDEX IF NOT EXISTS idx_position_history_ticker_strategy_asset
    ON position_history(ticker, strategy_type, asset_type, exit_ts DESC);

CREATE INDEX IF NOT EXISTS idx_position_history_execution
    ON position_history(execution_id);

CREATE INDEX IF NOT EXISTS idx_position_history_symbol
    ON position_history(instrument_symbol, exit_ts DESC);

-- Constraints to prevent junk categorical values
ALTER TABLE position_history
    ADD CONSTRAINT chk_position_history_asset_type
        CHECK (asset_type IN ('stock','option'));

ALTER TABLE position_history
    ADD CONSTRAINT chk_position_history_strategy_type
        CHECK (strategy_type IS NULL OR strategy_type IN ('day_trade','swing_trade','stock'));

ALTER TABLE position_history
    ADD CONSTRAINT chk_position_history_side
        CHECK (side IS NULL OR side IN ('long','short','call','put'));

ALTER TABLE position_history
    ADD CONSTRAINT chk_position_history_exit_reason
        CHECK (exit_reason IN (
            'tp','sl','trail','time_stop','expiry_risk','theta_decay','manual',
            'forced_close_missing_bracket','risk_gate_daily_loss','risk_gate_exposure'
        ));

-- Optional FKs (enable only after verifying types)
-- ALTER TABLE position_history
--   ADD CONSTRAINT fk_position_history_position
--   FOREIGN KEY (position_id) REFERENCES active_positions(id);

-- ALTER TABLE position_history
--   ADD CONSTRAINT fk_position_history_execution
--   FOREIGN KEY (execution_id) REFERENCES dispatch_executions(execution_id);


-- 2) position_path_marks (optional)
CREATE TABLE IF NOT EXISTS position_path_marks (
    position_id BIGINT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    mark_price NUMERIC(18,8) NOT NULL,
    unrealized_pnl_pct NUMERIC(18,8) NOT NULL,
    unrealized_pnl_dollars NUMERIC(18,8) NOT NULL,
    PRIMARY KEY (position_id, ts)
);

CREATE INDEX IF NOT EXISTS idx_position_path_marks_position
    ON position_path_marks(position_id, ts DESC);


-- 3) strategy_stats (aggregated)
CREATE TABLE IF NOT EXISTS strategy_stats (
    as_of_date DATE NOT NULL,
    lookback_days INT NOT NULL DEFAULT 90,
    ticker TEXT NOT NULL,
    strategy_type TEXT NULL,
    asset_type TEXT NOT NULL,
    n_trades INT NOT NULL,
    win_rate NUMERIC(8,4) NOT NULL,
    avg_return NUMERIC(18,8) NOT NULL,
    avg_mae NUMERIC(18,8) NOT NULL,
    avg_mfe NUMERIC(18,8) NOT NULL,
    mae_p50 NUMERIC(18,8) NULL,
    mae_p70 NUMERIC(18,8) NULL,
    mae_p80 NUMERIC(18,8) NULL,
    mae_p90 NUMERIC(18,8) NULL,
    mfe_p50 NUMERIC(18,8) NULL,
    mfe_p70 NUMERIC(18,8) NULL,
    mfe_p80 NUMERIC(18,8) NULL,
    mfe_p90 NUMERIC(18,8) NULL,
    avg_hold_win_min NUMERIC(18,8) NULL,
    avg_hold_loss_min NUMERIC(18,8) NULL,
    sharpe NUMERIC(18,8) NULL,
    max_drawdown NUMERIC(18,8) NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (as_of_date, lookback_days, ticker, strategy_type, asset_type)
);

CREATE INDEX IF NOT EXISTS idx_strategy_stats_date
    ON strategy_stats(as_of_date DESC);

ALTER TABLE strategy_stats
    ADD CONSTRAINT chk_strategy_stats_asset_type
        CHECK (asset_type IN ('stock','option'));

ALTER TABLE strategy_stats
    ADD CONSTRAINT chk_strategy_stats_strategy_type
        CHECK (strategy_type IS NULL OR strategy_type IN ('day_trade','swing_trade','stock'));

-- 4) active_positions extensions (behavior learning hooks)
ALTER TABLE active_positions
    ADD COLUMN IF NOT EXISTS execution_uuid UUID,
    ADD COLUMN IF NOT EXISTS entry_features_json JSONB,
    ADD COLUMN IF NOT EXISTS entry_iv_rank NUMERIC(8,4),
    ADD COLUMN IF NOT EXISTS entry_spread_pct NUMERIC(8,4),
    ADD COLUMN IF NOT EXISTS best_unrealized_pnl_pct NUMERIC(18,8) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS worst_unrealized_pnl_pct NUMERIC(18,8) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS best_unrealized_pnl_dollars NUMERIC(18,8) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS worst_unrealized_pnl_dollars NUMERIC(18,8) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_mark_price NUMERIC(18,8);

COMMIT;
