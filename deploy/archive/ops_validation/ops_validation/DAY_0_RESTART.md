# Day 0: Observation Period Restart
## Clean Baseline After Day 6 Incident Resolution

**Date:** 2026-01-16 14:59 UTC  
**Observation Period:** Day 0 of 7  
**Previous Attempt:** Jan 13-16 (6 days, terminated due to incident)  
**Status:** ✅ HEALTHY - All systems operational  

---

## Why Restart?

### Day 6 Incident Summary
- **Problem:** Feature computation stalled for 16.5 hours (11% of observation period)
- **Root Cause:** 120-minute lookback window insufficient for 50-bar SMA calculation
- **Impact:** No feature computations, watchlist/signals potentially affected
- **Resolution:** Implemented adaptive lookback (120min → 6h → 12h → 24h → 3d)
- **Time to Fix:** 30 minutes from detection to restoration

### Why Full Restart vs Continue
1. **Data Gap Too Large** - 11% downtime compromises baseline statistics
2. **Behavior Changed** - Adaptive lookback is different query pattern
3. **Monitoring Enhanced** - Now have 11 metrics (was 10), includes FeaturesComputed
4. **Alarm Gaps Fixed** - Previous alarms were INSUFFICIENT_DATA
5. **Clean Start Needed** - Can't establish reliable production baseline with known issues

**Decision:** Better to lose 6 days of flawed data than proceed with compromised baseline.

---

## System State at Restart (14:59 UTC)

### Current Health Metrics (ALL GREEN ✅)
```json
{
  "telemetry_lag_sec": 121,           ✅ <180s threshold
  "feature_lag_sec": 24,              ✅ <600s threshold (RESTORED!)
  "watchlist_lag_sec": 50,            ✅ Healthy
  "reco_lag_sec": 0,                  ℹ️  Market closed
  "exec_lag_sec": 0,                  ℹ️  Market closed
  "reco_data_present": 0,             ℹ️  Expected
  "exec_data_present": 0,             ℹ️  Expected
  "bars_written_10m": 56,             ✅ Active ingestion
  "features_computed_10m": 7,         ✅ NEW METRIC - All tickers computing!
  "unfinished_runs": 0,               ✅ Clean
  "duplicate_recos": 0                ✅ Clean
}
```

### Services Status
**All 7 ECS Services:**
1. ✅ RSS Ingest (EventBridge Rule, 1 min)
2. ✅ Telemetry (EventBridge Rule, 1 min)
3. ✅ Classifier (EventBridge Rule, 1 min)
4. ✅ **Features (EventBridge Rule, 1 min) - FIXED with adaptive lookback**
5. ✅ Watchlist (EventBridge Scheduler, 5 min)
6. ✅ Signal Engine (EventBridge Scheduler, 1 min)
7. ✅ Dispatcher (EventBridge Scheduler, 1 min)

**Monitoring:**
- ✅ Healthcheck Lambda (every 5 min)
- ✅ 11 CloudWatch metrics emitting
- ✅ 4 CloudWatch alarms configured

---

## Improvements Since Previous Observation

### 1. Adaptive Lookback (Feature-Computer)
**Before:**
- Fixed 120-minute window
- Failed during warmup (needed 50 bars in 120 min)
- Silent failure mode

**After:**
- Progressive lookback: 120min → 6h → 12h → 24h → 3d → all
- Handles warmup automatically
- Currently finding sufficient data in 1,300+ bar history

**Benefit:** Prevents recurrence of Day 6 incident

### 2. Immutable Deployments (Phase 10.3)
**Feature-computer now using digest-pinned image:**
```
160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/feature-computer-1m@sha256:ef7abf0...
```

**Benefit:** Prevents cache issues like Day 1 dispatcher bug

### 3. Enhanced Monitoring (11 Metrics)
**Added FeaturesComputed10m:**
- Tracks how many tickers had features computed in last 10 minutes
- Expected value: 7 during normal operation
- Would have detected Day 6 incident immediately

**Benefit:** Early detection of silent failures

---

## Observation Period Goals (Days 0-7)

### Primary Objectives
1. **Establish clean baselines** for all 11 health metrics
2. **Verify alarms transition** from INSUFFICIENT_DATA to OK
3. **Track FeaturesComputed** metric (should be 7 during active periods)
4. **Monitor for any anomalies** with enhanced detection
5. **Validate alarm wiring** with controlled tests (optional)

