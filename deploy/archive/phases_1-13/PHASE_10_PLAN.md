# Phase 10: Monitoring & Alerts
## Self-Defending Operations Layer

**Status:** PLANNING  
**Approval:** PENDING  
**Timeline:** 2-3 hours implementation + testing  
**Cost Impact:** +$5-10/month  

---

## Executive Summary

Phase 10 adds **automated monitoring** to replace human-in-the-loop health checks. This is the final critical gap before the system is truly production-ready.

### Why Now?
- Phase 9 logic is frozen ✅
- OVS-001 validation is GREEN ✅
- **Humans are still the monitoring system** ❌

If a service stalls at 3am, we won't know until morning. Data silently rots, baselines get corrupted, future ML labels become untrustworthy.

### Core Principle
**Phase 10 does NOT change trading behavior.** It observes, measures, and alerts. Zero impact on execution semantics.

---

## Phase 10.1: Automated Healthcheck (MANDATORY)

### Overview
Reuse `ops-pipeline-db-query` Lambda on a 5-minute EventBridge schedule. Emit CloudWatch custom metrics for all critical lag measurements.

### Metrics to Track
1. **telemetry_lag_sec** - Time since last OHLCV bar
2. **feature_lag_sec** - Time since last feature computation
3. **watchlist_lag_sec** - Time since last watchlist update
4. **reco_lag_sec** - Time since last recommendation generated
5. **exec_lag_sec** - Time since last execution attempt
6. **unfinished_runs** - Count of dispatcher_runs without finished_at in last 10 min
7. **duplicate_recos** - Count of duplicate executions (CRITICAL: should always be 0)

### Implementation Steps

#### 1. Create Healthcheck Lambda (New)
**File:** `services/healthcheck_lambda/lambda_function.py`

```python
import json
import boto3
import os
from datetime import datetime

cloudwatch = boto3.client('cloudwatch')
lambda_client = boto3.client('lambda')

QUERY_LAMBDA = 'ops-pipeline-db-query'
NAMESPACE = 'OPsPipeline'

HEALTH_QUERY = """
SELECT 
    EXTRACT(EPOCH FROM (NOW() - (SELECT MAX(ts) FROM lane_telemetry)))::int AS telemetry_lag_sec,
    EXTRACT(EPOCH FROM (NOW() - (SELECT MAX(computed_at) FROM lane_features)))::int AS feature_lag_sec,
    EXTRACT(EPOCH FROM (NOW() - (SELECT MAX(updated_at) FROM watchlist_state)))::int AS watchlist_lag_sec,
    EXTRACT(EPOCH FROM (NOW() - (SELECT MAX(created_at) FROM dispatch_recommendations)))::int AS reco_lag_sec,
    EXTRACT(EPOCH FROM (NOW() - (SELECT MAX(executed_at) FROM dispatch_executions)))::int AS exec_lag_sec,
    (SELECT COUNT(*) FROM dispatcher_runs 
     WHERE finished_at IS NULL 
       AND started_at >= NOW() - INTERVAL '10 minutes') AS unfinished_runs,
    (SELECT COUNT(*) FROM (
        SELECT recommendation_id 
        FROM dispatch_executions 
        GROUP BY recommendation_id 
        HAVING COUNT(*) > 1
    ) x) AS duplicate_recos
"""

def lambda_handler(event, context):
    """
    5-minute healthcheck: query DB via ops-pipeline-db-query, emit CloudWatch metrics.
    """
    try:
        # Query DB via existing Lambda
        response = lambda_client.invoke(
            FunctionName=QUERY_LAMBDA,
            InvocationType='RequestResponse',
            Payload=json.dumps({'sql': HEALTH_QUERY})
        )
        
        result = json.loads(response['Payload'].read())
        body = json.loads(result.get('body', '{}'))
        
        if body.get('error'):
            print(f"Query error: {body['error']}")
            return {'statusCode': 500, 'body': json.dumps({'error': body['error']})}
        
        metrics = body['rows'][0]
        timestamp = datetime.utcnow()
        
        # Emit CloudWatch metrics
        metric_data = [
            {
                'MetricName': 'TelemetryLag',
                'Value': metrics['telemetry_lag_sec'],
                'Unit': 'Seconds',
                'Timestamp': timestamp
            },
            {
                'MetricName': 'FeatureLag',
                'Value': metrics['feature_lag_sec'],
                'Unit': 'Seconds',
                'Timestamp': timestamp
            },
            {
                'MetricName': 'WatchlistLag',
                'Value': metrics['watchlist_lag_sec'],
                'Unit': 'Seconds',
                'Timestamp': timestamp
            },
            {
                'MetricName': 'RecommendationLag',
                'Value': metrics['reco_lag_sec'],
                'Unit': 'Seconds',
                'Timestamp': timestamp
            },
            {
                'MetricName': 'ExecutionLag',
                'Value': metrics['exec_lag_sec'],
                'Unit': 'Seconds',
                'Timestamp': timestamp
            },
            {
                'MetricName': 'UnfinishedRuns',
                'Value': metrics['unfinished_runs'],
                'Unit': 'Count',
                'Timestamp': timestamp
            },
            {
                'MetricName': 'DuplicateExecutions',
                'Value': metrics['duplicate_recos'],
                'Unit': 'Count',
                'Timestamp': timestamp
            }
        ]
        
        cloudwatch.put_metric_data(
            Namespace=NAMESPACE,
            MetricData=metric_data
        )
        
        print(f"Emitted metrics: {json.dumps(metrics)}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Health metrics emitted',
                'metrics': metrics
            })
        }
        
    except Exception as e:
        print(f"Healthcheck error: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
```

