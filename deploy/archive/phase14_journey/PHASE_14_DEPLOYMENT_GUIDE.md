# Phase 14: AI Learning System Deployment Guide

**Date:** January 26, 2026  
**Components:** Ticker Discovery Service + Opportunity Analyzer Service  
**Purpose:** AI-powered ticker selection and trade opportunity analysis using Bedrock Sonnet

---

## Overview

Phase 14 adds two AI-powered services that use AWS Bedrock (Claude 3.5 Sonnet) to:

1. **Ticker Discovery** - Analyzes market every 6 hours, recommends 25-35 tickers for trading
2. **Opportunity Analyzer** - Nightly analysis of missed trades with AI explanations

Both services update the database and provide automated learning/optimization.

---

## Prerequisites

### 1. AWS Resources Required
- **Bedrock Access:** Claude 3.5 Sonnet model enabled in us-west-2
- **SES Email:** Verified sender email for reports (noreply@ops-pipeline.com)
- **Lambda Role:** ops-lambda-role with permissions for:
  - Bedrock InvokeModel
  - RDS PostgreSQL access
  - SSM Parameter read/write
  - SES SendEmail
  - CloudWatch Logs

### 2. Database Migration
- Migration 010 adds `ticker_universe` and `missed_opportunities` tables
- Must be applied before deploying services

### 3. SSM Parameter
- `/ops-pipeline/tickers` must exist (currently holds 25 tickers)
- Services will update this parameter

---

## Part 1: Apply Database Migration

### Step 1: Create Migration Payload

```bash
cd /home/nflos/workplace/inbound_aigen

# Create payload for Lambda
cat > /tmp/migration_010_payload.json << 'EOF'
{
  "migration_file": "010_add_ai_learning_tables.sql",
  "migration_sql": "-- Migration content will be read from file"
}
EOF
```

### Step 2: Read Migration SQL

```bash
# Read the migration SQL
MIGRATION_SQL=$(cat db/migrations/010_add_ai_learning_tables.sql)

# Create full payload with SQL content
cat > /tmp/migration_010_payload.json << EOF
{
  "migration_file": "010_add_ai_learning_tables.sql",
  "migration_sql": $(echo "$MIGRATION_SQL" | jq -Rs .)
}
EOF
```

### Step 3: Apply via Lambda

```bash
aws lambda invoke \
  --function-name ops-db-migrator \
  --payload file:///tmp/migration_010_payload.json \
  --region us-west-2 \
  /tmp/migration_010_response.json

# Check result
cat /tmp/migration_010_response.json | jq .
```

**Expected Output:**
```json
{
  "statusCode": 200,
  "body": "{\"success\": true, \"migration\": \"010_add_ai_learning_tables.sql\", \"tables_created\": 2, \"views_created\": 3}"
}
```

### Step 4: Verify Tables

```bash
# Query via Lambda to verify
cat > /tmp/verify_tables.json << 'EOF'
{
  "query": "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('ticker_universe', 'missed_opportunities') ORDER BY table_name"
}
EOF

aws lambda invoke \
  --function-name ops-db-query \
  --payload file:///tmp/verify_tables.json \
  --region us-west-2 \
  /tmp/verify_response.json

cat /tmp/verify_response.json | jq .
```

---

## Part 2: Deploy Ticker Discovery Lambda

### Step 1: Package Lambda

```bash
cd services/ticker_discovery

# Clean previous builds
rm -rf package ticker_discovery_lambda.zip

# Install dependencies
pip install -r requirements.txt -t package/

# Copy code
cp discovery.py package/

# Create ZIP
cd package
zip -r ../ticker_discovery_lambda.zip . -q
cd ..

ls -lh ticker_discovery_lambda.zip
```

### Step 2: Create/Update Lambda

