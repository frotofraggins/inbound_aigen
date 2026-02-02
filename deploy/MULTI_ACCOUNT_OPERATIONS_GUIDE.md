# Multi-Account Operations Guide

**Purpose:** How to track, query, modify, and manage multiple paper trading accounts  
**Created:** 2026-01-29

---

## Account Overview

### Structure

Each account has:
- **Unique scheduler** - ops-pipeline-dispatcher-{tier}
- **Unique task definition** - ops-pipeline-dispatcher-{tier}:N
- **Unique log group** - /ecs/ops-pipeline/dispatcher-{tier}
- **Unique credentials** - ops-pipeline/alpaca/{tier}
- **Database tracking** - account_name column

### Current Accounts

| Account | Tier | Balance | Scheduler | Status |
|---------|------|---------|-----------|--------|
| large-100k | large | $93,000 | ops-pipeline-dispatcher | ✅ Active (rev 15) |
| tiny-1k | tiny | $1,000 | ops-pipeline-dispatcher-tiny | ⏳ Configured |
| small-5k | small | $5,000 | ops-pipeline-dispatcher-small | ⏳ Not created |
| medium-25k | medium | $25,000 | ops-pipeline-dispatcher-medium | ⏳ Not created |

---

## Tracking & Monitoring

### 1. Check Which Accounts Are Running

```bash
# List all dispatcher schedulers
aws scheduler list-schedules \
  --region us-west-2 \
  --query 'Schedules[?contains(Name, `dispatcher`)].{Name: Name, State: State}' \
  --output table
```

**Expected Output:**
```
|                     Name                      | State   |
|-----------------------------------------------|---------|
| ops-pipeline-dispatcher                       | ENABLED |
| ops-pipeline-dispatcher-tiny                  | ENABLED |
| ops-pipeline-dispatcher-small                 | ENABLED |
| ops-pipeline-dispatcher-medium                | ENABLED |
```

### 2. Check Account Activity in Database

```bash
python3 << 'EOF'
import boto3, json
client = boto3.client('lambda', region_name='us-west-2')

r = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'sql': """
        SELECT 
            account_name,
            COUNT(*) as trades_today,
            SUM(notional) as capital_used,
            AVG(contracts) as avg_contracts,
            MAX(simulated_ts)::text as last_trade
        FROM dispatch_executions
        WHERE simulated_ts::date = CURRENT_DATE
            AND account_name IS NOT NULL
        GROUP BY account_name
        ORDER BY account_name
    """})
)

result = json.loads(json.load(r['Payload'])['body'])
print(json.dumps(result, indent=2))
EOF
```

**Expected Output:**
```json
{
  "rows": [
    {
      "account_name": "large-100k",
      "trades_today": 28,
      "capital_used": "54000.00",
      "avg_contracts": 8.5,
      "last_trade": "2026-01-29 17:42:33"
    },
    {
      "account_name": "tiny-1k",
      "trades_today": 5,
      "capital_used": "1250.00",
      "avg_contracts": 1.2,
      "last_trade": "2026-01-29 17:40:15"
    }
  ]
}
```

### 3. Check Logs for Specific Account

```bash
# Large account logs
aws logs tail /ecs/ops-pipeline/dispatcher \
  --region us-west-2 \
  --since 5m \
  | grep -E "(Tier:|account)"

# Tiny account logs (once deployed)
aws logs tail /ecs/ops-pipeline/dispatcher-tiny \
  --region us-west-2 \
  --since 5m \
  | grep -E "(Tier:|account)"
```

---

## Querying Accounts

### Query Single Account Performance

```sql
-- Get today's performance for tiny account
SELECT 
    ticker,
    action,
    contracts,
    notional,
    simulated_ts::text
FROM dispatch_executions
WHERE account_name = 'tiny-1k'
    AND simulated_ts::date = CURRENT_DATE
ORDER BY simulated_ts DESC
LIMIT 10;
```

