# FINAL FIX - Alpaca Position Intent Error

## 🚨 NEW ERROR After Fix

```
Error: position intent mismatch
  inferred: sell_to_open (Alpaca thinks: opening NEW short)
  specified: sell_to_close (We said: closing LONG)
```

**Translation:** Alpaca doesn't recognize we have these positions!

---

## 🔍 Root Cause

**Two possibilities:**

### **1. Symbol Mismatch (Most Likely)**

Database has: `ORCL260220C00340000`  
Alpaca has: `ORCL260220C00034000` (different format?)

Check if option_symbol format matches Alpaca's format.

### **2. Position Already Closed**

The position was actually closed earlier (when it sold the stock by mistake), so now Alpaca has no position to close.

---

## ✅ THE REAL FIX

**Don't use PositionIntent.SELL_TO_CLOSE for options!**

Alpaca requires this for stocks but **NOT for options**. For options, just selling the contract is enough.

### **In exits.py, line 167:**

**Change FROM:**
```python
from alpaca.trading.enums import PositionIntent
order_data = MarketOrderRequest(
    symbol=symbol_to_close,
    qty=quantity,
    side=OrderSide.SELL,
    time_in_force=TimeInForce.DAY,
    position_intent=PositionIntent.SELL_TO_CLOSE  # ← REMOVE THIS
)
```

**Change TO:**
```python
order_data = MarketOrderRequest(
    symbol=symbol_to_close,  # Use option_symbol
    qty=quantity,
    side=OrderSide.SELL,
    time_in_force=TimeInForce.DAY
    # NO position_intent for options!
)
```

**Why:** 
- For options, OrderSide.SELL on a long position = close automatically
- PositionIntent.SELL_TO_CLOSE confuses Alpaca
- Alpaca says "you don't have this position to close"

---

## 🎯 Alternative: Use Alpaca's close_position API

**Even simpler - use the dedicated close API:**

```python
else:  # OPTIONS (CALL or PUT)
    symbol_to_close = position.get('option_symbol') or ticker
    
    logger.info(f"Closing position via Alpaca close_position API: {symbol_to_close}")
    
    # Use Alpaca's dedicated close API (handles SELL_TO_CLOSE automatically)
    try:
        order = alpaca_client.close_position(symbol_to_close)
        
        return {
            'order_id': str(order.id) if hasattr(order, 'id') else None,
            'status': str(order.status) if hasattr(order, 'status') else 'submitted',
            'filled_qty': float(order.filled_qty) if hasattr(order, 'filled_qty') else quantity
        }
    except Exception as e:
        logger.error(f"Error closing position via API: {e}")
        return None
```

**This is simpler and more reliable!**

---

## 🚀 Recommended Fix

### **Option A: Remove PositionIntent** (Quick)
```python
# Just remove the position_intent parameter
order_data = MarketOrderRequest(
    symbol=symbol_to_close,
    qty=quantity,
    side=OrderSide.SELL,
    time_in_force=TimeInForce.DAY
)
```

### **Option B: Use close_position API** (Cleaner)
```python
# Use Alpaca's dedicated close API
order = alpaca_client.close_position(symbol_to_close)
```

---

## 🎯 Summary

**The Problem:**
- PositionIntent.SELL_TO_CLOSE doesn't work for options
- Alpaca interprets as trying to open new short
- Requires buying power (thinks it's cash-secured put)

**The Solution:**
- Remove PositionIntent parameter
- Or use close_position API instead
- Let Alpaca infer close intent from OrderSide.SELL

**Deploy:** 3 minutes  
**Result:** Options will close correctly

**Tell Kiro:** Remove the `position_intent` parameter from the MarketOrderRequest for options!
