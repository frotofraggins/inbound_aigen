# Day 1 Acceptance Criteria
## Validate System Before 7-Day Shakedown

**Run these checks TODAY to establish baseline health.**

All queries run from Lambda (db-migration Lambda or create a query Lambda).

---

## Acceptance Criteria (All Must Pass)

### ✅ 1. No Backlog Growth
```sql
-- Current state distribution
SELECT status, COUNT(*) 
FROM dispatch_recommendations
GROUP BY status
ORDER BY status;
```

**Pass Criteria:**
- PENDING: 0-20 (normal accumulation between runs)
- SIMULATED: Any count (shows dispatcher working)
- SKIPPED: Any count (gates working)
- PROCESSING: 0 (must be zero)
- FAILED: 0-5 (occasional ok)

**Fail If:** PENDING > 100 OR PROCESSING > 0

---

### ✅ 2. No Stuck Processing
```sql
-- Stuck PROCESSING rows (should be 0)
SELECT COUNT(*) AS stuck_processing
FROM dispatch_recommendations
WHERE status = 'PROCESSING'
  AND created_at < NOW() - INTERVAL '10 minutes';
```

**Pass Criteria:** Result = 0

**Fail If:** Result > 0 (reaper not working)

---

### ✅ 3. Idempotency Holds (No Duplicates)
```sql
-- Duplicate executions (should be 0)
SELECT recommendation_id, COUNT(*) as exec_count
FROM dispatch_executions
GROUP BY recommendation_id
HAVING COUNT(*) > 1;
```

**Pass Criteria:** No rows returned

**Fail If:** Any rows (UNIQUE constraint failed somehow)

---

### ✅ 4. Freshness Gates Working
```sql
-- Check bar age in recent executions
SELECT
  ticker,
  simulated_ts,
  sim_json->'bar_used'->>'timestamp' as bar_timestamp,
  EXTRACT(EPOCH FROM (
    simulated_ts - (sim_json->'bar_used'->>'timestamp')::timestamptz
  )) AS bar_age_seconds
FROM dispatch_executions
WHERE simulated_ts >= NOW() - INTERVAL '1 hour'
ORDER BY simulated_ts DESC
LIMIT 10;
```

**Pass Criteria:** All bar_age_seconds < 120

**Fail If:** Any > 120 (freshness gate not enforcing)

---

### ✅ 5. Dispatcher Runs Completing
```sql
-- Recent dispatcher runs
SELECT 
  started_at,
  finished_at,
  pulled_count,
  simulated_count,
  skipped_count,
  failed_count,
  EXTRACT(EPOCH FROM (finished_at - started_at)) as duration_seconds
FROM dispatcher_runs
ORDER BY started_at DESC
LIMIT 10;
```

**Pass Criteria:**
- All runs have finished_at (not NULL)
- Duration: 2-30 seconds
- At least 1 run in last 5 minutes

**Fail If:** No recent runs OR any NULL finished_at

---

### ✅ 6. Execution Volumes Make Sense
```sql
-- Today's execution summary
SELECT 
  COUNT(*) as total_executions,
  COUNT(DISTINCT ticker) as unique_tickers,
  MIN(simulated_ts) as first_execution,
  MAX(simulated_ts) as last_execution
FROM dispatch_executions
WHERE simulated_ts >= CURRENT_DATE;
```

**Pass Criteria:**
- total_executions: 0-100 (0 is ok on first day)
- unique_tickers: 0-30

**Fail If:** total_executions > 200 (likely duplicate execution bug)

---

### ✅ 7. Signal Generation Working
```sql
-- Signals created in last hour
SELECT 
  COUNT(*) as signals_last_hour,
  COUNT(DISTINCT ticker) as unique_tickers
FROM dispatch_recommendations
WHERE ts >= NOW() - INTERVAL '1 hour';
```

**Pass Criteria:**
- signals_last_hour: 1-60 (during market hours)
- signals_last_hour: 0 (acceptable outside market hours)

**Fail If:** 0 signals during 10am-3pm ET (signal engine not working)

---

### ✅ 8. Cost Validation
```bash
# Check ECS task counts
aws ecs list-tasks --cluster ops-pipeline-cluster --region us-west-2

# Check recent CloudWatch costs (next day)
aws ce get-cost-and-usage \
  --time-period Start=2026-01-12,End=2026-01-14 \
  --granularity DAILY \
  --metrics UnblendedCost \
  --region us-west-2
```

**Pass Criteria:**
- No tasks running (all scheduled, none persistent)
- Daily cost < $2 (monthly ~$35-40)

**Fail If:** Persistent tasks running OR daily cost > $5

---

## If Any Check Fails

### PROCESSING stuck:
- Check dispatcher logs for errors
- Verify reaper is running (should see log event)
- Lower processing_ttl_minutes if needed

### Duplicates found:
- CRITICAL BUG - Check for race condition
- Verify UNIQUE constraint exists:
  ```sql
  SELECT indexname, indexdef 
  FROM pg_indexes 
  WHERE tablename = 'dispatch_executions' 
  AND indexname = 'ux_dispatch_execution_reco';
  ```

### Freshness violations:
- Check if bars/features are updating
- Review gate threshold (may need to relax if data lag is structural)
- Check dispatcher logs for freshness gate failures

### No signals:
- Check Signal Engine logs
- Verify watchlist has data
- Check if market is open

### Cost spike:
- Check for persistent tasks (should be 0)
- Verify schedules are correct (not running every second)
- Look for NAT gateway (should be $0)

---

## Day 1 Success Criteria

**All 8 checks pass = System is healthy.**

Document results:
```
Day 1 Results:
- Backlog state: PENDING=5, SIMULATED=12, SKIPPED=48
- Stuck processing: 0 ✅
- Duplicate executions: 0 ✅
- Freshness violations: 0 ✅
- Dispatcher runs: 45 completed in last hour ✅
- Execution count: 12 today ✅
- Signal generation: 60 signals last hour ✅
- Cost check: No persistent tasks ✅

Status: PASS - System is healthy
```

---

## If All Pass: Enter Observation Mode

For next 6 days:
1. Run backlog + stuck processing queries daily
2. Check dispatcher_runs once daily
3. Spot-check execution volumes
4. **Do not change code**
5. Only tune SSM config if clearly needed

---

## After 7 Clean Days

You've **proven the system runs unattended**.

Then choose:
- **Path A:** Add monitoring/alerts (operational safety)
- **Path B:** Add outcome tracking (ML prep)
- **Path C:** Expand universe (more opportunities)

**Recommendation:** Path A first. You can't improve what you can't see failing.

---

**Run these 8 checks now. Save the results. This is your Day 1 baseline.**
