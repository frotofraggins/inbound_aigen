# Multi-Account Paper Trading Design

**Created:** 2026-01-29  
**Priority:** P1 - Enhanced learning and tier validation  
**Estimated Time:** 2-3 hours implementation  
**Status:** Design phase

---

## Goal

Run multiple Alpaca paper trading accounts simultaneously to:
1. Test all 4 account tiers in parallel (tiny, small, medium, large)
2. Compare performance across different account sizes
3. Validate tier-specific logic is working correctly
4. Learn optimal settings for each tier

---

## Architecture Options

### Option 1: Multiple Dispatcher Instances (RECOMMENDED)

**Concept:** Run separate dispatcher scheduler for each account

**Pros:**
- Clean separation of concerns
- Each account fully independent
- Easy to start/stop individual accounts
- No code changes to dispatcher
- Scales easily to N accounts

**Cons:**
- More AWS resources (4x schedulers, 4x task defs)
- Higher cost (~$0.01/hr per account)

**Implementation:**
1. Create 4 task definitions (one per account tier)
2. Store different API keys in Secrets Manager
3. Create 4 EventBridge schedulers
4. Database tracks which account made each trade

### Option 2: Single Dispatcher with Account Rotation

**Concept:** One dispatcher cycles through multiple accounts

**Pros:**
- Single scheduler/task definition
- Lower AWS costs
- Simpler AWS infrastructure

**Cons:**
- More complex code
- Accounts share rate limits
- One account's error affects all
- Harder to debug

**Implementation:**
1. Store multiple API key pairs in config
2. Dispatcher cycles through accounts
3. Track which account is "active" this minute
4. Database stores account_id with each trade

### Option 3: Account Pool with Load Balancing

**Concept:** Dispatcher picks best available account for each signal

**Pros:**
- Optimal account utilization
- Can route signals to appropriate tier
- Advanced learning capabilities

**Cons:**
- Very complex logic
- May not test all tiers equally
- Harder to analyze results

---

## RECOMMENDED APPROACH: Option 1

**Why:** Clean, simple, independent testing of each tier

---

## Implementation Plan - Option 1

### Step 1: Create Secrets for Each Account (15 min)

Store 4 sets of Alpaca API credentials:

```bash
# Tiny account ($1K starting balance)
aws secretsmanager create-secret \
  --name ops-pipeline/alpaca/tiny \
  --region us-west-2 \
  --secret-string '{
    "api_key": "YOUR_TINY_API_KEY",
    "api_secret": "YOUR_TINY_SECRET",
    "account_name": "tiny-1k",
    "initial_balance": 1000
  }'

# Small account ($5K starting balance)
aws secretsmanager create-secret \
  --name ops-pipeline/alpaca/small \
  --region us-west-2 \
  --secret-string '{
    "api_key": "YOUR_SMALL_API_KEY",
    "api_secret": "YOUR_SMALL_SECRET",
    "account_name": "small-5k",
    "initial_balance": 5000
  }'

# Medium account ($25K starting balance)
aws secretsmanager create-secret \
  --name ops-pipeline/alpaca/medium \
  --region us-west-2 \
  --secret-string '{
    "api_key": "YOUR_MEDIUM_API_KEY",
    "api_secret": "YOUR_MEDIUM_SECRET",
    "account_name": "medium-25k",
    "initial_balance": 25000
  }'

# Large account ($100K starting balance) - already exists
aws secretsmanager update-secret \
  --secret-id ops-pipeline/alpaca \
  --region us-west-2 \
  --secret-string '{
    "api_key": "EXISTING_KEY",
    "api_secret": "EXISTING_SECRET",
    "account_name": "large-100k",
    "initial_balance": 100000
  }'
```

### Step 2: Modify Dispatcher to Read Account ID (30 min)

**File:** `services/dispatcher/config.py`

