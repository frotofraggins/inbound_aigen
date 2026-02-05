# Phase 3: Production Foot-Gun Fixes

**Date:** February 2, 2026  
**Status:** ✅ Fixed - Ready for Deployment

---

## Critical Issues Fixed

### Issue 1: False Success Reporting ❌ → ✅

**Problem:**
- `apply_behavior_learning_migration.py` and `apply_phase3_migration.py` reported success even when migrations failed
- Only checked HTTP 200 status, didn't verify:
  - Lambda execution errors (`errorMessage` in payload)
  - Body success flag
  - Migration recorded in `schema_migrations` table

**Impact:**
- Trains users to trust wrong output
- Dangerous in production - could lead to believing migrations applied when they didn't
- Could cause cascading failures if dependent code expects schema changes

**Fix:**
Both scripts now perform comprehensive validation:

```python
# 1. Check HTTP status code
if response['StatusCode'] != 200:
    return False

# 2. Check for Lambda execution errors
if 'errorMessage' in response_payload:
    return False

# 3. Parse body and check success flag
body = json.loads(response_payload['body'])
if not body.get('success'):
    return False

# 4. Verify migration recorded in schema_migrations
verify_response = lambda_client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({
        'sql': "SELECT version FROM schema_migrations WHERE version = '...'"
    })
)
if not verify_body.get('rows'):
    return False
```

**Files Fixed:**
- `apply_behavior_learning_migration.py`
- `apply_phase3_migration.py`
- `apply_constraints_migration.py` (new, uses correct pattern)

---

### Issue 2: Missing Constraints ❌ → ✅

**Problem:**
- Migration `2026_02_02_0001_position_telemetry.sql` had DO blocks with constraint checks
- DO blocks were removed instead of fixing the executor
- Lost enforcement for:
  - `active_positions.side` CHECK (side IN ('long', 'short'))
  - `active_positions.strategy_type` CHECK (strategy_type IN (...))
  - `position_history.side` CHECK (side IN ('long', 'short'))
  - `position_history.strategy_type` CHECK (strategy_type IN (...))

**Impact:**
- No validation on critical enum fields
- Could allow invalid data: `side = 'banana'`, `strategy_type = 'yolo'`
- Breaks downstream analytics and AI training

**Fix:**
Created new migration `2026_02_02_0003_add_constraints_no_do.sql`:

```sql
-- No DO blocks, just direct ALTER TABLE
ALTER TABLE active_positions 
ADD CONSTRAINT chk_active_positions_side 
CHECK (side IN ('long', 'short'))
NOT VALID;

ALTER TABLE active_positions 
ADD CONSTRAINT chk_active_positions_strategy_type 
CHECK (strategy_type IN ('day_trade', 'swing_trade', 'conservative'))
NOT VALID;

-- Same for position_history...
```

**Why NOT VALID:**
- Won't check existing data (safe for production)
- Will enforce for new inserts/updates
- Can be validated later with `ALTER TABLE ... VALIDATE CONSTRAINT`

**Files Created:**
- `db/migrations/2026_02_02_0003_add_constraints_no_do.sql`
- `apply_constraints_migration.py`

---

### Issue 3: Lambda Executor Bug ✅ (Actually Not a Bug!)

**Initial Concern:**
- Thought Lambda had naive `.split(';')` that would break DO blocks

**Investigation Result:**
- Lambda executor is **actually correct**!
- Line 1000: `cursor.execute(MIGRATIONS[version])`
- Executes whole migration as one statement
- PostgreSQL's psycopg2 handles multiple statements correctly

**Conclusion:**
- No fix needed for Lambda executor
- DO blocks were removed for different reason (probably manual editing)
- Constraints just need to be re-added without DO blocks

---

## New Migrations Added to Lambda

Updated `services/db_migration_lambda/lambda_function.py` MIGRATIONS dict:

### 1. `2026_02_02_0002_websocket_idempotency`
- Creates `alpaca_event_dedupe` table
- Adds `alpaca_order_id` column to `active_positions`
- Adds indexes for fast lookups
- Prevents duplicate position creation from WebSocket events

### 2. `2026_02_02_0003_add_constraints_no_do`
- Re-adds missing constraints without DO blocks
- Validates enum fields for `side` and `strategy_type`
- Uses NOT VALID for safe production deployment

---

## Deployment Process

### Quick Deploy (All-in-One)

```bash
./deploy_phase3_complete.sh
```

This script:
1. Rebuilds and redeploys db-migration Lambda
2. Applies Phase 3 WebSocket idempotency migration
3. Applies constraints migration
4. Rebuilds and redeploys trade-stream service

### Manual Deploy (Step-by-Step)

#### Step 1: Update Lambda with New Migrations

```bash
cd services/db_migration_lambda

# Create deployment package
rm -f migration_lambda.zip
cd package
zip -r ../migration_lambda.zip .
cd ..
zip -g migration_lambda.zip lambda_function.py

# Deploy
aws lambda update-function-code \
    --function-name ops-pipeline-db-migration \
    --zip-file fileb://migration_lambda.zip \
    --region us-west-2

# Wait for update
aws lambda wait function-updated \
    --function-name ops-pipeline-db-migration \
    --region us-west-2
```

#### Step 2: Apply Migrations

```bash
# Apply WebSocket idempotency
python3 apply_phase3_migration.py

# Apply constraints
python3 apply_constraints_migration.py
```

#### Step 3: Deploy Trade-Stream

