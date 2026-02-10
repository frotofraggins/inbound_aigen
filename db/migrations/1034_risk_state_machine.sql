-- Risk State Machine - Database Schema
-- Date: 2026-02-10
-- Purpose: Add lifecycle management for professional risk management

-- Phase 1: Add lifecycle columns to active_positions
-- These columns track position progression through risk states
ALTER TABLE active_positions 
ADD COLUMN IF NOT EXISTS lifecycle_state TEXT DEFAULT 'OPEN',
ADD COLUMN IF NOT EXISTS peak_price FLOAT,
ADD COLUMN IF NOT EXISTS partial_taken BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS partial_qty_sold FLOAT DEFAULT 0,
ADD COLUMN IF NOT EXISTS breakeven_armed BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS trail_price FLOAT,
ADD COLUMN IF NOT EXISTS trail_level INT DEFAULT 0,
ADD COLUMN IF NOT EXISTS last_state_change TIMESTAMP,
ADD COLUMN IF NOT EXISTS state_change_count INT DEFAULT 0;

-- Phase 2: Create state transition audit table
-- Tracks every state change for debugging and ML learning
CREATE TABLE IF NOT EXISTS position_state_history (
    id SERIAL PRIMARY KEY,
    position_id INT REFERENCES active_positions(id) ON DELETE CASCADE,
    old_state TEXT NOT NULL,
    new_state TEXT NOT NULL,
    reason TEXT,
    profit_pct FLOAT,
    peak_price FLOAT,
    current_price FLOAT,
    changed_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_state_history_position 
ON position_state_history(position_id, changed_at DESC);

CREATE INDEX IF NOT EXISTS idx_state_history_transitions
ON position_state_history(old_state, new_state, changed_at DESC);

-- Phase 3: Configuration table with versioning
CREATE TABLE IF NOT EXISTS trade_management_config (
    id SERIAL PRIMARY KEY,
    config_version INT NOT NULL,
    breakeven_trigger FLOAT NOT NULL,
    partial_profit_trigger FLOAT NOT NULL,
    partial_size FLOAT NOT NULL,
    time_stop_minutes INT NOT NULL,
    min_progress_pct FLOAT NOT NULL,
    trail_levels JSONB NOT NULL,
    enabled BOOLEAN DEFAULT FALSE,  -- START DISABLED FOR SAFETY
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(config_version)
);

-- Insert default config (DISABLED for safety)
INSERT INTO trade_management_config (
    config_version,
    breakeven_trigger,
    partial_profit_trigger,
    partial_size,
    time_stop_minutes,
    min_progress_pct,
    trail_levels,
    enabled,
    notes
) VALUES (
    1,
    0.10,  -- +10% profit → move stop to breakeven
    0.20,  -- +20% profit → take 40% partial
    0.40,  -- Partial size = 40%
    240,   -- 4 hour time stop
    0.05,  -- Need 5% progress per hour
    '[
        {
            "name": "tier1",
            "profit": 0.20,
            "keep": 0.70,
            "description": "At +20% profit, trail at 70% (locks +14%)"
        },
        {
            "name": "tier2",
            "profit": 0.40,
            "keep": 0.80,
            "description": "At +40% profit, trail at 80% (locks +32%)"
        },
        {
            "name": "tier3",
            "profit": 0.60,
            "keep": 0.85,
            "description": "At +60% profit, trail at 85% (locks +51%)"
        }
    ]'::jsonb,
    false,  -- START DISABLED
    'Initial config - DISABLED by default for safe rollout. Enable after testing.'
) ON CONFLICT (config_version) DO NOTHING;

-- Phase 4: Analytics views for monitoring
CREATE OR REPLACE VIEW v_state_transition_stats AS
SELECT 
    old_state,
    new_state,
    COUNT(*) as transition_count,
    AVG(profit_pct) as avg_profit_at_transition,
    STDDEV(profit_pct) as stddev_profit,
    MIN(changed_at) as first_seen,
    MAX(changed_at) as last_seen
FROM position_state_history
GROUP BY old_state, new_state
ORDER BY transition_count DESC;

CREATE OR REPLACE VIEW v_position_lifecycle_summary AS
SELECT 
    ap.id,
    ap.ticker,
    ap.instrument_type,
    ap.lifecycle_state,
    ap.entry_time,
    ap.peak_price,
    ap.current_price,
    ap.entry_price,
    CASE 
        WHEN ap.peak_price IS NOT NULL AND ap.entry_price > 0 
        THEN ((ap.peak_price - ap.entry_price) / ap.entry_price) * 100 
        ELSE 0 
    END as peak_profit_pct,
    CASE 
        WHEN ap.entry_price > 0 
        THEN ((ap.current_price - ap.entry_price) / ap.entry_price) * 100 
        ELSE 0 
    END as current_profit_pct,
    ap.partial_taken,
    ap.breakeven_armed,
    ap.trail_price,
    ap.trail_level,
    ap.state_change_count,
    EXTRACT(EPOCH FROM (NOW() - ap.entry_time))/60 as age_minutes,
    ap.account_name
FROM active_positions ap
WHERE ap.status = 'open'
ORDER BY ap.entry_time DESC;

-- Success message
SELECT 'Risk State Machine schema deployed successfully' as status;
