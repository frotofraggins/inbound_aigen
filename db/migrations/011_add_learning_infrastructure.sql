-- Migration 011: Learning Infrastructure
-- Adds feature snapshots and normalized outcomes for Phase 16 learning
-- Priority: P0 - Required for reproducible learning

-- ============================================================================
-- PART A: FEATURE SNAPSHOTS (P0 - Reproducibility)
-- ============================================================================

-- Add snapshots to recommendations table
ALTER TABLE dispatch_recommendations
    ADD COLUMN features_snapshot JSONB,
    ADD COLUMN sentiment_snapshot JSONB;

-- Add snapshots to executions table
ALTER TABLE dispatcher_execution
    ADD COLUMN features_snapshot JSONB,
    ADD COLUMN sentiment_snapshot JSONB;

-- Indexes for efficient querying
CREATE INDEX idx_dispatch_recs_features_gin
    ON dispatch_recommendations USING GIN (features_snapshot);

CREATE INDEX idx_dispatch_recs_sentiment_gin
    ON dispatch_recommendations USING GIN (sentiment_snapshot);

CREATE INDEX idx_dispatcher_exec_features_gin
    ON dispatcher_execution USING GIN (features_snapshot);

CREATE INDEX idx_dispatcher_exec_sentiment_gin
    ON dispatcher_execution USING GIN (sentiment_snapshot);

COMMENT ON COLUMN dispatch_recommendations.features_snapshot IS 
'Frozen technical indicators at decision time - ensures reproducibility';

COMMENT ON COLUMN dispatch_recommendations.sentiment_snapshot IS 
'Frozen sentiment data at decision time - version 1 schema';

-- ============================================================================
-- PART B: NORMALIZED OUTCOMES (P0 - Learning Quality)
-- ============================================================================

-- Add outcome labels to position history
ALTER TABLE position_history
    ADD COLUMN win_loss_label SMALLINT CHECK (win_loss_label IN (-1, 0, 1)),
    ADD COLUMN r_multiple NUMERIC(8,4),
    ADD COLUMN mae_pct NUMERIC(8,4),
    ADD COLUMN mfe_pct NUMERIC(8,4),
    ADD COLUMN holding_minutes INT,
    ADD COLUMN exit_reason_norm VARCHAR(32);

-- Indexes for learning queries
CREATE INDEX idx_position_history_win_loss ON position_history(win_loss_label);
CREATE INDEX idx_position_history_r_multiple ON position_history(r_multiple);
CREATE INDEX idx_position_history_exit_reason ON position_history(exit_reason_norm);

COMMENT ON COLUMN position_history.win_loss_label IS 
'1=win, 0=breakeven, -1=loss - for classification learning';

COMMENT ON COLUMN position_history.r_multiple IS 
'P&L divided by initial risk - risk-adjusted return metric';

COMMENT ON COLUMN position_history.mae_pct IS 
'Maximum Adverse Excursion - worst drawdown during trade';

COMMENT ON COLUMN position_history.mfe_pct IS 
'Maximum Favorable Excursion - best profit during trade';

COMMENT ON COLUMN position_history.holding_minutes IS 
'Total minutes position was held';

COMMENT ON COLUMN position_history.exit_reason_norm IS 
'Normalized exit reason: TAKE_PROFIT, STOP_LOSS, TIME_EXIT, EOD_EXIT, EXPIRE_EXIT, MANUAL_EXIT, ERROR_EXIT';

-- ============================================================================
-- PART C: LEARNING RECOMMENDATIONS TABLE (Phase 16)
-- ============================================================================

