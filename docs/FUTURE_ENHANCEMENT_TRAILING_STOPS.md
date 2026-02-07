# Future Enhancement: Trailing Stops for Winners

## 🎯 Your Question: What About Winning Trades?

You're absolutely right! With the current +80% take profit, if a position goes to +100%, it just closes at +80%. We should let winners run!

## ✅ Already Implemented (Currently Disabled)

### Trailing Stop Feature
**File:** `services/position_manager/monitor.py` (lines 380-425)

**How it works:**
```python
def check_trailing_stop(position):
    # Lock in 75% of peak gains
    # Example:
    # Entry: $10
    # Peak: $18 (+80%)
    # Trail: $16 (keeps 75% of $8 gain = $6 gain locked in)
    # If price drops to $16, sell
    # If price goes to $20, new trail at $17.50
```

**Why it's disabled:**
- Needs `peak_price` column in database
- Comment says: "TODO: Re-enable after running migration 013"

### Partial Profit Taking (Already Active)
**File:** `services/position_manager/monitor.py` (lines 540-585)

**Already working:**
- Take 50% off at +50% profit
- Take 25% more at +75% profit
- Let final 25% ride with trailing stop

**Example:**
```
Entry: 10 contracts at $5 = $5,000
+50%: Sell 5 contracts at $7.50, lock in $1,250 profit
+75%: Sell 2-3 more contracts at $8.75, lock more profit
+100%: Final 2-3 contracts ride to peak with trailing stop
```

### Time Decay Intelligence (Already Active)
**File:** `services/position_manager/monitor.py` (lines 606-618)

Only exits near expiration if NOT profitable:
- If +80% and 7 days to expiry: HOLD (let it run!)
- If +20% and 7 days to expiry: EXIT (theta decay risk)

---

## 🚀 To Enable Trailing Stops

### Step 1: Add peak_price Column
Run migration 013 (if it exists) or create:
```sql
ALTER TABLE active_positions ADD COLUMN peak_price DECIMAL(10, 2);
```

### Step 2: Uncomment Trailing Stop Logic
**File:** `services/position_manager/monitor.py` (line 380)

Change:
```python
# TODO: Re-enable after running migration 013 to add peak_price column
return None
```

To:
```python
# Enabled 2026-02-04 - trailing stops active
# (remove the early return)
```

### Step 3: Deploy
Redeploy position-manager with trailing stops enabled.

---

## 📊 Example with All Features Enabled

**Scenario:** NVDA PUT goes from -$30 to +$150

```
Entry: 10 contracts at $8 = $8,000
$10 (+25%): Hold, under 30-min minimum
$12 (+50%): Sell 5 contracts, lock $2,000 profit
            Keep 5 contracts riding
$14 (+75%): Sell 2 contracts, lock $600 more
            Keep 3 contracts with trailing stop
$16 (+100%): Peak hits, trail at $14 (75% of gain)
$18 (+125%): New peak, trail at $16
$17 (-5% from peak): Trailing stop hits, SELL
            Lock in $9 profit per contract × 3 = $27 profit
            
Total: $2,000 + $600 + $27 = $2,627 profit on $8,000 entry
Return: +32.8% on full position (vs +80% if sold all at first target)
```

---

## 💡 Current Behavior (After Today's Fix)

**With +80% target and 30-min hold:**
```
Entry: $8
$12 (+50%): Sell 50% (partial exit already active)
$14 (+75%): Sell 25% more (partial exit already active)
$16 (+100%): Hit +80% target on remaining 25%, SELL ALL
```

**With trailing stops enabled:**
```
Entry: $8
$12 (+50%): Sell 50% (partial exit)
$14 (+75%): Sell 25% more (partial exit)
$16, $18, $20: Keep riding with trailing stop
$17: Trail hits, SELL (after riding from $8 to $20!)
```

---

## 🎯 Recommendation

### Phase 1 (Deployed Today)
- ✅ Position manager checks every 1 minute
- ✅ No Alpaca brackets (our control)
- ✅ -40%/+80% with 30-min hold
- ✅ Partial exits at +50%/+75% (already active)

### Phase 2 (Enable Trailing Stops)
After verifying Phase 1 works:
1. Add peak_price column to database
2. Enable trailing stop logic
3. Let winners run until they pull back 25% from peak

### Phase 3 (Market Condition Monitoring)
Advanced: Check if trend is continuing
- If uptrend strong: Disable profit targets, use trailing stop only
- If trend weakening: Take profits earlier
- If reversal pattern: Exit immediately

---

## 📞 Summary

**Your concern:** +80% target might exit too early on big winners

**Good news:** Code already has:
- ✅ Partial exits (50% at +50%, 25% at +75%)
- ✅ Trailing stops (disabled, needs peak_price column)
- ✅ Theta decay intelligence (holds profitable positions near expiry)

**Next steps:**
1. Verify today's fix works (positions hold 30+ min)
2. Add peak_price column to database
3. Enable trailing stops
4. Let winners ride to peak with 75% gain lock-in

**Status:** The foundation is there, just needs trailing stops enabled!
