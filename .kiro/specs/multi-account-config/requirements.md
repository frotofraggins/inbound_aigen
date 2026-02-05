# Multi-Account Configuration System - Requirements

## 🎯 Purpose

Enable the trading system to operate multiple Alpaca accounts (tiny, small, medium, large) simultaneously with account-specific risk parameters, credentials, and trading limits.

## 📊 Current State Reference

- `SESSION_COMPLETE_2026-02-03.md` - Recent deployment status
- `SEPARATE_CONFIGS_DEPLOYED_2026-02-03.md` - Configuration deployment
- `services/dispatcher/config.py` - Current implementation
- `config/trading_params.json` - Account tier definitions

## ✅ Requirements (Must Have)

### R1: Account Tier System

**Description:** Support multiple account size tiers with appropriate risk parameters

**Account Tiers:**
- **Tiny:** $1K-$2K accounts (aggressive growth strategy)
- **Small:** $2K-$5K accounts (balanced growth)
- **Medium:** $5K-$25K accounts (moderate risk)
- **Large:** $25K+ accounts (professional risk management)

**Acceptance Criteria:**
- System automatically determines tier based on buying power
- Each tier has distinct risk parameters
- Tier configuration is centralized and maintainable

### R2: Separate Credentials per Account

**Description:** Each account tier uses its own Alpaca API credentials

**Requirements:**
- Credentials stored in AWS Secrets Manager
- Secret naming: `ops-pipeline/alpaca/{tier}` (e.g., `ops-pipeline/alpaca/tiny`)
- Each secret contains: `api_key`, `api_secret`, `account_name`
- Fallback to default credentials for backward compatibility

**Acceptance Criteria:**
- Large account uses `ops-pipeline/alpaca/large` credentials
- Tiny account uses `ops-pipeline/alpaca/tiny` credentials
- No credential cross-contamination between accounts
- Service logs show which account credentials are loaded

### R3: Separate Risk Configurations per Account

**Description:** Each account tier has its own risk limits and trading parameters

**Configuration Storage:** AWS SSM Parameter Store
- `/ops-pipeline/dispatcher_config_large` - Large account config
- `/ops-pipeline/dispatcher_config_tiny` - Tiny account config
- `/ops-pipeline/dispatcher_config_small` - Small account config (future)
- `/ops-pipeline/dispatcher_config_medium` - Medium account config (future)

**Required Parameters per Account:**
- `max_notional_exposure` - Maximum dollar exposure
- `max_open_positions` - Maximum concurrent positions
- `max_contracts_per_trade` - Maximum contracts per trade
- `max_daily_loss` - Daily loss limit (kill switch)
- `max_risk_per_trade_pct` - Risk per trade as % of capital
- `ticker_cooldown_minutes` - Cooldown after trading a ticker
- `confidence_min_options_swing` - Minimum confidence for swing trades
- `confidence_min_options_daytrade` - Minimum confidence for day trades
- `allowed_actions` - Permitted trade types (e.g., ["BUY_CALL", "BUY_PUT"])
- `paper_ignore_buying_power` - Whether to ignore buying power checks

**Acceptance Criteria:**
- Each account loads its tier-specific configuration
- Configuration changes don't require code deployment
- Invalid configurations are rejected at startup
- Service logs show which configuration is loaded

### R4: Account Isolation

**Description:** Accounts operate independently without interference

**Requirements:**
- Position tracking filtered by `account_name`
- Risk gates evaluate per-account limits
- Exposure calculations per-account
- Daily loss tracking per-account
- No cross-account position counting

**Acceptance Criteria:**
- Large account positions don't affect tiny account risk gates
- Tiny account positions don't affect large account risk gates
- Each account can hit its own limits independently
- Database queries filter by `account_name` column

### R5: Tier-Appropriate Risk Parameters

**Description:** Risk parameters scale appropriately with account size

**Large Account ($209K buying power):**
- Max exposure: $10,000 (~5% of capital)
- Max positions: 5
- Max contracts per trade: 10
- Daily loss limit: $500 (0.25% of capital)
- Risk per trade: 1-2% (professional)

**Tiny Account ($1,804 buying power):**
- Max exposure: $1,500 (~80% of capital)
- Max positions: 2
- Max contracts per trade: 2
- Daily loss limit: $100 (5.5% of capital)
- Risk per trade: 10-15% (aggressive growth)

**Acceptance Criteria:**
- Tiny account can afford to execute trades
- Large account maintains professional risk management
- Risk parameters prevent account blow-up
- Parameters are documented and justified

### R6: Environment Variable Configuration

**Description:** Account tier specified via environment variable

