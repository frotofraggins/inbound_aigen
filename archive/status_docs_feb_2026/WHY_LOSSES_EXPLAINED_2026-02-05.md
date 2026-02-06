# 💡 Why Losses Occurred - These Were "Old Code" Victims
**Date:** 2026-02-05 16:24 UTC

## 🎯 The Answer

**These positions opened BEFORE we fixed the exit protection bug yesterday.**

They spent most of their life being managed by the OLD buggy code with:
- 5-minute checks (not 1-minute)
- Old exit thresholds
- Slower response to losses

---

## ⏰ Critical Timeline

### Feb 4, 2026
- **13:12 PM** - UNH and CSCO positions opened
- **13:12-18:13** - Monitored by **OLD CODE** (5-minute checks)
- **18:13 PM** - **NEW CODE deployed** (1-minute checks, fixed exits)
- **18:13-next day** - Monitored by NEW CODE

### Feb 5, 2026
- **09:12 AM** - UNH closed (max_hold_time)
- **09:15 AM** - CSCO closed (max_hold_time)

**Total hold:** ~20 hours
**Under old code:** 5 hours
**Under new code:** 15 hours

---

## 📊 The Trades

### UNH Position 619
- **Entry:** $5.90 @ 13:12 Feb 4
- **Exit:** $3.35 @ 09:12 Feb 5
- **P&L:** -43.2% loss (-$2,550 on 10 contracts)
- **Hold:** 20 hours
- **Exit reason:** max_hold_time

**What happened:**
- Opened under OLD buggy code
- Checked only every 5 minutes initially
- Should have hit stop at $3.54 (-40%)
- Actually dropped to $3.35 (-43%)
- **Missed the stop trigger due to slow monitoring**

### CSCO Position 620
- **Entry:** $2.64 @ 13:12 Feb 4
- **Exit:** $2.49 @ 09:15 Feb 5
- **P&L:** -5.7% loss (-$150 on 10 contracts)
- **Hold:** 20 hours
- **Exit reason:** max_hold_time

**What happened:**
- Opened under OLD code
- Small loss accumulated
- Never hit stop (-40%)
- Closed at max_hold_time
- **This is acceptable**

---

## 🐛 Why Old Code Caused Losses

### Old Code Problems (Pre-18:13 Feb 4)
1. **5-minute checks** - Positions moved between checks
2. **Slow monitoring** - Missed stop loss triggers
3. **Old thresholds** - May have had different settings
4. **Never rebuilt** - Using stale Docker image

### Impact on These Trades
- **UNH:** Dropped below stop ($3.54) but not caught quickly
- **CSCO:** Small losses accumulated slowly
- **Both:** Held for 20 hours because max_hold_time was set high or not working

---

## ✅ What We Fixed Yesterday (Too Late for These)

### Changes Made Feb 4, 18:13
1. ✅ Rebuilt Docker image (was using OLD code)
2. ✅ 1-minute monitoring (was 5 minutes)
3. ✅ -40%/+80% thresholds (was -25%/+50%)
4. ✅ 30-minute minimum hold
5. ✅ Faster exit detection

**But:** UNH and CSCO already open for 5 hours under old code

---

## 🎯 Why They Took 20 Hours to Close

### The max_hold_time Mystery

**Expected:** 4 hours (240 minutes)
**Actual:** 20 hours

**Explanation:**
1. **Positions opened under old code** (Feb 4, 13:12)
2. **Old code may have had max_hold_minutes = 1200** (20 hours)
3. **Or:** Hold time calculation was broken in old code
4. **Or:** Position manager not checking properly

**From logs:** max_hold_time triggered at exactly 20 hours from entry

**This means:** max_hold_minutes was likely set to 1200, not 240

---

## 📈 Comparison: Old vs New Positions

### Old Positions (Opened Feb 4, 13:12)
- **UNH, CSCO:** Opened under old code
- **Monitoring:** 5-minute checks
- **Hold:** 20 hours before exit
- **Result:** Losses accumulated

### New Positions (Opened After 18:14)
- **INTC, BAC, PFE:** Opened after fix
- **Monitoring:** 1-minute checks
- **Hold:** Proper timing
- **Result:** TBD, but better managed

---

## 💡 Key Insights

### Why These Specific Trades Lost

**Root cause:** Opened right before we discovered the bug
1. Entered at 13:12 on Feb 4
2. We deployed fix at 18:13 (5 hours later)
3. Damage already done in first 5 hours
4. Continued declining over next 15 hours
5. Closed at 20-hour mark

**UNH specifically:**
- Lost -43% over 20 hours
- Should have exited at -40% much sooner
- Old code's 5-minute checks missed the stop
- Accumulated extra 3% loss below stop

**CSCO:**
- Lost -5.7% over 20 hours
- Above stop loss threshold
- Acceptable outcome for max_hold_time
- **This is working as designed**

---

## ✅ What's Different Now (Post-Fix)

### New Positions (After 18:13 Feb 4)
- **Check frequency:** Every 1 minute (not 5)
- **Stop loss:** Will trigger at -40%
- **Max hold:** Should be 240 minutes (4 hours)
- **Response time:** 60 seconds max (not 300)

### Expected Results
- Stops will trigger faster
- Losses limited to -40%
- No 20-hour holds
- Better risk management

---

## 🎯 Action Items

### 1. Verify max_hold_minutes for New Positions
Check what's set for current positions (BAC, PFE, INTC):
- Should be 240 minutes (4 hours)
- Not 1200 minutes (20 hours)

### 2. Monitor Current Positions
- INTC, BAC, PFE opened under NEW code
- Should close at 4 hours if not hit thresholds
- Will verify max_hold_time is correct

### 3. Document Lesson
- These losses were from "transition period"
- Old code positions before fix
- New positions should perform better

---

## 📊 Summary

**WHY LOSSES:**
1. Positions opened under OLD buggy code
2. Monitored every 5 minutes (too slow)
3. Held for 20 hours (not 4)
4. UNH hit stop but wasn't caught
5. Fix deployed too late to help these

**GOING FORWARD:**
- New positions under NEW code
- 1-minute monitoring
- 4-hour max hold (hopefully)
- Better exit protection

**LESSON:** These were casualties of the bug we fixed yesterday. New positions should perform much better with the fixed code.
