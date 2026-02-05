# Multi-Account Configuration System - Design

## 🏗️ Architecture Overview

The multi-account configuration system enables independent operation of multiple Alpaca trading accounts with tier-specific risk parameters, credentials, and trading limits.

### Design Principles

1. **Separation of Concerns:** Credentials, configuration, and code are separate
2. **Account Isolation:** Each account operates independently
3. **Configuration-Driven:** Risk parameters externalized to SSM
4. **Backward Compatible:** Falls back to default config if tier-specific not found
5. **Fail-Safe:** Invalid configurations rejected at startup

## 📐 System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     ECS Task Definition                      │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Environment Variables:                                 │ │
│  │  - ACCOUNT_TIER=large                                  │ │
│  │  - RUN_MODE=LOOP                                       │ │
│  │  - EXECUTION_MODE=ALPACA_PAPER                         │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              Dispatcher Service (config.py)                  │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  load_config():                                         │ │
│  │  1. Read ACCOUNT_TIER env var                          │ │
│  │  2. Load tier-specific credentials from Secrets Mgr    │ │
│  │  3. Load tier-specific config from SSM                 │ │
│  │  4. Merge with account tier defaults                   │ │
│  │  5. Return unified config dict                         │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
            ┌───────────────┴───────────────┐
            ▼                               ▼
┌─────────────────────────┐   ┌─────────────────────────┐
│  AWS Secrets Manager    │   │  AWS SSM Parameter      │
│                         │   │  Store                  │
│  /ops-pipeline/alpaca/  │   │  /ops-pipeline/         │
│  ├── large              │   │  dispatcher_config_     │
│  │   ├── api_key       │   │  ├── large              │
│  │   ├── api_secret    │   │  ├── tiny               │
│  │   └── account_name  │   │  ├── small (future)     │
│  └── tiny               │   │  └── medium (future)    │
│      ├── api_key        │   │                         │
│      ├── api_secret     │   │  Each contains:         │
│      └── account_name   │   │  - max_exposure         │
└─────────────────────────┘   │  - max_positions        │
                              │  - max_contracts        │
                              │  - daily_loss_limit     │
                              │  - confidence_thresholds│
                              │  - allowed_actions      │
                              └─────────────────────────┘
```

## 🔧 Component Design

### 1. Configuration Loader (`config.py`)

**Responsibility:** Load and merge configuration from multiple sources

**Algorithm:**
```python
def load_config() -> Dict[str, Any]:
    # 1. Get account tier from environment
    account_tier = os.getenv('ACCOUNT_TIER', 'large')
    
    # 2. Load tier-specific credentials
    try:
        secret_name = f'ops-pipeline/alpaca/{account_tier}'
        alpaca_creds = load_secret(secret_name)
    except:
        # Fallback to default for backward compatibility
        alpaca_creds = load_secret('ops-pipeline/alpaca')
    
    # 3. Load tier-specific configuration
    try:
        config_name = f'/ops-pipeline/dispatcher_config_{account_tier}'
        dispatcher_config = load_ssm_parameter(config_name)
    except:
        # Fallback to default config
        dispatcher_config = load_ssm_parameter('/ops-pipeline/dispatcher_config')
    
    # 4. Get tier defaults from ACCOUNT_TIERS constant
    tier_defaults = ACCOUNT_TIERS.get(account_tier, ACCOUNT_TIERS['large'])
    
    # 5. Merge configurations (SSM overrides tier defaults)
    merged_config = {
        **tier_defaults,
        **dispatcher_config,
        'account_name': alpaca_creds['account_name'],
        'account_tier': account_tier
    }
    
    return merged_config
