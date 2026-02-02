# 7-14 Day Shakedown Plan
## Observation Period Before Phase 10

**Purpose:** Establish baseline behavior and validate system correctness before adding monitoring/optimization.

**Critical Rule:** 🔒 **FREEZE EXECUTION SEMANTICS** - Do not change gate logic, sizing formulas, or entry pricing during this period. Only tune thresholds via SSM if absolutely necessary.

---

## Why This Matters

**You want a clean baseline.**

Phase 10 metrics only mean something if the underlying behavior is stable. Otherwise you're chasing noise instead of signal.

Once frozen, you can safely add:
- Outcome attribution
- Forward-return labeling  
- Performance dashboards
- ML preparation

---

## Daily Checks (Days 1-7)

Run these queries **once per day** (from Lambda or db-migration Lambda):

### 1. Processing Health Check
```sql
-- Are we processing everything?
SELECT status, COUNT(*) 
FROM dispatch_recommendations
WHERE ts >= CURRENT_DATE
GROUP BY status
ORDER BY COUNT(*) DESC;
```

**Expected:**
- PENDING: 0-20 (new signals accumulating between dispatcher runs)
- SIMULATED: 10-100 (depends on how many signals generated)
- SKIPPED: 50-200 (most signals won't meet strict gates initially)
- PROCESSING: 0 (should never persist)
- FAILED: 0-5 (occasional errors acceptable)

### 2. Stuck PROCESSING Detection
```sql
-- Any stuck PROCESSING rows?
SELECT COUNT(*) as stuck_count
FROM dispatch_recommendations
WHERE status = 'PROCESSING'
  AND processed_at IS NULL
  AND ts < NOW() - INTERVAL '10 minutes';
```

**Expected:** 0 always (reaper should clear these)

**If > 0:** Tighten processing_ttl_minutes in config (not the code).

### 3. Execution Volume
```sql
-- Daily execution count
SELECT 
  DATE(simulated_ts) as date,
  COUNT(*) as executions,
  COUNT(DISTINCT ticker) as unique_tickers,
  SUM(notional) as total_notional
FROM dispatch_executions
GROUP BY DATE(simulated_ts)
ORDER BY date DESC
LIMIT 7;
```

**Expected:** 
- 5-50 executions per day (market hours only)
- 5-20 unique tickers
- $10K-$100K total notional

### 4. Dispatcher Run Stats
```sql
-- Recent runs summary
SELECT 
  started_at,
  pulled_count,
  simulated_count,
  skipped_count,
  failed_count,
  EXTRACT(EPOCH FROM (finished_at - started_at)) as duration_seconds
FROM dispatcher_runs
WHERE started_at >= CURRENT_DATE
ORDER BY started_at DESC
LIMIT 20;
```

**Expected:**
- Duration: 2-10 seconds
- Pulled: 0-10 per run
- Simulated: 0-10 per run
- Skipped: varies based on gates
- Failed: 0

---

## After 5-7 Days: Descriptive Analysis (NOT Optimization)

Answer these questions with data:

### Question 1: Signal Volume
```sql
-- Signals generated per day
SELECT 
  DATE(created_at) as date,
  COUNT(*) as total_signals,
  COUNT(*) FILTER (WHERE instrument_type = 'CALL') as calls,
  COUNT(*) FILTER (WHERE instrument_type = 'PUT') as puts,
  COUNT(*) FILTER (WHERE instrument_type = 'STOCK') as stock
FROM dispatch_recommendations
WHERE created_at >= NOW() - INTERVAL '7 days'
GROUP BY DATE(created_at)
ORDER BY date DESC;
```

### Question 2: Gate Rejection Patterns
```sql
-- Which gates reject most?
SELECT 
  risk_gate_json->'confidence'->>'passed' as conf_pass,
  risk_gate_json->'action_allowed'->>'passed' as action_pass,
  risk_gate_json->'bar_freshness'->>'passed' as bar_pass,
  risk_gate_json->'feature_freshness'->>'passed' as feat_pass,
  risk_gate_json->'ticker_daily_limit'->>'passed' as limit_pass,
  COUNT(*) as count
FROM dispatch_recommendations
WHERE status = 'SKIPPED'
  AND processed_at >= NOW() - INTERVAL '7 days'
GROUP BY 1,2,3,4,5
ORDER BY count DESC
LIMIT 10;
```

**Look for:**
- Is one gate rejecting 80%+ of signals? (May be too strict)
- Are freshness gates failing? (Data pipeline issue)
- Are confidence gates working as expected?

### Question 3: Ticker Distribution
```sql
-- Which tickers execute most?
SELECT 
  ticker,
  COUNT(*) as exec_count,
  AVG(confidence) as avg_confidence,
  AVG(notional) as avg_notional
FROM dispatch_executions
WHERE simulated_ts >= NOW() - INTERVAL '7 days'
GROUP BY ticker
ORDER BY exec_count DESC
LIMIT 15;
```

**Look for:**
- Diversification (not 80% in one ticker)
- Reasonable position sizes ($1K-$10K per trade)

### Question 4: Position Sizing Sanity
```sql
-- Position size distribution
SELECT 
  action,
  COUNT(*) as count,
  AVG(qty) as avg_qty,
  MIN(qty) as min_qty,
  MAX(qty) as max_qty,
  AVG(notional) as avg_notional,
  AVG(entry_price) as avg_entry_price
FROM dispatch_executions
WHERE simulated_ts >= NOW() - INTERVAL '7 days'
GROUP BY action;
```

**Look for:**
- Reasonable share counts (10-500 shares typically)
- Notional matches expectations ($500-$25K per position)
- No weird edge cases (qty=0 or qty=10000)

### Question 5: Stop/TP Distance Check
```sql
-- Stop/TP distances
SELECT 
  ticker,
  AVG((stop_loss_price - entry_price) / entry_price) as avg_stop_pct,
  AVG((take_profit_price - entry_price) / entry_price) as avg_tp_pct,
  AVG(sim_json->'features_used'->>'recent_vol') as avg_vol
FROM dispatch_executions
WHERE simulated_ts >= NOW() - INTERVAL '7 days'
  AND action LIKE 'BUY%'  -- Longs
GROUP BY ticker
ORDER BY avg_vol DESC
LIMIT 10;
```

**Look for:**
- Stop distance correlates with volatility
- TP distance ~2× stop distance (2:1 R/R)

---

## Red Flags to Watch For

### 🚩 No executions for 24+ hours
**Likely causes:**
- Signal Engine not generating signals
- All signals failing confidence gate
- Data pipeline stall

**Action:** Check Signal Engine logs first.

### 🚩 All executions are SKIPPED
**Likely causes:**
- Confidence threshold too high (0.70 may be strict)
- Data freshness issues (bars/features not updating)
- Daily limits hit early

**Action:** Review gate_results in risk_gate_json.

### 🚩 Huge position sizes (>$50K notional)
**Likely causes:**
- Stop too tight (risk_per_share near zero)
- Paper equity misconfigured

**Action:** Review sim_json sizing_rationale.

### 🚩 Stuck PROCESSING rows persist
**Likely causes:**
- Reaper not running
- Processing TTL too long

**Action:** Lower processing_ttl_minutes to 5.

---

## Configuration Tuning (If Needed)

**Only change thresholds via SSM, never code.**

### If Too Few Executions:
```bash
# Lower confidence threshold
aws ssm put-parameter \
  --name /ops-pipeline/dispatcher_config \
  --value '{"confidence_min": 0.65}' \
  --type String \
  --overwrite \
  --region us-west-2
```

### If Too Many Executions:
```bash
# Raise confidence threshold or reduce daily limits
aws ssm put-parameter \
  --name /ops-pipeline/dispatcher_config \
  --value '{"confidence_min": 0.75, "max_signals_per_run": 5}' \
  --type String \
  --overwrite \
  --region us-west-2
```

### If Data Freshness Issues:
```bash
# Relax freshness gates (only if data lag is unavoidable)
aws ssm put-parameter \
  --name /ops-pipeline/dispatcher_config \
  --value '{"max_bar_age_seconds": 180, "max_feature_age_seconds": 420}' \
  --type String \
  --overwrite \
  --region us-west-2
```

---

## After 7-14 Days: Decide Next Steps

### Option 1: Phase 10 - Monitoring That Matters
**Not vanity dashboards, but operational alerts:**
- Health check Lambda (detect data stalls)
- SNS alerts for stuck pipelines
- CloudWatch metrics that drive decisions
- Data freshness watchdog

**Time:** 2-3 hours  
**Benefit:** Catch issues before they compound

### Option 2: Outcome Annotator (ML Prep)
**Lightweight batch that computes realized outcomes:**
- Forward returns at horizons (1m, 5m, 15m, 60m)
- Whether stop/TP hit first
- Max adverse/favorable excursion
- Regime context at entry

**Time:** 3-4 hours  
**Benefit:** Prepares for ML without training anything yet

### Option 3: Expand Universe (Option A)
**Add 120-150 stocks (ETFs, sectors):**
- Update universe_tickers SSM parameter
- Add liquidity scoring to watchlist
- Add catalyst tracking (earnings proximity)
- Deploy and monitor

**Time:** 4-6 hours  
**Benefit:** More opportunities, better diversification

### Recommendation: Monitor First
Let the system run for 7-14 days with current 36 stocks. Observe patterns. Then expand universe with confidence that the execution layer is solid.

---

## Validation Questions for Day 7

Before proceeding to Phase 10, answer these:

1. **Are executions happening?** (Yes/No)
2. **Is the reaper working?** (No stuck PROCESSING rows)
3. **Are gates reasonable?** (Not rejecting 95% of signals)
4. **Are position sizes sane?** ($500-$25K per trade)
5. **Is execution_id unique per recommendation_id?** (Idempotency working)

**If all 5 = Yes:** System is working as designed.  
**If any = No:** Debug before Phase 10.

---

## Critical: Execution Semantics Freeze

Before Phase 10, **commit to these semantics:**

### Frozen (Do Not Change):
- Entry pricing model (close + 5bps)
- Position sizing formula (2% risk)
- Stop distance calculation (2× ATR)
- Take profit ratio (2:1 R/R)
- Gate definitions (5 gates)

### Tunable (Via SSM Only):
- Confidence threshold (0.70)
- Daily limits (2 per ticker)
- Freshness windows (120s bars, 300s features)
- Paper equity ($100K)
- Risk per trade (2%)

**Why freeze?**
- Metrics are meaningful only with stable behavior
- Can compare week-over-week accurately
- Outcome attribution is valid
- ML training data is consistent

**When to unfreeze:**
- After 2-4 weeks of stable operation
- After analyzing outcome distributions
- When you have evidence a change will improve

---

## What "Let It Run" Means

For next 7-14 days:

### Do:
✅ Monitor logs daily  
✅ Run health check queries  
✅ Document observed patterns  
✅ Tune SSM config if gates clearly wrong  
✅ Fix bugs if found

### Don't:
❌ Add new features to dispatcher  
❌ Change gate logic  
❌ Modify sizing/pricing code  
❌ Optimize prematurely  
❌ Start backtesting yet

**The goal:** Earn trust by behaving predictably.

---

## Success Criteria

After 7-14 days, you should have:

✅ **Consistent execution counts** (not wildly variable)  
✅ **No stuck PROCESSING rows** (reaper working)  
✅ **Reasonable gate rejection rates** (60-80% rejection is normal)  
✅ **Sane position sizes** (no edge cases)  
✅ **Complete logs** (no unexplained errors)

**When these are true:** You have a production-grade system you can build on.

---

## Then Choose Your Path

### Path A: Add Monitoring (Conservative)
- Alerts for data stalls
- Dashboards for execution rates
- Watchdog for pipeline health
- **Best if:** You want operational visibility first

### Path B: Add Outcome Tracking (Ambitious)
- Annotate realized returns
- Compute stop/TP hit rates
- Build dataset for ML
- **Best if:** You want to start learning what works

### Path C: Expand Universe (Aggressive)
- 120-150 stocks
- ETFs + sectors
- More opportunities
- **Best if:** Current execution patterns look good

**My recommendation:** Start with Path A (monitoring). You can't improve what you can't see.

---

## Document Your Baseline

Save these for comparison:

**Week 1 Baseline:**
- Total executions: ___
- Unique tickers: ___
- Avg confidence: ___
- Gate rejection %: ___
- Avg position size: ___
- Most executed ticker: ___

**Week 2 Comparison:**
- Are patterns consistent?
- Did tuning improve anything?
- Any unexpected behaviors?

---

**Remember:** Good systems earn trust through predictable behavior over time. This one is set up to do exactly that.

**Next milestone:** Clean 7-day run with no manual intervention.
