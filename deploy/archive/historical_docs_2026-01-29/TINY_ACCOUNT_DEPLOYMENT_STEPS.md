# Tiny Account Deployment - Exact Steps

**Status:** 50% Complete  
**Remaining:** 1-1.5 hours  
**Complexity:** Medium (broker update + DB migration + deployment)

---

## What's Done ✅

1. ✅ Tiny account credentials stored in Secrets Manager
2. ✅ config.py modified to read tier-specific secrets
3. ✅ account_name and credentials added to config dict

---

## What's Needed (Step-by-Step)

### Step 1: Update main.py to Use Config Credentials (15 min)

**File:** `services/dispatcher/main.py`

**Find this section** (around line 80-90):
```python
alpaca_key = ssm.get_parameter(
    Name='/ops-pipeline/alpaca_key_id',
    WithDecryption=True
)['Parameter']['Value']

alpaca_secret = ssm.get_parameter(
    Name='/ops-pipeline/alpaca_secret_key',
    WithDecryption=True
)['Parameter']['Value']

alpaca_config = {
    **config,
    'alpaca_key_id': alpaca_key,
    'alpaca_secret_key': alpaca_secret
}
```

**Replace with:**
```python
# MULTI-ACCOUNT: Use credentials from config (already loaded tier-specific)
alpaca_config = {
    **config,
    'alpaca_key_id': config['alpaca_api_key'],
    'alpaca_secret_key': config['alpaca_api_secret']
}

# Log which account we're using
print(f"Initializing broker for account: {config.get('account_name', 'unknown')}")
```

###

 Step 2: Add Database Migration (15 min)

**File:** `db/migrations/012_add_account_tracking.sql`

```sql
-- Add account tracking to dispatch_executions
ALTER TABLE dispatch_executions 
ADD COLUMN IF NOT EXISTS account_name VARCHAR(50);

-- Add index for queries
CREATE INDEX IF NOT EXISTS idx_dispatch_executions_account_name 
ON dispatch_executions(account_name, simulated_ts DESC);

-- Account metadata table
CREATE TABLE IF NOT EXISTS account_metadata (
    account_name VARCHAR(50) PRIMARY KEY,
    tier VARCHAR(20) NOT NULL,
    alpaca_account_id VARCHAR(100),
    initial_balance DECIMAL(12,2) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT
);

-- Insert known accounts
INSERT INTO account_metadata (account_name, tier, initial_balance, notes)
VALUES 
    ('tiny-1k', 'tiny', 1000.00, 'Aggressive growth testing (25% risk)'),
    ('large-100k', 'large', 100000.00, 'Professional tier testing (1% risk)')
ON CONFLICT (account_name) DO NOTHING;
```

**Apply:**
```bash
# Create apply script
cat > scripts/apply_migration_012.py << 'EOF'
import boto3, json

client = boto3.client('lambda', region_name='us-west-2')

with open('db/migrations/012_add_account_tracking.sql') as f:
    sql = f.read()

r = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'sql': sql})
)

result = json.loads(json.load(r['Payload'])['body'])
print(json.dumps(result, indent=2))
EOF

python3 scripts/apply_migration_012.py
```

### Step 3: Update Execution Recording (15 min)

**File:** `services/dispatcher/db/repositories.py`

**Find:** `create_execution()` function

**Add:** `account_name` parameter and insert it:

```python
def create_execution(
    conn,
    run_id: str,
    recommendation_id: int,
    ticker: str,
    action: str,
    # ... existing params ...
    account_name: str = None  # NEW
):
    """Record execution with account tracking"""
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO dispatch_executions (
            run_id, recommendation_id, ticker, action,
            contracts, notional, simulated_ts,
            account_name  -- NEW
            -- ... other fields ...
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, ...)
    """, (run_id, recommendation_id, ticker, action,
          contracts, notional, simulated_ts,
          account_name,  # NEW
          ...))
```

**In main.py where create_execution is called:**

Add `account_name=config.get('account_name')` to the call.

### Step 4: Build New Image with Multi-Account Support (10 min)

```bash
cd /home/nflos/workplace/inbound_aigen/services/dispatcher

docker build --no-cache -t ops-pipeline/dispatcher:multi-account .

docker tag ops-pipeline/dispatcher:multi-account 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/dispatcher:multi-account

aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin 160027201036.dkr.ecr.us-west-2.amazonaws.com

docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/dispatcher:multi-account

# Note the SHA256 from output
```

### Step 5: Create Tiny Account Task Definition (10 min)

