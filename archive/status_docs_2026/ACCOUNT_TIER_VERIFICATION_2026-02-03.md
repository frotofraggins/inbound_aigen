# Account Tier Risk Parameter Verification

**Date:** February 3, 2026 18:00 UTC  
**Status:** ⚠️ ISSUES FOUND - Fixes Required

---

## 🔍 Verification Summary

I've reviewed the entire account tier system to ensure both accounts (large and tiny) are using their correct risk parameters and spending limits.

### ✅ What's Working Correctly

1. **Account Tier Configuration System (`config.py`)**
   - ✅ Loads `ACCOUNT_TIER` from environment variable
   - ✅ Retrieves tier-specific Alpaca credentials from Secrets Manager
   - ✅ Loads tier-specific risk parameters from `ACCOUNT_TIERS` dictionary
   - ✅ Passes complete `account_tier_config` to broker

2. **Risk Parameters Defined Correctly**
   ```python
   ACCOUNT_TIERS = {
       'tiny': {
           'max_size': 2000,
           'risk_pct_day': 0.15,      # 15% - aggressive for small accounts
           'risk_pct_swing': 0.08,    # 8%
           'max_contracts': 1,         # Only 1 contract at a time
           'min_confidence': 0.45,
           'min_volume_ratio': 2.0
       },
       'large': {
           'max_size': 999999999,
           'risk_pct_day': 0.01,      # 1% - professional
           'risk_pct_swing': 0.02,    # 2%
           'max_contracts': 10,        # Up to 10 contracts
           'min_confidence': 0.45,
           'min_volume_ratio': 1.2
       }
   }
   ```

3. **Broker Position Sizing (`broker.py`)**
   - ✅ Uses `account_tier_config` for position sizing
   - ✅ Respects `max_contracts` limit from tier
   - ✅ Uses buying power from Alpaca account
   - ✅ Applies Kelly Criterion when enough trade history exists

4. **Multi-Account Credentials**
   - ✅ Tiny account: `ops-pipeline/alpaca/tiny` secret
   - ✅ Large account: `ops-pipeline/alpaca/large` secret (or default)

---

## ⚠️ Issues Found

### 1. CRITICAL: Tiny Account RUN_MODE Typo

**Problem:** Tiny account task definition has `MODE=LOOP` instead of `RUN_MODE=LOOP`

**File:** `deploy/dispatcher-task-definition-tiny-service.json`

**Current (WRONG):**
```json
"environment": [
  {"name": "AWS_REGION", "value": "us-west-2"},
  {"name": "EXECUTION_MODE", "value": "ALPACA_PAPER"},
  {"name": "ACCOUNT_TIER", "value": "tiny"},
  {"name": "MODE", "value": "LOOP"}  // ❌ WRONG - should be RUN_MODE
]
```

**Should Be:**
```json
"environment": [
  {"name": "AWS_REGION", "value": "us-west-2"},
  {"name": "EXECUTION_MODE", "value": "ALPACA_PAPER"},
  {"name": "ACCOUNT_TIER", "value": "tiny"},
  {"name": "RUN_MODE", "value": "LOOP"}  // ✅ CORRECT
]
```

**Impact:** Tiny account dispatcher runs ONCE then exits, instead of running continuously in loop mode. This means it only processes recommendations when manually triggered, not every 60 seconds like it should.

---

### 2. MEDIUM: Large Account Missing Explicit ACCOUNT_TIER

**Problem:** Large account task definition doesn't explicitly set `ACCOUNT_TIER`

**File:** `deploy/dispatcher-task-definition.json`

**Current:**
```json
"environment": [
  {"name": "AWS_REGION", "value": "us-west-2"},
  {"name": "EXECUTION_MODE", "value": "ALPACA_PAPER"},
  {"name": "RUN_MODE", "value": "LOOP"}
  // Missing: ACCOUNT_TIER
]
```

**Should Be:**
```json
"environment": [
  {"name": "AWS_REGION", "value": "us-west-2"},
  {"name": "EXECUTION_MODE", "value": "ALPACA_PAPER"},
  {"name": "ACCOUNT_TIER", "value": "large"},  // ✅ Explicit
  {"name": "RUN_MODE", "value": "LOOP"}
]
```

**Impact:** Currently defaults to 'large' (correct behavior), but implicit. Better to be explicit for clarity and maintainability.

---

### 3. LOW: Missing Account Logging in Broker

**Problem:** Broker doesn't log which account it's managing at startup

**File:** `services/dispatcher/alpaca_broker/broker.py`

**Current:**
```python
def _verify_connection(self):
    """Verify we can connect to Alpaca"""
    # ... connection code ...
    print(f"Connected to Alpaca Paper Trading")
    print(f"  Account: {account['account_number']}")
    print(f"  Buying power: ${float(account['buying_power']):.2f}")
```

