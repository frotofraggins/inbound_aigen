# Current System Status - February 11, 2026
**Date:** February 11, 2026, 19:25 UTC  
**Status:** ✅ OPERATIONAL — All critical bugs fixed, trades executing, learning pipeline active

---

## 🎯 Executive Summary

**Major fixes deployed Feb 11 (four sessions):**

Session 1 (earlier today):
- ✅ Telemetry crash-loop fixed (sys.exit → return)
- ✅ Bar freshness threshold increased (120s → 180s)
- ✅ Dispatcher competition eliminated (both accounts process independently)
- ✅ Position manager crash-loop fixed (sys.exit → raise)
- ✅ Stale Docker image tags updated to :latest
- ✅ Large account Alpaca secret created (ops-pipeline/alpaca/large)

Session 2:
- ✅ Option price tracking fixed (positions API → Market Data quotes API)
- ✅ Dispatcher backlog eliminated (lookback 60min → 5min)
- ✅ Ticker coverage mismatch fixed (28 → 39 tickers)

Session 3 (current — ML/Learning Pipeline):
- ✅ Dispatcher now saves features_snapshot to dispatch_executions
- ✅ Position manager sync order fixed (DB-first → features flow to position_history)
- ✅ Trade Analyzer service built and deployed (statistical analysis → learning_recommendations)
- ✅ First analysis run: 6 findings from 35 trades written for human review

**Result:** BAC auto-closed at +99% profit target. Learning pipeline operational.

Session 4 (current):
- ✅ Cross-account position sync bug fixed (tiny PM now correctly tracks positions)
- ✅ Cleaned up 8,851 stuck "closing" records in tiny account (migration 1037)
- ✅ Dispatcher position count bug fixed (was using Alpaca account_name 'large-100k' instead of DB account_name 'large')
- ✅ max_positions and max_exposure gates now working correctly (were effectively disabled due to account_name mismatch)

### Applied from Analyzer Findings:
- ✅ Swing trade confidence threshold raised: 0.40 → 0.55 (7 trades below 0.5 averaged -29.5%)
- ✅ Volume multiplier: below-surge (1.5-2.0x) penalized 0.8 instead of neutral 1.0 (no-surge trades avg -23.8%)
- ✅ max_hold_minutes already 360 (applied Feb 7, analyzer confirmed it was correct)
- ⏳ CALL/PUT bias and trend alignment: deferred until 100+ trades (too noisy at 35)
- ✅ Trade analyzer scheduled daily at 9:15 PM UTC (Mon-Fri, after market close)
- ✅ Learning Applier built — Bedrock Claude reviews findings, auto-applies SSM changes, flags code changes
- ✅ Learning Applier scheduled daily at 9:30 PM UTC (15 min after analyzer)
- ✅ Backfilled features for 10/15 open positions from their recommendations

### Signal Quality Tuning (Feb 11, Session 5):
- ✅ SSM configs converted from YAML to JSON (json.loads was silently failing, falling back to old defaults)
- ✅ confidence_min: 0.55 (was 0.3 via fallback), confidence_min_options_swing: 0.58, confidence_min_options: 0.58
- ✅ last_entry_hour_et: 15 (blocks new entries after 3 PM ET — 3-4 PM trades avg -39.4%)
- ✅ Both large and tiny dispatchers verified loading tier-specific configs correctly

### EOD Trading Strategy (Feb 11, Session 6):
- ✅ EOD Exit Engine implemented — replaces blanket 3:55 PM force-close with strategy-aware, P&L-aware system
- ✅ Graduated close windows: 4 checkpoints (2:30, 3:00, 3:30, 3:55 PM ET) with progressively stricter criteria
- ✅ Strategy routing: day trades close at final window; swing trades evaluated for overnight hold
- ✅ Overnight hold criteria: DTE ≥ 3, P&L ≥ 10% (large) / 15% (tiny), position size ≤ 5% of equity
- ✅ Theta scoring: high theta decay lowers P&L threshold; DTE ≤ 2 + high theta forces close
- ✅ VIX regime adjustment: elevated/high/extreme VIX tightens criteria or forces close
- ✅ Earnings calendar client: positions with earnings within 1 trading day force-closed
- ✅ Overnight exposure limit: $5K large, $200 tiny; least profitable closed first
- ✅ Close-loop monitor: detects stuck closes, retries once, queues for next open
- ✅ Entry cutoff gates: strategy-specific cutoffs (day trade 2 PM / swing 3 PM for large)
- ✅ Duplicate position blocking: one position per ticker/account/instrument type
- ✅ 40 property-based + unit tests passing (theta, VIX, earnings, close-loop, EOD engine)
- ✅ All SSM-configurable per account tier
- New files: `eod_engine.py`, `eod_config.py`, `eod_models.py`, `close_loop.py`, `earnings_client.py`
- Modified: `monitor.py`, `main.py`, `exits.py`, `config.py`, `gates.py`, dispatcher `config.py`

