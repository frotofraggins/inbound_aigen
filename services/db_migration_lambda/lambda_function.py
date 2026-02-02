import json
import os
import boto3
import psycopg2
from datetime import datetime, timezone

def log(event, **kwargs):
    """Structured JSON logging"""
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **kwargs
    }
    print(json.dumps(log_entry), flush=True)

def get_db_config():
    """Load database configuration from AWS services"""
    log("config_load_start")
    
    ssm = boto3.client('ssm', region_name='us-west-2')
    secrets = boto3.client('secretsmanager', region_name='us-west-2')
    
    db_host = ssm.get_parameter(Name='/ops-pipeline/db_host')['Parameter']['Value']
    db_port = ssm.get_parameter(Name='/ops-pipeline/db_port')['Parameter']['Value']
    db_name = ssm.get_parameter(Name='/ops-pipeline/db_name')['Parameter']['Value']
    
    secret_value = secrets.get_secret_value(SecretId='ops-pipeline/db')
    secret_data = json.loads(secret_value['SecretString'])
    
    log("config_load_success")
    
    return {
        'host': db_host,
        'port': int(db_port),
        'database': db_name,
        'user': secret_data['username'],
        'password': secret_data['password']
    }

# Migration SQL files embedded in Lambda
MIGRATIONS = {
    '001_init': """
-- Migration: 001_init.sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS inbound_events_raw (
    id BIGSERIAL PRIMARY KEY,
    event_uid TEXT NOT NULL UNIQUE,
    published_at TIMESTAMPTZ NULL,
    source TEXT NULL,
    title TEXT NOT NULL,
    link TEXT NULL,
    summary TEXT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_inbound_raw_processed 
    ON inbound_events_raw(processed_at) 
    WHERE processed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_inbound_raw_published 
    ON inbound_events_raw(published_at DESC);

CREATE INDEX IF NOT EXISTS idx_inbound_raw_fetched 
    ON inbound_events_raw(fetched_at DESC);

CREATE TABLE IF NOT EXISTS inbound_events_classified (
    id BIGSERIAL PRIMARY KEY,
    raw_event_id BIGINT NOT NULL REFERENCES inbound_events_raw(id) ON DELETE CASCADE,
    tickers TEXT[] NOT NULL DEFAULT '{}',
    sentiment_label TEXT NOT NULL,
    sentiment_score DOUBLE PRECISION NOT NULL,
    event_type TEXT NULL,
    urgency TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(raw_event_id)
);

CREATE INDEX IF NOT EXISTS idx_classified_tickers 
    ON inbound_events_classified USING GIN(tickers);

CREATE INDEX IF NOT EXISTS idx_classified_created 
    ON inbound_events_classified(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_classified_sentiment 
    ON inbound_events_classified(sentiment_label, created_at DESC);

CREATE TABLE IF NOT EXISTS feed_state (
    feed_url TEXT PRIMARY KEY,
    etag TEXT NULL,
    last_modified TEXT NULL,
    last_seen_published TIMESTAMPTZ NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS lane_telemetry (
    ticker TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    open DOUBLE PRECISION NOT NULL,
    high DOUBLE PRECISION NOT NULL,
    low DOUBLE PRECISION NOT NULL,
    close DOUBLE PRECISION NOT NULL,
    volume BIGINT NULL,
    PRIMARY KEY (ticker, ts)
);

CREATE INDEX IF NOT EXISTS idx_telemetry_ticker_ts 
    ON lane_telemetry(ticker, ts DESC);

CREATE TABLE IF NOT EXISTS dispatch_recommendations (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ticker TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('BUY', 'SELL')),
    confidence DOUBLE PRECISION NULL,
    reason JSONB NOT NULL DEFAULT '{}'::JSONB,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'EXECUTED', 'CANCELLED')),
    executed_at TIMESTAMPTZ NULL,
    filled_price DOUBLE PRECISION NULL,
    shares DOUBLE PRECISION NULL
);

CREATE INDEX IF NOT EXISTS idx_recommendations_status_ts 
    ON dispatch_recommendations(status, ts DESC);

CREATE INDEX IF NOT EXISTS idx_recommendations_ticker_ts 
    ON dispatch_recommendations(ticker, ts DESC);

CREATE INDEX IF NOT EXISTS idx_recommendations_executed 
    ON dispatch_recommendations(executed_at DESC) 
    WHERE executed_at IS NOT NULL;

INSERT INTO schema_migrations (version) VALUES ('001_init') ON CONFLICT (version) DO NOTHING;
""",
    '002_add_volatility_features': """
-- Migration: 002_add_volatility_features.sql
CREATE TABLE IF NOT EXISTS lane_features (
    ticker TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    
    -- Moving averages
    sma20 DOUBLE PRECISION NULL,
    sma50 DOUBLE PRECISION NULL,
    
    -- Volatility metrics
    recent_vol DOUBLE PRECISION NULL,
    baseline_vol DOUBLE PRECISION NULL,
    vol_ratio DOUBLE PRECISION NULL,
    
    -- Derived metrics
    distance_sma20 DOUBLE PRECISION NULL,
    distance_sma50 DOUBLE PRECISION NULL,
    trend_state INTEGER NULL,
    
    -- Latest close
    close DOUBLE PRECISION NULL,
    
    -- Metadata
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    PRIMARY KEY (ticker, ts)
);

CREATE INDEX IF NOT EXISTS idx_features_ticker_ts 
    ON lane_features(ticker, ts DESC);

CREATE INDEX IF NOT EXISTS idx_features_computed 
    ON lane_features(computed_at DESC);

INSERT INTO schema_migrations (version) VALUES ('002_add_volatility_features') ON CONFLICT (version) DO NOTHING;
""",
    '003_add_watchlist_state': """
-- Migration: 003_add_watchlist_state.sql
CREATE TABLE IF NOT EXISTS watchlist_state (
    ticker TEXT PRIMARY KEY,
    watch_score DOUBLE PRECISION NOT NULL,
    rank INTEGER NOT NULL,
    
    sentiment_pressure DOUBLE PRECISION NULL,
    vol_score DOUBLE PRECISION NULL,
    setup_quality DOUBLE PRECISION NULL,
    trend_alignment INTEGER NULL,
    
    reasons JSONB NOT NULL DEFAULT '{}'::JSONB,
    
    in_watchlist BOOLEAN NOT NULL DEFAULT FALSE,
    entered_at TIMESTAMPTZ NULL,
    
    last_score_update TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_watchlist_active 
    ON watchlist_state(in_watchlist, rank) 
    WHERE in_watchlist = TRUE;

CREATE INDEX IF NOT EXISTS idx_watchlist_score 
    ON watchlist_state(watch_score DESC);

CREATE INDEX IF NOT EXISTS idx_watchlist_computed 
    ON watchlist_state(computed_at DESC);

INSERT INTO schema_migrations (version) VALUES ('003_add_watchlist_state') ON CONFLICT (version) DO NOTHING;
""",
    '004_add_dispatcher_execution': """
-- Migration: 004_add_dispatcher_execution.sql
ALTER TABLE dispatch_recommendations
  ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'PENDING',
  ADD COLUMN IF NOT EXISTS processed_at TIMESTAMPTZ NULL,
  ADD COLUMN IF NOT EXISTS dispatcher_run_id UUID NULL,
  ADD COLUMN IF NOT EXISTS failure_reason TEXT NULL,
  ADD COLUMN IF NOT EXISTS risk_gate_json JSONB NULL;

CREATE INDEX IF NOT EXISTS idx_dispatch_reco_pending
  ON dispatch_recommendations (status, ts)
  WHERE status = 'PENDING';

CREATE INDEX IF NOT EXISTS idx_dispatch_reco_run
  ON dispatch_recommendations (dispatcher_run_id)
  WHERE dispatcher_run_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS dispatch_executions (
  execution_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  recommendation_id BIGINT NOT NULL REFERENCES dispatch_recommendations(id),
  dispatcher_run_id UUID NOT NULL,
  ticker            TEXT NOT NULL,
  action            TEXT NOT NULL,
  decision_ts       TIMESTAMPTZ NOT NULL,
  simulated_ts      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  entry_price       NUMERIC(18,8) NOT NULL,
  fill_model        TEXT NOT NULL,
  slippage_bps      INT NOT NULL DEFAULT 0,
  qty               NUMERIC(18,8) NOT NULL,
  notional          NUMERIC(18,8) NOT NULL,
  stop_loss_price   NUMERIC(18,8) NULL,
  take_profit_price NUMERIC(18,8) NULL,
  max_hold_minutes  INT NULL,
  execution_mode    TEXT NOT NULL DEFAULT 'SIMULATED',
  explain_json      JSONB NOT NULL,
  risk_json         JSONB NOT NULL,
  sim_json          JSONB NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_dispatch_execution_reco
  ON dispatch_executions (recommendation_id);

CREATE INDEX IF NOT EXISTS idx_dispatch_exec_run
  ON dispatch_executions (dispatcher_run_id);

CREATE INDEX IF NOT EXISTS idx_dispatch_exec_ticker
  ON dispatch_executions (ticker, simulated_ts DESC);

CREATE INDEX IF NOT EXISTS idx_dispatch_exec_time
  ON dispatch_executions (simulated_ts DESC);

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

CREATE INDEX IF NOT EXISTS idx_dispatcher_runs_time
  ON dispatcher_runs (started_at DESC);

INSERT INTO schema_migrations (version) VALUES ('004_add_dispatcher_execution') ON CONFLICT (version) DO NOTHING;
""",
    '005_add_missing_columns': """
-- Migration: 005_add_missing_columns.sql
ALTER TABLE dispatch_recommendations
  ADD COLUMN IF NOT EXISTS instrument_type TEXT,
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ;

UPDATE dispatch_recommendations
SET created_at = ts
WHERE created_at IS NULL;

INSERT INTO schema_migrations (version) VALUES ('005_add_missing_columns') ON CONFLICT (version) DO NOTHING;
""",
    '006_fix_dispatcher_status_constraint': """
-- Migration: 006_fix_dispatcher_status_constraint.sql
ALTER TABLE dispatch_recommendations 
DROP CONSTRAINT IF EXISTS dispatch_recommendations_status_check;

ALTER TABLE dispatch_recommendations
ADD CONSTRAINT dispatch_recommendations_status_check 
CHECK (status IN ('PENDING', 'PROCESSING', 'SIMULATED', 'SKIPPED', 'FAILED', 'EXECUTED', 'CANCELLED'));

COMMENT ON COLUMN dispatch_recommendations.status IS 
'State machine: PENDING → PROCESSING → (SIMULATED | SKIPPED | FAILED | EXECUTED | CANCELLED)';

INSERT INTO schema_migrations (version) VALUES ('006_fix_dispatcher_status_constraint') ON CONFLICT (version) DO NOTHING;
""",
    '007_add_volume_features': """
-- Migration: 007_add_volume_features.sql
ALTER TABLE lane_features 
ADD COLUMN IF NOT EXISTS volume_current BIGINT,
ADD COLUMN IF NOT EXISTS volume_avg_20 BIGINT,
ADD COLUMN IF NOT EXISTS volume_ratio NUMERIC(10,4),
ADD COLUMN IF NOT EXISTS volume_surge BOOLEAN;

COMMENT ON COLUMN lane_features.volume_current IS 
  'Current bar volume (number of shares traded)';

COMMENT ON COLUMN lane_features.volume_avg_20 IS 
  '20-period moving average of volume for baseline comparison';

COMMENT ON COLUMN lane_features.volume_ratio IS 
  'Current volume / 20-bar average. >2.0 = surge, <0.5 = dry, 1.0 = normal';

COMMENT ON COLUMN lane_features.volume_surge IS 
  'True if volume_ratio > 2.0 (indicates significant volume spike)';

CREATE INDEX IF NOT EXISTS idx_lane_features_volume 
ON lane_features(ticker, ts, volume_ratio);

INSERT INTO schema_migrations (version) VALUES ('007_add_volume_features') ON CONFLICT (version) DO NOTHING;
""",
    '008_add_options_support': """
-- Migration 008: Add Options Trading Support
ALTER TABLE dispatch_recommendations
ADD COLUMN IF NOT EXISTS strategy_type TEXT CHECK (strategy_type IN ('day_trade', 'swing_trade', 'conservative'));

CREATE INDEX IF NOT EXISTS idx_dispatch_reco_strategy_type 
ON dispatch_recommendations(strategy_type) 
WHERE strategy_type IS NOT NULL;

COMMENT ON COLUMN dispatch_recommendations.strategy_type IS 'Options strategy: day_trade (0-1 DTE), swing_trade (7-30 DTE), conservative (ITM)';

ALTER TABLE dispatch_executions
ADD COLUMN IF NOT EXISTS instrument_type TEXT DEFAULT 'STOCK' CHECK (instrument_type IN ('STOCK', 'CALL', 'PUT')),
ADD COLUMN IF NOT EXISTS strike_price NUMERIC(10,2),
ADD COLUMN IF NOT EXISTS expiration_date DATE,
ADD COLUMN IF NOT EXISTS contracts INT,
ADD COLUMN IF NOT EXISTS premium_paid NUMERIC(10,2),
ADD COLUMN IF NOT EXISTS delta NUMERIC(10,4),
ADD COLUMN IF NOT EXISTS theta NUMERIC(10,4),
ADD COLUMN IF NOT EXISTS implied_volatility NUMERIC(10,4),
ADD COLUMN IF NOT EXISTS option_symbol TEXT,
ADD COLUMN IF NOT EXISTS strategy_type TEXT CHECK (strategy_type IN ('day_trade', 'swing_trade', 'conservative'));

CREATE INDEX IF NOT EXISTS idx_dispatch_executions_instrument_type 
ON dispatch_executions(instrument_type);

CREATE INDEX IF NOT EXISTS idx_dispatch_executions_expiration_date 
ON dispatch_executions(expiration_date) 
WHERE expiration_date IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_dispatch_executions_strategy_type 
ON dispatch_executions(strategy_type) 
WHERE strategy_type IS NOT NULL;

COMMENT ON COLUMN dispatch_executions.instrument_type IS 'Type of instrument: STOCK (default), CALL, or PUT';
COMMENT ON COLUMN dispatch_executions.strike_price IS 'Strike price for options (NULL for stocks)';
COMMENT ON COLUMN dispatch_executions.expiration_date IS 'Expiration date for options (NULL for stocks)';
COMMENT ON COLUMN dispatch_executions.contracts IS 'Number of option contracts (NULL for stocks, 1 contract = 100 shares)';
COMMENT ON COLUMN dispatch_executions.premium_paid IS 'Premium paid per contract (NULL for stocks)';
COMMENT ON COLUMN dispatch_executions.delta IS 'Option delta (sensitivity to price changes)';
COMMENT ON COLUMN dispatch_executions.theta IS 'Option theta (time decay)';
COMMENT ON COLUMN dispatch_executions.implied_volatility IS 'Implied volatility of the option';
COMMENT ON COLUMN dispatch_executions.option_symbol IS 'OCC formatted option symbol (e.g., AAPL250131C00150000)';
COMMENT ON COLUMN dispatch_executions.strategy_type IS 'Trading strategy: day_trade (0-1 DTE), swing_trade (7-30 DTE), conservative (ITM)';

-- Add constraint only if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'check_options_metadata'
    ) THEN
        ALTER TABLE dispatch_executions 
        ADD CONSTRAINT check_options_metadata 
        CHECK (
            (instrument_type = 'STOCK') OR 
            (instrument_type IN ('CALL', 'PUT') AND strike_price IS NOT NULL AND expiration_date IS NOT NULL)
        );
    END IF;
END $$;

CREATE OR REPLACE VIEW active_options_positions AS
SELECT 
    execution_id, ticker, instrument_type, strike_price, expiration_date,
    contracts, premium_paid, delta, theta, implied_volatility, option_symbol,
    strategy_type, entry_price, qty, notional, stop_loss_price, take_profit_price,
    simulated_ts, (expiration_date - CURRENT_DATE) AS days_to_expiration
FROM dispatch_executions
WHERE instrument_type IN ('CALL', 'PUT')
    AND expiration_date >= CURRENT_DATE
    AND execution_mode IN ('ALPACA_PAPER', 'LIVE')
ORDER BY expiration_date ASC, simulated_ts DESC;

CREATE OR REPLACE VIEW options_performance_by_strategy AS
SELECT 
    strategy_type, instrument_type, COUNT(*) AS total_trades,
    AVG(notional) AS avg_position_size, AVG(premium_paid) AS avg_premium,
    AVG(delta) AS avg_delta,
    AVG(expiration_date - DATE(simulated_ts)) AS avg_days_held,
    MIN(simulated_ts) AS first_trade, MAX(simulated_ts) AS last_trade
FROM dispatch_executions
WHERE instrument_type IN ('CALL', 'PUT') AND strategy_type IS NOT NULL
GROUP BY strategy_type, instrument_type
ORDER BY strategy_type, instrument_type;

CREATE OR REPLACE VIEW daily_options_summary AS
SELECT 
    DATE(simulated_ts) AS trade_date, instrument_type, strategy_type,
    COUNT(*) AS num_trades, SUM(notional) AS total_notional,
    SUM(contracts) AS total_contracts, AVG(premium_paid) AS avg_premium, AVG(delta) AS avg_delta
FROM dispatch_executions
WHERE instrument_type IN ('CALL', 'PUT')
GROUP BY DATE(simulated_ts), instrument_type, strategy_type
ORDER BY trade_date DESC, instrument_type, strategy_type;

INSERT INTO schema_migrations (version) VALUES ('008_add_options_support') ON CONFLICT (version) DO NOTHING;
""",
    '009_add_position_tracking': """
-- Migration 009: Add position tracking tables for Position Manager
-- First add missing fields to dispatch_executions
ALTER TABLE dispatch_executions
ADD COLUMN IF NOT EXISTS side VARCHAR(10) DEFAULT 'long',
ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'PENDING',
ADD COLUMN IF NOT EXISTS broker_order_id VARCHAR(100),
ADD COLUMN IF NOT EXISTS stop_order_id VARCHAR(100),
ADD COLUMN IF NOT EXISTS target_order_id VARCHAR(100),
ADD COLUMN IF NOT EXISTS executed_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS filled_qty DECIMAL(12, 4);

CREATE INDEX IF NOT EXISTS idx_dispatch_executions_status ON dispatch_executions(status);

-- Now create active_positions table
CREATE TABLE IF NOT EXISTS active_positions (
    id SERIAL PRIMARY KEY,
    execution_id UUID REFERENCES dispatch_executions(execution_id),
    ticker VARCHAR(10) NOT NULL,
    instrument_type VARCHAR(20) NOT NULL,
    strategy_type VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    quantity DECIMAL(12, 4) NOT NULL,
    entry_price DECIMAL(12, 4) NOT NULL,
    entry_time TIMESTAMP NOT NULL,
    strike_price DECIMAL(12, 4),
    expiration_date DATE,
    stop_loss DECIMAL(12, 4),
    take_profit DECIMAL(12, 4),
    max_hold_minutes INTEGER,
    bracket_order_accepted BOOLEAN DEFAULT FALSE,
    stop_order_id VARCHAR(100),
    target_order_id VARCHAR(100),
    current_price DECIMAL(12, 4),
    current_pnl_dollars DECIMAL(12, 4),
    current_pnl_percent DECIMAL(8, 4),
    last_checked_at TIMESTAMP,
    check_count INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'open',
    close_reason VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP
);

CREATE INDEX idx_active_positions_status ON active_positions(status);
CREATE INDEX idx_active_positions_ticker ON active_positions(ticker);
CREATE INDEX idx_active_positions_execution ON active_positions(execution_id);
CREATE INDEX idx_active_positions_expiration ON active_positions(expiration_date) WHERE expiration_date IS NOT NULL;
CREATE INDEX idx_active_positions_entry_time ON active_positions(entry_time);

CREATE TABLE IF NOT EXISTS position_events (
    id SERIAL PRIMARY KEY,
    position_id INTEGER REFERENCES active_positions(id),
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_position_events_position ON position_events(position_id);
CREATE INDEX idx_position_events_type ON position_events(event_type);
CREATE INDEX idx_position_events_created ON position_events(created_at);

CREATE OR REPLACE VIEW v_open_positions_summary AS
SELECT 
    ap.id, ap.ticker, ap.instrument_type, ap.strategy_type, ap.quantity,
    ap.entry_price, ap.current_price, ap.current_pnl_dollars, ap.current_pnl_percent,
    ap.stop_loss, ap.take_profit, ap.entry_time, ap.expiration_date,
    EXTRACT(EPOCH FROM (NOW() - ap.entry_time))/60 AS hold_minutes,
    ap.max_hold_minutes,
    CASE 
        WHEN ap.expiration_date IS NOT NULL 
        THEN EXTRACT(EPOCH FROM (ap.expiration_date::timestamp - NOW()))/3600 
        ELSE NULL 
    END AS hours_to_expiration,
    ap.bracket_order_accepted, ap.last_checked_at, ap.check_count, ap.created_at
FROM active_positions ap
WHERE ap.status = 'open'
ORDER BY ap.entry_time DESC;

CREATE OR REPLACE VIEW v_position_performance AS
SELECT 
    ap.id, ap.ticker, ap.instrument_type, ap.strategy_type,
    ap.entry_price, ap.current_price AS exit_price, ap.quantity,
    ap.entry_time, ap.closed_at,
    EXTRACT(EPOCH FROM (ap.closed_at - ap.entry_time))/60 AS hold_minutes,
    ap.current_pnl_dollars AS final_pnl_dollars,
    ap.current_pnl_percent AS final_pnl_percent,
    ap.close_reason, ap.stop_loss, ap.take_profit,
    CASE 
        WHEN ap.close_reason IN ('take_profit') THEN 'win'
        WHEN ap.close_reason IN ('stop_loss') THEN 'loss'
        ELSE 'other'
    END AS outcome
FROM active_positions ap
WHERE ap.status = 'closed'
ORDER BY ap.closed_at DESC;

CREATE OR REPLACE VIEW v_position_health_check AS
SELECT 
    COUNT(*) FILTER (WHERE status = 'open') AS open_positions,
    COUNT(*) FILTER (WHERE status = 'closing') AS closing_positions,
    COUNT(*) FILTER (WHERE status = 'closed') AS closed_positions_today,
    COUNT(*) FILTER (WHERE status = 'open' AND last_checked_at < NOW() - INTERVAL '5 minutes') AS stale_positions,
    COUNT(*) FILTER (WHERE status = 'open' AND NOT bracket_order_accepted) AS missing_brackets,
    COUNT(*) FILTER (WHERE status = 'open' AND strategy_type = 'day_trade') AS open_day_trades,
    COUNT(*) FILTER (WHERE status = 'open' AND expiration_date IS NOT NULL AND expiration_date < CURRENT_DATE + 1) AS expiring_soon
FROM active_positions
WHERE created_at >= CURRENT_DATE;

INSERT INTO schema_migrations (version) VALUES ('009_add_position_tracking') ON CONFLICT (version) DO NOTHING;
""",
    '010_add_ai_learning_tables': """
-- Migration 010: AI Learning Tables
CREATE TABLE IF NOT EXISTS ticker_universe (
    ticker VARCHAR(10) PRIMARY KEY,
    sector VARCHAR(50) NOT NULL,
    catalyst TEXT NOT NULL,
    confidence DECIMAL(4,3) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    expected_volume VARCHAR(20) NOT NULL DEFAULT 'normal',
    discovered_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_updated TIMESTAMP NOT NULL DEFAULT NOW(),
    active BOOLEAN NOT NULL DEFAULT true
);

CREATE INDEX idx_ticker_universe_active ON ticker_universe(active);
CREATE INDEX idx_ticker_universe_confidence ON ticker_universe(confidence DESC);
CREATE INDEX idx_ticker_universe_sector ON ticker_universe(sector);

CREATE TABLE IF NOT EXISTS missed_opportunities (
    id SERIAL PRIMARY KEY,
    analysis_date DATE NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    ts TIMESTAMP NOT NULL,
    volume_ratio DECIMAL(10,4) NOT NULL,
    close_price DECIMAL(12,4) NOT NULL,
    sentiment_score DECIMAL(4,3),
    why_skipped TEXT NOT NULL,
    rule_that_blocked TEXT NOT NULL,
    real_opportunity BOOLEAN NOT NULL,
    estimated_profit_pct DECIMAL(6,3) NOT NULL,
    should_have_traded BOOLEAN NOT NULL,
    ai_reasoning TEXT NOT NULL,
    suggested_adjustment TEXT NOT NULL,
    analyzed_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_missed_opportunities_date ON missed_opportunities(analysis_date);
CREATE INDEX idx_missed_opportunities_ticker ON missed_opportunities(ticker);
CREATE INDEX idx_missed_opportunities_should_trade ON missed_opportunities(should_have_traded);
CREATE INDEX idx_missed_opportunities_real_opp ON missed_opportunities(real_opportunity);

CREATE OR REPLACE VIEW v_active_tickers AS
SELECT ticker, sector, catalyst, confidence, expected_volume, last_updated
FROM ticker_universe
WHERE active = true
ORDER BY confidence DESC;

CREATE OR REPLACE VIEW v_daily_missed_summary AS
SELECT 
    analysis_date,
    COUNT(*) as total_surges,
    SUM(CASE WHEN should_have_traded THEN 1 ELSE 0 END) as should_have_traded,
    SUM(CASE WHEN NOT should_have_traded THEN 1 ELSE 0 END) as correctly_skipped,
    SUM(CASE WHEN should_have_traded THEN estimated_profit_pct ELSE 0 END) as potential_missed_profit_pct,
    AVG(volume_ratio) as avg_volume_ratio
FROM missed_opportunities
GROUP BY analysis_date
ORDER BY analysis_date DESC;

CREATE OR REPLACE VIEW v_ticker_missed_patterns AS
SELECT 
    ticker,
    COUNT(*) as missed_count,
    SUM(CASE WHEN should_have_traded THEN 1 ELSE 0 END) as should_have_traded_count,
    AVG(volume_ratio) as avg_volume_ratio,
    AVG(estimated_profit_pct) as avg_estimated_profit_pct,
    MAX(analysis_date) as last_missed_date
FROM missed_opportunities
WHERE analysis_date > CURRENT_DATE - INTERVAL '30 days'
GROUP BY ticker
HAVING COUNT(*) >= 2
ORDER BY should_have_traded_count DESC, missed_count DESC;

INSERT INTO schema_migrations (version) VALUES ('010_add_ai_learning_tables') ON CONFLICT (version) DO NOTHING;
""",
    '011_add_learning_infrastructure': """
-- Migration 011: Learning Infrastructure (Phase 16 P0) - FIXED table names
-- First remove old migration record to reapply
DELETE FROM schema_migrations WHERE version = '011_add_learning_infrastructure';

ALTER TABLE dispatch_recommendations
    ADD COLUMN IF NOT EXISTS features_snapshot JSONB,
    ADD COLUMN IF NOT EXISTS sentiment_snapshot JSONB;

ALTER TABLE dispatch_executions
    ADD COLUMN IF NOT EXISTS features_snapshot JSONB,
    ADD COLUMN IF NOT EXISTS sentiment_snapshot JSONB;

ALTER TABLE active_positions
    ADD COLUMN IF NOT EXISTS win_loss_label SMALLINT,
    ADD COLUMN IF NOT EXISTS r_multiple NUMERIC(8,4),
    ADD COLUMN IF NOT EXISTS mae_pct NUMERIC(8,4),
    ADD COLUMN IF NOT EXISTS mfe_pct NUMERIC(8,4),
    ADD COLUMN IF NOT EXISTS holding_minutes INT,
    ADD COLUMN IF NOT EXISTS exit_reason_norm VARCHAR(32);

CREATE INDEX IF NOT EXISTS idx_dispatch_recs_features_gin
    ON dispatch_recommendations USING GIN (features_snapshot);

CREATE INDEX IF NOT EXISTS idx_dispatch_recs_sentiment_gin
    ON dispatch_recommendations USING GIN (sentiment_snapshot);

CREATE INDEX IF NOT EXISTS idx_dispatch_exec_features_gin
    ON dispatch_executions USING GIN (features_snapshot);

CREATE INDEX IF NOT EXISTS idx_dispatch_exec_sentiment_gin
    ON dispatch_executions USING GIN (sentiment_snapshot);

CREATE INDEX IF NOT EXISTS idx_active_positions_win_loss ON active_positions(win_loss_label);
CREATE INDEX IF NOT EXISTS idx_active_positions_r_multiple ON active_positions(r_multiple);

CREATE TABLE IF NOT EXISTS learning_recommendations (
    id SERIAL PRIMARY KEY,
    parameter_name VARCHAR(100) NOT NULL,
    parameter_path VARCHAR(200) NOT NULL,
    current_value NUMERIC(12,6) NOT NULL,
    suggested_value NUMERIC(12,6) NOT NULL,
    rollback_value NUMERIC(12,6),
    sample_size INT NOT NULL,
    confidence DECIMAL(4,3) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    avg_return_if_changed NUMERIC(8,4),
    backtest_sharpe NUMERIC(6,3),
    recommendation_reason TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    reviewed_by VARCHAR(50),
    reviewed_at TIMESTAMP,
    generated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

INSERT INTO schema_migrations (version) VALUES ('011_add_learning_infrastructure') ON CONFLICT (version) DO NOTHING;
""",
    '012_phase16_columns_only': """
-- Migration 012: Phase 16 Columns Only (learning_recommendations already exists)
-- Safe - uses IF NOT EXISTS

ALTER TABLE dispatch_recommendations 
ADD COLUMN IF NOT EXISTS features_snapshot JSONB,
ADD COLUMN IF NOT EXISTS sentiment_snapshot JSONB;

ALTER TABLE dispatch_executions
ADD COLUMN IF NOT EXISTS features_snapshot JSONB,
ADD COLUMN IF NOT EXISTS sentiment_snapshot JSONB;

ALTER TABLE active_positions
ADD COLUMN IF NOT EXISTS win_loss_label SMALLINT,
ADD COLUMN IF NOT EXISTS r_multiple NUMERIC(8,4),
ADD COLUMN IF NOT EXISTS mae_pct NUMERIC(8,4),
ADD COLUMN IF NOT EXISTS mfe_pct NUMERIC(8,4),
ADD COLUMN IF NOT EXISTS holding_minutes INT,
ADD COLUMN IF NOT EXISTS exit_reason_norm VARCHAR(32);

CREATE INDEX IF NOT EXISTS idx_dispatch_recs_features_gin
    ON dispatch_recommendations USING GIN (features_snapshot);

CREATE INDEX IF NOT EXISTS idx_dispatch_recs_sentiment_gin
    ON dispatch_recommendations USING GIN (sentiment_snapshot);

CREATE INDEX IF NOT EXISTS idx_dispatch_exec_features_gin
    ON dispatch_executions USING GIN (features_snapshot);

CREATE INDEX IF NOT EXISTS idx_dispatch_exec_sentiment_gin
    ON dispatch_executions USING GIN (sentiment_snapshot);

CREATE INDEX IF NOT EXISTS idx_active_positions_win_loss ON active_positions(win_loss_label);
CREATE INDEX IF NOT EXISTS idx_active_positions_r_multiple ON active_positions(r_multiple);

INSERT INTO schema_migrations (version) VALUES ('012_phase16_columns_only') ON CONFLICT (version) DO NOTHING;
""",
    '013_options_columns_safe': """
-- Migration 013: Options Columns (From Migration 008, Safe Retry)
-- Uses IF NOT EXISTS - completely safe, won't break existing data

-- Add options columns to dispatch_executions
ALTER TABLE dispatch_executions
ADD COLUMN IF NOT EXISTS instrument_type TEXT DEFAULT 'STOCK',
ADD COLUMN IF NOT EXISTS strike_price NUMERIC(10,2),
ADD COLUMN IF NOT EXISTS expiration_date DATE,
ADD COLUMN IF NOT EXISTS contracts INT,
ADD COLUMN IF NOT EXISTS premium_paid NUMERIC(10,2),
ADD COLUMN IF NOT EXISTS delta NUMERIC(10,4),
ADD COLUMN IF NOT EXISTS theta NUMERIC(10,4),
ADD COLUMN IF NOT EXISTS implied_volatility NUMERIC(10,4),
ADD COLUMN IF NOT EXISTS option_symbol TEXT,
ADD COLUMN IF NOT EXISTS strategy_type TEXT;

-- Add indexes
CREATE INDEX IF NOT EXISTS idx_dispatch_executions_instrument_type 
ON dispatch_executions(instrument_type);

CREATE INDEX IF NOT EXISTS idx_dispatch_executions_expiration_date 
ON dispatch_executions(expiration_date) 
WHERE expiration_date IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_dispatch_executions_strategy_type 
ON dispatch_executions(strategy_type) 
WHERE strategy_type IS NOT NULL;

-- Record migration
INSERT INTO schema_migrations (version) VALUES ('013_options_columns_safe') ON CONFLICT (version) DO NOTHING;
""",
    '014_force_options_columns': """
-- Migration 014: Force Options Columns (FINAL FIX)
DELETE FROM schema_migrations WHERE version IN ('008_add_options_support', '013_options_columns_safe');
ALTER TABLE dispatch_executions ADD COLUMN IF NOT EXISTS instrument_type TEXT;
ALTER TABLE dispatch_executions ADD COLUMN IF NOT EXISTS strike_price NUMERIC(10,2);
ALTER TABLE dispatch_executions ADD COLUMN IF NOT EXISTS expiration_date DATE;
ALTER TABLE dispatch_executions ADD COLUMN IF NOT EXISTS contracts INT;
ALTER TABLE dispatch_executions ADD COLUMN IF NOT EXISTS premium_paid NUMERIC(10,2);
ALTER TABLE dispatch_executions ADD COLUMN IF NOT EXISTS delta NUMERIC(10,4);
ALTER TABLE dispatch_executions ADD COLUMN IF NOT EXISTS theta NUMERIC(10,4);
ALTER TABLE dispatch_executions ADD COLUMN IF NOT EXISTS implied_volatility NUMERIC(10,4);
ALTER TABLE dispatch_executions ADD COLUMN IF NOT EXISTS option_symbol TEXT;
ALTER TABLE dispatch_executions ADD COLUMN IF NOT EXISTS strategy_type TEXT;
UPDATE dispatch_executions SET instrument_type = 'STOCK' WHERE instrument_type IS NULL;
ALTER TABLE dispatch_executions ALTER COLUMN instrument_type SET DEFAULT 'STOCK';
CREATE INDEX IF NOT EXISTS idx_dispatch_executions_instrument_type ON dispatch_executions(instrument_type);
CREATE INDEX IF NOT EXISTS idx_dispatch_executions_expiration_date ON dispatch_executions(expiration_date) WHERE expiration_date IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_dispatch_executions_strategy_type ON dispatch_executions(strategy_type) WHERE strategy_type IS NOT NULL;
INSERT INTO schema_migrations (version) VALUES ('014_force_options_columns') ON CONFLICT (version) DO NOTHING;
""",
    '015_options_telemetry_integrated': """
-- Migration 015: Options telemetry for AI learning (integrated approach)
-- Creates tables for capturing historical option price movement

CREATE TABLE IF NOT EXISTS option_bars (
    symbol TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    open NUMERIC(10,2) NOT NULL,
    high NUMERIC(10,2) NOT NULL,
    low NUMERIC(10,2) NOT NULL,
    close NUMERIC(10,2) NOT NULL,
    volume BIGINT NULL,
    trade_count INT NULL,
    vwap NUMERIC(10,2) NULL,
    PRIMARY KEY (symbol, ts)
);

CREATE INDEX IF NOT EXISTS idx_option_bars_symbol_ts ON option_bars(symbol, ts DESC);
CREATE INDEX IF NOT EXISTS idx_option_bars_ts ON option_bars(ts DESC);

COMMENT ON TABLE option_bars IS 'Historical 1-minute bars for option contracts. Enables temporal analysis.';

ALTER TABLE dispatch_executions 
ADD COLUMN IF NOT EXISTS bars_captured_count INT DEFAULT 0,
ADD COLUMN IF NOT EXISTS first_bar_ts TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS last_bar_ts TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS peak_premium NUMERIC(10,2),
ADD COLUMN IF NOT EXISTS lowest_premium NUMERIC(10,2);

COMMENT ON COLUMN dispatch_executions.bars_captured_count IS 'Number of 1-min bars captured for position.';

CREATE TABLE IF NOT EXISTS iv_surface (
    ticker TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    expiration_date DATE NOT NULL,
    strike_price NUMERIC(10,2) NOT NULL,
    option_type TEXT NOT NULL CHECK (option_type IN ('call', 'put')),
    implied_volatility NUMERIC(10,4),
    delta NUMERIC(10,4),
    volume BIGINT,
    open_interest BIGINT,
    PRIMARY KEY (ticker, ts, expiration_date, strike_price, option_type)
);

CREATE INDEX IF NOT EXISTS idx_iv_surface_ticker_ts ON iv_surface(ticker, ts DESC);

COMMENT ON TABLE iv_surface IS 'IV surface snapshots for volatility analysis.';

INSERT INTO schema_migrations (version) VALUES ('015_options_telemetry_integrated') ON CONFLICT (version) DO NOTHING;
"""
    ,
    '016_add_active_positions_option_symbol': """
-- Migration 016: Add option_symbol to active_positions
-- Fixes Position Manager sync for options

ALTER TABLE active_positions 
ADD COLUMN IF NOT EXISTS option_symbol TEXT;

COMMENT ON COLUMN active_positions.option_symbol IS 'Full OCC option symbol for options positions (e.g., QCOM260206C00150000)';

CREATE INDEX IF NOT EXISTS idx_active_positions_option_symbol 
ON active_positions(option_symbol) 
WHERE option_symbol IS NOT NULL;

INSERT INTO schema_migrations (version) VALUES ('016_add_active_positions_option_symbol') ON CONFLICT (version) DO NOTHING;
"""
    ,
    '017_release_stuck_processing': """
-- Migration 017: Release stuck PROCESSING recommendations
-- Clears stale PROCESSING rows so dispatcher can re-claim them.

UPDATE dispatch_recommendations
SET status = 'PENDING',
    dispatcher_run_id = NULL,
    failure_reason = 'Released from stuck PROCESSING state (migration 017)'
WHERE status = 'PROCESSING'
  AND COALESCE(processed_at, ts) < NOW() - INTERVAL '10 minutes';

INSERT INTO schema_migrations (version) VALUES ('017_release_stuck_processing') ON CONFLICT (version) DO NOTHING;
"""
    ,
    '018_add_account_activities': """
-- Migration 018: Account activities for AI learning/audit
CREATE TABLE IF NOT EXISTS account_activities (
    id BIGSERIAL PRIMARY KEY,
    activity_id TEXT NOT NULL UNIQUE,
    activity_type TEXT NOT NULL,
    activity_date DATE NULL,
    transaction_time TIMESTAMPTZ NULL,
    symbol TEXT NULL,
    qty NUMERIC(18,8) NULL,
    price NUMERIC(18,8) NULL,
    net_amount NUMERIC(18,8) NULL,
    order_id TEXT NULL,
    account_name TEXT NULL,
    raw_json JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_account_activities_type_date
    ON account_activities(activity_type, activity_date DESC);

CREATE INDEX IF NOT EXISTS idx_account_activities_symbol_date
    ON account_activities(symbol, activity_date DESC);

CREATE INDEX IF NOT EXISTS idx_account_activities_order_id
    ON account_activities(order_id)
    WHERE order_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_account_activities_account_date
    ON account_activities(account_name, activity_date DESC);

CREATE INDEX IF NOT EXISTS idx_account_activities_transaction_time
    ON account_activities(transaction_time DESC);

INSERT INTO schema_migrations (version) VALUES ('018_add_account_activities') ON CONFLICT (version) DO NOTHING;
"""
}

