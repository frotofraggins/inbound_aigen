# Alpaca Paper Trading - Complete Fix v4

**Date:** February 3, 2026 17:25 UTC  
**Status:** Ready to Deploy

---

## 🎯 Issues Fixed in This Version

### 1. Price Precision Error (CRITICAL)
**Problem:** Alpaca rejects orders with sub-penny prices (more than 2 decimal places)
```
Error: "invalid take_profit.limit_price 699.7462. sub-penny increment does not f..."
```

**Fix:** Round all stock prices to 2 decimal places in `_execute_stock()`:
```python
# Round prices to 2 decimal places (Alpaca rejects sub-penny prices)
entry_price = round(entry_price, 2)
if stop_loss:
    stop_loss = round(stop_loss, 2)
if take_profit:
    take_profit = round(take_profit, 2)
```

### 2. Import Error for Options Validation (CRITICAL)
**Problem:** Code was trying to import from `alpaca.options` which doesn't exist
```
Error: "No module named 'alpaca.options'"
```

**Fix:** Changed imports to use local `options` module:
```python
# Before (WRONG):
from alpaca.options import validate_iv_rank
from alpaca.options import calculate_kelly_criterion_size

# After (CORRECT):
from options import validate_iv_rank
from options import calculate_kelly_criterion_size
```

### 3. Missing Action Variable (CRITICAL)
**Problem:** `action` variable was not defined in `_execute_stock()` but used in return statement

**Fix:** Extract action from recommendation at start of function:
```python
# Extract action from recommendation
action = recommendation['action']
```

---

## ✅ All Fixes Applied

1. ✅ Price rounding for stocks (2 decimal places)
2. ✅ Fixed import from `alpaca.options` → `options` (validate_iv_rank)
3. ✅ Fixed import from `alpaca.options` → `options` (calculate_kelly_criterion_size)
4. ✅ Added action variable extraction in _execute_stock
5. ✅ Verified all dependencies in requirements.txt
6. ✅ Verified all local modules exist (options.py, db/iv_history.py)

---

## 📦 Deployment Steps

1. **Build Docker Image:**
   ```bash
   docker build -t ops-pipeline/dispatcher:alpaca-sdk-v4 services/dispatcher
   ```

2. **Tag for ECR:**
   ```bash
   docker tag ops-pipeline/dispatcher:alpaca-sdk-v4 \
     160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/dispatcher:alpaca-sdk-v4
   ```

3. **Push to ECR:**
   ```bash
   docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/dispatcher:alpaca-sdk-v4
   ```

4. **Register Task Definition:**
   ```bash
   aws ecs register-task-definition \
     --cli-input-json file://deploy/dispatcher-task-definition.json \
     --region us-west-2
   ```

5. **Update Service:**
   ```bash
   aws ecs update-service \
     --cluster ops-pipeline-cluster \
     --service dispatcher-service \
     --task-definition ops-pipeline-dispatcher:31 \
     --force-new-deployment \
     --region us-west-2
   ```

---

## 🔍 Verification Steps

After deployment, check logs for:

1. **Successful Connection:**
   ```
   Connected to Alpaca Paper Trading
   Account: PA3PBOQAH7ZY
   Buying power: $209234.50
   ```

2. **Order Submission (Stock):**
   ```
   {"event": "execution_simulated", "execution_mode": "ALPACA_PAPER"}
   ```
   Should show `ALPACA_PAPER` not `SIMULATED_FALLBACK`

3. **No More Errors:**
   - ❌ No "sub-penny increment" errors
   - ❌ No "No module named 'alpaca.options'" errors
   - ❌ No "NameError: name 'action' is not defined" errors

4. **Check Alpaca Positions:**
   ```bash
   # Via API or Alpaca dashboard
   # Should see positions opening in paper account
   ```

---

## 📊 Expected Behavior

### Before Fix:
- Orders submitted to Alpaca ✅
- Orders rejected due to price precision ❌
- Fallback to simulation ❌
- Status: SIMULATED_FALLBACK ❌

### After Fix:
- Orders submitted to Alpaca ✅
- Orders accepted (prices rounded) ✅
- Real fills from Alpaca ✅
- Status: ALPACA_PAPER ✅
- Positions tracked in Alpaca ✅

---

## 🎉 Success Criteria

- [ ] Dispatcher connects to Alpaca successfully
- [ ] Stock orders are accepted (no price precision errors)
- [ ] Options orders work (no import errors)
- [ ] Executions show status="EXECUTED" not "SIMULATED"
- [ ] Positions appear in Alpaca Paper account
- [ ] Position Manager tracks positions correctly

---

## 📝 Files Modified

- `services/dispatcher/alpaca_broker/broker.py` - All fixes applied
- `deploy/dispatcher-task-definition.json` - Updated image to alpaca-sdk-v4

---

## 🚀 Next Steps After Deployment

1. Monitor logs for 5-10 minutes
2. Verify orders are being accepted
3. Check Alpaca Paper account for positions
4. Verify Position Manager is tracking correctly
5. If all good, consider disabling redundant schedulers:
   - `ops-pipeline-dispatcher-tiny`
   - `ops-pipeline-classifier`

---

## 🔧 Rollback Plan

If issues occur:
```bash
# Revert to previous revision (30)
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service dispatcher-service \
  --task-definition ops-pipeline-dispatcher:30 \
  --force-new-deployment \
  --region us-west-2
```

---

**Ready to deploy!** All issues identified and fixed in a single comprehensive update.