```

**Error Handling:**
- Invalid tier → Use 'large' as default
- Missing credentials → Fail fast (no fallback)
- Missing SSM config → Use tier defaults from code
- Invalid JSON in SSM → Fail fast with clear error

### 2. Account Tier Definitions

**Location:** `config/trading_params.json` and `services/dispatcher/config.py`

**Structure:**
```python
ACCOUNT_TIERS = {
    'tiny': {
        'max_size': 2000,           # Max account size for this tier
        'risk_pct_day': 0.15,       # 15% risk for 0-1 DTE
        'risk_pct_swing': 0.08,     # 8% risk for 7-30 DTE
        'max_contracts': 1,         # Max contracts per trade
        'min_confidence': 0.45,     # Minimum signal confidence
        'min_volume_ratio': 2.0     # Volume surge required
    },
    'large': {
        'max_size': 999999999,
        'risk_pct_day': 0.01,       # 1% risk (professional)
        'risk_pct_swing': 0.02,     # 2% risk
        'max_contracts': 10,
        'min_confidence': 0.45,
        'min_volume_ratio': 1.2
    }
}
```

**Usage:**
- Tier defaults provide baseline risk parameters
- SSM configuration can override any parameter
- Used for dynamic risk sizing calculations

### 3. SSM Configuration Schema

**Parameter Name:** `/ops-pipeline/dispatcher_config_{tier}`

**JSON Schema:**
```json
{
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
  "paper_ignore_buying_power": false,
  "max_signals_per_run": 10,
  "max_trades_per_ticker_per_day": 2,
  "lookback_window_minutes": 60,
  "processing_ttl_minutes": 10,
  "max_bar_age_seconds": 120,
  "max_feature_age_seconds": 300
}
```

**Validation Rules:**
- `max_notional_exposure` > 0
- `max_open_positions` > 0
- `max_contracts_per_trade` > 0
- `max_daily_loss` > 0
- `confidence_min_*` between 0.0 and 1.0
- `allowed_actions` is non-empty array

### 4. Secrets Manager Schema

**Secret Name:** `ops-pipeline/alpaca/{tier}`

**JSON Schema:**
```json
{
  "api_key": "PK...",
  "api_secret": "...",
  "account_name": "large-paper-account"
}
```

**Security:**
- Secrets encrypted at rest (AWS KMS)
- IAM role-based access (ECS task role)
- No secrets in code or environment variables
- Rotation supported (manual for now)

### 5. Database Schema Changes

**Table:** `dispatch_executions`

**Added Column:**
```sql
ALTER TABLE dispatch_executions 
ADD COLUMN account_name VARCHAR(50) DEFAULT 'large';

CREATE INDEX idx_dispatch_executions_account 
ON dispatch_executions(account_name);
```

**Table:** `active_positions`

**Added Column:**
```sql
ALTER TABLE active_positions 
ADD COLUMN account_name VARCHAR(50) DEFAULT 'large';

CREATE INDEX idx_active_positions_account 
ON active_positions(account_name);
```

**Purpose:** Enable per-account filtering in queries

### 6. Risk Gate Integration

**Modified Functions:**

**`get_account_state(account_name: str)`**
```python
def get_account_state(account_name: str) -> Dict[str, Any]:
    """Get current positions and exposure for specific account."""
    
    # Count open positions for this account
    position_count = db.execute("""
        SELECT COUNT(*) 
        FROM active_positions 
        WHERE status = 'open' 
        AND account_name = %s
    """, [account_name])
    
    # Calculate total exposure for this account
    total_exposure = db.execute("""
        SELECT COALESCE(SUM(notional_value), 0)
        FROM active_positions
        WHERE status = 'open'
        AND account_name = %s
    """, [account_name])
    
    return {
        'position_count': position_count,
        'total_exposure': total_exposure
    }
```

**`evaluate_all_gates(recommendation, config, account_name)`**
```python
def evaluate_all_gates(recommendation, config, account_name):
    """Evaluate all risk gates for a recommendation."""
    
    # Get account-specific state
    account_state = get_account_state(account_name)
    
    # Check position limit (per-account)
    if account_state['position_count'] >= config['max_open_positions']:
        return False, "Position limit reached for this account"
    
    # Check exposure limit (per-account)
    if account_state['total_exposure'] >= config['max_notional_exposure']:
        return False, "Exposure limit reached for this account"
    
    # ... other gates
    
    return True, "All gates passed"
```

## 🔄 Data Flow

### Startup Sequence

```
1. ECS Task starts
   └─> Read ACCOUNT_TIER environment variable
   
2. Load Configuration (config.py)
   ├─> Load tier-specific credentials from Secrets Manager
   ├─> Load tier-specific config from SSM Parameter Store
   ├─> Merge with tier defaults from ACCOUNT_TIERS
   └─> Validate configuration
   