```bash
LAMBDA_NAME="ops-ticker-discovery"
LAMBDA_ROLE="arn:aws:iam::381492033317:role/ops-lambda-role"

# Check if exists
if aws lambda get-function --function-name ${LAMBDA_NAME} --region us-west-2 2>/dev/null; then
    echo "Updating existing Lambda..."
    aws lambda update-function-code \
        --function-name ${LAMBDA_NAME} \
        --zip-file fileb://ticker_discovery_lambda.zip \
        --region us-west-2
else
    echo "Creating new Lambda..."
    aws lambda create-function \
        --function-name ${LAMBDA_NAME} \
        --runtime python3.11 \
        --role ${LAMBDA_ROLE} \
        --handler discovery.lambda_handler \
        --zip-file fileb://ticker_discovery_lambda.zip \
        --timeout 300 \
        --memory-size 512 \
        --environment Variables="{
            DB_HOST=ops-pipeline-db.cluster-cjvnjyvvxkhr.us-west-2.rds.amazonaws.com,
            DB_NAME=ops_pipeline,
            DB_USER=postgres,
            DB_PASSWORD=your_password_here
        }" \
        --region us-west-2
fi
```

### Step 3: Create EventBridge Schedule

```bash
# Create schedule: Every 6 hours (6 AM, 12 PM, 6 PM, 12 AM ET)
# Cron: 0 11,17,23,5 * * ? * (UTC times for ET hours)

aws events put-rule \
    --name ops-ticker-discovery-schedule \
    --schedule-expression "cron(0 11,17,23,5 * * ?)" \
    --state ENABLED \
    --description "Run ticker discovery every 6 hours" \
    --region us-west-2

# Add Lambda permission
aws lambda add-permission \
    --function-name ${LAMBDA_NAME} \
    --statement-id AllowEventBridgeInvoke \
    --action lambda:InvokeFunction \
    --principal events.amazonaws.com \
    --source-arn arn:aws:events:us-west-2:381492033317:rule/ops-ticker-discovery-schedule \
    --region us-west-2 2>/dev/null || echo "Permission already exists"

# Add target
aws events put-targets \
    --rule ops-ticker-discovery-schedule \
    --targets "Id=1,Arn=arn:aws:lambda:us-west-2:381492033317:function:${LAMBDA_NAME}" \
    --region us-west-2
```

### Step 4: Test Manually

```bash
# Invoke Lambda directly
aws lambda invoke \
    --function-name ${LAMBDA_NAME} \
    --payload '{}' \
    --region us-west-2 \
    /tmp/ticker_discovery_test.json

# Check response
cat /tmp/ticker_discovery_test.json | jq .
```

**Expected Output:**
```json
{
  "statusCode": 200,
  "body": "{
    \"success\": true,
    \"recommendations_count\": 35,
    \"active_tickers_count\": 28,
    \"active_tickers\": [\"NVDA\", \"AMD\", \"GOOGL\", ...],
    \"elapsed_seconds\": 15.3
  }"
}
```

---

## Part 3: Deploy Opportunity Analyzer Lambda

### Step 1: Verify SES Email

```bash
# Check if email is verified
aws ses get-identity-verification-attributes \
    --identities noreply@ops-pipeline.com \
    --region us-west-2

# If not verified, verify it
aws ses verify-email-identity \
    --email-address noreply@ops-pipeline.com \
    --region us-west-2

# Check inbox for verification email
```

### Step 2: Package Lambda

```bash
cd services/opportunity_analyzer

# Clean previous builds
rm -rf package opportunity_analyzer_lambda.zip

# Install dependencies
pip install -r requirements.txt -t package/

# Copy code
cp analyzer.py package/

# Create ZIP
cd package
zip -r ../opportunity_analyzer_lambda.zip . -q
cd ..

ls -lh opportunity_analyzer_lambda.zip
```

### Step 3: Create/Update Lambda