### Compare Accounts Side-by-Side

```sql
-- Daily comparison across all accounts
SELECT 
    COALESCE(account_name, 'TOTAL') as account,
    COUNT(*) as trades,
    SUM(notional) as capital,
    AVG(contracts) as avg_contracts,
    COUNT(DISTINCT ticker) as unique_tickers
FROM dispatch_executions
WHERE simulated_ts::date = CURRENT_DATE
GROUP BY ROLLUP(account_name)
ORDER BY account_name;
```

### Account Performance Over Time

```sql
-- Weekly performance by account
SELECT 
    account_name,
    DATE_TRUNC('day', simulated_ts) as trade_date,
    COUNT(*) as trades,
    SUM(notional) as capital_used
FROM dispatch_executions
WHERE simulated_ts > NOW() - INTERVAL '7 days'
    AND account_name IS NOT NULL
GROUP BY account_name, DATE_TRUNC('day', simulated_ts)
ORDER BY trade_date DESC, account_name;
```

---

## Managing Individual Accounts

### Start/Stop Specific Account

```bash
# Stop tiny account
aws scheduler update-schedule \
  --name ops-pipeline-dispatcher-tiny \
  --region us-west-2 \
  --state DISABLED

# Start tiny account
aws scheduler update-schedule \
  --name ops-pipeline-dispatcher-tiny \
  --region us-west-2 \
  --state ENABLED

# Check status
aws scheduler get-schedule \
  --name ops-pipeline-dispatcher-tiny \
  --region us-west-2 \
  --query 'State'
```

### Update Specific Account Code

**Scenario:** You want to update ONLY the tiny account to use different logic

**Option 1: Different Image (Advanced)**
```bash
# Build separate image for tiny account
cd services/dispatcher
docker build -t ops-pipeline/dispatcher:tiny-custom .

# Push with different tag
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/dispatcher:tiny-custom

# Update ONLY tiny task definition to use new image
# Edit dispatcher-task-definition-tiny.json with new SHA256
# Register new revision
```

**Option 2: Same Image, Different Config (Easier)**
```bash
# All accounts use same image (revision 15)
# Differences controlled by:
# 1. ACCOUNT_TIER env var (tiny/small/medium/large)
# 2. Credentials in Secrets Manager
# 3. Config parameters

# To change tiny account behavior:
# Update ops-pipeline/alpaca/tiny secret with new parameters
```

### Change Account Credentials

```bash
# Update tiny account API keys
aws secretsmanager update-secret \
  --secret-id ops-pipeline/alpaca/tiny \
  --region us-west-2 \
  --secret-string '{
    "api_key": "NEW_KEY",
    "api_secret": "NEW_SECRET",
    "account_name": "tiny-1k",
    "initial_balance": 1000
  }'

# Credentials take effect on next scheduler run (no restart needed)
```

### Deploy Update to All Accounts

```bash
# When you have a new dispatcher image (e.g., revision 16):

# 1. Update all task definitions
for tier in tiny small medium large; do
  # Edit dispatcher-task-definition-${tier}.json with new SHA256
  aws ecs register-task-definition \
    --cli-input-json file://deploy/dispatcher-task-definition-${tier}.json \
    --region us-west-2 \
    --query 'taskDefinition.revision'
done

# 2. Update all schedulers
for tier in tiny small medium large; do
  aws scheduler update-schedule \
    --name ops-pipeline-dispatcher-${tier} \
    --region us-west-2 \
    --target '{
      "Arn": "arn:aws:ecs:us-west-2:160027201036:cluster/ops-pipeline-cluster",
      "RoleArn": "arn:aws:iam::160027201036:role/ops-pipeline-eventbridge-ecs-role",
      "EcsParameters": {
        "TaskDefinitionArn": "arn:aws:ecs:us-west-2:160027201036:task-definition/ops-pipeline-dispatcher-'${tier}':NEW_REVISION",
        ...
      }
    }'
done
```

