# 🎯 Next Session Tasks - Concrete Actions
**Date:** 2026-02-04 19:33 UTC

---

## ✅ What's Working Now

1. **Exit protection deployed** - 1-min checks, 30-min hold, -40%/+80%
2. **INTC Position 606** - Held 45+ minutes, verified working
3. **position_history logging improved** - Will show detailed errors
4. **Documentation organized** - 10 essential files, rest archived
5. **API limitations documented** - 403 explained in docs/ALPACA_API_REFERENCE.md

---

## 🔧 Ready to Enable (Just Needs Migration)

### Trailing Stops Feature
**Status:** CODE READY, just blocked on adding database columns

**What it does:**
- Solves "exit at bad timing" problem
- Locks in 75% of peak gains
- Exits when drops 25% from peak
- AMD example: Peak +15% → exits at -5% OR higher if peaked higher

**Files:**
- Code: services/position_manager/monitor.py (lines 380-425, disabled at line 394)
- Migration: db/migrations/013_phase3_improvements.sql
- Script: scripts/apply_013_direct.py (ready to run)
- Docs: docs/TRAILING_STOPS_READY_TO_ENABLE.md

**To enable:**
1. Run: `python3 scripts/apply_013_direct.py` (adds peak_price columns)
2. Edit monitor.py line 394: Remove `return None`
3. Rebuild: `./scripts/rebuild_and_deploy_position_manager.sh`
4. Test with live positions

---

## ⏳ Waiting For

### position_history Error Details
- Improved logging deployed
- Need position to close
- Will show full error traceback
- Then fix root cause

---

## 📋 Concrete Next Steps

### Step 1: Apply Migration 013
```bash
python3 scripts/apply_013_direct.py
```

**What this adds:**
- peak_price column
- trailing_stop_price column
- entry_underlying_price column
- original_quantity column
- iv_history table
- Partial exit tracking

### Step 2: Enable Trailing Stops
Edit `services/position_manager/monitor.py` line 394:

**Change from:**
```python
# TODO: Re-enable after running migration 013
return None
```

**Change to:**
```python
# Enabled 2026-02-04 - trailing stops active
# return None  # commented out
```

### Step 3: Rebuild and Deploy
```bash
cd services/position_manager
docker build --no-cache -t 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/position-manager:account-filter .
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/position-manager:account-filter
aws ecs update-service --cluster ops-pipeline-cluster --service position-manager-service --force-new-deployment --region us-west-2
aws ecs update-service --cluster ops-pipeline-cluster --service position-manager-tiny-service --force-new-deployment --region us-west-2
```

### Step 4: Verify Trailing Stops Active
```bash
# Wait 60 seconds, then check logs
aws logs tail /ecs/ops-pipeline/position-manager-service --since 2m --region us-west-2 | grep -i "trailing"
```

Look for: "Trailing stop triggered" or "Updated trailing stop"

### Step 5: Test With Live Positions
- AMD currently at +15%
- Watch for trailing stop updates
- Verify exits when drops from peak

---

## 🐛 Still To Fix

### 1. position_history Inserts
- Improved logging deployed (18:49 UTC)
- Waiting for position close to see error
- Then fix based on error details

### 2. instrument_type Detection
- Some options logged as STOCK
- Check dispatcher execution logging
- Fix detection logic

---

## 📊 Progress

**Task file:** POSITION_EXIT_FIX_TASK_LIST.md
**Progress:** 71/81 tasks (88%)
**Phases complete:** 11 of 14

**Key files:**
- scripts/apply_013_direct.py (ready)
- docs/TRAILING_STOPS_READY_TO_ENABLE.md (instructions)
- services/position_manager/monitor.py line 394 (enable here)

---

**PRIORITY:** Enable trailing stops to solve "bad timing" exits

**ESTIMATED TIME:** 15 minutes

**BENEFIT:** Better exit timing, locks partial profits
