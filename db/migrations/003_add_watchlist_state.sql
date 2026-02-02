-- Migration: 003_add_watchlist_state.sql
-- Description: Adds watchlist state table for dynamic stock selection
-- Tracks which stocks are in the active watchlist and their scores

-- ============================================================================
-- WATCHLIST STATE TABLE
-- Maintains current watchlist of top 30 stocks
-- Updated by watchlist engine every 5 minutes
-- ============================================================================
CREATE TABLE IF NOT EXISTS watchlist_state (
    ticker TEXT PRIMARY KEY,
    watch_score DOUBLE PRECISION NOT NULL,
    rank INTEGER NOT NULL,
    
    -- Score components for debugging
    sentiment_pressure DOUBLE PRECISION NULL,
    vol_score DOUBLE PRECISION NULL,
    setup_quality DOUBLE PRECISION NULL,
    trend_alignment INTEGER NULL,
    
    -- Reasons (detailed breakdown)
    reasons JSONB NOT NULL DEFAULT '{}'::JSONB,
    
    -- Watchlist status
    in_watchlist BOOLEAN NOT NULL DEFAULT FALSE,
    entered_at TIMESTAMPTZ NULL,
    
    -- Timestamps
    last_score_update TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for finding active watchlist stocks
CREATE INDEX IF NOT EXISTS idx_watchlist_active 
    ON watchlist_state(in_watchlist, rank) 
    WHERE in_watchlist = TRUE;

-- Index for score-based queries
CREATE INDEX IF NOT EXISTS idx_watchlist_score 
    ON watchlist_state(watch_score DESC);

-- Index for time-based queries
CREATE INDEX IF NOT EXISTS idx_watchlist_computed 
    ON watchlist_state(computed_at DESC);

-- ============================================================================
-- RECORD MIGRATION
-- ============================================================================
INSERT INTO schema_migrations (version, applied_at)
VALUES ('003_add_watchlist_state', NOW())
ON CONFLICT (version) DO NOTHING;