**File:** `deploy/dispatcher-task-definition-tiny.json`

```json
{
  "family": "ops-pipeline-dispatcher-tiny",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "executionRoleArn": "arn:aws:iam::160027201036:role/ops-pipeline-ecs-task-role",
  "taskRoleArn": "arn:aws:iam::160027201036:role/ops-pipeline-ecs-task-role",
  "containerDefinitions": [
    {
      "name": "dispatcher",
      "image": "160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/dispatcher@sha256:NEW_SHA256_HERE",
      "essential": true,
      "environment": [
        {"name": "AWS_REGION", "value": "us-west-2"},
        {"name": "EXECUTION_MODE", "value": "ALPACA_PAPER"},
        {"name": "ACCOUNT_TIER", "value": "tiny"}
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/ops-pipeline/dispatcher-tiny",
          "awslogs-region": "us-west-2",
          "awslogs-stream-prefix": "dispatcher-tiny",
          "awslogs-create-group": "true"
        }
      }
    }
  ]
}
```

**Register:**
```bash
aws ecs register-task-definition \
  --cli-input-json file:///home/nflos/workplace/inbound_aigen/deploy/dispatcher-task-definition-tiny.json \
  --region us-west-2 \
  --query 'taskDefinition.revision'

# Returns: 1 (first revision for tiny family)
```

### Step 6: Also Update Large Account (10 min)

**File:** `deploy/dispatcher-task-definition.json` (existing)

Update to same new SHA256 so both accounts use same code:

```bash
# Edit dispatcher-task-definition.json with new SHA256
aws ecs register-task-definition \
  --cli-input-json file:///home/nflos/workplace/inbound_aigen/deploy/dispatcher-task-definition.json \
  --region us-west-2 \
  --query 'taskDefinition.revision'

# Returns: 16

# Update large account scheduler
aws scheduler update-schedule \
  --name ops-pipeline-dispatcher \
  --region us-west-2 \
  --schedule-expression "rate(1 minute)" \
  --flexible-time-window Mode=OFF \
  --target '{
    "Arn": "arn:aws:ecs:us-west-2:160027201036:cluster/ops-pipeline-cluster",
    "RoleArn": "arn:aws:iam::160027201036:role/ops-pipeline-eventbridge-ecs-role",
    "EcsParameters": {
      "TaskDefinitionArn": "arn:aws:ecs:us-west-2:160027201036:task-definition/ops-pipeline-dispatcher:16",
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

### Step 7: Create Tiny Account Scheduler (15 min)

```bash
aws scheduler create-schedule \
  --name ops-pipeline-dispatcher-tiny \
  --schedule-expression "rate(5 minutes)" \
  --flexible-time-window Mode=OFF \
  --target '{
    "Arn": "arn:aws:ecs:us-west-2:160027201036:cluster/ops-pipeline-cluster",
    "RoleArn": "arn:aws:iam::160027201036:role/ops-pipeline-eventbridge-ecs-role",
    "EcsParameters": {
      "TaskDefinitionArn": "arn:aws:ecs:us-west-2:160027201036:task-definition/ops-pipeline-dispatcher-tiny:1",
      "LaunchType": "FARGATE",
      "NetworkConfiguration": {
        "awsvpcConfiguration": {
          "Subnets": ["subnet-0c182a149eeef918a"],
          "SecurityGroups": ["sg-0cd16a909f4e794ce"],
          "AssignPublicIp": "ENABLED"
        }
      }
    },
    "RetryPolicy": {
      "MaximumEventAgeInSeconds": 86400,
      "MaximumRetryAttempts": 185
    }
  }' \
  --region us-west-2
```

### Step 8: Verify Both Accounts Running (10 min)

```bash
# 1. Check schedulers
aws scheduler list-schedules --region us-west-2 | grep dispatcher

# 2. Wait 1-2 minutes, check logs

# Large account
aws logs tail /ecs/ops-pipeline/dispatcher --region us-west-2 --since 2m | grep -E "(account_name|Tier:)"

# Tiny account  
aws logs tail /ecs/ops-pipeline/dispatcher-tiny --region us-west-2 --since 2m | grep -E "(account_name|Tier:)"

