#!/bin/bash
# Deploy Migration 011 via ECS db-migrator task
# This is the reliable approach used for previous migrations

set -e

echo "=================================================================="
echo "DEPLOYING MIGRATION 011: Learning Infrastructure"
echo "=================================================================="
echo ""

# Configuration
CLUSTER="ops-pipeline-cluster"
TASK_FAMILY="ops-pipeline-db-migrator"
SUBNET="subnet-0c182a149eeef918a"
SECURITY_GROUP="sg-0cd16a909f4e794ce"

echo "Step 1: Checking latest task definition..."
TASK_DEF_ARN=$(aws ecs describe-task-definition \
    --task-definition $TASK_FAMILY \
    --query 'taskDefinition.taskDefinitionArn' \
    --output text)

echo "  Using task definition: $TASK_DEF_ARN"
echo ""

echo "Step 2: Running migration task..."
TASK_ARN=$(aws ecs run-task \
    --cluster $CLUSTER \
    --task-definition $TASK_DEF_ARN \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$SECURITY_GROUP],assignPublicIp=ENABLED}" \
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
    --tasks $TASK_ARN

echo "Step 4: Checking task exit status..."
EXIT_CODE=$(aws ecs describe-tasks \
    --cluster $CLUSTER \
    --tasks $TASK_ARN \
    --query 'tasks[0].containers[0].exitCode' \
    --output text)

echo "  Exit code: $EXIT_CODE"
echo ""

if [ "$EXIT_CODE" = "0" ]; then
    echo "✅ Migration 011 applied successfully!"
    echo ""
    echo "Step 5: Verifying schema changes..."
    python3 scripts/test_phase16_columns.py
    echo ""
    echo "=================================================================="
    echo "MIGRATION 011 DEPLOYMENT COMPLETE"
    echo "=================================================================="
    exit 0
else
    echo "❌ Migration failed with exit code: $EXIT_CODE"
    echo ""
    echo "Fetching logs..."
    aws logs tail /ecs/ops-pipeline-db-migrator \
        --since 5m \
        --format short \
        --follow=false
    echo ""
    echo "=================================================================="
    echo "MIGRATION 011 DEPLOYMENT FAILED"
    echo "=================================================================="
    exit 1
fi
