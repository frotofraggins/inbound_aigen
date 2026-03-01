#!/bin/bash
# Deploy Dispatcher with timezone fix for bar_freshness gate

set -e

echo "=========================================="
echo "DEPLOYING DISPATCHER FIX"
echo "Fix: Timezone-aware datetime in bar queries"
echo "=========================================="

REGION="us-west-2"
CLUSTER="ops-pipeline-cluster"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo ""
echo "Building dispatcher image..."
cd /home/nflos/workplace/inbound_aigen/services/dispatcher

docker build --no-cache -t ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/ops-pipeline/dispatcher:latest .

echo ""
echo "Pushing to ECR..."
aws ecr get-login-password --region ${REGION} | \
  docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com

docker push ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/ops-pipeline/dispatcher:latest

echo ""
echo "Deploying large account dispatcher..."
aws ecs update-service \
  --cluster ${CLUSTER} \
  --service dispatcher-service \
  --force-new-deployment \
  --region ${REGION}

echo ""
echo "✅ DEPLOYMENT COMPLETE"
echo ""
echo "Dispatcher will restart with timezone fix in ~2 minutes"
echo ""
echo "To verify:"
echo "  aws logs tail /ecs/ops-pipeline/dispatcher --follow --region ${REGION}"
echo ""
echo "Look for:"
echo "  - Signals being claimed (count > 0)"
echo "  - Bar data found"
echo "  - Trades executing"
