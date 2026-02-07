#!/bin/bash
set -e

echo "=================================="
echo "Position Manager Account Filter Fix"
echo "Deployment Script"
echo "=================================="
echo ""

# Configuration
REGION="us-west-2"
ECR_REPO="891377316085.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline"
IMAGE_TAG="position-manager-account-filter"
CLUSTER="ops-pipeline-cluster"
SERVICE="position-manager-service"
TASK_DEF="position-manager-service"

echo "Step 1: Building Docker image..."
docker build -t position-manager:account-filter services/position_manager/
echo "✓ Docker image built"
echo ""

echo "Step 2: Tagging for ECR..."
docker tag position-manager:account-filter ${ECR_REPO}:${IMAGE_TAG}
echo "✓ Image tagged"
echo ""

echo "Step 3: Logging into ECR..."
aws ecr get-login-password --region ${REGION} | \
  docker login --username AWS --password-stdin ${ECR_REPO}
echo "✓ Logged into ECR"
echo ""

echo "Step 4: Pushing to ECR..."
docker push ${ECR_REPO}:${IMAGE_TAG}
echo "✓ Image pushed to ECR"
echo ""

echo "Step 5: Updating task definition..."
# Read current task definition
TASK_DEF_JSON=$(aws ecs describe-task-definition \
  --task-definition ${TASK_DEF} \
  --region ${REGION} \
  --query 'taskDefinition')

# Extract relevant fields and update image
NEW_TASK_DEF=$(echo $TASK_DEF_JSON | jq --arg IMAGE "${ECR_REPO}:${IMAGE_TAG}" '
  {
    family: .family,
    taskRoleArn: .taskRoleArn,
    executionRoleArn: .executionRoleArn,
    networkMode: .networkMode,
    containerDefinitions: [
      .containerDefinitions[0] | 
      .image = $IMAGE |
      .environment += [{name: "ACCOUNT_NAME", value: "large"}]
    ],
    requiresCompatibilities: .requiresCompatibilities,
    cpu: .cpu,
    memory: .memory
  }
')

# Register new task definition
NEW_REVISION=$(aws ecs register-task-definition \
  --region ${REGION} \
  --cli-input-json "$NEW_TASK_DEF" \
  --query 'taskDefinition.revision' \
  --output text)

echo "✓ Registered task definition revision: ${NEW_REVISION}"
echo ""

echo "Step 6: Updating ECS service..."
aws ecs update-service \
  --cluster ${CLUSTER} \
  --service ${SERVICE} \
  --task-definition ${TASK_DEF}:${NEW_REVISION} \
  --desired-count 1 \
  --region ${REGION} \
  --force-new-deployment \
  --query 'service.{Status:status,Running:runningCount,Desired:desiredCount}' \
  --output table

echo "✓ Service updated"
echo ""

echo "Step 7: Waiting for service to stabilize..."
aws ecs wait services-stable \
  --cluster ${CLUSTER} \
  --services ${SERVICE} \
  --region ${REGION}

echo "✓ Service is stable"
echo ""

echo "=================================="
echo "Deployment Complete!"
echo "=================================="
echo ""
echo "Next steps:"
echo "1. Monitor logs: aws logs tail /ecs/position-manager-service --follow --region us-west-2"
echo "2. Look for: 'Managing positions for account: large'"
echo "3. Verify no duplicate position creation for 30 minutes"
echo "4. Run sync script: python3 scripts/sync_positions_with_alpaca.py"
echo ""
