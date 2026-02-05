# Complete Trading System Status - February 4, 2026

**Time:** 3:45 PM ET  
**Market:** OPEN (9:30 AM - 4:00 PM ET)  
**Status:** ✅ FIXED - Trades should start within 10 minutes

---

## Root Cause: Ticker List Mismatch

### The Problem
The system had **TWO different ticker parameters** that got out of sync:

1. **`/ops-pipeline/tickers`** (28 tickers) ← Used by **Telemetry Service**
2. **`/ops-pipeline/universe_tickers`** (36 tickers) ← Used by **Watchlist Engine**

This caused:
- Watchlist selected tickers with stale data (AAPL, TSLA, AMZN from days ago)
- Signal engine generated only HOLD signals (low confidence)
- HOLD signals not inserted into recommendations table
- Dispatcher found zero recommendations to execute
- **Result: NO TRADES**

### The Fix Applied

1. ✅ **Synchronized ticker lists** - Updated `/ops-pipeline/universe_tickers` to match `/ops-pipeline/tickers` (28 tickers)
2. ✅ **Updated ticker discovery code** - Now updates BOTH parameters when AI refreshes tickers
3. ✅ **Both dispatchers running as services** - Large and tiny accounts both active

---

## System Architecture

### AI Ticker Discovery (Every 6 Hours)
```
Ticker Discovery Service (ECS Task)
  ↓ Analyzes market with Bedrock Claude Sonnet
  ↓ Recommends 35 tickers based on:
     - News momentum
     - Volume surges  
     - Technical setups
     - Options liquidity
  ↓ Updates BOTH SSM parameters:
     - /ops-pipeline/tickers (telemetry)
     - /ops-pipeline/universe_tickers (watchlist)
  ↓ Stores recommendations in ticker_universe table
```

**Schedule:** Every 6 hours via EventBridge Scheduler  
**Last Run:** Check with: `aws scheduler get-schedule --name ticker-discovery-6h --region us-west-2`

### Trading Pipeline (Continuous)

```
1. Telemetry Service (every 1 min)
   ↓ Fetches OHLCV data from Alpaca
   ↓ Stores in lane_features_clean table
   ↓ Tracks: /ops-pipeline/tickers (28 tickers)

2. Watchlist Engine (every 5 min)
   ↓ Scores universe tickers
   ↓ Selects top 30 (or all if <30)
   ↓ Universe: /ops-pipeline/universe_tickers (28 tickers)
   ↓ Stores in watchlist_state table

3. Signal Engine (every 1 min)
   ↓ Generates signals for active watchlist
   ↓ Applies confidence thresholds
   ↓ Inserts actionable signals (not HOLD) into recommendations table

4. Dispatcher - Large Account (every 1 min)
   ↓ Claims pending recommendations
   ↓ Evaluates risk gates
   ↓ Executes trades via Alpaca Paper API
   ↓ Account: ACCOUNT_TIER=large
   ↓ Config: /ops-pipeline/dispatcher_config

5. Dispatcher - Tiny Account (every 1 min)
   ↓ Claims pending recommendations  
   ↓ Evaluates risk gates
   ↓ Executes trades via Alpaca Paper API
   ↓ Account: ACCOUNT_TIER=tiny
   ↓ Config: /ops-pipeline/dispatcher_config_tiny
```

---

## Service Status

### ECS Services (Continuous)
```bash
✅ telemetry-service          - Fetching data every 1 min
✅ dispatcher-service          - Large account (LOOP mode)
✅ dispatcher-tiny-service     - Tiny account (LOOP mode)
✅ position-manager-service    - Monitoring positions
✅ trade-stream                - Real-time trade updates
✅ ops-pipeline-classifier-service - News classification
```

### ECS Scheduled Tasks (Periodic)
```bash
✅ watchlist-engine-5m         - Every 5 minutes
✅ signal-engine-1m            - Every 1 minute
✅ feature-computer-1m         - Every 1 minute
✅ ticker-discovery            - Every 6 hours
```

### Log Groups
```
Dispatcher (large):  /ecs/ops-pipeline/dispatcher
Dispatcher (tiny):   /ecs/ops-pipeline/dispatcher-tiny
Telemetry:           /ecs/ops-pipeline/telemetry-service
Signal Engine:       /ecs/ops-pipeline/signal-engine-1m
Watchlist:           /ecs/ops-pipeline/watchlist-engine-5m
Position Manager:    /ecs/ops-pipeline/position-manager-service
```

**IMPORTANT:** Dispatcher logs to `/ecs/ops-pipeline/dispatcher` NOT `/ecs/ops-pipeline/dispatcher-service`

---

## Current Configuration

### Ticker Lists (Now Synchronized)
Both parameters now have the same 28 tickers:
```
NVDA, AMD, META, GOOGL, AVGO, CRM, MSFT, QCOM, NOW, ORCL,
JPM, UNH, LLY, XOM, CVX, PFE, BAC, WMT, PG, HD,
CAT, DE, GS, RTX, HON, MRK, BMY, MMM
```

### Account Configurations

**Large Account ($209K):**
```json
{
  "account_tier": "large",
  "max_contracts": 10,
  "max_exposure": 50000,
  "max_positions": 5,
  "confidence_threshold": 0.40,
  "allowed_actions": ["BUY_CALL", "BUY_PUT", "BUY_STOCK", "SELL_STOCK"]
}
```
**SSM:** `/ops-pipeline/dispatcher_config`  
**Secrets:** `ops-pipeline/alpaca` (default)

