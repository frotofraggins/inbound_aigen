-- Quick Data Check - Run via Lambda to verify pipeline is collecting data
-- This shows row counts across all tables to confirm services are writing

SELECT 'inbound_events_raw' as table_name, COUNT(*) as row_count, 
       MAX(fetched_at) as latest_timestamp
FROM inbound_events_raw
UNION ALL
SELECT 'inbound_events_classified', COUNT(*), MAX(created_at)
FROM inbound_events_classified
UNION ALL
SELECT 'lane_telemetry', COUNT(*), MAX(ts)
FROM lane_telemetry
UNION ALL
SELECT 'lane_features', COUNT(*), MAX(computed_at)
FROM lane_features
UNION ALL
SELECT 'watchlist_state', COUNT(*), MAX(computed_at)
FROM watchlist_state
UNION ALL
SELECT 'dispatch_recommendations', COUNT(*), MAX(ts)
FROM dispatch_recommendations
UNION ALL
SELECT 'dispatch_executions', COUNT(*), MAX(simulated_ts)
FROM dispatch_executions
UNION ALL
SELECT 'dispatcher_runs', COUNT(*), MAX(started_at)
FROM dispatcher_runs
ORDER BY table_name;