#### 2. Deploy Healthcheck Lambda
```bash
# Package
cd services/healthcheck_lambda
pip install -r requirements.txt -t package/
cp lambda_function.py package/
cd package && zip -r ../healthcheck_lambda.zip . && cd ..

# Upload
aws lambda create-function \
  --function-name ops-pipeline-healthcheck \
  --runtime python3.11 \
  --role arn:aws:iam::160027201036:role/ops-pipeline-lambda-role \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://healthcheck_lambda.zip \
  --timeout 30 \
  --region us-west-2

# Grant invoke permissions to itself
aws lambda add-permission \
  --function-name ops-pipeline-healthcheck \
  --statement-id AllowOpsQueryLambdaInvoke \
  --action lambda:InvokeFunction \
  --principal lambda.amazonaws.com \
  --region us-west-2
```

#### 3. Create EventBridge Schedule
```bash
aws scheduler create-schedule \
  --name ops-pipeline-healthcheck-5m \
  --schedule-expression "rate(5 minutes)" \
  --target '{
    "Arn": "arn:aws:lambda:us-west-2:160027201036:function:ops-pipeline-healthcheck",
    "RoleArn": "arn:aws:iam::160027201036:role/ops-pipeline-eventbridge-ecs-role"
  }' \
  --flexible-time-window '{"Mode": "OFF"}' \
  --region us-west-2
```

---

## Phase 10.2: CloudWatch Alarms (MANDATORY)

### Alarm Definitions

**Cost:** ~$2/month (4-6 alarms × $0.10/alarm + $0.30/metric)

#### 1. Telemetry Lag Alarm (WARN)
```bash
aws cloudwatch put-metric-alarm \
  --alarm-name ops-pipeline-telemetry-lag \
  --alarm-description "Telemetry data is stale (>180s)" \
  --metric-name TelemetryLag \
  --namespace OPsPipeline \
  --statistic Maximum \
  --period 300 \
  --evaluation-periods 2 \
  --threshold 180 \
  --comparison-operator GreaterThanThreshold \
  --region us-west-2
```

#### 2. Feature Lag Alarm (WARN)
```bash
aws cloudwatch put-metric-alarm \
  --alarm-name ops-pipeline-feature-lag \
  --alarm-description "Feature computation is behind (>600s)" \
  --metric-name FeatureLag \
  --namespace OPsPipeline \
  --statistic Maximum \
  --period 300 \
  --evaluation-periods 2 \
  --threshold 600 \
  --comparison-operator GreaterThanThreshold \
  --region us-west-2
```

#### 3. Dispatcher Completion Alarm (CRITICAL)
```bash
aws cloudwatch put-metric-alarm \
  --alarm-name ops-pipeline-dispatcher-stalled \
  --alarm-description "Dispatcher has unfinished runs (CRITICAL)" \
  --metric-name UnfinishedRuns \
  --namespace OPsPipeline \
  --statistic Maximum \
  --period 300 \
  --evaluation-periods 2 \
  --threshold 0 \
  --comparison-operator GreaterThanThreshold \
  --region us-west-2
```

