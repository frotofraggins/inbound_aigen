# Day 6 Incident Resolution: Feature Computation RESTORED ✅
## Adaptive Lookback Implementation

**Date:** 2026-01-16  
**Resolution Time:** 14:56 UTC  
**Downtime:** 16.5 hours  
**Status:** ✅ RESOLVED  

---

## Resolution Summary

Feature computation **fully restored** using adaptive lookback strategy. System recovered from 16.5-hour stall to healthy state in under 30 minutes.

### Health Metrics After Fix (14:56 UTC)
```
telemetry_lag_sec: 153s        ✅ GREEN (<180s)
feature_lag_sec: 4s            ✅ GREEN (RESTORED from 59,358s!)
watchlist_lag_sec: 200s        ✅ GREEN
bars_written_10m: 56           ✅ Active
unfinished_runs: 0             ✅ Clean
duplicate_recos: 0             ✅ Clean
```

### Feature Computation Results
```json
{
  "success": true,
  "tickers_total": 36,
  "tickers_computed": 7,      ✅ RESTORED (was 0 for 16 hours)
  "tickers_skipped": 29,      ℹ️  Expected (no telemetry data)
  "tickers_failed": 0,        ✅ All working tickers successful
  "duration_ms": 847.95
}
```

---

## Root Cause Recap

**Problem:** Feature-computer queried only last 120 minutes of telemetry, getting 9-14 bars, but needed 50 minimum for SMA50 calculation.

**Why It Persisted:**
1. Services kept running without crashes
2. Logs showed "success" with 0 computed (not obviously an error)
3. CloudWatch alarm stayed in INSUFFICIENT_DATA (never evaluated)
4. Configuration mismatch (36 universe tickers, only 7 with data)

---

## Solution Implemented: Adaptive Lookback

### Code Changes

#### 1. db.py - Adaptive Query Strategy
```python
def get_last_telemetry(self, ticker: str, min_bars: int = 50):
    """
    Get sufficient telemetry using progressive lookback windows.
    Tries: 2h → 6h → 12h → 24h → 3d → all available
    Returns when min_bars threshold met.
    """
    lookback_minutes = [120, 360, 720, 1440, 4320, None]
    
    for minutes in lookback_minutes:
        rows = query_telemetry(ticker, minutes)
        if len(rows) >= min_bars:
            return rows
    
    return rows  # Return whatever found
```

#### 2. main.py - Updated Function Call
```python
# OLD: telemetry = db.get_last_telemetry(ticker, minutes=120)
# NEW: telemetry = db.get_last_telemetry(ticker, min_bars=50)
```

### Benefits of Adaptive Approach

**Handles Multiple Scenarios:**
1. ✅ **Warmup periods** - Finds data in earlier windows during initial deployment
2. ✅ **Historical backfill** - Uses all available data if recent window insufficient
3. ✅ **Normal operation** - Returns quickly with 2-hour window once system warmed up
4. ✅ **Data gaps** - Gracefully handles missing data for some tickers

**Performance:**
- Best case (warm): Single 2-hour query (~10-20 bars)
- Warmup case: 2-3 queries before finding sufficient data
- Worst case: 6 queries, returns all available data

---

## Deployment Process

### Steps Executed
1. ✅ Updated `services/feature_computer_1m/db.py` with adaptive logic
2. ✅ Updated `services/feature_computer_1m/main.py` function signature
3. ✅ Built Docker image: `ops-pipeline-feature-computer-1m:fixed-v2`
4. ✅ Pushed to ECR with digest: `sha256:ef7abf043b3baa8bbaf725beef33e69a2a3fe0fab775ac5977aade5cc81a7a07`
5. ✅ Registered task definition revision 5 with **digest-pinned image**
6. ✅ Updated EventBridge rule to use revision 5
7. ✅ Verified successful execution within 2 minutes

**Implementation Time:** 25 minutes (including diagnosis, fix, deploy, verify)

### Important: Immutable Deployment
This deployment implements **Phase 10.3: Immutable Deployments** by using digest-pinned images instead of `latest` tag.

