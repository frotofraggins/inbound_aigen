#!/bin/bash
# Deploy Phase 3 Complete: Migrations + Trade Stream
# Fixes all three production foot-guns identified

set -e

echo "=========================================="
echo "Phase 3 Complete Deployment"
echo "=========================================="
echo ""
echo "This script will:"
echo "1. Rebuild and redeploy db-migration Lambda (with new migrations)"
echo "2. Apply Phase 3 WebSocket idempotency migration"
echo "3. Apply constraints migration (re-add missing constraints)"
echo "4. Rebuild and redeploy trade-stream service"
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

# Step 1: Rebuild and redeploy db-migration Lambda
echo ""
echo "=========================================="
echo "Step 1: Rebuild db-migration Lambda"
echo "=========================================="
cd services/db_migration_lambda

echo "Creating deployment package..."
rm -f migration_lambda.zip
cd package
zip -r ../migration_lambda.zip . > /dev/null
cd ..
zip -g migration_lambda.zip lambda_function.py

echo "Deploying to Lambda..."
aws lambda update-function-code \
    --function-name ops-pipeline-db-migration \
    --zip-file fileb://migration_lambda.zip \
    --region us-west-2

echo "Waiting for Lambda update to complete..."
aws lambda wait function-updated \
    --function-name ops-pipeline-db-migration \
    --region us-west-2

echo "✅ Lambda updated successfully"
cd ../..

# Step 2: Apply Phase 3 migration
echo ""
echo "=========================================="
echo "Step 2: Apply WebSocket Idempotency Migration"
echo "=========================================="
python3 apply_phase3_migration.py
if [ $? -ne 0 ]; then
    echo "❌ Phase 3 migration failed!"
    exit 1
fi

# Step 3: Apply constraints migration
echo ""
echo "=========================================="
echo "Step 3: Apply Constraints Migration"
echo "=========================================="
python3 apply_constraints_migration.py
if [ $? -ne 0 ]; then
    echo "❌ Constraints migration failed!"
    exit 1
fi

# Step 4: Rebuild and redeploy trade-stream
echo ""
echo "=========================================="
echo "Step 4: Rebuild trade-stream Service"
echo "=========================================="
cd services/trade_stream

echo "Building Docker image..."
docker build -t trade-stream:phase3 .

echo "Tagging for ECR..."
docker tag trade-stream:phase3 \
    160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/trade-stream:latest

echo "Logging into ECR..."
aws ecr get-login-password --region us-west-2 | \
    docker login --username AWS --password-stdin \
    160027201036.dkr.ecr.us-west-2.amazonaws.com

echo "Pushing to ECR..."
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/trade-stream:latest

echo "Forcing ECS service update..."
aws ecs update-service \
    --cluster ops-pipeline \
    --service trade-stream \
    --force-new-deployment \
    --region us-west-2 > /dev/null

echo "✅ Trade-stream service update initiated"
cd ../..

# Final verification
echo ""
echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
echo ""
echo "✅ All migrations applied successfully"
echo "✅ Lambda updated with new migrations"
echo "✅ Trade-stream service redeployed"
echo ""
echo "Next steps:"
echo "1. Monitor trade-stream logs:"
echo "   aws logs tail /ecs/trade-stream --follow --region us-west-2"
echo ""
echo "2. Verify no duplicate positions:"
echo "   python3 -c \"import boto3, json; ..."
echo ""
echo "3. Check for WebSocket event deduplication in logs"
echo ""
echo "Phase 3 deployment complete! 🎉"
