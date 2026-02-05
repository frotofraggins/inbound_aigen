# ⏰ Option Expiration Handling - How It Works

## ✅ Yes, We Handle Expiration!

The position manager has **TWO layers of expiration protection** built in.

---

## 🎯 Expiration Logic

### Check 1: Emergency Exit (24 Hours Before Expiry)
**Location:** `monitor.py` line 359-378

```python
OPTIONS_EXPIRY_WARNING_HOURS = 24  # From config.py

# Check if within 24 hours of expiration
if hours_to_expiry <= 24:
    # HIGH PRIORITY EXIT - expiration risk
    return {
        'reason': 'expiration_risk',
        'priority': 2,  # High priority
        'message': f'Options expiring in {hours_to_expiry:.1f} hours'
    }
```

**What this does:**
- Checks expiration date every minute
- If < 24 hours until expiry → Force close
- Priority 2 (high) - overrides other exit logic
- **Purpose:** Prevent worthless expiration

### Check 2: Theta Decay Protection (7 Days Before Expiry)
**Location:** `monitor.py` line 500-516

```python
# If < 7 days to expiry and not profitable enough
if days_to_expiry <= 7 and option_pnl_pct < 30:
    # Exit to avoid theta decay eating profits
    return {
        'reason': 'theta_decay_risk',
        'priority': 4,
        'message': f'{days_to_expiry} days to expiry, only +{option_pnl_pct:.1f}% profit'
    }
```

**What this does:**
- If within 7 days of expiry AND < 30% profit
- Suggests exit to preserve gains
- Priority 4 (medium-low)
- **Purpose:** Avoid theta decay eroding profits

---

## 📊 INTC Example (Current Position)

### INTC260220C00049500
- **Symbol breakdown:**
  - INTC = Intel stock
  - 260220 = February 20, 2026 (expiration)
  - C = Call option
  - 00049500 = $49.50 strike price

### Expiration Timeline
- **Today:** February 4, 2026
- **Expiration:** February 20, 2026
- **Days until expiry:** 16 days
- **Hours until expiry:** 384 hours

### How Code Will Handle It

**Today (Day 0-9):**
- Normal exit logic applies
- 30-minute minimum hold
- Exit at -40% or +80%
- No expiration concerns

**Days 10-15 (Feb 14-19):**
- Still normal operation
- But if within 7 days AND < 30% profit
- May suggest early exit (theta decay check)

**Last 24 Hours (Feb 19-20):**
- **EMERGENCY MODE**
- Automatic force close
- High priority (overrides everything)
- Prevents worthless expiration

---

## 🎯 Protection Levels

### Level 1: Expiration Emergency (< 24 hours)
- **Priority:** 2 (Very High)
- **Action:** Force close immediately
- **Reason:** Contract becomes worthless at expiry
- **Can't be overridden**

### Level 2: Theta Decay Warning (< 7 days)
- **Priority:** 4 (Medium-Low)
- **Condition:** < 7 days AND < 30% profit
- **Action:** Suggest exit
- **Reason:** Time decay eating profits
- **Can be overridden by other logic**

### Level 3: Normal Operations (> 7 days)
- **All normal exit logic applies:**
  - 30-minute minimum hold
  - -40% stop loss
  - +80% take profit
  - Max hold time

---

## 📅 INTC Timeline Prediction

### Feb 4-13 (Days 1-9)
- Normal exit logic
- Hold 30 minutes minimum
- Exit at -40% or +80%
- No expiration risk

### Feb 14-19 (Days 10-15)
- Still mostly normal
- Theta decay check active
- If not profitable (< 30%), may suggest exit
- Emergency check not triggered yet

### Feb 19 11:14 AM - Feb 20 11:14 AM (Last 24 hours)
- **EMERGENCY MODE**
- Force close regardless of P&L
- High priority exit
- Prevents worthless expiration

---

## ✅ INTC Status (Current)

### Expiration Info
- **Expires:** Feb 20, 2026 @ 11:14 AM
- **Days until expiry:** 16 days
- **Within 24-hour emergency?** NO ✅
- **Within 7-day theta warning?** NO ✅

### Current Exit Logic Active
1. ✅ 30-minute minimum hold (currently 13 min old)
2. ✅ -40% stop loss ($1.16)
3. ✅ +80% take profit ($3.47)
4. ✅ Max hold time (4 hours default)
5. ❌ Expiration emergency (not yet - 16 days away)
6. ❌ Theta decay warning (not yet - 16 days away)

**Result:** Position will be held normally, won't force close due to expiration for 15 more days.

---

## 🎓 Why This Design Is Smart

### Advantage 1: No Surprise Worthless Expiration
- Emergency exit at 24 hours prevents total loss
- Even if forgot about position
- Automatic protection

### Advantage 2: Theta Decay Awareness
- Options lose value as expiration approaches
- If not profitable enough at 7 days, better to exit
- Preserves small gains from theta erosion

### Advantage 3: Normal Operations Most of Time
- For first 2 weeks, normal exit logic
- Only restricts near expiration
- Allows full strategy to play out

---

## 📊 Summary for INTC

**INTC260220C00049500 Expiration Handling:**

| Days Until Expiry | Current Status | Action |
|---|---|---|
| 16 (today) | ✅ Safe | Normal exit logic |
| 10-15 | 🟡 Monitor | Theta check if < 30% profit |
| < 7 days | 🟡 Warning | Exit suggested if unprofitable |
| < 24 hours | 🔴 Emergency | Force close immediately |

**Current:** 16 days away, fully protected, normal operations ✅

---

## 🔍 How to Monitor Expiration

### In Logs (When It Triggers)
```
Options expiring in 23.5 hours - expiration_risk
```
or
```
7 days to expiry, only +15.0% profit - theta_decay_risk
```

### For INTC Specifically
Won't see expiration messages until:
- Feb 13 (7 days): Theta decay check activates if < 30% profit
- Feb 19 (24 hours): Emergency exit triggers automatically

---

**ANSWER:** Yes, we handle expiration! Two-tier system with 24-hour emergency exit and 7-day theta decay protection.

**INTC STATUS:** 16 days until expiry, no expiration risk currently, normal exit logic active.

**SMART DESIGN:** Prevents worthless expiration while allowing strategy to work for most of contract life.