---

## Account-Specific Analysis

### Compare Risk Percentages Used

```sql
-- Verify each account uses appropriate risk %
WITH account_stats AS (
    SELECT 
        account_name,
        AVG(notional) as avg_position_size
    FROM dispatch_executions
    WHERE simulated_ts::date = CURRENT_DATE
        AND account_name IS NOT NULL
    GROUP BY account_name
),
expected_balances AS (
    SELECT 'tiny-1k' as account_name, 1000.00 as balance, 0.25 as expected_risk_pct
    UNION ALL SELECT 'small-5k', 5000.00, 0.12
    UNION ALL SELECT 'medium-25k', 25000.00, 0.04
    UNION ALL SELECT 'large-100k', 100000.00, 0.01
)
SELECT 
    eb.account_name,
    eb.balance,
    eb.expected_risk_pct * 100 as expected_risk_pct,
    COALESCE(ast.avg_position_size, 0) as actual_avg_position,
    ROUND(COALESCE(ast.avg_position_size / eb.balance * 100, 0), 2) as actual_risk_pct,
    CASE 
        WHEN COALESCE(ast.avg_position_size / eb.balance, 0) BETWEEN eb.expected_risk_pct * 0.8 AND eb.expected_risk_pct * 1.2 
        THEN '✅ OK'
        ELSE '❌ Off target'
    END as status
FROM expected_balances eb
LEFT JOIN account_stats ast ON eb.account_name = ast.account_name;
```

### Check Contract Counts by Tier

```sql
-- Verify contract counts respect tier caps
SELECT 
    account_name,
    MIN(contracts) as min_contracts,
    AVG(contracts) as avg_contracts,
    MAX(contracts) as max_contracts,
    CASE account_name
        WHEN 'tiny-1k' THEN 2
        WHEN 'small-5k' THEN 3
        WHEN 'medium-25k' THEN 5
        WHEN 'large-100k' THEN 10
    END as tier_cap
FROM dispatch_executions
WHERE simulated_ts::date = CURRENT_DATE
    AND account_name IS NOT NULL
    AND contracts IS NOT NULL
GROUP BY account_name
ORDER BY account_name;
```

---

## Making Changes

### Change Single Account Settings

**Scenario:** Tiny account is too aggressive, reduce to 20% risk

```bash
# Option 1: Update tier definition in config.py
# Edit ACCOUNT_TIERS['tiny']['risk_pct_day'] = 0.20
# Rebuild, deploy new revision
# Update tiny scheduler to new revision

# Option 2: Override in Secrets Manager (if supported)
# Add risk_override to secret
# Update config.py to read overrides
```

### Pause/Resume All Accounts

```bash
# Pause all
for tier in tiny small medium large; do
  aws scheduler update-schedule \
    --name ops-pipeline-dispatcher-${tier} \
    --region us-west-2 \
    --state DISABLED
done

# Resume all
for tier in tiny small medium large; do
  aws scheduler update-schedule \
    --name ops-pipeline-dispatcher-${tier} \
    --region us-west-2 \
    --state ENABLED
done
```

### Emergency Stop Single Account

```bash
# If tiny account misbehaving:
aws scheduler update-schedule \
  --name ops-pipeline-dispatcher-tiny \
  --region us-west-2 \
  --state DISABLED

# Check no more runs happening
aws logs tail /ecs/ops-pipeline/dispatcher-tiny \
  --region us-west-2 \
  --since 5m
```

---

## Monitoring Dashboard Queries

### Daily Account Summary

```sql
-- Run this every morning
SELECT 
    account_name,
    COUNT(*) as trades,
    SUM(notional) as capital_deployed,
    AVG(contracts) as avg_contracts,
    COUNT(DISTINCT ticker) as tickers_traded,
    MIN(simulated_ts)::text as first_trade,
    MAX(simulated_ts)::text as last_trade
FROM dispatch_executions
WHERE simulated_ts::date = CURRENT_DATE
    AND account_name IS NOT NULL
GROUP BY account_name
ORDER BY account_name;
```

