#!/bin/bash
#
# Trade Alerts Setup Script
# Quick deployment of trade notification system
#

set -e

echo "========================================================================"
echo "TRADE ALERTS SETUP"
echo "========================================================================"
echo ""
echo "This will set up email notifications for all trades (stocks + options)"
echo "Notifications will be sent to: nsflournoy@gmail.com"
echo ""

AWS_REGION="us-west-2"
AWS_ACCOUNT="160027201036"
EMAIL="nsflournoy@gmail.com"

# Step 1: Create SNS Topic
echo "Step 1: Creating SNS topic..."
TOPIC_ARN=$(aws sns create-topic \
  --name trading-alerts \
  --region $AWS_REGION \
  --query 'TopicArn' \
  --output text)

echo "✅ Topic created: $TOPIC_ARN"

# Step 2: Subscribe email
echo ""
echo "Step 2: Subscribing $EMAIL to alerts..."
aws sns subscribe \
  --topic-arn $TOPIC_ARN \
  --protocol email \
  --notification-endpoint $EMAIL \
  --region $AWS_REGION

echo "✅ Subscription created"
echo "⚠️  CHECK YOUR EMAIL ($EMAIL) and confirm the subscription!"
echo ""
read -p "Press ENTER after confirming email subscription..."

# Step 3: Package Lambda
echo ""
echo "Step 3: Packaging Lambda function..."
cd services/trade_alert_lambda

mkdir -p package
pip3 install -r requirements.txt -t package/ --quiet
cp lambda_function.py package/

cd package
zip -r ../trade_alert_lambda.zip . > /dev/null 2>&1
cd ..

echo "✅ Lambda package created"

# Step 4: Deploy Lambda
echo ""
echo "Step 4: Deploying Lambda function..."

# Check if function exists
if aws lambda get-function --function-name trade-alert-checker --region $AWS_REGION &>/dev/null; then
    echo "Lambda exists, updating..."
    aws lambda update-function-code \
      --function-name trade-alert-checker \
      --zip-file fileb://trade_alert_lambda.zip \
      --region $AWS_REGION
    
    aws lambda update-function-configuration \
      --function-name trade-alert-checker \
      --environment "Variables={TRADE_ALERT_TOPIC_ARN=$TOPIC_ARN}" \
      --region $AWS_REGION
    
    echo "✅ Lambda updated"
else
    echo "Creating new Lambda function..."
    aws lambda create-function \
      --function-name trade-alert-checker \
      --runtime python3.11 \
      --role arn:aws:iam::$AWS_ACCOUNT:role/ops-pipeline-lambda-role \
      --handler lambda_function.lambda_handler \
      --zip-file fileb://trade_alert_lambda.zip \
      --timeout 60 \
      --memory-size 256 \
      --environment "Variables={TRADE_ALERT_TOPIC_ARN=$TOPIC_ARN}" \
      --region $AWS_REGION
    
    echo "✅ Lambda created"
fi

cd ../..

# Step 5: Create EventBridge Schedule
echo ""
echo "Step 5: Creating EventBridge schedule (1 minute interval)..."

# Delete existing schedule if it exists
aws scheduler delete-schedule \
  --name trade-alert-checker \
  --region $AWS_REGION 2>/dev/null || true

# Create new schedule
aws scheduler create-schedule \
  --name trade-alert-checker \
  --schedule-expression "rate(1 minute)" \
  --flexible-time-window Mode=OFF \
  --target "{
    \"Arn\": \"arn:aws:lambda:$AWS_REGION:$AWS_ACCOUNT:function:trade-alert-checker\",
    \"RoleArn\": \"arn:aws:iam::$AWS_ACCOUNT:role/EventBridgeSchedulerRole\"
  }" \
  --region $AWS_REGION

echo "✅ Schedule created"

# Summary
echo ""
echo "========================================================================"
echo "TRADE ALERTS SETUP COMPLETE"
echo "========================================================================"
echo ""
echo "Configuration:"
echo "  Email: nsflournoy@gmail.com"
echo "  Topic: $TOPIC_ARN"
echo "  Lambda: trade-alert-checker"
echo "  Schedule: Every 1 minute"
echo ""
echo "What you'll receive:"
echo "  🔔 OPTIONS TRADE: BUY AAPL CALL (when options execute)"
echo "  📈 STOCK TRADE: BUY MSFT (when stocks execute)"
echo ""
echo "Alerts will arrive within 1-2 minutes of any trade execution."
echo ""
echo "To test:"
echo "  aws lambda invoke --function-name trade-alert-checker response.json --region us-west-2"
echo ""
