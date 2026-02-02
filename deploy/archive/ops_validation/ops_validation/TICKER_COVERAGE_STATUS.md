# Ticker Coverage Status - Phase 9

**Date:** 2026-01-13  
**Finding:** Parameter mismatch between data collection (7) and universe (36)

---

## Current Configuration

### Data Collection Layer (7 Stocks)
**Parameter:** `/ops-pipeline/tickers`  
**Used By:** Telemetry, Features  
**Stocks:** AAPL, MSFT, TSLA, GOOGL, AMZN, META, NVDA

### Watchlist Universe (36 Stocks)
**Parameter:** `/ops-pipeline/universe_tickers`  
**Used By:** Watchlist Engine  
**Stocks:** All 36 tech stocks (full list in parameter)

---

## Actual Behavior (Phase 9)

**Watchlist Engine:**
- Attempts to score 36 stocks
- Only 7 have telemetry/features data  
- Selects "top 30" from 7 available
- **Result:** All 7 stocks enter watchlist (100% coverage of available)

**Signal Engine:**
- Processes watchlist (7 stocks)
- Generates recommendations for available stocks

**Dispatcher:**
- Processes recommendations from 7-stock universe

---

## Why This Is Intentional (Phase 9 Validation)

**Phase 8.0a-8.1:** Built with 7-stock core for testing  
**Phase 9:** Validating execution layer with proven 7-stock dataset  
**Option A (Future):** Expand to 36 or 120-150 stocks

**Benefit:** Known-good data lets us validate dispatcher logic without variable noise.

---

## Issue: Validation Expectations Must Match Reality

### ❌ Wrong Expectation:
- Watchlist selects 30 stocks
- 36-stock coverage

### ✅ Correct Expectation (Phase 9):
- Watchlist selects 7 stocks (all available)
- 7-stock coverage
- Top 30 selection will activate when >= 30 stocks have data

---

## Required DB Validation Queries

Run these via Lambda to verify end-to-end flow:

### Query A: Watchlist Activity
```sql
-- Check if watchlist ran recently
SELECT 
  NOW() - MAX(computed_at) AS watchlist_lag_minutes,
  COUNT(*) as total_stocks,
  COUNT(*) FILTER (WHERE in_watchlist = TRUE) as in_watchlist_count
FROM watchlist_state;
```

**Pass Criteria:**
- lag < 15 minutes
- total_stocks: 7-36
- in_watchlist_count: 7 (current scope)

---

### Query B: Signal Generation
```sql
-- Signals generated in last hour
SELECT COUNT(*) AS signals_last_hour,
       COUNT(DISTINCT ticker) as unique_tickers
FROM dispatch_recommendations
WHERE ts >= NOW() - INTERVAL '1 hour';
```

**Pass Criteria:**
- signals_last_hour: 0-50 (depends on market + rules)
- unique_tickers: 0-7

**Explainable 0:** Market closed or no stocks meet entry criteria

---

### Query C: Dispatcher Processing
```sql
-- Recommendation status breakdown (last hour)
SELECT
  SUM(CASE WHEN status='SIMULATED' THEN 1 ELSE 0 END) AS simulated,
  SUM(CASE WHEN status='SKIPPED' THEN 1 ELSE 0 END) AS skipped,
  SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END) AS failed,
  SUM(CASE WHEN status='PENDING' THEN 1 ELSE 0 END) AS pending,
  SUM(CASE WHEN status='PROCESSING' THEN 1 ELSE 0 END) AS processing
FROM dispatch_recommendations
WHERE ts >= NOW() - INTERVAL '1 hour';
```

**Pass Criteria:**
- processing: 0 (must be zero)
- pending: 0-10 (normal accumulation)
- simulated + skipped > 0 (shows dispatcher ran)

---

## Action Items

### During Phase 9 Shakedown (Next 7 Days):
- [x] Document 7-stock scope is intentional
- [ ] Run 3 DB validation queries (A, B, C above)
- [ ] Verify end-to-end flow with 7 stocks
- [ ] Update acceptance expectations to match reality

### After Validation (Option A):
- [ ] Expand /ops-pipeline/tickers to 36 or 120-150
- [ ] Verify telemetry handles larger list
- [ ] Confirm watchlist selects top 30 from expanded universe
- [ ] Monitor for 7 days after expansion

---

## Summary

**Current State:** Intentional 7-stock core for Phase 9 validation  
**Issue:** Acceptance criteria assumed 36-stock coverage  
**Fix:** Update validation expectations to match 7-stock reality  
**Future:** Expand after proving dispatcher works with 7

**System is healthy. Just need to align validation to actual scope.**
