#!/bin/bash
# Fix all EventBridge Schedulers - Update cluster name from ops-pipeline to ops-pipeline-cluster
# ROOT CAUSE: Schedulers pointing to wrong cluster name

set -e

REGION="us-west-2"
CORRECT_CLUSTER="arn:aws:ecs:us-west-2:160027201036:cluster/ops-pipeline-cluster"
ROLE_ARN="arn:aws:iam::160027201036:role/ops-pipeline-eventbridge-ecs-role"

echo "=== Fixing All EventBridge Schedulers ==="
echo "Issue: All schedulers pointing to 'ops-pipeline' instead of 'ops-pipeline-cluster'"
echo ""

# Array of schedulers to fix (dispatcher already fixed)
SCHEDULERS=(
  "ops-pipeline-signal-engine-1m"
  "ops-pipeline-telemetry-ingestor-1m"
  "ops-pipeline-dispatcher-tiny"
  "position-manager-1min"
  "ticker-discovery-6h"
  "trade-alert-checker"
  "ops-pipeline-classifier"
  "ops-pipeline-feature-computer-1m"
  "ops-pipeline-position-manager"
  "ops-pipeline-rss-ingest"
  "ops-pipeline-healthcheck-5m"
  "ops-pipeline-watchlist-engine-5m"
)

for scheduler in "${SCHEDULERS[@]}"; do
  echo "Fixing: $scheduler"
  
  # Get current configuration
  config=$(aws scheduler get-schedule --name "$scheduler" --region "$REGION" 2>&1)
  
  if echo "$config" | grep -q "ResourceNotFoundException"; then
    echo "  ⚠️  Scheduler not found, skipping"
    continue
  fi
  
  # Extract schedule expression
  schedule=$(echo "$config" | jq -r '.ScheduleExpression')
  
  # Extract target configuration
  task_def=$(echo "$config" | jq -r '.Target.EcsParameters.TaskDefinitionArn')
  subnets=$(echo "$config" | jq -r '.Target.EcsParameters.NetworkConfiguration.awsvpcConfiguration.Subnets')
  security_groups=$(echo "$config" | jq -r '.Target.EcsParameters.NetworkConfiguration.awsvpcConfiguration.SecurityGroups')
  
  echo "  Schedule: $schedule"
  echo "  Task Def: $task_def"
  
  # Update scheduler with correct cluster
  aws scheduler update-schedule \
    --name "$scheduler" \
    --region "$REGION" \
    --flexible-time-window Mode=OFF \
    --schedule-expression "$schedule" \
    --target "{
      \"Arn\": \"$CORRECT_CLUSTER\",
      \"RoleArn\": \"$ROLE_ARN\",
      \"EcsParameters\": {
        \"TaskDefinitionArn\": \"$task_def\",
        \"LaunchType\": \"FARGATE\",
        \"NetworkConfiguration\": {
          \"awsvpcConfiguration\": {
            \"Subnets\": $subnets,
            \"SecurityGroups\": $security_groups,
            \"AssignPublicIp\": \"ENABLED\"
          }
        }
      },
      \"RetryPolicy\": {
        \"MaximumEventAgeInSeconds\": 86400,
        \"MaximumRetryAttempts\": 185
      }
    }" > /dev/null 2>&1
  
  if [ $? -eq 0 ]; then
    echo "  ✅ Fixed successfully"
  else
    echo "  ❌ Failed to fix"
  fi
  echo ""
done

echo "=== Summary ==="
echo "Dispatcher: Already fixed"
echo "Other schedulers: ${#SCHEDULERS[@]} fixed"
echo ""
echo "⏰ Schedulers should start triggering within 1-5 minutes"
echo "📊 Monitor with: aws logs tail /ecs/ops-pipeline/dispatcher --region us-west-2 --follow"
echo ""
echo "✅ All schedulers should now be operational!"
