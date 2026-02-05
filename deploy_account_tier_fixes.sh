#!/bin/bash
# Deploy Account Tier Fixes
# Fixes:
# 1. Tiny account RUN_MODE typo (MODE → RUN_MODE)
# 2. Large account explicit ACCOUNT_TIER
# 3. Enhanced account tier logging in broker

set -e

echo "========================================="
echo "Account Tier Fixes Deployment"
echo "Date: $(date)"
echo "========================================="
echo ""

# Check AWS credentials
echo "Checking AWS credentials..."
aws sts get-caller-identity > /dev/null 2>&1 || {
    echo "❌ AWS credentials not configured or expired"
    exit 1
}
echo "✅ AWS credentials valid"
echo ""

# Build new Docker image with enhanced logging
echo "Step 1: Building Docker image with enhanced logging..."
docker build -t ops-pipeline/dispatcher:account-tier-v5 services/dispatcher
echo "✅ Docker image built"
echo ""

# Tag for ECR
echo "Step 2: Tagging image for ECR..."
docker tag ops-pipeline/dispatcher:account-tier-v5 \
  160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/dispatcher:account-tier-v5
echo "✅ Image tagged"
echo ""

# Login to ECR
echo "Step 3: Logging in to ECR..."
aws ecr get-login-password --region us-west-2 | \
  docker login --username AWS --password-stdin \
  160027201036.dkr.ecr.us-west-2.amazonaws.com
echo "✅ Logged in to ECR"
echo ""

# Push to ECR
echo "Step 4: Pushing image to ECR..."
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/dispatcher:account-tier-v5
echo "✅ Image pushed to ECR"
echo ""

# Update task definitions to use new image
echo "Step 5: Updating task definition image references..."
sed -i 's|alpaca-sdk-v4|account-tier-v5|g' deploy/dispatcher-task-definition.json
sed -i 's|alpaca-sdk-v4|account-tier-v5|g' deploy/dispatcher-task-definition-tiny-service.json
echo "✅ Task definitions updated"
echo ""

# Register large account task definition
echo "Step 6: Registering large account task definition..."
LARGE_REVISION=$(aws ecs register-task-definition \
  --cli-input-json file://deploy/dispatcher-task-definition.json \
  --region us-west-2 \
  --query 'taskDefinition.revision' \
  --output text)
echo "✅ Large account task definition registered: revision $LARGE_REVISION"
echo ""

# Register tiny account task definition
echo "Step 7: Registering tiny account task definition..."
TINY_REVISION=$(aws ecs register-task-definition \
  --cli-input-json file://deploy/dispatcher-task-definition-tiny-service.json \
  --region us-west-2 \
  --query 'taskDefinition.revision' \
  --output text)
echo "✅ Tiny account task definition registered: revision $TINY_REVISION"
echo ""

# Update large account service
echo "Step 8: Updating large account service..."
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service dispatcher-service \
  --task-definition ops-pipeline-dispatcher:$LARGE_REVISION \
  --force-new-deployment \
  --region us-west-2 > /dev/null
echo "✅ Large account service updated to revision $LARGE_REVISION"
echo ""

# Update tiny account service
echo "Step 9: Updating tiny account service..."
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service dispatcher-tiny-service \
  --task-definition ops-pipeline-dispatcher-tiny-service:$TINY_REVISION \
  --force-new-deployment \
  --region us-west-2 > /dev/null
echo "✅ Tiny account service updated to revision $TINY_REVISION"
echo ""

echo "========================================="
echo "✅ Deployment Complete!"
echo "========================================="
echo ""
echo "Next Steps:"
echo "1. Wait 2-3 minutes for services to stabilize"
echo "2. Check logs for both accounts:"
echo ""
echo "   # Large account logs"
echo "   aws logs tail /ecs/ops-pipeline/dispatcher --follow --region us-west-2"
echo ""
echo "   # Tiny account logs"
echo "   aws logs tail /ecs/ops-pipeline/dispatcher-tiny-service --follow --region us-west-2"
echo ""
echo "3. Verify account tier information is logged:"
echo "   - Account Name: large / tiny"
echo "   - Account Tier: large / tiny"
echo "   - Risk Limits displayed correctly"
echo ""
echo "4. Verify both services run in LOOP mode (every 60 seconds)"
echo ""
