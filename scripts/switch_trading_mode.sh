#!/bin/bash
# Switch between PAPER and LIVE trading modes
# Usage: ./switch_trading_mode.sh [paper|live]

set -e

MODE=$1
REGION="us-west-2"

if [ -z "$MODE" ]; then
    echo "Usage: $0 [paper|live]"
    echo ""
    echo "Current mode:"
    aws ecs describe-task-definition \
        --task-definition ops-pipeline-dispatcher \
        --region $REGION \
        --query 'taskDefinition.containerDefinitions[0].environment[?name==`EXECUTION_MODE`].value' \
        --output text
    exit 1
fi

MODE_UPPER=$(echo "$MODE" | tr '[:lower:]' '[:upper:]')

if [ "$MODE_UPPER" != "PAPER" ] && [ "$MODE_UPPER" != "LIVE" ]; then
    echo "Error: Mode must be 'paper' or 'live'"
    exit 1
fi

# Map to actual execution mode
if [ "$MODE_UPPER" == "PAPER" ]; then
    EXECUTION_MODE="ALPACA_PAPER"
    API_URL="https://paper-api.alpaca.markets"
elif [ "$MODE_UPPER" == "LIVE" ]; then
    EXECUTION_MODE="ALPACA_LIVE"
    API_URL="https://api.alpaca.markets"
fi

echo "========================================="
echo "SWITCHING TO: $MODE_UPPER TRADING"
echo "Execution Mode: $EXECUTION_MODE"
echo "API URL: $API_URL"
echo "========================================="
echo ""

# Confirm if switching to live
if [ "$MODE_UPPER" == "LIVE" ]; then
    echo "⚠️  WARNING: Switching to LIVE TRADING with REAL MONEY ⚠️"
    echo ""
    echo "Checklist before enabling live:"
    echo "  [ ] Options execution gates implemented and tested"
    echo "  [ ] Account kill switches active"
    echo "  [ ] Paper trading validated for 1+ week"
    echo "  [ ] Position sizes appropriate for live account"
    echo "  [ ] Risk limits set correctly"
    echo ""
    read -p "Are you ABSOLUTELY SURE you want to enable LIVE trading? (type YES): " confirmation
    
    if [ "$confirmation" != "YES" ]; then
        echo "Cancelled. Staying in current mode."
        exit 0
    fi
fi

echo "Step 1: Getting current task definition..."
TASK_DEF=$(aws ecs describe-task-definition \
    --task-definition ops-pipeline-dispatcher \
    --region $REGION \
    --query 'taskDefinition' \
    --output json)

echo "Step 2: Updating EXECUTION_MODE environment variable..."

# Create new task definition with updated EXECUTION_MODE
NEW_TASK_DEF=$(echo "$TASK_DEF" | jq --arg mode "$EXECUTION_MODE" '
  .containerDefinitions[0].environment = [
    .containerDefinitions[0].environment[] | 
    if .name == "EXECUTION_MODE" then .value = $mode else . end
  ] |
  del(.taskDefinitionArn, .revision, .status, .requiresAttributes, .compatibilities, .registeredAt, .registeredBy)
')

echo "$NEW_TASK_DEF" > /tmp/dispatcher-task-definition-new.json

echo "Step 3: Registering new task definition..."
REVISION=$(aws ecs register-task-definition \
    --cli-input-json file:///tmp/dispatcher-task-definition-new.json \
    --region $REGION \
    --query 'taskDefinition.revision' \
    --output text)

echo "New task definition registered: ops-pipeline-dispatcher:$REVISION"

echo "Step 4: Updating scheduler to use new revision..."
aws scheduler update-schedule \
    --name ops-pipeline-dispatcher \
    --region $REGION \
    --schedule-expression "rate(1 minute)" \
    --flexible-time-window Mode=OFF \
    --target "{
        \"Arn\":\"arn:aws:ecs:us-west-2:160027201036:cluster/ops-pipeline-cluster\",
        \"RoleArn\":\"arn:aws:iam::160027201036:role/ops-pipeline-eventbridge-ecs-role\",
        \"EcsParameters\":{
            \"TaskDefinitionArn\":\"arn:aws:ecs:us-west-2:160027201036:task-definition/ops-pipeline-dispatcher:$REVISION\",
            \"LaunchType\":\"FARGATE\",
            \"NetworkConfiguration\":{
                \"awsvpcConfiguration\":{
                    \"Subnets\":[\"subnet-0c182a149eeef918a\"],
                    \"SecurityGroups\":[\"sg-0cd16a909f4e794ce\"],
                    \"AssignPublicIp\":\"ENABLED\"
                }
            }
        },
        \"RetryPolicy\":{
            \"MaximumRetryAttempts\":185,
            \"MaximumEventAgeInSeconds\":86400
        }
    }"

echo ""
echo "✅ Successfully switched to $MODE_UPPER trading mode!"
echo ""
echo "Dispatcher will use $EXECUTION_MODE on next run."
echo ""

if [ "$MODE_UPPER" == "LIVE" ]; then
    echo "🔴 LIVE TRADING ACTIVE - MONITOR CLOSELY 🔴"
    echo ""
    echo "Monitor logs:"
    echo "  aws logs tail /ecs/ops-pipeline/dispatcher --region $REGION --follow"
    echo ""
    echo "Check account:"
    echo "  # Query Alpaca account status"
    echo ""
fi

echo "View recent logs:"
echo "  aws logs tail /ecs/ops-pipeline/dispatcher --region $REGION --since 5m"
