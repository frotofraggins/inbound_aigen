# Critical TODOs Before Live Options Trading

**Created:** 2026-01-27 4:02 PM UTC  
**Purpose:** Track required implementations - DO NOT FORGET THESE  
**Status:** 🔴 BLOCKERS FOR LIVE TRADING

---

## 🚨 CRITICAL BLOCKERS (Must Implement)

### 1. Options Execution Gates ⚠️ CRITICAL
**Status:** ❌ NOT IMPLEMENTED  
**Risk:** Will buy illiquid/expensive options → Immediate losses  
**Priority:** P0 - Required before ANY live options trades

**Implementation Location:**
- File: `services/dispatcher/alpaca/options.py`
- Function to add: `validate_option_contract(contract, config)`

**Required Gates:**
```python
def validate_option_contract(contract, config):
    """
    Validate option contract before execution.
    Returns (passed, reason, fallback_to_stock)
    """
    # Gate 1: Bid/Ask Spread
    spread_pct = (contract.ask - contract.bid) / ((contract.ask + contract.bid) / 2)
    if spread_pct > config['max_option_spread']:  # 0.10 = 10%
        return (False, f"Spread too wide: {spread_pct:.1%}", True)
    
    # Gate 2: Option Volume
    if contract.volume < config['min_option_volume']:  # 100
        return (False, f"Volume too low: {contract.volume}", True)
    
    # Gate 3: Open Interest
    if contract.open_interest < config['min_open_interest']:  # 100
        return (False, f"OI too low: {contract.open_interest}", True)
    
    # Gate 4: IV Percentile (when available)
    if hasattr(contract, 'iv_percentile') and contract.iv_percentile:
        if contract.iv_percentile > config['max_iv_percentile']:  # 80
            return (False, f"IV too high: {contract.iv_percentile}th percentile", True)
    
    return (True, "All gates passed", False)

# In dispatcher main.py, before executing option:
passed, reason, fallback = validate_option_contract(selected_contract, config)
if not passed:
    if fallback:
        # Try stock instead
        execute_stock_trade(...)
    else:
        # Skip trade
        mark_as_skipped(reason)
```

**Test Plan:**
1. Add validation function
2. Test with known illiquid options (should block)
3. Test with liquid options (should pass)
4. Verify fallback to stock works
5. Deploy dispatcher with gates enabled

**ETA:** 1-2 hours implementation + testing

---

### 2. Account-Level Kill Switches ⚠️ HIGH PRIORITY
**Status:** ❌ NOT IMPLEMENTED  
**Risk:** No emergency stop → Can't halt losses  
**Priority:** P0 - Required before increasing position sizes

**Implementation Location:**
- File: `services/dispatcher/risk/gates.py`
- Add functions and integrate into `evaluate_all_gates()`

**Required Controls:**
```python
def check_daily_loss_limit(account_state, config):
    """Max daily loss kill switch."""
    daily_pnl = account_state.get('daily_pnl', 0)
    max_loss = config.get('max_daily_loss', 500)  # $500 for paper
    
    if daily_pnl < -max_loss:
        return (False, f"Daily loss ${abs(daily_pnl):.0f} exceeds limit ${max_loss}", daily_pnl, max_loss)
    return (True, f"Daily P&L ${daily_pnl:.0f} within limit", daily_pnl, max_loss)

def check_max_positions(active_positions_count, config):
    """Max concurrent positions limit."""
    max_positions = config.get('max_open_positions', 5)
    
    if active_positions_count >= max_positions:
        return (False, f"At position limit: {active_positions_count}/{max_positions}", active_positions_count, max_positions)
    return (True, f"Positions {active_positions_count}/{max_positions}", active_positions_count, max_positions)

def check_max_exposure(total_notional, config):
    """Max notional exposure limit."""
    max_notional = config.get('max_notional_exposure', 10000)
    
    if total_notional >= max_notional:
        return (False, f"At exposure limit: ${total_notional:.0f}/${max_notional}", total_notional, max_notional)
    return (True, f"Exposure ${total_notional:.0f}/${max_notional}", total_notional, max_notional)

def check_trading_hours(config):
    """Time-of-day restrictions."""
    # Market hours: 9:30 AM - 4:00 PM ET
    # Block: First 5 minutes (9:30-9:35)
    # Block: Last 15 minutes (3:45-4:00)
    
    # TODO: Implement with proper timezone handling
    return (True, "Trading hours check not yet implemented", None, None)
```