### Account Health Check

```sql
-- Check each account had recent activity
SELECT 
    account_name,
    MAX(simulated_ts) as last_trade,
    EXTRACT(EPOCH FROM (NOW() - MAX(simulated_ts)))/60 as minutes_since_last_trade,
    CASE 
        WHEN MAX(simulated_ts) > NOW() - INTERVAL '15 minutes' THEN '✅ Active'
        WHEN MAX(simulated_ts) > NOW() - INTERVAL '1 hour' THEN '⚠️ Slow'
        ELSE '❌ Stale'
    END as status
FROM dispatch_executions
WHERE account_name IS NOT NULL
GROUP BY account_name
ORDER BY account_name;
```

### Tier Validation Report

```sql
-- Comprehensive validation of tier logic
WITH tier_expectations AS (
    SELECT 'tiny-1k' as account_name, 1000 as balance, 25.0 as risk_pct, 2 as max_contracts
    UNION ALL SELECT 'small-5k', 5000, 12.0, 3
    UNION ALL SELECT 'medium-25k', 25000, 4.0, 5
    UNION ALL SELECT 'large-100k', 100000, 1.0, 10
),
actual_behavior AS (
    SELECT 
        account_name,
        AVG(notional) as avg_notional,
        MAX(contracts) as max_contracts_used,
        COUNT(*) as num_trades
    FROM dispatch_executions
    WHERE simulated_ts::date = CURRENT_DATE
        AND account_name IS NOT NULL
    GROUP BY account_name
)
SELECT 
    te.account_name,
    te.balance as expected_balance,
    te.risk_pct as expected_risk_pct,
    te.max_contracts as tier_cap,
    COALESCE(ab.avg_notional, 0) as avg_position_size,
    ROUND(COALESCE(ab.avg_notional / te.balance * 100, 0), 1) as actual_risk_pct,
    COALESCE(ab.max_contracts_used, 0) as max_contracts_used,
    COALESCE(ab.num_trades, 0) as trades,
    CASE 
        WHEN COALESCE(ab.max_contracts_used, 0) <= te.max_contracts THEN '✅'
        ELSE '❌ Over limit!'
    END as cap_respected
FROM tier_expectations te
LEFT JOIN actual_behavior ab ON te.account_name = ab.account_name
ORDER BY te.balance;
```

---

## Log Management

### Check Logs for Specific Account

```bash
# Today's activity for tiny account
aws logs tail /ecs/ops-pipeline/dispatcher-tiny \
  --region us-west-2 \
  --since 24h \
  --format short \
  | grep -E "(Tier:|Buying power|contracts)" \
  | tail -20

# Live tail for debugging
aws logs tail /ecs/ops-pipeline/dispatcher-tiny \
  --region us-west-2 \
  --follow
```

### Compare Logs Across Accounts

```bash
# Check all accounts' last tier detection
for tier in tiny small medium large; do
  echo "=== $tier account ==="
  aws logs tail /ecs/ops-pipeline/dispatcher-${tier} \
    --region us-west-2 \
    --since 1h \
    | grep "Tier:" \
    | tail -1
  echo ""
done
```

---

## Making Changes to Accounts

### Scenario 1: Update All Accounts (New Feature)

**When:** You want to deploy Phase 3 to all accounts

```bash
# 1. Build new image
cd services/dispatcher
docker build --no-cache -t ops-pipeline/dispatcher:phase3 .
docker tag ops-pipeline/dispatcher:phase3 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/dispatcher:phase3
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/dispatcher:phase3

# 2. Get new SHA256 from push output
NEW_SHA="sha256:XXXXX"

# 3. Update ALL task definitions
for tier in tiny small medium large; do
  # Edit dispatcher-task-definition-${tier}.json
  # Change image SHA256 to $NEW_SHA
  
  aws ecs register-task-definition \
    --cli-input-json file://deploy/dispatcher-task-definition-${tier}.json \
    --region us-west-2
done

# 4. Update ALL schedulers
for tier in tiny small medium large; do
  # Update scheduler to new revision
  # ... (scheduler update command)
done
```

