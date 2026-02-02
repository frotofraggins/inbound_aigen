#!/bin/bash
# Enable Alpaca Paper Trading
# Date: 2026-01-26
# Switches from simulation to real Alpaca paper trades

set -e

REGION="us-west-2"
ACCOUNT_ID="160027201036"
ECR_REPO="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/ops-pipeline/dispatcher"

echo "=================================="
echo "Enabling Alpaca Paper Trading"
echo "=================================="
echo ""

# 1. Build new dispatcher image
echo "1. Building dispatcher image..."
cd services/dispatcher
docker build -t ops-pipeline-dispatcher:paper .
cd ../..
echo "   ✓ Image built"

# 2. Tag for ECR
echo "2. Tagging image..."
docker tag ops-pipeline-dispatcher:paper ${ECR_REPO}:paper
docker tag ops-pipeline-dispatcher:paper ${ECR_REPO}:latest
echo "   ✓ Tagged"

# 3. Login to ECR
echo "3. Logging into ECR..."
aws ecr get-login-password --region ${REGION} | \
  docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com
echo "   ✓ Logged in"

# 4. Push to ECR
echo "4. Pushing to ECR..."
docker push ${ECR_REPO}:paper
docker push ${ECR_REPO}:latest
echo "   ✓ Images pushed"

# 5. Register new task definition  
echo "5. Registering new task definition..."
NEW_REV=$(aws ecs register-task-definition \
  --cli-input-json file://deploy/dispatcher-task-definition.json \
  --region ${REGION} \
  --query 'taskDefinition.revision' \
  --output text)
echo "   ✓ New revision: ${NEW_REV}"

echo ""
echo "=================================="
echo "Paper Trading Enabled!"
echo "=================================="
echo ""
echo "Task Definition: ops-pipeline-dispatcher:${NEW_REV}"
echo "Mode: ALPACA_PAPER"
echo "Endpoint: https://paper-api.alpaca.markets"
echo ""
echo "⚠️  IMPORTANT:"
echo "   - Paper account starts with $100,000 virtual cash"
echo "   - Trades execute on real market data"
echo "   - No real money at risk"
echo "   - Can reset account anytime via Alpaca dashboard"
echo ""
echo "Monitor trades at:"
echo "   https://app.alpaca.markets/paper/dashboard/overview"
echo ""
echo "Next dispatcher run will use paper trading!"
