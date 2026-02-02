-- Migration 013: Phase 3 Improvements
-- Adds support for trailing stops, IV rank tracking, and entry price tracking
-- Created: 2026-01-29

BEGIN;

-- Add columns for trailing stop support
ALTER TABLE active_positions 
ADD COLUMN IF NOT EXISTS peak_price DECIMAL(12, 4),
ADD COLUMN IF NOT EXISTS trailing_stop_price DECIMAL(12, 4),
ADD COLUMN IF NOT EXISTS entry_underlying_price DECIMAL(12, 4),
ADD COLUMN IF NOT EXISTS original_quantity INTEGER;

-- Add IV rank tracking to ticker_features
ALTER TABLE ticker_features_1m
ADD COLUMN IF NOT EXISTS iv_rank DECIMAL(5, 4);

-- Create IV history table for IV rank calculations
CREATE TABLE IF NOT EXISTS iv_history (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    implied_volatility DECIMAL(8, 6),
    recorded_at TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(ticker, recorded_at)
);

CREATE INDEX IF NOT EXISTS idx_iv_history_ticker_date 
ON iv_history(ticker, recorded_at DESC);

-- Add partial exit tracking
ALTER TABLE position_events
ADD COLUMN IF NOT EXISTS partial_quantity INTEGER,
ADD COLUMN IF NOT EXISTS remaining_quantity INTEGER;

COMMIT;
