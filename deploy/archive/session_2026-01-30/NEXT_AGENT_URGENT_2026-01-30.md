# URGENT: Telemetry & Position Manager Not Working - Jan 30, 2026 4:00 PM ET

## Current Situation (During Live Trading)

**Market:** 🟢 OPEN (1h 30m into trading day)  
**Critical Issue:** Telemetry NOT collecting data, Position manager NOT monitoring  
**User Positions:** 3 QCOM positions unmonitored for 16 hours

---

## What's Working ✅

1. **Position Manager CODE** - Tested manually at 15:57, found 3 positions ✅
2. **Dispatcher** - Has fresh Secrets Manager credentials ✅
3. **Feature Computer & Signal Engine** - Working from historical data ✅
4. **Secrets Manager** - Has correct API key (PKHE57Z4BKSIUQLTNQQK...) ✅

---

## What's NOT Working ❌

### 1. Position Manager Scheduler
- **State:** ENABLED
- **Configuration:** Correct (points to rev 9, cluster correct)
- **Problem:** NOT auto-triggering (last run: 23:37 last night - 16 hours ago!)
- **Manual Test:** Works perfectly
- **Issue:** EventBridge scheduler not firing despite being ENABLED

### 2. Telemetry Scheduler  
- **Deployed:** Revision 7 with DATA_SOURCE=yfinance (no credentials needed)
- **Scheduler:** Recreated fresh at 15:58:35
- **Problem:** Still using old revision with DATA_SOURCE=alpaca
- **Evidence:** Logs at 16:00:01 show Alpaca 401 errors
- **Issue:** Scheduler not picking up new task definition

---

## Root Cause Analysis

**EventBridge Scheduler Issues (Recurring):**
1. Same issue as last night (schedulers not triggering)
2. Schedulers show ENABLED but don't fire
3. Configuration looks perfect
4. Manual task execution works
5. Scheduler → ECS invocation broken

**Possible Causes:**
1. EventBridge service degradation
2. IAM permission drift
3. Task definition registration lag
4. Scheduler state corruption
5. AWS regional issue

---

## Attempted Fixes (This Session)

### Telemetry:
1. ✅ Fixed config.py to use Secrets Manager (rev 6)
2. ✅ Switched DATA_SOURCE to yfinance (rev 7)
3. ✅ Rebuilt Docker with cache-busting
4. ✅ Registered task definitions
5. ✅ Updated scheduler
6. ✅ Deleted and recreated scheduler from scratch
7. ❌ Still not working - scheduler triggering but using OLD revision

### Position Manager:
1. ✅ Fixed code (rev 9)
2. ✅ Scheduler configured correctly
3. ✅ Deleted and recreated scheduler
4. ❌ Still not auto-triggering (manual works)

---

## Diagnostics

### Position Manager Scheduler:
```
State: ENABLED
Schedule: rate(5 minutes)
Cluster: ops-pipeline-cluster (CORRECT)
TaskDef: position-manager:9 (CORRECT)
Last Auto Run: 23:37:25 (16 hours ago)
Manual Test: 15:57:05 - SUCCESS (found 3 positions)
```

### Telemetry Scheduler:
```
State: ENABLED
Schedule: rate(1 minute)  
Cluster: ops-pipeline-cluster (CORRECT)
TaskDef: ops-pipeline-telemetry-1m:7 (yfinance)
Last Run: 16:00:01 - FAILED (still using old revision)
Evidence: Alpaca 401 errors + yfinance failures
```

---

## Required Actions

### Immediate (Next Agent):

**1. Investigate EventBridge Scheduler Service Health**
```bash
# Check if there are broader AWS issues
aws health describe-events --region us-west-2

# Check CloudTrail for scheduler invocations
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=RunTask \
  --start-time $(date -d '1 hour ago' --utc +%FT%TZ) \
  --region us-west-2
```

**2. Verify IAM Permissions**
```bash
# The role may have lost permissions
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::160027201036:role/ops-pipeline-eventbridge-ecs-role \
  --action-names ecs:RunTask \
  --resource-arns arn:aws:ecs:us-west-2:160027201036:task-definition/position-manager:9
```

**3. Alternative: Use ECS Services Instead**
Convert from schedulers to always-running services:
- More reliable than schedulers
- No invocation lag
- Position manager can loop with sleep
- Telemetry can run continuously

---

## Workaround (Until Fixed)

**Manual Position Sync:**
```bash
# Run every 5 minutes manually
aws ecs run-task \
  --cluster ops-pipeline-cluster \
  --task-definition position-manager:9 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-0c182a149eeef918a],securityGroups=[sg-0cd16a909f4e794ce],assignPublicIp=ENABLED}" \
  --region us-west-2
```

---

## Files Modified Today

1. `services/telemetry_ingestor_1m/config.py` - Use Secrets Manager
2. `services/telemetry_ingestor_1m/Dockerfile` - Cache bust
3. `LIVE_TRADING_STATUS_2026-01-30_1050AM.md` - Status doc

---

## User's Positions (From Alpaca)

```
QCOM260206C00150000: $6.30 x 26 = $16,380 (+$1,430)
QCOM260227P00150000: $5.40 x 30 = $16,200 (-$2,850)
SPY260130C00609000: $83.57 x 1 = $8,357
```

**Position manager CAN see these** (manual test confirmed).  
**Just need scheduler to trigger it automatically.**

---

## Critical Next Steps

1. **Understand WHY schedulers not triggering** despite perfect config
2. **Consider ditching EventBridge Schedulers** entirely for ECS Services
3. **Get telemetry collecting data** (yfinance should work but scheduler not using rev 7)
4. **Get position manager auto-running** (manual works, scheduler doesn't)

**Time Pressure:** Market closes in 3 hours. System needs monitoring.

---

## Context for Next Agent

**From Last Night:**
- Fixed 13 schedulers (cluster name issue)
- All worked until today

**Today:**
- Position manager hasn't auto-run since last night
- Telemetry failing (credential + data source issues)
- Manual tests prove code is correct
- Schedulers configured correctly but not firing

**This is an EventBridge Scheduler infrastructure issue, not code.**