```python
def load_config() -> Dict[str, Any]:
    # ... existing code ...
    
    # Load account-specific credentials
    account_tier = os.environ.get('ACCOUNT_TIER', 'large')  # tiny/small/medium/large
    
    try:
        secret_name = f'ops-pipeline/alpaca/{account_tier}'
        secret_value = secrets.get_secret_value(SecretId=secret_name)
        alpaca_creds = json.loads(secret_value['SecretString'])
    except:
        # Fallback to default secret for backwards compatibility
        secret_value = secrets.get_secret_value(SecretId='ops-pipeline/alpaca')
        alpaca_creds = json.loads(secret_value['SecretString'])
        alpaca_creds['account_name'] = 'default'
    
    return {
        # ... existing config ...
        'alpaca_api_key': alpaca_creds['api_key'],
        'alpaca_api_secret': alpaca_creds['api_secret'],
        'account_name': alpaca_creds.get('account_name', 'default'),
        'account_tier': account_tier,
    }
```

**File:** `services/dispatcher/db/repositories.py`

Add account_name to executions:

```python
def create_execution(..., account_name: str = None):
    """Record execution with account tracking"""
    # ... existing code ...
    
    cursor.execute("""
        INSERT INTO dispatch_executions (
            run_id, recommendation_id, ticker, action,
            contracts, notional, simulated_ts,
            account_name  -- NEW FIELD
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (..., account_name))
```

### Step 3: Create 4 Task Definitions (15 min)

Create separate files for each tier:

```bash
# dispatcher-task-definition-tiny.json
{
  "family": "ops-pipeline-dispatcher-tiny",
  "containerDefinitions": [{
    "name": "dispatcher",
    "image": "...same image...",
    "environment": [
      {"name": "AWS_REGION", "value": "us-west-2"},
      {"name": "EXECUTION_MODE", "value": "ALPACA_PAPER"},
      {"name": "ACCOUNT_TIER", "value": "tiny"}  # NEW
    ]
  }]
}

# Repeat for small, medium, large
```

### Step 4: Register All Task Definitions (5 min)

```bash
for tier in tiny small medium large; do
  aws ecs register-task-definition \
    --cli-input-json file://deploy/dispatcher-task-definition-${tier}.json \
    --region us-west-2
done
```

### Step 5: Create 4 Schedulers (20 min)

**Important:** Stagger execution times to avoid DB contention

```bash
# Tiny account - runs at :00, :05, :10, :15, etc (every 5 min offset 0)
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
      ...
    }
  }' \
  --region us-west-2

# Small account - runs at :01, :06, :11, :16, etc (every 5 min offset 1)
aws scheduler create-schedule \
  --name ops-pipeline-dispatcher-small \
  --schedule-expression "cron(1/5 * * * ? *)" \
  ...

# Medium account - runs at :02, :07, :12, :17, etc (every 5 min offset 2)
aws scheduler create-schedule \
  --name ops-pipeline-dispatcher-medium \
  --schedule-expression "cron(2/5 * * * ? *)" \
  ...

# Large account - runs at :03, :08, :13, :18, etc (every 5 min offset 3)
# (Or keep existing 1-minute schedule if you want large account more active)
```

### Step 6: Add Database Column (15 min)

**File:** `db/migrations/012_add_account_tracking.sql`

```sql
-- Add account tracking to executions
ALTER TABLE dispatch_executions 
ADD COLUMN IF NOT EXISTS account_name VARCHAR(50);

-- Add index for performance
CREATE INDEX IF NOT EXISTS idx_dispatch_executions_account 
ON dispatch_executions(account_name, simulated_ts);

-- Add account metadata table
CREATE TABLE IF NOT EXISTS account_metadata (
    account_name VARCHAR(50) PRIMARY KEY,
    tier VARCHAR(20) NOT NULL,
    initial_balance DECIMAL(12,2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT
);

-- Insert metadata for tracking
INSERT INTO account_metadata (account_name, tier, initial_balance, notes)
VALUES 
    ('tiny-1k', 'tiny', 1000.00, 'Testing tiny tier (25% risk)'),
    ('small-5k', 'small', 5000.00, 'Testing small tier (12% risk)'),
    ('medium-25k', 'medium', 25000.00, 'Testing medium tier (4% risk)'),
    ('large-100k', 'large', 100000.00, 'Testing large tier (1% risk)')
ON CONFLICT (account_name) DO NOTHING;
```

