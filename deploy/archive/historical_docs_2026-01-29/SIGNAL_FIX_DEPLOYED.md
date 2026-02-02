# Signal Engine Fix Deployed

**Date:** 2026-01-27 14:44 UTC  
**Deployment Duration:** 12 minutes  
**Status:** ✅ COMPLETE

---

## What Was Deployed

### The Problem
- NVDA showed 8.63x volume surge with +0.91 sentiment
- Signal engine rejected trade because price was $186.86 (18 cents below SMA20 at $187.20)
- Logic required strictly **above** SMA20, blocking valid support trades

### The Fix
- Applied ±0.5% tolerance to SMA20 requirement
- Now allows trades AT support/resistance zones
- File: `services/signal_engine_1m/rules.py`
- Logic: `near_or_above_sma20 = close >= sma20 * 0.995`

### Technical Details
- **Docker Image:** `160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/signal-engine-1m`
- **Image Digest:** `sha256:bf438a3f2ef507cae9e67134e07159ab54ea4bf81f0a304f07b8eeef0bfdcb3d`
- **Task Definition:** `ops-pipeline-signal-engine-1m:7`
- **Scheduler:** `ops-pipeline-signal-engine-1m` (runs every 1 minute)
- **Deployment Time:** 2:44 PM UTC

---

## Deployment Steps Completed

1. ✅ Built Docker image with updated rules.py
2. ✅ Pushed to ECR (digest: bf438a3f...)
3. ✅ Updated task definition JSON with new digest
4. ✅ Registered task definition revision 7
5. ✅ Updated EventBridge scheduler to use revision 7
6. ✅ Verified scheduler configuration

---

## Expected Impact

### Immediate Changes
- Next signal engine run (within 1 minute) will use new code
- NVDA and similar setups at SMA20 ±0.5% will now qualify
- Should see first signals generated within 30 minutes

### What to Monitor
```bash
# Check for signals generated
aws logs tail /ecs/ops-pipeline/signal-engine-1m --region us-west-2 --follow

# Query dispatch_recommendations table
python3 scripts/verify_all_phases.py

# Check for trades executed
# (Dispatcher runs every 1 minute and will pick up signals)
```

### Success Criteria
- [ ] Signals appear in dispatch_recommendations table
- [ ] Dispatcher executes trades
- [ ] Position Manager tracks positions
- [ ] First trade documented

---

## Configuration Reference

### SMA Tolerance Parameter
```python
# services/signal_engine_1m/rules.py
SMA_TOLERANCE = 0.005  # ±0.5% from SMA20

# For NVDA example:
# SMA20 = $187.20
# Min price = $187.20 * 0.995 = $186.26
# Current price = $186.86 ✅ NOW QUALIFIES
```

### All Trading Parameters
See: `config/trading_params.json`
- sentiment_threshold: 0.50
- sma_tolerance: 0.005 (±0.5%)
- confidence_min: 0.55
- volume_min: 2.0x

---

## Rollback Plan

If issues arise, rollback to revision 6:

```bash
aws scheduler update-schedule \
  --name ops-pipeline-signal-engine-1m \
  --region us-west-2 \
  --schedule-expression "rate(1 minute)" \
  --flexible-time-window Mode=OFF \
  --target '{
    "Arn": "arn:aws:ecs:us-west-2:160027201036:cluster/ops-pipeline-cluster",
    "RoleArn": "arn:aws:iam::160027201036:role/ops-pipeline-eventbridge-ecs-role",
    "EcsParameters": {
      "TaskDefinitionArn": "arn:aws:ecs:us-west-2:160027201036:task-definition/ops-pipeline-signal-engine-1m:6",
      "LaunchType": "FARGATE",
      "NetworkConfiguration": {
        "awsvpcConfiguration": {
          "Subnets": ["subnet-0c182a149eeef918a"],
          "SecurityGroups": ["sg-0cd16a909f4e794ce"],
          "AssignPublicIp": "ENABLED"
        }
      }
    }
  }'
```

---

## Next Steps

1. **Monitor (10-30 min):** Watch CloudWatch logs for signals
2. **Verify (30-60 min):** Check dispatch_recommendations table
3. **Validate (1-2 hours):** Confirm trades executed
4. **Document:** Record first successful trade

---

## Notes

- This fix enables trading at support/resistance zones
- Conservative approach: only ±0.5% tolerance (not aggressive)
- Volume requirement (2.0x) and confidence (0.55) still enforced
- Sentiment threshold (0.50) still conservative for options

**The trading system is now one signal generation away from going live!**