### Scenario 2: Update Single Account (Bug Fix)

**When:** Tiny account has an issue, need to fix just that one

```bash
# 1. Fix code
# 2. Build image with specific tag
docker build -t ops-pipeline/dispatcher:tiny-hotfix .

# 3. Update ONLY tiny task definition
# Edit dispatcher-task-definition-tiny.json
aws ecs register-task-definition \
  --cli-input-json file://deploy/dispatcher-task-definition-tiny.json \
  --region us-west-2

# 4. Update ONLY tiny scheduler
aws scheduler update-schedule \
  --name ops-pipeline-dispatcher-tiny \
  --region us-west-2 \
  ...new revision...

# Other accounts continue with old version
```

### Scenario 3: Change Account Balance

**When:** You want to test tiny account with $2K instead of $1K

**Method 1: Change in Alpaca**
```
1. Log into Alpaca paper trading UI
2. Select tiny-1k account
3. Reset equity to $2,000
4. System automatically detects new balance
5. Tier logic will still see it as "tiny" (≤$2K threshold)
```

**Method 2: Update Tier Thresholds**
```bash
# If you want to change what "tiny" means:
# Edit services/dispatcher/config.py
# Change ACCOUNT_TIERS['tiny']['max_size'] = 3000  # Now $0-3K
# Rebuild, deploy new revision to all accounts
```

---

## Troubleshooting

### Account Not Trading

**Check 1: Is scheduler enabled?**
```bash
aws scheduler get-schedule \
  --name ops-pipeline-dispatcher-tiny \
  --region us-west-2 \
  --query '{State: State, LastRun: LastExecutionTime}'
```

**Check 2: Are credentials valid?**
```bash
# Check logs for authentication errors
aws logs tail /ecs/ops-pipeline/dispatcher-tiny \
  --region us-west-2 \
  --since 10m \
  | grep -i "error\|fail\|auth"
```

**Check 3: Is account hitting daily limits?**
```sql
SELECT 
    ticker,
    COUNT(*) as times_traded
FROM dispatch_executions
WHERE account_name = 'tiny-1k'
    AND simulated_ts::date = CURRENT_DATE
GROUP BY ticker
HAVING COUNT(*) >= 2
ORDER BY times_traded DESC;
```

### Account Over-Trading

**Symptom:** Tiny account using more than 25% risk

```sql
-- Find problematic trades
SELECT 
    ticker,
    contracts,
    notional,
    simulated_ts::text,
    ROUND(notional / 1000.0 * 100, 1) as risk_pct_used
FROM dispatch_executions
WHERE account_name = 'tiny-1k'
    AND simulated_ts::date = CURRENT_DATE
    AND notional > 250  -- More than 25% of $1K
ORDER BY notional DESC;
```

**Fix:** Check tier detection logic, verify account balance is correct

---

## Performance Comparison Scripts

### Script 1: Daily Account Report

**File:** `scripts/multi_account_report.py`

```python
#!/usr/bin/env python3
import boto3, json
from datetime import date

client = boto3.client('lambda', region_name='us-west-2')

r = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'sql': """
        SELECT 
            account_name,
            COUNT(*) as trades,
            SUM(notional) as capital,
            AVG(contracts) as avg_contracts,
            MIN(contracts) as min_contracts,
            MAX(contracts) as max_contracts
        FROM dispatch_executions
        WHERE simulated_ts::date = CURRENT_DATE
            AND account_name IS NOT NULL
        GROUP BY account_name
        ORDER BY account_name
    """})
)

result = json.loads(json.load(r['Payload'])['body'])

print(f"\n=== Multi-Account Report - {date.today()} ===\n")
for row in result.get('rows', []):
    print(f"{row['account_name']:15} | Trades: {row['trades']:3} | "
          f"Capital: ${float(row['capital']):8,.0f} | "
          f"Contracts: {float(row['min_contracts']):.0f}-{float(row['max_contracts']):.0f} "
          f"(avg {float(row['avg_contracts']):.1f})")
```

