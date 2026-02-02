#!/bin/bash
# Comprehensive System Health Validation Script
# Run this to verify all services are operational

set -e

echo "=========================================="
echo "Ops Pipeline Health Validation"
echo "Date: $(date -u +%Y-%m-%d\ %H:%M:%S) UTC"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. Check Healthcheck Lambda
echo "1. Testing Healthcheck Lambda..."
HEALTH_RESULT=$(aws lambda invoke \
  --function-name ops-pipeline-healthcheck \
  --region us-west-2 \
  /tmp/health_check.json 2>&1)

if [ $? -eq 0 ]; then
    METRICS=$(cat /tmp/health_check.json | jq '.body | fromjson | .metrics')
    echo -e "${GREEN}✅ Healthcheck Lambda: OK${NC}"
    echo "$METRICS" | jq '.'
    
    # Extract key metrics
    FEATURE_LAG=$(echo "$METRICS" | jq -r '.feature_lag_sec')
    FEATURES_COMPUTED=$(echo "$METRICS" | jq -r '.features_computed_10m')
    DUPLICATES=$(echo "$METRICS" | jq -r '.duplicate_recos')
    
    # Validate thresholds
    if [ "$FEATURE_LAG" -lt 600 ]; then
        echo -e "${GREEN}✅ Feature lag OK: ${FEATURE_LAG}s < 600s${NC}"
    else
        echo -e "${RED}❌ Feature lag CRITICAL: ${FEATURE_LAG}s > 600s${NC}"
    fi
    
    if [ "$FEATURES_COMPUTED" -gt 0 ]; then
        echo -e "${GREEN}✅ Features computing: ${FEATURES_COMPUTED} tickers${NC}"
    else
        echo -e "${YELLOW}⚠️  No features computed (may be market closed)${NC}"
    fi
    
    if [ "$DUPLICATES" -eq 0 ]; then
        echo -e "${GREEN}✅ Idempotency intact: 0 duplicates${NC}"
    else
        echo -e "${RED}❌ CRITICAL: ${DUPLICATES} duplicate executions!${NC}"
    fi
else
    echo -e "${RED}❌ Healthcheck Lambda: FAILED${NC}"
    echo "$HEALTH_RESULT"
fi

echo ""
echo "2. Checking CloudWatch Metrics..."
METRIC_COUNT=$(aws cloudwatch list-metrics \
  --namespace OPsPipeline \
  --region us-west-2 \
  | jq '.Metrics | length')

if [ "$METRIC_COUNT" -eq 11 ]; then
    echo -e "${GREEN}✅ CloudWatch Metrics: $METRIC_COUNT/11 present${NC}"
else
    echo -e "${YELLOW}⚠️  CloudWatch Metrics: $METRIC_COUNT/11 (expected 11)${NC}"
fi

echo ""
echo "3. Checking CloudWatch Alarms..."
aws cloudwatch describe-alarms \
  --alarm-name-prefix ops-pipeline \
  --region us-west-2 \
  | jq -r '.MetricAlarms[] | "\(.AlarmName): \(.StateValue)"' \
  | while read -r line; do
    if [[ $line == *"OK"* ]]; then
        echo -e "${GREEN}✅ $line${NC}"
    elif [[ $line == *"INSUFFICIENT_DATA"* ]]; then
        echo -e "${YELLOW}⏳ $line (normal for new alarms)${NC}"
    else
        echo -e "${RED}❌ $line${NC}"
    fi
done

echo ""
echo "4. Checking EventBridge Schedules..."
SCHEDULES=$(aws scheduler list-schedules --region us-west-2 \
  | jq -r '.Schedules[] | select(.Name | startswith("ops-pipeline")) | "\(.Name): \(.State)"')

echo "$SCHEDULES" | while read -r line; do
    if [[ $line == *"ENABLED"* ]]; then
        echo -e "${GREEN}✅ $line${NC}"
    else
        echo -e "${RED}❌ $line${NC}"
    fi
done

echo ""
echo "5. Checking Recent Feature Computation..."
RECENT_FEATURE=$(aws logs filter-log-events \
  --log-group-name /ecs/ops-pipeline/feature-computer-1m \
  --region us-west-2 \
  --start-time $(($(date +%s) - 300))000 \
  --filter-pattern "feature_run_complete" \
  | jq -r '.events[-1].message' | jq '.')

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Recent Feature Run:${NC}"
    echo "$RECENT_FEATURE" | jq '{success, tickers_computed, tickers_skipped, tickers_failed}'
    
    COMPUTED=$(echo "$RECENT_FEATURE" | jq -r '.tickers_computed')
    if [ "$COMPUTED" -ge 7 ]; then
        echo -e "${GREEN}✅ Computing all 7 available tickers${NC}"
    elif [ "$COMPUTED" -gt 0 ]; then
        echo -e "${YELLOW}⚠️  Only computing $COMPUTED tickers${NC}"
    else
        echo -e "${RED}❌ No tickers being computed${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  No recent feature runs (may be expected)${NC}"
fi

echo ""
echo "6. Checking Database Telemetry..."
echo '{"sql":"SELECT COUNT(*) as total_bars, COUNT(DISTINCT ticker) as ticker_count, MAX(ts) as latest_bar FROM lane_telemetry"}' \
  | aws lambda invoke \
    --function-name ops-pipeline-db-query \
    --region us-west-2 \
    --cli-binary-format raw-in-base64-out \
    --payload file:///dev/stdin \
    /tmp/db_check.json > /dev/null 2>&1

if [ $? -eq 0 ]; then
    DB_RESULT=$(cat /tmp/db_check.json | jq '.body | fromjson | .rows[0]')
    echo -e "${GREEN}✅ Database Query: OK${NC}"
    echo "$DB_RESULT" | jq '.'
else
    echo -e "${RED}❌ Database Query: FAILED${NC}"
fi

echo ""
echo "=========================================="
echo "Health Check Complete"
echo "=========================================="
echo ""
echo "Summary:"
echo "  - Run this script daily during observation"
echo "  - Expected: All green checks, FeaturesComputed=7"
echo "  - Document any red/yellow items immediately"
echo ""