### Success Criteria for Day 7
✅ All services running continuously  
✅ Feature_lag stays < 600s  
✅ FeaturesComputed = 7 for available tickers  
✅ BarsWritten10m shows consistent throughput  
✅ No unfinished_runs or duplicate_recos  
✅ Alarms in OK state (not INSUFFICIENT_DATA)  
✅ No unexpected failures or degradations  

---

## Daily Monitoring Tasks

### Automated (Every 5 Minutes)
- Healthcheck Lambda emits all 11 metrics
- CloudWatch stores time-series data
- Alarms evaluate thresholds

### Manual (Once Per Day)
```bash
# Run healthcheck manually
aws lambda invoke \
  --function-name ops-pipeline-healthcheck \
  --region us-west-2 \
  /tmp/daily_health.json && cat /tmp/daily_health.json | jq '.body | fromjson'

# Check alarm states
aws cloudwatch describe-alarms \
  --alarm-name-prefix ops-pipeline \
  --region us-west-2 \
  | jq '.MetricAlarms[] | {AlarmName, StateValue, StateReason}'
```

**Expected Results:**
- All lag metrics < thresholds
- FeaturesComputed10m = 7 (or 0 if market closed)
- BarsWritten10m = 40-70 (market hours) or 0 (closed)
- Alarms transitioning from INSUFFICIENT_DATA → OK over first 24 hours

---

## Known Expected Behavior

### Market Closed (Nights/Weekends)
```
reco_data_present: 0
exec_data_present: 0
features_computed_10m: 7 (still computing from historical data)
bars_written_10m: 0-10 (minimal activity)
```

### Market Hours (9:30am-4pm ET)
```
reco_data_present: 0 or 1 (if signals generated)
exec_data_present: 0 or 1 (if trades executed)
features_computed_10m: 7 (all core tickers)
bars_written_10m: 40-70 (1 bar/min × 7 tickers)
```

### Normal Variance
- Telemetry lag: 10-180s (API delays, network)
- Feature lag: 10-120s (computation time)
- Watchlist lag: 30-300s (5-minute cycle)

---

## Configuration State

### Ticker Coverage
**Telemetry collects:** 7 tickers
- AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA

**Feature computes:** 36 tickers (7 with data, 29 gracefully skipped)
**Watchlist universe:** 36 tickers (selects from 7 available)

**This mismatch is acceptable** - feature-computer gracefully handles missing data with adaptive lookback.

**Decision Point:** Post-baseline, decide whether to:
- Reduce feature universe to 7 (simplify)
- Expand telemetry to 36 (enable full universe)

---

## Infrastructure State

### Immutable Deployments
**Feature-computer:** ✅ Digest-pinned (sha256:ef7abf0...)  
**All other services:** ⏳ Still using `:latest` tags  

**Post-observation:** Consider digest-pinning all remaining services.

### CloudWatch Alarms (4)
1. ops-pipeline-telemetry-lag (>180s, 2 periods)
2. ops-pipeline-feature-lag (>600s, 2 periods)
3. ops-pipeline-dispatcher-stalled (unfinished>0, 2 periods)
4. ops-pipeline-duplicate-executions (duplicates>0, 1 period)

**Current State:** INSUFFICIENT_DATA (will transition to OK as metrics accumulate)

### Future Alarm (Post-Baseline)
5. **ops-pipeline-features-stalled** (FeaturesComputed=0 for 10+ min)
   - Would have caught Day 6 incident immediately
   - Add after establishing baseline for this metric

---

## Cost Baseline

### Current Monthly Cost (~$40)
- RDS db.t3.micro: $15.10
- VPC Endpoints (2): $15.00
- 7 ECS scheduled tasks: $5.71
- CloudWatch metrics (11): $3.30
- CloudWatch alarms (4): $0.40
- Secrets Manager: $0.40
- Lambda healthcheck: $0 (free tier)
- S3/misc: $0.30

**Observation Goal:** Verify actual costs match projections.

---

## Data Collection Plan

### Metrics to Baseline (Day 7 Analysis)
1. **Telemetry Health**
   - p50/p95 telemetry_lag during bars_written>0 periods
   - Throughput pattern: bars_written_10m distribution
   
