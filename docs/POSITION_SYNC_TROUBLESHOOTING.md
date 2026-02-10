# Position Sync Troubleshooting Guide
**Created:** February 7, 2026  
**Purpose:** Diagnose and resolve position synchronization issues

---

## 🎯 Overview

This guide helps resolve issues where the database and Alpaca accounts have mismatched positions, causing monitoring failures and inaccurate risk calculations.

---

## 🚨 Common Symptoms

### Symptom 1: "Position not found" errors
```
ERROR - Error closing position CRM260213C00200000: 
{"code":40410000,"message":"position not found: CRM260213C00200000"}
```

**Cause:** Phantom position - exists in database but not in Alpaca  
**Impact:** Stop-loss/take-profit monitoring fails for this position  
**Solution:** Run position reconciliation service (see below)

---

### Symptom 2: Position monitoring shows errors
```
Positions with errors: 1
⚠ Some positions encountered errors - check logs above
```

**Cause:** Usually related to phantom positions  
**Impact:** Position not being monitored correctly  
**Solution:** Check logs for specific error, run reconciliation

---

### Symptom 3: Missing positions in database
**Symptom:** Alpaca shows open position, database doesn't  
**Cause:** Position opened manually or sync failure  
**Impact:** Position not being monitored at all  
**Solution:** Reconciliation will auto-create database entry

---

## 🔧 Diagnostic Steps

### Step 1: Identify the Issue

**Check position manager logs:**
```bash
aws logs tail /ecs/ops-pipeline/position-manager-service \
  --region us-west-2 --since 10m | grep -i error
```

Look for:
- "position not found" errors → Phantom position
- Multiple errors for same position → Sync issue
- Errors during close attempt → Position already closed

---

### Step 2: Compare Database vs Alpaca

**Query database positions:**
```python
python3 -c "
import boto3, json
client = boto3.client('lambda', region_name='us-west-2')
response = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({
        'sql': 'SELECT id, ticker, option_symbol, status, account_name FROM active_positions WHERE status = \"open\" ORDER BY account_name, id'
    })
)
result = json.loads(response['Payload'].read())
print(json.dumps(json.loads(result['body']), indent=2))
"
```

**Check Alpaca positions manually:**
- Large account: https://app.alpaca.markets/paper/dashboard/overview
- Tiny account: (use separate paper account dashboard)

**Compare the lists - positions should match exactly.**

---

### Step 3: Determine Root Cause

| Database | Alpaca | Issue Type | Action |
|----------|--------|------------|--------|
| Has position | No position | Phantom | Reconcile (close in DB) |
| No position | Has position | Missing | Reconcile (add to DB) |
| Different price | Different price | Out of sync | Reconcile (update price) |
| Position exists | Position exists | Match | No action needed |

---

## 🔨 Resolution Methods

### Method 1: Automated Reconciliation (Recommended)

The position reconciliation service automatically fixes sync issues every 5 minutes.

**Deploy reconciliation service:**
```bash
cd /home/nflos/workplace/inbound_aigen
chmod +x scripts/deploy_position_reconciler.sh
./scripts/deploy_position_reconciler.sh
```

**What it does:**
1. Compares database positions with Alpaca positions
2. Marks phantom positions as "closed" in database
3. Creates database entries for missing positions
4. Syncs prices for matched positions
5. Logs all actions for audit trail

**Verify it's running:**
```bash
# Check schedule
aws scheduler get-schedule \
  --name ops-pipeline-position-reconciler-5m \
  --region us-west-2

# View logs
aws logs tail /ecs/ops-pipeline/position-reconciler \
  --region us-west-2 --follow
```

**Expected output:**
```
Starting reconciliation for large account
Found 3 open positions in database for large
Found 3 open positions in Alpaca for large
Checked: 3, Phantoms: 0, Missing: 0, Synced: 0
```

---

### Method 2: Manual Reconciliation (Emergency)

**For phantom positions (in DB but not Alpaca):**

```python
# Close phantom position in database
import boto3, json
from datetime import datetime, timezone

client = boto3.client('lambda', region_name='us-west-2')

# Replace with actual position ID
position_id = 2566

response = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({
        'sql': f'''
            UPDATE active_positions 
            SET status = 'closed',
                closed_at = '{datetime.now(timezone.utc).isoformat()}',
                close_reason = 'manual_reconciliation'
            WHERE id = {position_id}
        '''
    })
)
print(json.loads(response['Payload'].read()))
```

**For missing positions (in Alpaca but not DB):**

Use the reconciliation service - manual creation is complex and error-prone.

---

### Method 3: Prevention (Enhanced Error Handling)

The position manager has been enhanced to handle "position not found" gracefully:

1. Before attempting close, verify position exists in Alpaca
2. If not found, mark as closed in database automatically
3. Log for audit trail
4. Continue monitoring other positions

This prevents the error from recurring.

---

## 📊 Monitoring Reconciliation

### Check reconciliation metrics

```bash
# View last 5 reconciliation runs
aws logs tail /ecs/ops-pipeline/position-reconciler \
  --region us-west-2 --since 30m | grep "SUMMARY" -A 10
```

