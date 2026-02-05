#!/bin/bash
# Deploy features capture fix to BOTH dispatcher services
# Fix: Pass features_snapshot from recommendations through to executions

set -e

echo "🔧 DEPLOYING FEATURES CAPTURE FIX"
echo "Fix: Capture market conditions (trend, sentiment, volume) at entry time"
echo ""

# Build and push dispatcher image
cd services/dispatcher

echo "🔨 Building new Docker image with --no-cache..."
docker build --no-cache -t 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/dispatcher:latest .

echo "🔑 Logging in to ECR..."
aws ecr get-login-password --region us-west-2 | \
  docker login --username AWS --password-stdin 160027201036.dkr.ecr.us-west-2.amazonaws.com

echo "📤 Pushing image to ECR..."
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/dispatcher:latest

echo "✅ Docker image pushed to ECR"

# Force new deployment for large account
echo ""
echo "🚀 Deploying to LARGE account dispatcher..."
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service dispatcher-service \
  --force-new-deployment \
  --region us-west-2

echo "✅ Large account dispatcher deployment initiated"

# Force new deployment for tiny account  
echo ""
echo "🚀 Deploying to TINY account dispatcher..."
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service dispatcher-tiny-service \
  --force-new-deployment \
  --region us-west-2

echo "✅ Tiny account dispatcher deployment initiated"

echo ""
echo "✅ DEPLOYMENT COMPLETE"
echo ""
echo "Wait 60 seconds for tasks to start, then verify:"
echo "  python3 -c \"Check next trade has entry_features_json populated\""
echo ""
echo "Expected: Future trades will have market conditions captured"
echo "  - trend_state: +1/-1/0"
echo "  - sentiment_score: 0.0-1.0"
echo "  - volume_ratio: e.g. 1.8"
echo "  - distance_sma20: e.g. 0.015"
