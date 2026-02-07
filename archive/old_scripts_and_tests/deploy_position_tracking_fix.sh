#!/bin/bash
# Deploy Position Tracking Fix - CRITICAL
# Fixes dispatcher not filtering positions by account_name

set -e

echo "========================================="
echo "CRITICAL: Position Tracking Fix"
echo "Date: $(date)"
echo "========================================="
echo ""

echo "⚠️  CRITICAL BUG FIX:"
echo "   Dispatcher was not filtering positions by account"
echo "   Result: Opened 11 positions (limit: 5)"
echo "   Result: $98,630 exposure (limit: $10,000)"
echo ""

# Check AWS credentials
echo "Checking AWS credentials..."
aws sts get-caller-identity > /dev/null 2>&1 || {
    echo "❌ AWS credentials not configured or expired"
    exit 1
}
echo "✅ AWS credentials valid"
echo ""

# Build new Docker image
echo "Step 1: Building Docker image with position tracking fix..."
docker build -t ops-pipeline/dispatcher:position-tracking-fix services/dispatcher
echo "✅ Docker image built"
echo ""

# Tag for ECR
echo "Step 2: Tagging image for ECR..."
docker tag ops-pipeline/dispatcher:position-tracking-fix \
  160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/dispatcher:position-tracking-fix
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
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/dispatcher:position-tracking-fix
echo "✅ Image pushed to ECR"
echo ""

# Update task definitions
echo "Step 5: Updating task definition image references..."
cp deploy/dispatcher-task-definition.json deploy/dispatcher-task-definition.json.bak
cp deploy/dispatcher-task-definition-tiny-service.json deploy/dispatcher-task-definition-tiny-service.json.bak

sed -i 's|"image": ".*dispatcher:.*"|"image": "160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/dispatcher:position-tracking-fix"|g' deploy/dispatcher-task-definition.json
sed -i 's|"image": ".*dispatcher:.*"|"image": "160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/dispatcher:position-tracking-fix"|g' deploy/dispatcher-task-definition-tiny-service.json
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

# Restore backups
mv deploy/dispatcher-task-definition.json.bak deploy/dispatcher-task-definition.json
mv deploy/dispatcher-task-definition-tiny-service.json.bak deploy/dispatcher-task-definition-tiny-service.json

echo "========================================="
echo "✅ CRITICAL FIX DEPLOYED!"
echo "========================================="
echo ""
echo "What Was Fixed:"
echo "  ✅ get_account_state() now filters by account_name"
echo "  ✅ Dispatcher passes account_name to get_account_state()"
echo "  ✅ Position counts are now account-specific"
echo "  ✅ Exposure limits are now account-specific"
echo ""
echo "Expected Behavior:"
echo "  ✅ Large account: Max 5 positions, $10,000 exposure"
echo "  ✅ Tiny account: Max 1 position, ~$2,000 exposure"
echo "  ✅ Risk gates will now block when limits reached"
echo ""
echo "Verification:"
echo "  1. Wait 2-3 minutes for services to stabilize"
echo "  2. Check logs for correct position counts:"
echo ""
echo "     aws logs tail /ecs/ops-pipeline/dispatcher --follow --region us-west-2"
echo ""
echo "  3. Look for:"
echo "     \"max_positions\": \"Positions X/5\"  (should show actual count)"
echo "     \"max_exposure\": \"Exposure $X/$10000\"  (should show actual exposure)"
echo ""
echo "  4. Verify gates block when limits reached"
echo ""
