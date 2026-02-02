# Production Logic V2.0 - Implementation Summary

**Date:** 2026-01-27 4:00 PM UTC  
**Status:** 🟡 READY FOR REVIEW (Not Yet Deployed)  
**Changes:** Signal Engine rules.py + Dispatcher gates.py + trading_params.json

---

## 🎯 What Was Changed

### 1. Signal Engine (rules.py) - Complete Rewrite

**OLD Logic (V1.0):**
```python
# Sentiment as HARD GATE
is_bullish = sentiment_score > 0.5 and trend_state >= 0
if not is_bullish and not is_bearish: HOLD

# Problem: NVDA with 8.63x volume rejected because sentiment not strong enough
```

**NEW Logic (V2.0):**
```python
# Direction from PRICE + TREND (not sentiment)
if (close above/at SMA20) and (trend_state == 1): BULL
if (close below/at SMA20) and (trend_state == -1): BEAR

# Sentiment becomes CONFIDENCE MODIFIER
sentiment_boost = 1 + (0.25 * strength * news_weight)  # If aligns
sentiment_penalty = 1 - (0.20 * strength * news_weight)  # If opposes

# Final confidence = base × sentiment × volume × move
```

**Key Improvements:**
1. ✅ **Sentiment as scaler, not gate** - Fixes NVDA issue without noise trades
2. ✅ **Strict trend requirement** - Options need trend_state = ±1 (no chop trades)
3. ✅ **volume_ratio defaults to None** - Catches missing data (was 1.0)
4. ✅ **Breakout confirmation** - Requires 1% move from SMA20
5. ✅ **Adaptive threshold slower** - 5% per 0.2 vol increase (was 10%), cap 0.75 (was 0.85)
6. ✅ **News count weighting** - More articles = higher sentiment impact
7. ✅ **Better volume multipliers** - Extended to 1.35x for extreme surges

### 2. Dispatcher Gates (gates.py) - Production Hardening

**Added Gates:**
1. ✅ **Recommendation freshness** - Max 5 minutes old (prevents stale executions)
2. ✅ **Ticker cooldown** - Min 15 minutes between trades (prevents whipsaw)
3. ✅ **SELL_STOCK position check** - Requires open long (prevents accidental shorts)
4. ✅ **Instrument-aware confidence** - Different thresholds for options vs stocks

**Robustness Improvements:**
1. ✅ **Safe field extraction** - `.get()` with defaults (no KeyError crashes)
2. ✅ **Action/Instrument normalization** - Handles aliases and format variations
3. ✅ **Safe datetime parsing** - Handles strings and datetime objects
4. ✅ **Validation** - Checks for known action/instrument values

### 3. Configuration (trading_params.json) - V2.0 Documentation

Updated to reflect new logic with complete parameter explanations and TODOs.

---

## ✅ Production Improvements Implemented

### Critical Fixes
- [x] Sentiment changed from hard gate → confidence scaler
- [x] Direction determined by price action + trend (NOT sentiment)
- [x] Strict trend requirement for options (trend_state = ±1)
- [x] volume_ratio defaults to None (catches missing data)
- [x] Breakout confirmation added (1% threshold)
- [x] Adaptive confidence with slower ramp (5% not 10%)
- [x] News count weighting in sentiment impact
- [x] Robust error handling in dispatcher gates
- [x] Instrument-aware confidence thresholds
- [x] Recommendation freshness gate
- [x] Ticker cooldown gate
- [x] SELL_STOCK position verification

---

## 🚨 REQUIRED TODOs Before Live Options Trading

### CRITICAL: Options Execution Gates (Dispatcher)

**Status:** ⚠️ NOT IMPLEMENTED - Will cause losses if ignored

**Required Implementation:**
```python
# In dispatcher at execution time (when fetching option chain):

1. Check bid/ask spread:
   spread_pct = (ask - bid) / mid
   if spread_pct > 0.10:  # 10% max
       BLOCK or fallback to STOCK

2. Check option volume:
   if daily_volume < 100:
       BLOCK

3. Check open interest:
   if open_interest < 100:
       BLOCK

4. Check IV percentile (when available):
   if iv_percentile > 80:
       BLOCK (options too expensive)
```

**Where to Implement:**
- File: `services/dispatcher/alpaca/options.py`
- Function: Add `validate_option_contract()` before execution
- Fallback: If any gate fails → try STOCK trade or skip