# 3. Check database
python3 << 'EOF'
import boto3, json
client = boto3.client('lambda', region_name='us-west-2')
r = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'sql': """
        SELECT account_name, COUNT(*) as count
        FROM dispatch_executions
        WHERE simulated_ts > NOW() - INTERVAL '10 minutes'
        GROUP BY account_name
    """})
)
print(json.loads(json.load(r['Payload'])['body']))
EOF
```

---

## Expected Results

### Tiny Account Logs Should Show:

```
Loaded tiny account credentials: tiny-1k
Initializing broker for account: tiny-1k
Connected to Alpaca Paper Trading
  Account: PA3PBOQAH7ZY (different from large)
  Buying power: $1000.00
  Cash: $1000.00

Tier: tiny, Strategy: day_trade, Risk: 25.0% of $1000 = $250
Premium: $2.50 × 100 = $250/contract
Contracts: 1 (cap: 2)
Total: $250

Selected contract with quality score: 75.2/100
  Strike: $520.0, Spread: 1.5%, Volume: 450, Delta: 0.35
```

### Database Should Show:

```sql
SELECT account_name, COUNT(*) as trades
FROM dispatch_executions
WHERE simulated_ts::date = CURRENT_DATE
GROUP BY account_name;

-- Result:
-- account_name  | trades
-- large-100k    | 28
-- tiny-1k       | 5
```

---

## Troubleshooting

### Issue: Tiny account not loading credentials

**Check:**
```bash
# Verify secret exists
aws secretsmanager describe-secret \
  --secret-id ops-pipeline/alpaca/tiny \
  --region us-west-2

# Check logs for error
aws logs tail /ecs/ops-pipeline/dispatcher-tiny \
  --region us-west-2 \
  --since 5m \
  | grep -i error
```

### Issue: Database migration fails

**Symptom:** Column already exists error

**Fix:**
```sql
-- Check if column exists
SELECT column_name 
FROM information_schema.columns 
WHERE table_name = 'dispatch_executions' 
    AND column_name = 'account_name';

-- If exists, skip ALTER TABLE
-- Just create index and metadata table
```

---

## Files to Modify

**Required changes:**

1. ✅ `services/dispatcher/config.py` - DONE
2. ⏳ `services/dispatcher/main.py` - Update alpaca_config
3. ⏳ `services/dispatcher/db/repositories.py` - Add account_name param
4. ⏳ `db/migrations/012_add_account_tracking.sql` - Create
5. ⏳ `deploy/dispatcher-task-definition-tiny.json` - Create
6. ⏳ `deploy/dispatcher-task-definition.json` - Update SHA256

**Build & Deploy:**
7. ⏳ Build revision 16
8. ⏳ Register both task definitions
9. ⏳ Update large scheduler
10. ⏳ Create tiny scheduler
11. ⏳ Test both

---

## Time Estimate

| Step | Time | Cumulative |
|------|------|------------|
| Update main.py | 15 min | 15 min |
| Add DB migration | 15 min | 30 min |
| Apply migration | 5 min | 35 min |
| Update repositories.py | 15 min | 50 min |
| Create tiny task def | 10 min | 60 min |
| Build & push image | 10 min | 70 min |
| Register task defs | 5 min | 75 min |
| Create/update schedulers | 10 min | 85 min |
| Test & verify | 10 min | 95 min |

**Total: 1.5 hours**

---

## Quick Test Alternative (30 min)

**Don't want full deployment? Just test tiny account credentials:**

1. Update main.py only (15 min)
2. Build revision 16 (10 min)
3. Run tiny task manually once (5 min):

```bash
# Register tiny task def
aws ecs register-task-definition --cli-input-json file://deploy/dispatcher-task-definition-tiny.json --region us-west-2

# Run once manually
aws ecs run-task \
  --cluster ops-pipeline-cluster \
  --task-definition ops-pipeline-dispatcher-tiny:1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-0c182a149eeef918a],securityGroups=[sg-0cd16a909f4e794ce],assignPublicIp=ENABLED}" \
  --region us-west-2

# Check logs
aws logs tail /ecs/ops-pipeline/dispatcher-tiny --region us-west-2 --since 2m | grep -E "(Loaded tiny|Buying power|Tier:)"
```

Should see:
```
Loaded tiny account credentials: tiny-1k
Buying power: $1000.00
Tier: tiny, Strategy: day_trade, Risk: 25.0% of $1000 = $250
```

---

## Recommendation

**Given session length (2+ hours already):**

**Option A:** Document current state, complete in next session (FRESH START)  
**Option B:** Quick test now (30 min) to prove credentials work  
**Option C:** Full deployment now (1.5 hours) for complete multi-account

**My suggestion: Option A or B**

Phases 1 & 2 are already a huge win. Multi-account can be separate focused session.
