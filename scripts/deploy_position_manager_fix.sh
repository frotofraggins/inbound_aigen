#!/bin/bash
# Deploy position-manager fix (remove unused import causing crash)

set -e

echo "🔧 Deploying Position Manager Fix..."
echo ""

cd /home/nflos/workplace/inbound_aigen/services/position_manager

# Force rebuild by touching the file
touch monitor.py

# Build with fresh copy
echo "1. Building Docker image..."
docker build -t position-manager:latest . 2>&1 | tail -5

# Login to ECR
echo "2. Logging into ECR..."
aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin 160027201036.dkr.ecr.us-west-2.amazonaws.com 2>&1 | grep -i "succeeded"

# Tag and push
echo "3. Pushing to ECR..."
docker tag position-manager:latest 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/position-manager:latest
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/position-manager:latest 2>&1 | tail -3

# Register new task definition
echo "4. Registering task definition revision 7..."
aws ecs register-task-definition \
  --cli-input-json file:///home/nflos/workplace/inbound_aigen/deploy/position-manager-task-definition.json \
  --region us-west-2 \
  --query 'taskDefinition.{revision:revision}' \
  --output text

# Update schedulers
echo "5. Updating schedulers to use revision 7..."
aws scheduler update-schedule \
  --name ops-pipeline-position-manager \
  --region us-west-2 \
  --flexible-time-window Mode=OFF \
  --schedule-expression "rate(1 minute)" \
  --target '{
    "Arn": "arn:aws:ecs:us-west-2:160027201036:cluster/ops-pipeline-cluster",
    "RoleArn": "arn:aws:iam::160027201036:role/ops-pipeline-eventbridge-ecs-role",
    "EcsParameters": {
      "TaskDefinitionArn": "arn:aws:ecs:us-west-2:160027201036:task-definition/position-manager:7",
      "LaunchType": "FARGATE",
      "NetworkConfiguration": {
        "awsvpcConfiguration": {
          "Subnets": ["subnet-0c182a149eeef918a"],
          "SecurityGroups": ["sg-0cd16a909f4e794ce"],
          "AssignPublicIp": "ENABLED"
        }
      }
    }
  }' > /dev/null

aws scheduler update-schedule \
  --name position-manager-1min \
  --region us-west-2 \
  --flexible-time-window Mode=OFF \
  --schedule-expression "rate(1 minute)" \
  --target '{
    "Arn": "arn:aws:ecs:us-west-2:160027201036:cluster/ops-pipeline-cluster",
    "RoleArn": "arn:aws:iam::160027201036:role/ops-pipeline-eventbridge-ecs-role",
    "EcsParameters": {
      "TaskDefinitionArn": "arn:aws:ecs:us-west-2:160027201036:task-definition/position-manager:7",
      "LaunchType": "FARGATE",
      "NetworkConfiguration": {
        "awsvpcConfiguration": {
          "Subnets": ["subnet-0c182a149eeef918a"],
          "SecurityGroups": ["sg-0cd16a909f4e794ce"],
          "AssignPublicIp": "ENABLED"
        }
      }
    }
  }' > /dev/null

echo "✅ Position manager deployed as revision 7"
echo "✅ Both schedulers updated"
echo ""
echo "⏰ Scheduler will trigger within 1 minute"
echo "📊 Monitor: aws logs tail /ecs/ops-pipeline/position-manager --region us-west-2 --follow"
