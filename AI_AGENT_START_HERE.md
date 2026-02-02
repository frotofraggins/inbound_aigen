# 🤖 AI AGENT START HERE

**You are an AI agent helping with an AWS-based options trading system.**

This document provides everything you need to understand and troubleshoot the system quickly.

---

## 🎯 System Overview

**What it does**: Automated trading system that:
1. Fetches financial news (RSS)
2. Classifies sentiment with AI
3. Computes technical indicators
4. Generates trading signals
5. Executes trades in Alpaca Paper Trading
6. Tracks positions and P/L

**Status**: ✅ Operational (Alpaca integration complete as of 2026-01-28)

---

## 📚 Essential Documents (Read These First)

### 1. **Quick System Check**
```bash
python3 scripts/verify_all_phases.py
```
Shows health of all 15 phases in 30 seconds.

### 2. **Architecture & Logic**
**File**: `deploy/COMPLETE_TRADING_LOGIC_EXPLAINED.md`
- How signals are generated
- Entry/exit rules
- Risk management

### 3. **Troubleshooting**
**File**: `deploy/TROUBLESHOOTING_GUIDE.md`
- Common issues & solutions
- Correct query formats
- Proven diagnostic commands

### 4. **Current Status**
**File**: `CURRENT_SYSTEM_STATUS.md`
- Infrastructure details
- Database info
- Service endpoints

### 5. **Deployment Guide**
**File**: `deploy/HOW_TO_APPLY_MIGRATIONS.md`
- Proven migration method
- Avoid common pitfalls

---

## ⚡ Critical Knowledge for AI Agents

### Database Queries (Use This Exact Format!)

**✅ CORRECT**:
```python
import boto3, json

client = boto3.client('lambda', region_name='us-west-2')
response = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({
        'sql': 'SELECT * FROM dispatch_executions LIMIT 5'  # 'sql' key!
    })
)

result = json.loads(json.load(response['Payload'])['body'])
rows = result.get('rows', [])  # 'rows', not 'results'!

for row in rows:
    print(row)
```

**❌ WRONG** (Will fail silently):
- Using `'query'` key instead of `'sql'`
- Expecting `'results'` instead of `'rows'`

### Table Names (Use Correct Plurals!)

| ✅ CORRECT | ❌ WRONG |
|-----------|---------|
| `dispatch_recommendations` | dispatch_recommendation |
| `dispatch_executions` | dispatcher_execution |  
| `active_positions` | position_history |
| `lane_features` | features |
| `lane_telemetry` | telemetry |

### Service Logs

```bash
# Signal Engine (generates trading signals)
aws logs tail /ecs/ops-pipeline/signal-engine-1m --region us-west-2 --since 10m

# Dispatcher (executes trades)
aws logs tail /ecs/ops-pipeline/dispatcher --region us-west-2 --since 10m

# Check for "signal_computed" to see what signals are being generated
```

### Alpaca Dashboard

**URL**: https://app.alpaca.markets/paper/dashboard

**Test Order**:
```bash
curl -X POST 'https://paper-api.alpaca.markets/v2/orders' \
  -H 'APCA-API-KEY-ID: PKG7MU6D3EPFNCMVHL6QQSADRS' \
  -H 'APCA-API-SECRET-KEY: BBsd4MCQKKWfCZahkM2jJMXhD4BSE8ddcVkoVR6kXjM9' \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"SPY","qty":"1","side":"buy","type":"market","time_in_force":"day"}'
```

---

## 🚨 Common Pitfalls

### 1. "No trades happening"

**Check ECS logs first!**
```bash
aws logs tail /ecs/ops-pipeline/signal-engine-1m --region us-west-2 --since 5m | grep "signal_computed"
```

Look for:
- `"action": "HOLD"` with `"rule": "VOLUME_TOO_LOW"` = Low volume (correct behavior)
- `"action": "HOLD"` with `"rule": "CONFIDENCE_TOO_LOW"` = Weak signal (correct)
- `"action": "BUY"` or `"SELL"` = Signal triggered!

### 2. "Migration not applying"

**Only one method works**: Embed in Lambda code

**File**: `services/db_migration_lambda/lambda_function.py`

Add to `MIGRATIONS` dict, rebuild, invoke. See `deploy/HOW_TO_APPLY_MIGRATIONS.md`.

### 3. "Can't connect to database"

**You can't!** RDS is in private VPC. Always use:
- `ops-pipeline-db-query` Lambda for SELECT
- `ops-pipeline-db-migration` Lambda for DDL

### 4. "Expired credentials"

