# Day 6 Incident Report: Feature Computation Stalled
## Configuration Mismatch Between Services

**Date:** 2026-01-16  
**Observation Day:** 6 of 7  
**Status:** ❌ DEGRADED - Feature pipeline stalled for 16.5 hours  
**Impact:** Moderate - Core services running, but no feature computation  

---

## Incident Summary

Feature computation has been **silently failing** for approximately 16.5 hours due to configuration mismatch between telemetry collection and feature computation services.

### Key Metrics (14:38 UTC)
```
telemetry_lag_sec: 114s        ✅ GREEN
feature_lag_sec: 59,358s       ❌ CRITICAL (16.5 hours!)
watchlist_lag_sec: 46s         ✅ GREEN  
bars_written_10m: 57           ✅ Active telemetry
unfinished_runs: 0             ✅ Clean
duplicate_recos: 0             ✅ Clean
```

---

## Root Cause Analysis

### The Problem
Feature-computer service loads **36 universe tickers** but:
1. Only **7 tickers have telemetry data** (AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA)
2. DB query uses **120-minute lookback window**
3. Recent 120 minutes contains only **9-14 bars** per ticker
4. Feature computation requires **50 bars minimum** for SMA50

**Result:** All 36 tickers skipped every minute for days.

### Configuration Mismatch

**Telemetry Service (`/ops-pipeline/tickers`):**
```
AAPL,MSFT,TSLA,GOOGL,AMZN,META,NVDA (7 stocks)
```

**Feature Computer (`/ops-pipeline/universe_tickers`):**
```
36 stocks including the above 7 + 29 others with NO telemetry data
```

### Query Limitation

```python
# db.py line 42
cursor.execute("""
    SELECT ts, open, high, low, close
    FROM lane_telemetry
    WHERE ticker = %s
      AND ts >= NOW() - INTERVAL '120 minutes'  # <-- TOO NARROW
    ORDER BY ts ASC
""", (ticker, minutes))
```

**120-minute window contains:**
- During market hours: ~10-15 bars (not enough for 50-bar SMA)
- During market closed: 0 bars

**Available data:**
- 1,300+ bars per ticker spanning 4 days (plenty for analysis)

---

## Why The Alarm Didn't Trigger

### ops-pipeline-feature-lag Alarm
**Configuration:**
- Metric: FeatureLag
- Threshold: >600s
- Evaluation Periods: 2
- Period: 300s (5 minutes)

**Why INSUFFICIENT_DATA:**
Alarm requires 2 consecutive 5-minute periods with valid FeatureLag metrics. However:
1. Healthcheck Lambda was only deployed on Day 1 (Jan 13, 18:07 UTC)
2. If healthcheck had issues or FeatureLag wasn't consistently emitted, alarm stays in INSUFFICIENT_DATA
3. CloudWatch alarm needs consistent datapoints to transition to ALARM state

**This is actually a monitoring blind spot** - the alarm exists but never had enough data to evaluate.

---

## Services Actually Running

### EventBridge Rules (4)
- ops-pipeline-rss-ingest-schedule ✅
- ops-pipeline-telemetry-1m-schedule ✅  
- ops-pipeline-classifier-batch-schedule ✅
- ops-pipeline-feature-computer-schedule ✅ (but silently failing)

### EventBridge Scheduler (4)
- ops-pipeline-watchlist-engine-5m ✅
- ops-pipeline-signal-engine-1m ✅
- ops-pipeline-dispatcher ✅
- ops-pipeline-healthcheck-5m ✅

### Data Status
**Healthy:**
- RSS ingest: Running
- Telemetry: 1,300+ bars for 7 tickers, current to 114s ago
- Classifier: Running on 36 universe tickers
- Watchlist: Current (46s lag)

**Degraded:**
- Features: No computation for 16.5 hours (0 tickers passing 50-bar threshold)
- Signals: Unknown (depends on features)
- Dispatcher: No recommendations (reco_data_present=0)

---

## Impact Assessment

### Data Gaps Created
1. **lane_features table:** Last entry is 16.5 hours old
2. **Watchlist scoring:** May be using stale features (needs verification)
3. **Signal generation:** Likely blocked or using stale data
4. **Trading decisions:** Effectively halted

### Why This Wasn't Obvious
1. **Services kept running** - No container crashes
2. **Logs show "success"** - Feature-computer completes with 0/36 computed
3. **Alarms stayed quiet** - INSUFFICIENT_DATA state
4. **Telemetry stayed current** - Superficially healthy