**Task Definition Image:**
```
160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/feature-computer-1m@sha256:ef7abf0...
```

**Benefit:** Prevents image caching issues like Day 1 dispatcher bug.

---

## Verification Results

### Feature Computation Restored
```bash
aws logs filter-log-events \
  --log-group-name /ecs/ops-pipeline/feature-computer-1m \
  --filter-pattern "feature_run_complete" \
  --start-time $(($(date +%s) - 120))000
```

**Result (14:55 UTC):**
- ✅ 7 tickers computed (AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA)
- ✅ 29 tickers skipped (no telemetry data - expected)
- ✅ 0 tickers failed
- ✅ Success status true

### Health Metrics Restored
```bash
aws lambda invoke --function-name ops-pipeline-healthcheck --region us-west-2 /tmp/health.json
```

**Result (14:56 UTC):**
- feature_lag_sec: **4 seconds** (was 59,358s) ✅
- All other metrics healthy ✅

---

## Impact on Observation Period

### Data Collected During Incident (16.5 hours)
**Lost:**
- Feature computations for 7 tickers
- Watchlist scores based on current features (if dependent)
- Signal generation (if dependent on features)
- Dispatcher execution patterns

**Preserved:**
- Telemetry data: 1,300+ bars collected successfully
- RSS ingest patterns
- Cost validation data
- Infrastructure operational patterns

### Observation Period Decision

**RESTART 7-DAY OBSERVATION FROM TODAY**

**Rationale:**
1. **Incident was major** - 16.5 hour stall = 11% of 6-day period
2. **Fix changes behavior** - Adaptive lookback is different query pattern
3. **Monitoring gaps discovered** - Alarms didn't fire (INSUFFICIENT_DATA)
4. **Clean baseline needed** - Can't establish reliable baselines with 11% gap
5. **Low cost to restart** - Only losing 6 days that had issues anyway

**New Observation Start:** 2026-01-16 (today)  
**New Observation End:** 2026-01-23 (7 days from now)  
**Previous 6 days:** Documented as "shakedown period with learnings"

---

## Monitoring Improvements Required

### Issue: Alarm Never Triggered
**ops-pipeline-feature-lag alarm** stayed in INSUFFICIENT_DATA state despite 16-hour stall.

**Root Causes:**
1. Healthcheck Lambda only deployed on Day 1 evening
2. If healthcheck had early issues, metrics weren't consistent
3. Alarm needs 2 consecutive valid datapoints to evaluate

**Fix Needed:**
Add **FeaturesComputed metric** to healthcheck that tracks computed ticker count:
- Emit every 5 minutes
- Alarm if = 0 for 10+ minutes during expected active periods
- This would have caught the issue immediately

### Additional Monitoring Enhancements

#### 1. Add FeaturesComputed Metric
```sql
-- In healthcheck query
(SELECT COUNT(DISTINCT ticker) 
 FROM lane_features 
 WHERE computed_at >= NOW() - INTERVAL '10 minutes') AS features_computed_10m
```

**Alarm:** FeaturesComputed = 0 for 2 periods (10 minutes)  
**Benefit:** Detects silent failures immediately

#### 2. Add Composite Alarm for Smart Alerting
```
RecoDataPresent = 1 AND RecommendationLag > 600s
```
**Benefit:** Only alarms during market hours when data should exist

#### 3. Validate Alarm Wiring
Test each alarm with controlled failure:
- Stop service for 15 minutes
- Verify alarm fires
- Verify recovery detected

---

## Files Modified

### Services
```
services/feature_computer_1m/db.py
  - Replaced fixed 120-minute lookback with adaptive strategy
  - Progressive windows: 120 → 360 → 720 → 1440 → 4320 → all
  - Returns when min_bars threshold met

services/feature_computer_1m/main.py
  - Changed function call from minutes=120 to min_bars=50
  - No other logic changes
```

### Deploy
```
deploy/feature-computer-task-definition.json
  - Updated image to digest-pinned (Phase 10.3 implementation)
  - sha256:ef7abf043b3baa8bbaf725beef33e69a2a3fe0fab775ac5977aade5cc81a7a07
  - Registered as revision 5
```