**Integration:**
```python
# In evaluate_all_gates(), add:
gates['daily_loss'] = check_daily_loss_limit(account_state, config)
gates['max_positions'] = check_max_positions(len(active_positions), config)
gates['max_exposure'] = check_max_exposure(total_notional, config)
gates['trading_hours'] = check_trading_hours(config)
```

**Data Requirements:**
- Query `active_positions` table for count
- Query `dispatch_executions` for today's P&L
- Calculate total notional from active positions

**ETA:** 2-3 hours implementation + testing

---

### 3. Dispatcher Call Signature Update ⚠️ MEDIUM
**Status:** ❌ gates.py updated, dispatcher main.py NOT updated yet  
**Risk:** Runtime error when dispatcher calls gates  
**Priority:** P1 - Must fix before deploying gates.py

**Problem:**
`gates.py` now expects additional parameters:
```python
evaluate_all_gates(
    recommendation, bar, features, 
    ticker_count_today,
    last_trade_time,        # NEW
    has_open_position,      # NEW
    config
)
```

**Required Fix:**
In `services/dispatcher/main.py`, update the call:
```python
# Query for ticker's last trade time
last_trade = get_last_trade_for_ticker(conn, ticker)
last_trade_time = last_trade['executed_at'] if last_trade else None

# Check if ticker has open position
has_open_position = check_open_position(conn, ticker)

# Call gates with all parameters
gates_passed, gate_results = evaluate_all_gates(
    rec, bar, features, 
    ticker_count_today,
    last_trade_time,        # Pass this
    has_open_position,      # Pass this
    config
)
```

**ETA:** 30 minutes

---

## 🟡 HIGH PRIORITY (Improve Quality)

### 4. Real Momentum Confirmation
**Status:** ❌ Currently uses SMA distance proxy  
**Impact:** May catch moves late, less accurate  
**Priority:** P1 - High quality improvement

**Current:**
```python
# check_breakout() uses distance_sma20 > 0.01
# This is "how far from SMA" not "how fast moving"
```

**Better:**
```python
# Add to features table via migration:
ALTER TABLE lane_features 
ADD COLUMN close_5m_ago NUMERIC,
ADD COLUMN close_15m_ago NUMERIC;

# In feature_computer, compute:
close_5m_ago = get_close_n_minutes_ago(telemetry, 5)
close_15m_ago = get_close_n_minutes_ago(telemetry, 15)

# In rules.py check_momentum():
ret_5m = (close / close_5m_ago) - 1
ret_15m = (close / close_15m_ago) - 1

if primary_direction == "BULL":
    move_confirmed = ret_5m >= 0.002 or ret_15m >= 0.004
elif primary_direction == "BEAR":
    move_confirmed = ret_5m <= -0.002 or ret_15m <= -0.004
```

**ETA:** 1-2 hours (migration + feature_computer update + rules.py)

---

### 5. Watchlist Liquidity Scoring
**Status:** ❌ Currently prioritizes sentiment/volume over liquidity  
**Impact:** May select illiquid tickers  
**Priority:** P2 - Quality improvement

**Enhancement:**
```python
# In watchlist_engine scoring.py:
liquidity_score = (
    0.5 * normalized(avg_daily_volume) +
    0.3 * normalized(spread_quality) +
    0.2 * normalized(option_oi_proxy)
)

final_score = (
    0.40 * sentiment_momentum +
    0.30 * liquidity_score +      # NEW
    0.20 * technical_setup +
    0.10 * volatility_score
)
```

**ETA:** 2 hours

---

## 🟢 MEDIUM PRIORITY (Nice to Have)

### 6. Load Parameters from SSM
**Status:** ❌ Currently hardcoded in rules.py  
**Impact:** Requires redeployment to tune  
**Priority:** P2 - Operational convenience

**Implementation:**
```python
# In signal_engine config.py:
def load_trading_params():
    ssm = boto3.client('ssm', region_name='us-west-2')
    try:
        param = ssm.get_parameter(Name='/ops-pipeline/trading-params')
        return json.loads(param['Parameter']['Value'])
    except:
        # Fall back to hardcoded defaults
        return DEFAULT_PARAMS

# In rules.py:
# Import from config instead of constants
params = config['trading_params']
CONFIDENCE_DAY_TRADE = params['confidence_thresholds']['day_trade_base']
```

**Benefit:** Change parameters without redeployment

**ETA:** 1 hour

---

## 📋 TODO Tracking

### Implementation Phases

