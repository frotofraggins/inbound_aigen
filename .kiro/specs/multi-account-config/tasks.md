# Multi-Account Configuration System - Tasks

**Status:** ✅ COMPLETED (February 3, 2026)  
**Priority:** HIGH  
**Effort:** 2-3 hours

---

## Task Checklist

### Phase 1: Core Infrastructure ✅

- [x] 1.1 Define account tier structure in `config/trading_params.json`
- [x] 1.2 Add `ACCOUNT_TIERS` constant to `services/dispatcher/config.py`
- [x] 1.3 Create database migration to add `account_name` column to `dispatch_executions`
- [x] 1.4 Create database migration to add `account_name` column to `active_positions`
- [x] 1.5 Apply database migrations

### Phase 2: Configuration Loader ✅

- [x] 2.1 Update `load_config()` to read `ACCOUNT_TIER` environment variable
- [x] 2.2 Implement tier-specific credential loading from Secrets Manager
- [x] 2.3 Implement tier-specific config loading from SSM Parameter Store
- [x] 2.4 Add fallback logic for backward compatibility
- [x] 2.5 Add configuration validation at startup
- [x] 2.6 Add logging for loaded tier, credentials, and config

### Phase 3: Risk Gate Updates ✅

- [x] 3.1 Update `get_account_state()` to accept `account_name` parameter
- [x] 3.2 Add `WHERE account_name = %s` filter to position count query
- [x] 3.3 Add `WHERE account_name = %s` filter to exposure calculation query
- [x] 3.4 Update `evaluate_all_gates()` to pass `account_name` parameter
- [x] 3.5 Update `main.py` to extract `account_name` from config
- [x] 3.6 Update `main.py` to pass `account_name` to risk gate functions

### Phase 4: Large Account Deployment ✅

- [x] 4.1 Create SSM parameter `/ops-pipeline/dispatcher_config_large`
  - [x] Set `max_notional_exposure: 10000`
  - [x] Set `max_open_positions: 5`
  - [x] Set `max_contracts_per_trade: 10`
  - [x] Set `max_daily_loss: 500`
  - [x] Set `confidence_min_options_swing: 0.40`
  - [x] Set `confidence_min_options_daytrade: 0.60`
  - [x] Set `allowed_actions: ["BUY_CALL", "BUY_PUT"]`
  - [x] Set `paper_ignore_buying_power: false`

- [x] 4.2 Build Docker image with tag `separate-configs`
- [x] 4.3 Push Docker image to ECR
- [x] 4.4 Register task definition revision 34 with `ACCOUNT_TIER=large`
- [x] 4.5 Update `dispatcher-service` to use revision 34
- [x] 4.6 Verify service starts successfully
- [x] 4.7 Verify logs show correct config loaded
- [x] 4.8 Verify large account connects to Alpaca

### Phase 5: Tiny Account Setup ✅

- [x] 5.1 Create Secrets Manager secret `ops-pipeline/alpaca/tiny`
  - [x] Add `api_key` for tiny account
  - [x] Add `api_secret` for tiny account
  - [x] Add `account_name: "tiny-paper-account"`

- [x] 5.2 Create SSM parameter `/ops-pipeline/dispatcher_config_tiny`
  - [x] Set `max_notional_exposure: 1500`
  - [x] Set `max_open_positions: 2`
  - [x] Set `max_contracts_per_trade: 2`
  - [x] Set `max_daily_loss: 100`
  - [x] Set `max_risk_per_trade_pct: 0.10`
  - [x] Set `confidence_min_options_swing: 0.40`
  - [x] Set `confidence_min_options_daytrade: 0.60`
  - [x] Set `allowed_actions: ["BUY_CALL", "BUY_PUT"]`
  - [x] Set `paper_ignore_buying_power: false`

### Phase 6: Tiny Account Deployment ✅