def lambda_handler(event, context):
    """
    Database migration Lambda - applies all pending migrations in order
    """
    
    log("migration_lambda_start")
    
    try:
        # Get DB configuration
        config = get_db_config()
        
        # Connect to database
        log("db_connect_start")
        conn = psycopg2.connect(**config, connect_timeout=10)
        log("db_connect_success")
        
        # Get applied migrations
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            conn.commit()
            
            cursor.execute("SELECT version FROM schema_migrations")
            applied = set(row[0] for row in cursor.fetchall())
        
        log("migrations_status", applied=list(applied))
        
        # Apply pending migrations in order
        migrations_applied = []
        migrations_skipped = []
        
        for version in sorted(MIGRATIONS.keys()):
            if version in applied:
                log("migration_skipped", version=version)
                migrations_skipped.append(version)
                continue
            
            log("migration_apply_start", version=version)
            
            with conn.cursor() as cursor:
                cursor.execute(MIGRATIONS[version])
                conn.commit()
            
            log("migration_apply_success", version=version)
            migrations_applied.append(version)
        
        # Get final table list
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT tablename FROM pg_tables 
                WHERE schemaname = 'public' 
                ORDER BY tablename
            """)
            tables = [row[0] for row in cursor.fetchall()]
        
        conn.close()
        
        result = {
            "success": True,
            "migrations_applied": migrations_applied,
            "migrations_skipped": migrations_skipped,
            "tables": tables,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        log("migration_lambda_complete", **result)
        
        return {
            'statusCode': 200,
            'body': json.dumps(result)
        }
        
    except Exception as e:
        log("migration_lambda_failed", 
            error=str(e), 
            error_type=type(e).__name__)
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'error': str(e)
            })
        }