**Healthy output:**
```
RECONCILIATION SUMMARY
LARGE Account:
  Positions checked: 3
  Phantoms resolved: 0
  Missing positions added: 0
  Prices synced: 0
TINY Account:
  Positions checked: 0
  Phantoms resolved: 0
  Missing positions added: 0
  Prices synced: 0
```

**Unhealthy output:**
```
Phantoms resolved: 1  ← Position was in DB but not Alpaca
Missing positions added: 1  ← Position was in Alpaca but not DB
```

---

## 🎯 Success Criteria

✅ **System is healthy when:**
- Position manager error rate = 0%
- Database position count = Alpaca position count (per account)
- All positions have matching prices (within 1%)
- Reconciliation finds 0 phantoms and 0 missing positions
- Position manager logs show "✓ All positions processed successfully"

---

## 🔍 Advanced Diagnostics

### Find positions causing errors

```bash
# Get position IDs with errors from logs
aws logs filter-pattern /ecs/ops-pipeline/position-manager-service \
  --region us-west-2 \
  --start-time $(date -d '1 hour ago' +%s)000 \
  --filter-pattern "[time, service, level=ERROR*, ...]" \
  | grep "position not found" | grep -oP 'position \K\d+'
```

### Check position history

```python
# See when position was opened/closed
import boto3, json
client = boto3.client('lambda', region_name='us-west-2')

position_id = 2566  # Replace with actual ID

response = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({
        'sql': f'''
            SELECT id, ticker, option_symbol, status, entry_time, closed_at, close_reason
            FROM active_positions 
            WHERE id = {position_id}
        '''
    })
)
print(json.loads(response['Payload'].read()))
```

### Verify account configuration

```bash
# Check position manager environment variables
aws ecs describe-task-definition \
  --task-definition ops-pipeline-position-manager-service \
  --region us-west-2 \
  --query 'taskDefinition.containerDefinitions[0].environment'
```

Verify:
- ACCOUNT_NAME is set correctly (large or tiny)
- No conflicting environment variables

---

## 🚫 Common Mistakes to Avoid

### ❌ DON'T manually close positions in Alpaca without updating DB
**Problem:** Creates phantom positions  
**Fix:** Always use position manager to close, or run reconciliation after

### ❌ DON'T ignore "position not found" errors
**Problem:** Monitoring fails silently  
**Fix:** Investigate immediately, run reconciliation

### ❌ DON'T assume database is always correct
**Problem:** Alpaca is the source of truth for actual positions  
**Fix:** Always reconcile against Alpaca when in doubt

### ❌ DON'T delete positions from database manually
**Problem:** Loses audit trail and learning data  
**Fix:** Mark as closed, move to position_history

---

## 📈 Prevention Best Practices

### 1. Deploy Reconciliation Service
Run every 5 minutes to catch issues early

### 2. Monitor Position Manager Logs
Set up CloudWatch alerts for errors

### 3. Daily Health Checks
Compare database vs Alpaca position counts

### 4. Use Only Automated Trading
Avoid manual trades that bypass the system

### 5. Test in Paper Trading First
Validate all changes before live deployment

---

## 🆘 Emergency Procedures

### If reconciliation service fails:

**Check logs for errors:**
```bash
aws logs tail /ecs/ops-pipeline/position-reconciler \
  --region us-west-2 --since 10m
```

**Common issues:**
- Database connection timeout → Check security groups
- Alpaca API errors → Check credentials in Secrets Manager
- Task won't start → Check task definition, ECR image

**Emergency manual sync:**
```bash
# Run reconciliation task immediately
aws ecs run-task \
  --cluster ops-pipeline-cluster \
  --task-definition ops-pipeline-position-reconciler \
  --launch-type FARGATE \
  --network-configuration 'awsvpcConfiguration={subnets=[subnet-0c182a149eeef918a],securityGroups=[sg-0cd16a909f4e794ce],assignPublicIp=ENABLED}' \
  --region us-west-2
```

### If position manager keeps failing:

**Disable position monitoring temporarily:**
```bash
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service position-manager-service \
  --desired-count 0 \
  --region us-west-2
```

**Fix sync issues, then re-enable:**
```bash
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service position-manager-service \
  --desired-count 1 \
  --region us-west-2
```

---

## 📞 Getting Help

**Check these resources:**
1. This troubleshooting guide
2. OPERATIONS_GUIDE.md for deployment procedures
3. SYSTEM_OVERVIEW.md for architecture details
4. Position manager logs for specific errors

**Still stuck?**
1. Document the error message
2. Check when the issue started
3. Review recent deployments or manual changes
4. Run reconciliation service
5. Check CloudWatch metrics

---

## ✅ Verification Checklist

After resolving sync issues, verify:

- [ ] Position manager error rate = 0%
- [ ] Database position count matches Alpaca
- [ ] All open positions have recent price updates
- [ ] Reconciliation service running every 5 minutes
- [ ] CloudWatch logs show successful reconciliation
- [ ] No phantom positions in database
- [ ] No missing positions in database
- [ ] Position manager logs show successful monitoring

---

**Last Updated:** February 7, 2026  
**Owner:** AI System Owner  
**Related Docs:** SYSTEM_ANALYSIS_2026_02_07.md, OPERATIONS_GUIDE.md
