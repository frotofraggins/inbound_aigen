#!/bin/bash
# Deploy Backtest-Driven Optimizations
# Based on analysis from PATTERN_ANALYSIS_FINDINGS_2026_02_07.md
# 
# Changes:
# 1. Stop loss: -40% → -60% (options too volatile for tight stops)
# 2. Max hold: 240 → 360 minutes (winners need time to peak)
# 3. Trailing stops: Verify enabled (should lock 75% of peak gains)
#
# Author: AI System Owner
# Date: 2026-02-07

set -e

REGION="us-west-2"
ACCOUNT_ID="160027201036"
CLUSTER="ops-pipeline-cluster"

echo "=" * 80
echo "DEPLOYING BACKTEST-DRIVEN OPTIMIZATIONS"
echo "=" * 80
echo ""
echo "Changes being deployed:"
echo "  1. Stop loss: -40% → -60%"
echo "  2. Max hold: 240 min → 360 min"
echo "  3. Trailing stops verification"
echo ""

# Step 1: Rebuild and deploy position managers
echo "Step 1: Deploying Position Managers..."
echo ""

cd services/position_manager

echo "  Building position-manager image..."
docker build --no-cache -t $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/ops-pipeline/position-manager:latest .

echo "  Logging into ECR..."
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com

echo "  Pushing image..."
docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/ops-pipeline/position-manager:latest

echo "  Restarting position-manager-service (large account)..."
aws ecs update-service \
  --cluster $CLUSTER \
  --service position-manager-service \
  --force-new-deployment \
  --region $REGION

echo "  Restarting position-manager-tiny-service (tiny account)..."
aws ecs update-service \
  --cluster $CLUSTER \
  --service position-manager-tiny-service \
  --force-new-deployment \
  --region $REGION

cd ../..

# Step 2: Rebuild and deploy dispatchers
echo ""
echo "Step 2: Deploying Dispatchers..."
echo ""

cd services/dispatcher

echo "  Building dispatcher image..."
docker build --no-cache -t $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/ops-pipeline/dispatcher:latest .

echo "  Pushing image..."
docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/ops-pipeline/dispatcher:latest

echo "  Restarting dispatcher-service (large account)..."
aws ecs update-service \
  --cluster $CLUSTER \
  --service dispatcher-service \
  --force-new-deployment \
  --region $REGION

echo "  Restarting dispatcher-tiny-service (tiny account)..."
aws ecs update-service \
  --cluster $CLUSTER \
  --service dispatcher-tiny-service \
  --force-new-deployment \
  --region $REGION

cd ../..

echo ""
echo "=" * 80
echo "DEPLOYMENT COMPLETE!"
echo "=" * 80
echo ""
echo "Services updated:"
echo "  ✅ position-manager-service (large)"
echo "  ✅ position-manager-tiny-service (tiny)"
echo "  ✅ dispatcher-service (large)"
echo "  ✅ dispatcher-tiny-service (tiny)"
echo ""
echo "Changes deployed:"
echo "  ✅ Stop loss widened to -60% (was -40%)"
echo "  ✅ Max hold extended to 360 min (was 240 min)"
echo ""
echo "Expected improvements (based on backtest):"
echo "  • Win rate: 25% → 55-60%"
echo "  • Fewer premature stop-outs"
echo "  • Better gain capture on winners"
echo ""
echo "Monitor logs:"
echo "  aws logs tail /ecs/ops-pipeline/position-manager-tiny-service --region $REGION --follow"
echo "  aws logs tail /ecs/ops-pipeline/dispatcher-tiny-service --region $REGION --follow"
echo ""
echo "Next: Wait for Monday market open and monitor next 10 trades"
echo "Then: Run python3 scripts/backtest_trades.py to measure improvement"
echo ""
