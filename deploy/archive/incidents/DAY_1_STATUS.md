# Day 1 Status Report
**Date:** 2026-01-13  
**Time:** 14:58 UTC

---

## Deployment Status: ✅ COMPLETE

### All 7 Services Scheduled and Enabled

**EventBridge Rules (1-minute intervals):**
1. ✅ ops-pipeline-rss-ingest-schedule - ENABLED
2. ✅ ops-pipeline-classifier-batch-schedule - ENABLED
3. ✅ ops-pipeline-telemetry-1m-schedule - ENABLED
4. ✅ ops-pipeline-feature-computer-schedule - ENABLED

**EventBridge Scheduler (variable intervals):**
5. ✅ ops-pipeline-watchlist-engine-5m - ENABLED (every 5 min)
6. ✅ ops-pipeline-signal-engine-1m - ENABLED (every 1 min)
7. ✅ ops-pipeline-dispatcher - ENABLED (every 1 min)

### Infrastructure Health

✅ **No persistent ECS tasks** (all batch/scheduled as designed)  
✅ **All schedules enabled**  
✅ **Database schema complete** (10 tables, 4 migrations applied)  
✅ **Migration 004 applied successfully** (dispatcher tables created)

---

## Expected Behavior (Next 2-3 Hours)

### First Executions:
- **Within 1 minute:** RSS, Classifier, Telemetry, Features, Signal, Dispatcher will trigger
- **Within 5 minutes:** Watchlist will trigger
- **Log groups created:** Auto-created on first execution

### Services Will:
1. **RSS Ingest** → Fetch news items
2. **Classifier** → Classify sentiments (if unprocessed news exists)
3. **Telemetry** → Fetch 1-min bars from Alpaca
4. **Features** → Compute SMA/vol/trends
5. **Watchlist** → Score and select top 30
6. **Signal Engine** → Generate recommendations
7. **Dispatcher** → Process recommendations with risk gates

---

## How to Monitor (Next Few Hours)

### Check Logs Are Being Created:
```bash
# List all log groups
aws logs describe-log-groups \
  --log-group-name-prefix /ecs/ops-pipeline \
  --region us-west-2 \
  --query 'logGroups[*].logGroupName'
```

**Expected:** 7 log groups created within 10 minutes

### View Recent Logs (After 5-10 Minutes):
```bash
# Signal Engine (should show watchlist loaded, signals computed)
aws logs tail /ecs/ops-pipeline/signal-engine-1m --region us-west-2 --since 10m

# Dispatcher (should show runs, claims, gates, executions/skips)
aws logs tail /ecs/ops-pipeline/dispatcher --region us-west-2 --since 10m

# Watchlist (should show scoring, top 30 selection)
aws logs tail /ecs/ops-pipeline/watchlist-engine-5m --region us-west-2 --since 10m
```

### Check Cost (Tomorrow):
```bash
aws ce get-cost-and-usage \
  --time-period Start=2026-01-13,End=2026-01-14 \
  --granularity DAILY \
  --metrics UnblendedCost \
  --region us-west-2
```

**Expected:** < $2 per day (~$35-40 per month)

---

## Day 1 Acceptance Checks (Run After 2-3 Hours)

Once services have executed a few times, run these queries via Lambda:

### Quick Health Check:
```sql
-- 1. Check backlog state
SELECT status, COUNT(*) 
FROM dispatch_recommendations
GROUP BY status;

-- 2. Check stuck processing (should be 0)
SELECT COUNT(*) 
FROM dispatch_recommendations
WHERE status = 'PROCESSING' 
  AND ts < NOW() - INTERVAL '10 minutes';

-- 3. Check for duplicate executions (should be 0)
SELECT recommendation_id, COUNT(*) 
FROM dispatch_executions
GROUP BY recommendation_id
HAVING COUNT(*) > 1;

-- 4. Check execution counts
SELECT COUNT(*) as executions_today
FROM dispatch_executions
WHERE simulated_ts >= CURRENT_DATE;

-- 5. Check dispatcher runs
SELECT 
  started_at,
  pulled_count,
  simulated_count,
  skipped_count
FROM dispatcher_runs
ORDER BY started_at DESC
LIMIT 5;
```

**All queries in:** `scripts/day1_acceptance_checks.py`

---

## Expected Results (End of Day 1)

### Normal Patterns:
- **Signal Engine:** 5-100 signals generated (depends on market activity)
- **Dispatcher:** 60-120 runs (once per minute when signals exist)
- **Executions:** 0-50 simulated (many will be SKIPPED by gates)
- **SKIPPED rate:** 60-80% (strict gates are working)

### What "Success" Looks Like:
✅ No PROCESSING rows stuck  
✅ No duplicate executions  
✅ Dispatcher runs completing (all have finished_at)  
✅ Some executions simulated (proves end-to-end flow)  
✅ Fresh bar data used (age < 120 seconds)

### What to Watch For:
⚠️ All signals SKIPPED (gates may be too strict)  
⚠️ PROCESSING rows accumulating (dispatcher not running)  
⚠️ No signals generated (signal engine issue)  
⚠️ Duplicate executions (idempotency failure - CRITICAL)

---

## If Issues Found

### No Logs After 10 Minutes:
1. Check EventBridge schedules are enabled
2. Verify IAM role permissions
3. Check VPC/subnet/security group config
4. Review CloudWatch for schedule errors

### Services Failing:
1. Check individual log groups for errors
2. Verify RDS accessible from ECS
3. Check SSM parameters exist
4. Verify Secrets Manager accessible

### Cost Spike:
1. Check for persistent tasks (should be 0)
2. Verify schedules not running too frequently
3. Check for NAT gateway (should not exist)

---

## 🔒 Execution Semantics Freeze (EFFECTIVE NOW)

**Do NOT change these for 7-14 days:**
- Entry pricing: close + 5bps
- Position sizing: 2% account risk
- Stop calculation: 2× ATR
- Take profit: 2:1 risk/reward
- Gate definitions: 5 gates

**Only tune via SSM:**
- Thresholds (confidence, limits, freshness)
- Paper equity
- Risk percentages

**Why:** Need clean baseline for meaningful metrics.

---

## Next 7 Days: Observation Mode

### Daily (Once per day):
```bash
# Quick health check - run via Lambda
SELECT status, COUNT(*) FROM dispatch_recommendations GROUP BY status;
SELECT COUNT(*) FROM dispatcher_runs WHERE started_at >= CURRENT_DATE;
```

### Day 7: Baseline Analysis
- Signal volume per day
- Gate rejection rates
- Ticker distribution
- Position size ranges
- Execution patterns

**Full plan in:** `deploy/SHAKEDOWN_PLAN.md`

---

## After 7 Clean Days: Choose Phase 10

**Path A: Monitoring & Alerts** (Recommended)
- Health check Lambda
- SNS alerts for data stalls
- CloudWatch dashboards

**Path B: Outcome Tracking** (ML Prep)
- Annotate realized returns
- Compute stop/TP hit rates
- Build ML-ready dataset

**Path C: Expand Universe** (After Validation)
- 120-150 stocks
- Add ETFs + sectors
- Liquidity scoring

---

## Summary

**Status:** ✅ All services deployed and scheduled

**Next actions:**
1. Wait 10-15 minutes for first executions
2. Check logs to verify services running
3. Run Day 1 acceptance checks (after 2-3 hours of operation)
4. Document baseline
5. Enter 7-day observation mode (no code changes)

**You've built a production-grade system. Now let it prove itself.**

---

**System is operational. Services will begin executing within their schedule intervals.**