- [x] 6.1 Register task definition revision 14 with `ACCOUNT_TIER=tiny`
- [x] 6.2 Update `dispatcher-tiny-service` to use revision 14
- [x] 6.3 Verify service starts successfully
- [x] 6.4 Verify logs show correct config loaded
- [x] 6.5 Verify tiny account connects to Alpaca
- [x] 6.6 Verify tiny account shows correct buying power

### Phase 7: Verification & Testing ✅

- [x] 7.1 Verify large account loads `/ops-pipeline/dispatcher_config_large`
- [x] 7.2 Verify tiny account loads `/ops-pipeline/dispatcher_config_tiny`
- [x] 7.3 Verify large account uses large credentials
- [x] 7.4 Verify tiny account uses tiny credentials
- [x] 7.5 Verify position tracking filters by account_name
- [x] 7.6 Verify risk gates evaluate per-account
- [x] 7.7 Verify no cross-account interference
- [x] 7.8 Monitor logs for 30 minutes to ensure stability

### Phase 8: Documentation ✅

- [x] 8.1 Create `SEPARATE_ACCOUNT_CONFIGS_SOLUTION.md`
- [x] 8.2 Create `SEPARATE_CONFIGS_DEPLOYED_2026-02-03.md`
- [x] 8.3 Update `SESSION_COMPLETE_2026-02-03.md`
- [x] 8.4 Create deployment script `deploy_separate_account_configs.sh`
- [x] 8.5 Document SSM parameter schemas
- [x] 8.6 Document Secrets Manager schemas
- [x] 8.7 Create this spec (requirements, design, tasks)

---

## Future Enhancements (Not Started)

### Phase 9: Small Account Support (Future)

- [ ] 9.1 Create `ops-pipeline/alpaca/small` secret
- [ ] 9.2 Create `/ops-pipeline/dispatcher_config_small` SSM parameter
  - [ ] Set `max_notional_exposure: 4000`
  - [ ] Set `max_open_positions: 3`
  - [ ] Set `max_contracts_per_trade: 3`
  - [ ] Set `max_daily_loss: 200`
- [ ] 9.3 Register task definition with `ACCOUNT_TIER=small`
- [ ] 9.4 Create `dispatcher-small-service` ECS service
- [ ] 9.5 Verify deployment and isolation

### Phase 10: Medium Account Support (Future)

- [ ] 10.1 Create `ops-pipeline/alpaca/medium` secret
- [ ] 10.2 Create `/ops-pipeline/dispatcher_config_medium` SSM parameter
  - [ ] Set `max_notional_exposure: 15000`
  - [ ] Set `max_open_positions: 4`
  - [ ] Set `max_contracts_per_trade: 5`
  - [ ] Set `max_daily_loss: 300`
- [ ] 10.3 Register task definition with `ACCOUNT_TIER=medium`
- [ ] 10.4 Create `dispatcher-medium-service` ECS service
- [ ] 10.5 Verify deployment and isolation

### Phase 11: CloudWatch Metrics (Future)

- [ ] 11.1 Add CloudWatch metrics client to dispatcher
- [ ] 11.2 Emit `positions.count` metric with account_name dimension
- [ ] 11.3 Emit `exposure.dollars` metric with account_name dimension
- [ ] 11.4 Emit `trades.executed` metric with account_name dimension
- [ ] 11.5 Emit `gates.failed` metric with account_name and reason dimensions
- [ ] 11.6 Create CloudWatch dashboard for multi-account monitoring

### Phase 12: Configuration Auto-Reload (Future)

- [ ] 12.1 Implement SSM parameter change detection
- [ ] 12.2 Add configuration reload without service restart
- [ ] 12.3 Add validation before applying new config
- [ ] 12.4 Add rollback on invalid config
- [ ] 12.5 Add logging for config changes

### Phase 13: Unit Tests (Future)