```bash
LAMBDA_NAME="ops-opportunity-analyzer"
LAMBDA_ROLE="arn:aws:iam::381492033317:role/ops-lambda-role"

# Check if exists
if aws lambda get-function --function-name ${LAMBDA_NAME} --region us-west-2 2>/dev/null; then
    echo "Updating existing Lambda..."
    aws lambda update-function-code \
        --function-name ${LAMBDA_NAME} \
        --zip-file fileb://opportunity_analyzer_lambda.zip \
        --region us-west-2
else
    echo "Creating new Lambda..."
    aws lambda create-function \
        --function-name ${LAMBDA_NAME} \
        --runtime python3.11 \
        --role ${LAMBDA_ROLE} \
        --handler analyzer.lambda_handler \
        --zip-file fileb://opportunity_analyzer_lambda.zip \
        --timeout 600 \
        --memory-size 1024 \
        --environment Variables="{
            DB_HOST=ops-pipeline-db.cluster-cjvnjyvvxkhr.us-west-2.rds.amazonaws.com,
            DB_NAME=ops_pipeline,
            DB_USER=postgres,
            DB_PASSWORD=your_password_here,
            EMAIL_FROM=noreply@ops-pipeline.com,
            EMAIL_TO=nsflournoy@gmail.com
        }" \
        --region us-west-2
fi
```

### Step 4: Create EventBridge Schedule

```bash
# Create schedule: Daily at 6 PM ET = 11 PM UTC
aws events put-rule \
    --name ops-opportunity-analyzer-schedule \
    --schedule-expression "cron(0 23 * * ? *)" \
    --state ENABLED \
    --description "Run opportunity analyzer daily at 6 PM ET" \
    --region us-west-2

# Add Lambda permission
aws lambda add-permission \
    --function-name ${LAMBDA_NAME} \
    --statement-id AllowEventBridgeInvoke \
    --action lambda:InvokeFunction \
    --principal events.amazonaws.com \
    --source-arn arn:aws:events:us-west-2:381492033317:rule/ops-opportunity-analyzer-schedule \
    --region us-west-2 2>/dev/null || echo "Permission already exists"

# Add target
aws events put-targets \
    --rule ops-opportunity-analyzer-schedule \
    --targets "Id=1,Arn=arn:aws:lambda:us-west-2:381492033317:function:${LAMBDA_NAME}" \
    --region us-west-2
```

### Step 5: Test with Today's Date

```bash
# Test with today's date
TODAY=$(date +%Y-%m-%d)

aws lambda invoke \
    --function-name ${LAMBDA_NAME} \
    --payload "{\"analysis_date\": \"${TODAY}\"}" \
    --region us-west-2 \
    /tmp/opportunity_analyzer_test.json

# Check response
cat /tmp/opportunity_analyzer_test.json | jq .
```

**Expected Output:**
```json
{
  "statusCode": 200,
  "body": "{
    \"success\": true,
    \"analysis_date\": \"2026-01-26\",
    \"missed_count\": 5,
    \"should_have_traded\": 2,
    \"correctly_skipped\": 3,
    \"elapsed_seconds\": 45.2
  }"
}
```

---

## Part 4: Verification

### 1. Check Ticker Discovery

```bash
# Query active tickers
cat > /tmp/check_tickers.json << 'EOF'
{
  "query": "SELECT * FROM v_active_tickers LIMIT 10"
}
EOF

aws lambda invoke \
    --function-name ops-db-query \
    --payload file:///tmp/check_tickers.json \
    --region us-west-2 \
    /tmp/tickers_response.json

cat /tmp/tickers_response.json | jq .
```

### 2. Check SSM Parameter

```bash
# Verify SSM parameter was updated
aws ssm get-parameter \
    --name /ops-pipeline/tickers \
    --region us-west-2 | jq -r '.Parameter.Value'
```

### 3. Check Missed Opportunities

```bash
# Query today's analysis
cat > /tmp/check_missed.json << EOF
{
  "query": "SELECT * FROM v_daily_missed_summary WHERE analysis_date = '$(date +%Y-%m-%d)'"
}
EOF

aws lambda invoke \
    --function-name ops-db-query \
    --payload file:///tmp/check_missed.json \
    --region us-west-2 \
    /tmp/missed_response.json

cat /tmp/missed_response.json | jq .
```

### 4. Check Email

- Look for email from noreply@ops-pipeline.com
- Subject: "Daily Trading Analysis - January 26, 2026"
- Should contain HTML report with missed opportunities

---

## Monitoring

### CloudWatch Logs

