-- Migration 1004: Add VIX regime tracking
-- Purpose: Track market volatility and regime changes for risk management
-- Date: 2026-02-07

-- Create vix_history table
CREATE TABLE IF NOT EXISTS vix_history (
    id SERIAL PRIMARY KEY,
    vix_value DECIMAL(10, 2) NOT NULL,
    regime VARCHAR(20) NOT NULL,  -- 'complacent', 'normal', 'elevated', 'high', 'extreme'
    risk_level INTEGER NOT NULL,  -- 1 (low) to 5 (extreme)
    position_size_multiplier DECIMAL(5, 2) NOT NULL,  -- 0.0 to 1.0
    new_trades_allowed BOOLEAN NOT NULL DEFAULT TRUE,
    confidence_adjustment DECIMAL(5, 2) NOT NULL,  -- Multiplier for signal confidence
    regime_message TEXT,
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Index for fast latest regime lookups
CREATE INDEX IF NOT EXISTS idx_vix_history_recorded_at ON vix_history(recorded_at DESC);

-- Index for regime queries
CREATE INDEX IF NOT EXISTS idx_vix_history_regime ON vix_history(regime, recorded_at DESC);

-- Verify table created
SELECT 
    column_name, 
    data_type, 
    is_nullable
FROM information_schema.columns 
WHERE table_name = 'vix_history'
ORDER BY ordinal_position;
