# Deployment Verification Plan - February 4, 2026

## 🚀 Current Deployment Status

All three services deploying:
- position-manager-service: IN_PROGRESS
- dispatcher-service: IN_PROGRESS
- dispatcher-tiny-service: IN_PROGRESS

**Started:** 9:20 AM Arizona Time  
**Expected Complete:** ~9:23 AM Arizona Time

---

## ✅ What Was Deployed

### 1. Position Manager (2 fixes)
- **Check interval:** 5 minutes → 1 minute (catches positions faster)
- **Exit logic:** -25%/+50% → -40%/+80% (wider stops for options)
- **Min hold:** 30 minutes added (no premature exits)
- **Duplicate checks:** Removed (options only check once)

### 2. Dispatcher (1 critical fix)
- **Alpaca brackets:** Disabled (was closing positions in 4 minutes)
- **Our control:** Position manager now handles all exits

### 3. Tiny Dispatcher
- Same fixes as main dispatcher

---

## 🧪 Verification Steps (After Deployment Completes)

### Step 1: Verify Services Are Running
```bash
aws ecs describe-services --cluster ops-pipeline-cluster \
  --services position-manager-service dispatcher-service dispatcher-tiny-service \
  --region us-west-2 \
  --query 'services[].{name:serviceName,status:deployments[0].rolloutState}' \
  --output table
```

**Expected:** All show "COMPLETED"

### Step 2: Check Position Manager Logs
```bash
aws logs tail /ecs/ops-pipeline/position-manager --since 2m --region us-west-2 | head -30
```

**Look for:**
- "Running in LOOP mode"
- "Will check positions every 1 minute" (NOT 5 minutes)
- "Managing positions for account: large"

### Step 3: Check Dispatcher Logs
```bash
aws logs tail /ecs/ops-pipeline/dispatcher --since 2m --region us-west-2 | head -30
```

**Look for:**
- "Connected to Alpaca Paper Trading"
- Account information
- "order_class": "simple" (NOT "bracket")

### Step 4: Wait for Next Position to Open
```bash
# Monitor for new executions
aws logs tail /ecs/ops-pipeline/dispatcher --follow --region us-west-2 | grep "execution_executed"
```

**When you see a new execution:**
- Note the ticker and time
- Proceed to Step 5

### Step 5: Verify Position is Tracked
Within 1-2 minutes of execution:
```bash
python3 << 'EOF'
import boto3, json
client = boto3.client('lambda', region_name='us-west-2')
response = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({
        'sql': """
        SELECT id, ticker, option_symbol, entry_time, status,
               EXTRACT(EPOCH FROM (NOW() - entry_time))/60 as hold_minutes
        FROM active_positions 
        WHERE status = 'open'
        AND entry_time > NOW() - INTERVAL '10 minutes'
        """
    })
)
result = json.loads(json.load(response['Payload'])['body'])
for row in result['rows']:
    print(f"{row['ticker']}: {row['hold_minutes']:.1f} min, {row['status']}")
EOF
```

**Expected:** Position appears in database within 1 minute

### Step 6: Monitor Hold Time
Use the monitoring script:
```bash
python3 scripts/monitor_exit_fix.py
```

**Watch for:**
- Hold time increasing: 1 min, 2 min, 5 min, 10 min...
- "Too early to exit" messages in first 30 minutes
- Position still open after 30 minutes
- Exit only at -40% or +80% (not -25%/+50%)

---

## ✅ Success Criteria

### Immediate (First 5 Minutes After Deployment)
- [x] All services show "COMPLETED" rollout
- [ ] Position manager logs show "every 1 minute"
- [ ] Dispatcher logs show "simple" order class (not "bracket")
- [ ] Services are stable (no crash loops)

### Short Term (Next Position Opens)
- [ ] Position appears in active_positions table within 1 minute
- [ ] Position manager logs show it's monitoring the position
- [ ] Hold time starts incrementing (1 min, 2 min, 3 min...)

### Medium Term (30-60 Minutes)
- [ ] Position holds for at least 30 minutes
- [ ] "Too early to exit" log messages in first 30 minutes
- [ ] No premature exits at -25% or +50%
- [ ] Position tracked in database throughout

### Long Term (4-24 Hours)
- [ ] Positions close at -40% or +80% (not sooner)
- [ ] Average hold time >30 minutes
- [ ] Position history shows proper exit reasons
- [ ] Win rate improves (target 40-50%)

---

## 🚨 Troubleshooting

### If Position Still Closes in 4 Minutes
**Check:**
1. Are Alpaca brackets still being set?
   ```bash
   aws logs tail /ecs/ops-pipeline/dispatcher --since 5m --region us-west-2 | grep bracket
   ```
   Should see: NOTHING (brackets disabled)

2. Is old dispatcher still running?
   ```bash
   aws ecs describe-services --cluster ops-pipeline-cluster --service dispatcher-service --region us-west-2 --query 'services[0].deployments[0].rolloutState'
   ```
   Should see: "COMPLETED"

### If Position Not Tracked in Database
**Check:**
1. Is position manager running with 1-min interval?
   ```bash
   aws logs tail /ecs/ops-pipeline/position-manager --since 5m --region us-west-2 | grep "Sleeping for"
   ```
   Should see: "Sleeping for 1 minute"

2. Did position manager sync from Alpaca?
   ```bash
   aws logs tail /ecs/ops-pipeline/position-manager --since 5m --region us-west-2 | grep "Synced from Alpaca"
   ```

### If Position Closes Too Early (< 30 Minutes)
**Check logs for exit reason:**
```bash
aws logs tail /ecs/ops-pipeline/position-manager --since 30m --region us-west-2 | grep "EXIT TRIGGERED"
```

Should show:
- "option_stop_loss" at -40% (not -25%)
- "option_profit_target" at +80% (not +50%)
- "Too early to exit" if < 30 minutes

---

## 📊 Monitoring Dashboard

### Quick Status Check
```bash
# Service health
aws ecs describe-services --cluster ops-pipeline-cluster \
  --services position-manager-service dispatcher-service \
  --region us-west-2 \
  --query 'services[].{name:serviceName,running:runningCount,desired:desiredCount}' \
  --output table

# Current positions
python3 << 'EOF'
import boto3, json
client = boto3.client('lambda', region_name='us-west-2')
response = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'sql': 'SELECT COUNT(*) as open_positions FROM active_positions WHERE status = \'open\''})
)
result = json.loads(json.load(response['Payload'])['body'])
print(f"Open positions: {result['rows'][0]['open_positions']}")
EOF
```

---

## 📞 Expected Timeline

**9:23 AM:** All deployments complete  
**9:25 AM:** Services stable and running with new code  
**9:30 AM:** Next position opens (signal engine runs every 1 min)  
**9:31 AM:** Position tracked in database (position manager checks every 1 min)  
**10:00 AM:** Position still open (30-min minimum hold working)  
**10:30+ AM:** Position closes at real exit condition (-40% or +80%)

---

## 🎯 Final Checklist

Before considering fix complete:
- [ ] All services deployed successfully
- [ ] Position manager checking every 1 minute
- [ ] Dispatcher not setting Alpaca brackets
- [ ] Next position opens and is tracked
- [ ] Position holds >= 30 minutes
- [ ] Exit occurs at -40% or +80% (not -25%/+50%)
- [ ] Position data saved to position_history

---

**Status:** Deployments in progress, verification pending