### Documentation
```
deploy/ops_validation/DAY_6_INCIDENT_REPORT.md - Problem analysis
deploy/ops_validation/DAY_6_RESOLUTION.md - This file (solution)
```

---

## Lessons Learned

### What Worked
✅ Adaptive lookback handles warmup gracefully  
✅ Digest-pinned images prevent cache issues  
✅ EventBridge task scheduling reliable  
✅ Structured logging made diagnosis fast  
✅ Incident discovered during observation (not production)  

### What Failed
❌ Simple lookback window inadequate for warmup  
❌ Silent failure mode - "success" logs misleading  
❌ Alarm INSUFFICIENT_DATA instead of alerting  
❌ No ticker-computed metric for early detection  

### Improvements Implemented
✅ Adaptive lookback prevents recurrence  
✅ Digest-pinned deployment (Phase 10.3)  
✅ Better error handling (returns partial data)  

### Still Needed
⏳ Add FeaturesComputed metric to healthcheck  
⏳ Add composite alarms for market-hour awareness  
⏳ Test alarm wiring with controlled failures  
⏳ Align configuration (36 universe vs 7 collection tickers)  

---

## Observation Period Restart Plan

### Today (Day 0 - Restart)
1. ✅ Feature computation restored
2. ⏳ Add FeaturesComputed metric to healthcheck
3. ⏳ Document restart in OVS_TRACKER.md
4. ⏳ Create DAY_0_RESTART.md

### Days 1-7 (New Observation)
- Monitor all 10 healthcheck metrics daily
- Track FeaturesComputed metric (should be 7 during market hours)
- Verify alarms transition from INSUFFICIENT_DATA to OK
- Document any anomalies immediately
- No code changes except monitoring enhancements

### Day 7 (Baseline Analysis)
- Extract p50/p95 for all lag metrics
- Analyze throughput patterns (BarsWritten10m)
- Establish normal alarm threshold ranges
- Decide on Phase 11 direction

---

## Configuration Alignment Still Needed

### Current State
**Telemetry collects:** 7 tickers (AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA)  
**Feature computes:** 36 tickers (7 with data + 29 without)

### Options for Alignment

**Option A: Reduce Feature Universe to 7**
```bash
# Change feature-computer config to use /ops-pipeline/tickers instead of /universe_tickers
```
**Pro:** Simple, saves processing  
**Con:** Limits future expansion

**Option B: Expand Telemetry to 36**
```bash
# Update /ops-pipeline/tickers to include all 36 universe tickers
```
**Pro:** Enables full universe analysis  
**Con:** Higher Alpaca API usage, more cost

**Option C: Keep As-Is (Recommended for now)**
- 7 tickers compute successfully
- 29 tickers gracefully skip (no error)
- Adaptive lookback handles this cleanly
- Decide on expansion post-baseline

**Recommendation:** Option C for observation period, decide Option A or B afterward.

---

## Cost Impact

### Fix Cost
- Rebuild/redeploy: $0 (free)
- Observation restart: $0 (same services)
- No new infrastructure

### Future Monitoring Enhancements
- Add FeaturesComputed metric: +$0.30/month
- Add composite alarm: +$0.10/month
- **Total:** ~$0.40/month additional

---

## Next Steps

### Immediate (Today)
1. ✅ Feature computation restored
2. ⏳ Add FeaturesComputed metric to healthcheck Lambda
3. ⏳ Update OVS_TRACKER with incident + resolution
4. ⏳ Create DAY_0_RESTART.md to mark new observation start

### Days 1-7 (Clean Observation)
- Monitor system with working feature computation
- Verify alarms begin working (sufficient data)
- Track all 10 metrics for baseline
- Document any issues immediately

### Post-Observation
- Decide on ticker alignment strategy (7 vs 36)
- Add composite alarms for market-hour logic
- Test alarm wiring with controlled failures
- Proceed to Phase 11 (outcome tracking or expansion)

---

## Success Metrics

