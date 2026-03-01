# 🤖 NEW AI START HERE - Complete Onboarding

**You're inheriting a professional algorithmic trading system. Here's everything you need.**

---

## ⚡ FIRST 5 MINUTES

### Step 1: Understand What You Have

**This is a production options trading system with:**
- 10 microservices running in AWS ECS
- $122K under algorithmic management (2 accounts)
- Real-time signal generation + execution
- Professional risk management
- VIX regime intelligence

**Tech stack:** Python 3.11, AWS ECS Fargate, PostgreSQL RDS, EventBridge, Alpaca Markets

---

### Step 2: Read These 3 Files (In Order)

**Start here (5 min):** `SYSTEM_OVERVIEW.md`
- Complete architecture
- How services work together  
- What data flows where

**Then read (10 min):** `OPERATIONS_GUIDE.md`
- How to deploy code
- How to monitor
- How to troubleshoot

**Finally (5 min):** `CURRENT_STATUS.md`
- What's working right now
- Recent changes
- Known issues

**Total: 20 minutes to full context**

---

### Step 3: Run Quick Health Check

```bash
# Refresh AWS credentials (ALWAYS DO THIS FIRST)
ada cred update --account 160027201036 --role IibsAdminAccess-DO-NOT-DELETE --provider conduit --once

# Check all services running
aws ecs list-services --cluster ops-pipeline-cluster --region us-west-2

# Check for errors (any service)
aws logs tail /ecs/ops-pipeline/SERVICE-NAME --since 10m --region us-west-2 | grep -i error

# Check positions
python3 -c "
import boto3, json
client = boto3.client('lambda', region_name='us-west-2')
response = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'sql': 'SELECT COUNT(*) FROM active_positions WHERE status = \"open\"'})
)
print(json.loads(json.loads(response['Payload'].read())['body']))
"
```

**If everything returns clean: System is healthy ✅**

---

## 🎯 UNDERSTANDING THE ARCHITECTURE

### Signal Flow (How Trades Happen)

```
1. DATA INGESTION
   ├─ telemetry-service (price/volume every minute)
   ├─ rss-ingest-task (news every minute)
   └─ ticker-discovery (AI selection weekly)
          ↓

2. FEATURE COMPUTATION
   ├─ feature-computer-1m (SMA, trend, volume)
   └─ classifier-worker (sentiment from news)
          ↓

3. SIGNAL GENERATION (REAL-TIME)
   ├─ market-data-stream (WebSocket, 1-3 sec) ← NEW
   └─ signal-engine-1m (scheduled, 60 sec) ← FALLBACK
          ↓
   Writes to: dispatch_recommendations table
          ↓

4. TRADE EXECUTION (BOTH ACCOUNTS)
   ├─ dispatcher-service (large: $6-24K per trade)
   └─ dispatcher-tiny-service (tiny: $80 per trade)
          ↓
   Checks 13 risk gates (optimized order):
   1. daily_loss_limit (kill switch)
   2. vix_regime (volatility check)
   3. trading_hours (9:30 AM - 4 PM ET)
   4. Data freshness (bar, features, signal)
   5. Account capacity (max positions, exposure)
   6. Ticker limits (daily limit, cooldown)
   7. Signal quality (confidence, valid action)
          ↓
   If all pass → Execute on Alpaca
          ↓

5. POSITION MONITORING (BOTH ACCOUNTS)
   ├─ position-manager-service (large account)
   └─ position-manager-tiny-service (tiny account)
          ↓
   Every minute:
   - Update prices
   - Check stop losses (-40%)
   - Check trailing stops (75% lock)
   - Check take profit (+80%)
   - Close at 3:55 PM ET
          ↓

6. LEARNING & INTELLIGENCE
   ├─ position_history (closed trades)
   ├─ vix_history (regime tracking) ← NEW
   └─ Future: AI confidence adjustment (after 50 trades)
```

**This is the complete flow for BOTH accounts.**

---

## 🔧 COMMON TASKS (Copy-Paste Ready)

### Deploy Code Change

```bash
# Example: Update signal engine
cd services/signal_engine_1m

# Build
docker build -t 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/signal-engine-1m:latest .

# Login to ECR
aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin 160027201036.dkr.ecr.us-west-2.amazonaws.com

# Push
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/signal-engine-1m:latest

# Restart service (persistent) OR update schedule (scheduled task)
aws ecs update-service --cluster ops-pipeline-cluster --service SERVICE-NAME --force-new-deployment --region us-west-2
```

### Deploy Database Change

**ONLY method that works: db-migrator ECS task**

