# Ops Pipeline Operations Runbook

**Last Updated:** 2026-01-30  
**Owner:** Operations  
**Purpose:** Single source of truth for troubleshooting and maintenance

---

## Quick Health Check (30 seconds)

```bash
# 1. Check schedules enabled
aws scheduler list-schedules --region us-west-2 --query 'Schedules[?contains(Name,`ops-pipeline`)].{Name:Name,State:State}'
aws events list-rules --region us-west-2 --query 'Rules[?contains(Name,`ops-pipeline`)].{Name:Name,State:State}'

# 2. Check no persistent tasks (should be empty)
aws ecs list-tasks --cluster ops-pipeline-cluster --region us-west-2

# 3. Check recent logs exist
aws logs describe-log-groups --log-group-name-prefix /ecs/ops-pipeline --region us-west-2
```

**Normal:** 7 schedules ENABLED, 0 persistent tasks, 7 log groups

---

## Service Health Checks

### Check If Service Executed Recently

```bash
# Replace {SERVICE} with: rss-ingest, classifier-worker, telemetry-1m, 
# feature-computer-1m, watchlist-engine-5m, signal-engine-1m, dispatcher

aws logs filter-log-events \
  --log-group-name /ecs/ops-pipeline/{SERVICE} \
  --start-time $(($(date +%s) - 600))000 \
  --region us-west-2 \
  --max-items 5
```

**Normal:** Logs within last 5-10 minutes  
**Problem:** No logs = service not running

### Check RDS Connectivity

```bash
# Via db-migration Lambda
aws lambda invoke \
  --function-name ops-pipeline-db-migration \
  --region us-west-2 \
  /tmp/db_test.json

cat /tmp/db_test.json
```

**Normal:** Success with table list  
**Problem:** Timeout or connection error

---

## Acceptance Queries (Run Via Lambda)

### Query 1: Backlog State
```sql
SELECT status, COUNT(*) 
FROM dispatch_recommendations
GROUP BY status
ORDER BY status;
```

**Normal:**
- PENDING: 0-20
- SIMULATED: 10-200
- SKIPPED: 50-500
- PROCESSING: 0

**Problem:** PROCESSING > 0 for > 10 min

### Query 2: Stuck Processing
```sql
SELECT COUNT(*) 
FROM dispatch_recommendations
WHERE status = 'PROCESSING' 
  AND ts < NOW() - INTERVAL '10 minutes';
```

**Normal:** 0  
**Problem:** > 0 (reaper not working)

### Query 3: Duplicate Executions
```sql
SELECT recommendation_id, COUNT(*) 
FROM dispatch_executions
GROUP BY recommendation_id
HAVING COUNT(*) > 1;
```

**Normal:** Empty result  
**Problem:** Any rows (CRITICAL - idempotency broken)

### Query 4: Recent Dispatcher Runs
```sql
SELECT 
  started_at,
  finished_at,
  pulled_count,
  simulated_count,
  skipped_count,
  failed_count
FROM dispatcher_runs
ORDER BY started_at DESC
LIMIT 10;
```

**Normal:** All have finished_at, duration 2-10s  
**Problem:** NULL finished_at or no recent runs

### Query 5: Execution Volume
```sql
SELECT COUNT(*) 
FROM dispatch_executions
WHERE simulated_ts >= CURRENT_DATE;
```

**Normal:** 0-100 per day  
**Problem:** > 200 (runaway execution) OR 0 for 24+ hours (stall)

---

## Common Issues & Fixes

### Issue: No Logs Generated

**Symptoms:** Log groups don't exist after 15 minutes

**Check:**
1. Schedules enabled? (see Quick Health Check)
2. IAM role has CloudWatch Logs permissions?
3. ECS tasks failing to start?

**Fix:**
```bash
# Check schedule history
aws events describe-rule --name ops-pipeline-{SERVICE}-schedule --region us-west-2

# Check for ECS task failures
aws ecs describe-tasks --cluster ops-pipeline-cluster --tasks {TASK_ARN} --region us-west-2
```

---

### Issue: Backlog Growing (PENDING Accumulating)

**Symptoms:** PENDING count increases hour over hour

**Check:**
1. Is dispatcher running? (check dispatcher_runs table)
2. Are gates too strict? (check SKIPPED reasons)
3. Is max_signals_per_run too low?

**Fix:**
```sql
-- Check gate failures
SELECT 
  risk_gate_json->'confidence'->>'reason' as reason,
  COUNT(*)
FROM dispatch_recommendations
WHERE status = 'SKIPPED'
GROUP BY 1
ORDER BY 2 DESC;
```

