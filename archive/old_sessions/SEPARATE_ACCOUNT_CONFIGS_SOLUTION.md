# 🎯 Separate Account Configs Solution

**Date:** February 3, 2026, 18:15 UTC  
**Status:** Ready to Deploy  
**Priority:** HIGH - Fixes tiny account not trading

---

## 📊 Problem Summary

### User Questions
1. **Why only BUY_CALL/BUY_PUT but not SELL_CALL/SELL_PUT?**
2. **Do we need 2 different configs for large vs tiny accounts?**

### Current Issues
1. **Both accounts using SAME config** - Large account limits applied to tiny account
2. **Tiny account can't trade** - Limits too high for $1,804 account
3. **Large account churning** - May be related to wrong limits

---

## 💡 Answers to User Questions

### 1. Why Only BUY Actions?

**The system only OPENS long positions, it doesn't sell premium (write options).**

| Action Type | What It Does | Risk Profile |
|-------------|--------------|--------------|
| **BUY_CALL** | Buy call option (long) | Limited risk (premium paid) |
| **BUY_PUT** | Buy put option (long) | Limited risk (premium paid) |
| **SELL_CALL** | Write/sell call option | Unlimited risk, requires margin |
| **SELL_PUT** | Write/sell put option | High risk, requires margin |

**Why only BUY?**
- ✅ Risk limited to premium paid
- ✅ No margin requirements
- ✅ No assignment risk
- ✅ Simpler position management
- ✅ Safer for automated trading

**To add SELL actions would require:**
- Margin calculations
- Assignment handling
- Much tighter risk controls
- Different position sizing logic
- More complex risk management

**Current Design:** Directional trading (buying options), not premium selling.

---

### 2. Do We Need Separate Configs?

**YES! Absolutely necessary.**

#### Current Problem
Both accounts reading **SAME** SSM parameter: `/ops-pipeline/dispatcher_config`

```json
{
  "max_notional_exposure": 10000,  // ❌ Too high for tiny account!
  "max_open_positions": 5,         // ❌ Too many for tiny account!
  "max_contracts_per_trade": 10    // ❌ Way too many for tiny account!
}
```

#### Why This Breaks Tiny Account

**Tiny Account Reality:**
- Buying power: $1,804
- Can afford: 1-2 contracts (~$850-$1,700 per trade)
- Should have: 2 max positions

**With Large Account Config:**
- Tries to open: 10 contracts ($8,500+)
- Result: **Can't afford any trades!**
- System: Wastes compute checking signals that can't execute

---

## 🏗️ Solution: Separate SSM Parameters

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SSM Parameter Store                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  /ops-pipeline/dispatcher_config_large                      │
│  ├─ max_notional_exposure: 10000                            │
│  ├─ max_open_positions: 5                                   │
│  ├─ max_contracts_per_trade: 10                             │
│  └─ max_daily_loss: 500                                     │
│                                                              │
│  /ops-pipeline/dispatcher_config_tiny                       │
│  ├─ max_notional_exposure: 1500                             │
│  ├─ max_open_positions: 2                                   │
│  ├─ max_contracts_per_trade: 2                              │
│  └─ max_daily_loss: 100                                     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                           │
                           │ Load based on ACCOUNT_TIER env var
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  services/dispatcher/config.py               │
│                                                              │
│  account_tier = os.environ.get('ACCOUNT_TIER', 'large')     │
│  config_name = f'/ops-pipeline/dispatcher_config_{tier}'    │
│  dispatcher_config = ssm.get_parameter(Name=config_name)    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                           │
                           │
        ┌──────────────────┴──────────────────┐
        ▼                                      ▼
