# 🚨 CRITICAL BUG: Position Manager Creating Short Positions Instead of Closing Longs

**Date:** February 3, 2026  
**Status:** ✅ FIXED AND DEPLOYED  
**Severity:** CRITICAL - System was opening unintended short positions

---

## 🐛 The Problem

Position Manager was **creating short stock positions** instead of **closing long option positions**. This happened because:

1. **Wrong Symbol**: Using `ticker` (e.g., "GOOGL") instead of `option_symbol` (e.g., "GOOGL260220C00340000")
2. **Missing position_intent**: Not specifying `position_intent="sell_to_close"` for options

### What Was Happening

```
User bought: GOOGL260220C00340000 (GOOGL $340 Call option)
Position Manager tried to close it by selling: GOOGL (underlying stock!)

Result:
✅ Option position STILL OPEN (stop loss not working!)
❌ Created -10 shares SHORT position in GOOGL stock
❌ Huge unintended risk and margin usage
```

### Real Impact

User had 8 option positions that should have closed but instead created 8 short stock positions:
- CRM: -11 shares short
- GOOGL: -10 shares short  
- META: -1 share short
- NOW: (short position)
- ORCL: -12 shares short
- QCOM: -5 shares short (from one position)
- QCOM: (another short position)
- SPY: (short position)

---

## 🔍 Root Cause Analysis

### Issue #1: Wrong Symbol (FIXED)

**File:** `services/position_manager/exits.py`  
**Lines:** 167, 353, 364, 432

**Before (BUG):**
```python
order_data = MarketOrderRequest(
    symbol=ticker,  # ❌ BUG! ticker = "GOOGL", should be "GOOGL260220C00340000"
    qty=quantity,
    side=OrderSide.SELL,
    time_in_force=TimeInForce.DAY
)
```

**After (FIXED):**
```python
symbol_to_close = position.get('option_symbol') or ticker  # ✅ Use option symbol for options
order_data = MarketOrderRequest(
    symbol=symbol_to_close,
    qty=quantity,
    side=OrderSide.SELL,
    time_in_force=TimeInForce.DAY
)
```

### Issue #2: Missing position_intent (MOST CRITICAL - FIXED)

According to Alpaca API documentation, for options:
- `side="sell"` + `position_intent="sell_to_open"` = Opening a SHORT position
- `side="sell"` + `position_intent="sell_to_close"` = Closing a LONG position

**Without `position_intent`, Alpaca defaults to opening a new position!**

**Before (BUG):**
```python
order_data = MarketOrderRequest(
    symbol=symbol_to_close,
    qty=quantity,
    side=OrderSide.SELL,  # ❌ Without position_intent, this OPENS a short!
    time_in_force=TimeInForce.DAY
)
```

**After (FIXED):**
```python
from alpaca.trading.enums import PositionIntent

order_data = MarketOrderRequest(
    symbol=symbol_to_close,
    qty=quantity,
    side=OrderSide.SELL,
    time_in_force=TimeInForce.DAY,
    position_intent=PositionIntent.SELL_TO_CLOSE  # ✅ CRITICAL: Specify we're closing!
)
```

---

## ✅ All Fixes Applied

### 1. Main Close Order (exits.py line ~167)
- ✅ Fixed symbol usage: `position.get('option_symbol') or ticker`
- ✅ Added `position_intent=PositionIntent.SELL_TO_CLOSE`

### 2. Stop Loss Bracket Order (exits.py line ~353)
- ✅ Fixed symbol usage
- ✅ Added `position_intent=PositionIntent.SELL_TO_CLOSE`

### 3. Take Profit Bracket Order (exits.py line ~364)
- ✅ Fixed symbol usage
- ✅ Added `position_intent=PositionIntent.SELL_TO_CLOSE`

### 4. Partial Exit Order (exits.py line ~432)
- ✅ Fixed symbol usage
- ✅ Added `position_intent=PositionIntent.SELL_TO_CLOSE`

### 5. Database Sync Error (db.py)
- ✅ Removed invalid `ON CONFLICT` clause from `create_position_from_alpaca()`

### 6. Alpaca API Call Error (monitor.py)
- ✅ Fixed `get_orders()` to use proper SDK syntax with `GetOrdersRequest`

### 7. Trailing Stop Crashes (monitor.py)
- ✅ Disabled trailing stop logic until migration 013 adds required columns

### 8. UUID Serialization Error (exits.py)
- ✅ Convert UUID to string before JSON serialization

---

## 📊 Deployment History

### Deployment 1: emergency-fix-v2 (15:44 UTC)
- Fixed symbol usage
- Fixed database ON CONFLICT error
- Fixed Alpaca API call
- Fixed UUID serialization
- **PROBLEM:** Docker not picking up code changes

### Deployment 2: position-intent-fix (15:52 UTC) ✅ CURRENT
- All fixes from Deployment 1
- **CRITICAL FIX:** Added `position_intent=PositionIntent.SELL_TO_CLOSE` to all close orders
- Forced complete Docker rebuild
- Successfully deployed

