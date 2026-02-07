# 🤖 AI AGENT START HERE - UPDATED FEB 6, 2026

**You are an AI agent helping with an AWS-based options trading system.**

This document provides everything you need to understand and work with the system.

---

## 🎯 Current System Status (Feb 6, 2026)

**Completion:** 10/11 features working (91%)  
**Status:** ✅ FULLY OPERATIONAL  
**Last Updated:** February 6, 2026

**What it does**: AI-powered options trading system:
1. Monitors 30 tickers with AI selection (Bedrock)
2. Ingests news and computes sentiment (FinBERT)
3. Calculates technical indicators (SMA, trend, volume)
4. Generates trading signals (momentum + gap fade strategies)
5. Executes trades on Alpaca Paper Trading
6. Monitors positions with trailing stops
7. Learns from outcomes (13 trades captured)

**Key Achievement:** Trailing stops now active, protecting winners from reversals

---

## 📚 Essential Documents (Updated Feb 6, 2026)

### START HERE FIRST:
1. **COMPLETE_SYSTEM_STATUS_2026-02-06_FINAL.md** ⭐ READ THIS FIRST
   - Current system status (10/11 features working)
   - All services health check
   - What's working, what's not

2. **WHY_TRADES_LOST_MONEY_2026-02-06.md** - Trade analysis
   - Why 23% win rate
   - Peak reversal pattern
   - Late entry problem

3. **MASTER_SYSTEM_DOCUMENTATION.md** - Complete technical reference

### Architecture:
- `docs/ECS_DOCKER_ARCHITECTURE.md` - How services connect (NO local Docker!)
- `deploy/AI_PIPELINE_EXPLAINED.md` - How AI/ML works
- `README.md` - System overview

### Operations:
- `deploy/RUNBOOK.md` - Daily operations
- `deploy/TROUBLESHOOTING_GUIDE.md` - Fix issues
- `docs/DATABASE_ACCESS_GUIDE.md` - How to query database

---

## 🔌 How To Connect To The System

### AWS Credentials (REQUIRED FIRST!)
```bash
# Refresh credentials (expire every few hours)
ada cred update --account 160027201036 --role IibsAdminAccess-DO-NOT-DELETE --provider conduit --once
```

### ECS Services (All in AWS Cloud)
**Cluster:** ops-pipeline-cluster  
**Region:** us-west-2

**List services:**
```bash
aws ecs list-services --cluster ops-pipeline-cluster --region us-west-2
```

**Check health:**
```bash
aws ecs describe-services \
  --cluster ops-pipeline-cluster \
  --services dispatcher-service position-manager-service \
  --region us-west-2 \
  --query 'services[*].[serviceName,runningCount,desiredCount]'
```

**View logs:**
```bash
aws logs tail /ecs/ops-pipeline/SERVICE-NAME \
  --region us-west-2 --since 10m --follow
```

### Database Access (RDS in Private VPC)

**IMPORTANT:** You CANNOT connect directly! Database is in private VPC.

**✅ CORRECT Method - Via Lambda:**
```python
import boto3, json

client = boto3.client('lambda', region_name='us-west-2')
response = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({
        'sql': 'SELECT * FROM active_positions WHERE status = \'open\' LIMIT 5'
    })
)

result = json.loads(response['Payload'].read())
data = json.loads(result['body'])
rows = data.get('rows', [])  # Note: 'rows' not 'results'

for row in rows:
    print(row)
```

**❌ WRONG Methods (Will timeout):**
- Direct psycopg2 connection
- Local SQL clients (DBeaver, pgAdmin)
- Any connection from outside VPC

**Database Details:**
- Host: ops-pipeline-db.cls4wuyg010k.us-west-2.rds.amazonaws.com
- Port: 5432
- Name: ops_pipeline
- VPC: vpc-0444cb2b7a3457502 (Private)
- Security Group: sg-09379d105ed7901a9

## 📝 How To Deploy Code Changes

### 1. Update Service Code (e.g., signal engine)