```bash
# 1. Create migration file
cat > db/migrations/1005_my_feature.sql << 'EOF'
ALTER TABLE active_positions ADD COLUMN my_column VARCHAR(50);
EOF

# 2. Rebuild db-migrator
cd /home/nflos/workplace/inbound_aigen
docker build --no-cache -f services/db_migrator/Dockerfile -t 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/db-migrator:latest .

# 3. Push
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/db-migrator:latest

# 4. Run migration
aws ecs run-task --cluster ops-pipeline-cluster --task-definition ops-pipeline-db-migrator --launch-type FARGATE --network-configuration "awsvpcConfiguration={subnets=[subnet-0c182a149eeef918a],securityGroups=[sg-0cd16a909f4e794ce],assignPublicIp=ENABLED}" --region us-west-2

# 5. Verify
python3 -c "
import boto3, json
client = boto3.client('lambda', region_name='us-west-2')
response = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'sql': 'SELECT * FROM active_positions LIMIT 1'})
)
print(json.loads(json.loads(response['Payload'].read())['body']))
"
```

### Check System Health

```bash
# All services
aws ecs describe-services --cluster ops-pipeline-cluster --services dispatcher-service dispatcher-tiny-service position-manager-service position-manager-tiny-service --region us-west-2 --query 'services[*].[serviceName,runningCount,desiredCount]' --output table

# Recent errors (any service)
aws logs tail /ecs/ops-pipeline/SERVICE-NAME --since 10m --region us-west-2 | grep -i error

# Open positions
python3 scripts/query_via_lambda.py

# Recent signals
python3 check_recent_trades.py
```

---

## 🚨 TROUBLESHOOTING DECISION TREE

### Problem: "No trades executing"

**Step 1:** Check market hours
```
Current time: 8:37 AM ET → PRE-MARKET (wait until 9:30 AM)
Current time: 11:00 AM ET → Should be trading
Current time: 5:00 PM ET → AFTER-HOURS (done for day)
```

**Step 2:** Check signal generation
```bash
aws logs tail /ecs/ops-pipeline/signal-engine-1m --since 5m --region us-west-2 | grep run_complete
```
- See "signals_generated": 1-2 → Working ✅
- See "signals_hold": 10-15 → Normal (waiting for setups)
- No output → Service may be down

**Step 3:** Check dispatcher
```bash
aws logs tail /ecs/ops-pipeline/dispatcher-service --since 5m --region us-west-2
```
- See signal processing → Working ✅
- See "SKIPPED" with reasons → Risk gates blocking (check reasons)
- No logs → Service may be down

**Step 4:** Check why signals skipped
- trading_hours: Market closed (wait)
- bar_freshness: Data stale (after hours, wait)
- ticker_daily_limit: Already traded today (by design)
- confidence_too_low: Weak signal (by design)
- vix_regime: VIX > 40 (extreme volatility, by design)

**90% of "no trading" is correct behavior (waiting for good setups).**

---

### Problem: "Service won't start"

**Check task health:**
```bash
aws ecs describe-services --cluster ops-pipeline-cluster --services SERVICE-NAME --region us-west-2 --query 'services[0].events[0:5]'
```

**Check logs:**
```bash
aws logs tail /ecs/ops-pipeline/SERVICE-NAME --since 5m --region us-west-2
```

**Common causes:**
1. **Import error** - Missing dependency (rebuild with correct requirements.txt)
2. **Config error** - Wrong secret name (check Secrets Manager)
3. **Database timeout** - VPC issue (check security groups)

**Fix:** Rebuild with --no-cache, push, restart

---

### Problem: "Position not being monitored"

**Check which account:**
```python
# Query database
SELECT * FROM active_positions WHERE ticker = 'AAPL' AND status = 'open'
```

**If position exists in Alpaca but not database:**
1. Check position-manager logs for sync errors
2. Verify account credentials correct (ops-pipeline/alpaca vs ops-pipeline/alpaca/tiny)
3. Check if ACCOUNT_NAME environment variable set
4. Manually sync via migration if needed

**Documented in:** OPERATIONS_GUIDE.md "Multi-Account Configuration"

---

## 📊 SERVICE DEPENDENCY MAP

### Critical Services (Must Work):
```
signal-engine-1m ← Generates signals (REQUIRED)
    ↓
dispatcher-service ← Executes large account (REQUIRED)
dispatcher-tiny-service ← Executes tiny account (REQUIRED)
    ↓
position-manager-service ← Monitors large (REQUIRED)
position-manager-tiny-service ← Monitors tiny (REQUIRED)
```

### Support Services:
```
telemetry-service ← Market data (REQUIRED)
feature-computer-1m ← Indicators (REQUIRED)
trade-stream ← Order fill sync (IMPORTANT)
watchlist-engine-5m ← Ticker scoring (NICE TO HAVE)
ticker-discovery ← AI selection (NICE TO HAVE)
```