3. Initialize Broker
   ├─> Connect to Alpaca API with tier credentials
   ├─> Verify account access
   ├─> Log account name, tier, and buying power
   └─> Ready to trade
   
4. Main Loop
   └─> Process recommendations with account-specific limits
```

### Trade Execution Flow

```
1. Signal Engine generates recommendation
   └─> Stored in recommendations table (no account filter)
   
2. Dispatcher fetches recommendations
   └─> SELECT * FROM recommendations WHERE status = 'pending'
   
3. For each recommendation:
   ├─> Load account-specific config
   ├─> Get account state (filtered by account_name)
   │   ├─> Count open positions for this account
   │   └─> Calculate exposure for this account
   ├─> Evaluate risk gates (account-specific limits)
   │   ├─> Position limit check
   │   ├─> Exposure limit check
   │   ├─> Daily loss check
   │   └─> Confidence threshold check
   ├─> If gates pass:
   │   ├─> Calculate position size (account-specific)
   │   ├─> Submit order to Alpaca (account-specific credentials)
   │   └─> Record execution (with account_name)
   └─> If gates fail:
       └─> Mark recommendation as rejected (with reason)
```

## 🎯 Design Decisions

### Decision 1: SSM vs. Secrets Manager for Config

**Chosen:** SSM Parameter Store for configuration, Secrets Manager for credentials

**Rationale:**
- SSM: Free, versioned, easy to update, good for non-sensitive config
- Secrets Manager: Encrypted, rotation support, audit trail, good for credentials
- Separation of concerns: config vs. secrets

**Alternatives Considered:**
- All in Secrets Manager: More expensive, overkill for non-sensitive config
- All in SSM: Less secure for credentials, no rotation support
- Environment variables: Not dynamic, requires redeployment

### Decision 2: Tier-Specific vs. Shared Configuration

**Chosen:** Separate SSM parameter per tier

**Rationale:**
- Clear separation of concerns
- Easy to update one tier without affecting others
- Prevents accidental cross-tier configuration
- Supports different risk profiles per tier

**Alternatives Considered:**
- Single config with tier sections: More complex parsing, error-prone
- Hardcoded in code: Not dynamic, requires redeployment
- Database table: Overkill, adds complexity

### Decision 3: Environment Variable for Tier Selection

**Chosen:** `ACCOUNT_TIER` environment variable in ECS task definition

**Rationale:**
- Simple and explicit
- Set once at deployment time
- No runtime tier switching (safer)
- Easy to verify in logs

**Alternatives Considered:**
- Auto-detect from credentials: Fragile, requires API call
- Command-line argument: More complex, not standard for ECS
- Config file: Requires mounting, more complex

### Decision 4: Fallback to Default Config

**Chosen:** Fall back to default config if tier-specific not found

**Rationale:**
- Backward compatibility with existing deployments
- Graceful degradation
- Easier migration path

**Alternatives Considered:**
- Fail fast: More strict, but breaks existing deployments
- Use tier defaults only: Loses SSM configuration capability

### Decision 5: Account Name in Database

**Chosen:** Add `account_name` column to relevant tables

**Rationale:**
- Enables per-account filtering in queries
- Simple and explicit
- Indexed for performance
- Supports future multi-account features

**Alternatives Considered:**
- Separate tables per account: Too complex, hard to maintain
- Account ID instead of name: Less readable in logs
- No database changes: Can't filter by account

## 🔒 Security Considerations

### Credential Management
- ✅ Credentials stored in AWS Secrets Manager (encrypted at rest)
- ✅ IAM role-based access (ECS task role only)
- ✅ No credentials in code, logs, or environment variables
- ✅ Separate credentials per account (no sharing)

### Configuration Security
- ✅ SSM parameters use IAM for access control
- ✅ Configuration validated at startup
- ✅ Invalid configurations rejected (fail-fast)
- ⚠️ SSM parameters not encrypted (non-sensitive data)

### Account Isolation
- ✅ Database queries filter by account_name
- ✅ Risk gates evaluate per-account
- ✅ No cross-account position counting
- ✅ Separate Alpaca API connections per account

## 📊 Performance Considerations

### Configuration Loading
- **Frequency:** Once at startup
- **Latency:** ~200ms (Secrets Manager + SSM)
- **Caching:** Config cached in memory for service lifetime
- **Impact:** Negligible (startup only)

### Database Queries
- **Added Overhead:** `WHERE account_name = %s` filter
- **Index:** `idx_dispatch_executions_account` and `idx_active_positions_account`
- **Performance:** < 5ms per query (indexed)
- **Impact:** Negligible

### Risk Gate Evaluation
- **Added Overhead:** Account-specific state lookup
- **Frequency:** Per recommendation (every 1-5 minutes)
- **Latency:** < 10ms (indexed queries)
- **Impact:** Negligible

## 🧪 Testing Strategy

### Unit Tests

**Test:** `test_load_config_with_tier()`
- Mock Secrets Manager and SSM
- Verify tier-specific config loaded
- Verify fallback to default works

**Test:** `test_get_account_state_filtering()`
- Insert positions for multiple accounts
- Verify query returns only specified account
- Verify counts and exposure calculations

**Test:** `test_risk_gates_per_account()`
- Set up positions for account A
- Evaluate gates for account B
- Verify account B not affected by account A

### Integration Tests

**Test:** `test_multi_account_deployment()`
- Deploy large and tiny services
- Verify each loads correct config
- Verify each connects to correct Alpaca account
- Verify no cross-account interference

**Test:** `test_config_update_without_redeployment()`
- Update SSM parameter
- Restart service
- Verify new config loaded
- Verify no code changes needed

### End-to-End Tests

**Test:** `test_large_account_trading()`
- Generate recommendation
- Verify large account executes with large limits
- Verify position recorded with account_name='large'

**Test:** `test_tiny_account_trading()`
- Generate recommendation
- Verify tiny account executes with tiny limits
- Verify position recorded with account_name='tiny'

**Test:** `test_account_isolation()`
- Large account hits position limit
- Verify tiny account can still trade
- Verify no cross-account effects

## 📈 Monitoring & Observability

### Startup Logs
```
INFO: Account tier: large
INFO: Loaded tier-specific config: /ops-pipeline/dispatcher_config_large
INFO: Loaded credentials for account: large-paper-account
INFO: Connected to Alpaca: Account PA3PBOQAH7ZY, Buying power: $209,234.50
INFO: Risk limits: Max exposure $10,000, Max positions 5, Max contracts 10
```

### Runtime Logs
```
INFO: Evaluating risk gates for account: large
INFO: Account state: Positions 3/5, Exposure $6,500/$10,000
INFO: All gates passed for account: large
INFO: Order submitted for account: large, Symbol: AAPL260207C00180000
```

### Metrics (Future)
- `dispatcher.positions.count` (dimension: account_name)
- `dispatcher.exposure.dollars` (dimension: account_name)
- `dispatcher.trades.executed` (dimension: account_name)
- `dispatcher.gates.failed` (dimension: account_name, reason)

## 🚀 Deployment Strategy

### Phase 1: Large Account (Completed)
1. Create `/ops-pipeline/dispatcher_config_large` in SSM
2. Update `config.py` to load tier-specific config
3. Build and push Docker image
4. Register new task definition with `ACCOUNT_TIER=large`
5. Update `dispatcher-service` to use new task definition
6. Verify logs show correct config loaded

### Phase 2: Tiny Account (Completed)
1. Create `ops-pipeline/alpaca/tiny` secret
2. Create `/ops-pipeline/dispatcher_config_tiny` in SSM
3. Register new task definition with `ACCOUNT_TIER=tiny`
4. Create `dispatcher-tiny-service` ECS service
5. Verify logs show correct config loaded
6. Verify tiny account can execute trades

### Phase 3: Small/Medium Accounts (Future)
1. Create credentials in Secrets Manager
2. Create SSM configurations
3. Register task definitions
4. Create ECS services
5. Verify isolation and limits

## 📚 References

- [AWS Secrets Manager](https://docs.aws.amazon.com/secretsmanager/)
- [AWS SSM Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html)
- [ECS Task Definitions](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definitions.html)
- [Alpaca API Authentication](https://docs.alpaca.markets/docs/authentication)

---

**Status:** IMPLEMENTED & DEPLOYED  
**Date:** February 3, 2026  
**Version:** 1.0
