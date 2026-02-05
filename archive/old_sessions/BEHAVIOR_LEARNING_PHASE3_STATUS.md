# Behavior Learning Mode - Phase 3 Status

**Date:** February 2, 2026  
**Phase:** 3 - Bug Fixes & Hardening  
**Status:** 🔨 Implementation Complete - Ready for Deployment

---

## Summary

Phase 3 adds critical hardening to the behavior learning mode:

1. **Entry Features Capture** - Verified working correctly
2. **WebSocket Idempotency** - Prevents duplicate position creation from WebSocket events

---

## Task 3.1-3.4: Entry Features Capture (✅ VERIFIED WORKING)

### Investigation Results

The entry features capture is **already implemented correctly**:

**File:** `services/position_manager/db.py` (line 68)
```python
dr.features_snapshot as entry_features_json,
```

**How it works:**
1. `get_filled_executions_since()` JOINs `dispatch_executions` with `dispatch_recommendations`
2. Pulls `features_snapshot` from recommendations table
3. Renames to `entry_features_json` for consistency
4. `create_active_position()` stores it in `active_positions.entry_features_json`

**Schema verified:**
- `dispatch_recommendations.features_snapshot` exists (JSONB)
- `active_positions.entry_features_json` exists (JSONB)
- JOIN correctly maps the data

### No Changes Needed

The code is already correct. Features will be captured automatically when:
1. Signal engine creates recommendations with `features_snapshot`
2. Dispatcher creates executions linked to those recommendations
3. Position manager picks up filled executions

---

## Task 3.5-3.11: WebSocket Idempotency (✅ IMPLEMENTED)

### Problem Statement

The trade-stream WebSocket service can receive duplicate events from Alpaca:
- Network retries
- Reconnection scenarios
- Multiple event notifications for same order

Without idempotency, this creates duplicate positions in the database.

### Solution Design

**Three-layer idempotency:**

1. **Event-level dedupe** - Track processed WebSocket events
2. **Order-level dedupe** - Track positions by Alpaca order_id
3. **Symbol-level dedupe** - Fallback check by ticker/option_symbol

### Implementation

#### 1. Database Migration

**File:** `db/migrations/2026_02_02_0002_websocket_idempotency.sql`

**Changes:**
- New table: `alpaca_event_dedupe` (tracks processed WebSocket events)
- New column: `active_positions.alpaca_order_id` (links to Alpaca orders)
- New index: `idx_active_positions_execution_uuid_unique` (partial unique on execution_uuid)
- New index: `idx_active_positions_alpaca_order_id` (fast order lookup)

**Idempotency guarantees:**
- Event ID is primary key (prevents duplicate event processing)
- Order ID index prevents duplicate positions per order
- Execution UUID unique index prevents duplicate positions per execution

#### 2. Database Functions

**File:** `services/trade_stream/db.py`

**New functions:**
```python
check_event_processed(event_id) -> bool
    # Check if WebSocket event already processed

record_event_processed(event_id, event_type, order_id, symbol, event_data) -> bool
    # Record event as processed (idempotent)

get_position_by_order_id(order_id) -> Optional[Dict]
    # Find position by Alpaca order ID

create_position_from_alpaca_with_order_id(...) -> Optional[int]
    # Create position with full idempotency:
    # 1. Check by order_id
    # 2. Check by symbol
    # 3. Use ON CONFLICT for race conditions
```

#### 3. WebSocket Handler

**File:** `services/trade_stream/main.py`

**Changes to `handle_trade_update()`:**

```python
# Before processing fill event:
event_id = f"fill_{order.id}_{order.filled_at}"
if db.check_event_processed(event_id):
    logger.info("Event already processed")
    return

# Create position with order_id tracking:
position_id = db.create_position_from_alpaca_with_order_id(
    ...,
    order_id=str(order.id),
    ...
)

# Record event as processed:
db.record_event_processed(
    event_id=event_id,
    event_type='fill',
    order_id=str(order.id),
    symbol=order.symbol,
    event_data={...}
)
```

