# SPECIFIC FIX - Position Manager Line-by-Line

## 🎯 Exact Problem Location

**File:** `services/position_manager/db.py`  
**Function:** `create_position_from_alpaca` (starts line 318)  
**Line 323:** Includes `original_quantity` in INSERT column list  
**Line 352:** Tries to insert value for `original_quantity`

**Error:** Column doesn't exist in database!

---

## ✅ EXACT FIX (Copy-Paste Ready)

### **Step 1: Edit db.py**

**Remove ONE line from column list (line 323):**

**BEFORE:**
```python
INSERT INTO active_positions (
    ticker, instrument_type, strategy_type,
    side, quantity, entry_price, entry_time,
    strike_price, expiration_date, option_symbol,
    stop_loss, take_profit, max_hold_minutes,
    current_price, status, original_quantity,  # ← REMOVE THIS LINE
    entry_features_json,
```

**AFTER:**
```python
INSERT INTO active_positions (
    ticker, instrument_type, strategy_type,
    side, quantity, entry_price, entry_time,
    strike_price, expiration_date, option_symbol,
    stop_loss, take_profit, max_hold_minutes,
    current_price, status,  # ← original_quantity removed
    entry_features_json,
```

**Remove ONE line from values list (line 352):**

**BEFORE:**
```python
) VALUES (
    %s, %s, %s,
    %s, %s, %s, NOW(),
    %s, %s, %s,
    %s, %s, %s,
    %s, 'open', %s,  # ← REMOVE THE %s
    %s::jsonb,
```

**AFTER:**
```python
) VALUES (
    %s, %s, %s,
    %s, %s, %s, NOW(),
    %s, %s, %s,
    %s, %s, %s,
    %s, 'open',  # ← %s removed
    %s::jsonb,
```

**Remove ONE line from execute parameters (line 352):**

**BEFORE:**
```python
cur.execute(query, (
    ticker,
    instrument_type,
    'swing_trade',
    side,
    quantity,
    entry_price,
    strike_price,
    expiration_date,
    option_symbol,
    stop_loss,
    take_profit,
    240,
    current_price,
    quantity,  # original_quantity = quantity ← REMOVE THIS LINE
    json.dumps({}),
```

**AFTER:**
```python
cur.execute(query, (
    ticker,
    instrument_type,
    'swing_trade',
    side,
    quantity,
    entry_price,
    strike_price,
    expiration_date,
    option_symbol,
    stop_loss,
    take_profit,
    240,
    current_price,
    # original_quantity removed ← REMOVED
    json.dumps({}),
```

---

## 🚀 Deploy Fix (5 Minutes)

```bash
# 1. Make the edits above to services/position_manager/db.py

# 2. Rebuild Docker image
cd services/position_manager
docker build --no-cache -t position-manager .

# 3. Tag for ECR
docker tag position-manager:latest \
  160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/position-manager:latest

# 4. Login to ECR
aws ecr get-login-password --region us-west-2 | \
  docker login --username AWS --password-stdin \
  160027201036.dkr.ecr.us-west-2.amazonaws.com

# 5. Push to ECR
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/position-manager:latest

# 6. Force ECS to deploy
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service position-manager-service \
  --force-new-deployment \
  --region us-west-2

# 7. Monitor deployment
aws logs tail /ecs/position-manager-service \
  --region us-west-2 \
  --since 2m \
  --follow
```

**Position Manager will start working in 2-3 minutes!**

---

## 🔍 Why This Works

**The Issue:**
- Code tries to use `original_quantity` column
- Column doesn't exist (migration 013 wasn't applied)
- INSERT fails → Position Manager crashes

**The Fix:**
- Remove `original_quantity` from INSERT
- Column was just being set to same value as `quantity` anyway
- Not needed for basic functionality
- Can add column properly later

**Impact:**
- ✅ Position Manager works immediately
- ✅ Can sync positions from Alpaca
- ✅ Stop loss, take profit work
- ⏸️ Advanced features (trailing stops) can add later

---

## 📋 Verification

**After deploying, check:**

```bash
# 1. Service should be running
aws ecs describe-services \
  --cluster ops-pipeline-cluster \
  --services position-manager-service \
  --region us-west-2 \
  --query 'services[0].{Running:runningCount,Desired:desiredCount}'

# 2. No errors in logs
aws logs tail /ecs/position-manager-service \
  --region us-west-2 \
  --since 5m

# 3. Should see "synced positions" messages
# Not "KeyError: 'original_quantity'" errors
```

---

## 🎯 Summary for Kiro

**Problem:** Missing database column (`original_quantity`)  
**Root Cause:** Migration 013 not applied  
**Quick Fix:** Remove column from code (3 lines)  
**Time:** 5 minutes  
**Result:** Position Manager works, can add columns later

**Just remove the 3 lines referencing `original_quantity` and redeploy!**