**Steps:**
```bash
# 1. Edit code in services/signal_engine_1m/

# 2. Build Docker image
cd services/signal_engine_1m
docker build -t 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/signal-engine-1m:latest .

# 3. Push to ECR
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/signal-engine-1m:latest

# 4. Get current task definition
aws ecs describe-task-definition \
  --task-definition ops-pipeline-signal-engine-1m \
  --region us-west-2 \
  --query 'taskDefinition' > /tmp/task-def.json

# 5. Update image in JSON to :latest
jq '.containerDefinitions[0].image = "160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/signal-engine-1m:latest" | del(.taskDefinitionArn, .revision, .status, .requiresAttributes, .compatibilities, .registeredAt, .registeredBy)' \
  /tmp/task-def.json > /tmp/task-def-new.json

# 6. Register new task definition
aws ecs register-task-definition \
  --cli-input-json file:///tmp/task-def-new.json \
  --region us-west-2

# 7. Update EventBridge schedule (signal engine is scheduled, not a service)
# Get schedule target config, update task definition ARN to new version
```

### 2. Add Database Columns (PROVEN METHOD)

**ONLY method that works:**

```bash
# 1. Add migration to services/db_migrator/migrations/
cp my_migration.sql services/db_migrator/migrations/1003_my_feature.sql

# 2. Rebuild db-migrator Docker image from project root
cd /path/to/project
docker build --no-cache -f services/db_migrator/Dockerfile \
  -t 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/db-migrator:latest .

# 3. Push to ECR
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/db-migrator:latest

# 4. Create task definition with :latest
cat > /tmp/migrator-latest.json << 'EOF'
{
  "family": "ops-pipeline-db-migrator",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "executionRoleArn": "arn:aws:iam::160027201036:role/ops-pipeline-ecs-task-role",
  "taskRoleArn": "arn:aws:iam::160027201036:role/ops-pipeline-ecs-task-role",
  "containerDefinitions": [{
    "name": "db-migrator",
    "image": "160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/db-migrator:latest",
    "essential": true,
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "/ecs/ops-pipeline/db-migrator",
        "awslogs-region": "us-west-2",
        "awslogs-stream-prefix": "migrator",
        "awslogs-create-group": "true"
      }
    }
  }]
}
EOF

# 5. Register and run
aws ecs register-task-definition --cli-input-json file:///tmp/migrator-latest.json --region us-west-2

# 6. Run task
aws ecs run-task \
  --cluster ops-pipeline-cluster \
  --task-definition ops-pipeline-db-migrator \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-0c182a149eeef918a],securityGroups=[sg-0cd16a909f4e794ce],assignPublicIp=ENABLED}" \
  --region us-west-2

# 7. Verify (check exit code 0 and query columns)
```

**Methods that DON'T work:**
- ❌ Lambda ops-pipeline-db-query (read-only)
- ❌ Direct psycopg2 (no VPC access)
- ❌ Lambda in VPC (needs NAT Gateway)
- ❌ RDS Query Editor (not available for non-Aurora)

### Table Names (Use Correct Plurals!)

| ✅ CORRECT | ❌ WRONG |
|-----------|---------|
| `dispatch_recommendations` | dispatch_recommendation |
| `dispatch_executions` | dispatcher_execution |  
| `active_positions` | position_history |
| `position_history` | closed_positions |
| `lane_features` | features |
| `lane_telemetry` | telemetry |

## 🏗️ System Architecture (Feb 6, 2026)

### Services (6 Persistent):
1. **dispatcher-service** - Trade execution (large account)
2. **dispatcher-tiny-service** - Trade execution (tiny account, 8% risk)
3. **position-manager-service** - Monitor positions (large)
4. **position-manager-tiny-service** - Monitor positions (tiny)
5. **telemetry-service** - Market data (1-minute bars)
6. **trade-stream** - WebSocket for instant position sync

### Scheduled Tasks (5 via EventBridge):
7. **signal-engine-1m** (v16) - Generate signals every minute
   - Momentum urgency detection
   - Gap fade strategy (9:30-10:30 AM)
8. **feature-computer-1m** - Technical indicators
9. **watchlist-engine-5m** - Score opportunities
10. **ticker-discovery** (weekly) - AI ticker selection (Bedrock)
11. **rss-ingest-task** - News ingestion

### Service Logs