**This is exactly the kind of silent failure Phase 10 monitoring was meant to catch, but alarm conditions weren't triggered.**

---

## Fix Options

### Option A: Increase Lookback Window (Immediate)
**Change:**
```python
# In db.py
def get_last_telemetry(self, ticker: str, minutes: int = 1440):  # 24 hours, not 120
```

**Pros:**
- Immediate fix
- No deployment complexity
- Uses existing historical data

**Cons:**
- Slightly more DB load
- Not addressing universe vs collection mismatch

### Option B: Align Universe with Collection (Proper Fix)
**Change:**
```bash
# Revert feature-computer to use /ops-pipeline/tickers (7 stocks)
# OR expand telemetry to collect all 36 universe tickers
```

**Pros:**
- Fixes configuration drift
- Sustainable long-term

**Cons:**
- Requires deciding on ticker coverage strategy
- May need code changes

### Option C: Adaptive Lookback (Best)
**Change:**
```python
# Try progressively longer lookbacks until 50 bars found
lookback_windows = [120, 360, 720, 1440, 4320]  # 2h, 6h, 12h, 24h, 3d
```

**Pros:**
- Handles both recent and historical data
- Graceful degradation
- Works during warmup periods

**Cons:**
- More complex logic
- Multiple queries if data sparse

---

## Recommended Immediate Action

**DO THIS NOW (Option A):**

1. Change lookback from 120 to 1440 minutes (24 hours)
2. Redeploy feature-computer service
3. Wait 2-3 minutes for feature computation to succeed
4. Verify feature_lag_sec drops below 180s

**Takes:** ~5 minutes  
**Risk:** Minimal (read-only query change)  
**Benefit:** Restores feature pipeline immediately

---

## Observation Period Assessment

### Is The 7-Day Observation Still Valid?

**NO - Observation period is compromised.**

**Reasons:**
1. **Features stalled for ~40% of time** (16.5 hours out of ~144 hours)
2. **Watchlist/signals likely affected** (need to verify)
3. **Baseline data incomplete** for feature computation
4. **Alarm didn't fire** (monitoring gap discovered)

### Options Moving Forward

#### Option 1: Fix + Restart 7-Day Observation (Recommended)
- Fix lookback window today
- Restart observation clock from Day 0
- Acknowledge previous 6 days as "shakedown with issues"
- Complete proper 7-day observation with working monitoring

#### Option 2: Fix + Continue as "Observed Failure Mode"
- Document this as a failure mode discovery
- Fix the issue
- Count it toward operational learnings
- Move to Day 7 baseline with gap acknowledged

#### Option 3: Fix + Abbreviated Observation
- Fix issue
- Run 3-4 more days of clean observation
- Proceed with less confidence in baseline

---

## Monitoring Lessons Learned

### What Worked
✅ Healthcheck Lambda detected the lag  
✅ Presence metrics show reco/exec data absent  
✅ Throughput metrics confirm telemetry working  
✅ Logs are structured and queryable  

### What Failed
❌ Alarm didn't trigger (INSUFFICIENT_DATA state)  
❌ No alert on "all tickers skipped" condition  
❌ Silent failure mode - service appeared healthy  
❌ Configuration drift went undetected  

### Improvements Needed
1. **Add alert on features computed = 0** for extended period
2. **Composite alarm:** `BarsWritten > 0 AND FeaturesComputed = 0`
3. **Config validation:** Verify universe ⊆ telemetry collection
4. **Warmup handling:** Adaptive lookback or explicit warmup phase

---

## Immediate Next Steps

1. **Fix lookback window** (120 → 1440 minutes)
2. **Verify feature computation resumes**
3. **Check cascade effects** on watchlist/signals
4. **Decide:** Restart observation or continue with gap
5. **Update OVS_TRACKER** with incident details
6. **Add FeaturesComputed metric** to healthcheck

---

## Data Collected During Days 1-6

### Still Valuable
- Telemetry collection: 1,300+ bars × 7 tickers
- RSS ingest patterns
- Watchlist behavior (if not dependent on features)
- Throughput baselines
- Cost validation

### Compromised
- Feature computation reliability
- Signal generation patterns (if occurred)
- End-to-end pipeline validation
- Alarm effectiveness validation

---

## Status Summary

**Current State:** DEGRADED  
**Root Cause:** 120-minute lookback too narrow for 50-bar SMA  
**Fix Available:** Yes (immediate)  
**Observation Valid:** No (requires decision)  
**Production Ready:** Not yet (monitoring gaps discovered)  

**This incident proves the value of the observation period - we found a critical issue before production use.**