2. **Feature Computation**
   - p50/p95 feature_lag
   - FeaturesComputed10m stability (should be constant 7)
   - Adaptive lookback performance
   
3. **Watchlist Behavior**
   - p50/p95 watchlist_lag
   - Selection patterns (which tickers chosen)
   
4. **Signal/Dispatcher**
   - RecoDataPresent transitions (market open/close detection)
   - Execution patterns (if any occur)
   
5. **Alarm Behavior**
   - Time to transition from INSUFFICIENT_DATA → OK
   - False positive rate
   - Threshold appropriateness

---

## Success Metrics for This Observation

### Quantitative
- ✅ 168 hours of continuous operation (7 days × 24 hours)
- ✅ features_computed_10m = 7 for >95% of active periods
- ✅ 0 unfinished_runs throughout period
- ✅ 0 duplicate_recos throughout period
- ✅ All alarms in OK state (not ALARM or INSUFFICIENT_DATA)

### Qualitative
- ✅ No silent failures or degraded modes
- ✅ Alarms fire appropriately for real issues
- ✅ Baseline data enables confident threshold tuning
- ✅ System behavior predictable and documented

---

## Previous Observation Learnings (Jan 13-16)

### What Worked
- Infrastructure deployed successfully
- Telemetry collected 1,300+ bars
- Monitoring infrastructure functional
- Cost projections accurate
- Incident discovered before production

### What Failed
- Feature computation stalled silently
- Alarms didn't fire (INSUFFICIENT_DATA)
- Configuration drift (36 vs 7 tickers)
- Lookback window too narrow for warmup

### Applied Fixes
- ✅ Adaptive lookback prevents stalls
- ✅ Digest-pinned deployment prevents cache issues
- ✅ FeaturesComputed metric detects silent failures
- ✅ Enhanced documentation

**These learnings make the restart valuable** - we're now observing a more robust system.

---

## Next Milestone

**Day 7 (2026-01-23):**
- Extract baseline statistics
- Evaluate alarm performance
- Decide on Phase 11 direction:
  - Path A: Outcome tracking (ML prep)
  - Path B: Universe expansion (7 → 36 stocks)
  - Path C: Strategy enhancements

**Until then:** Hands-off observation, document anomalies only.

---

## Files Created/Updated

### Incident Documentation
- `deploy/ops_validation/DAY_6_INCIDENT_REPORT.md` - Problem analysis
- `deploy/ops_validation/DAY_6_RESOLUTION.md` - Solution details
- `deploy/ops_validation/DAY_0_RESTART.md` - This file

### Code Fixes
- `services/feature_computer_1m/db.py` - Adaptive lookback
- `services/feature_computer_1m/main.py` - Updated function call
- `services/healthcheck_lambda/lambda_function.py` - Added FeaturesComputed metric

### Deploy Updates
- `deploy/feature-computer-task-definition.json` - Digest-pinned image (rev 5)

---

## Monitoring Dashboard (CloudWatch Console)

### Recommended View
**Namespace:** OPsPipeline  
**Time Range:** Last 7 days  
**Metrics to Track:**
1. TelemetryLag (line graph)
2. FeatureLag (line graph)
3. FeaturesComputed10m (line graph) ← NEW
4. BarsWritten10m (line graph)
5. UnfinishedRuns (single value)
6. DuplicateExecutions (single value)

**Check daily** to spot trends before alarms fire.

---

## Communication Plan

### Internal Status
**System:** Operational  
**Observation:** Day 0 of 7 (restarted)  
**Incident:** Resolved, system more robust  
**Confidence:** High - incident caught and fixed pre-production  

### Stakeholder Message
"Observation period restarted after discovering and resolving a configuration issue. System now includes adaptive lookback and enhanced monitoring. No production impact - issue found during validation phase as intended."

---

## Success Declaration

**System is ready for clean 7-day observation:**
- ✅ All services healthy
- ✅ Feature computation restored
- ✅ Enhanced monitoring (11 metrics)
- ✅ Immutable deployment (feature-computer)
- ✅ Improved error handling
- ✅ Comprehensive documentation

**Observation Period: ACTIVE**  
**Start:** 2026-01-16 14:59 UTC  
**End:** 2026-01-23 14:59 UTC  
**Goal:** Establish production-ready baseline with confidence

**The system is now MORE reliable than before the incident.**
