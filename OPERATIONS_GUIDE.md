# Operations Guide - Deploy, Monitor, Troubleshoot
**Last Updated:** February 6, 2026, 19:52 UTC  
**For:** System operators, developers, AI agents

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Daily Operations](#daily-operations)
3. [Deploying Code Changes](#deploying-code-changes)
4. [Deploying Database Changes](#deploying-database-changes)
5. [Monitoring & Health Checks](#monitoring--health-checks)
6. [Troubleshooting](#troubleshooting)
7. [Common Tasks](#common-tasks)
8. [Emergency Procedures](#emergency-procedures)

---

## Prerequisites

### AWS Credentials

**REQUIRED FIRST STEP:**

```bash
# Refresh credentials (expire every few hours)
ada cred update --account 160027201036 --role IibsAdminAccess-DO-NOT-DELETE --provider conduit --once
```

Run this before ANY AWS CLI command. Credentials expire every ~4 hours.

### Required Tools

```bash
# Check tools installed
aws --version        # AWS CLI
docker --version     # Docker
jq --version         # JSON processor
python3 --version    # Python 3.11+
```

### AWS Configuration

```bash
# Verify correct region
aws configure get region
# Should output: us-west-2

# If not set:
aws configure set region us-west-2
```

---

## Daily Operations

### Morning Checklist

```bash
# 1. Refresh credentials
ada cred update --account 160027201036 --role IibsAdminAccess-DO-NOT-DELETE --provider conduit --once

# 2. Check all services running
aws ecs list-services --cluster ops-pipeline-cluster --region us-west-2

# 3. Verify signal generation
aws logs tail /ecs/ops-pipeline/signal-engine-1m --region us-west-2 --since 5m | grep "run_complete"

# 4. Check for errors
for service in dispatcher position-manager telemetry trade-stream; do
  echo "=== $service ==="
  aws logs tail /ecs/ops-pipeline/$service-service --region us-west-2 --since 10m | grep -iE "(error|exception)" | wc -l
done

# 5. Check open positions
python3 scripts/query_via_lambda.py
```

### End of Day Checklist

```bash
# 1. Verify all positions closed (3:55 PM ET close)
python3 -c "
import boto3, json
client = boto3.client('lambda', region_name='us-west-2')
response = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({
        'sql': \"SELECT COUNT(*) FROM active_positions WHERE status = 'open'\"
    })
)
result = json.loads(response['Payload'].read())
data = json.loads(result['body'])
print(f\"Open positions: {data['rows'][0]['count']}\")
"

# 2. Review today's trades
python3 check_recent_trades.py

# 3. Check service health
aws ecs describe-services \
  --cluster ops-pipeline-cluster \
  --services dispatcher-service position-manager-service \
  --region us-west-2 \
  --query 'services[*].[serviceName,runningCount,desiredCount]'
```

---

## Deploying Code Changes

### Option A: Service Code (Persistent Services)

Example: Update dispatcher logic

```bash
# 1. Navigate to service directory
cd services/dispatcher

# 2. Build Docker image
docker build -t 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/dispatcher:latest .

# 3. Login to ECR
aws ecr get-login-password --region us-west-2 | \
  docker login --username AWS --password-stdin \
  160027201036.dkr.ecr.us-west-2.amazonaws.com

# 4. Push image
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/dispatcher:latest

# 5. Force service to use new image
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service dispatcher-service \
  --force-new-deployment \
  --region us-west-2

# 6. Monitor deployment
aws ecs describe-services \
  --cluster ops-pipeline-cluster \
  --services dispatcher-service \
  --region us-west-2 \
  --query 'services[0].deployments'

# 7. Check logs for new deployment
aws logs tail /ecs/ops-pipeline/dispatcher-service \
  --region us-west-2 --since 2m --follow
```

### Option B: Scheduled Task Code (Signal Engine, etc.)

Example: Update signal engine

```bash
# 1. Build and push image (same as above)
cd services/signal_engine_1m
docker build -t 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/signal-engine-1m:latest .
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/signal-engine-1m:latest

# 2. Get current task definition
aws ecs describe-task-definition \
  --task-definition ops-pipeline-signal-engine-1m \
  --region us-west-2 \
  --query 'taskDefinition' > /tmp/task-def.json

# 3. Update image to :latest and clean metadata
jq 'del(.taskDefinitionArn, .revision, .status, .requiresAttributes, .compatibilities, .registeredAt, .registeredBy) | 
    .containerDefinitions[0].image = "160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/signal-engine-1m:latest"' \
    /tmp/task-def.json > /tmp/task-def-new.json

# 4. Register new task definition
aws ecs register-task-definition \
  --cli-input-json file:///tmp/task-def-new.json \
  --region us-west-2

# 5. Get new revision number
NEW_REV=$(aws ecs describe-task-definition \
  --task-definition ops-pipeline-signal-engine-1m \
  --region us-west-2 \
  --query 'taskDefinition.revision' \
  --output text)

# 6. Update EventBridge schedule
aws scheduler update-schedule \
  --name ops-pipeline-signal-engine-1m-schedule \
  --region us-west-2 \
  --target "
  {
    \"Arn\": \"arn:aws:ecs:us-west-2:160027201036:cluster/ops-pipeline-cluster\",
    \"RoleArn\": \"arn:aws:iam::160027201036:role/ops-pipeline-eventbridge-scheduler-role\",
    \"EcsParameters\": {
      \"TaskDefinitionArn\": \"arn:aws:ecs:us-west-2:160027201036:task-definition/ops-pipeline-signal-engine-1m:${NEW_REV}\",
      \"LaunchType\": \"FARGATE\",
      \"NetworkConfiguration\": {
        \"awsvpcConfiguration\": {
          \"Subnets\": [\"subnet-0c182a149eeef918a\"],
          \"SecurityGroups\": [\"sg-0cd16a909f4e794ce\"],
          \"AssignPublicIp\": \"ENABLED\"
        }
      }
    }
  }"

# 7. Verify next run uses new version
aws logs tail /ecs/ops-pipeline/signal-engine-1m \
  --region us-west-2 --since 2m --follow
```

---

## Deploying Database Changes

### CRITICAL: Only ONE Method Works

**✅ CORRECT: db-migrator ECS Task**

```bash
# 1. Create migration file
cat > services/db_migrator/migrations/1003_my_feature.sql << 'EOF'
-- Migration: Add my new feature
-- Version: 1003
-- Date: 2026-02-06

ALTER TABLE active_positions
ADD COLUMN IF NOT EXISTS my_new_column VARCHAR(50);

-- Verify
SELECT column_name FROM information_schema.columns 
WHERE table_name = 'active_positions' AND column_name = 'my_new_column';
EOF

# 2. Rebuild db-migrator Docker image from project root
cd /home/nflos/workplace/inbound_aigen
docker build --no-cache \
  -f services/db_migrator/Dockerfile \
  -t 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/db-migrator:latest .

# 3. Push to ECR
aws ecr get-login-password --region us-west-2 | \
  docker login --username AWS --password-stdin \
  160027201036.dkr.ecr.us-west-2.amazonaws.com
  
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/db-migrator:latest

# 4. Create task definition with :latest tag
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

# 5. Register task definition
aws ecs register-task-definition \
  --cli-input-json file:///tmp/migrator-latest.json \
  --region us-west-2

# 6. Run migration task
TASK_ARN=$(aws ecs run-task \
  --cluster ops-pipeline-cluster \
  --task-definition ops-pipeline-db-migrator \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-0c182a149eeef918a],securityGroups=[sg-0cd16a909f4e794ce],assignPublicIp=ENABLED}" \
  --region us-west-2 \
  --query 'tasks[0].taskArn' \
  --output text)

echo "Migration task: $TASK_ARN"

# 7. Wait for completion (2-3 minutes)
aws ecs wait tasks-stopped \
  --cluster ops-pipeline-cluster \
  --tasks $TASK_ARN \
  --region us-west-2

# 8. Check exit code
aws ecs describe-tasks \
  --cluster ops-pipeline-cluster \
  --tasks $TASK_ARN \
  --region us-west-2 \
  --query 'tasks[0].containers[0].exitCode'
# Should be 0 for success

# 9. View logs
aws logs tail /ecs/ops-pipeline/db-migrator \
  --region us-west-2 --since 5m

# 10. Verify columns added
python3 -c "
import boto3, json
client = boto3.client('lambda', region_name='us-west-2')
response = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({
        'sql': \"SELECT column_name FROM information_schema.columns WHERE table_name = 'active_positions' AND column_name = 'my_new_column'\"
    })
)
result = json.loads(response['Payload'].read())
print(json.loads(result['body']))
"
```

### ❌ WRONG Methods (Don't Use)

These will **FAIL** or **TIMEOUT**:

```bash
# ❌ ops-pipeline-db-query Lambda (read-only)
# ❌ Direct psycopg2 connection (no VPC access)
# ❌ Lambda in VPC without NAT Gateway (can't reach Secrets Manager)
# ❌ RDS Query Editor (not available for non-Aurora)
# ❌ Any method besides db-migrator ECS task
```

---

## Monitoring & Health Checks

### Quick Health Check

```bash
# All services status
aws ecs describe-services \
  --cluster ops-pipeline-cluster \
  --services dispatcher-service dispatcher-tiny-service \
             position-manager-service position-manager-tiny-service \
             telemetry-service trade-stream \
  --region us-west-2 \
  --query 'services[*].[serviceName,runningCount,desiredCount,status]' \
  --output table
```

Expected output: All show `1/1` for running/desired, status=ACTIVE

### Check Signal Generation

```bash
# Last 5 minutes of signal engine
aws logs tail /ecs/ops-pipeline/signal-engine-1m \
  --region us-west-2 --since 5m | grep "run_complete"

# Should see entries every minute with:
# - signals_generated: 1-2
# - signals_hold: 10-15
# - watchlist: 30
```

### Check for Errors

```bash
# Count errors in last hour per service
for service in dispatcher position-manager telemetry signal-engine-1m trade-stream; do
  ERROR_COUNT=$(aws logs tail /ecs/ops-pipeline/$service-service \
    --region us-west-2 --since 1h 2>/dev/null | \
    grep -iE "(error|exception|failed)" | wc -l)
  echo "$service: $ERROR_COUNT errors"
done
```

### Database Queries

```python
# Query via Lambda (ONLY method that works)
import boto3, json

def query_db(sql):
    client = boto3.client('lambda', region_name='us-west-2')
    response = client.invoke(
        FunctionName='ops-pipeline-db-query',
        Payload=json.dumps({'sql': sql})
    )
    result = json.loads(response['Payload'].read())
    return json.loads(result['body'])['rows']

# Check open positions
rows = query_db("SELECT * FROM active_positions WHERE status = 'open' LIMIT 5")
for row in rows:
    print(f"{row['ticker']}: P&L {row['pnl_pct']:.1f}%")

# Check today's executions
rows = query_db("""
    SELECT ticker, instrument_type, action, confidence 
    FROM dispatch_executions 
    WHERE simulated_ts::date = CURRENT_DATE 
    ORDER BY simulated_ts DESC LIMIT 10
""")
```

### View Recent Trades

```bash
python3 check_recent_trades.py
```

### Alpaca Dashboard

**URL:** https://app.alpaca.markets/paper/dashboard

**Check:**
- Account balance
- Open positions
- Recent orders
- Buying power

---

## Troubleshooting

### Problem: "No trades happening"

**This is usually CORRECT behavior!**

**Debug steps:**

```bash
# 1. Check signals being generated
aws logs tail /ecs/ops-pipeline/signal-engine-1m \
  --region us-west-2 --since 5m | grep "signal_computed"

# Look for:
# - action: "HOLD", rule: "VOLUME_TOO_LOW" = Volume < 0.5x (correct)
# - action: "HOLD", rule: "CONFIDENCE_TOO_LOW" = Weak signal (correct)
# - action: "BUY" = Trade signal generated!

# 2. If signal generated, check dispatcher
aws logs tail /ecs/ops-pipeline/dispatcher-service \
  --region us-west-2 --since 5m | grep -E "(execution|buying_power)"

# 3. Check risk gates
aws logs tail /ecs/ops-pipeline/dispatcher-service \
  --region us-west-2 --since 5m | grep "gate"
```

### Problem: "Migration not applying"

**Solution:** Use db-migrator ECS task (see "Deploying Database Changes" above)

**Common mistakes:**
- Using cached Docker image (use `--no-cache`)
- Using old task definition (use `:latest` tag)
- Migration version already exists (check logs)

**Debug:**

```bash
# Check logs for "migrations_discovered"
aws logs tail /ecs/ops-pipeline/db-migrator \
  --region us-west-2 --since 10m

# Look for your migration file listed
# If not listed, Docker image wasn't rebuilt correctly
```

### Problem: "Can't connect to database"

**You can't and shouldn't!** Database is in private VPC.

**Solution:** ALWAYS use Lambda

```python
import boto3, json

client = boto3.client('lambda', region_name='us-west-2')
response = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'sql': 'SELECT NOW()'})
)
result = json.loads(response['Payload'].read())
print(json.loads(result['body']))
```

### Problem: "Service won't start"

**Check:**

```bash
# 1. Task definition valid?
aws ecs describe-task-definition \
  --task-definition ops-pipeline-dispatcher \
  --region us-west-2

# 2. Docker image exists in ECR?
aws ecr describe-images \
  --repository-name ops-pipeline/dispatcher \
  --region us-west-2 \
  --query 'imageDetails[0]'

# 3. Service has correct task definition?
aws ecs describe-services \
  --cluster ops-pipeline-cluster \
  --services dispatcher-service \
  --region us-west-2 \
  --query 'services[0].taskDefinition'

# 4. Check recent events
aws ecs describe-services \
  --cluster ops-pipeline-cluster \
  --services dispatcher-service \
  --region us-west-2 \
  --query 'services[0].events[0:5]'
```

### Problem: "Expired credentials"

**Solution:**

```bash
ada cred update --account 160027201036 --role IibsAdminAccess-DO-NOT-DELETE --provider conduit --once
```

Run this every ~4 hours or before any AWS CLI command.

---

## Common Tasks

### Restart a Service

```bash
# Force new deployment (rolling restart)
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service dispatcher-service \
  --force-new-deployment \
  --region us-west-2
```

### Stop a Service

```bash
# Set desired count to 0
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service dispatcher-service \
  --desired-count 0 \
  --region us-west-2
```

### Start a Service

```bash
# Set desired count to 1
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service dispatcher-service \
  --desired-count 1 \
  --region us-west-2
```

### View Logs (Live)

```bash
# Follow logs in real-time
aws logs tail /ecs/ops-pipeline/signal-engine-1m \
  --region us-west-2 --since 5m --follow
```

### Search Logs

```bash
# Find specific errors
aws logs tail /ecs/ops-pipeline/position-manager-service \
  --region us-west-2 --since 1h | \
  grep -i "trailing_stop"
```

### List All ECR Images

```bash
# See all service images
aws ecr describe-repositories \
  --region us-west-2 \
  --query 'repositories[*].repositoryName' \
  --output table
```

---

## Emergency Procedures

### Emergency Stop All Trading

```bash
# Stop both dispatchers
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service dispatcher-service \
  --desired-count 0 \
  --region us-west-2

aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service dispatcher-tiny-service \
  --desired-count 0 \
  --region us-west-2

# Verify stopped
aws ecs describe-services \
  --cluster ops-pipeline-cluster \
  --services dispatcher-service dispatcher-tiny-service \
  --region us-west-2 \
  --query 'services[*].[serviceName,runningCount]'
```

### Emergency Close All Positions

**Use Alpaca Dashboard:**
1. Go to https://app.alpaca.markets/paper/dashboard
2. Navigate to Positions tab
3. Click "Close All" button

### Rollback Service to Previous Version

```bash
# 1. List recent task definition versions
aws ecs list-task-definitions \
  --family-prefix ops-pipeline-dispatcher \
  --region us-west-2 \
  --sort DESC \
  --max-items 5

# 2. Update service to previous version
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service dispatcher-service \
  --task-definition ops-pipeline-dispatcher:PREVIOUS_REVISION \
  --region us-west-2
```

### Check System After Outage

```bash
# 1. All services running?
aws ecs list-services --cluster ops-pipeline-cluster --region us-west-2

# 2. Any stuck positions?
python3 -c "
import boto3, json
client = boto3.client('lambda', region_name='us-west-2')
response = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({
        'sql': \"SELECT * FROM active_positions WHERE status = 'open' AND last_check_ts < NOW() - INTERVAL '10 minutes'\"
    })
)
result = json.loads(response['Payload'].read())
print(json.loads(result['body']))
"

# 3. Recent errors?
for service in dispatcher position-manager telemetry; do
  aws logs tail /ecs/ops-pipeline/$service-service \
    --region us-west-2 --since 30m | grep -i error
done
```

---

## Key Files for Operations

**Task Definitions:** `deploy/*-task-definition.json`  
**Deployment Scripts:** `scripts/deploy_*.sh`  
**Health Checks:** `scripts/comprehensive_health_check.py`  
**Database Queries:** `scripts/query_via_lambda.py`  
**Trade Verification:** `check_recent_trades.py`

---

## Multi-Account Configuration

### How Services Choose Accounts

**The system supports TWO Alpaca paper trading accounts:**

1. **Large Account** - $121K capital, tier-based sizing (5-20%)
2. **Tiny Account** - $1K capital, fixed 8% sizing (learning environment)

**Configuration Method:**

Services use the `ACCOUNT_NAME` environment variable to determine which Alpaca account to connect to:

```bash
# In ECS task definition
"environment": [
  {
    "name": "ACCOUNT_NAME",
    "value": "tiny"  # or "large"
  }
]
```

### Secrets Manager Organization

**Two separate Alpaca API key secrets:**

```
ops-pipeline/alpaca       → Large account credentials
ops-pipeline/alpaca/tiny  → Tiny account credentials
```

**How services load credentials:**

```python
# From services/position_manager/config.py
account_name = os.environ.get('ACCOUNT_NAME', 'large')

if account_name == 'tiny':
    alpaca_secret_id = 'ops-pipeline/alpaca/tiny'
else:
    alpaca_secret_id = 'ops-pipeline/alpaca'

# Load the appropriate secret
alpaca_secret = secrets.get_secret_value(SecretId=alpaca_secret_id)
```

**Services using multi-account pattern:**
- position-manager-service (ACCOUNT_NAME=large)
- position-manager-tiny-service (ACCOUNT_NAME=tiny)
- dispatcher-service (ACCOUNT_NAME=large)
- dispatcher-tiny-service (ACCOUNT_NAME=tiny)

### Troubleshooting Account Issues

**Problem: Service connecting to wrong account**

**Symptoms:**
- position-manager-tiny says "No positions found in Alpaca"
- But Alpaca dashboard shows positions
- Positions not being monitored

**Solution:**
1. Check task definition has correct ACCOUNT_NAME:
```bash
aws ecs describe-task-definition \
  --task-definition position-manager-tiny-service \
  --region us-west-2 \
  --query 'taskDefinition.containerDefinitions[0].environment'
```

2. Verify config.py checks ACCOUNT_NAME:
```bash
grep -A5 "ACCOUNT_NAME" services/position_manager/config.py
```

3. Rebuild and redeploy if config was fixed:
```bash
cd services/position_manager
docker build -t 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/position-manager:latest .
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/position-manager:latest

# Restart BOTH services (they share the same image)
aws ecs update-service --cluster ops-pipeline-cluster --service position-manager-service --force-new-deployment --region us-west-2
aws ecs update-service --cluster ops-pipeline-cluster --service position-manager-tiny-service --force-new-deployment --region us-west-2
```

**Verify fix worked:**
```bash
# Check tiny account logs
aws logs tail /ecs/ops-pipeline/position-manager-tiny --since 2m --region us-west-2 | grep "Found.*position"

# Should see: "Found 4 position(s) in Alpaca" (not "No positions")
```

### Database Account Filtering

**All tables have `account_name` column:**

```sql
-- Get positions for specific account
SELECT * FROM active_positions WHERE account_name = 'tiny';

-- Get executions for specific account  
SELECT * FROM dispatch_executions WHERE account_name = 'large';
```

**Services filter by their ACCOUNT_NAME:**
- position-manager-tiny only monitors `account_name='tiny'` positions
- position-manager-service only monitors `account_name='large'` positions
- Each dispatcher writes its account_name when creating positions

---

## Quick Reference

**AWS Account:** 160027201036  
**Region:** us-west-2  
**ECS Cluster:** ops-pipeline-cluster  
**RDS Endpoint:** ops-pipeline-db.cls4wuyg010k.us-west-2.rds.amazonaws.com  
**VPC:** vpc-0444cb2b7a3457502  
**Log Group Prefix:** /ecs/ops-pipeline/  
**Alpaca Dashboard:** https://app.alpaca.markets/paper/dashboard
**Alpaca Secrets:** ops-pipeline/alpaca (large), ops-pipeline/alpaca/tiny

---

**Remember: Always refresh AWS credentials before operations!**
