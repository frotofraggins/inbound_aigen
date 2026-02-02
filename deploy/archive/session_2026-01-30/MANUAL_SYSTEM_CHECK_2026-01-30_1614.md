# Manual System Check - Jan 30, 2026 4:14 PM ET

## Infrastructure Status

### ECS Cluster
```
Services: 1 (position-manager-service)
Tasks Running: 1
Task: position-manager-service running continuously
```

### Secrets Manager (3 secrets)
```
✅ ops-pipeline/db (database credentials)
✅ ops-pipeline/alpaca (large-100k account - PKHE57...)
✅ ops-pipeline/alpaca/tiny (tiny-1k account - PKRTA...)
```

### Active Schedulers (11 ENABLED)
```
✅ ops-pipeline-dispatcher
✅ ops-pipeline-signal-engine-1m
✅ ops-pipeline-dispatcher-tiny
✅ ticker-discovery-6h
✅ trade-alert-checker
✅ ops-pipeline-classifier
✅ ops-pipeline-feature-computer-1m
✅ ops-pipeline-rss-ingest
✅ ops-pipeline-healthcheck-5m
✅ ops-pipeline-telemetry-ingestor-1m (→ revision 7)
✅ ops-pipeline-watchlist-engine-5m
```

---

## Position Manager Service - WORKING ✅

### API Calls Status:
```
✅ Alpaca GET /v2/positions → SUCCESS
✅ Found 3 positions in Alpaca:
   - QCOM260206C00150000
   - QCOM260227P00150000
   - SPY260130C00609000
✅ Base URL: https://paper-api.alpaca.markets
✅ Credentials: From Secrets Manager (ops-pipeline/alpaca)
✅ Authentication: Working
```

### Current Issue:
```
❌ Database schema error: column "option_symbol" missing
✅ Service handles gracefully (continues working)
✅ Logs show "Position Manager completed successfully"
✅ Sleeping 5 minutes between checks
```

**Result:** Position Manager IS monitoring your positions via Alpaca API, just can't persist to database yet.

---

## Telemetry Service - NOT WORKING ❌

### Scheduler Configuration:
```
State: ENABLED
Schedule: rate(1 minute)
Task Definition: ops-pipeline-telemetry-1m:7
```

### Latest Logs (16:13:51, 16:14:03):
```
❌ success: false
❌ tickers_total: 28
❌ tickers_ok: 0
❌ tickers_failed: 28
❌ total_rows_upserted: 0
```

### Issues Found:
1. Revision 7 supposedly uses DATA_SOURCE=yfinance
2. But still failing on all 28 tickers
3. Not getting Alpaca 401 errors anymore (progress!)
4. yfinance errors: "Expecting value: line 1 column 1"

---

## Alpaca API Access (From User Info)

### Basic Plan (Free) Includes:
```
✅ Trading API: Full access
   - POST /v2/orders (submit orders)
   - GET /v2/positions (get positions) 
   - GET /v2/account (account info)
   - GET /v1/options/contracts (options chain)

✅ Market Data API: IEX feed (free)
   - GET /v2/stocks/{symbol}/bars?feed=iex
   - Limited to IEX exchange (~2.5% of volume)
   - Should work with paper trading credentials

❌ Market Data API: SIP feed (requires paid plan)
   - GET /v2/stocks/{symbol}/bars?feed=sip
   - 100% market coverage
   - Not included in Basic plan
```

### Code Already Correct:
```python
# services/telemetry_ingestor_1m/sources/alpaca_1m.py
params = {
    'feed': 'iex'  # ✅ Correct for Basic plan
}
```

---

## Issues Summary

### Issue #1: Database Schema ⚠️
**Problem:** `active_positions` missing `option_symbol` column  
**Impact:** Position Manager can't persist synced positions  
**Status:** Migration 015 created, ready to apply  
**Blocking:** No - service works, just logs errors

### Issue #2: Telemetry Data Collection ❌
**Problem:** Still failing on all tickers  
**Potential Causes:**
1. Revision 7 not actually being used (scheduler cache)
2. yfinance having issues during market hours
3. Credentials not being passed correctly
4. Code issue in data fetching

**Impact:** No new price data since last night  
**Blocking:** Yes - need fresh data for signals

---

## What's Working

### ✅ Position Manager:
- Alpaca API calls successful
- Finding your 3 QCOM positions
- Running every 5 minutes as ECS Service
- Monitoring P&L (even if can't persist)

### ✅ Credentials:
- Secrets Manager configured correctly
- Position Manager loading from Secrets Manager
- Alpaca Trading API authentication working

### ✅ Infrastructure:
- ECS cluster operational
- Services can run
- Logs accessible

---

## What's NOT Working

### ❌ Telemetry:
- Not collecting market data
- Revision 7 (yfinance) failing
- All 28 tickers returning no data
- System using stale historical data

### ❌ Other Schedulers:
- 11 schedulers show ENABLED
- But only 1 ECS task running (position-manager-service)
- Schedulers may not be triggering (same issue as yesterday)

---

## Next Steps (Manual Verification)

### Test #1: Verify Alpaca IEX Access
```python
import requests

url = "https://data.alpaca.markets/v2/stocks/QCOM/bars"
headers = {
    'APCA-API-KEY-ID': 'PKHE57Z4BKSIUQLTNQQK...',
    'APCA-API-SECRET-KEY': 'Ft5yje4MJYbgRaEUGHbafgi5...'
}
params = {
    'timeframe': '1Min',
    'start': '2026-01-30T15:00:00Z',
    'end': '2026-01-30T16:00:00Z',
    'feed': 'iex',
    'limit': 100
}

response = requests.get(url, headers=headers, params=params)
print(f"Status: {response.status_code}")
print(response.json())
```

**Expected:** 200 OK with IEX bars (even on Basic plan)

### Test #2: Check Telemetry Task Revision
```bash
# Get running telemetry task
aws ecs list-tasks --cluster ops-pipeline-cluster \
  --family ops-pipeline-telemetry-1m --region us-west-2

# Check which revision it's using
aws ecs describe-tasks --cluster ops-pipeline-cluster \
  --tasks <task-arn> --region us-west-2 \
  --query 'tasks[0].taskDefinitionArn'
```

**Expected:** Should be revision 7 with yfinance

### Test #3: Database Column Check
```sql
SELECT column_name 
FROM information_schema.columns 
WHERE table_name = 'active_positions';
```

**Expected:** Should NOT have option_symbol (explains the error)

---

## Recommendations (NO DEPLOYMENTS YET)

1. **First:** Test Alpaca IEX API manually with credentials
2. **Then:** Verify what revision telemetry is actually running
3. **Then:** Decide on fix based on test results
4. **Finally:** Apply database migration if Position Manager working

**DO NOT deploy anything until manual tests confirm root cause.**