- [ ] 13.1 Test `load_config()` with different tiers
- [ ] 13.2 Test fallback to default config
- [ ] 13.3 Test `get_account_state()` filtering
- [ ] 13.4 Test risk gates with multiple accounts
- [ ] 13.5 Test configuration validation
- [ ] 13.6 Test error handling for missing credentials
- [ ] 13.7 Test error handling for invalid config

### Phase 14: Integration Tests (Future)

- [ ] 14.1 Test multi-account deployment
- [ ] 14.2 Test config update without redeployment
- [ ] 14.3 Test account isolation
- [ ] 14.4 Test large account trading
- [ ] 14.5 Test tiny account trading
- [ ] 14.6 Test cross-account non-interference

---

## Deployment Commands

### Create SSM Parameters

```bash
# Large account config
aws ssm put-parameter \
  --name /ops-pipeline/dispatcher_config_large \
  --type String \
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
  --overwrite

# Tiny account config
aws ssm put-parameter \
  --name /ops-pipeline/dispatcher_config_tiny \
  --type String \
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
  --overwrite
```

### Build and Deploy

```bash
# Build Docker image
cd services/dispatcher
docker build -t ops-pipeline/dispatcher:separate-configs .

# Tag and push to ECR
aws ecr get-login-password --region us-west-2 | \
  docker login --username AWS --password-stdin \
  160027201036.dkr.ecr.us-west-2.amazonaws.com

docker tag ops-pipeline/dispatcher:separate-configs \
  160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/dispatcher:separate-configs

docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/dispatcher:separate-configs

# Register task definitions
aws ecs register-task-definition \
  --cli-input-json file://deploy/dispatcher-task-definition.json

aws ecs register-task-definition \
  --cli-input-json file://deploy/dispatcher-task-definition-tiny-service.json

# Update services
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service dispatcher-service \
  --task-definition ops-pipeline-dispatcher:34

aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service dispatcher-tiny-service \
  --task-definition ops-pipeline-dispatcher-tiny-service:14
```

### Verify Deployment

```bash
# Check service status
aws ecs describe-services \
  --cluster ops-pipeline-cluster \
  --services dispatcher-service dispatcher-tiny-service \
  --query 'services[*].{name:serviceName,desired:desiredCount,running:runningCount,taskDef:taskDefinition}'

# Check logs
aws logs filter-log-events \
  --log-group-name /ecs/ops-pipeline/dispatcher \
  --start-time $(($(date +%s) - 300))000 \
  --filter-pattern "tier-specific"

aws logs filter-log-events \
  --log-group-name /ecs/ops-pipeline/dispatcher-tiny-service \
  --start-time $(($(date +%s) - 300))000 \
  --filter-pattern "tier-specific"
```

---

## Success Criteria

### Deployment Success ✅
- [x] Both services deployed and running
- [x] Each service loads correct credentials
- [x] Each service loads correct configuration
- [x] Services log account name and tier at startup

### Trading Behavior ✅
- [x] Large account respects $10K exposure limit
- [x] Tiny account can execute 1-2 contract trades
- [x] Tiny account respects $1.5K exposure limit
- [x] Each account operates independently

### Risk Management ✅
- [x] Position tracking filtered by account
- [x] Risk gates evaluate per-account
- [x] No cross-account interference

### Observability ✅
- [x] Logs show account name and tier
- [x] Logs show loaded configuration
- [x] Logs show risk gate evaluations per-account

---

## Rollback Plan

If deployment causes issues:

```bash
# Rollback large account
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service dispatcher-service \
  --task-definition ops-pipeline-dispatcher:33

# Rollback tiny account
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service dispatcher-tiny-service \
  --task-definition ops-pipeline-dispatcher-tiny-service:13
```

Both accounts will fall back to `/ops-pipeline/dispatcher_config` (backward compatible).

---

**Completion Date:** February 3, 2026  
**Status:** ✅ ALL TASKS COMPLETE  
**Next Steps:** Monitor system behavior, consider adding small/medium tiers
