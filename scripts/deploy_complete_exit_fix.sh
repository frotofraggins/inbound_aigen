#!/bin/bash
# Complete Exit Fix Deployment - February 4, 2026
# Fixes TWO issues:
# 1. Position manager checking too slowly (5 min → 1 min)
# 2. Alpaca bracket orders closing positions before our system can monitor

set -e

echo "========================================"
echo "Complete Exit Fix Deployment"
echo "========================================"
echo ""
echo "Fixes Being Deployed:"
echo "1. Position Manager:"
echo "   - Check interval: 5 min → 1 min"
echo "   - Exit logic: -25%/+50% → -40%/+80%"
echo "   - Min hold time: 30 minutes"
echo "   - Duplicate check removal"
echo ""
echo "2. Dispatcher:"
echo "   - Disabled Alpaca bracket orders"
echo "   - Our system now handles all exits"
echo ""

read -p "Deploy BOTH services? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "Deployment cancelled"
    exit 1
fi

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION="us-west-2"

echo ""
echo "========== DEPLOYING POSITION MANAGER =========="
echo ""
echo "Step 1: Building position-manager image..."
cd services/position_manager
docker build -t position-manager:complete-fix .

echo ""
echo "Step 2: Pushing to ECR..."
ECR_PM="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/ops-pipeline/position-manager"
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_PM}
docker tag position-manager:complete-fix ${ECR_PM}:complete-fix-2026-02-04
docker tag position-manager:complete-fix ${ECR_PM}:latest
docker push ${ECR_PM}:complete-fix-2026-02-04
docker push ${ECR_PM}:latest

echo ""
echo "Step 3: Updating position-manager service..."
aws ecs update-service \
    --cluster ops-pipeline-cluster \
    --service position-manager-service \
    --force-new-deployment \
    --region ${AWS_REGION}

echo "✓ Position manager deployment triggered"

echo ""
echo "========== DEPLOYING DISPATCHER =========="
echo ""
echo "Step 4: Building dispatcher image..."
cd ../dispatcher
docker build -t dispatcher:no-brackets .

echo ""
echo "Step 5: Pushing to ECR..."
ECR_DISP="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/ops-pipeline/dispatcher"
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_DISP}
docker tag dispatcher:no-brackets ${ECR_DISP}:no-brackets-2026-02-04
docker tag dispatcher:no-brackets ${ECR_DISP}:latest
docker push ${ECR_DISP}:no-brackets-2026-02-04
docker push ${ECR_DISP}:latest

echo ""
echo "Step 6: Updating dispatcher service..."
aws ecs update-service \
    --cluster ops-pipeline-cluster \
    --service dispatcher-service \
    --force-new-deployment \
    --region ${AWS_REGION}

echo "✓ Dispatcher deployment triggered"

echo ""
echo "========== DEPLOYING TINY DISPATCHER =========="
echo ""
echo "Step 7: Updating dispatcher-tiny service (same image)..."
aws ecs update-service \
    --cluster ops-pipeline-cluster \
    --service dispatcher-tiny-service \
    --force-new-deployment \
    --region ${AWS_REGION}

echo "✓ Tiny dispatcher deployment triggered"

echo ""
echo "========================================"
echo "✓ All Deployments Complete!"
echo "========================================"
echo ""
echo "Next Steps:"
echo "1. Wait 2-3 minutes for services to stabilize"
echo "2. Monitor next positions that open"
echo "3. Verify they hold >= 30 minutes"
echo "4. Check position manager logs for 'Too early to exit' messages"
echo ""
echo "Monitor deployments:"
echo "  aws ecs describe-services --cluster ops-pipeline-cluster --services position-manager-service dispatcher-service --region us-west-2 --query 'services[].deployments[0].rolloutState'"
echo ""
echo "Watch position manager logs:"
echo "  aws logs tail /ecs/ops-pipeline/position-manager --follow --region us-west-2"
echo ""
echo "Check positions:"
echo "  python3 scripts/monitor_exit_fix.py"
echo ""