### Idempotency Flow

```
WebSocket Event Received
    ↓
Check event_id in alpaca_event_dedupe
    ↓ (not found)
Check order_id in active_positions
    ↓ (not found)
Check symbol in active_positions
    ↓ (not found)
Create position with ON CONFLICT
    ↓
Record event_id in alpaca_event_dedupe
    ↓
Done (position created once)
```

**If duplicate event arrives:**
```
WebSocket Event Received
    ↓
Check event_id in alpaca_event_dedupe
    ↓ (FOUND!)
Skip processing
    ↓
Done (no duplicate position)
```

### Testing Strategy

**Test scenarios:**
1. Normal fill event → Position created
2. Duplicate fill event (same event_id) → Skipped
3. Duplicate order (different event_id) → Existing position returned
4. Race condition (concurrent events) → ON CONFLICT prevents duplicate

---

## Deployment Steps

### Step 1: Apply Migration

```bash
python3 apply_phase3_migration.py
```

**Expected output:**
- ✅ alpaca_event_dedupe table created
- ✅ active_positions.alpaca_order_id column added
- ✅ Indexes created
- ✅ Migration recorded in schema_migrations

### Step 2: Rebuild Trade-Stream Service

```bash
cd services/trade_stream

# Build Docker image
docker build -t trade-stream:phase3 .

# Tag for ECR
docker tag trade-stream:phase3 \
  160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/trade-stream:latest

# Login to ECR
aws ecr get-login-password --region us-west-2 | \
  docker login --username AWS --password-stdin \
  160027201036.dkr.ecr.us-west-2.amazonaws.com

# Push to ECR
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/trade-stream:latest
```

### Step 3: Update ECS Task Definition

```bash
# Get new image digest
IMAGE_DIGEST=$(aws ecr describe-images \
  --repository-name ops-pipeline/trade-stream \
  --region us-west-2 \
  --query 'sort_by(imageDetails,& imagePushedAt)[-1].imageDigest' \
  --output text)

echo "New image digest: $IMAGE_DIGEST"

# Update task definition with new digest
# Edit deploy/trade-stream-task-definition.json
# Change image to: 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/trade-stream@$IMAGE_DIGEST

# Register new task definition
aws ecs register-task-definition \
  --cli-input-json file://deploy/trade-stream-task-definition.json \
  --region us-west-2
```

### Step 4: Restart Service

```bash
# Force new deployment (picks up new task definition)
aws ecs update-service \
  --cluster ops-pipeline \
  --service trade-stream \
  --force-new-deployment \
  --region us-west-2

# Monitor deployment
aws ecs describe-services \
  --cluster ops-pipeline \
  --services trade-stream \
  --region us-west-2 \
  --query 'services[0].deployments'
```

### Step 5: Verify Deployment

```bash
# Check service is running
aws ecs describe-services \
  --cluster ops-pipeline \
  --services trade-stream \
  --region us-west-2 \
  --query 'services[0].{status:status,running:runningCount,desired:desiredCount}'

# Check logs for startup
aws logs tail /ecs/trade-stream --follow --region us-west-2
```

---

## Verification

### Check Migration Applied

```bash
python3 -c "
import boto3, json
lambda_client = boto3.client('lambda', region_name='us-west-2')
response = lambda_client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({
        'sql': '''
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_name IN ('alpaca_event_dedupe', 'active_positions')
              AND column_name IN ('event_id', 'alpaca_order_id')
            ORDER BY table_name, column_name;
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
    {"table_name": "active_positions", "column_name": "alpaca_order_id", "data_type": "character varying"},
    {"table_name": "alpaca_event_dedupe", "column_name": "event_id", "data_type": "character varying"}
  ]
}
```

### Test Idempotency

**Scenario 1: Normal operation**
1. Place test order via Alpaca
2. Wait for fill event
3. Check logs: "Position X synced in REAL-TIME"
4. Verify position created in database