### Step 7: Update AI Learning Tables (10 min)

Add account_name to learning tables so AI can learn tier-specific patterns:

```sql
ALTER TABLE ai_option_trades 
ADD COLUMN IF NOT EXISTS account_name VARCHAR(50);

ALTER TABLE ai_feature_importance
ADD COLUMN IF NOT EXISTS account_tier VARCHAR(20);
```

---

## Analysis Queries

### Compare Performance Across Tiers

```sql
-- Daily P&L by account
SELECT 
    account_name,
    COUNT(*) as trades,
    SUM(notional) as total_capital_used,
    -- Would need to join with actual fills for P&L
    AVG(contracts) as avg_contracts
FROM dispatch_executions
WHERE simulated_ts::date = CURRENT_DATE
    AND account_name IS NOT NULL
GROUP BY account_name
ORDER BY 
    CASE account_name
        WHEN 'tiny-1k' THEN 1
        WHEN 'small-5k' THEN 2
        WHEN 'medium-25k' THEN 3
        WHEN 'large-100k' THEN 4
    END;
```

### Tier Validation

```sql
-- Verify tier sizing is working
SELECT 
    account_name,
    ticker,
    contracts,
    notional,
    ROUND(notional / 
        CASE account_name
            WHEN 'tiny-1k' THEN 1000.00
            WHEN 'small-5k' THEN 5000.00
            WHEN 'medium-25k' THEN 25000.00
            WHEN 'large-100k' THEN 100000.00
        END * 100, 2) as risk_pct_used
FROM dispatch_executions
WHERE simulated_ts::date = CURRENT_DATE
    AND account_name IS NOT NULL
ORDER BY simulated_ts DESC
LIMIT 20;
```

---

## Cost Analysis

### Current (1 account):
- Dispatcher: 1,440 runs/day × $0.000004 = $0.0058/day
- Total: ~$0.18/month

### With 4 Accounts:
- If all run every 5 minutes: 1,152 runs/day × $0.000004 = $0.0046/day × 4 = $0.55/month
- If staggered optimally: ~$0.60/month total

**Cost increase: $0.42/month (~$5/year)**

---

## Alternative: Simpler Approach

### Option 1B: Environment Variable Only (30 min)

Don't create separate schedulers, just test manually:

1. Modify current dispatcher to read `ACCOUNT_TIER` env var
2. Manually update task definition environment to test each tier:

```bash
# Test tiny tier
aws ecs register-task-definition \
  --cli-input-json file://deploy/dispatcher-task-definition.json \
  --region us-west-2

# Update environment: ACCOUNT_TIER=tiny
# Run once manually to test
aws ecs run-task \
  --cluster ops-pipeline-cluster \
  --task-definition ops-pipeline-dispatcher:XX \
  --region us-west-2
```

3. Check logs for tier behavior
4. Repeat for each tier

**Pros:** Quick validation without infrastructure changes  
**Cons:** Not continuous, manual process

---

## Recommended Phased Approach

### Phase A: Quick Validation (30 min - DO THIS FIRST)
1. Add `ACCOUNT_TIER` env var support to dispatcher
2. Manually test each tier by running task with different env
3. Verify tier logic works correctly
4. Document results

### Phase B: Full Multi-Account (2 hours - LATER IF NEEDED)
1. Create all secrets
2. Create all task definitions
3. Create all schedulers
4. Add database tracking
5. Run continuously for learning

---

## Implementation Steps for Phase A (Quick Test)

### 1. Modify config.py (Already Done!)
The tier detection is already automatic based on buying power.

### 2. Create Test Script