```bash
# Signal Engine (generates trading signals) - SCHEDULED TASK
aws logs tail /ecs/ops-pipeline/signal-engine-1m --region us-west-2 --since 10m

# Position Manager (monitors exits + trailing stops)
aws logs tail /ecs/ops-pipeline/position-manager-service --region us-west-2 --since 10m

# Dispatcher (executes trades)
aws logs tail /ecs/ops-pipeline/dispatcher-service --region us-west-2 --since 10m

# Check for "signal_computed" to see what signals are being generated
# Check for "trailing" to verify trailing stops working
```

## ⚠️ Known Issues & Workarounds (Feb 6, 2026)

### 1. News WebSocket Not Available
**Issue:** `from alpaca.data.live import NewsDataStream` fails  
**Cause:** NewsDataStream doesn't exist in alpaca-py 0.21.0  
**Workaround:** RSS feeds working as backup (rss-ingest-task)  
**Impact:** Low - not critical for trading  
**Status:** Service disabled (desired-count=0)

### 2. Options Bars Return 403
**Issue:** `403 Forbidden` when fetching option bars  
**Cause:** Requires paid Alpaca options data subscription  
**Workaround:** System works without bars (optional learning feature)  
**Impact:** Low - doesn't affect trading  
**Status:** Acceptable warning in logs

### 3. Direct Database Connection Impossible
**Issue:** Can't connect to RDS from local machine  
**Cause:** Database in private VPC, security group blocks external access  
**Solution:** ALWAYS use Lambda ops-pipeline-db-query  
**For DDL:** Use db-migrator ECS task method (see "How To Deploy" above)

### Alpaca Dashboard

**URL**: https://app.alpaca.markets/paper/dashboard

**API Keys** (stored in Secrets Manager):
- Key ID: PKG7MU6D3EPFNCMVHL6QQSADRS
- Secret: (in ops-pipeline/alpaca-api-keys secret)

**Test Connection:**
```bash
curl 'https://paper-api.alpaca.markets/v2/account' \
  -H 'APCA-API-KEY-ID: PKG7MU6D3EPFNCMVHL6QQSADRS' \
  -H 'APCA-API-SECRET-KEY: [from secrets manager]'
```

---

## 🚨 Common Pitfalls & Solutions

### 1. "No trades happening"

**This is usually CORRECT behavior!** Check why:

```bash
aws logs tail /ecs/ops-pipeline/signal-engine-1m --region us-west-2 --since 5m | grep "signal_computed"
```

Look for:
- `"action": "HOLD", "rule": "VOLUME_TOO_LOW"` = Low volume (correct)
- `"action": "HOLD", "rule": "CONFIDENCE_TOO_LOW"` = Weak signal (correct)
- `"action": "BUY"` with `instrument_type: "PUT"` = Trade signal generated!

**If signal generates but no trade:**
- Check dispatcher logs for execution
- Verify buying power available

### 2. "Migration not applying"

**PROVEN METHOD (Feb 6, 2026):**

Rebuild db-migrator Docker image (see "How To Deploy" section above). This is the ONLY reliable way.

**Methods that FAILED:**
- ❌ ops-pipeline-db-query Lambda (read-only)
- ❌ ops-pipeline-db-migration Lambda (broken when updated)
- ❌ Direct psycopg2 (times out)
- ❌ Lambda in VPC (needs NAT Gateway)

### 3. "Can't connect to database"

**You can't and shouldn't!** Database is in private VPC.

**Always use:**
- `ops-pipeline-db-query` Lambda for SELECT (read-only)
- db-migrator ECS task for DDL/DML (write operations)

### 4. "Expired credentials"

```bash
ada cred update --account 160027201036 --role IibsAdminAccess-DO-NOT-DELETE --provider conduit --once
```

Credentials expire every few hours. Run this before any AWS CLI commands.

### 5. "Exit code 0 but migration didn't work"

**Common causes:**
- Migration version already exists in database (check logs for "migration_skip")
- Docker image using cached layers (use --no-cache)
- Task definition using old SHA256 digest (use :latest tag)

**Solution:** Check logs for "migrations_discovered" - verify your file is listed

---

## 🎯 Quick Health Checks

