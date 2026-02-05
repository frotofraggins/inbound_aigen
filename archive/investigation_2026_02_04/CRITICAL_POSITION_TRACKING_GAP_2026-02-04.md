# CRITICAL: Position Tracking Gap - February 4, 2026, 9:15 AM AZ

## 🚨 The Real Problem

Positions are closing **BEFORE** the position manager ever sees them!

### What Happened to BMY and WMT

```
9:06:39 AM - BMY CALL opened (Alpaca filled)
9:06:40 AM - WMT CALL opened (Alpaca filled)
... position manager runs every 5 minutes, next check at ~9:11 AM ...
9:10:59 AM - BMY CALL closed (4 min 20 sec hold)
9:11:00 AM - WMT CALL closed (4 min 21 sec hold)
9:11:XX AM - Position manager checks (positions already gone!)
```

**Result:** Position manager NEVER saw these positions, so:
- ❌ Never recorded in `active_positions` table
- ❌ Never recorded in `position_history` table  
- ❌ Exit logic never ran (old OR new)
- ❌ Positions closed by Alpaca's bracket orders (not our system)

### Why This Happens

1. **Dispatcher opens position** → Alpaca fills order
2. **Dispatcher sets bracket orders** (stop/profit) on Alpaca
3. **Alpaca's bracket orders trigger** within 4 minutes
4. **Alpaca closes position** automatically
5. **Position manager checks** (5 min later) → position already gone

**Our position manager exit logic NEVER RUNS because Alpaca closes first!**

---

## 🔍 Root Cause Analysis

### Problem 1: Position Manager Check Interval Too Slow
- **Current:** Checks every **5 minutes** (300 seconds)
- **Positions closing in:** 4-5 minutes
- **Result:** Misses positions that close quickly

### Problem 2: Dispatcher Setting Alpaca Bracket Orders
When dispatcher opens a position, it likely sets bracket orders directly on Alpaca with tight stops. These execute BEFORE our position manager can take control.

### Problem 3: No Initial Position Tracking
- Dispatcher executes trade → inserts into `dispatch_executions`
- Position manager should immediately create `active_positions` entry
- But with 5-minute delay, positions close first

---

## 🎯 Solutions Needed

### Solution 1: Reduce Position Manager Check Interval ⚡ URGENT
**File:** `services/position_manager/main.py` (line 154)

**Change:**
```python
# Current
time.sleep(300)  # 5 minutes

# Should be
time.sleep(60)   # 1 minute (matches other services)
```

**Impact:** Position manager will check every 60 seconds, catching positions within 1 minute of opening.

### Solution 2: Disable Alpaca Bracket Orders (Let Our System Handle Exits)
**File:** `services/dispatcher/alpaca_broker/broker.py`

The dispatcher is setting bracket orders on Alpaca, which execute BEFORE our system can monitor. We need to:
1. NOT set bracket orders on Alpaca
2. Let position manager handle all exits with our logic

**Look for:**
```python
order_data["order_class"] = "bracket"
order_data["stop_loss"] = {"stop_price": str(stop_loss)}
order_data["take_profit"] = {"limit_price": str(take_profit)}
```

**Change to:**
```python
# Don't set bracket orders - our position manager handles exits
order_data["order_class"] = "simple"
# Store stop/profit in database only, not on Alpaca
```

### Solution 3: Immediate Position Tracking
After dispatcher executes a trade, immediately insert into `active_positions` table (don't wait for position manager to sync).

---

## 📊 Current vs Needed Behavior

### Current (Broken)
```
9:06 - Dispatcher opens position
9:06 - Dispatcher sets Alpaca bracket orders (tight stops)
9:07-9:10 - Nothing monitoring (position manager asleep)
9:10 - Alpaca bracket hits, closes position
9:11 - Position manager wakes up, position already gone
```

### Needed (Fixed)
```
9:06 - Dispatcher opens position
9:06 - Dispatcher creates active_position record immediately
9:06 - Dispatcher does NOT set Alpaca brackets
9:07 - Position manager checks, sees new position
9:08 - Position manager checks, sees position (1 min old)
...  - Position manager continues monitoring every 60s
9:36+ - Position manager closes based on OUR exit logic (30+ min)
```

---

## 🚀 Immediate Actions Required

### 1. Reduce Check Interval (5 min → 1 min)
```bash
# Edit services/position_manager/main.py line 154
# Change: time.sleep(300) to time.sleep(60)
# Redeploy position-manager-service
```

### 2. Investigate Alpaca Bracket Orders
Check if dispatcher is setting bracket orders that bypass our exit logic:
```bash
grep -r "bracket" services/dispatcher/alpaca_broker/
```

### 3. Add Immediate Position Tracking
When dispatcher executes, immediately create active_position (don't wait for sync).

---

## 📈 Expected Results After Fix

**Before:**
- ❌ Positions close in 4-5 minutes (Alpaca brackets)
- ❌ Position manager never sees them
- ❌ Exit fix can't work (positions gone before it runs)
- ❌ No tracking data collected

**After:**
- ✅ Position manager checks every 60 seconds
- ✅ Sees positions within 1 minute of opening
- ✅ Our exit logic controls closing (not Alpaca)
- ✅ Positions hold 30+ minutes
- ✅ Full tracking data collected

---

## 💡 Why Exit Fix Didn't Work

The exit fix we deployed is **CORRECT CODE** but **CAN'T RUN** because:
1. Position manager only checks every 5 minutes
2. Positions close in 4 minutes (via Alpaca brackets)
3. Position manager never sees them
4. Our exit logic never executes

**The fix will work AFTER we:**
1. Reduce check interval to 1 minute
2. Disable Alpaca bracket orders (or widen them significantly)

---

## 🔧 Files to Modify

1. **services/position_manager/main.py**
   - Line 154: `time.sleep(300)` → `time.sleep(60)`

2. **services/dispatcher/alpaca_broker/broker.py**
   - Remove or disable bracket order setting
   - Let position manager handle all exits

3. **services/dispatcher/main.py** (optional)
   - Add immediate `active_positions` creation after execution

---

## ⏱️ Timeline Analysis

| Time (AZ) | Event | Service |
|-----------|-------|---------|
| 9:06:39 | BMY opened | Dispatcher |
| 9:06:40 | WMT opened | Dispatcher |
| 9:06:40 | Bracket orders set? | Dispatcher → Alpaca |
| 9:10:59 | BMY closed | Alpaca brackets |
| 9:11:00 | WMT closed | Alpaca brackets |
| 9:11:XX | Position manager checks | Too late! |
| 9:12:00 | Exit fix deployed | After positions closed |

**Conclusion:** Exit fix deployed AFTER positions already closed, AND position manager was checking too slowly to ever see them.

---

## 📞 Next Steps

1. **Reduce check interval** - Most critical
2. **Investigate bracket orders** - Are they being set?
3. **Test with next positions** - Verify fix works
4. **Monitor for 30+ minute holds** - Confirm success

**Status:** Exit logic is fixed in code but can't execute due to timing gap.