**Tiny Account ($1.8K):**
```json
{
  "account_tier": "tiny",
  "max_contracts": 2,
  "max_exposure": 1500,
  "max_positions": 2,
  "confidence_threshold": 0.40,
  "allowed_actions": ["BUY_CALL", "BUY_PUT", "BUY_STOCK", "SELL_STOCK"]
}
```
**SSM:** `/ops-pipeline/dispatcher_config_tiny`  
**Secrets:** `ops-pipeline/alpaca/tiny`

---

## Verification Steps

### 1. Check Watchlist Updated (5 min)
```bash
aws logs filter-log-events \
  --log-group-name /ecs/ops-pipeline/watchlist-engine-5m \
  --start-time $(($(date +%s) - 600))000 \
  --region us-west-2 \
  --filter-pattern "watchlist_selected" | \
  jq -r '.events[].message' | tail -5
```
**Expected:** `"selected": 28` (not 17)

### 2. Check Signal Engine Generating Trades (1-2 min)
```bash
aws logs filter-log-events \
  --log-group-name /ecs/ops-pipeline/signal-engine-1m \
  --start-time $(($(date +%s) - 300))000 \
  --region us-west-2 \
  --filter-pattern "recommendation_created" | \
  jq -r '.events[].message' | tail -10
```
**Expected:** See BUY_CALL or BUY_PUT recommendations (not all HOLD)

### 3. Check Dispatcher Executing (1-2 min)
```bash
# Large account
aws logs filter-log-events \
  --log-group-name /ecs/ops-pipeline/dispatcher \
  --start-time $(($(date +%s) - 300))000 \
  --region us-west-2 \
  --filter-pattern "recommendations_claimed" | \
  jq -r '.events[].message' | tail -5

# Tiny account  
aws logs filter-log-events \
  --log-group-name /ecs/ops-pipeline/dispatcher-tiny \
  --start-time $(($(date +%s) - 300))000 \
  --region us-west-2 \
  --filter-pattern "recommendations_claimed" | \
  jq -r '.events[].message' | tail -5
```
**Expected:** `"count": > 0` (not 0)

### 4. Check Trades Executed
```bash
aws logs filter-log-events \
  --log-group-name /ecs/ops-pipeline/dispatcher \
  --start-time $(($(date +%s) - 600))000 \
  --region us-west-2 \
  --filter-pattern "EXECUTED" | \
  jq -r '.events[].message' | tail -10
```
**Expected:** See EXECUTED status with trade details

---

## What Changed

### Code Changes
1. **`services/ticker_discovery/discovery.py`**
   - Now updates BOTH `/ops-pipeline/tickers` AND `/ops-pipeline/universe_tickers`
   - Ensures telemetry and watchlist always use same ticker list

### Configuration Changes
1. **`/ops-pipeline/universe_tickers`** (SSM Parameter)
   - Updated from 36 tickers → 28 tickers
   - Now matches `/ops-pipeline/tickers`

### No Changes Needed
- ✅ Both dispatchers already running as services (not schedulers)
- ✅ Both accounts have correct ACCOUNT_TIER environment variables
- ✅ Both accounts have separate SSM configs and Alpaca secrets
- ✅ All other services running correctly

---

## Timeline to Trading

**Now (3:45 PM):** Fix applied, ticker lists synchronized

**3:50 PM:** Watchlist engine next run
- Will pick up new 28-ticker universe
- All tickers will have fresh data
- Should select 28 active tickers

**3:51 PM:** Signal engine next run
- Will generate signals for fresh watchlist
- Should produce actionable BUY signals (not HOLD)
- Recommendations inserted into database

**3:52 PM:** Dispatcher next run
- Will claim pending recommendations
- Will execute trades via Alpaca Paper API
- **FIRST TRADES SHOULD EXECUTE**

---

## Monitoring Commands

### Quick Health Check
```bash
# Check all services running
aws ecs list-services --cluster ops-pipeline-cluster --region us-west-2

# Check recent dispatcher activity (large)
aws logs tail /ecs/ops-pipeline/dispatcher --since 5m --region us-west-2

# Check recent dispatcher activity (tiny)
aws logs tail /ecs/ops-pipeline/dispatcher-tiny --since 5m --region us-west-2

# Check telemetry fetching data
aws logs tail /ecs/ops-pipeline/telemetry-service --since 2m --region us-west-2
```

### Check Ticker Lists Match
```bash
# Telemetry list
aws ssm get-parameter --name /ops-pipeline/tickers --region us-west-2 --query 'Parameter.Value' --output text

# Watchlist universe
aws ssm get-parameter --name /ops-pipeline/universe_tickers --region us-west-2 --query 'Parameter.Value' --output text

# Should be identical!
```

---

## Next AI Ticker Update

The ticker discovery service will run again in ~6 hours and may update the ticker list based on:
- Market news and momentum
- Volume surges
- Technical setups
- Sector rotation

When it runs, it will now update BOTH parameters automatically, keeping them in sync.

---

## Summary

✅ **Root cause identified:** Ticker list mismatch between telemetry and watchlist  
✅ **Fix applied:** Synchronized both SSM parameters  
✅ **Code updated:** Ticker discovery now updates both parameters  
✅ **Services verified:** Both dispatchers running as services (not schedulers)  
✅ **Expected result:** Trades should start within 5-10 minutes  

**Market closes at 4:00 PM ET** - We have 15 minutes to see trades execute!