CREATE TABLE IF NOT EXISTS learning_recommendations (
    id SERIAL PRIMARY KEY,
    
    -- Parameter being recommended
    parameter_name VARCHAR(100) NOT NULL,
    parameter_path VARCHAR(200) NOT NULL,  -- Supports nested configs
    current_value NUMERIC(12,6) NOT NULL,
    suggested_value NUMERIC(12,6) NOT NULL,
    rollback_value NUMERIC(12,6),
    
    -- Evidence
    sample_size INT NOT NULL,
    confidence DECIMAL(4,3) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    avg_return_if_changed NUMERIC(8,4),
    backtest_sharpe NUMERIC(6,3),
    win_rate_if_changed NUMERIC(5,4),
    trade_count_impact_pct NUMERIC(6,2),
    
    -- Risk assessment
    risk_increase_pct NUMERIC(6,2),
    max_drawdown_impact NUMERIC(6,2),
    downside_risk_note TEXT,
    
    -- Analysis
    analysis_logic TEXT NOT NULL,
    sql_query TEXT,
    recommendation_reason TEXT NOT NULL,
    confidence_interval_lower NUMERIC(8,4),
    confidence_interval_upper NUMERIC(8,4),
    
    -- Approval workflow
    status VARCHAR(20) NOT NULL DEFAULT 'pending' 
        CHECK (status IN ('pending', 'approved', 'rejected', 'applied', 'rolled_back')),
    reviewed_by VARCHAR(50),
    reviewed_at TIMESTAMP,
    applied_at TIMESTAMP,
    
    -- Metadata
    generated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    generated_by VARCHAR(50) NOT NULL DEFAULT 'learning_engine'
);

CREATE INDEX idx_learning_recs_status ON learning_recommendations(status);
CREATE INDEX idx_learning_recs_param ON learning_recommendations(parameter_name);
CREATE INDEX idx_learning_recs_generated ON learning_recommendations(generated_at DESC);

COMMENT ON TABLE learning_recommendations IS 
'AI-generated parameter adjustment suggestions - NEVER auto-applied';

COMMENT ON COLUMN learning_recommendations.parameter_path IS 
'Nested config path like "thresholds.day_trade.confidence_min"';

COMMENT ON COLUMN learning_recommendations.sample_size IS 
'Number of historical trades analyzed - minimum 30 required';

-- ============================================================================
-- PART D: ENHANCED MISSED OPPORTUNITIES (Deterministic Labeling)
-- ============================================================================

-- Add deterministic outcome fields
ALTER TABLE missed_opportunities
    ADD COLUMN ret_15m NUMERIC(8,4),
    ADD COLUMN ret_60m NUMERIC(8,4),
    ADD COLUMN max_favorable_move NUMERIC(8,4),
    ADD COLUMN volume_sustained BOOLEAN,
    ADD COLUMN direction_matched BOOLEAN,
    ADD COLUMN deterministic_opportunity BOOLEAN;

COMMENT ON COLUMN missed_opportunities.ret_15m IS 
'Actual return 15 minutes after skip - deterministic ground truth';

COMMENT ON COLUMN missed_opportunities.ret_60m IS 
'Actual return 60 minutes after skip - deterministic ground truth';

COMMENT ON COLUMN missed_opportunities.deterministic_opportunity IS 
'Rule-based: ret_60m >= threshold AND direction_matched AND volume_sustained';

-- ============================================================================
-- PART E: LEARNING VIEWS (Analysis Helpers)
-- ============================================================================

-- View: Confidence bucket performance
CREATE OR REPLACE VIEW v_confidence_performance AS
SELECT 
    FLOOR(confidence * 20) / 20 as confidence_bucket,  -- 0.05 increments
    COUNT(*) as trades,
    AVG(final_pnl_percent) as avg_return_pct,
    STDDEV(final_pnl_percent) as return_volatility,
    AVG(r_multiple) as avg_r_multiple,
    COUNT(*) FILTER (WHERE win_loss_label = 1) / NULLIF(COUNT(*), 0)::FLOAT as win_rate,
    AVG(holding_minutes) as avg_hold_min,
    COUNT(*) FILTER (WHERE exit_reason_norm = 'TAKE_PROFIT') as profit_exits,
    COUNT(*) FILTER (WHERE exit_reason_norm = 'STOP_LOSS') as loss_exits
FROM dispatch_recommendations dr
JOIN dispatcher_execution de ON dr.id = de.recommendation_id
JOIN position_history ph ON de.id = ph.execution_id
WHERE ph.closed_at IS NOT NULL
GROUP BY confidence_bucket
HAVING COUNT(*) >= 5
ORDER BY confidence_bucket DESC;

COMMENT ON VIEW v_confidence_performance IS 
'Performance metrics by confidence level - for threshold calibration';