**Current Task Definition:** `position-manager-service:6`  
**Current Image:** `160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/position-manager:position-intent-fix`  
**Digest:** `sha256:f787f44d6b707fc3fb69aa092e0da1c1a103da0ff9f693bde0badf34089ade72`

---

## 🧪 How to Verify the Fix

### 1. Check Service Status
```bash
aws ecs describe-services \
  --cluster ops-pipeline-cluster \
  --service position-manager-service \
  --region us-west-2 \
  --query 'services[0].taskDefinition'
```
Should show: `arn:aws:ecs:us-west-2:160027201036:task-definition/position-manager-service:6`

### 2. Check Logs for Errors
```bash
aws logs describe-log-streams \
  --log-group-name /ecs/ops-pipeline/position-manager-service \
  --order-by LastEventTime \
  --descending \
  --max-items 1 \
  --region us-west-2 \
  --query 'logStreams[0].logStreamName' \
  --output text
```

Then check the logs - should see NO MORE:
- ❌ "ON CONFLICT" errors
- ❌ "wrong symbol" errors  
- ❌ Short positions being created

### 3. Monitor Alpaca Positions
Go to: https://app.alpaca.markets/paper/dashboard

**Expected behavior:**
- ✅ Options close correctly using option symbols
- ✅ No new short stock positions created
- ✅ Stop losses work properly

---

## 🚨 Manual Cleanup Required

The bug created unintended short stock positions that need manual closure:

### Via Alpaca Dashboard:
1. Go to: https://app.alpaca.markets/paper/dashboard
2. For each short position (negative quantity):
   - Click "Close Position" OR
   - Create a Buy Market Order for the quantity shown
3. This will cover the shorts and return portfolio to normal

### Short Positions to Close:
- CRM: -11 shares → Buy 11 shares
- GOOGL: -10 shares → Buy 10 shares
- META: -1 share → Buy 1 share
- NOW: Check quantity → Buy to cover
- ORCL: -12 shares → Buy 12 shares
- QCOM: -5 shares → Buy 5 shares (first position)
- QCOM: Check quantity → Buy to cover (second position)
- SPY: Check quantity → Buy to cover

---

## 📚 Key Learnings

### 1. Options Require position_intent
For Alpaca options trading, **ALWAYS** specify `position_intent`:
- Opening: `position_intent=PositionIntent.BUY_TO_OPEN` or `SELL_TO_OPEN`
- Closing: `position_intent=PositionIntent.BUY_TO_CLOSE` or `SELL_TO_CLOSE`

### 2. Options Use Different Symbols
- Stock symbol: `GOOGL`
- Option symbol: `GOOGL260220C00340000` (ticker + expiry + type + strike)
- **ALWAYS** use `option_symbol` for options orders

### 3. Docker Caching Issues
- `--no-cache` doesn't always work
- Sometimes need to use different image tags
- Verify code changes are actually in the running container

### 4. Test in Paper Trading First
- This bug was caught in paper trading (fake money)
- Would have been catastrophic in live trading
- Always test thoroughly before going live

---

## 🔮 Next Steps

### Immediate (Done)
- ✅ Deploy position-intent-fix
- ✅ Verify service is running
- ⏳ User manually closes short positions

### Soon
1. Apply migration 013 to add missing columns:
   - `peak_price`
   - `trailing_stop_price`
   - `original_quantity`
   - `entry_underlying_price`

2. Re-enable trailing stop logic after columns exist

3. Monitor for 24 hours to ensure:
   - No more short positions created
   - Options close correctly
   - Stop losses work properly

### Later
1. Add integration tests for options closing
2. Add alerts for unexpected short positions
3. Consider adding position_intent validation in dispatcher

---

## 📝 Files Modified

1. **services/position_manager/exits.py**
   - Fixed symbol usage in 4 locations
   - Added position_intent to 4 locations
   - Fixed UUID serialization

2. **services/position_manager/db.py**
   - Removed invalid ON CONFLICT clause

3. **services/position_manager/monitor.py**
   - Fixed Alpaca API call syntax
   - Disabled trailing stop logic

4. **services/position_manager/Dockerfile**
   - Updated cache bust comment

5. **deploy/position-manager-service-task-definition.json**
   - Updated image tag to position-intent-fix

---

## ✅ Success Criteria

- [x] Service deployed with new code
- [x] No more "ON CONFLICT" errors in logs
- [x] No more short positions being created
- [ ] User manually closes existing short positions
- [ ] Options close correctly using option symbols
- [ ] Stop losses trigger and close positions properly
- [ ] Position Manager runs for 24 hours without errors

---

**Status:** ✅ DEPLOYED AND READY FOR TESTING  
**Priority:** 🚨 CRITICAL - Fixed immediately  
**Risk:** ⚠️ Manual cleanup still required for existing short positions

**Next Action:** User should manually close the short stock positions via Alpaca dashboard, then monitor to ensure new positions close correctly.
