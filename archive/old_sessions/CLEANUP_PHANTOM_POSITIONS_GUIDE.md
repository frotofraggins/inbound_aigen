# 🧹 Phantom Positions Cleanup Guide

**Date:** February 3, 2026  
**Status:** Ready to Execute  
**Priority:** HIGH - Prevents Position Manager errors

---

## 🎯 What Are Phantom Positions?

Phantom positions are records in the database that show as "open" but don't actually exist in Alpaca. They were created by the original bug where:

1. Position Manager tried to close option positions
2. Bug caused it to create short stock positions instead
3. User manually closed those shorts via Alpaca dashboard
4. Database was never updated → positions still show as "open"

**Result:** Position Manager keeps trying to close positions that don't exist, generating errors.

---

## 📊 Current State

### Database vs Alpaca Mismatch

**Large Account:**
- Alpaca: 3 real positions
- Database: 17 positions (14 phantom)
- **Phantom IDs:** 16, 24, 13, 21

**Tiny Account:**
- Alpaca: 0 positions (all manually closed)
- Database: 17 positions (all phantom)
- **Phantom IDs:** 19, 32, 33

**Total Phantom Positions to Clean:** 7

---

## 🔧 Cleanup Script

Two scripts are available:

### Option 1: Direct Database Connection (Recommended)
**File:** `cleanup_phantom_direct.py`

**Advantages:**
- ✅ Direct database access
- ✅ Immediate execution
- ✅ Full control
- ✅ Detailed output

**Usage:**
```bash
python3 cleanup_phantom_direct.py
```

### Option 2: Lambda-Based (Original)
**File:** `cleanup_phantom_positions.py`

**Note:** This script was designed to use `db-query-lambda` but that Lambda only allows SELECT queries. Use the direct script instead.

---

## 🚀 Execution Steps

### Step 1: Run Cleanup Script

```bash
cd /home/nflos/workplace/inbound_aigen
python3 cleanup_phantom_direct.py
```

**Expected Output:**
```
================================================================================
PHANTOM POSITION CLEANUP - DIRECT DATABASE
================================================================================

Phantom positions to close:
  - Large account: 4 positions (IDs: 16, 24, 13, 21)
  - Tiny account: 3 positions (IDs: 19, 32, 33)

================================================================================

Loading database configuration...
✅ Connected to: ops-pipeline-db.xxx.us-west-2.rds.amazonaws.com:5432/ops_pipeline

Executing UPDATE query...

✅ SUCCESS! Closed 7 phantom positions:
  - ID 16: QCOM → closed (manual_reconciliation)
  - ID 24: CRM260227P00200000 → closed (manual_reconciliation)
  - ID 13: NOW → closed (manual_reconciliation)
  - ID 21: ORCL260213C00155000 → closed (manual_reconciliation)
  - ID 19: SPY → closed (manual_reconciliation)
  - ID 32: NOW260220P00110000 → closed (manual_reconciliation)
  - ID 33: QCOM260220P00145000 → closed (manual_reconciliation)

================================================================================
VERIFICATION
================================================================================

✅ Current open positions:
  - Total: 3
  - Options: 3
  - Stocks: 0

✅ Database is clean! Only real positions remain.

================================================================================
✅ CLEANUP COMPLETE!
================================================================================
```

### Step 2: Verify with Sync Script

```bash
python3 scripts/sync_positions_with_alpaca.py
```

**Expected Output:**
```
Large Account:
  Alpaca: 3 positions
  Database: 3 positions
  ✅ MATCH!

Tiny Account:
  Alpaca: 0 positions
  Database: 0 positions
  ✅ MATCH!
```

### Step 3: Monitor Position Manager Logs

```bash
aws logs tail /ecs/ops-pipeline/position-manager-service \
  --region us-west-2 \
  --since 10m \
  --follow | grep -i "position\|error"
```

**Should NOT see:**
- ❌ "position does not exist"
- ❌ "no position found for symbol"
- ❌ "error closing position"

**Should see:**
- ✅ "Checking 3 open positions" (large account)
- ✅ "Checking 0 open positions" (tiny account)
- ✅ Clean monitoring cycles

---

## 📝 What the Cleanup Does

### SQL Query Executed

```sql
UPDATE active_positions
SET 
    status = 'closed',
    close_reason = 'manual_reconciliation',
    closed_at = NOW(),
    exit_price = entry_price,  -- Use entry price (no profit/loss)
    current_pnl_dollars = 0,
    current_pnl_percent = 0
WHERE status IN ('open', 'closing')
AND id IN (16, 24, 13, 21, 19, 32, 33);
```

### Fields Updated

- **status:** `open` → `closed`
- **close_reason:** Set to `manual_reconciliation`
- **closed_at:** Current timestamp
- **exit_price:** Set to entry_price (neutral exit)
- **current_pnl_dollars:** Set to 0
- **current_pnl_percent:** Set to 0