**Requirements:**
- `ACCOUNT_TIER` environment variable in ECS task definition
- Valid values: `tiny`, `small`, `medium`, `large`
- Default: `large` (for backward compatibility)
- Used to load correct credentials and configuration

**Acceptance Criteria:**
- Large account service has `ACCOUNT_TIER=large`
- Tiny account service has `ACCOUNT_TIER=tiny`
- Invalid tier values are rejected at startup
- Service logs show configured tier

## 🚫 Non-Requirements (Must NOT)

### NR1: Cross-Account Trading
- System must NOT allow one account to trade on behalf of another
- Credentials must NOT be shared between accounts

### NR2: Dynamic Tier Switching
- Account tier must NOT change during service runtime
- Requires service restart to change tier

### NR3: Shared Configuration
- Accounts must NOT share risk configurations
- Each tier must have independent parameters

## 📋 Acceptance Criteria (Overall)

### AC1: Deployment Success
- ✅ Both large and tiny accounts deployed and running
- ✅ Each account loads correct credentials
- ✅ Each account loads correct configuration
- ✅ Services log account name and tier at startup

### AC2: Trading Behavior
- ✅ Large account respects $10K exposure limit
- ✅ Tiny account can execute 1-2 contract trades
- ✅ Tiny account respects $1.5K exposure limit
- ✅ Each account operates independently

### AC3: Risk Management
- ✅ Position tracking filtered by account
- ✅ Risk gates evaluate per-account
- ✅ Daily loss tracking per-account
- ✅ No cross-account interference

### AC4: Observability
- ✅ Logs show account name and tier
- ✅ Logs show loaded configuration
- ✅ Logs show risk gate evaluations per-account
- ✅ CloudWatch metrics per-account (future)

## 🔍 Test Scenarios

### TS1: Large Account Trading
**Given:** Large account with $209K buying power  
**When:** Signal Engine generates recommendation  
**Then:** 
- Dispatcher loads large account config
- Risk gates use $10K exposure limit
- Can open up to 5 positions
- Can trade up to 10 contracts per trade

### TS2: Tiny Account Trading
**Given:** Tiny account with $1,804 buying power  
**When:** Signal Engine generates recommendation  
**Then:**
- Dispatcher loads tiny account config
- Risk gates use $1.5K exposure limit
- Can open up to 2 positions
- Can trade up to 2 contracts per trade

### TS3: Account Isolation
**Given:** Large account has 5 open positions  
**When:** Tiny account evaluates risk gates  
**Then:**
- Tiny account shows 0 positions (not 5)
- Tiny account can still open positions
- Large account positions don't affect tiny account

### TS4: Configuration Update
**Given:** Need to change tiny account limits  
**When:** Update SSM parameter `/ops-pipeline/dispatcher_config_tiny`  
**Then:**
- Restart tiny account service
- New limits take effect
- No code deployment required

## 📊 Success Metrics

### Deployment Metrics
- ✅ 2 accounts deployed (large, tiny)
- ✅ 0 credential cross-contamination incidents
- ✅ 0 configuration loading errors

### Trading Metrics
- Tiny account trade execution rate > 0 (was 0 before fix)
- Large account respects limits (no over-trading)
- Position counts accurate per-account
- Exposure calculations accurate per-account

### Operational Metrics
- Configuration update time < 5 minutes (SSM + restart)
- Service startup time < 30 seconds
- Log clarity score: 10/10 (clear account identification)

## 🚨 Known Issues & Limitations

### Issue 1: Only 2 Tiers Deployed
**Status:** Large and tiny deployed, small/medium not yet needed  
**Impact:** Medium - Can add more tiers when needed  
**Workaround:** Use large or tiny tier for now

### Issue 2: No CloudWatch Metrics per Account
**Status:** Logs only, no metrics dashboard  
**Impact:** Low - Can query logs for now  
**Future:** Add CloudWatch metrics with account dimension

### Issue 3: Manual Service Restart for Config Changes
**Status:** Must restart ECS service after SSM update  
**Impact:** Low - Rare configuration changes  
**Future:** Consider auto-reload on config change

## 📚 References

- [AWS Secrets Manager Best Practices](https://docs.aws.amazon.com/secretsmanager/latest/userguide/best-practices.html)
- [AWS SSM Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html)
- [Alpaca Account Types](https://docs.alpaca.markets/docs/about-accounts)
- `config/trading_params.json` - Account tier definitions
- `services/dispatcher/config.py` - Configuration loader implementation

---

**Priority:** HIGH - Critical for multi-account operations  
**Status:** DEPLOYED (February 3, 2026)  
**Effort:** 2-3 hours (already implemented)  
**Owner:** System deployed and verified