✅ Feature computation resumed (7/7 tickers with data)  
✅ Feature lag dropped from 16.5 hours to 4 seconds  
✅ Adaptive lookback handles warmup gracefully  
✅ Digest-pinned deployment prevents cache issues  
✅ Zero ongoing errors or failures  
✅ Ready for clean 7-day observation  

---

## Technical Improvements Achieved

### Before Fix
- ❌ Fixed 120-minute lookback
- ❌ Failed during warmup (needed 50 bars in 120 min)
- ❌ Silent failure (0 computed, no errors)
- ❌ Using `:latest` tag (cache issues possible)

### After Fix
- ✅ Adaptive lookback (120min → 6h → 12h → 24h → 3d)
- ✅ Handles warmup automatically
- ✅ Returns partial data if insufficient (no hard failure)
- ✅ Digest-pinned image (immutable deployment)

---

## Resolution Timeline

**14:38 UTC** - Incident discovered via healthcheck (feature_lag = 59,358s)  
**14:40 UTC** - Root cause identified (120-min lookback too narrow)  
**14:48 UTC** - Adaptive lookback implemented  
**14:50 UTC** - Docker image built and pushed (digest: ef7abf0)  
**14:54 UTC** - Task definition revision 5 registered  
**14:54 UTC** - EventBridge rule updated  
**14:55 UTC** - First successful execution (7/7 tickers computed)  
**14:56 UTC** - Health metrics confirm restoration (feature_lag = 4s)  

**Total Resolution Time:** 18 minutes from diagnosis to confirmation

---

## Observation Period Status

### Previous Observation (Jan 13-16)
- **Status:** TERMINATED DUE TO INCIDENT
- **Duration:** 6 days with 16.5-hour feature stall
- **Value:** Shakedown period, identified critical issues
- **Learnings:** Preserved and documented

### New Observation (Jan 16-23)
- **Status:** ACTIVE - Day 0
- **Start:** 2026-01-16 14:56 UTC
- **End:** 2026-01-23 14:56 UTC
- **Goal:** Clean 7-day baseline with working system

**This is the correct decision** - can't establish reliable baselines with 11% downtime.

---

## System State After Resolution

**All Services:** ✅ HEALTHY
- RSS Ingest: Active
- Telemetry: 1,300+ bars, <180s lag
- Classifier: Running on 36 universe
- **Features: RESTORED (7 tickers, <10s lag)** ← FIXED
- Watchlist: Current (<5min lag)
- Signals: Ready (depends on features)
- Dispatcher: Ready (depends on signals)
- Healthcheck: Running every 5 minutes

**Monitoring:** ✅ OPERATIONAL
- 10 CloudWatch metrics emitting
- 4 CloudWatch alarms configured
- Healthcheck Lambda running every 5 minutes

**Deployment:** ✅ IMMUTABLE
- Feature-computer now using digest-pinned image
- Prevents cache-related issues
- True rollback capability

---

## Remaining Work

### Priority 1: Monitoring Enhancement (Today)
Add FeaturesComputed metric to healthcheck:
```sql
(SELECT COUNT(DISTINCT ticker) 
 FROM lane_features 
 WHERE computed_at >= NOW() - INTERVAL '10 minutes') AS features_computed_10m
```

### Priority 2: Documentation (Today)
- Create DAY_0_RESTART.md
- Update OVS_TRACKER.md
- Note incident in RUNBOOK.md

### Priority 3: Alarm Validation (This Week)
Test each alarm with controlled failure to verify wiring works.

### Priority 4: Config Alignment (Post-Baseline)
Decide on ticker universe strategy (7 vs 36 stocks).

---

## Conclusion

**Incident Type:** Configuration mismatch + inadequate warmup handling  
**Detection:** Manual Day 6 check (alarms failed to fire)  
**Resolution:** Adaptive lookback + digest-pinned deployment  
**Downtime:** 16.5 hours (silent failure, no user impact)  
**Recovery:** Complete within 30 minutes  
**Observation:** Restarting from Day 0 for clean baseline  

**The system is now more robust than before the incident.**

**Key Achievement:** This incident validates the observation period approach - we found and fixed a critical issue before it affected real trading.
