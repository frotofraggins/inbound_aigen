-- Migration: 002_add_volatility_features.sql
-- Description: Adds computed features table for volatility and technical indicators
-- Computed features are calculated from lane_telemetry data

-- ============================================================================
-- LANE FEATURES TABLE
-- Stores computed technical indicators and volatility metrics
-- Updated by feature computation task every 1-5 minutes
-- ============================================================================
CREATE TABLE IF NOT EXISTS lane_features (
    ticker TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    
    -- Moving averages
    sma20 DOUBLE PRECISION NULL,
    sma50 DOUBLE PRECISION NULL,
    
    -- Volatility metrics
    recent_vol DOUBLE PRECISION NULL,      -- 30-minute rolling volatility
    baseline_vol DOUBLE PRECISION NULL,    -- 2-hour rolling volatility
    vol_ratio DOUBLE PRECISION NULL,       -- recent_vol / baseline_vol
    
    -- Derived metrics
    distance_sma20 DOUBLE PRECISION NULL,  -- (close - sma20) / sma20
    distance_sma50 DOUBLE PRECISION NULL,  -- (close - sma50) / sma50
    trend_state INTEGER NULL,               -- +1 (bullish), 0 (neutral), -1 (bearish)
    
    -- Latest close for reference
    close DOUBLE PRECISION NULL,
    
    -- Metadata
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    PRIMARY KEY (ticker, ts)
);

-- Index for efficient time-series queries
CREATE INDEX IF NOT EXISTS idx_features_ticker_ts 
    ON lane_features(ticker, ts DESC);

-- Index for finding latest features per ticker
CREATE INDEX IF NOT EXISTS idx_features_computed 
    ON lane_features(computed_at DESC);

-- ============================================================================
-- RECORD MIGRATION
-- ============================================================================
INSERT INTO schema_migrations (version, applied_at)
VALUES ('002_add_volatility_features', NOW())
ON CONFLICT (version) DO NOTHING;
