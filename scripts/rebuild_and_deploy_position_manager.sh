#!/bin/bash
# Rebuild position manager with correct code and deploy
# This fixes the issue where service is running old code (5-min sleep instead of 1-min)

set -e

echo "🔨 Building new Docker image with updated code..."

# Build and push position-manager image
cd services/position_manager

# Build image with --no-cache to ensure fresh build
docker build --no-cache -t 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline-position-manager:latest .

# Login to ECR
aws ecr get-login-password --region us-west-2 | \
  docker login --username AWS --password-stdin 160027201036.dkr.ecr.us-west-2.amazonaws.com

# Push image
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline-position-manager:latest

echo "✅ Docker image pushed to ECR"

# Force new deployment for large account
echo "🚀 Deploying to large account service..."
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service position-manager-service \
  --force-new-deployment \
  --region us-west-2

echo "✅ Large account service deployment initiated"

# Force new deployment for tiny account  
echo "🚀 Deploying to tiny account service..."
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service position-manager-tiny-service \
  --force-new-deployment \
  --region us-west-2

echo "✅ Tiny account service deployment initiated"

echo ""
echo "✅ DEPLOYMENT COMPLETE"
echo ""
echo "Wait 60 seconds for tasks to start, then check logs:"
echo "  aws logs tail /ecs/ops-pipeline/position-manager-service --follow --region us-west-2"
echo ""
echo "Look for: 'Sleeping for 1 minute until next check...'"
echo "  (NOT 'Sleeping for 5 minutes')"
