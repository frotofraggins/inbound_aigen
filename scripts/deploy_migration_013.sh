#!/bin/bash
# Deploy Migration 013 via ECS db-migrator task
# Adds trailing stop columns: peak_price, trailing_stop_price, etc.

set -e

echo "=================================================================="
echo "DEPLOYING MIGRATION 013: Trailing Stops Infrastructure"
echo "=================================================================="
echo ""

# Configuration
CLUSTER="ops-pipeline-cluster"
SUBNET="subnet-0c182a149eeef918a"
SECURITY_GROUP="sg-0cd16a909f4e794ce"

echo "Step 1: Registering task definition for migration 013..."
TASK_DEF_ARN=$(aws ecs register-task-definition \
    --cli-input-json file://deploy/db-migrator-task-definition-013.json \
    --query 'taskDefinition.taskDefinitionArn' \
    --output text)

echo "  Registered: $TASK_DEF_ARN"
echo ""

echo "Step 2: Running migration task..."
TASK_ARN=$(aws ecs run-task \
    --cluster $CLUSTER \
    --task-definition $TASK_DEF_ARN \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$SECURITY_GROUP],assignPublicIp=ENABLED}" \
    --region us-west-2 \
    --query 'tasks[0].taskArn' \
    --output text)

echo "  Task started: $TASK_ARN"
echo ""

# Extract task ID
TASK_ID=$(echo $TASK_ARN | grep -o '[^/]*$')
echo "  Task ID: $TASK_ID"
echo ""

echo "Step 3: Waiting for task to complete..."
echo "  (This typically takes 30-60 seconds)"
echo ""

# Wait for task to complete
aws ecs wait tasks-stopped \
    --cluster $CLUSTER \
    --tasks $TASK_ARN \
    --region us-west-2

echo "Step 4: Checking task exit status..."
EXIT_CODE=$(aws ecs describe-tasks \
    --cluster $CLUSTER \
    --tasks $TASK_ARN \
    --region us-west-2 \
    --query 'tasks[0].containers[0].exitCode' \
    --output text)

echo "  Exit code: $EXIT_CODE"
echo ""

if [ "$EXIT_CODE" = "0" ]; then
    echo "✅ Migration 013 applied successfully!"
    echo ""
    echo "Columns added:"
    echo "  - peak_price (for trailing stop tracking)"
    echo "  - trailing_stop_price (calculated stop level)"
    echo "  - entry_underlying_price (for future use)"
    echo "  - original_quantity (for partial exits)"
    echo ""
    echo "Trailing stops are now ACTIVE in position-manager service!"
    echo ""
    echo "=================================================================="
    echo "MIGRATION 013 DEPLOYMENT COMPLETE"
    echo "=================================================================="
    exit 0
else
    echo "❌ Migration failed with exit code: $EXIT_CODE"
    echo ""
    echo "Fetching logs..."
    aws logs tail /ecs/ops-pipeline/db-migrator \
        --since 5m \
        --region us-west-2 \
        --format short
    echo ""
    echo "=================================================================="
    echo "MIGRATION 013 DEPLOYMENT FAILED"
    echo "=================================================================="
    exit 1
fi
