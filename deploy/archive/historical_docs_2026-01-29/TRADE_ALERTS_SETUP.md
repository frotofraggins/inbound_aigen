# Trade Alert System - Quick Setup Guide

**Purpose:** Get instant notifications when your system executes trades (stocks or options)

## What It Does

Sends you an email/SMS alert whenever:
- Any trade executes (stock or options)
- Includes full trade details (ticker, price, size, option strike/expiration)
- Different format for stocks vs options

**Example alerts:**
```
🔔 OPTIONS TRADE: BUY AAPL CALL
Strategy: day_trade
Strike: $152.50
Expiration: 2026-01-27
Contracts: 20
Premium: $2.50
Total Cost: $5,000.00
```

## Setup (5 minutes)

### 1. Create SNS Topic
```bash
aws sns create-topic \
  --name trading-alerts \
  --region us-west-2
```

**Output:** Topic ARN (save this!)
```
arn:aws:sns:us-west-2:160027201036:trading-alerts
```

### 2. Subscribe Your Email
```bash
aws sns subscribe \
  --topic-arn arn:aws:sns:us-west-2:160027201036:trading-alerts \
  --protocol email \
  --notification-endpoint your-email@example.com \
  --region us-west-2
```

**Check your email** and confirm subscription.

### 3. Deploy Alert Lambda
```bash
cd services/trade_alert_lambda

# Install dependencies
pip3 install -r requirements.txt -t package/
cp lambda_function.py package/

# Create deployment package
cd package
zip -r ../trade_alert_lambda.zip .
cd ..

# Create Lambda function
aws lambda create-function \
  --function-name trade-alert-checker \
  --runtime python3.11 \
  --role arn:aws:iam::160027201036:role/lambda-execution-role \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://trade_alert_lambda.zip \
  --timeout 60 \
  --memory-size 256 \
  --environment "Variables={TRADE_ALERT_TOPIC_ARN=arn:aws:sns:us-west-2:160027201036:trading-alerts}" \
  --region us-west-2
```

### 4. Create EventBridge Schedule
```bash
aws scheduler create-schedule \
  --name trade-alert-checker \
  --schedule-expression "rate(1 minute)" \
  --flexible-time-window Mode=OFF \
  --target '{
    "Arn": "arn:aws:lambda:us-west-2:160027201036:function:trade-alert-checker",
    "RoleArn": "arn:aws:iam::160027201036:role/EventBridgeSchedulerRole"
  }' \
  --region us-west-2
```

## That's It!

You'll now get alerts within 1-2 minutes of any trade execution.

### Testing

To test the alert system:
```bash
# Invoke Lambda manually
aws lambda invoke \
  --function-name trade-alert-checker \
  --region us-west-2 \
  response.json

cat response.json
```

Should return:
```json
{"statusCode": 200, "body": "No recent trades"}
```

When a trade happens, you'll get the alert email.

## Monitoring

**Check if Lambda is running:**
```bash
aws logs tail /aws/lambda/trade-alert-checker --follow --region us-west-2
```

**Check SNS topic:**
```bash
aws sns list-subscriptions-by-topic \
  --topic-arn arn:aws:sns:us-west-2:160027201036:trading-alerts \
  --region us-west-2
```

## Troubleshooting

**Not getting alerts?**
1. Check Lambda logs for errors
2. Verify email subscription is confirmed
3. Test SNS topic manually:
   ```bash
   aws sns publish \
     --topic-arn arn:aws:sns:us-west-2:160027201036:trading-alerts \
     --subject "Test" \
     --message "Test message" \
     --region us-west-2
   ```

**Too many alerts?**
- Adjust schedule to rate(5 minutes) instead of rate(1 minute)
- Add filters in Lambda code (only alert on options, or >$1000 trades)

## Cost

- Lambda: ~$0.20/month (43,200 invocations)
- SNS: $0.00 (free tier)
- **Total: <$1/month**

---

**Quick deployment:** Run the 4 commands above and you're done!
