-- Migration 1036: Backfill entry_features_json for open positions
-- Matches active_positions to dispatch_recommendations via ticker + entry_price
-- This populates features so when positions close, position_history gets real data

UPDATE active_positions ap
SET entry_features_json = sub.features_snapshot
FROM (
    SELECT DISTINCT ON (ap2.id)
        ap2.id as position_id,
        dr.features_snapshot
    FROM active_positions ap2
    JOIN dispatch_executions de
        ON de.ticker = ap2.ticker
        AND de.execution_mode IN ('ALPACA_PAPER', 'LIVE')
        AND ABS(de.entry_price::float - ap2.entry_price::float) < 0.01
    JOIN dispatch_recommendations dr
        ON dr.id = de.recommendation_id
        AND dr.features_snapshot IS NOT NULL
    WHERE ap2.status = 'open'
      AND (ap2.entry_features_json IS NULL OR ap2.entry_features_json = '{}'::jsonb)
    ORDER BY ap2.id, de.simulated_ts DESC
) sub
WHERE ap.id = sub.position_id;