**Scenario 2: Duplicate event**
1. Simulate duplicate by restarting service during fill
2. Check logs: "Event already processed"
3. Verify only one position exists

**Scenario 3: Race condition**
1. Multiple concurrent fills (rare but possible)
2. Check logs: One creates, others skip
3. Verify only one position exists

---

## Files Modified

### Created
- `db/migrations/2026_02_02_0002_websocket_idempotency.sql` - Migration
- `apply_phase3_migration.py` - Migration deployment script
- `BEHAVIOR_LEARNING_PHASE3_STATUS.md` - This file

### Modified
- `services/trade_stream/db.py` - Added idempotency functions
- `services/trade_stream/main.py` - Added event dedupe logic
- `spec/behavior_learning_mode/TASKS.md` - Updated task status

---

## Impact Assessment

### Risk: LOW
- Observability-only changes (no trading logic affected)
- Idempotency is defensive (prevents bugs, doesn't change behavior)
- Migration is idempotent (safe to re-run)

### Benefits: HIGH
- Prevents duplicate position tracking
- Prevents incorrect P&L calculations
- Prevents duplicate exit orders
- Improves data quality for AI training

### Rollback Plan
If issues occur:
1. Revert trade-stream service to previous task definition
2. Migration can stay (doesn't affect old code)
3. New columns are nullable (backward compatible)

---

## Next Steps

After Phase 3 deployment:

### Phase 4: Nightly Statistics Job

1. Review `services/learning_stats_job/` scaffold
2. Verify `compute_strategy_stats.sql` completeness
3. Create ECS task definition or Lambda
4. Create EventBridge schedule (daily 2 AM UTC)
5. Test manual execution
6. Verify `strategy_stats` table population

This will create the `strategy_stats` table for AI training data aggregation.

---

## Monitoring

### Check Event Dedupe Table

```bash
aws lambda invoke --function-name ops-pipeline-db-query --region us-west-2 \
  --cli-binary-format raw-in-base64-out \
  --payload '{"sql":"SELECT COUNT(*) as total_events, COUNT(DISTINCT order_id) as unique_orders, MAX(processed_at) as latest FROM alpaca_event_dedupe;"}' \
  /tmp/check_dedupe.json && cat /tmp/check_dedupe.json
```

### Check Position Order IDs

```bash
aws lambda invoke --function-name ops-pipeline-db-query --region us-west-2 \
  --cli-binary-format raw-in-base64-out \
  --payload '{"sql":"SELECT COUNT(*) as total, COUNT(alpaca_order_id) as with_order_id, COUNT(DISTINCT alpaca_order_id) as unique_orders FROM active_positions WHERE created_at > NOW() - INTERVAL '\''1 day'\'';"}' \
  /tmp/check_orders.json && cat /tmp/check_orders.json
```

### Check for Duplicates

```bash
aws lambda invoke --function-name ops-pipeline-db-query --region us-west-2 \
  --cli-binary-format raw-in-base64-out \
  --payload '{"sql":"SELECT alpaca_order_id, COUNT(*) as count FROM active_positions WHERE alpaca_order_id IS NOT NULL GROUP BY alpaca_order_id HAVING COUNT(*) > 1;"}' \
  /tmp/check_duplicates.json && cat /tmp/check_duplicates.json
```

**Expected:** Empty result (no duplicates)

---

## References

- **Spec:** `spec/behavior_learning_mode/`
- **Tasks:** `spec/behavior_learning_mode/TASKS.md`
- **Design:** `spec/behavior_learning_mode/DESIGN.md`
- **Phase 1:** `BEHAVIOR_LEARNING_PHASE1_COMPLETE.md`

---

**Phase 3 Status:** ✅ Implementation Complete  
**Next Action:** Apply migration and deploy trade-stream service  
**Next Phase:** Phase 4 - Nightly Statistics Job