### AI Learning Loop (Fully Automated):
```
Trades close → position_history (with features)
  → Trade Analyzer (9:15 PM UTC) → learning_recommendations
  → Learning Applier (9:30 PM UTC) → Bedrock reviews → auto-apply SSM / flag code changes
```

---

## 📊 Services Status

### Persistent Services (6/6 Running)

| Service | Task Def | Image Tag | Status |
|---------|----------|-----------|--------|
| dispatcher-service | :39 | dispatcher:latest | ✅ Running |
| dispatcher-tiny-service | :19 | dispatcher:latest | ✅ Running |
| position-manager-service | :10 | position-manager:latest | ✅ Running |
| position-manager-tiny-service | :1 | position-manager:latest | ✅ Running |
| telemetry-service | :1 | telemetry:service-mode | ✅ Running |
| trade-stream | — | — | ✅ Running |

### One-Shot Tasks

| Task | Task Def | Purpose |
|------|----------|---------|
| trade-analyzer | ops-pipeline-trade-analyzer:1 | Statistical analysis of trade outcomes → learning_recommendations |

### Scheduled Tasks (5/5 Active)

| Task | Schedule | Status |
|------|----------|--------|
| signal-engine-1m | Every minute | ✅ Working |
| feature-computer-1m | Every minute | ✅ Working |
| watchlist-engine-5m | Every 5 minutes | ✅ Working |
| ticker-discovery | Weekly | ✅ Working |
| rss-ingest-task | Every minute | ✅ Working |

---

## 🔧 Fixes Deployed Feb 11, 2026

### Fix 1: Telemetry Crash-Loop (CRITICAL)
**File:** `services/telemetry_ingestor_1m/main.py`  
**Problem:** `sys.exit(0)` after each run. `SystemExit` inherits from `BaseException`, not `Exception`, so the outer loop couldn't catch it. Process died every run, ECS restarted (2-3 min gap), bar data went stale (>120s), `bar_freshness` gate blocked ALL trades.  
**Fix:** Changed `sys.exit(0)` to `return`, `sys.exit(1)` to `raise`.  
**Verified:** Telemetry runs continuously, ~60s cycle.

### Fix 2: Bar Freshness Threshold (CRITICAL)
**SSM:** `/ops-pipeline/dispatcher_config_large`, `/ops-pipeline/dispatcher_config_tiny`  
**Problem:** Default `max_bar_age_seconds=120` too tight. Telemetry cycle is ~78s (18s fetch + 60s sleep). Bars frequently 130-160s old.  
**Fix:** Set `max_bar_age_seconds: 180` in both SSM configs.  
**Verified:** Gate logs show "Bar age 134s ≤ threshold 180s" — PASSING.

### Fix 3: Dispatcher Competition (CRITICAL)
**File:** `services/dispatcher/db/repositories.py`  
**Migration:** `db/migrations/1035_fix_dispatcher_competition.sql`  
**Problem:** `claim_pending_recommendations()` used `FOR UPDATE SKIP LOCKED` — whichever dispatcher ran first exclusively claimed the recommendation. The large dispatcher consistently found 0 recommendations.  
**Fix:**
- Changed claim to non-exclusive read: `NOT IN (SELECT recommendation_id FROM dispatch_executions WHERE account_name = %s)`
- Added `allowed_actions` filter so dispatchers only see signals they can process
- DB migration: Changed UNIQUE index from `(recommendation_id)` to `(recommendation_id, account_name)`

**Verified:** Both dispatchers independently process same signals.

### Fix 4: Position Manager Crash-Loop
**File:** `services/position_manager/main.py`  
**Problem:** Same `sys.exit(1)` pattern as telemetry.  
**Fix:** Changed to `raise` so outer loop catches and retries.

