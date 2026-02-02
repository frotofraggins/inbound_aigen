#!/usr/bin/env python3
"""
Quick data check - shows row counts and latest timestamps for all tables.
Run this via the db-migration Lambda to verify data is flowing.
"""
import json
import boto3

# Create the query to run
query_sql = """
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
"""

# Create a custom Lambda event with the query
event = {
    "query_mode": True,
    "query": query_sql
}

print("To check data, run this command:")
print()
print("aws lambda invoke \\")
print("  --function-name ops-pipeline-db-migration \\")
print("  --region us-west-2 \\")
print("  --payload '" + json.dumps(event) + "' \\")
print("  /tmp/data_check.json && cat /tmp/data_check.json")
print()
print("This will show row counts and latest timestamps for all tables.")
