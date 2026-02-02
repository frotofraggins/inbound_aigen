#!/bin/bash
# Enable Options-Only Mode
# Removes BUY_STOCK and SELL_STOCK from allowed actions
# Forces system to trade ONLY calls and puts (no stock trading)

set -e

echo "=================================="
echo "ENABLE OPTIONS-ONLY MODE"
echo "=================================="
echo ""
echo "Current configuration allows: BUY_CALL, BUY_PUT, BUY_STOCK, SELL_STOCK"
echo "Changing to: BUY_CALL, BUY_PUT (OPTIONS ONLY)"
echo ""

# New configuration - OPTIONS ONLY
NEW_CONFIG='{
  "max_bar_age_seconds": 7200,
  "max_feature_age_seconds": 7200,
  "confidence_min": 0.3,
  "confidence_min_stock": 0.9,
  "confidence_min_options_swing": 0.40,
  "confidence_min_options_daytrade": 0.50,
  "max_trades_per_ticker_per_day": 4,
  "allowed_actions": [
    "BUY_CALL",
    "BUY_PUT"
  ],
  "allow_shorting": true,
  "options_only_mode": true,
  "force_options": true
}'

echo "Updating SSM parameter: /ops-pipeline/dispatcher_config"
aws ssm put-parameter \
  --name "/ops-pipeline/dispatcher_config" \
  --value "$NEW_CONFIG" \
  --type String \
  --overwrite \
  --region us-west-2

echo ""
echo "✅ Configuration updated!"
echo ""
echo "Changes:"
echo "  ✗ Removed: BUY_STOCK"
echo "  ✗ Removed: SELL_STOCK"
echo "  ✅ Kept: BUY_CALL"
echo "  ✅ Kept: BUY_PUT"
echo "  ✅ Added: options_only_mode=true"
echo "  ✅ Added: force_options=true"
echo "  ⚠️ Raised: confidence_min_stock=0.9 (effectively blocks stocks)"
echo ""
echo "Next steps:"
echo "1. Dispatcher will reload config on next run (< 5 min)"
echo "2. Stock signals will be REJECTED (action_allowed gate)"
echo "3. Only CALL/PUT signals will execute"
echo ""
echo "To verify:"
echo "  aws ssm get-parameter --name /ops-pipeline/dispatcher_config --region us-west-2 --query 'Parameter.Value' --output text | python3 -m json.tool"
echo ""
echo "To monitor next signals:"
echo "  aws logs tail /ecs/ops-pipeline/signal-engine-1m --region us-west-2 --since 5m --follow | grep signal_computed"
echo ""
