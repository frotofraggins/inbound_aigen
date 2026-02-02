-- Migration 010: AI Learning Tables
-- Adds ticker_universe and missed_opportunities tables for Phase 14

-- ============================================================================
-- TICKER UNIVERSE TABLE
-- ============================================================================
-- Stores AI-recommended tickers for trading
-- Updated every 6 hours by ticker_discovery service

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

COMMENT ON TABLE ticker_universe IS 'AI-recommended tickers for trading based on market analysis';
COMMENT ON COLUMN ticker_universe.confidence IS 'AI confidence score 0.0-1.0 for trading viability';
COMMENT ON COLUMN ticker_universe.catalyst IS 'Current market catalyst (news, volume, technical)';
COMMENT ON COLUMN ticker_universe.active IS 'Whether ticker is currently recommended (updated every 6h)';

-- ============================================================================
-- MISSED OPPORTUNITIES TABLE
-- ============================================================================
-- Stores daily analysis of volume surges that were NOT traded
-- Used for learning and threshold optimization

CREATE TABLE IF NOT EXISTS missed_opportunities (
    id SERIAL PRIMARY KEY,
    analysis_date DATE NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    ts TIMESTAMP NOT NULL,
    
    -- What we detected
    volume_ratio DECIMAL(10,4) NOT NULL,
    close_price DECIMAL(12,4) NOT NULL,
    sentiment_score DECIMAL(4,3),
    
    -- Why skipped
    why_skipped TEXT NOT NULL,
    rule_that_blocked TEXT NOT NULL,
    
    -- AI analysis
    real_opportunity BOOLEAN NOT NULL,
    estimated_profit_pct DECIMAL(6,3) NOT NULL,
    should_have_traded BOOLEAN NOT NULL,
    ai_reasoning TEXT NOT NULL,
    suggested_adjustment TEXT NOT NULL,
    
    -- Metadata
    analyzed_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_missed_opportunities_date ON missed_opportunities(analysis_date);
CREATE INDEX idx_missed_opportunities_ticker ON missed_opportunities(ticker);
CREATE INDEX idx_missed_opportunities_should_trade ON missed_opportunities(should_have_traded);
CREATE INDEX idx_missed_opportunities_real_opp ON missed_opportunities(real_opportunity);

COMMENT ON TABLE missed_opportunities IS 'Daily AI analysis of volume surges that were not traded';
COMMENT ON COLUMN missed_opportunities.real_opportunity IS 'AI assessment: was this actually tradeable?';
COMMENT ON COLUMN missed_opportunities.estimated_profit_pct IS 'Estimated P&L if we had traded';
COMMENT ON COLUMN missed_opportunities.should_have_traded IS 'AI verdict: should we have taken this trade?';

-- ============================================================================
-- VIEWS FOR REPORTING
-- ============================================================================

-- Active ticker recommendations
CREATE OR REPLACE VIEW v_active_tickers AS
SELECT 
    ticker,
    sector,
    catalyst,
    confidence,
    expected_volume,
    last_updated
FROM ticker_universe
WHERE active = true
ORDER BY confidence DESC;

COMMENT ON VIEW v_active_tickers IS 'Currently active ticker recommendations sorted by confidence';

-- Daily missed opportunity summary
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

COMMENT ON VIEW v_daily_missed_summary IS 'Daily summary of missed opportunities and potential profit';

-- Ticker-specific missed opportunity patterns
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

COMMENT ON VIEW v_ticker_missed_patterns IS 'Which tickers do we keep missing trades on?';

-- Migration complete
INSERT INTO schema_migrations (version, applied_at) 
VALUES (10, NOW())
ON CONFLICT (version) DO NOTHING;