**Impact if not implemented:**
- Will buy illiquid options (can't exit)
- Will pay huge spreads (immediate loss)
- Will buy expensive options at IV peaks (poor risk/reward)

### HIGH Priority: Account-Level Kill Switches

**Status:** ⚠️ NOT IMPLEMENTED

**Required in Dispatcher:**
```python
1. Max daily loss: $500 (paper) / $X (live)
   - Check before ANY trade
   - If exceeded: BLOCK all trades for rest of day

2. Max open positions: 5
   - Count active_positions
   - If at limit: BLOCK new entries

3. Max notional exposure: $10,000
   - Sum all position values
   - If exceeded: BLOCK

4. Time-of-day restrictions:
   - No trades first 5 minutes after open (9:30-9:35 AM ET)
   - No trades last 15 minutes (3:45-4:00 PM ET)
```

**Where to Implement:**
- File: `services/dispatcher/risk/gates.py`
- Add functions: `check_daily_loss()`, `check_max_positions()`, etc.
- Call in: `evaluate_all_gates()`

### MEDIUM Priority: Better Momentum Confirmation

**Status:** ⚠️ Current uses SMA distance proxy (not ideal)

**Better Implementation:**
```python
# Add to features table:
- close_5m_ago (from telemetry)
- close_15m_ago (from telemetry)

# In rules.py:
ret_5m = (close / close_5m_ago) - 1
ret_15m = (close / close_15m_ago) - 1

move_confirmed = (
  (primary_direction == "BULL" and (ret_5m >= 0.002 or ret_15m >= 0.004)) or
  (primary_direction == "BEAR" and (ret_5m <= -0.002 or ret_15m <= -0.004))
)
```

**Impact:**
- Current: SMA breakout catches moves but may be late
- Better: Momentum shows current move strength (more real-time)

### LOW Priority: Watchlist Liquidity Scoring

**Status:** ⚠️ Watchlist prioritizes sentiment/volume, not liquidity

**Enhancement:**
- Add average share volume to watchlist scoring
- Add options volume/OI as proxy when available
- Add bid/ask spread quality
- Weight liquidity heavily (30-40% of score)

---

## 📊 Expected Behavior Changes

### Before V2.0 (Sentiment as Gate):
- NVDA 8.63x surge, 0.91 sentiment → **REJECTED** (need 0.5+ sentiment + uptrend)
- Conservative but missed opportunities
- ~0 signals generated

### After V2.0 (Sentiment as Scaler):
- NVDA 8.63x surge → **Direction from price/trend** (above SMA20, trend=1)
- Sentiment 0.91 **boosts** confidence +23%
- Move confirmed (>1% breakout)
- Volume 8.63x **boosts** confidence +35%
- **Result: High confidence signal generated**

### Trade-off:
- ✅ Captures real opportunities (volume surges with price confirmation)
- ✅ Sentiment still matters (boosts aligned signals, penalizes opposing)
- ⚠️ Slightly more trades (but volume + breakout filters prevent noise)
- ⚠️ Options gates MUST be implemented (currently missing)

---

## 🔍 Code Review Checklist

### Rules.py
- [x] Sentiment as scaler implemented correctly
- [x] Direction from price + trend (not sentiment)
- [x] Strict trend_state = ±1 for options
- [x] Weak trend (state=0) allows stocks only
- [x] volume_ratio defaults to None
- [x] Breakout confirmation implemented
- [x] Adaptive threshold with slower ramp (5% not 10%)
- [x] News count weighting added
- [x] All helper functions defined
- [x] No TODOs left in critical paths
- [x] Comprehensive logging in reason dict

### Gates.py
- [x] Robust .get() extraction (no KeyError)
- [x] Action/Instrument normalization
- [x] Safe datetime parsing
- [x] Instrument-aware confidence thresholds
- [x] Recommendation freshness gate
- [x] Ticker cooldown gate
- [x] SELL_STOCK position verification
- [x] Validate known action/instrument values
- [x] Updated function signature (added params)

### Configuration
- [x] trading_params.json updated with V2.0 logic
- [x] All thresholds documented
- [x] TODOs clearly marked
- [x] Implementation notes included

---

## ⚠️ Pre-Deployment Checklist

### Before Deploying Signal Engine V2.0:
- [ ] **User reviews changes**
- [ ] **User approves deployment**
- [ ] Build Docker image (signal-engine revision 11)
- [ ] Push to ECR
- [ ] Update task definition
- [ ] Register with ECS
- [ ] Update scheduler
- [ ] Monitor first execution
- [ ] Verify behavior in logs
- [ ] Check signals in database

### Before Enabling Live Options Trading:
- [ ] **Implement options execution gates** (IV, spread, volume, OI)
- [ ] **Implement account-level kill switches** (daily loss, position limits)
- [ ] Test with paper trading for 1 week minimum
- [ ] Verify no losses from spreads/slippage
- [ ] Verify proper option contract selection
- [ ] Monitor fill quality

---

## 📝 Deployment Impact Assessment

**Signal Generation:**
- Expect **more signals** (sentiment no longer hard blocks)
- Expect **higher quality** (strict trend + breakout + volume required)
- NVDA-type setups will now qualify

**Risk:**
- Lower (strict trend requirement prevents chop)
- Controlled (volume gates + breakout confirmation)
- Safe for paper trading to validate

**Options Execution:**
- ⚠️ **Current state: Will execute without spread/liquidity checks**
- ⚠️ **Action needed: Implement execution gates before live**
- ✅ **Safe for now: Paper trading mode**

---

## 🎯 Recommended Next Steps

### Immediate (This Session):
1. **USER REVIEWS** this summary
2. **USER APPROVES** deployment
3. Deploy signal engine revision 11
4. Monitor for 30 minutes
5. Verify increased signal generation
6. Check signal quality in logs

### Next Session (Before Live Trading):
1. **CRITICAL:** Implement options execution gates in dispatcher
2. **CRITICAL:** Add account-level kill switches
3. Consider adding momentum features (close_5m_ago, close_15m_ago)
4. Test for 1 week with paper trading
5. Analyze results and tune if needed

---

## 📞 Questions for User

Before I deploy, please confirm:

1. ✅ **Logic approved?** Sentiment as scaler, direction from price/trend?
2. ✅ **Thresholds okay?** Confidence 0.60/0.45/0.35, volume 1.2x min, breakout 1%?
3. ✅ **Aware of TODOs?** Options gates + account controls needed before live?
4. ✅ **Ready to deploy?** This will be revision 11, replacing revision 10?
5. ✅ **Monitor plan?** Watch logs for 30 min after deployment?

---

**Awaiting your approval to proceed with deployment.** 🚦
