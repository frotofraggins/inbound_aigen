# Phase 8.0a: Watchlist Engine - DEPLOYMENT COMPLETE ✅

**Deployment Date:** 2026-01-12  
**Service:** ops-pipeline-watchlist-engine-5m  
**Schedule:** Every 5 minutes  
**Status:** Deployed and scheduled

---

## What Was Deployed

The Watchlist Engine dynamically selects the top 30 stocks from a universe of 36 tech stocks based on:
- Sentiment activity (news count + strength + recency)
- Volatility expansion (vol_ratio)
- Setup quality (distance from SMA20)
- Trend alignment (sentiment matches trend direction)

**Scoring Formula:**
```
watch_score = 
  0.35 × sentiment_pressure +
  0.25 × setup_quality +
  0.20 × vol_score +
  0.20 × trend_alignment
```

---

## Deployment Steps Completed

1. ✅ Created ECR repository: `ops-pipeline/watchlist-engine-5m`
2. ✅ Built Docker image locally
3. ✅ Pushed image to ECR: `160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/watchlist-engine-5m:latest`
4. ✅ Registered ECS task definition: `ops-pipeline-watchlist-engine-5m:1`
5. ✅ Updated IAM role trust policy to allow EventBridge Scheduler
6. ✅ Created EventBridge schedule: `rate(5 minutes)`

---

## AWS Resources Created

### ECR Repository
- **Name:** ops-pipeline/watchlist-engine-5m
- **URI:** 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/watchlist-engine-5m
- **ARN:** arn:aws:ecr:us-west-2:160027201036:repository/ops-pipeline/watchlist-engine-5m

### ECS Task Definition
- **Family:** ops-pipeline-watchlist-engine-5m
- **Revision:** 1
- **ARN:** arn:aws:ecs:us-west-2:160027201036:task-definition/ops-pipeline-watchlist-engine-5m:1
- **CPU:** 256
- **Memory:** 512 MB
- **Network Mode:** awsvpc (Fargate)
- **Execution Role:** ops-pipeline-ecs-task-role
- **Task Role:** ops-pipeline-ecs-task-role

### EventBridge Schedule
- **Name:** ops-pipeline-watchlist-engine-5m
- **ARN:** arn:aws:scheduler:us-west-2:160027201036:schedule/default/ops-pipeline-watchlist-engine-5m
- **Expression:** rate(5 minutes)
- **Target:** ops-pipeline-cluster ECS task
- **Network:** Public subnet with public IP enabled

### CloudWatch Log Group
- **Name:** /ecs/ops-pipeline/watchlist-engine-5m
- **Auto-created:** Yes (via awslogs-create-group: true)
- **Retention:** Default (never expire)

---

## Service Configuration

### Container Settings
- **Image:** Latest from ECR
- **Essential:** true
- **Environment Variables:**
  - AWS_REGION=us-west-2

### Network Configuration
- **Subnet:** subnet-0c182a149eeef918a (public)
- **Security Group:** sg-0cd16a909f4e794ce
- **Public IP:** Enabled
- **VPC:** vpc-0444cb2b7a3457502

### Database Access
- Reads from SSM parameters for connection details
- Connects to RDS: ops-pipeline-db.cls4wuyg010k.us-west-2.rds.amazonaws.com
- Uses Secrets Manager for credentials: ops-pipeline/db

---

## How to Verify Deployment

### 1. Check Running Tasks
```bash
aws ecs list-tasks --cluster ops-pipeline-cluster --region us-west-2
```

### 2. View Logs (after first execution)
```bash
aws logs filter-log-events \
  --log-group-name /ecs/ops-pipeline/watchlist-engine-5m \
  --start-time $(($(date +%s) - 600))000 \
  --region us-west-2 \
  --max-items 50
```

### 3. Query Watchlist State (from within VPC/Lambda)
```sql
-- See current top 30 watchlist
SELECT 
  ticker, 
  watch_score, 
  rank,
  entry_count,
  last_updated
FROM watchlist_state 
WHERE in_watchlist = TRUE 
ORDER BY rank;

-- Count total stocks in watchlist
SELECT COUNT(*) FROM watchlist_state WHERE in_watchlist = TRUE;

-- See recent score changes
SELECT 
  ticker,
  watch_score,
  in_watchlist,
  last_updated
FROM watchlist_state 
ORDER BY last_updated DESC 
LIMIT 10;
```

### 4. Check Schedule Status
```bash
aws scheduler get-schedule \
  --name ops-pipeline-watchlist-engine-5m \
  --region us-west-2
```

---

## Expected Behavior

**First Execution:**
- Will start within 5 minutes of deployment
- Queries lane_features for latest technical indicators
- Aggregates sentiment from inbound_events_classified
- Computes scores for all 36 universe tickers
- Selects top 30 based on watch_score >= 0.6
- Writes results to watchlist_state table

**Ongoing Operation:**
- Runs every 5 minutes
- Updates scores based on latest data
- Automatically adds/removes stocks from watchlist
- Maintains stickiness (new stock must beat #30 by 10%)
- Tracks entry_count and maintains rank ordering

**Selection Rules:**
- Entry threshold: watch_score >= 0.6
- Exit threshold: watch_score < 0.3 for 15+ minutes
- Rank updates: Every execution
- Maximum: 30 stocks in watchlist at once

---

## Service Code Location

All watchlist engine code is in:
```
services/watchlist_engine_5m/
├── config.py      # AWS configuration loader
├── db.py          # Database operations
├── scoring.py     # Scoring algorithm
├── main.py        # Main orchestration
├── requirements.txt
└── Dockerfile
```

---

## Cost Impact

**Monthly Cost:** ~$0.30
- 5-minute intervals = 8,640 executions/month
- 256 CPU, 512 MB memory
- ~10 seconds per execution
- Total: 24 hours compute time/month

---

## Next Steps

1. ✅ **Phase 8.0a Complete** - Watchlist Engine deployed
2. 🔄 **Phase 8.1 Next** - Build Signal Engine
   - Will process only the top 30 watchlist stocks
   - Generate BUY/SELL/OPTIONS recommendations
   - Write to dispatch_recommendations table
3. **Phase 9** - Build Dispatcher (dry-run mode)
4. **Phase 10** - Add monitoring and alerts

---

## Troubleshooting

**If logs show connection errors:**
- Verify RDS security group allows inbound from ECS security group
- Check VPC endpoints are configured for SSM and Secrets Manager
- Verify IAM task role has permissions for SSM and Secrets Manager

**If no data appears in watchlist_state:**
- Ensure lane_features has recent data (feature-computer-1m running)
- Ensure inbound_events_classified has sentiment data (classifier running)
- Check logs for SQL errors or scoring issues

**If schedule doesn't trigger:**
- Verify EventBridge scheduler role has assume permissions
- Check schedule is not disabled
- View EventBridge Scheduler execution history in console

---

## IAM Trust Policy Update

Updated `ops-pipeline-eventbridge-ecs-role` to trust both:
- events.amazonaws.com (EventBridge Rules)
- scheduler.amazonaws.com (EventBridge Scheduler)

Trust policy saved in: `deploy/eventbridge-scheduler-trust-policy.json`

---

**Deployment completed successfully. Service will begin operations within 5 minutes.**