┌──────────────────┐                  ┌──────────────────┐
│ dispatcher-      │                  │ dispatcher-tiny- │
│ service          │                  │ service          │
│                  │                  │                  │
│ ACCOUNT_TIER=    │                  │ ACCOUNT_TIER=    │
│ large            │                  │ tiny             │
└──────────────────┘                  └──────────────────┘
```

---

## 📋 Configuration Details

### Large Account Config
```json
{
  "account_tier": "large",
  "max_notional_exposure": 10000,      // ~5% of $209K
  "max_open_positions": 5,             // Diversification
  "max_contracts_per_trade": 10,       // $8K-$17K per trade
  "max_daily_loss": 500,               // 0.25% of capital
  "max_risk_per_trade_pct": 0.05,      // 5% risk per trade
  "ticker_cooldown_minutes": 15,
  "confidence_min_options_swing": 0.40,
  "confidence_min_options_daytrade": 0.60,
  "allowed_actions": ["BUY_CALL", "BUY_PUT"],
  "paper_ignore_buying_power": false
}
```

**Rationale:**
- Conservative 1% daily risk (professional level)
- Can handle 10 contracts ($8,500-$17,000 per trade)
- 5 positions for diversification
- $10K max exposure (~5% of capital)

### Tiny Account Config
```json
{
  "account_tier": "tiny",
  "max_notional_exposure": 1500,       // ~80% of $1,804
  "max_open_positions": 2,             // Can only afford 2
  "max_contracts_per_trade": 2,        // $850-$1,700 per trade
  "max_daily_loss": 100,               // 5.5% of capital
  "max_risk_per_trade_pct": 0.10,      // 10% risk (more aggressive)
  "ticker_cooldown_minutes": 15,
  "confidence_min_options_swing": 0.40,
  "confidence_min_options_daytrade": 0.60,
  "allowed_actions": ["BUY_CALL", "BUY_PUT"],
  "paper_ignore_buying_power": false
}
```

**Rationale:**
- More aggressive 10% risk per trade (growth mode)
- 1-2 contracts affordable ($850-$1,700 per trade)
- 2 positions max (can't afford more)
- $1,500 max exposure (~80% of capital)

---

## 🚀 Deployment Steps

### Prerequisites
- AWS credentials refreshed
- Docker running
- Access to ECR repository

### Step 1: Create SSM Parameters
```bash
./create_separate_account_configs.sh
```

**What it does:**
- Creates `/ops-pipeline/dispatcher_config_large`
- Creates `/ops-pipeline/dispatcher_config_tiny`
- Sets appropriate limits for each account

### Step 2: Deploy Updated Code
```bash
./deploy_separate_account_configs.sh
```

**What it does:**
1. Creates SSM parameters (calls Step 1)
2. Builds Docker image with updated config loader
3. Pushes to ECR with tag `separate-configs`
4. Registers new task definitions for both accounts
5. Updates both ECS services
6. Forces new deployment

**Expected Output:**
```
✅ Deployment Complete!

Summary:
  - SSM configs created: /ops-pipeline/dispatcher_config_large and _tiny
  - Docker image: separate-configs
  - Large account: revision XX
  - Tiny account: revision YY

Large Account Limits:
  - Max exposure: $10,000
  - Max positions: 5
  - Max contracts: 10
  - Max daily loss: $500

Tiny Account Limits:
  - Max exposure: $1,500
  - Max positions: 2
  - Max contracts: 2
  - Max daily loss: $100
```

---

## ✅ Verification

### Check Logs
```bash
# Large account
aws logs tail /ecs/ops-pipeline/dispatcher --follow --filter-pattern "large"

# Tiny account
aws logs tail /ecs/ops-pipeline/dispatcher --follow --filter-pattern "tiny"
```

### Expected Log Output

**Large Account:**
```
Connected to Alpaca Paper Trading
  Account Name: large
  Account Tier: large
  Buying power: $209,234.50
  Risk Limits:
    - Max contracts: 10
    - Risk % (day): 1.0%
    - Risk % (swing): 2.0%