If confidence gate blocking most:
```bash
aws ssm put-parameter \
  --name /ops-pipeline/dispatcher_config \
  --value '{"confidence_min": 0.60}' \
  --overwrite \
  --region us-west-2
```

---

### Issue: No Trades Happening (Signals SKIPPED)

**Symptoms:** Dispatcher logs show `recommendations_claimed` but all SKIPPED, or no PENDING within the last 60 minutes.

**Most common causes:**
1. **Trading-hours gate** (outside 9:30–16:00 ET, or in 9:30–9:35 / 15:45–16:00 blocks)
2. **Confidence gate** (especially tiny tier min confidence = 0.60)
3. **Shorting disabled** (if allow_shorting=false)

**Check:**
```sql
-- Recent skip reasons (last 30 minutes)
SELECT failure_reason, COUNT(*) 
FROM dispatch_recommendations
WHERE status = 'SKIPPED'
  AND ts >= NOW() - INTERVAL '30 minutes'
GROUP BY failure_reason
ORDER BY COUNT(*) DESC;
```

**If trading_hours is the blocker:**
- Wait until market opens (after 9:35 AM ET)
- Verify time in ET: `date` (UTC) → convert to ET

**If confidence is the blocker (tiny tier):**
- Current tiny thresholds enforce `min_confidence = 0.60`
- Lowering thresholds increases trade frequency but raises risk

---

### Issue: Trade-Stream WebSocket Not Running

**Symptoms:** trade-stream ECS task exits or no real-time position sync.

**Common causes:**
1. **Secrets Manager references** (ALPACA or DB secrets incorrect)
2. **DB host mismatch** (must match `/ops-pipeline/db_host`)
3. **Stale image cache** (rebuild with `--no-cache`)

**Check:**
```bash
aws ecs describe-services --cluster ops-pipeline-cluster --services trade-stream --region us-west-2
aws logs tail /ecs/ops-pipeline/trade-stream --region us-west-2 --since 10m
aws ssm get-parameter --name /ops-pipeline/db_host --region us-west-2
```

**Fix (summary):**
- Ensure trade-stream task definition uses:
  - `ops-pipeline/alpaca` secret keys for `ALPACA_API_KEY` / `ALPACA_API_SECRET`
  - `ops-pipeline/db` secret keys for `DB_USER` / `DB_PASSWORD`
  - `DB_HOST` set to `/ops-pipeline/db_host`
- Rebuild and push image with `--no-cache`, then redeploy.

---

### Issue: Stuck PROCESSING Rows

**Symptoms:** COUNT(*) > 0 from stuck processing query

**Check:**
1. Is reaper running? (check dispatcher logs for "stuck_processing_released")
2. Is processing_ttl_minutes too high?

**Fix:**
```bash
# Lower TTL to 5 minutes
aws ssm put-parameter \
  --name /ops-pipeline/dispatcher_config \
  --value '{"processing_ttl_minutes": 5}' \
  --overwrite \
  --region us-west-2
```

---

### Issue: No Executions (All SKIPPED)

**Symptoms:** dispatcher runs but simulated_count always 0

**Check:**
```sql
-- See which gates failing
SELECT 
  risk_gate_json
FROM dispatch_recommendations
WHERE status = 'SKIPPED'
ORDER BY processed_at DESC
LIMIT 5;
```

**Common causes:**
- Confidence too low (all signals < 0.70)
- Data stale (bars/features too old)
- Daily limits hit

**Fix:** Review gate_results, adjust thresholds via SSM

---

### Issue: Duplicate Executions (CRITICAL)

**Symptoms:** Query 3 returns rows

**This is a critical bug. DO NOT ignore.**

**Immediate action:**
1. Disable dispatcher schedule:
   ```bash
   aws scheduler update-schedule \
     --name ops-pipeline-dispatcher \
     --state DISABLED \
     --region us-west-2
   ```

2. Investigate:
   - Check UNIQUE constraint exists
   - Review dispatcher logs for errors
   - Check for race conditions

3. Do not re-enable until fixed

---

### Issue: Data Freshness Violations

**Symptoms:** Executions using bars > 120s old

**Check:**
```sql
SELECT 
  ticker,
  simulated_ts,
  sim_json->'bar_used'->>'timestamp' as bar_ts,
  EXTRACT(EPOCH FROM (simulated_ts - (sim_json->'bar_used'->>'timestamp')::timestamptz)) as age_sec
FROM dispatch_executions
WHERE simulated_ts >= NOW() - INTERVAL '1 hour'
ORDER BY age_sec DESC
LIMIT 10;
```

