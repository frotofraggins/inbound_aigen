#!/bin/bash
# Create separate SSM configs for large and tiny accounts

set -e

echo "Creating separate account configs..."

# Large account config
echo "Creating large account config..."
aws ssm put-parameter \
  --name /ops-pipeline/dispatcher_config_large \
  --value '{
    "account_tier": "large",
    "max_notional_exposure": 10000,
    "max_open_positions": 5,
    "max_contracts_per_trade": 10,
    "max_daily_loss": 500,
    "max_risk_per_trade_pct": 0.05,
    "ticker_cooldown_minutes": 15,
    "confidence_min_options_swing": 0.40,
    "confidence_min_options_daytrade": 0.60,
    "allowed_actions": ["BUY_CALL", "BUY_PUT"],
    "paper_ignore_buying_power": false
  }' \
  --type String \
  --region us-west-2 \
  --overwrite

echo "✓ Large account config created"

# Tiny account config
echo "Creating tiny account config..."
aws ssm put-parameter \
  --name /ops-pipeline/dispatcher_config_tiny \
  --value '{
    "account_tier": "tiny",
    "max_notional_exposure": 1500,
    "max_open_positions": 2,
    "max_contracts_per_trade": 2,
    "max_daily_loss": 100,
    "max_risk_per_trade_pct": 0.10,
    "ticker_cooldown_minutes": 15,
    "confidence_min_options_swing": 0.40,
    "confidence_min_options_daytrade": 0.60,
    "allowed_actions": ["BUY_CALL", "BUY_PUT"],
    "paper_ignore_buying_power": false
  }' \
  --type String \
  --region us-west-2 \
  --overwrite

echo "✓ Tiny account config created"

echo ""
echo "✅ Both account configs created!"
echo ""
echo "Next steps:"
echo "1. Update services/dispatcher/config.py to load tier-specific config"
echo "2. Rebuild and deploy dispatcher Docker image"
echo "3. Update both task definitions with new image"
echo "4. Restart both services"