### New Services (Enhancements):
```
market-data-stream ← Real-time signals (OPTIONAL - fallback works)
vix-monitor ← Regime intelligence (OPTIONAL - trades without it)
```

**If critical services work: System trades**  
**If support services work: System works well**  
**If new services work: System works better**

---

## 🎯 EXPECTED ERRORS (These Are Normal)

### ⚠️ "403 Forbidden" fetching option bars
**Meaning:** Alpaca requires paid subscription for options historical data  
**Impact:** ZERO - This is optional learning feature  
**Fix:** Ignore (or upgrade Alpaca subscription)

### ⚠️ "trading_hours" blocking signals
**Meaning:** Market is closed  
**Impact:** ZERO - This is correct behavior  
**Fix:** Wait for market hours (9:30 AM - 4:00 PM ET)

### ⚠️ "bar_freshness" or "feature_freshness" after hours
**Meaning:** Data is stale because market closed  
**Impact:** ZERO - This is correct protection  
**Fix:** Wait for market open

### ⚠️ WebSocket "extra_headers" error
**Meaning:** alpaca-py library compatibility issue  
**Impact:** UNKNOWN - May still work, fallback exists  
**Fix:** Test at market open, signal_engine_1m works either way

**These errors don't break the system.**

---

## 💡 CRITICAL CONCEPTS

### 1. Multi-Account Architecture

**Two separate Alpaca accounts:**
- Large: $121K capital (ops-pipeline/alpaca secret)
- Tiny: $1K capital (ops-pipeline/alpaca/tiny secret)

**Services share:**
- Signal generation (same signals for both)
- Risk intelligence (same VIX regime)
- Database (filtered by account_name column)

**Services separate:**
- Dispatchers (different credentials)
- Position managers (different credentials)
- Execution (different Alpaca accounts)

**Key:** ACCOUNT_NAME environment variable determines which account a service uses

---

### 2. Database Access

**Cannot connect directly!**
- Database in private VPC
- Only accessible from ECS services
- For queries: Use Lambda ops-pipeline-db-query
- For DDL/DML: Use db-migrator ECS task

**Wrong methods (will timeout):**
- psycopg2 direct connection
- RDS Query Editor
- Any local tool

---

### 3. Signal Generation Has 2 Paths

**Path 1:** market-data-stream (WebSocket)
- Real-time (1-3 sec)
- NEW, may have issues
- Falls back to Path 2

**Path 2:** signal-engine-1m (scheduled)
- Every 60 seconds
- PROVEN, reliable
- Always works

**Both write to same table: dispatch_recommendations**

**Dispatchers don't care which path generated the signal.**

---

### 4. Risk Gate Ordering Matters

**Current order (optimized):**
```
TIER 1 KILL SWITCHES (check first):
  1. daily_loss_limit
  2. vix_regime
  3. trading_hours
  
If any TIER 1 fails → Skip all other checks (90% faster after hours)

TIER 2-5: Only checked if TIER 1 passed
```

**Previous order was inefficient (checked confidence before trading_hours).**

---

## 🚀 DEPLOYING NEW FEATURES

### Adding a New Service (Example: market breadth monitor)

**Step 1:** Create service
```bash
mkdir services/breadth_monitor
cd services/breadth_monitor

# Create main.py, requirements.txt, Dockerfile
# Copy pattern from services/vix_monitor/
```

**Step 2:** Create database table (if needed)
```bash
# Create migration: db/migrations/1005_add_breadth_table.sql
# Use db-migrator to apply (see OPERATIONS_GUIDE.md)
```

**Step 3:** Build and deploy
```bash
docker build -t 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/breadth-monitor:latest .
docker push ...

# Create task definition (copy pattern from deploy/vix-monitor-task-definition.json)
aws ecs register-task-definition --cli-input-json file://deploy/breadth-monitor-task-definition.json

# Run as scheduled task or service
```

**Step 4:** Integrate
```python
# Add check in dispatcher/risk/gates.py
# Or add to signal_engine/rules.py for confidence adjustment
```

**Pattern is always the same:**
1. New service directory
2. Database table (optional)
3. Build & deploy
4. Integrate into decision flow

---

## ⚠️ CRITICAL DIFFERENCES (Read Carefully)

### Persistent Services vs Scheduled Tasks

**Persistent (run 24/7):**
- dispatcher-service
- position-manager-service
- telemetry-service
- trade-stream
- market-data-stream

**Deploy:** `aws ecs update-service --force-new-deployment`

**Scheduled (EventBridge triggers):**
- signal-engine-1m
- feature-computer-1m
- watchlist-engine-5m
- ticker-discovery
- vix-monitor

