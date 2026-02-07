#!/bin/bash
# Deploy Option Exit Fix - 2026-02-04
# Fixes premature option exits by widening thresholds and adding minimum hold time

set -e

echo "=== Deploying Option Exit Fix ==="
echo "Date: $(date)"
echo ""

# Build and push Docker image
echo "1. Building position manager Docker image..."
cd services/position_manager
docker build -t ops-pipeline-position-manager:option-exit-fix .

echo ""
echo "2. Tagging image..."
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
docker tag ops-pipeline-position-manager:option-exit-fix \
  ${AWS_ACCOUNT_ID}.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline-position-manager:option-exit-fix

docker tag ops-pipeline-position-manager:option-exit-fix \
  ${AWS_ACCOUNT_ID}.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline-position-manager:latest

echo ""
echo "3. Logging into ECR..."
aws ecr get-login-password --region us-west-2 | \
  docker login --username AWS --password-stdin \
  ${AWS_ACCOUNT_ID}.dkr.ecr.us-west-2.amazonaws.com

echo ""
echo "4. Pushing images to ECR..."
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline-position-manager:option-exit-fix
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline-position-manager:latest

cd ../..

echo ""
echo "5. Updating ECS services..."

# Update large account position manager
echo "  - Updating position-manager-large service..."
aws ecs update-service \
  --cluster ops-pipeline \
  --service position-manager-large \
  --force-new-deployment \
  --region us-west-2

# Update tiny account position manager
echo "  - Updating position-manager-tiny service..."
aws ecs update-service \
  --cluster ops-pipeline \
  --service position-manager-tiny \
  --force-new-deployment \
  --region us-west-2

echo ""
echo "=== Deployment Complete ==="
echo ""
echo "Changes deployed:"
echo "  ✓ Option profit target: +50% → +80%"
echo "  ✓ Option stop loss: -25% → -40%"
echo "  ✓ Minimum hold time: 0 min → 30 min"
echo "  ✓ Removed duplicate exit checking for options"
echo ""
echo "Expected behavior:"
echo "  - Options will hold for at least 30 minutes (unless >50% loss)"
echo "  - No exits on small premium swings (±10-20%)"
echo "  - Exits only on real moves (±40%+) or time-based triggers"
echo ""
echo "Monitor next trades to verify improved hold times."