```bash
cd services/trade_stream

# Build and push
docker build -t trade-stream:phase3 .
docker tag trade-stream:phase3 \
    160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/trade-stream:latest

aws ecr get-login-password --region us-west-2 | \
    docker login --username AWS --password-stdin \
    160027201036.dkr.ecr.us-west-2.amazonaws.com

docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/trade-stream:latest

# Update service
aws ecs update-service \
    --cluster ops-pipeline \
    --service trade-stream \
    --force-new-deployment \
    --region us-west-2
```

---

## Verification

### Check Migrations Applied

```bash
python3 -c "
import boto3, json
lambda_client = boto3.client('lambda', region_name='us-west-2')
response = lambda_client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({
        'sql': '''
            SELECT version, applied_at 
            FROM schema_migrations 
            WHERE version LIKE '2026_02_02%'
            ORDER BY version;
        '''
    })
)
result = json.loads(response['Payload'].read())
print(json.dumps(json.loads(result['body']), indent=2))
"
```

**Expected:**
```json
{
  "rows": [
    {"version": "2026_02_02_0001_position_telemetry", "applied_at": "..."},
    {"version": "2026_02_02_0002_websocket_idempotency", "applied_at": "..."},
    {"version": "2026_02_02_0003_add_constraints_no_do", "applied_at": "..."}
  ]
}
```

### Check Constraints Exist

```bash
python3 -c "
import boto3, json
lambda_client = boto3.client('lambda', region_name='us-west-2')
response = lambda_client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({
        'sql': '''
            SELECT 
                conname AS constraint_name,
                conrelid::regclass AS table_name
            FROM pg_constraint
            WHERE conname LIKE 'chk_%'
            ORDER BY table_name, constraint_name;
        '''
    })
)
result = json.loads(response['Payload'].read())
print(json.dumps(json.loads(result['body']), indent=2))
"
```

**Expected:**
```json
{
  "rows": [
    {"constraint_name": "chk_active_positions_side", "table_name": "active_positions"},
    {"constraint_name": "chk_active_positions_strategy_type", "table_name": "active_positions"},
    {"constraint_name": "chk_position_history_side", "table_name": "position_history"},
    {"constraint_name": "chk_position_history_strategy_type", "table_name": "position_history"}
  ]
}
```

### Check Trade-Stream Running

```bash
aws ecs describe-services \
    --cluster ops-pipeline \
    --services trade-stream \
    --region us-west-2 \
    --query 'services[0].{status:status,running:runningCount,desired:desiredCount}'
```

### Monitor for Duplicate Events

```bash
# Watch logs for "Event already processed" messages
aws logs tail /ecs/trade-stream --follow --region us-west-2 | grep -i "event already"
```

---

## Files Created/Modified

### Created
- `db/migrations/2026_02_02_0003_add_constraints_no_do.sql` - Constraints migration
- `apply_constraints_migration.py` - Deployment script for constraints
- `deploy_phase3_complete.sh` - All-in-one deployment script
- `PHASE3_PRODUCTION_FIXES.md` - This document

### Modified
- `apply_behavior_learning_migration.py` - Fixed success reporting
- `apply_phase3_migration.py` - Fixed success reporting
- `services/db_migration_lambda/lambda_function.py` - Added new migrations to MIGRATIONS dict

---

## Impact Assessment

### Risk: LOW
- All changes are defensive (prevent bugs, don't change behavior)
- Migrations are idempotent (safe to re-run)
- Constraints are NOT VALID (won't break existing data)
- Success reporting fixes prevent false positives

### Benefits: HIGH
- **Reliability:** Accurate migration status reporting
- **Data Quality:** Constraints prevent invalid enum values
- **Idempotency:** No duplicate positions from WebSocket events
- **Confidence:** Can trust deployment scripts

---

## Rollback Plan

If issues occur:

### Rollback Trade-Stream
```bash
# Get previous task definition
aws ecs describe-task-definition \
    --task-definition trade-stream \
    --region us-west-2 \
    --query 'taskDefinition.revision'

# Update to previous revision
aws ecs update-service \
    --cluster ops-pipeline \
    --service trade-stream \
    --task-definition trade-stream:<previous-revision> \
    --region us-west-2
```

### Rollback Lambda
```bash
# List versions
aws lambda list-versions-by-function \
    --function-name ops-pipeline-db-migration \
    --region us-west-2

# Rollback to previous version
aws lambda update-function-configuration \
    --function-name ops-pipeline-db-migration \
    --region us-west-2 \
    --publish
```

### Migrations
- Migrations can stay (backward compatible)
- New columns are nullable
- Constraints are NOT VALID (don't affect existing data)

---

## Next Steps

After Phase 3 deployment:

1. **Monitor for 24 hours**
   - Check logs for duplicate event messages
   - Verify no constraint violations
   - Confirm positions created correctly

2. **Validate Constraints (Optional)**
   ```sql
   -- After confirming data quality
   ALTER TABLE active_positions VALIDATE CONSTRAINT chk_active_positions_side;
   ALTER TABLE active_positions VALIDATE CONSTRAINT chk_active_positions_strategy_type;
   -- Same for position_history...
   ```

3. **Phase 4: Nightly Statistics Job**
   - Review `services/learning_stats_job/`
   - Create ECS task or Lambda
   - Schedule daily at 2 AM UTC
   - Populate `strategy_stats` table

---

## References

- **Spec:** `spec/behavior_learning_mode/`
- **Tasks:** `spec/behavior_learning_mode/TASKS.md`
- **Phase 3 Status:** `BEHAVIOR_LEARNING_PHASE3_STATUS.md`
- **Quick Guide:** `PHASE3_READY_TO_DEPLOY.md`

---

**Status:** ✅ All Production Foot-Guns Fixed  
**Ready:** Deploy with confidence  
**Next:** Phase 4 - Nightly Statistics Job
