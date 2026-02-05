# Phase 3: Ready to Deploy

**Date:** February 2, 2026  
**Status:** ✅ Implementation Complete - Ready for Deployment

---

## What Was Done

### 1. Entry Features Capture (✅ Verified Working)
- Investigated `position_manager/db.py` 
- **Result:** Already implemented correctly
- Features are captured from `dispatch_recommendations.features_snapshot`
- No changes needed

### 2. WebSocket Idempotency (✅ Implemented)
- Created migration: `2026_02_02_0002_websocket_idempotency.sql`
- Added `alpaca_event_dedupe` table for event tracking
- Added `alpaca_order_id` column to `active_positions`
- Implemented three-layer idempotency in `trade_stream` service:
  1. Event-level dedupe (prevents duplicate event processing)
  2. Order-level dedupe (prevents duplicate positions per order)
  3. Symbol-level dedupe (fallback safety check)

---

## Quick Deploy

### Apply Migration
```bash
python3 apply_phase3_migration.py
```

### Rebuild & Deploy Trade-Stream
```bash
cd services/trade_stream
docker build -t trade-stream .

# Tag and push to ECR
aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin 160027201036.dkr.ecr.us-west-2.amazonaws.com
docker tag trade-stream:latest 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/trade-stream:latest
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/trade-stream:latest

# Update ECS service
aws ecs update-service --cluster ops-pipeline --service trade-stream --force-new-deployment --region us-west-2
```

---

## What This Fixes

**Problem:** WebSocket can receive duplicate fill events  
**Impact:** Creates duplicate positions in database  
**Solution:** Three-layer idempotency prevents duplicates

**Example scenario:**
1. Order fills
2. WebSocket sends event
3. Network hiccup causes retry
4. **Before:** Two positions created
5. **After:** Second event skipped, one position created

---

## Files Changed

**Created:**
- `db/migrations/2026_02_02_0002_websocket_idempotency.sql`
- `apply_phase3_migration.py`
- `BEHAVIOR_LEARNING_PHASE3_STATUS.md` (detailed docs)
- `PHASE3_READY_TO_DEPLOY.md` (this file)

**Modified:**
- `services/trade_stream/db.py` - Added idempotency functions
- `services/trade_stream/main.py` - Added event dedupe logic
- `spec/behavior_learning_mode/TASKS.md` - Updated progress

---

## Verification

After deployment, check for duplicates:
```bash
aws lambda invoke --function-name ops-pipeline-db-query --region us-west-2 \
  --cli-binary-format raw-in-base64-out \
  --payload '{"sql":"SELECT alpaca_order_id, COUNT(*) FROM active_positions WHERE alpaca_order_id IS NOT NULL GROUP BY alpaca_order_id HAVING COUNT(*) > 1;"}' \
  /tmp/check.json && cat /tmp/check.json
```

**Expected:** Empty result (no duplicates)

---

## Next Phase

**Phase 4: Nightly Statistics Job**
- Aggregate position_history data
- Create strategy_stats table
- Schedule daily at 2 AM UTC
- Enable AI training data analysis

---

**See:** `BEHAVIOR_LEARNING_PHASE3_STATUS.md` for complete details