Loaded tier-specific config: /ops-pipeline/dispatcher_config_large
```

**Tiny Account:**
```
Connected to Alpaca Paper Trading
  Account Name: tiny
  Account Tier: tiny
  Buying power: $1,804.00
  Risk Limits:
    - Max contracts: 2
    - Risk % (day): 15.0%
    - Risk % (swing): 8.0%
Loaded tier-specific config: /ops-pipeline/dispatcher_config_tiny
```

---

## 📊 Expected Behavior After Deployment

### Large Account
- ✅ Continues trading with $10K limit
- ✅ Max 5 positions
- ✅ Max 10 contracts per trade
- ✅ Stops at $500 daily loss

### Tiny Account
- ✅ **STARTS TRADING** (was blocked before)
- ✅ Opens 1-2 contract positions
- ✅ Max 2 positions
- ✅ Stays within $1,500 exposure
- ✅ Stops at $100 daily loss

---

## 🎯 Impact Summary

### Before Fix
| Account | Status | Problem |
|---------|--------|---------|
| Large | ✅ Trading | Using correct limits |
| Tiny | ❌ Not trading | Limits too high, can't afford trades |

### After Fix
| Account | Status | Improvement |
|---------|--------|-------------|
| Large | ✅ Trading | Same limits, explicit config |
| Tiny | ✅ Trading | **Can now afford trades!** |

---

## 🔍 Code Changes

### Modified Files
1. **services/dispatcher/config.py**
   - Updated to load tier-specific SSM parameter
   - Falls back to default config if tier-specific not found
   - Maintains backward compatibility

### New Files
1. **create_separate_account_configs.sh**
   - Creates both SSM parameters
   - Sets appropriate limits for each account

2. **deploy_separate_account_configs.sh**
   - End-to-end deployment script
   - Builds, pushes, registers, updates services

3. **SEPARATE_ACCOUNT_CONFIGS_SOLUTION.md**
   - This document

---

## 🚨 Rollback Plan

If deployment causes issues:

### Rollback Services
```bash
# Large account - revert to previous revision
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service dispatcher-service \
  --task-definition ops-pipeline-dispatcher:33 \
  --region us-west-2

# Tiny account - revert to previous revision
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service dispatcher-tiny-service \
  --task-definition ops-pipeline-dispatcher-tiny:13 \
  --region us-west-2
```

### Restore Old Config
```bash
# Both accounts will fall back to /ops-pipeline/dispatcher_config
# No action needed - backward compatible
```

---

## 📝 Next Steps After Deployment

### Immediate (Next 1 Hour)
1. ✅ Monitor logs for correct config loading
2. ✅ Verify tiny account starts trading
3. ✅ Check position counts show actual values
4. ✅ Confirm limits are enforced correctly

### Short Term (Next 24 Hours)
1. Verify tiny account opens 1-2 contract positions
2. Confirm large account respects $10K limit
3. Check that both accounts operate independently
4. Monitor for any unexpected behavior

### Medium Term (Next Week)
1. Analyze tiny account performance
2. Adjust limits if needed (via SSM parameter update)
3. Consider adding more account tiers (small, medium)
4. Document lessons learned

---

## 🎊 Success Criteria

- ✅ Large account continues trading normally
- ✅ Tiny account starts opening positions
- ✅ Each account respects its own limits
- ✅ No cross-account interference
- ✅ Position counts show actual values
- ✅ Risk gates work correctly for both accounts

---

## 📞 Support

### If Tiny Account Still Not Trading
1. Check Signal Engine logs for recommendations
2. Verify confidence thresholds not too high
3. Check if market conditions suitable
4. Review Position Manager for any blocks

### If Large Account Behaves Differently
1. Verify config loaded correctly (check logs)
2. Compare limits before/after deployment
3. Check if any positions were closed
4. Review risk gate evaluations

### If Both Accounts Have Issues
1. Check SSM parameters created correctly
2. Verify Docker image built with new code
3. Check task definitions have correct image
4. Review service update status

---

**Ready to deploy!** Run `./deploy_separate_account_configs.sh` when ready.
