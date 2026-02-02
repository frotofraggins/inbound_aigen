#!/bin/bash
# Fix Missing EventBridge Schedulers
# Date: 2026-01-26
# Issue: Telemetry and feature-computer schedulers were never created/deleted

set -e

REGION="us-west-2"
CLUSTER="ops-pipeline-cluster"
ROLE_ARN="arn:aws:iam::160027201036:role/ops-pipeline-eventbridge-ecs-role"
ACCOUNT_ID="160027201036"
SUBNET="subnet-0c182a149eeef918a"
SECURITY_GROUP="sg-0cd16a909f4e794ce"

echo "=================================="
echo "Creating Missing Schedulers"
echo "=================================="
echo ""

# 1. Create Telemetry Ingestor Scheduler (every 1 minute)
echo "1. Creating telemetry-ingestor-1m scheduler..."
aws scheduler create-schedule \
  --name ops-pipeline-telemetry-ingestor-1m \
  --schedule-expression "rate(1 minute)" \
  --flexible-time-window Mode=OFF \
  --target "{
    \"Arn\": \"arn:aws:ecs:${REGION}:${ACCOUNT_ID}:cluster/${CLUSTER}\",
    \"RoleArn\": \"${ROLE_ARN}\",
    \"EcsParameters\": {
      \"TaskDefinitionArn\": \"arn:aws:ecs:${REGION}:${ACCOUNT_ID}:task-definition/ops-pipeline-telemetry-1m\",
      \"LaunchType\": \"FARGATE\",
      \"NetworkConfiguration\": {
        \"awsvpcConfiguration\": {
          \"Subnets\": [\"${SUBNET}\"],
          \"SecurityGroups\": [\"${SECURITY_GROUP}\"],
          \"AssignPublicIp\": \"ENABLED\"
        }
      }
    },
    \"RetryPolicy\": {
      \"MaximumRetryAttempts\": 0
    }
  }" \
  --region ${REGION}

echo "✓ Telemetry scheduler created"
echo ""

# 2. Create Feature Computer Scheduler (every 1 minute)
echo "2. Creating feature-computer-1m scheduler..."
aws scheduler create-schedule \
  --name ops-pipeline-feature-computer-1m \
  --schedule-expression "rate(1 minute)" \
  --flexible-time-window Mode=OFF \
  --target "{
    \"Arn\": \"arn:aws:ecs:${REGION}:${ACCOUNT_ID}:cluster/${CLUSTER}\",
    \"RoleArn\": \"${ROLE_ARN}\",
    \"EcsParameters\": {
      \"TaskDefinitionArn\": \"arn:aws:ecs:${REGION}:${ACCOUNT_ID}:task-definition/ops-pipeline-feature-computer-1m\",
      \"LaunchType\": \"FARGATE\",
      \"NetworkConfiguration\": {
        \"awsvpcConfiguration\": {
          \"Subnets\": [\"${SUBNET}\"],
          \"SecurityGroups\": [\"${SECURITY_GROUP}\"],
          \"AssignPublicIp\": \"ENABLED\"
        }
      }
    },
    \"RetryPolicy\": {
      \"MaximumRetryAttempts\": 0
    }
  }" \
  --region ${REGION}

echo "✓ Feature computer scheduler created"
echo ""

# 3. Create Classifier Scheduler (every 5 minutes)
echo "3. Creating classifier scheduler..."
aws scheduler create-schedule \
  --name ops-pipeline-classifier \
  --schedule-expression "rate(5 minutes)" \
  --flexible-time-window Mode=OFF \
  --target "{
    \"Arn\": \"arn:aws:ecs:${REGION}:${ACCOUNT_ID}:cluster/${CLUSTER}\",
    \"RoleArn\": \"${ROLE_ARN}\",
    \"EcsParameters\": {
      \"TaskDefinitionArn\": \"arn:aws:ecs:${REGION}:${ACCOUNT_ID}:task-definition/ops-pipeline-classifier-worker\",
      \"LaunchType\": \"FARGATE\",
      \"NetworkConfiguration\": {
        \"awsvpcConfiguration\": {
          \"Subnets\": [\"${SUBNET}\"],
          \"SecurityGroups\": [\"${SECURITY_GROUP}\"],
          \"AssignPublicIp\": \"ENABLED\"
        }
      }
    },
    \"RetryPolicy\": {
      \"MaximumRetryAttempts\": 0
    }
  }" \
  --region ${REGION}

echo "✓ Classifier scheduler created"
echo ""

# 4. Create RSS Ingest Scheduler (every 5 minutes)  
echo "4. Creating rss-ingest scheduler..."
aws scheduler create-schedule \
  --name ops-pipeline-rss-ingest \
  --schedule-expression "rate(5 minutes)" \
  --flexible-time-window Mode=OFF \
  --target "{
    \"Arn\": \"arn:aws:ecs:${REGION}:${ACCOUNT_ID}:cluster/${CLUSTER}\",
    \"RoleArn\": \"${ROLE_ARN}\",
    \"EcsParameters\": {
      \"TaskDefinitionArn\": \"arn:aws:ecs:${REGION}:${ACCOUNT_ID}:task-definition/ops-pipeline-rss-ingest\",
      \"LaunchType\": \"FARGATE\",
      \"NetworkConfiguration\": {
        \"awsvpcConfiguration\": {
          \"Subnets\": [\"${SUBNET}\"],
          \"SecurityGroups\": [\"${SECURITY_GROUP}\"],
          \"AssignPublicIp\": \"ENABLED\"
        }
      }
    },
    \"RetryPolicy\": {
      \"MaximumRetryAttempts\": 0
    }
  }" \
  --region ${REGION}

echo "✓ RSS ingest scheduler created"
echo ""

echo "=================================="
echo "All Schedulers Created Successfully"
echo "=================================="
echo ""
echo "Verifying schedulers..."
aws scheduler list-schedules --region ${REGION} --query 'Schedules[].{Name:Name,State:State}' --output table

echo ""
echo "Pipeline will start running within 1 minute!"