```bash
# Ticker Discovery logs
aws logs tail /aws/lambda/ops-ticker-discovery --follow

# Opportunity Analyzer logs
aws logs tail /aws/lambda/ops-opportunity-analyzer --follow
```

### EventBridge Schedules

```bash
# List all schedules
aws events list-rules --region us-west-2 | grep ops-

# Check next execution
aws events describe-rule \
    --name ops-ticker-discovery-schedule \
    --region us-west-2
```

### Database Queries

```sql
-- How many tickers active?
SELECT COUNT(*) FROM ticker_universe WHERE active = true;

-- Latest discovery run
SELECT MAX(last_updated) FROM ticker_universe;

-- Today's missed opportunities
SELECT * FROM v_daily_missed_summary 
WHERE analysis_date = CURRENT_DATE;

-- Patterns over last week
SELECT * FROM v_ticker_missed_patterns;
```

---

## Troubleshooting

### Issue: Bedrock Access Denied

**Solution:**
```bash
# Verify Bedrock model access
aws bedrock list-foundation-models --region us-west-2 | grep -A5 "claude-3-5-sonnet"

# Request access if needed (AWS Console > Bedrock > Model Access)
```

### Issue: Email Not Sending

**Solution:**
```bash
# Verify SES identity
aws ses get-identity-verification-attributes \
    --identities noreply@ops-pipeline.com \
    --region us-west-2

# Check SES sending limits
aws ses get-send-quota --region us-west-2
```

### Issue: SSM Parameter Not Updating

**Solution:**
```bash
# Check Lambda IAM permissions
aws iam get-role-policy \
    --role-name ops-lambda-role \
    --policy-name ops-lambda-policy

# Manual SSM update test
aws ssm put-parameter \
    --name /ops-pipeline/tickers \
    --value "TEST,NVDA,AMD" \
    --overwrite \
    --region us-west-2
```

### Issue: Database Connection Timeout

**Solution:**
```bash
# Check security group allows Lambda
# Lambda should be in same VPC or have internet access
# RDS security group should allow inbound from Lambda security group

# Test database connection via query Lambda
cat > /tmp/test_db.json << 'EOF'
{
  "query": "SELECT 1"
}
EOF

aws lambda invoke \
    --function-name ops-db-query \
    --payload file:///tmp/test_db.json \
    --region us-west-2 \
    /tmp/test_response.json
```

---

## Success Criteria

- [x] Migration 010 applied successfully
- [x] ticker_universe table has 28+ active tickers
- [x] SSM parameter updated with new ticker list
- [x] Ticker discovery runs every 6 hours
- [x] Opportunity analyzer runs daily at 6 PM ET
- [x] Email reports delivered successfully
- [x] missed_opportunities table populated with analysis
- [x] All services logging to CloudWatch
- [x] No errors in Lambda execution

---

## Next Steps

1. **Monitor for 1 week** - Collect 7 days of recommendations and analyses
2. **Review patterns** - Which tickers keep getting recommended? Which trades were missed?
3. **Adjust thresholds** - Based on AI recommendations in daily emails
4. **Add automation** - Auto-adjust signal engine thresholds based on analyses
5. **Expand analysis** - Add win/loss tracking for actual trades

---

## Files Created

```
services/ticker_discovery/
├── discovery.py           # Main service code
└── requirements.txt       # Dependencies

services/opportunity_analyzer/
├── analyzer.py           # Main service code
└── requirements.txt      # Dependencies

db/migrations/
└── 010_add_ai_learning_tables.sql  # Database schema

deploy/
└── PHASE_14_DEPLOYMENT_GUIDE.md    # This file
```

---

## Cost Estimate

- **Bedrock API:** ~$0.003/1K tokens
  - Ticker Discovery: 4x/day × 4K tokens = ~$0.05/day
  - Opportunity Analyzer: 1x/day × 10K tokens = ~$0.03/day
  - **Total:** ~$2.40/month

- **Lambda:** Free tier covers execution
- **SES:** Free tier (62,000 emails/month)

**Total Phase 14 Cost:** ~$2.50/month

---

**End of Deployment Guide**