**Deploy:** Update task definition, then update EventBridge schedule with new revision

---

### Services That Share Images

**position-manager image used by:**
- position-manager-service (ACCOUNT_NAME=large)
- position-manager-tiny-service (ACCOUNT_NAME=tiny)

**If you rebuild position-manager:**
- Restart BOTH services
- They use same image, different environment variables

**dispatcher image used by:**
- dispatcher-service (ACCOUNT_TIER=large)
- dispatcher-tiny-service (ACCOUNT_TIER=tiny)

**Same pattern - restart both if you rebuild.**

---

## 🎓 LEARNING THE SYSTEM

### First Week Goals:

**Day 1:** Read docs, run health checks, understand architecture  
**Day 2:** Deploy a code change (test with signal engine)  
**Day 3:** Apply a database migration (test with simple column add)  
**Day 4:** Add a new risk gate (test integration)  
**Day 5:** Add a new scheduled service (test deployment)

**By end of week:** You can maintain and extend the system independently.

---

### Common Beginner Mistakes:

❌ **Trying to connect to database directly** → Use Lambda  
❌ **Forgetting to refresh credentials** → ada cred update  
❌ **Not checking if market is open** → Most "errors" are correct blocks  
❌ **Rebuilding without --no-cache** → Old code cached  
❌ **Forgetting ACCOUNT_NAME** → Service uses wrong account  
❌ **Not waiting for deployment** → Service still using old image  
❌ **Using sys.exit() in service loops** → Use `return` or `raise` instead. `SystemExit` inherits from `BaseException`, not `Exception`, so `except Exception` won't catch it. This caused crash-loops in telemetry and position manager (fixed Feb 11).  
❌ **Using positions API for option prices** → Use `/v1beta1/options/quotes/latest` for live bid/ask. The positions API returns stale broker valuations (fixed Feb 11).  
❌ **Task definition pointing to old image tag** → Always verify the image tag in the task definition matches what you pushed. Use `:latest` for all services.
❌ **Position sync order matters** → DB sync (with features) must run BEFORE Alpaca sync. Alpaca sync creates positions with empty features. If it runs first, DB sync skips them (already exist). Fixed Feb 11.
❌ **Dispatcher not saving features_snapshot** → The INSERT into dispatch_executions must include features_snapshot. Without it, the learning pipeline has no feature data. Fixed Feb 11.

**Avoid these and you're 90% there.**

---

## 📖 QUICK REFERENCE

**AWS Account:** 160027201036  
**Region:** us-west-2  
**Cluster:** ops-pipeline-cluster  
**Database:** ops-pipeline-db.cls4wuyg010k.us-west-2.rds.amazonaws.com  
**Lambda (queries):** ops-pipeline-db-query  

**Alpaca Secrets:**
- Large: ops-pipeline/alpaca/large (or fallback: ops-pipeline/alpaca)
- Tiny: ops-pipeline/alpaca/tiny

**Market Hours:**  
- 9:30 AM - 4:00 PM ET
- 2:30 PM - 9:00 PM UTC
- 7:30 AM - 2:00 PM Arizona (winter)

---

## ✅ YOU'RE READY WHEN YOU CAN:

- [ ] Explain how a signal becomes a trade
- [ ] Deploy a code change without breaking anything
- [ ] Know when errors are critical vs normal
- [ ] Understand multi-account architecture
- [ ] Run health checks and interpret results

**If you can do these: You understand the system.**

---

## 🚀 ADVANCED TOPICS (After First Week)

### Learning Pipeline (Active as of Feb 11)
- **Trade Analyzer** (`services/trade_analyzer/`) — statistical analysis of trade outcomes
- **Learning Applier** (`services/learning_applier/`) — Bedrock Claude reviews findings, auto-applies SSM changes
- Daily schedule: Analyzer at 9:15 PM UTC → Applier at 9:30 PM UTC (Mon-Fri)
- Results go to `learning_recommendations` table
- SSM params auto-applied by AI, code changes flagged as 'ai_approved' for human deploy
- Pre-filters: rejects if sample_size < 10 or confidence < 0.5
- Data pipeline: `dispatch_recommendations` (features) → `dispatch_executions` (features_snapshot) → `active_positions` (entry_features_json) → `position_history` (entry_features_json)

### Future ML Topics
- Adding ML-based confidence adjustment (need 100+ trades)
- Implementing IV rank filtering
- Building market regime detection
- Adding institutional flow tracking
- Optimizing for live trading (vs paper)

**But master the basics first.**

---

**This document gives you everything to hit the ground running.**

**Read top-to-bottom: 30 minutes to full understanding.**

**Then start with health checks and small changes.**

**Welcome to professional quant development.**