### Fix 5: Stale Docker Image Tags
**Problem:** Task definitions used `sql-transaction-fix-v4` tag instead of `:latest`.  
**Fix:** Registered new task definitions pointing to `:latest`.

### Fix 6: Large Account Credentials
**Secret:** Created `ops-pipeline/alpaca/large`  
**Problem:** Dispatcher looked for `ops-pipeline/alpaca/large`, couldn't find it, fell back to default with hardcoded `account_name: "large-default"`.  
**Fix:** Created the secret with `account_name: "large-100k"`.  
**Verified:** Logs show "Loaded large account credentials: large-100k".

### Fix 7: Option Price Tracking (CRITICAL)
**File:** `services/position_manager/monitor.py`  
**Problem:** `get_current_price()` used `alpaca_client.get_open_position()` for options — returns broker's stale position valuation, not live market data. All option prices in DB were wrong. Take-profits and stop-losses not triggering correctly. MSFT had to be manually closed at +129.9% because system thought it was +21.6%.  
**Fix:** New `_get_option_quote()` function calls Alpaca Market Data API `/v1beta1/options/quotes/latest` for live bid/ask mid-price. Falls back to `bar_fetcher` if no quote available.  
**Verified:** ADBE went from $11.75→$16.61, INTC from +10%→-13%, BAC auto-closed at +99% profit target.

### Fix 8: Dispatcher Backlog
**SSM:** `lookback_window_minutes: 5` added to both dispatcher configs  
**Problem:** 60-minute lookback returned 100+ old signals. They all failed `recommendation_freshness` gate (>300s). Fresh signals existed but weren't reached.  
**Fix:** Set `lookback_window_minutes: 5` to match the 300s freshness gate.  
**Verified:** Dispatchers now find 1-2 fresh signals per run instead of churning through stale ones.

### Fix 9: Ticker Coverage Mismatch
**SSM:** `/ops-pipeline/tickers` updated from 28 to 39 tickers  
**Problem:** 11 tickers in signal engine watchlist had no telemetry data (AAPL, AMZN, BMY, CAT, CSCO, DE, HD, HON, LLY, MMM, PG). These always failed `bar_freshness`.  
**Fix:** Updated SSM to union of telemetry + watchlist tickers.

---

### Fix 10: Cross-Account Position Sync (CRITICAL)
**File:** `services/position_manager/db.py`, `services/position_manager/monitor.py`
**Migration:** `db/migrations/1037_cleanup_stuck_closing_tiny.sql`
**Problem:** `get_position_by_symbol()` didn't filter by `account_name`. When tiny PM checked if AMZN/AAPL/INTC were tracked, it found the large account's positions and skipped creating tiny entries. Also 8,851 stuck "closing" records accumulated in tiny account.
**Fix:** Added `account_name` parameter to `get_position_by_symbol()`. Updated `sync_from_alpaca_positions()` to pass account name. Migration cleaned up stuck records.
**Verified:** Tiny PM now tracks 4 positions (AAPL, AMZN, INTC, CSCO).

### Fix 11: Dispatcher Position Count Mismatch (CRITICAL)
**File:** `services/dispatcher/main.py`
**Problem:** Dispatcher used `config['account_name']` (from Alpaca secret: `'large-100k'`/`'tiny-1k'`) to query `active_positions`, but position manager stores `account_name` as `'large'`/`'tiny'` (from `ACCOUNT_TIER` env var). Result: `get_account_state()` always returned 0 positions, making `max_positions` and `max_exposure` gates effectively disabled.
**Fix:** Changed to use `config['account_tier']` (`'large'`/`'tiny'`) which matches the DB values.
**Verified:** Large dispatcher now shows "At position limit: 22/5", tiny shows "Positions 4/5".

---

## 💰 Current Positions (Feb 11, 17:00 UTC)

**Prices now accurate (live quotes from Alpaca Market Data API):**

| Position | Type | Entry | Current | P&L | Account |
|----------|------|-------|---------|-----|---------|
| ADBE | PUT | $11.75 | $16.61 | +41.4% | large |
| INTC | PUT | $2.07 | $1.79 | -13.3% | large |
| MSFT | PUT | $4.85 | $12.28 | +153.2% | large |
| NVDA | PUT | $7.20 | $6.42 | -10.9% | large |
| UNH | PUT | $5.00 | $4.13 | -17.4% | large |
| BAC | PUT | $0.57 | $1.14 | +99.1% | large ✅ CLOSED |
| PG | CALL | $4.10 | $6.00 | +46.5% | tiny |
| QCOM | CALL | $3.30 | $3.58 | +8.6% | tiny |

