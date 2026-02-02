-- Migration 009: Add position tracking tables for Position Manager
-- Date: 2026-01-26
-- Purpose: Enable real-time position monitoring and exit enforcement

-- Table: active_positions
-- Tracks all currently open trading positions
CREATE TABLE IF NOT EXISTS active_positions (
    id SERIAL PRIMARY KEY,
    execution_id INTEGER REFERENCES dispatch_executions(id),
    ticker VARCHAR(10) NOT NULL,
    instrument_type VARCHAR(20) NOT NULL, -- 'STOCK', 'CALL', 'PUT'
    strategy_type VARCHAR(20) NOT NULL,   -- 'day_trade', 'swing_trade'
    
    -- Position details
    side VARCHAR(10) NOT NULL,            -- 'long', 'short'
    quantity DECIMAL(12, 4) NOT NULL,
    entry_price DECIMAL(12, 4) NOT NULL,
    entry_time TIMESTAMP NOT NULL,
    
    -- Options specifics
    strike_price DECIMAL(12, 4),
    expiration_date DATE,
    
    -- Exit parameters
    stop_loss DECIMAL(12, 4),
    take_profit DECIMAL(12, 4),
    max_hold_minutes INTEGER,
    
    -- Bracket order tracking
    bracket_order_accepted BOOLEAN DEFAULT FALSE,
    stop_order_id VARCHAR(100),
    target_order_id VARCHAR(100),
    
    -- Monitoring
    current_price DECIMAL(12, 4),
    current_pnl_dollars DECIMAL(12, 4),
    current_pnl_percent DECIMAL(8, 4),
    last_checked_at TIMESTAMP,
    check_count INTEGER DEFAULT 0,
    
    -- Status
    status VARCHAR(20) DEFAULT 'open',    -- 'open', 'closing', 'closed'
    close_reason VARCHAR(50),             -- 'stop_loss', 'take_profit', 'time_exit', 'forced_close', 'expiration'
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP
);

-- Indexes for active_positions
CREATE INDEX idx_active_positions_status ON active_positions(status);
CREATE INDEX idx_active_positions_ticker ON active_positions(ticker);
CREATE INDEX idx_active_positions_execution ON active_positions(execution_id);
CREATE INDEX idx_active_positions_expiration ON active_positions(expiration_date) WHERE expiration_date IS NOT NULL;
CREATE INDEX idx_active_positions_entry_time ON active_positions(entry_time);

-- Table: position_events
-- Logs all position monitoring events for debugging and analytics
CREATE TABLE IF NOT EXISTS position_events (
    id SERIAL PRIMARY KEY,
    position_id INTEGER REFERENCES active_positions(id),
    event_type VARCHAR(50) NOT NULL,      -- 'created', 'price_update', 'exit_triggered', 'close_failed', 'closed', 'partial_fill'
    event_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for position_events
CREATE INDEX idx_position_events_position ON position_events(position_id);
CREATE INDEX idx_position_events_type ON position_events(event_type);
CREATE INDEX idx_position_events_created ON position_events(created_at);

-- View: v_open_positions_summary
-- Real-time view of all open positions with calculated metrics
CREATE OR REPLACE VIEW v_open_positions_summary AS
SELECT 
    ap.id,
    ap.ticker,
    ap.instrument_type,
    ap.strategy_type,
    ap.quantity,
    ap.entry_price,
    ap.current_price,
    ap.current_pnl_dollars,
    ap.current_pnl_percent,
    ap.stop_loss,
    ap.take_profit,
    ap.entry_time,
    ap.expiration_date,
    EXTRACT(EPOCH FROM (NOW() - ap.entry_time))/60 AS hold_minutes,
    ap.max_hold_minutes,
    CASE 
        WHEN ap.expiration_date IS NOT NULL 
        THEN EXTRACT(EPOCH FROM (ap.expiration_date::timestamp - NOW()))/3600 
        ELSE NULL 
    END AS hours_to_expiration,
    ap.bracket_order_accepted,
    ap.last_checked_at,
    ap.check_count,
    ap.created_at
FROM active_positions ap
WHERE ap.status = 'open'
ORDER BY ap.entry_time DESC;

-- View: v_position_performance
-- Historical position performance metrics
CREATE OR REPLACE VIEW v_position_performance AS
SELECT 
    ap.id,
    ap.ticker,
    ap.instrument_type,
    ap.strategy_type,
    ap.entry_price,
    ap.current_price AS exit_price,
    ap.quantity,
    ap.entry_time,
    ap.closed_at,
    EXTRACT(EPOCH FROM (ap.closed_at - ap.entry_time))/60 AS hold_minutes,
    ap.current_pnl_dollars AS final_pnl_dollars,
    ap.current_pnl_percent AS final_pnl_percent,
    ap.close_reason,
    ap.stop_loss,
    ap.take_profit,
    CASE 
        WHEN ap.close_reason IN ('take_profit') THEN 'win'
        WHEN ap.close_reason IN ('stop_loss') THEN 'loss'
        ELSE 'other'
    END AS outcome
FROM active_positions ap
WHERE ap.status = 'closed'
ORDER BY ap.closed_at DESC;

-- View: v_position_health_check
-- Quick health check of position monitoring system
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

-- Grant permissions
GRANT SELECT, INSERT, UPDATE ON active_positions TO pipeline_user;
GRANT SELECT, INSERT ON position_events TO pipeline_user;
GRANT USAGE, SELECT ON SEQUENCE active_positions_id_seq TO pipeline_user;
GRANT USAGE, SELECT ON SEQUENCE position_events_id_seq TO pipeline_user;
GRANT SELECT ON v_open_positions_summary TO pipeline_user;
GRANT SELECT ON v_position_performance TO pipeline_user;
GRANT SELECT ON v_position_health_check TO pipeline_user;

-- Migration complete