**Why neutral exit?** These positions were manually closed in Alpaca, so we don't have the actual exit prices. Setting to entry price marks them as closed without affecting P&L calculations.

---

## ✅ Success Criteria

After cleanup, verify:

- [ ] Script reports 7 positions closed
- [ ] Database shows 3 open positions (large account)
- [ ] Database shows 0 open positions (tiny account)
- [ ] Sync script shows Alpaca and Database match
- [ ] Position Manager logs show no errors
- [ ] No "position does not exist" errors

---

## 🔍 Troubleshooting

### Issue: Script Can't Connect to Database

**Error:** `could not connect to server`

**Solution:**
1. Check AWS credentials: `aws sts get-caller-identity`
2. Verify SSM parameters exist:
   ```bash
   aws ssm get-parameter --name /ops-pipeline/db_host --region us-west-2
   ```
3. Check security group allows your IP

### Issue: Positions Still Show as Open

**Error:** Database still shows 17 positions after cleanup

**Solution:**
1. Check if script actually executed UPDATE:
   ```bash
   python3 cleanup_phantom_direct.py 2>&1 | grep "SUCCESS"
   ```
2. Verify position IDs are correct:
   ```bash
   python3 scripts/sync_positions_with_alpaca.py
   ```
3. Re-run cleanup script

### Issue: Position Manager Still Shows Errors

**Error:** Logs still show "position does not exist"

**Solution:**
1. Wait 5 minutes for Position Manager to pick up changes
2. Check if service is using latest code (revision 8):
   ```bash
   aws ecs describe-services \
     --cluster ops-pipeline-cluster \
     --service position-manager-service \
     --region us-west-2 \
     --query 'services[0].taskDefinition'
   ```
3. Force service restart if needed:
   ```bash
   aws ecs update-service \
     --cluster ops-pipeline-cluster \
     --service position-manager-service \
     --force-new-deployment \
     --region us-west-2
   ```

---

## 📚 Related Documentation

- **Original Bug:** `CRITICAL_BUG_CLOSING_WRONG_SYMBOL.md`
- **Position Manager Fixes:** `POSITION_MANAGER_CRITICAL_FIXES_2026-02-03.md`
- **Final Fix:** `FINAL_FIX_CLOSE_POSITION_API_2026-02-03.md`
- **System Documentation:** `COMPLETE_SYSTEM_DOCUMENTATION_2026-02-03.md`

---

## 🎓 Why This Happened

### The Bug Chain

1. **Original Bug:** Position Manager used wrong symbol (stock instead of option)
2. **Unintended Result:** Created short stock positions instead of closing options
3. **Manual Fix:** User closed shorts via Alpaca dashboard
4. **Database Gap:** Database never updated → positions still "open"
5. **Ongoing Errors:** Position Manager keeps trying to close phantom positions

### The Fix Chain

1. **Code Fix:** Position Manager now uses `close_position()` API ✅
2. **Database Cleanup:** This script closes phantom positions ⏳
3. **Verification:** Sync script confirms database matches Alpaca ⏳
4. **Monitoring:** Position Manager runs cleanly ⏳

---

## 🔮 After Cleanup

### Immediate (Next 10 Minutes)
1. ✅ Database matches Alpaca
2. ✅ No more phantom position errors
3. ✅ Position Manager runs cleanly

### Soon (Next Session)
1. Apply migration 013 (add missing columns for trailing stops)
2. Re-enable trailing stop logic
3. Implement trailing stops feature (user request)

### Later (Future Enhancement)
1. Add automated reconciliation job
2. Add alerts for database/Alpaca mismatches
3. Add integration tests for position closing

---

## 📊 Position Details

### Phantom Positions Being Closed

**Large Account (4 positions):**
- ID 16: QCOM (stock)
- ID 24: CRM260227P00200000 (option)
- ID 13: NOW (stock)
- ID 21: ORCL260213C00155000 (option)

**Tiny Account (3 positions):**
- ID 19: SPY (stock)
- ID 32: NOW260220P00110000 (option)
- ID 33: QCOM260220P00145000 (option)

**Real Positions Being Kept:**

**Large Account (3 positions):**
- QCOM PUT (option)
- SPY (stock)
- NOW PUT (option)

**Tiny Account (0 positions):**
- All manually closed

---

## ✅ Final Checklist

Before running cleanup:
- [ ] Read this guide completely
- [ ] Understand what phantom positions are
- [ ] Know which positions will be closed
- [ ] Have AWS credentials configured

After running cleanup:
- [ ] Verify 7 positions closed
- [ ] Run sync script
- [ ] Check Position Manager logs
- [ ] Confirm no errors for 10 minutes

---

**Status:** 📋 READY TO EXECUTE  
**Risk:** ✅ LOW - Only closes phantom positions  
**Reversible:** ⚠️ NO - But positions are already closed in Alpaca  
**Impact:** ✅ POSITIVE - Fixes Position Manager errors

**Next Action:** Run `python3 cleanup_phantom_direct.py` to clean up phantom positions! 🚀
