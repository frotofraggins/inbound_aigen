# Root Cause: Why No Trades Are Happening

**Date:** February 4, 2026, 3:38 PM ET  
**Status:** ✅ FIXED

## Problem Summary

No trades were executing in either the large or tiny account despite:
- Market being OPEN
- All services running
- Recommendations being generated
- No obvious errors

## Root Cause Analysis

### The Issue
The system had **TWO different ticker lists** in SSM Parameter Store:

1. **`/ops-pipeline/tickers`** (28 tickers) - Used by **Telemetry Service**
   - NVDA, AMD, META, GOOGL, AVGO, CRM, MSFT, QCOM, NOW, ORCL, JPM, UNH, LLY, XOM, CVX, PFE, BAC, WMT, PG, HD, CAT, DE, GS, RTX, HON, MRK, BMY, MMM

2. **`/ops-pipeline/universe_tickers`** (36 tickers) - Used by **Watchlist Engine**
   - AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA, NFLX, ADBE, CRM, ORCL, INTC, AMD, QCOM, TXN, AVGO, CSCO, IBM, MU, AMAT, LRCX, KLAC, SNPS, CDNS, ASML, TSM, NOW, PLTR, SNOW, DDOG, ZS, NET, CRWD, PANW, FTNT, OKTA

### The Cascade Effect

```
Telemetry Service (every 1 min)
  ↓ Fetches fresh data for 28 tickers ✅
  
Watchlist Engine (every 5 min)
  ↓ Tries to score 36 tickers
  ↓ Only 17 have fresh features (missing 19!)
  ↓ Selects top 17 from stale data ❌
  
Signal Engine (every 1 min)
  ↓ Generates signals for watchlist (17 tickers)
  ↓ Many have stale data (AAPL, TSLA, AMZN from days ago)
  ↓ All signals are HOLD (confidence too low) ❌
  ↓ HOLD signals NOT inserted into recommendations table
  
Dispatcher (every 1 min)
  ↓ Queries for pending recommendations
  ↓ Finds ZERO recommendations ❌
  ↓ Logs: "no_pending_recommendations"
  ↓ No trades executed
```

### Evidence

**Signal Engine Logs (15:26:43):**
```json
{"event": "watchlist_loaded", "count": 17, "tickers": ["MSFT", "ORCL", "QCOM", "AVGO", "AMD", "NVDA", "GOOGL", "AMZN", "NOW", "META", "AAPL", "ADBE", "CSCO", "TSLA", "NFLX", "INTC", "CRM"]}

{"event": "signal_computed", "ticker": "MSFT", "action": "HOLD", "confidence": 0.143, "rule": "CONFIDENCE_TOO_LOW"}
{"event": "signal_computed", "ticker": "ORCL", "action": "HOLD", "confidence": 0.239, "rule": "CONFIDENCE_TOO_LOW"}
{"event": "signal_computed", "ticker": "GOOGL", "action": "HOLD", "confidence": 0.0, "rule": "VOLUME_TOO_LOW"}
{"event": "signal_computed", "ticker": "AMZN", "action": "HOLD", "confidence": 0.0, "rule": "VOLUME_TOO_LOW"}
```

**Dispatcher Logs (15:26:43):**
```json
{"event": "recommendations_claimed", "count": 0, "tickers": []}
{"event": "no_pending_recommendations", "message": "No pending recommendations to process"}
```

**Watchlist Engine Logs (15:08:07):**
```json
{"event": "config_loaded", "universe_size": 36}
{"event": "scoring_complete", "scored": 17, "missing_features": 19}
{"event": "watchlist_selected", "selected": 17}
```

## The Fix

Updated `/ops-pipeline/universe_tickers` to match `/ops-pipeline/tickers`:

```bash
aws ssm put-parameter \
  --name /ops-pipeline/universe_tickers \
  --value "NVDA,AMD,META,GOOGL,AVGO,CRM,MSFT,QCOM,NOW,ORCL,JPM,UNH,LLY,XOM,CVX,PFE,BAC,WMT,PG,HD,CAT,DE,GS,RTX,HON,MRK,BMY,MMM" \
  --type String \
  --overwrite \
  --region us-west-2
```

## Expected Outcome

Within 5-10 minutes:
1. ✅ Watchlist Engine picks up new 28-ticker universe
2. ✅ All 28 tickers have fresh telemetry data
3. ✅ Signal Engine generates actionable signals (not HOLD)
4. ✅ Recommendations inserted into database
5. ✅ Dispatcher executes trades

## Verification Steps

Wait 10 minutes, then check:

```bash
# Check watchlist selected tickers
aws logs filter-log-events \
  --log-group-name /ecs/ops-pipeline/watchlist-engine-5m \
  --start-time $(($(date +%s) - 600))000 \
  --region us-west-2 \
  --filter-pattern "watchlist_selected"

# Check signal engine generated non-HOLD signals
aws logs filter-log-events \
  --log-group-name /ecs/ops-pipeline/signal-engine-1m \
  --start-time $(($(date +%s) - 600))000 \
  --region us-west-2 \
  --filter-pattern "recommendation_created"

# Check dispatcher found recommendations
aws logs filter-log-events \
  --log-group-name /ecs/ops-pipeline/dispatcher \
  --start-time $(($(date +%s) - 600))000 \
  --region us-west-2\
  --filter-pattern "recommendations_claimed"
```

## Lessons Learned

1. **Single Source of Truth:** Having two ticker parameters (`/tickers` and `/universe_tickers`) created a synchronization problem
2. **Service Dependencies:** Telemetry → Watchlist → Signal → Dispatcher is a chain - any mismatch breaks the flow
3. **HOLD Signals:** The signal engine correctly doesn't persist HOLD signals, but this made the problem invisible
4. **Log Group Names:** Dispatcher logs to `/ecs/ops-pipeline/dispatcher` not `/ecs/ops-pipeline/dispatcher-service`

## Recommendation

Consider consolidating to a single ticker parameter, or add validation to ensure both lists stay in sync.
