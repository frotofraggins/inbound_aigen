#!/bin/bash
# Deploy Option Exit Logic Fix - February 4, 2026
# Fixes positions closing too quickly (1-2 minutes instead of 4-24 hours)

set -e

echo "========================================"
echo "Option Exit Logic Fix Deployment"
echo "========================================"
echo ""
echo "Changes:"
echo "1. Widened option stops: -25% → -40%, +50% → +80%"
echo "2. Added 30-minute minimum hold time"
echo "3. Removed duplicate exit checking"
echo "4. Separated time-based vs price-based exits"
echo ""

# Confirm deployment
read -p "Deploy to position-manager service? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "Deployment cancelled"
    exit 1
fi

echo ""
echo "Step 1: Building new Docker image..."
cd services/position_manager
docker build -t ops-pipeline-position-manager:option-fix-2026-02-04 .

echo ""
echo "Step 2: Tagging image for ECR..."
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION="us-west-2"
ECR_REPO="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/ops-pipeline/position-manager"

docker tag ops-pipeline-position-manager:option-fix-2026-02-04 ${ECR_REPO}:option-fix-2026-02-04
docker tag ops-pipeline-position-manager:option-fix-2026-02-04 ${ECR_REPO}:latest

echo ""
echo "Step 3: Pushing to ECR..."
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_REPO}
docker push ${ECR_REPO}:option-fix-2026-02-04
docker push ${ECR_REPO}:latest

echo ""
echo "Step 4: Updating ECS task definition..."
cd ../../deploy

# Get current task definition
CURRENT_TASK_DEF=$(aws ecs describe-task-definition \
    --task-definition position-manager-service \
    --region ${AWS_REGION} \
    --query 'taskDefinition' \
    --output json)

# Create new task definition with updated image
NEW_TASK_DEF=$(echo $CURRENT_TASK_DEF | jq --arg IMAGE "${ECR_REPO}:option-fix-2026-02-04" \
    '.containerDefinitions[0].image = $IMAGE | 
    del(.taskDefinitionArn, .revision, .status, .requiresAttributes, .compatibilities, .registeredAt, .registeredBy)')

# Register new task definition
NEW_REVISION=$(echo $NEW_TASK_DEF | aws ecs register-task-definition \
    --cli-input-json file:///dev/stdin \
    --region ${AWS_REGION} \
    --query 'taskDefinition.revision' \
    --output text)

echo "Created task definition revision: $NEW_REVISION"

echo ""
echo "Step 5: Updating ECS service..."
aws ecs update-service \
    --cluster ops-pipeline-cluster \
    --service position-manager-service \
    --task-definition position-manager-service:${NEW_REVISION} \
    --force-new-deployment \
    --region ${AWS_REGION}

echo ""
echo "========================================"
echo "✓ Deployment Complete!"
echo "========================================"
echo ""
echo "Next Steps:"
echo "1. Monitor CloudWatch logs for position-manager"
echo "2. Check that positions hold >30 minutes"
echo "3. Verify exits only trigger on real moves"
echo "4. Query position_history after 24 hours"
echo ""
echo "Monitor deployment:"
echo "  aws ecs describe-services --cluster ops-pipeline-cluster --services position-manager-service --region us-west-2"
echo ""
echo "Watch logs:"
echo "  aws logs tail /ecs/ops-pipeline/position-manager --follow --region us-west-2"
echo ""