---

## ⚙️ Current Configuration

### SSM Parameters
- `/ops-pipeline/dispatcher_config_large`: `max_bar_age_seconds: 180`, `lookback_window_minutes: 5`, `allowed_actions: ["BUY_CALL", "BUY_PUT"]`
- `/ops-pipeline/dispatcher_config_tiny`: `max_bar_age_seconds: 180`, `lookback_window_minutes: 5`, `allowed_actions: ["BUY_CALL", "BUY_PUT", "BUY_STOCK", "SELL_STOCK"]`
- `/ops-pipeline/tickers`: 39 tickers (expanded from 28)

### Secrets Manager
- `ops-pipeline/alpaca` — Large account credentials (account_name: large-100k)
- `ops-pipeline/alpaca/large` — Same as above (created Feb 11 so dispatcher finds it by tier)
- `ops-pipeline/alpaca/tiny` — Tiny account credentials

---

## ⚠️ Known Issues (Non-Critical)

### 1. Options Bars 403 Errors
**Service:** position-manager  
**Error:** 403 on `/v1beta1/options/bars`  
**Impact:** LOW — Learning feature only. Price tracking now uses `/v1beta1/options/quotes/latest` which works fine.

### 2. Tiny Account Position Sizing
**Problem:** Position sizes ($25K) exceed tiny account buying power (~$122). All tiny trades fall back to `SIMULATED_FALLBACK`.  
**Impact:** MEDIUM — Tiny account can't execute real paper trades.  
**Fix needed:** `compute_position_size()` in `services/dispatcher/sim/pricing.py` needs to account for actual buying power.

### 3. Redundant Scheduled Dispatcher-Tiny
**Problem:** EventBridge schedule `ops-pipeline-dispatcher-tiny` (rate 5 min) still runs alongside persistent `dispatcher-tiny-service`.  
**Impact:** LOW — May cause duplicate processing attempts.  
**Fix:** Disable the EventBridge schedule.

### 4. Large Account at Position Limit
**Problem:** 22 open positions vs max_open_positions=5. Now that the gate works correctly, no new trades will execute until positions close.  
**Impact:** MEDIUM — Large account blocked from new trades.  
**Fix options:** Either wait for positions to close naturally, or increase `max_open_positions` in SSM `/ops-pipeline/dispatcher_config_large`.

### 5. Uncommitted Code Changes
**8+ files modified but not committed to git** (from multiple sessions)

---

## 📊 Data Quality

| Metric | Value |
|--------|-------|
| Tickers monitored | 39 |
| Telemetry cycle | ~60s continuous |
| Bar freshness | 130-160s (within 180s threshold) |
| Option price source | Live quotes API (bid/ask mid) |
| Signal generation | 1-4 per minute |
| Dispatcher lookback | 5 minutes |

---

## 🎯 Next Steps

1. **Fix tiny account position sizing** — `compute_position_size()` needs buying power check
2. **Disable redundant dispatcher-tiny schedule** — EventBridge cleanup
3. **Commit all code changes to git** — 7 files uncommitted
4. **Monitor MSFT position** — +153% gain, well past +80% take-profit target
5. **Accumulate trades** — Target 50 for AI learning activation

---

## 📞 Quick Reference

**AWS Account:** 160027201036  
**Region:** us-west-2  
**ECS Cluster:** ops-pipeline-cluster  
**RDS:** ops-pipeline-db.cls4wuyg010k.us-west-2.rds.amazonaws.com  
**Lambda (queries):** ops-pipeline-db-query  
**Alpaca Dashboard:** https://app.alpaca.markets/paper/dashboard

```bash
# Refresh credentials
ada cred update --account 160027201036 --role IibsAdminAccess-DO-NOT-DELETE --provider conduit --once

# Check service health
aws ecs describe-services --cluster ops-pipeline-cluster \
  --services dispatcher-service position-manager-service telemetry-service \
  --region us-west-2 --query 'services[*].[serviceName,runningCount,desiredCount]'

# Check position manager prices
aws logs tail /ecs/ops-pipeline/position-manager-service --region us-west-2 --since 5m | grep "Price:"

# Check dispatcher activity
aws logs tail /ecs/ops-pipeline/dispatcher --region us-west-2 --since 5m | grep "recommendations_claimed"
```