**File:** `scripts/test_multi_tier.sh`

```bash
#!/bin/bash
# Test all account tiers manually

for tier in tiny small medium large; do
    echo "=== Testing $tier tier ==="
    
    # Modify Alpaca paper account balance to match tier
    # (This would need to be done in Alpaca UI)
    # tiny: Reset to $1,000
    # small: Reset to $5,000  
    # medium: Reset to $25,000
    # large: Reset to $100,000
    
    echo "1. Set Alpaca paper account balance"
    echo "2. Run dispatcher"
    
    aws ecs run-task \
        --cluster ops-pipeline-cluster \
        --task-definition ops-pipeline-dispatcher:15 \
        --launch-type FARGATE \
        --network-configuration "awsvpcConfiguration={
            subnets=[subnet-0c182a149eeef918a],
            securityGroups=[sg-0cd16a909f4e794ce],
            assignPublicIp=ENABLED
        }" \
        --region us-west-2
    
    echo "3. Wait for execution and check logs"
    sleep 30
    
    aws logs tail /ecs/ops-pipeline/dispatcher \
        --region us-west-2 \
        --since 1m \
        | grep -E "(Tier:|contracts|Risk:)"
    
    echo ""
    read -p "Press enter to test next tier..."
done
```

---

## Data Model Changes Needed

### For Full Multi-Account Support

**New table:** `trading_accounts`

```sql
CREATE TABLE trading_accounts (
    account_id SERIAL PRIMARY KEY,
    account_name VARCHAR(50) UNIQUE NOT NULL,
    tier VARCHAR(20) NOT NULL,
    alpaca_account_id VARCHAR(100),
    secret_name VARCHAR(100) NOT NULL,
    initial_balance DECIMAL(12,2) NOT NULL,
    current_balance DECIMAL(12,2),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_trade_at TIMESTAMP,
    notes TEXT
);

-- Add account reference to executions
ALTER TABLE dispatch_executions 
ADD COLUMN account_id INTEGER REFERENCES trading_accounts(account_id);

-- Add account reference to learning
ALTER TABLE ai_option_trades
ADD COLUMN account_id INTEGER REFERENCES trading_accounts(account_id);
```

---

## Testing Strategy

### Validation Tests

**Test 1: Verify Each Tier**
```python
# After running each tier manually
expected = {
    'tiny': {'risk_pct': 0.25, 'max_contracts': 2},
    'small': {'risk_pct': 0.12, 'max_contracts': 3},
    'medium': {'risk_pct': 0.04, 'max_contracts': 5},
    'large': {'risk_pct': 0.01, 'max_contracts': 10}
}

# Check logs show correct tier detection
# Check contract counts don't exceed max
# Check risk percentage matches expectation
```

**Test 2: Position Sizing**
```python
# For $1K account with $2.50 premium option:
# Expected: 1 contract ($250 total, 25% of $1K)

# For $100K account with $2.50 premium option:
# Expected: 4 contracts ($1,000 total, 1% of $100K)
```

**Test 3: Quality Scoring**
```python
# Should see in logs for each account:
# "Selected contract with quality score: XX.X/100"
# Quality scores should be similar across accounts (same contracts)
```

---

## Performance Comparison Dashboard

### SQL Query for Multi-Account Analysis

```sql
WITH daily_performance AS (
    SELECT 
        account_name,
        COUNT(*) as num_trades,
        SUM(notional) as capital_deployed,
        AVG(contracts) as avg_contracts,
        MIN(contracts) as min_contracts,
        MAX(contracts) as max_contracts
    FROM dispatch_executions
    WHERE simulated_ts::date = CURRENT_DATE
        AND account_name IS NOT NULL
    GROUP BY account_name
),
tier_metadata AS (
    SELECT 
        account_name,
        tier,
        initial_balance
    FROM account_metadata
)
SELECT 
    tm.tier,
    tm.account_name,
    tm.initial_balance,
    COALESCE(dp.num_trades, 0) as trades,
    COALESCE(dp.capital_deployed, 0) as capital_used,
    ROUND(COALESCE(dp.capital_deployed, 0) / tm.initial_balance * 100, 2) as utilization_pct,
    COALESCE(dp.avg_contracts, 0) as avg_contracts
FROM tier_metadata tm
LEFT JOIN daily_performance dp ON tm.account_name = dp.account_name
ORDER BY tm.initial_balance;
```

