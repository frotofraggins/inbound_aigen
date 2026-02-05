# ✅ Trailing Stops - Ready to Enable (Solves "Bad Timing" Problem)
**Date:** 2026-02-04 18:59 UTC
**Status:** CODE EXISTS, just needs migration + activation

---

## 🎯 What This Solves

**Your Question:** "What if we close at -5% at 4 hours but it was +15% earlier?"

**Answer:** Trailing stops solve this!
- Locks in 75% of peak gains
- Exits when price drops 25% from peak
- Prevents "close at temporary low" problem

---

## ✅ What's Already Done

### 1. Code Exists ✅
**File:** `services/position_manager/monitor.py` lines 380-425

**What it does:**
- Tracks peak price every minute
- Calculates trailing stop (75% of gains locked in)
- Exits when price drops to trail level
- Adapts as position makes new highs

**Status:** CODED but DISABLED (line 394)

### 2. Migration Ready ✅
**File:** `db/migrations/013_phase3_improvements.sql`

**What it adds:**
- `peak_price` column
- `trailing_stop_price` column
- `iv_history` table
- Partial exit tracking

**Status:** EXISTS but NOT APPLIED

### 3. Database Functions Ready ✅
**File:** `services/position_manager/db.py`

Functions exist for:
- `update_position_peak()`
- `update_position_trailing_stop()`

---

## 🔧 How to Enable (3 Steps)

### Step 1: Apply Migration 013

**Option A: Via db-migrator service (Recommended)**
```bash
# Trigger db-migrator to run migration 013
aws ecs run-task \
  --cluster ops-pipeline-cluster \
  --task-definition db-migrator \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-0c182a149eeef918a],securityGroups=[sg-0cd16a909f4e794ce],assignPublicIp=ENABLED}" \
  --region us-west-2
```

**Option B: Via SQL directly**
```sql
-- Run this SQL on RDS
-- Safe to run multiple times (uses IF NOT EXISTS)

ALTER TABLE active_positions 
ADD COLUMN IF NOT EXISTS peak_price DECIMAL(12, 4),
ADD COLUMN IF NOT EXISTS trailing_stop_price DECIMAL(12, 4);
```

### Step 2: Enable in Code

**File:** `services/position_manager/monitor.py` line 394

**Change from:**
```python
# TODO: Re-enable after running migration 013 to add peak_price column
return None  # ← Remove this line
```

**Change to:**
```python
# Enabled 2026-02-04 - trailing stops active!
# return None  ← Comment out
```

### Step 3: Rebuild and Deploy

```bash
cd services/position_manager
docker build --no-cache -t 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/position-manager:account-filter .
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/position-manager:account-filter
aws ecs update-service --cluster ops-pipeline-cluster --service position-manager-service --force-new-deployment --region us-west-2
aws ecs update-service --cluster ops-pipeline-cluster --service position-manager-tiny-service --force-new-deployment --region us-west-2
```

---

## 📊 How It Will Work

### AMD Example (Your Concern)
**Without trailing stops (current):**
- Hour 1: +15% (peak)
- Hour 4: -5%
- **Closes at -5%** (loses)

**With trailing stops (after enabling):**
- Hour 1: +15% (peak) → Trail = -5% (locks in 75% of gain)
- Hour 2: +5% → Trail still -5%
- Hour 3: -5% → **TRIGGERS TRAIL STOP**
- **Exits at -5%** (before drops further)
- If peaked at +25%: Would exit at +5% not -5%!

### INTC Current Position
**After enabling:**
- Tracks peak every minute
- If hits +20%: Trail = +0% (locks in 15% of gain)
- If hits +40%: Trail = +10% (locks in 30% of gain)
- If hits +80%: Trail = +40% (locks in 60% of gain!)
- **Let winners run** but protect gains

---

## 🎯 Benefits

### 1. Locks Partial Profits
- Don't need perfect +80% to win
- If peaks at +60%, trail at +30%
- Captures partial profit

### 2. Exits on Trend Reversal
- Position reversing from peak
- Better timing than fixed max hold
- Adapts to price action

### 3. Solves Your Problem
- Won't exit at random 4-hour mark
- Won't exit at temporary low
- Uses peak/current relationship

### 4. Let Winners Run
- No fixed profit target
- Ride trends as long as they go
- Only exit on pullback

---

## ⚠️ Trade-Offs

### Still Not Perfect
- Can exit before final recovery
- Can get whipsawed in choppy markets
- 25% pullback might be too tight or too loose

### Needs Tuning
- 25% trail might be too tight (exits too early)
- Or too loose (gives back too much)
- Will need to optimize from data

### Best Used With
- Partial exits (already active: 50% at +50%, 25% at +75%)
- Max hold as backup (4 hours)
- Stop loss protection (-40%)

---

## 📈 Expected Behavior After Enabling

### For Profitable Positions
**Old:** Close at +80% or 4 hours (whichever first)
**New:** Partial exits at +50%/+75%, remainder trails peak

**Example:**
- Enter 10 contracts
- +50%: Sell 5 (lock profit)
- +75%: Sell 2-3 more (lock more)
- +100%+: Last 2-3 trail the peak
- Exit when pulls back 25% from peak

### For Your AMD (+15%)
**After enabling:**
- Current: +15.24%
- Peak tracked: +15.24%
- Trail stop: -5% (locks 75% of +15%)
- If drops to -5%: Exits (limits loss)
- If rises to +30%: Trail moves to +12.5%
- **Adapts to price action!**

---

## 🚀 Recommendation

### Do This NOW (If You Want Better Exits)
1. Apply migration 013 (adds columns)
2. Enable trailing stops (remove return None)
3. Rebuild and deploy
4. Test with AMD and INTC

### Or Wait
- Current system works (30-min hold, thresholds)
- Trailing stops are enhancement, not critical
- Can enable after more testing

---

**STATUS:** Trailing stops ready, just needs migration + code activation

**SOLVES:** "Exit at bad timing" problem you identified

**EFFORT:** 15 minutes to enable

**BENEFIT:** Better exit timing, locks partial profits, lets winners run
