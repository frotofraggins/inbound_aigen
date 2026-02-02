# Troubleshooting Guide - AI Trading System

**Last Updated**: 2026-01-28  
**Purpose**: Clear instructions for diagnosing and fixing common issues

---

## Quick Reference: How to Access Everything

### 1. Database Queries

**✅ CORRECT WAY** (Use this format):
```python
import boto3, json

client = boto3.client('lambda', region_name='us-west-2')
response = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({
        'sql': 'YOUR SQL HERE'  # Note: 'sql' key, not 'query'
    })
)

result = json.loads(json.load(response['Payload'])['body'])
rows = result.get('rows', [])  # Note: 'rows', not 'results'

for row in rows:
    print(row)
```

**❌ WRONG** (These won't work):
- Using `'query'` instead of `'sql'`
- Expecting `'results'` instead of `'rows'`
- Trying to connect directly (RDS is in private VPC)

### 2. Service Logs

**Signal Engine:**
```bash
aws logs tail /ecs/ops-pipeline/signal-engine-1m --region us-west-2 --since 10m
```

**Dispatcher:**
```bash
aws logs tail /ecs/ops-pipeline/dispatcher --region us-west-2 --since 10m
```

**Migration Lambda:**
```bash
aws logs tail /aws/lambda/ops-pipeline-db-migration --region us-west-2 --since 30m
```

### 3. Alpaca Dashboard

**Direct URL**: https://app.alpaca.markets/paper/dashboard

**API Checks**:
```bash
# Account status
curl -X GET 'https://paper-api.alpaca.markets/v2/account' \
  -H 'APCA-API-KEY-ID: PKG7MU6D3EPFNCMVHL6QQSADRS' \
  -H 'APCA-API-SECRET-KEY: BBsd4MCQKKWfCZahkM2jJMXhD4BSE8ddcVkoVR6kXjM9'

# Positions
curl -X GET 'https://paper-api.alpaca.markets/v2/positions' \
  -H 'APCA-API-KEY-ID: PKG7MU6D3EPFNCMVHL6QQSADRS' \
  -H 'APCA-API-SECRET-KEY: BBsd4MCQKKWfCZahkM2jJMXhD4BSE8ddcVkoVR6kXjM9'
```

---

## Common Issues & Solutions

### Issue 1: "No automated trades happening"

**Diagnosis Steps:**

1. **Check if signal engine is running**:
   ```bash
   aws logs tail /ecs/ops-pipeline/signal-engine-1m --region us-west-2 --since 5m | grep "run_complete"
   ```
   Should show runs every 60 seconds.

2. **Check what signals it's generating**:
   ```bash
   aws logs tail /ecs/ops-pipeline/signal-engine-1m --region us-west-2 --since 5m | grep "signal_computed"
   ```
   Look for:
   - `"action": "BUY"` or `"SELL"` = good
   - `"action": "HOLD"` = no trade (check reason)

3. **Check why HOLD**:
   Common reasons:
   - `VOLUME_TOO_LOW`: volume_ratio < 0.5x (kills signal)
   - `CONFIDENCE_TOO_LOW`: confidence < 0.35 (not confident enough)
   - Cooldown period (15-minute wait between trades)

4. **Check if dispatcher is skipping due to trading-hours or confidence gates**:
   ```python
   # Recent skip reasons (last 30 minutes)
   'sql': "SELECT failure_reason, COUNT(*) FROM dispatch_recommendations WHERE status='SKIPPED' AND ts >= NOW() - INTERVAL '30 minutes' GROUP BY failure_reason ORDER BY COUNT(*) DESC"
   ```
   If you see `trading_hours`, the market is closed (outside 9:30–16:00 ET) or in the open/close block windows.

5. **Confirm ET time**:
   Market hours are based on US/Eastern.

4. **Check if volume data exists**:
   ```bash
   python3 scripts/verify_all_phases.py | grep "volume surges"
   ```
   Should show surge count. If 0, volume data not flowing.

**Fix**:
- If `trading_hours` blocked: wait until market hours (after 9:35 AM ET) or adjust the gate if you want extended-hours trading.
- If volume data missing: Check telemetry ingestor logs
- If confidence too low: May need to adjust thresholds in `config/trading_params.json`
- If cooldown: Wait 15 minutes or clear with SQL

### Issue 2: "Alpaca orders not appearing"

**Diagnosis:**

1. **Check dispatcher logs**:
   ```bash
   aws logs tail /ecs/ops-pipeline/dispatcher --region us-west-2 --since 10m
   ```

2. **Check execution_mode in database**:
   ```python
   # Should see ALPACA_PAPER, not SIMULATED_FALLBACK
   'sql': "SELECT execution_mode, COUNT(*) FROM dispatch_executions GROUP BY execution_mode"
   ```

3. **If SIMULATED_FALLBACK**, check explain_json**:
   ```python
   'sql': "SELECT explain_json->>'fallback_reason' FROM dispatch_executions ORDER BY simulated_ts DESC LIMIT 1"
   ```

**Fix**:
- If "No suitable option contract found": Options validation failed, will use stock instead
- If "Alpaca rejected": Check error message in explain_json
- If connection error: Verify Alpaca credentials in SSM

### Issue 3: "Database migration not applying"

**✅ PROVEN METHOD** (From deploy/HOW_TO_APPLY_MIGRATIONS.md):

1. **Add migration to Lambda code**:
   - File: `services/db_migration_lambda/lambda_function.py`
   - Add to `MIGRATIONS` dict with version key
   - Use `IF NOT EXISTS` for safety

2. **Rebuild Lambda**:
   ```bash
   cd services/db_migration_lambda
   rm -rf package migration_lambda.zip
   mkdir package
   pip install -q -r requirements.txt -t package/
   cp lambda_function.py package/
   cd package && zip -q -r ../migration_lambda.zip .
   cd ..
   
   aws lambda update-function-code \
     --function-name ops-pipeline-db-migration \
     --zip-file fileb://migration_lambda.zip \
     --region us-west-2
   ```

3. **Invoke Lambda**:
   ```bash
   aws lambda invoke \
     --function-name ops-pipeline-db-migration \
     --region us-west-2 \
     --payload '{}' \
     /tmp/result.json
   
   cat /tmp/result.json
   ```

4. **Verify**:
   ```python
   # Check schema_migrations table
   'sql': "SELECT version FROM schema_migrations ORDER BY version"
   ```

**❌ DON'T**:
- Try to connect directly with psql (will timeout - VPC)
- Use db-query Lambda for ALTER TABLE (read-only)
- Assume migration applied without verification

---

## Table Name Reference

**CORRECT Names** (Use these!):
- `dispatch_recommendations` (not dispatch_recommendation)
- `dispatch_executions` (not dispatcher_execution)
- `active_positions` (not position_history)
- `lane_features` (not features)
- `lane_telemetry` (not telemetry)

**Common Mistake**: Using singular instead of plural or wrong prefix.

---

## Service Status Checks

### Check All Schedulers
```bash
aws scheduler list-schedules --region us-west-2 | jq '.Schedules[] | {Name, State}'
```

### Check Task Definitions
```bash
aws ecs describe-task-definition --task-definition ops-pipeline-signal-engine-1m --region us-west-2 --query 'taskDefinition.revision'
```

### Check Recent Task Runs
```bash
aws ecs list-tasks --cluster ops-pipeline-cluster --region us-west-2 --desired-status RUNNING
```

---

## Pipeline Health Verification

**Use this script** (already created):
```bash
python3 scripts/verify_all_phases.py
```

**What to look for:**
- ✅ All tables exist
- ✅ Data ingestion working (RSS, telemetry)
- ✅ Features computing
- ✅ Signals generating
- ✅ Executions recording

**If any ❌**: See specific issue diagnosis above.

---

## Configuration Files

### Trading Parameters
**File**: `config/trading_params.json`

**Key settings:**
- Confidence thresholds (0.35-0.60)
- Volume thresholds (VOLUME_KILL = 0.5x)
- Risk limits (max position size, stop loss %)

### Service Configs
**Signal Engine**: `services/signal_engine_1m/config.py`
- Cooldown minutes (15)
- Sentiment window (30 minutes)

**Dispatcher**: `services/dispatcher/config.py`
- Execution mode (ALPACA_PAPER vs SIMULATED)
- Slippage settings

---

## Quick Diagnostics

### "Why no trades?"
```bash
# 1. Check signal engine is running
aws logs tail /ecs/ops-pipeline/signal-engine-1m --region us-west-2 --since 5m | grep "run_complete"

# 2. See what signals it's generating  
aws logs tail /ecs/ops-pipeline/signal-engine-1m --region us-west-2 --since 5m | grep "signal_computed" | tail -10

# 3. If HOLD, check reason
# Look for: VOLUME_TOO_LOW, CONFIDENCE_TOO_LOW, NO_SETUP
```

### "Why SIMULATED_FALLBACK instead of ALPACA_PAPER?"
```bash
# Check recent executions
python3 -c "
import boto3, json
client = boto3.client('lambda', region_name='us-west-2')
r = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'sql': 'SELECT ticker, execution_mode, explain_json->>\\'fallback_reason\\' as reason FROM dispatch_executions ORDER BY simulated_ts DESC LIMIT 5'})
)
result = json.loads(json.load(r['Payload'])['body'])
for row in result.get('rows', []):
    print(f\"{row['ticker']}: {row['execution_mode']} - {row.get('reason', 'N/A')}\")
"
```

### "Is Alpaca working?"
```bash
# Test API directly
curl 'https://paper-api.alpaca.markets/v2/account' \
  -H 'APCA-API-KEY-ID: PKG7MU6D3EPFNCMVHL6QQSADRS' \
  -H 'APCA-API-SECRET-KEY: BBsd4MCQKKWfCZahkM2jJMXhD4BSE8ddcVkoVR6kXjM9'
```

---

## Critical AWS Credentials Note

**If you get "ExpiredTokenException"**:
```bash
ada cred update --account 160027201036 --role IibsAdminAccess-DO-NOT-DELETE --provider conduit --once
```

This expires every few hours. Re-run before any AWS operations.

---

## Contact Points for AI Agents

### Start Here (README)
**File**: `README.md`
- System overview
- Architecture diagram
- Quick start

### System Status
**File**: `CURRENT_SYSTEM_STATUS.md`
- Current infrastructure
- Database credentials (SSM paths)
- Service endpoints

### Documentation Index
**File**: `deploy/DOCUMENTATION_INDEX.md`
- Links to all docs
- Organized by topic

### How Things Work
**File**: `deploy/COMPLETE_TRADING_LOGIC_EXPLAINED.md`
- Signal generation logic
- Entry/exit rules
- Risk management

### Deployments
**File**: `deploy/HOW_TO_APPLY_MIGRATIONS.md`
- Migration process (proven method)
- Deployment steps
- Verification commands

---

## Summary for AI Agents

**Key Learnings**:
1. ✅ Use `'sql'` key and `'rows'` response for db-query Lambda
2. ✅ RDS is in private VPC - always use Lambda, never direct connection
3. ✅ Table names are plural: dispatch_executions, not dispatcher_execution
4. ✅ Check ECS logs for service errors, not just scheduler status
5. ✅ Migrations go in Lambda code, not just SQL files
6. ✅ Alpaca credentials in `services/dispatcher/alpaca/broker.py`
7. ✅ Signal engine generates HOLD during low volume/confidence (this is correct!)

**Proven Scripts**:
- `scripts/verify_all_phases.py` - Complete system check
- `scripts/check_system_status.py` - Quick health check
- `scripts/test_options_validation.py` - Alpaca API test

**When Stuck**: Check ECS logs first, database second, configuration third.