**Should Include:**
```python
def _verify_connection(self):
    """Verify we can connect to Alpaca"""
    # ... connection code ...
    account_name = self.config.get('account_name', 'unknown')
    account_tier = self.config.get('account_tier', 'unknown')
    tier_config = self.config.get('account_tier_config', {})
    
    print(f"Connected to Alpaca Paper Trading")
    print(f"  Account Name: {account_name}")
    print(f"  Account Tier: {account_tier}")
    print(f"  Account Number: {account['account_number']}")
    print(f"  Buying power: ${float(account['buying_power']):.2f}")
    print(f"  Risk Limits:")
    print(f"    - Max contracts: {tier_config.get('max_contracts', 'N/A')}")
    print(f"    - Risk % (day): {tier_config.get('risk_pct_day', 'N/A') * 100}%")
    print(f"    - Risk % (swing): {tier_config.get('risk_pct_swing', 'N/A') * 100}%")
```

**Impact:** Makes it harder to verify correct account and risk limits are being used. Not critical, but helpful for debugging.

---

## 🔧 Required Fixes

### Fix 1: Correct Tiny Account RUN_MODE (CRITICAL)

```bash
# Update task definition
# File: deploy/dispatcher-task-definition-tiny-service.json
# Change: "MODE" → "RUN_MODE"

# Then register and deploy
aws ecs register-task-definition \
  --cli-input-json file://deploy/dispatcher-task-definition-tiny-service.json \
  --region us-west-2

aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service dispatcher-tiny-service \
  --task-definition ops-pipeline-dispatcher-tiny-service:13 \
  --force-new-deployment \
  --region us-west-2
```

### Fix 2: Add Explicit ACCOUNT_TIER to Large Account (RECOMMENDED)

```bash
# Update task definition
# File: deploy/dispatcher-task-definition.json
# Add: {"name": "ACCOUNT_TIER", "value": "large"}

# Then register and deploy
aws ecs register-task-definition \
  --cli-input-json file://deploy/dispatcher-task-definition.json \
  --region us-west-2

aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service dispatcher-service \
  --task-definition ops-pipeline-dispatcher:33 \
  --force-new-deployment \
  --region us-west-2
```

### Fix 3: Add Account Logging to Broker (OPTIONAL)

Update `services/dispatcher/alpaca_broker/broker.py` `_verify_connection()` method to log account tier and risk limits.

---

## 📊 Risk Parameter Comparison

| Parameter | Tiny Account | Large Account | Difference |
|-----------|--------------|---------------|------------|
| **Risk % (Day)** | 15% | 1% | 15x more aggressive |
| **Risk % (Swing)** | 8% | 2% | 4x more aggressive |
| **Max Contracts** | 1 | 10 | 10x more capacity |
| **Min Confidence** | 0.45 | 0.45 | Same threshold |
| **Min Volume Ratio** | 2.0x | 1.2x | Tiny needs more confirmation |
| **Buying Power** | ~$1,500 | ~$209,000 | 139x difference |

**Key Insight:** Tiny account is configured for aggressive growth (15% risk) with strict limits (1 contract max), while large account is conservative (1% risk) with higher capacity (10 contracts max).

---

## ✅ Verification Checklist

After applying fixes, verify:

- [ ] Tiny account logs show `ACCOUNT_TIER=tiny`
- [ ] Large account logs show `ACCOUNT_TIER=large`
- [ ] Tiny account runs in LOOP mode (every 60 seconds)
- [ ] Large account runs in LOOP mode (every 60 seconds)
- [ ] Tiny account respects 1 contract max
- [ ] Large account can open up to 10 contracts
- [ ] Tiny account uses 15% risk per day
- [ ] Large account uses 1% risk per day
- [ ] Both accounts connect to correct Alpaca credentials
- [ ] Position sizing reflects tier-specific limits

---

## 🎯 Expected Behavior After Fixes

### Tiny Account
- Runs continuously (every 60 seconds)
- Uses tiny-specific Alpaca credentials
- Limits to 1 contract per trade
- Risks up to 15% of buying power per day (~$225 max risk)
- Requires 2.0x volume surge for confirmation

### Large Account
- Runs continuously (every 60 seconds)
- Uses large-specific Alpaca credentials
- Can open up to 10 contracts per trade
- Risks up to 1% of buying power per day (~$2,092 max risk)
- Requires 1.2x volume surge for confirmation

---

## 📝 Next Steps

1. **Apply Fix 1 (CRITICAL):** Correct tiny account RUN_MODE typo
2. **Apply Fix 2 (RECOMMENDED):** Add explicit ACCOUNT_TIER to large account
3. **Apply Fix 3 (OPTIONAL):** Add account logging to broker
4. **Verify:** Check logs for both accounts after deployment
5. **Monitor:** Watch for trades to confirm correct risk limits are applied

---

**Status:** Ready to apply fixes. All issues identified and solutions provided.
