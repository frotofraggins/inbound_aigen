#!/bin/bash
# Deploy Position Reconciliation Service
# Author: AI System Owner
# Date: 2026-02-07

set -e

REGION="us-west-2"
ACCOUNT_ID="160027201036"
ECR_REPO="ops-pipeline/position-reconciler"
SERVICE_NAME="position-reconciler"
CLUSTER_NAME="ops-pipeline-cluster"

echo "========================================"
echo "Position Reconciliation Service Deploy"
echo "========================================"

# Step 1: Create CloudWatch Log Group
echo "Step 1: Creating CloudWatch log group..."
aws logs create-log-group --log-group-name /ecs/ops-pipeline/position-reconciler --region $REGION 2>/dev/null || echo "Log group already exists"

# Step 2: Create ECR repository
echo "Step 2: Creating ECR repository..."
aws ecr create-repository --repository-name $ECR_REPO --region $REGION 2>/dev/null || echo "Repository already exists"

# Step 3: Build Docker image
echo "Step 3: Building Docker image..."
cd services/position_reconciler
docker build --no-cache -t $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$ECR_REPO:latest .

# Step 4: Login to ECR
echo "Step 4: Logging into ECR..."
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com

# Step 5: Push image
echo "Step 5: Pushing image to ECR..."
docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$ECR_REPO:latest

# Step 6: Register task definition
echo "Step 6: Registering ECS task definition..."
cd ../../
aws ecs register-task-definition --cli-input-json file://deploy/position-reconciler-task-definition.json --region $REGION

# Step 7: Create EventBridge schedule (run every 5 minutes)
echo "Step 7: Creating EventBridge schedule..."

# Get latest task definition revision
TASK_DEF_ARN=$(aws ecs describe-task-definition --task-definition ops-pipeline-position-reconciler --region $REGION --query 'taskDefinition.taskDefinitionArn' --output text)

# Create schedule
aws scheduler create-schedule \
  --name ops-pipeline-position-reconciler-5m \
  --schedule-expression "rate(5 minutes)" \
  --target '{
    "Arn": "arn:aws:ecs:'$REGION':'$ACCOUNT_ID':cluster/'$CLUSTER_NAME'",
    "RoleArn": "arn:aws:iam::'$ACCOUNT_ID':role/AmazonEventBridgeSchedulerECSRole",
    "EcsParameters": {
      "TaskDefinitionArn": "'$TASK_DEF_ARN'",
      "LaunchType": "FARGATE",
      "NetworkConfiguration": {
        "awsvpcConfiguration": {
          "Subnets": ["subnet-0c182a149eeef918a"],
          "SecurityGroups": ["sg-0cd16a909f4e794ce"],
          "AssignPublicIp": "ENABLED"
        }
      }
    },
    "RetryPolicy": {
      "MaximumRetryAttempts": 2
    }
  }' \
  --flexible-time-window '{"Mode": "OFF"}' \
  --region $REGION 2>/dev/null || echo "Schedule already exists"

echo ""
echo "========================================"
echo "Deployment Complete!"
echo "========================================"
echo ""
echo "Service will run every 5 minutes to reconcile positions."
echo ""
echo "To test manually:"
echo "  aws ecs run-task --cluster $CLUSTER_NAME --task-definition ops-pipeline-position-reconciler --launch-type FARGATE --network-configuration 'awsvpcConfiguration={subnets=[subnet-0c182a149eeef918a],securityGroups=[sg-0cd16a909f4e794ce],assignPublicIp=ENABLED}' --region $REGION"
echo ""
echo "To view logs:"
echo "  aws logs tail /ecs/ops-pipeline/position-reconciler --region $REGION --follow"
echo ""
echo "To check schedule:"
echo "  aws scheduler get-schedule --name ops-pipeline-position-reconciler-5m --region $REGION"
echo ""
