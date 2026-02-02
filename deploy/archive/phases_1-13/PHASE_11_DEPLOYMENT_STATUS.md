# Phase 11 Deployment Status
**Date:** 2026-01-16 18:04 UTC  
**Status:** Paused - AWS Credentials Expired

## What We've Completed ✅

### 1. Docker Image Build & Push
- **Image Built:** ops-pipeline-classifier:phase11
- **Image Size:** 6.16GB
- **Pushed to ECR:** ✅ Success
- **Digest:** `sha256:906557742dc13b3a435064c9a276ae730883c9e699ef0e554220dca67ae2dd52`
- **ECR URL:** `160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/classifier-worker@sha256:906557742dc13b3a435064c9a276ae730883c9e699ef0e554220dca67ae2dd52`

### 2. Task Definition Updated
- **File:** `deploy/classifier-task-definition.json`
- **Updated with digest:** ✅ Complete
- **Ready for registration:** ✅ Yes

## What Needs to be Done Next 🔄

### Step 1: Refresh AWS Credentials
Your AWS security token has expired. Before continuing, you need to refresh your credentials:

```bash
# Method depends on your setup:
# - If using SSO: aws sso login
# - If using temporary credentials: refresh your credentials
# - If using assumed role: re-assume the role
```

### Step 2: Register New Task Definition
```bash
aws ecs register-task-definition \
  --region us-west-2 \
  --cli-input-json file://deploy/classifier-task-definition.json
```

This will return a new revision number (likely revision 2 or higher).

### Step 3: Update EventBridge Rule
Get the current rule configuration:
```bash
aws events describe-rule \
  --region us-west-2 \
  --name ops-pipeline-classifier-schedule
```

Then update the rule to use the new task definition revision:
```bash
aws events list-targets-by-rule \
  --region us-west-2 \
  --rule ops-pipeline-classifier-schedule

# Update target with new task definition revision
aws events put-targets \
  --region us-west-2 \
  --rule ops-pipeline-classifier-schedule \
  --targets '[{
    "Id": "1",
    "Arn": "arn:aws:ecs:us-west-2:160027201036:cluster/ops-pipeline",
    "RoleArn": "arn:aws:iam::160027201036:role/ops-pipeline-eventbridge-role",
    "EcsParameters": {
      "TaskDefinitionArn": "arn:aws:ecs:us-west-2:160027201036:task-definition/ops-pipeline-classifier-worker:<NEW_REVISION>",
      "TaskCount": 1,
      "LaunchType": "FARGATE",
      "NetworkConfiguration": {
        "awsvpcConfiguration": {
          "Subnets": ["subnet-0a1b2c3d4e5f6g7h8", "subnet-1a2b3c4d5e6f7g8h9"],
          "SecurityGroups": ["sg-0123456789abcdef0"],
          "AssignPublicIp": "DISABLED"
        }
      }
    }
  }]'
```

Note: You'll need to use the actual subnet and security group IDs from your existing configuration.

### Step 4: Monitor Initial Execution
Watch for the next scheduled classifier run (every 1 minute):

```bash
# Watch CloudWatch Logs
aws logs tail /ecs/ops-pipeline/classifier-worker \
  --region us-west-2 \
  --since 5m \
  --follow

# Look for these log indicators:
# - "ai_inference_enabled" or "ai_inference_disabled"
# - "ai_ticker_inference_used" (when AI is triggered)
# - Ticker extraction results
```

### Step 5: Wait for New News (2-3 hours)
The system needs to:
1. Ingest new news from ticker-specific Yahoo Finance RSS feeds
2. Process news with regex extraction (fast path)
3. Use AI inference as fallback (when regex finds nothing)
4. Classify sentiment with FinBERT

### Step 6: Validate Ticker Associations
After 2-3 hours, check ticker association rates:

```bash
# Query via Lambda
echo '{"sql":"SELECT COUNT(*) as total, COUNT(*) FILTER (WHERE array_length(tickers, 1) > 0) as with_tickers, ROUND(100.0 * COUNT(*) FILTER (WHERE array_length(tickers, 1) > 0) / COUNT(*), 1) as percentage FROM inbound_events_classified WHERE created_at >= NOW() - INTERVAL '\''2 hours'\''"}' | \
  aws lambda invoke \
  --function-name ops-pipeline-db-query \
  --region us-west-2 \
  --cli-binary-format raw-in-base64-out \
  --payload file:///dev/stdin \
  /tmp/check.json && cat /tmp/check.json | jq '.body | fromjson'
```