-- View: Sentiment alignment effectiveness
CREATE OR REPLACE VIEW v_sentiment_effectiveness AS
SELECT 
    (sentiment_snapshot->>'direction') as sentiment_direction,
    (features_snapshot->>'trend_state')::INT as trend_state,
    CASE 
        WHEN (sentiment_snapshot->>'direction' = 'bullish' AND 
              (features_snapshot->>'trend_state')::INT = 1) THEN true
        WHEN (sentiment_snapshot->>'direction' = 'bearish' AND 
              (features_snapshot->>'trend_state')::INT = -1) THEN true
        ELSE false
    END as alignment,
    COUNT(*) as trades,
    AVG(final_pnl_percent) as avg_return,
    AVG(r_multiple) as avg_r,
    COUNT(*) FILTER (WHERE win_loss_label = 1) / NULLIF(COUNT(*), 0)::FLOAT as win_rate
FROM dispatch_recommendations dr
JOIN dispatcher_execution de ON dr.id = de.recommendation_id
JOIN position_history ph ON de.id = ph.execution_id
WHERE ph.closed_at IS NOT NULL
  AND sentiment_snapshot IS NOT NULL
GROUP BY sentiment_direction, trend_state, alignment;

COMMENT ON VIEW v_sentiment_effectiveness IS 
'Does sentiment alignment actually improve returns?';

-- View: Volume surge performance
CREATE OR REPLACE VIEW v_volume_edge AS
SELECT 
    CASE 
        WHEN (features_snapshot->>'volume_ratio')::NUMERIC >= 2.0 THEN 'Surge (>=2x)'
        WHEN (features_snapshot->>'volume_ratio')::NUMERIC >= 1.5 THEN 'Strong (1.5-2x)'
        WHEN (features_snapshot->>'volume_ratio')::NUMERIC >= 1.0 THEN 'Normal (1-1.5x)'
        ELSE 'Weak (<1x)'
    END as volume_category,
    COUNT(*) as trades,
    AVG(final_pnl_percent) as avg_return,
    AVG(r_multiple) as avg_r,
    COUNT(*) FILTER (WHERE win_loss_label = 1) / NULLIF(COUNT(*), 0)::FLOAT as win_rate,
    AVG(holding_minutes) as avg_hold_min
FROM dispatch_recommendations dr
JOIN dispatcher_execution de ON dr.id = de.recommendation_id  
JOIN position_history ph ON de.id = ph.execution_id
WHERE ph.closed_at IS NOT NULL
  AND features_snapshot IS NOT NULL
GROUP BY volume_category
HAVING COUNT(*) >= 3;

COMMENT ON VIEW v_volume_edge IS 
'Does volume surge actually predict better trades?';

-- View: Options vs stocks performance
CREATE OR REPLACE VIEW v_instrument_performance AS
SELECT 
    instrument_type,
    strategy_type,
    COUNT(*) as trades,
    AVG(final_pnl_percent) as avg_return,
    AVG(r_multiple) as avg_r,
    STDDEV(r_multiple) as r_volatility,
    COUNT(*) FILTER (WHERE win_loss_label = 1) / NULLIF(COUNT(*), 0)::FLOAT as win_rate,
    AVG(holding_minutes) as avg_hold_min,
    AVG(mae_pct) as avg_max_drawdown,
    COUNT(*) FILTER (WHERE exit_reason_norm = 'TAKE_PROFIT') as profit_exits,
    COUNT(*) FILTER (WHERE exit_reason_norm = 'STOP_LOSS') as loss_exits
FROM dispatcher_execution de
JOIN position_history ph ON de.id = ph.execution_id
WHERE ph.closed_at IS NOT NULL
GROUP BY instrument_type, strategy_type;

COMMENT ON VIEW v_instrument_performance IS 
'Comparative performance: options vs stocks, day trades vs swings';

-- ============================================================================
-- PART F: BACKFILL HELPER FUNCTION
-- ============================================================================