---

## Monitoring & Alerts

### Key Metrics Per Account

1. **Trades per day** - Should be similar across accounts
2. **Capital utilization** - Should match tier (25% for tiny, 1% for large)
3. **Contract counts** - Should respect tier caps
4. **Quality scores** - Should be similar (same opportunities)
5. **Win rate** - Compare across tiers (is aggressive better?)

### CloudWatch Dashboard

Create dashboard showing:
- Trades per account (last 24h)
- Average position size per account
- Quality scores distribution per account
- Errors per account

---

## Rollout Plan

### Week 1: Manual Testing (Phase A)
1. Test each tier by manually adjusting Alpaca balance
2. Run dispatcher once per tier
3. Verify tier detection
4. Verify position sizing
5. Document results

### Week 2: Deploy Multi-Account (Phase B) - If Validated
1. Create all 4 Alpaca paper accounts
2. Store credentials in Secrets Manager
3. Deploy 4 schedulers
4. Run for 1 week
5. Analyze performance differences

### Week 3: Analysis & Tuning
1. Compare results across tiers
2. Adjust tier thresholds if needed
3. Optimize risk percentages
4. Document best practices

---

## Expected Learnings

### Questions Multi-Account Will Answer:

1. **Is 25% too aggressive for tiny accounts?**
   - Win rate vs large account
   - Drawdown analysis
   - Time to grow $1K → $2K

2. **Do different tiers need different strategies?**
   - Should tiny prefer day trades over swings?
   - Should large prefer swings for lower fees?

3. **Quality scoring effectiveness**
   - Do higher scores = better outcomes?
   - Is score threshold 40 appropriate?

4. **Optimal tier breakpoints**
   - Should tiny be $0-3K instead of $0-2K?
   - Should medium start at $10K instead of $5K?

---

## Quick Start: Test Single Tier Now

**Want to test right now?** Manually adjust your Alpaca paper account:

```bash
# 1. Log into Alpaca paper trading
# 2. Reset account to $1,000 (or desired amount)
# 3. Trigger dispatcher manually:

aws ecs run-task \
    --cluster ops-pipeline-cluster \
    --task-definition ops-pipeline-dispatcher:15 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={
        subnets=[subnet-0c182a149eeef918a],
        securityGroups=[sg-0cd16a909f4e794ce],
        assignPublicIp=ENABLED
    }" \
    --region us-west-2

# 4. Watch logs for tier detection:
aws logs tail /ecs/ops-pipeline/dispatcher \
    --region us-west-2 \
    --follow \
    | grep -E "(Tier:|Buying power)"
```

---

## Summary

### Immediate Action (If Desired):
1. Create 3 additional Alpaca paper accounts
2. Get API keys for each
3. Implement Phase A (quick test) or Phase B (full deployment)
4. Monitor and learn

### Benefits:
- Test all tiers simultaneously
- Validate tier logic comprehensively
- Compare performance objectively
- Optimize settings per tier
- Build confidence before live trading

### Next Steps:
1. Decide: Quick test (Phase A) or full deployment (Phase B)?
2. If Phase B: Create Alpaca accounts and provide API keys
3. Implement chosen approach
4. Run for 1-2 weeks
5. Analyze results and tune

---

## Recommendation

**Start with Phase A (manual testing):**
- Lower risk
- Faster validation
- Can always upgrade to Phase B later

**Only do Phase B if:**
- Phase A results look good
- You want continuous multi-tier learning
- Worth the extra AWS cost (~$5/year)