#### 4. Duplicate Execution Alarm (PAGE IMMEDIATELY)
```bash
aws cloudwatch put-metric-alarm \
  --alarm-name ops-pipeline-duplicate-executions \
  --alarm-description "CRITICAL: Duplicate executions detected - idempotency violation" \
  --metric-name DuplicateExecutions \
  --namespace OPsPipeline \
  --statistic Maximum \
  --period 300 \
  --evaluation-periods 1 \
  --threshold 0 \
  --comparison-operator GreaterThanThreshold \
  --region us-west-2
```

### Alarm Actions (Optional)
To add SNS notifications:
```bash
# Create SNS topic
aws sns create-topic --name ops-pipeline-alerts --region us-west-2

# Subscribe email
aws sns subscribe \
  --topic-arn arn:aws:sns:us-west-2:160027201036:ops-pipeline-alerts \
  --protocol email \
  --notification-endpoint your-email@example.com \
  --region us-west-2

# Add to alarms with --alarm-actions
```

---

## Phase 10.3: Immutable Deployments (RECOMMENDED)

### Problem
Currently using `latest` tag for ECS images. During Day 1, dispatcher cached old image causing bugs.

### Solution
Pin all task definitions to **image digest** instead of `latest`.

#### Process
1. Build and push image with unique tag (e.g., commit SHA)
2. Get image digest: `docker inspect --format='{{.RepoDigests}}' <image>`
3. Update task definition with digest: `<repo>@sha256:<digest>`
4. Register new task definition revision
5. Update service to use new revision

#### Example
```json
{
  "image": "160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline-dispatcher@sha256:abc123..."
}
```

**Benefit:** Eliminates cache issues, enables true rollback, audit trail

**Implementation:** Post-observation (requires rebuild)

---

## Phase 10.4: Run Ledgers (OPTIONAL)

### Overview
Add append-only execution tracking for remaining services (telemetry, features, watchlist, signal).

**Similar to:** `dispatcher_runs` table pattern

### Benefits
- Professional ops visibility
- Enable RCA for any service
- Support future scaling analysis
- Zero impact on execution semantics

### Tables to Add (Migration 006)
```sql
-- Telemetry runs
CREATE TABLE telemetry_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    bars_fetched INT,
    bars_stored INT,
    error_message TEXT
);

-- Feature runs
CREATE TABLE feature_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    features_computed INT,
    error_message TEXT
);

-- Similar for watchlist_runs, signal_runs
```

**Implementation:** After 7-day observation completes

---

## What We Are NOT Doing

❌ **Outcome Tracking** - Requires labeling (Phase 11)  
❌ **Universe Expansion** - Need baseline first  
❌ **Strategy Changes** - Config freeze  
❌ **Dashboards** - Alarms are sufficient  
❌ **ML Anything** - Wait for clean baseline  

---

## Implementation Checklist

### Phase 10.1: Healthcheck (2 hours)
- [ ] Create `services/healthcheck_lambda/` directory
- [ ] Write `lambda_function.py` (healthcheck logic)
- [ ] Create `requirements.txt` (boto3 only)
- [ ] Package and deploy Lambda
- [ ] Grant Lambda→Lambda invoke permission
- [ ] Create EventBridge schedule (5 minutes)
- [ ] Verify metrics appear in CloudWatch console
- [ ] Test manual invocation

### Phase 10.2: Alarms (30 minutes)
- [ ] Create TelemetryLag alarm (>180s, 2 periods)
- [ ] Create FeatureLag alarm (>600s, 2 periods)
- [ ] Create UnfinishedRuns alarm (>0, 2 periods)
- [ ] Create DuplicateExecutions alarm (>0, 1 period)
- [ ] Optional: Create SNS topic + email subscription
- [ ] Optional: Add alarm actions to all alarms
- [ ] Test alarm by stopping a service

### Phase 10.3: Immutable Deployments (1 hour)
- [ ] Document current image digests
- [ ] Create script to pin task definitions to digests
- [ ] **DEFER:** Wait until after observation
- [ ] Update deployment process docs

### Phase 10.4: Run Ledgers (2 hours)
- [ ] Design migration 006 (run tables)
- [ ] **DEFER:** Wait until after observation
- [ ] Update services to log runs
- [ ] Test and validate

---

## Validation