### Script 2: Tier Validation

**File:** `scripts/validate_tiers.sh`

```bash
#!/bin/bash
echo "=== Tier Validation Check ==="
echo ""

for tier in tiny small medium large; do
    echo "Checking ${tier} account..."
    
    # Check scheduler
    state=$(aws scheduler get-schedule \
        --name ops-pipeline-dispatcher-${tier} \
        --region us-west-2 \
        --query 'State' \
        --output text 2>/dev/null)
    
    if [ $? -eq 0 ]; then
        echo "  Scheduler: ${state}"
    else
        echo "  Scheduler: NOT FOUND"
    fi
    
    # Check recent logs
    last_run=$(aws logs tail /ecs/ops-pipeline/dispatcher-${tier} \
        --region us-west-2 \
        --since 5m 2>/dev/null \
        | grep "dispatcher_start" \
        | wc -l)
    
    echo "  Recent runs: ${last_run}"
    echo ""
done
```

---

## Best Practices

### 1. Stagger Schedulers

**Why:** Avoid DB contention, easier to debug

```
Large:  Runs every 1 minute    (:00, :01, :02, :03, ...)
Tiny:   Runs every 5 minutes   (:00, :05, :10, :15, ...)  
Small:  Runs every 5 minutes   (:01, :06, :11, :16, ...)
Medium: Runs every 5 minutes   (:02, :07, :12, :17, ...)
```

### 2. Separate Log Groups

**Why:** Easier to filter, debug specific account

```
/ecs/ops-pipeline/dispatcher        (large)
/ecs/ops-pipeline/dispatcher-tiny   (tiny)
/ecs/ops-pipeline/dispatcher-small  (small)
/ecs/ops-pipeline/dispatcher-medium (medium)
```

### 3. Use account_name Everywhere

**Why:** Clear tracking, easy queries

```sql
-- Always include account_name in queries
WHERE account_name = 'tiny-1k'

-- Group by account for comparisons
GROUP BY account_name
```

---

## Summary

### Tracking Accounts:
- ✅ Unique schedulers per account
- ✅ Unique log groups per account
- ✅ account_name in database
- ✅ Tier automatically detected

### Querying Accounts:
- ✅ Filter by account_name in SQL
- ✅ Compare across accounts with GROUP BY
- ✅ Validate tier behavior with SQL checks
- ✅ Account-specific log groups

### Managing Accounts:
- ✅ Enable/disable individual schedulers
- ✅ Update all accounts together (same image)
- ✅ Update single account (hotfix)
- ✅ Change credentials anytime
- ✅ Scripts for batch operations

### Making Changes:
- ✅ Same codebase, different env vars
- ✅ Tier-specific credentials
- ✅ Independent schedulers
- ✅ Deploy to all or just one

---

## Quick Reference

**List accounts:**
```bash
aws scheduler list-schedules --region us-west-2 | grep dispatcher
```

**Check account:**
```sql
SELECT * FROM dispatch_executions 
WHERE account_name = 'tiny-1k' 
ORDER BY simulated_ts DESC LIMIT 10;
```

**Stop account:**
```bash
aws scheduler update-schedule --name ops-pipeline-dispatcher-tiny --region us-west-2 --state DISABLED
```

**Update all accounts:**
```bash
# Build new image, update all task defs, update all schedulers
```

**See complete examples in MULTI_ACCOUNT_DESIGN.md and MULTI_ACCOUNT_STATUS.md**
