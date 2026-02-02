# How to Run Queries via Lambda

**Lambda Function:** `ops-pipeline-db-query`  
**Purpose:** Execute read-only SQL queries against private RDS

---

## Basic Usage

```bash
aws lambda invoke \
  --function-name ops-pipeline-db-query \
  --region us-west-2 \
  --payload '{"sql":"YOUR_SQL_QUERY_HERE"}' \
  /tmp/result.json

cat /tmp/result.json | jq -r '.body' | jq
```

---

## Daily Health Check (Use This)

```bash
aws lambda invoke \
  --function-name ops-pipeline-db-query \
  --region us-west-2 \
  --payload '{"sql":"SELECT EXTRACT(EPOCH FROM (NOW() - (SELECT MAX(ts) FROM lane_telemetry)))::int AS telem_lag, EXTRACT(EPOCH FROM (NOW() - (SELECT MAX(computed_at) FROM lane_features)))::int AS feat_lag, (SELECT COUNT(*) FROM dispatcher_runs WHERE finished_at IS NULL AND started_at < NOW() - INTERVAL '\''5 minutes'\'') AS unfinished, (SELECT COUNT(*) FROM (SELECT recommendation_id FROM dispatch_executions GROUP BY recommendation_id HAVING COUNT(*) > 1) x) AS duplicates"}' \
  /tmp/health.json

cat /tmp/health.json | jq -r '.body' | jq '.rows[0]'
```

**Expected Output:**
```json
{
  "telem_lag": 150,
  "feat_lag": 45,
  "unfinished": 0,
  "duplicates": 0
}
```

**Pass Criteria:**
- telem_lag < 180
- feat_lag < 600
- unfinished = 0
- duplicates = 0

---

## Example Queries

### Check Row Counts
```bash
aws lambda invoke \
  --function-name ops-pipeline-db-query \
  --region us-west-2 \
  --payload '{"sql":"SELECT '\''inbound_events'\'' as table_name, COUNT(*) FROM inbound_events_raw UNION ALL SELECT '\''telemetry'\'', COUNT(*) FROM lane_telemetry UNION ALL SELECT '\''features'\'', COUNT(*) FROM lane_features"}' \
  /tmp/counts.json

cat /tmp/counts.json | jq -r '.body' | jq
```

### Check Watchlist
```bash
aws lambda invoke \
  --function-name ops-pipeline-db-query \
  --region us-west-2 \
  --payload '{"sql":"SELECT ticker, watch_score, in_watchlist FROM watchlist_state WHERE in_watchlist = TRUE ORDER BY watch_score DESC"}' \
  /tmp/watchlist.json

cat /tmp/watchlist.json | jq -r '.body' | jq '.rows'
```

### Check Recent Signals
```bash
aws lambda invoke \
  --function-name ops-pipeline-db-query \
  --region us-west-2 \
  --payload '{"sql":"SELECT ticker, action, instrument_type, confidence, ts FROM dispatch_recommendations WHERE ts >= NOW() - INTERVAL '\''1 hour'\'' ORDER BY ts DESC LIMIT 10"}' \
  /tmp/signals.json

cat /tmp/signals.json | jq -r '.body' | jq '.rows'
```

### Check Dispatcher Runs
```bash
aws lambda invoke \
  --function-name ops-pipeline-db-query \
  --region us-west-2 \
  --payload '{"sql":"SELECT started_at, finished_at, pulled_count, simulated_count, skipped_count FROM dispatcher_runs ORDER BY started_at DESC LIMIT 5"}' \
  /tmp/runs.json

cat /tmp/runs.json | jq -r '.body' | jq '.rows'
```

---

## Troubleshooting

### Lambda Returns Error
```bash
# Check Lambda logs
aws logs filter-log-events \
  --log-group-name /aws/lambda/ops-pipeline-db-query \
  --start-time $(($(date +%s) - 600))000 \
  --region us-west-2 \
  --max-items 20
```

### Query Syntax Error
- Single quotes in SQL must be escaped: `'\''`
- Example: `'5 minutes'` becomes `'\''5 minutes'\''`

### Common Mistakes
❌ `--payload '{"sql":"SELECT * FROM table"}'`  
✅ `--payload '{"sql":"SELECT * FROM table"}'` (ensure proper quoting)

---

## Safety

**Lambda only allows SELECT queries.** Any other SQL will be rejected.

This protects the database from accidental modifications during validation.

---

## Quick Reference

**Lambda ARN:** `arn:aws:lambda:us-west-2:160027201036:function:ops-pipeline-db-query`  
**VPC:** Attached (can reach private RDS)  
**Timeout:** 15 seconds  
**Memory:** 256 MB

**Daily health check:** Run the health check query once per day and document results.