### Healthcheck Lambda
```bash
# Manual test
aws lambda invoke \
  --function-name ops-pipeline-healthcheck \
  --region us-west-2 \
  /tmp/health.json && cat /tmp/health.json

# Check CloudWatch metrics
aws cloudwatch list-metrics \
  --namespace OPsPipeline \
  --region us-west-2

# View metric data
aws cloudwatch get-metric-statistics \
  --namespace OPsPipeline \
  --metric-name TelemetryLag \
  --start-time 2026-01-13T17:00:00Z \
  --end-time 2026-01-13T18:00:00Z \
  --period 300 \
  --statistics Maximum \
  --region us-west-2
```

### Alarms
```bash
# List alarms
aws cloudwatch describe-alarms \
  --alarm-name-prefix ops-pipeline \
  --region us-west-2

# Check alarm history
aws cloudwatch describe-alarm-history \
  --alarm-name ops-pipeline-telemetry-lag \
  --region us-west-2
```

### Test Alarm (controlled)
```bash
# Stop telemetry service temporarily
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service ops-pipeline-telemetry-1m \
  --desired-count 0 \
  --region us-west-2

# Wait 15 minutes
# Check alarm triggers

# Re-enable
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service ops-pipeline-telemetry-1m \
  --desired-count 1 \
  --region us-west-2
```

---

## Cost Analysis

### Phase 10.1: Healthcheck
- Lambda invocations: 12/hour × 24 × 30 = 8,640/month
- Cost: $0 (well within free tier)

### Phase 10.2: Alarms
- 4 alarms × $0.10 = $0.40/month
- 7 metrics × $0.30 = $2.10/month
- **Subtotal:** $2.50/month

### Phase 10.3: Immutable Deployments
- $0 (just process change)

### Phase 10.4: Run Ledgers (future)
- Storage: ~100MB/month = $0.02/month
- Query overhead: negligible

**Total Phase 10 Cost:** ~$2.50/month (alarms only)

---

## Timeline

### Day 1 (Today): Implementation
- Phase 10.1: Healthcheck Lambda + Schedule (2 hours)
- Phase 10.2: CloudWatch Alarms (30 min)
- Validation testing (30 min)
- Documentation update (30 min)

**Total:** ~3.5 hours

### Days 2-7: Observation
- Monitor alarms daily
- Verify no false positives
- Establish baseline alarm patterns

### Day 7+: Optional Extensions
- Phase 10.3: Immutable deployments (rebuild required)
- Phase 10.4: Run ledgers (migration 006)

---

## Success Criteria

✅ Healthcheck Lambda runs every 5 minutes  
✅ All 7 metrics appear in CloudWatch  
✅ Alarms are configured and testable  
✅ No false positives during observation  
✅ Human health checks are now optional  

---

## Rollback Plan

If Phase 10 causes issues:

1. **Disable healthcheck schedule:**
   ```bash
   aws scheduler delete-schedule \
     --name ops-pipeline-healthcheck-5m \
     --region us-west-2
   ```

2. **Delete alarms:**
   ```bash
   aws cloudwatch delete-alarms \
     --alarm-names ops-pipeline-telemetry-lag \
                  ops-pipeline-feature-lag \
                  ops-pipeline-dispatcher-stalled \
                  ops-pipeline-duplicate-executions \
     --region us-west-2
   ```

3. **Delete Lambda:**
   ```bash
   aws lambda delete-function \
     --function-name ops-pipeline-healthcheck \
     --region us-west-2
   ```

**Risk:** Minimal. Healthcheck is read-only observer.

---

## Next Steps After Phase 10

1. **Complete 7-day observation** with automated monitoring
2. **Analyze alarm patterns** (OVS-006 baseline)
3. **Choose Phase 11 path:**
   - Path A: Outcome tracking (ML prep)
   - Path B: Universe expansion (36-150 stocks)
   - Path C: Strategy enhancements (post-baseline)

---

## Files to Create

```
services/healthcheck_lambda/
├── lambda_function.py
├── requirements.txt
└── README.md

deploy/
└── PHASE_10_PLAN.md (this file)
└── PHASE_10_COMPLETE.md (after implementation)
```

---

## Approval Required

**Proceed with Phase 10.1 + 10.2?**
- Read-only healthcheck Lambda
- CloudWatch metrics + alarms
- Zero behavior changes
- ~$2.50/month cost increase

Reply with:
- ✅ **APPROVED** - Proceed with implementation
- ⏸️ **HOLD** - Need clarification on [specific concern]
- ❌ **REJECTED** - Use Option 1 (manual daily checks) instead