```bash
ada cred update --account 160027201036 --role IibsAdminAccess-DO-NOT-DELETE --provider conduit --once
```

Expires every few hours.

---

## 🎯 Quick Diagnostics

### Is system running?
```bash
aws scheduler list-schedules --region us-west-2 | grep "ops-pipeline"
```
Should show: signal-engine-1m, dispatcher, etc. with State: ENABLED

### Recent trades?
```bash
python3 scripts/verify_all_phases.py | grep "Trade Executions"
```

### Alpaca working?
```bash
curl 'https://paper-api.alpaca.markets/v2/account' \
  -H 'APCA-API-KEY-ID: PKG7MU6D3EPFNCMVHL6QQSADRS' \
  -H 'APCA-API-SECRET-KEY: BBsd4MCQKKWfCZahkM2jJMXhD4BSE8ddcVkoVR6kXjM9'
```
Should return account with cash balance.

---

## 📖 Complete Documentation Map

**Getting Started:**
- `README.md` - System overview
- `CURRENT_SYSTEM_STATUS.md` - Infrastructure

**Understanding System:**
- `deploy/COMPLETE_TRADING_LOGIC_EXPLAINED.md` - Trading logic
- `deploy/PRODUCTION_LOGIC_V2_SUMMARY.md` - Signal rules

**Operating System:**
- `deploy/RUNBOOK.md` - Operations guide
- `deploy/TROUBLESHOOTING_GUIDE.md` - Fix common issues
- `deploy/HOW_TO_APPLY_MIGRATIONS.md` - Database changes

**Recent Work:**
- `deploy/ALPACA_OPTIONS_INTEGRATION_COMPLETE.md` - Options trading (Phase 15)
- `deploy/FINAL_STATUS_2026-01-28.md` - Latest session summary

**Scripts:**
- `scripts/verify_all_phases.py` - Complete system check ⭐
- `scripts/check_system_status.py` - Quick health check
- `scripts/test_options_validation.py` - Test Alpaca orders

---

## ⚡ Most Common Task: "Why aren't trades executing?"

**1. Check signal engine logs**:
```bash
aws logs tail /ecs/ops-pipeline/signal-engine-1m --region us-west-2 --since 5m | grep "signal_computed" | tail -10
```

**2. Look for action and rule**:
- `"action": "BUY"` or `"SELL"` = Trade signal! Check if dispatcher executed it.
- `"action": "HOLD", "rule": "VOLUME_TOO_LOW"` = Volume < 0.5x (safety gate working)
- `"action": "HOLD", "rule": "CONFIDENCE_TOO_LOW"` = Weak signal (< 0.35 threshold)

**3. If market is open and still HOLD**:
- Check if volume data exists: `python3 scripts/verify_all_phases.py | grep "volume surges"`
- If 0 surges: Volume ingestion issue
- If 100+ surges: Thresholds may be too restrictive

**4. If signals generate but no Alpaca trades**:
- Check dispatcher logs: `aws logs tail /ecs/ops-pipeline/dispatcher --region us-west-2 --since 10m`
- Check execution_mode in database (should be ALPACA_PAPER not SIMULATED_FALLBACK)

---

## 💡 Pro Tips for AI Agents

1. **Always check ECS logs first** - They show what's actually happening
2. **Use verify_all_phases.py** - Saves 10 minutes of investigation
3. **Check table names** - They're plural: dispatch_executions, not dispatcher_execution
4. **HOLD signals are normal** - System has safety gates (volume, confidence)
5. **Alpaca integration works** - Manual test proven (SPY260130C00609000)

---

## 🆘 If Completely Stuck

**Ask yourself:**
1. Are credentials fresh? (ada cred update)
2. Did I check ECS logs? (aws logs tail)
3. Did I run verify_all_phases.py?
4. Am I using correct table names?
5. Am I using `'sql'` key for queries?

**Then consult**:
- `deploy/TROUBLESHOOTING_GUIDE.md`
- `deploy/HOW_TO_APPLY_MIGRATIONS.md`
- ECS logs: `/ecs/ops-pipeline/SERVICE-NAME`

---

## ✅ Proven Working (As of 2026-01-28)

- ✅ Alpaca options trading integration
- ✅ Test order: SPY260130C00609000 FILLED
- ✅ Position tracking in dashboard
- ✅ Signal engine running
- ✅ Data pipeline operational
- ⏳ Automated trades pending (market hours + volume)

**The system works. If no trades, it's because risk gates are correctly preventing bad trades (low volume/confidence).**

🎯 **Start with `python3 scripts/verify_all_phases.py` - it will tell you what's broken (if anything).**
