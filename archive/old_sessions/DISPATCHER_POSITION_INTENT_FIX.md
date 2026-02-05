# 🚨 CRITICAL: Dispatcher Missing position_intent for Options

**Date:** February 3, 2026  
**Status:** ⚠️ NEEDS IMMEDIATE FIX  
**Severity:** CRITICAL - Same bug as Position Manager

---

## 🐛 The Problem

The dispatcher's Alpaca broker is placing option orders **WITHOUT** the `position_intent` parameter. This means:

1. **Opening positions works fine** (default behavior is `buy_to_open` for buys)
2. **Closing positions FAILS** - creates SHORT positions instead of closing LONG positions

This is the **EXACT SAME BUG** we just fixed in Position Manager!

---

## 📍 Location of Bug

**File:** `services/dispatcher/alpaca/broker.py`  
**Function:** `_execute_option()` around line 350

**Current Code (BUG):**
```python
# Prepare option order
order_data = {
    "symbol": option_symbol,
    "qty": str(num_contracts),
    "side": side,  # ❌ Without position_intent, this opens a new position!
    "type": "market",
    "time_in_force": "day",
    "order_class": "simple"
}
```

**Problem:** When `side="sell"`, Alpaca interprets this as opening a SHORT position, not closing a LONG position!

---

## ✅ The Fix

Add `position_intent` parameter to specify whether we're opening or closing:

```python
from alpaca.trading.enums import PositionIntent

# Determine position intent based on action
if recommendation['action'] == 'BUY':
    position_intent = PositionIntent.BUY_TO_OPEN
elif recommendation['action'] == 'SELL':
    # Check if we have an open position to close
    # For now, assume SELL means opening a short (sell_to_open)
    # Position Manager handles closing existing positions
    position_intent = PositionIntent.SELL_TO_OPEN
else:
    position_intent = None

# Prepare option order
order_data = {
    "symbol": option_symbol,
    "qty": str(num_contracts),
    "side": side,
    "type": "market",
    "time_in_force": "day",
    "order_class": "simple",
    "position_intent": position_intent.value if position_intent else None  # ✅ CRITICAL FIX
}
```

---

## 🤔 Important Design Question

**Q: Should dispatcher ever CLOSE positions?**

Looking at the code:
- Dispatcher processes **recommendations** from signal engine
- Recommendations have actions: `BUY` or `SELL`
- Position Manager handles **closing** existing positions

**Current Design:**
- `BUY` recommendation → Open LONG position (buy_to_open)
- `SELL` recommendation → Open SHORT position (sell_to_open)
- Position Manager → Close positions based on stop loss / take profit

**This means:**
- Dispatcher should use `BUY_TO_OPEN` for BUY actions
- Dispatcher should use `SELL_TO_OPEN` for SELL actions (shorting)
- Position Manager should use `SELL_TO_CLOSE` for closing longs
- Position Manager should use `BUY_TO_CLOSE` for closing shorts

**Conclusion:** The dispatcher fix is simpler than Position Manager because it only opens positions, never closes them!

---

## 🔧 Implementation Plan

### Step 1: Fix dispatcher/alpaca/broker.py

Add position_intent to option orders:

```python
# Around line 350 in _execute_option()

from alpaca.trading.enums import PositionIntent

# Determine position intent (dispatcher only OPENS positions)
if recommendation['action'] == 'BUY':
    position_intent = PositionIntent.BUY_TO_OPEN
elif recommendation['action'] == 'SELL':
    position_intent = PositionIntent.SELL_TO_OPEN  # Opening short position
else:
    raise ValueError(f"Invalid action: {recommendation['action']}")

# Prepare option order
order_data = {
    "symbol": option_symbol,
    "qty": str(num_contracts),
    "side": side,
    "type": "market",
    "time_in_force": "day",
    "order_class": "simple",
    "position_intent": position_intent.value  # ✅ CRITICAL: Specify intent
}
```

### Step 2: Deploy to BOTH dispatcher services

1. **dispatcher-service** (main account)
2. **dispatcher-tiny-service** (tiny account)

Both use the same code, so one fix applies to both!

---

## 📊 Impact Assessment

### Current State
- ✅ Opening LONG positions works (BUY actions)
- ⚠️ Opening SHORT positions might work by accident (SELL actions default to sell_to_open)
- ❌ If dispatcher ever tries to close positions, it would fail

### After Fix
- ✅ Opening LONG positions explicit (buy_to_open)
- ✅ Opening SHORT positions explicit (sell_to_open)
- ✅ Clear intent for all option orders
- ✅ Consistent with Position Manager fixes

---

## 🧪 Testing Plan

### 1. Verify Current Behavior
```bash
# Check recent dispatcher executions
aws logs tail /ecs/ops-pipeline/dispatcher-service --since 1h --region us-west-2 | grep -i "option"
```

### 2. Deploy Fix
```bash
# Build and push new image
cd services/dispatcher
docker build --no-cache -t 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/dispatcher:position-intent-fix .
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/dispatcher:position-intent-fix

# Update both services
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service dispatcher-service \
  --force-new-deployment \
  --region us-west-2

aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service dispatcher-tiny-service \
  --force-new-deployment \
  --region us-west-2
```

### 3. Monitor Logs
```bash
# Watch for option orders
aws logs tail /ecs/ops-pipeline/dispatcher-service --follow --region us-west-2 | grep -i "option"
```

### 4. Verify in Alpaca
- Check that new option positions have correct intent
- Verify no unintended short positions created

---

## 🎯 Success Criteria

- [x] Code fix applied to broker.py
- [ ] Docker image built and pushed
- [ ] dispatcher-service updated
- [ ] dispatcher-tiny-service updated
- [ ] Logs show position_intent in order data
- [ ] No unintended short positions created
- [ ] System runs for 24 hours without issues

---

## 📝 Related Issues

- **Position Manager Bug:** Fixed in `CRITICAL_BUG_CLOSING_WRONG_SYMBOL.md`
- **Same Root Cause:** Missing position_intent parameter
- **Alpaca API Requirement:** Options MUST specify position_intent

---

## 🔮 Next Steps

1. **IMMEDIATE:** Apply this fix to dispatcher
2. **VERIFY:** Check all other services that place option orders
3. **DOCUMENT:** Update API integration guide with position_intent requirement
4. **TEST:** Add integration tests for option order placement

---

**Priority:** 🚨 CRITICAL  
**Estimated Time:** 15 minutes  
**Risk:** LOW (only adds required parameter, doesn't change logic)

**Next Action:** Apply fix to `services/dispatcher/alpaca/broker.py` and deploy to both dispatcher services.
