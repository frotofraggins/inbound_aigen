#!/bin/bash
# Deploy separate account configs for large and tiny accounts

set -e

REGION="us-west-2"
ACCOUNT_ID="160027201036"
ECR_REPO="ops-pipeline/dispatcher"
IMAGE_TAG="separate-configs"

echo "=========================================="
echo "Deploying Separate Account Configs"
echo "=========================================="
echo ""

# Step 1: Create SSM parameters
echo "Step 1: Creating SSM parameters..."
./create_separate_account_configs.sh
echo ""

# Step 2: Build Docker image
echo "Step 2: Building Docker image..."
cd services/dispatcher
docker build -t ${ECR_REPO}:${IMAGE_TAG} .
cd ../..
echo "✓ Docker image built"
echo ""

# Step 3: Push to ECR
echo "Step 3: Pushing to ECR..."
aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com
docker tag ${ECR_REPO}:${IMAGE_TAG} ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}
docker push ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}
echo "✓ Image pushed to ECR"
echo ""

# Step 4: Register task definitions
echo "Step 4: Registering task definitions..."

# Large account
LARGE_TASK_DEF=$(cat deploy/dispatcher-task-definition.json | \
  jq --arg IMAGE "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}" \
  '.containerDefinitions[0].image = $IMAGE')

LARGE_REVISION=$(aws ecs register-task-definition \
  --cli-input-json "$LARGE_TASK_DEF" \
  --region ${REGION} \
  --query 'taskDefinition.revision' \
  --output text)

echo "✓ Large account task definition registered: revision ${LARGE_REVISION}"

# Tiny account
TINY_TASK_DEF=$(cat deploy/dispatcher-task-definition-tiny-service.json | \
  jq --arg IMAGE "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}" \
  '.containerDefinitions[0].image = $IMAGE')

TINY_REVISION=$(aws ecs register-task-definition \
  --cli-input-json "$TINY_TASK_DEF" \
  --region ${REGION} \
  --query 'taskDefinition.revision' \
  --output text)

echo "✓ Tiny account task definition registered: revision ${TINY_REVISION}"
echo ""

# Step 5: Update services
echo "Step 5: Updating ECS services..."

# Large account
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service dispatcher-service \
  --task-definition ops-pipeline-dispatcher:${LARGE_REVISION} \
  --region ${REGION} \
  --force-new-deployment \
  > /dev/null

echo "✓ Large account service updated to revision ${LARGE_REVISION}"

# Tiny account
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service dispatcher-tiny-service \
  --task-definition ops-pipeline-dispatcher-tiny-service:${TINY_REVISION} \
  --region ${REGION} \
  --force-new-deployment \
  > /dev/null

echo "✓ Tiny account service updated to revision ${TINY_REVISION}"
echo ""

echo "=========================================="
echo "✅ Deployment Complete!"
echo "=========================================="
echo ""
echo "Summary:"
echo "  - SSM configs created: /ops-pipeline/dispatcher_config_large and _tiny"
echo "  - Docker image: ${IMAGE_TAG}"
echo "  - Large account: revision ${LARGE_REVISION}"
echo "  - Tiny account: revision ${TINY_REVISION}"
echo ""
echo "Large Account Limits:"
echo "  - Max exposure: \$10,000"
echo "  - Max positions: 5"
echo "  - Max contracts: 10"
echo "  - Max daily loss: \$500"
echo ""
echo "Tiny Account Limits:"
echo "  - Max exposure: \$1,500"
echo "  - Max positions: 2"
echo "  - Max contracts: 2"
echo "  - Max daily loss: \$100"
echo ""
echo "Monitor logs:"
echo "  aws logs tail /ecs/ops-pipeline/dispatcher --follow"