**Phase 1: Fix Dispatcher Integration (Required for V2.0 deployment)**
- [ ] Update dispatcher main.py call signature for gates
- [ ] Test dispatcher with new gates
- [ ] Deploy dispatcher first (before signal engine)
- **ETA:** 30 minutes
- **Blocker:** YES - Must fix before deploying signal engine V2.0

**Phase 2: Options Execution Gates (Required before live options)**
- [ ] Implement `validate_option_contract()` in options.py
- [ ] Add config parameters for spread/volume/OI limits
- [ ] Test with paper trading
- [ ] Verify fallback to stock works
- **ETA:** 1-2 hours
- **Blocker:** YES - for live options trading

**Phase 3: Account Kill Switches (Required before live trading)**
- [ ] Implement daily loss check
- [ ] Implement max positions check
- [ ] Implement max exposure check
- [ ] Implement trading hours check
- [ ] Test emergency stops work
- **ETA:** 2-3 hours
- **Blocker:** YES - for any live trading

**Phase 4: Momentum Features (Quality improvement)**
- [ ] Create migration to add close_5m_ago, close_15m_ago
- [ ] Update feature_computer to compute momentum
- [ ] Update rules.py to use real momentum
- [ ] Test and validate
- **ETA:** 2 hours
- **Blocker:** NO - but improves quality

**Phase 5: SSM Parameter Loading (Operational convenience)**
- [ ] Store trading_params.json in SSM
- [ ] Update signal_engine to load from SSM
- [ ] Test parameter changes take effect
- **ETA:** 1 hour
- **Blocker:** NO - nice to have

---

## ⚠️ DEPLOYMENT DECISION TREE

### Can I Deploy Signal Engine V2.0 NOW?

**Prerequisites:**
1. ✅ Code changes completed (rules.py, gates.py, trading_params.json)
2. ❌ **Dispatcher main.py updated to call gates with new signature**
3. ❓ User approval

**Decision:**
→ **NO** - Must fix dispatcher main.py first (30 min)  
→ Then get user approval  
→ Then deploy dispatcher (revision N)  
→ Then deploy signal engine (revision 11)

### Can I Enable Live Options Trading?

**Prerequisites:**
1. ❌ Options execution gates implemented
2. ❌ Account kill switches implemented
3. ❌ 1 week paper trading validation
4. ❌ User approval

**Decision:**
→ **NO** - Continue paper trading mode  
→ Implement gates over next 1-2 sessions  
→ Test for 1 week  
→ Then consider live

---

## 📞 Action Items for This Session

### Immediate (Next 30-60 minutes):
1. **Fix dispatcher main.py** to call updated gates.py
2. **Get user approval** for V2.0 logic changes
3. **Deploy dispatcher** with enhanced gates
4. **Deploy signal engine** with production logic V2.0
5. **Monitor for 30 minutes** and verify behavior

### Next Session (1-3 hours):
1. **Implement options execution gates**
2. **Implement account kill switches**
3. Continue paper trading with new logic
4. Collect data for tuning

### Week 1 (Validation Period):
1. Monitor signal quality
2. Track paper P&L
3. Analyze spread costs
4. Tune parameters if needed
5. Document learnings

### After Week 1 (If All Tests Pass):
1. Review results with user
2. Decide on live trading
3. Set initial position sizes
4. Enable real trading if approved

---

## 🎯 Success Criteria

**V2.0 Logic is Working If:**
- ✅ More signals generated (NVDA-type setups qualify)
- ✅ No noise trades (strict trend + volume + breakout filters)
- ✅ Sentiment boosts aligned signals, penalizes opposing
- ✅ No crashes or errors
- ✅ Signals have detailed breakdowns in reason

**Ready for Live Options If:**
- ✅ Options gates implemented and tested
- ✅ Account kill switches implemented and tested
- ✅ 1 week paper trading shows positive results
- ✅ No execution issues (spreads, fills, etc.)
- ✅ User comfortable with risk

---

## 📌 How to Use This Document

**Before Each Session:**
1. Read this document
2. Check what's still ❌ NOT IMPLEMENTED
3. Prioritize based on blockers

**After Completing an Item:**
1. Update status ❌ → ✅
2. Document where it was implemented
3. Update ETA for remaining items

**Before Live Trading:**
1. Verify ALL CRITICAL items are ✅
2. Verify paper trading results are positive
3. Get user sign-off

---

**This document exists so we DON'T FORGET critical safety implementations!**