**Success Criteria:** >50% ticker association rate

### Step 7: Verify Signal Generation
Once ticker associations are working, check for signals:

```bash
# Check for sentiment data reaching signal engine
aws logs tail /ecs/ops-pipeline/signal-engine-1m \
  --region us-west-2 \
  --since 10m

# Check for recommendations
echo '{"sql":"SELECT COUNT(*), MIN(created_at), MAX(created_at) FROM dispatch_recommendations"}' | \
  aws lambda invoke \
  --function-name ops-pipeline-db-query \
  --region us-west-2 \
  --cli-binary-format raw-in-base64-out \
  --payload file:///dev/stdin \
  /tmp/check.json && cat /tmp/check.json | jq '.body | fromjson'
```

### Step 8: Monitor Bedrock Costs
Track AI inference usage and costs:

```bash
# CloudWatch Logs for AI usage
aws logs tail /ecs/ops-pipeline/classifier-worker \
  --region us-west-2 \
  --filter-pattern "ai_ticker_inference_used" \
  --since 1h

# Expected: <$0.10/day at ~300 news items/day
```

## Phase 11 Enhancements Summary

### Part A: Better RSS Feeds ✅
Added 7 ticker-specific feeds:
- https://finance.yahoo.com/rss/headline?s=AAPL
- https://finance.yahoo.com/rss/headline?s=MSFT
- https://finance.yahoo.com/rss/headline?s=GOOGL
- https://finance.yahoo.com/rss/headline?s=AMZN
- https://finance.yahoo.com/rss/headline?s=META
- https://finance.yahoo.com/rss/headline?s=NVDA
- https://finance.yahoo.com/rss/headline?s=TSLA

### Part B: AI Ticker Inference ✅
- **Implementation:** `services/classifier_worker/nlp/ai_ticker_inference.py`
- **Model:** AWS Bedrock with Claude 3 Haiku
- **Fallback Logic:** Regex first, AI when needed
- **Cost:** ~$2/month for 300 news items/day
- **IAM:** bedrock:InvokeModel added to ops-pipeline-ecs-task-role

## Problem Being Solved

**Issue:** 0 of 301 news items had ticker associations (0%)

**Root Cause:** RSS feeds provided macro news without ticker mentions
- Example: "Novo Nordisk rise" (no NVO ticker)
- Example: "ASML AI boost" (no ticker mentioned)
- Example: "Trump tariffs" (no affected stocks listed)

**Solution:** Two-pronged approach
1. **Better feeds:** Yahoo Finance ticker-specific RSS (direct mentions)
2. **AI inference:** Claude analyzes context to infer affected tickers

**Expected Result:** 50-70% ticker association rate

## Files Modified

### Phase 11 Code
1. `services/classifier_worker/nlp/ai_ticker_inference.py` - NEW
2. `services/classifier_worker/main.py` - AI integration
3. `deploy/classifier-task-definition.json` - Digest pinned

### Infrastructure (Already Done Day 6)
4. `services/feature_computer_1m/db.py` - Adaptive lookback
5. `services/signal_engine_1m/db.py` - Sentiment aggregation fix
6. `services/signal_engine_1m/rules.py` - Directional sentiment

## Next Session Checklist

When you return to complete the deployment:

- [ ] Refresh AWS credentials
- [ ] Register task definition (get revision number)
- [ ] Get current EventBridge rule config
- [ ] Update EventBridge rule with new revision
- [ ] Verify next classifier run executes successfully
- [ ] Wait 2-3 hours for news accumulation
- [ ] Check ticker association rates (target: >50%)
- [ ] Verify signal generation starts working
- [ ] Confirm dispatcher executes trades
- [ ] Monitor Bedrock costs
- [ ] Create PHASE_11_COMPLETE.md document

## Important Notes

1. **Image is pinned:** Using digest ensures immutability
2. **No rollback needed:** Old task definition still available if issues arise
3. **Graceful degradation:** AI inference has fallback handling
4. **Cost monitoring:** Set up billing alerts if needed ($5/month threshold)
5. **Observation period:** May need to restart 7-day period if behavior changes significantly

---

**Deployment paused at:** Task definition ready, awaiting AWS credential refresh  
**Resume by:** Running Step 1 (refresh credentials) then Step 2 (register task def)
