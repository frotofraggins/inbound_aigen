# Multi-Account Setup Status

**Date:** 2026-01-29  
**Status:** Partially Complete (50%)  
**Remaining Time:** 1-1.5 hours

---

## What's Complete ✅

### 1. Tiny Account Credentials Stored
```
✅ Secret created: ops-pipeline/alpaca/tiny
✅ API Key: PKRTAIU5VRKXIAOCZHFIGK3CT7
✅ Account: tiny-1k ($1,000 starting balance)
```

### 2. Config Modified for Multi-Account
```
✅ services/dispatcher/config.py updated
✅ Reads ACCOUNT_TIER env var
✅ Loads tier-specific secrets
✅ Returns account_name and credentials
✅ Backwards compatible (falls back to default)
```

### 3. Design Document Created
```
✅ deploy/MULTI_ACCOUNT_DESIGN.md
✅ Complete architecture
✅ Implementation steps
✅ Analysis queries
```

---

## What's Needed (1-1.5 hours)

### 1. Update Broker Initialization (30 min)

**File:** `services/dispatcher/alpaca/broker.py`

Need to modify broker to use credentials from config instead of fetching from Secrets Manager:

```python
# Current: Broker fetches credentials itself
# Need: Broker accepts credentials from config

def initialize_broker(config: Dict[str, Any]):
    api_key = config['alpaca_api_key']
    api_secret = config['alpaca_api_secret']
    account_name = config['account_name']
    
    # Initialize with provided credentials
    broker = AlpacaPaperBroker(api_key, api_secret)
    
    print(f"Initialized {account_name} account")
    return broker
```

### 2. Add Account Tracking to Database (20 min)

**File:** `db/migrations/012_add_account_tracking.sql`

```sql
-- Add account_name column to executions
ALTER TABLE dispatch_executions 
ADD COLUMN IF NOT EXISTS account_name VARCHAR(50);

CREATE INDEX IF NOT EXISTS idx_dispatch_executions_account 
ON dispatch_executions(account_name, simulated_ts);
```

Apply migration:
```bash
python3 scripts/apply_012_via_query_lambda.py
```

### 3. Update Execution Recording (15 min)

**File:** `services/dispatcher/db/repositories.py`

Add account_name parameter to `create_execution()` function.

### 4. Create Tiny Account Task Definition (10 min)

**File:** `deploy/dispatcher-task-definition-tiny.json`

```json
{
  "family": "ops-pipeline-dispatcher-tiny",
  "containerDefinitions": [{
    "name": "dispatcher",
    "image": "...revision 15 SHA256...",
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
        "awslogs-stream-prefix": "dispatcher-tiny"
      }
    }
  }],
  ...
}
```

### 5. Register and Schedule (15 min)

```bash
# Register task definition
aws ecs register-task-definition \
  --cli-input-json file://deploy/dispatcher-task-definition-tiny.json \
  --region us-west-2

# Create scheduler (runs every 5 minutes, offset from main)
aws scheduler create-schedule \
  --name ops-pipeline-dispatcher-tiny \
  --schedule-expression "rate(5 minutes)" \
  --region us-west-2 \
  ...
```

---

## Quick Alternative: Manual Test (5 min)

**Don't want to wait? Test tiny account NOW:**

The config changes are already deployed in revision 15. Just need to test it:

```bash
# Create tiny task definition with ACCOUNT_TIER=tiny env var
# Then run it manually once to test

# Will need to:
# 1. Copy dispatcher-task-definition.json
# 2. Change family to "ops-pipeline-dispatcher-tiny"
# 3. Add ACCOUNT_TIER=tiny to environment
# 4. Register it
# 5. Run task manually
```

---

## Current State

**Large Account (Existing):**
- ✅ Running on revision 15
- ✅ Scheduler: every 1 minute
- ✅ Account: $93K balance
- ✅ Working perfectly

**Tiny Account (New):**
- ✅ Credentials stored
- ✅ Config code ready
- ⏳ Needs: Broker update, task def, scheduler
- ⏳ Estimated: 1-1.5 hours to complete

---

## Recommendation

**Option A: Finish Multi-Account Now (1.5 hours)**
- Complete all remaining steps
- Deploy tiny account scheduler
- Run both accounts in parallel
- Start collecting comparison data

**Option B: Test Manually First (30 min)**
- Create one-off tiny task definition
- Run it manually to verify credentials work
- Check logs show "tiny-1k" account
- Then decide if want full automation

**Option C: Document and Defer**
- Everything documented in MULTI_ACCOUNT_DESIGN.md
- Can be implemented in future session
- Focus on monitoring Phases 1 & 2 first

---

## My Recommendation

**Option B** - Quick manual test:
1. Proves tiny account credentials work
2. Validates tier detection with $1K balance
3. Only 30 minutes
4. Can automate later if results good

Want me to proceed with Option B (quick test)?