-- Function to compute normalized outcomes for existing positions
CREATE OR REPLACE FUNCTION backfill_normalized_outcomes()
RETURNS TABLE (position_id INT, updated BOOLEAN, reason TEXT) AS $$
BEGIN
    RETURN QUERY
    UPDATE position_history ph
    SET 
        -- Win/loss label
        win_loss_label = CASE 
            WHEN final_pnl_percent > 0.5 THEN 1   -- Win
            WHEN final_pnl_percent < -0.5 THEN -1  -- Loss
            ELSE 0                                 -- Breakeven
        END,
        
        -- Holding time
        holding_minutes = EXTRACT(EPOCH FROM (closed_at - entry_time)) / 60,
        
        -- Exit reason normalization (from sim_json or explain_json)
        exit_reason_norm = CASE exit_reason
            WHEN 'stop_loss' THEN 'STOP_LOSS'
            WHEN 'take_profit' THEN 'TAKE_PROFIT'
            WHEN 'max_hold_time' THEN 'TIME_EXIT'
            WHEN 'day_trade_close' THEN 'EOD_EXIT'
            WHEN 'expiration_risk' THEN 'EXPIRE_EXIT'
            WHEN 'manual_close' THEN 'MANUAL_EXIT'
            ELSE 'TIME_EXIT'
        END
    WHERE win_loss_label IS NULL  -- Only update unprocessed
    RETURNING id, true, 'Normalized outcomes computed';
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION backfill_normalized_outcomes IS 
'Backfill normalized outcome labels for existing positions';

-- ============================================================================
-- VALIDATION QUERIES
-- ============================================================================

-- Check snapshot coverage
CREATE OR REPLACE VIEW v_snapshot_coverage AS
SELECT 
    'recommendations' as table_name,
    COUNT(*) as total_rows,
    COUNT(features_snapshot) as with_features,
    COUNT(sentiment_snapshot) as with_sentiment,
    (COUNT(features_snapshot)::FLOAT / NULLIF(COUNT(*), 0) * 100)::NUMERIC(5,2) as features_coverage_pct,
    (COUNT(sentiment_snapshot)::FLOAT / NULLIF(COUNT(*), 0) * 100)::NUMERIC(5,2) as sentiment_coverage_pct
FROM dispatch_recommendations
UNION ALL
SELECT 
    'executions' as table_name,
    COUNT(*) as total_rows,
    COUNT(features_snapshot) as with_features,
    COUNT(sentiment_snapshot) as with_sentiment,
    (COUNT(features_snapshot)::FLOAT / NULLIF(COUNT(*), 0) * 100)::NUMERIC(5,2) as features_coverage_pct,
    (COUNT(sentiment_snapshot)::FLOAT / NULLIF(COUNT(*), 0) * 100)::NUMERIC(5,2) as sentiment_coverage_pct
FROM dispatcher_execution;

COMMENT ON VIEW v_snapshot_coverage IS 
'Monitor feature snapshot adoption - should reach 100% after deployment';

-- Check outcome normalization coverage  
CREATE OR REPLACE VIEW v_outcome_normalization_coverage AS
SELECT 
    COUNT(*) as total_closed_positions,
    COUNT(win_loss_label) as with_win_loss,
    COUNT(r_multiple) as with_r_multiple,
    COUNT(mae_pct) as with_mae,
    COUNT(holding_minutes) as with_holding_time,
    COUNT(exit_reason_norm) as with_norm_exit,
    (COUNT(win_loss_label)::FLOAT / NULLIF(COUNT(*), 0) * 100)::NUMERIC(5,2) as normalization_pct
FROM position_history
WHERE closed_at IS NOT NULL;

COMMENT ON VIEW v_outcome_normalization_coverage IS 
'Monitor outcome normalization - backfill if < 100%';

-- ============================================================================
-- ROLLBACK PLAN
-- ============================================================================

-- To rollback this migration:
/*
ALTER TABLE dispatch_recommendations
    DROP COLUMN IF EXISTS features_snapshot,
    DROP COLUMN IF EXISTS sentiment_snapshot;

ALTER TABLE dispatcher_execution
    DROP COLUMN IF EXISTS features_snapshot,
    DROP COLUMN IF EXISTS sentiment_snapshot;

ALTER TABLE position_history
    DROP COLUMN IF EXISTS win_loss_label,
    DROP COLUMN IF EXISTS r_multiple,
    DROP COLUMN IF EXISTS mae_pct,
    DROP COLUMN IF EXISTS mfe_pct,
    DROP COLUMN IF EXISTS holding_minutes,
    DROP COLUMN IF EXISTS exit_reason_norm;

DROP TABLE IF EXISTS learning_recommendations CASCADE;
DROP VIEW IF EXISTS v_snapshot_coverage CASCADE;
DROP VIEW IF EXISTS v_outcome_normalization_coverage CASCADE;
DROP FUNCTION IF EXISTS backfill_normalized_outcomes();
*/

-- Migration complete
INSERT INTO schema_migrations (version, applied_at) 
VALUES (11, NOW())
ON CONFLICT (version) DO NOTHING;