**Causes:**
- Telemetry service not running
- Alpaca API issues
- Clock skew

**Fix:**
1. Check telemetry service logs
2. Verify Alpaca API responding
3. May need to relax max_bar_age_seconds temporarily

---

### Issue: Service Won't Start

**Symptoms:** Schedule enabled but no tasks running, no logs

**Check:**
1. VPC/subnet/security group correct?
2. Task definition valid?
3. Image exists in ECR?

**Debug:**
```bash
# Check task definition
aws ecs describe-task-definition \
  --task-definition ops-pipeline-{SERVICE} \
  --region us-west-2

# Check ECR image exists
aws ecr describe-images \
  --repository-name ops-pipeline/{SERVICE} \
  --region us-west-2

# Try manual run
aws ecs run-task \
  --cluster ops-pipeline-cluster \
  --task-definition ops-pipeline-{SERVICE}:1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-0c182a149eeef918a],securityGroups=[sg-0cd16a909f4e794ce],assignPublicIp=ENABLED}" \
  --region us-west-2
```

---

### Issue: RDS Connection Timeout

**Symptoms:** Services log "connection timeout" to RDS

**Check:**
1. Security group allows inbound from ECS security group?
2. RDS in correct VPC/subnets?
3. VPC endpoints for SSM/Secrets working?

**Fix:**
```bash
# Check RDS security group
aws ec2 describe-security-groups \
  --group-ids sg-09379d105ed7901a9 \
  --region us-west-2

# Should allow inbound 5432 from sg-0cd16a909f4e794ce
```

---

## Normal Operating Ranges

### Daily Volumes (Market Hours)
- RSS items fetched: 50-200
- Sentiment classifications: 50-200
- Telemetry bars: 5,000-10,000 (7 tickers × 390 minutes × 1.2)
- Feature computations: 7 tickers per minute
- Watchlist updates: 12 per hour (every 5 min)
- Signals generated: 10-100
- Executions simulated: 5-50
- Executions skipped: 20-200

### Performance Baselines
- RSS ingest: < 10s
- Classifier: < 30s (with FinBERT)
- Telemetry: < 10s
- Feature computer: < 5s
- Watchlist: < 15s
- Signal engine: < 10s
- Dispatcher: < 10s

### Cost Baselines
- Daily: $1.00-$1.50
- Monthly: $35-$40
- No runaway costs (check weekly)

---

## Escalation

### Critical (Immediate Action Required)
- Duplicate executions found
- Cost spike (> $5/day)
- RDS connection lost
- All services failing

### High (Fix Within 24h)
- One service not running
- Backlog growing rapidly
- Data freshness violations

### Medium (Fix Within Week)
- All signals being skipped
- No executions for 24+ hours
- Gate tuning needed

### Low (Monitor)
- Occasional FAILED status
- Variable execution counts
- Minor log warnings

---

## Configuration Management

### View Current Config
```bash
# Dispatcher config (if exists)
aws ssm get-parameter \
  --name /ops-pipeline/dispatcher_config \
  --region us-west-2

# Other params
aws ssm get-parameters-by-path \
  --path /ops-pipeline \
  --region us-west-2
```

### Update Config (Log All Changes)
```bash
# Example: Lower confidence threshold
aws ssm put-parameter \
  --name /ops-pipeline/dispatcher_config \
  --value '{"confidence_min": 0.65}' \
  --type String \
  --overwrite \
  --region us-west-2

# Document in: deploy/ops_validation/ssm_changes.md
```

---

## Contact / Escalation

**System Owner:** {YOUR_NAME}  
**AWS Account:** 160027201036  
**Region:** us-west-2  
**RDS:** ops-pipeline-db.cls4wuyg010k.us-west-2.rds.amazonaws.com

**Documentation:**
- Day 1 Status: `deploy/DAY_1_STATUS.md`
- Shakedown Plan: `deploy/SHAKEDOWN_PLAN.md`
- Phase 9 Complete: `deploy/PHASE_9_COMPLETE.md`

---

## Maintenance Windows

**No scheduled downtime required.**

Services can be individually disabled via EventBridge if needed:
```bash
aws scheduler update-schedule \
  --name ops-pipeline-{SERVICE} \
  --state DISABLED \
  --region us-west-2
```

---

**This runbook covers 90% of operational issues. Update as new patterns emerge.**