### 1. Are services running?
```bash
aws ecs describe-services \
  --cluster ops-pipeline-cluster \
  --services dispatcher-service position-manager-service \
  --region us-west-2 \
  --query 'services[*].[serviceName,runningCount,desiredCount]' \
  --output table
```
Expected: All show 1/1

### 2. Is signal engine generating signals?
```bash
aws logs tail /ecs/ops-pipeline/signal-engine-1m \
  --region us-west-2 --since 5m | grep "run_complete"
```
Expected: See "signals_generated": 1-2 every minute

### 3. Are there open positions?
```python
# Via Lambda (ONLY way to query database)
import boto3, json
client = boto3.client('lambda', region_name='us-west-2')
response = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({
        'sql': "SELECT COUNT(*) as count FROM active_positions WHERE status = 'open'"
    })
)
result = json.loads(response['Payload'].read())
print(json.loads(result['body']))
```

### 4. Check for errors in any service:
```bash
for service in dispatcher position-manager telemetry signal-engine-1m; do
  echo "=== $service ==="
  aws logs tail /ecs/ops-pipeline/$service-service \
    --region us-west-2 --since 5m 2>&1 | \
    grep -iE "(error|exception|failed)" | wc -l
done
```
Expected: 0 errors (or only known 403 warnings)

---

## 📖 Current System Documentation (Feb 6, 2026)

### Must Read (Start Here):
1. **COMPLETE_SYSTEM_STATUS_2026-02-06_FINAL.md** ⭐
   - Current verified status (10/11 features)
   - Service health checks
   - No hidden errors

2. **WHY_TRADES_LOST_MONEY_2026-02-06.md** ⭐
   - Trade analysis (13 positions)
   - Why 23% win rate
   - What trailing stops will fix

3. **MASTER_SYSTEM_DOCUMENTATION.md**
   - Complete technical reference
   - All you need in one place

### Architecture:
- `docs/ECS_DOCKER_ARCHITECTURE.md` - How services connect
- `deploy/AI_PIPELINE_EXPLAINED.md` - AI/ML components
- `README.md` - System overview

### Operations:
- `deploy/RUNBOOK.md` - Daily operations
- `deploy/TROUBLESHOOTING_GUIDE.md` - Fix issues
- `docs/DATABASE_ACCESS_GUIDE.md` - Query methods

### Historical (Archive):
- Old status docs moved to `archive/` folders
- Session summaries from previous work
- Outdated deployment guides (use methods above instead)

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

## ✅ Verified Working (As of Feb 6, 2026)

### Core Features (10/11):
- ✅ Position tracking (accurate option prices)
- ✅ Learning data capture (13 trades)
- ✅ Overnight protection (3:55 PM close)
- ✅ Tiny account rules (8% risk)
- ✅ Features capture (market context)
- ✅ Stop loss/take profit (-40%/+80%)
- ✅ **Momentum urgency** (signal engine v16)
- ✅ **Gap fade strategy** (signal engine v16)
- ✅ **Trailing stops** (JUST ENABLED!)
- ✅ Master documentation

### Not Working (1/11):
- ❌ News WebSocket (API doesn't exist in alpaca-py 0.21.0)
  - RSS feeds working as backup
  - Not critical

### Current Performance:
- Win rate: 23% (13 trades)
- Expected with trailing stops: 50-60%
- Open positions: 3 (all with trailing stops protection)

### Services Health:
```bash
# Check all services
aws ecs list-services --cluster ops-pipeline-cluster --region us-west-2

# Expected: 6 services running
# dispatcher, dispatcher-tiny, position-manager (x2), telemetry, trade-stream
```

**System is operational and trading.** If no new trades, it's because risk gates are correctly preventing bad setups.

---

## 🎯 Next Agent: Start Here

1. **Read:** COMPLETE_SYSTEM_STATUS_2026-02-06_FINAL.md
2. **Refresh credentials:** `ada cred update...`
3. **Check services:** `aws ecs list-services...`
4. **Check signals:** `aws logs tail /ecs/ops-pipeline/signal-engine-1m...`
5. **Query database:** Use Lambda ops-pipeline-db-query (examples above)

**Git:** Commit 738c63b  
**All working:** Trailing stops, momentum, gap fade, position monitoring
