# CRITICAL: Tiny Account Has No Position Manager!

## 🚨 Discovery

There is only **ONE** position manager service:
- Service name: `position-manager-service`
- Account: `ACCOUNT_NAME=large` (from task definition)
- Monitoring: Large account only

**But you have TWO dispatcher services:**
- `dispatcher-service` (large account)
- `dispatcher-tiny-service` (tiny account)

**Result:** Tiny account opens positions that are NEVER monitored!

---

## 🔍 Evidence

### From Alpaca (What You Saw)
```
BMY260220C00057500: 10 contracts (TINY account signature)
WMT260213C00130000: 10 contracts (TINY account signature)
```

### From Large Dispatcher Logs
```
BMY: qty 436 shares (STOCK execution, large account)
WMT: qty 195 shares (STOCK execution, large account)
```

### The Mismatch
The OPTIONS you're seeing in Alpaca (10 contracts each) are from **TINY account**, not large!

Large account executed stocks, tiny executed options.

---

## 🎯 Solutions

### Option 1: Create Second Position Manager (Recommended)
Deploy a separate `position-manager-tiny-service` that:
- Monitors tiny account Alpaca credentials
- Uses `ACCOUNT_NAME=tiny` environment variable
- Checks every 1 minute like the large one

### Option 2: Make Single Position Manager Handle Both
Modify position manager to:
- Connect to BOTH Alpaca accounts
- Monitor positions from both
- Track account_name in database

---

## 🚀 Quick Fix (Option 1)

Since we already have a working position manager, just deploy a second instance:

```bash
# services/position_manager is already built and in ECR

# Just need to create a new ECS service with tiny account config
# Copy position-manager-service task definition
# Change environment variable: ACCOUNT_NAME=tiny
# Point to tiny Alpaca secret: ops-pipeline/alpaca/tiny
# Create new service: position-manager-tiny-service
```

This is the cleanest solution - mirrors the dispatcher pattern.

---

## 📝 Current Architecture (Incomplete)

```
LARGE ACCOUNT:
✅ dispatcher-service → Opens positions
✅ position-manager-service → Monitors positions
✅ Works correctly

TINY ACCOUNT:
✅ dispatcher-tiny-service → Opens positions
❌ NO POSITION MANAGER → Positions never monitored!
❌ Alpaca brackets close them (no protection)
```

---

## 🎯 Target Architecture

```
LARGE ACCOUNT:
✅ dispatcher-service
✅ position-manager-service

TINY ACCOUNT:
✅ dispatcher-tiny-service
✅ position-manager-tiny-service (NEED TO CREATE)
```

---

## 💡 Why This Wasn't Obvious

1. **Tiny account rarely trades** (stricter confidence threshold)
2. **Position manager was checking every 5 min** (missed everything)
3. **No database tracking** (positions closed before sync)
4. **Assumed one position manager** could handle both accounts

---

## 🚀 Action Required

**Deploy position-manager-tiny-service:**
```bash
# The Docker image is already in ECR from our deployment
# Just need to:
# 1. Create task definition with ACCOUNT_NAME=tiny
# 2. Point to ops-pipeline/alpaca/tiny secret
# 3. Create ECS service

# OR use the same image with environment override
```

**Quick deploy:**
```bash
aws ecs create-service \
  --cluster ops-pipeline-cluster \
  --service-name position-manager-tiny-service \
  --task-definition position-manager-service:9 \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-0c182a149eeef918a],securityGroups=[sg-0cd16a909f4e794ce],assignPublicIp=ENABLED}" \
  --region us-west-2
  # Plus environment override for ACCOUNT_NAME=tiny
```

---

## 📞 Summary

**Problem:** Only large account has position manager, tiny account positions are unmonitored

**Impact:** 
- Tiny account positions close via Alpaca brackets (4 minutes)
- Never tracked in database
- Exit fix can't help

**Solution:** Deploy `position-manager-tiny-service` with same code, tiny account config

**Status:** Need to create and deploy tiny position manager service
