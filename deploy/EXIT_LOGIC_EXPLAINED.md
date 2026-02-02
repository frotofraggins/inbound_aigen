# Exit Logic - Complete Explanation

**Created:** 2026-01-29  
**Critical Issue Identified:** Position Manager Not Monitoring Positions

---

## Your Questions Answered

### Q1: When will META sell?

**Answer: It won't automatically right now.**

**The Problem:**
- Positions exist in `dispatch_executions` (trade ledger)
- But `active_positions` table is EMPTY
- Position Manager isn't monitoring them
- So exits won't trigger automatically

### Q2: Does it know when it hit the top?

**Answer: It has a target ($726.37 for META), but isn't checking it.**

**The Targets Were Calculated:**
- Take Profit: $726.37 (META stock price)
- Stop Loss: $720.60 (META stock price)
- Entry: $720.93 (META stock when trade made)

**Current META Price:** ~$725 (within exit range!)

**But:** Position Manager has no active positions to monitor

### Q3: Does it know beforehand what it thinks it will go to?

**Answer: YES - calculated at entry time.**

**How Targets Are Set:**

```python
# At entry (16:36:38):
META_price = $720.93
entry_premium = $17.15

# Calculate stop loss (2 ATR below entry)
stop_loss = $720.93 - (2 × $ATR) = $720.60

# Calculate take profit (2:1 risk/reward)
risk = $720.93 - $720.60 = $0.33
reward = $0.33 × 2 = $0.66
take_profit = $720.93 + $0.66 = $726.37
```

**These targets are STOCK prices, not option prices!**

---

## The Critical Gap

### What's Happening

**1. Dispatcher Creates Trades ✅**
```
dispatch_executions table:
- META: 6 contracts @ $17.15
- Stop: $720.60
- Target: $726.37
- Status: SIMULATED
```

**2. Position Manager Should Monitor ❌**
```
active_positions table:
- (EMPTY)
- Position Manager has nothing to monitor
- Exits never trigger
```

### Why This Happens

**Position Manager expects:**
```python
# In monitor.py: sync_new_positions()
# This should copy dispatch_executions → active_positions
# But it's not running or not working
```

**The Flow Should Be:**
```
1. Dispatcher creates execution (✅ working)
2. Position Manager picks it up (❌ not happening)
3. Position Manager monitors price (❌ no positions)
4. Position Manager triggers exits (❌ never runs)
```

---

## Current Exit Logic (When It Works)

### From `services/position_manager/monitor.py`

**Exit Conditions Checked:**

1. **Stop Loss Hit** (Priority 1)
   ```python
   if current_price <= stop_loss:
       exit("stop_loss hit")
   ```

2. **Take Profit Hit** (Priority 1)
   ```python
   if current_price >= take_profit:
       exit("take_profit hit")
   ```

3. **Day Trade Close** (Priority 2)
   ```python
   if strategy == 'day_trade' and time >= 15:55 ET:
       exit("day trade must close")
   ```

4. **Max Hold Time** (Priority 3)
   ```python
   if minutes_held >= max_hold_minutes:
       exit("max hold time exceeded")
   ```

5. **Expiration Risk** (Priority 2)
   ```python
   if hours_to_expiry <= 24:
       exit("options expiring soon")
   ```

---

## Why META Hasn't Exited

### The Answer

**Position Manager isn't monitoring META because:**

1. ❌ `active_positions` table is empty
2. ❌ Position Manager didn't sync from executions
3. ❌ No monitoring = no exit checks
4. ❌ Your +$3,210 profit just sits there

**Ironically:**
- META stock is at ~$725
- Target is $726.37
- It's 0.19% away from target!
- But nobody's watching

---

## What About QCOM?

**QCOM Position:**
- Entry: 26 contracts @ $5.75 (strike $150)
- Take Profit: $151.70 (QCOM stock)
- Stop Loss: $150.71 (QCOM stock)

**Your Alpaca shows:** Dash (–) for P&L

**This means:**
- Either exited already and you're seeing old data
- Or also not being monitored
- Need to check Alpaca directly

---

## How To Fix This

### Immediate: Check Position Manager

**1. Is Position Manager Running?**
```bash
aws scheduler get-schedule \
  --name ops-pipeline-position-manager \
  --region us-west-2 \
  --query 'State'
```

**2. Check Position Manager Logs**
```bash
aws logs tail /ecs/ops-pipeline/position-manager \
  --region us-west-2 \
  --since 1h \
  | grep -E "(syncing|monitoring|exit)"
```

**3. Manually Check Alpaca**
```python
import requests

headers = {
    'APCA-API-KEY-ID': 'YOUR_KEY',
    'APCA-API-SECRET-KEY': 'YOUR_SECRET'
}

# Get open positions
r = requests.get('https://paper-api.alpaca.markets/v2/positions', headers=headers)
positions = r.json()

for pos in positions:
    print(f"{pos['symbol']}: {pos['qty']} @ ${pos['avg_entry_price']} "
          f"Current: ${pos['current_price']} "
          f"P&L: ${pos['unrealized_pl']} ({pos['unrealized_plpc']}%)")
```

---

## Phase 3: What Needs to Be Fixed

### Issue #1: Position Syncing Not Working

**Problem:** dispatch_executions → active_positions sync failing

**Fix:** Debug why Position Manager isn't creating active_positions

### Issue #2: Exit Logic Uses Stock Price

**Problem:** 
- Targets are STOCK prices ($726.37)
- But we're trading OPTIONS
- Option price ≠ stock price
- $17.15 option → $22.50 option (+31%)
- But stock only moved $720 → $725 (+0.7%)

**Fix:** 
- Monitor option price directly
- Or use underlying % moves (e.g., stock +5% = exit)
- Or use option % targets (+50% profit = exit)

### Issue #3: Targets Too Tight for Options

**Current:**
- Stop: $720.60
- Entry: $720.93  
- Target: $726.37
- Range: $5.77 (0.8%)

**Problem:**
- 0.8% stock move is NOTHING for options
- Options move 10-50% intraday
- These targets will never hit (or hit instantly)

**Fix (Phase 3):**
- Use option-based targets
- Or wider % on underlying (±3-5%)
- Or trailing stops

---

## Immediate Next Steps

### 1. Check If Position Manager Running
```bash
aws logs tail /ecs/ops-pipeline/position-manager --region us-west-2 --since 30m
```

### 2. Check Alpaca Directly
Log into Alpaca paper account and see:
- Are META/QCOM positions still open?
- What's current P&L?
- Were exits triggered outside our system?

### 3. Phase 3 Implementation
This is EXACTLY why Phase 3 is critical:
- Fix position sync
- Fix exit logic for options
- Add trailing stops
- Add time-based exits

---

## Summary

**Your META Position:**
- Entry: $17.15 premium
- Current: $22.50 premium  
- Profit: +$3,210 (+31%)
- **Issue: Not being monitored for exits**

**When It Will Exit:**
- ❌ Automatically: Never (position manager not tracking)
- ⏳ Manual: You can close in Alpaca UI
- ✅ After Phase 3: Properly with trailing stops

**The targets exist** ($726.37 take profit) **but nobody's watching them.**

**Critical:** Position Manager needs to be:
1. Running (check scheduler)
2. Syncing positions from executions
3. Monitoring active positions
4. Triggering exits when conditions met

**This is documented in Phase 3 of PRODUCTION_IMPROVEMENTS_NEEDED.md**
