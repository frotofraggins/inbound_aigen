#!/bin/bash
# Deploy option price update fix to BOTH position manager services
# Fix: Use option_symbol instead of ticker when querying Alpaca for option prices

set -e

echo "🔧 DEPLOYING OPTION PRICE UPDATE FIX"
echo "Fix: Use option_symbol (e.g., MSFT260220P00400000) not ticker (e.g., MSFT)"
echo ""

# Build and push position-manager image
cd services/position_manager

echo "🔨 Building new Docker image with --no-cache..."
docker build --no-cache -t 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/position-manager:latest .

echo "🔑 Logging in to ECR..."
aws ecr get-login-password --region us-west-2 | \
  docker login --username AWS --password-stdin 160027201036.dkr.ecr.us-west-2.amazonaws.com

echo "📤 Pushing image to ECR..."
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/position-manager:latest

echo "✅ Docker image pushed to ECR"

# Force new deployment for large account
echo ""
echo "🚀 Deploying to LARGE account service..."
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service position-manager-service \
  --force-new-deployment \
  --region us-west-2

echo "✅ Large account service deployment initiated"

# Force new deployment for tiny account  
echo ""
echo "🚀 Deploying to TINY account service..."
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service position-manager-tiny-service \
  --force-new-deployment \
  --region us-west-2

echo "✅ Tiny account service deployment initiated"

echo ""
echo "✅ DEPLOYMENT COMPLETE"
echo ""
echo "Wait 60 seconds for tasks to start, then verify:"
echo "  python3 scripts/check_msft_tracking.py"
echo ""
echo "Expected: Database prices should match Alpaca prices (updating every minute)"
echo "MSFT PUT should show ~$12.35 (not $9.00)"
