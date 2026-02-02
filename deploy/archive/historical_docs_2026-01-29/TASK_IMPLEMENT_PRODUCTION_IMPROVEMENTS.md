# Task: Implement Production Options Trading Improvements

**Created:** 2026-01-29  
**Priority:** P0 - Critical for small account trading  
**Estimated Time:** Phase 1 (45 min), Phase 2 (2 hours), Phase 3+ (8 hours)  
**Prerequisites:** Options API working (dispatcher rev 13), Phase 17 deployed (position-manager rev 2)

---

## Mission

Implement production-grade improvements to options trading system to support:
1. **Small accounts** ($1,000) with aggressive growth sizing
2. **Professional risk management** for all account sizes
3. **Live trading readiness** (not just paper)

---

## Current State (Jan 29, 2026)

### What's Working ✅
- Options API fetching 165+ contracts
- Dispatcher revision 13 deployed
- Got ALPACA_PAPER execution
- Phase 17 bar capture active
- All 9 services running

### What Needs Improvement 🔧
1. **Position sizing:** 5-10% is too aggressive for large accounts, too conservative for small
2. **Liquidity validation:** Missing OI, volume, premium floor; wrong spread calc
3. **Contract selection:** Picks closest, not best quality
4. **Exit logic:** -2% will chop options traders to death
5. **Momentum:** distance_sma20 is late entry proxy
6. **Chop filter:** Missing - will trade in ranging markets
7. **Option monitoring:** Need to verify fetching option quotes

---

## Implementation Phases

### Phase 1: Critical Safety (45 minutes) - THIS TASK

**Changes:**
1. Account tier detection (4 tiers: tiny/small/medium/large)
2. Dynamic position sizing (25% for $1K → 1% for $100K)
3. Contract count hard caps (2 for tiny, 10 for large)
4. Fix spread calculation (use mid, not bid)
5. Add minimum premium check ($0.30+)

**Files to Modify:**
- `services/dispatcher/config.py` - Add tier system
- `services/dispatcher/alpaca/options.py` - Update sizing + validation
- `config/trading_params.json` - Add tier configuration

**Expected Result:**
- $1,000 account: 1-2 contracts per trade (25% risk)
- $10,000 account: 3-5 contracts (8-12% risk)
- $100,000 account: 5-50 contracts (1-2% risk)

### Phase 2: Quality Improvements (2 hours) - FUTURE TASK

**Changes:**
6. Add OI ≥ 500 and volume ≥ 200 checks
7. Contract quality scoring (spread + OI + volume + delta)
8. Select best quality, not just closest strike
9. Add chop filter (SMA slope detection)
10. Improve momentum (ret_5m, ret_15m indicators)

**Files:**
- `services/dispatcher/alpaca/options.py` - Scoring function
- `services/signal_engine_1m/rules.py` - Chop filter
- `services/feature_computer_1m/features.py` - Momentum indicators

### Phase 3: Advanced (3 hours) - FUTURE TASK

**Changes:**
11. Exit logic rewrite (underlying-based or -25-40%)
12. IV Rank calculation and filtering
13. Trailing stops implementation
14. Time-based exits (21 DTE for shorts)
15. Portfolio Greeks tracking

**Files:**
- `services/position_manager/monitor.py` - Exit conditions
- `services/position_manager/exits.py` - Exit execution
- New: `services/dispatcher/greeks.py` - Portfolio Greeks

### Phase 4: Professional (4 hours) - FUTURE TASK

**Changes:**
16. Kelly criterion sizing
17. ATR-adjusted sizing  
18. Auto-rolling positions
19. Scaling in/out (50% entry, 50% add)
20. Partial exits (50-75% at first target)

---

## Detailed Implementation Guide - Phase 1

### Step 1: Add Account Tier System (15 min)

**File:** `services/dispatcher/config.py`

**Add at top of file:**
```python
# Account size tiers for dynamic risk management
ACCOUNT_TIERS = {
    'tiny': {
        'max_size': 2000,
        'risk_pct_day': 0.25,      # 25% - aggressive for growth
        'risk_pct_swing': 0.15,    # 15%
        'max_contracts': 2,
        'min_confidence': 0.70,     # Higher bar
        'min_volume_ratio': 2.0     # Volume surge required
    },
    'small': {
        'max_size': 5000,
        'risk_pct_day': 0.12,      # 12%
        'risk_pct_swing': 0.08,    # 8%
        'max_contracts': 3,
        'min_confidence': 0.65,
        'min_volume_ratio': 1.8
    },
    'medium': {
        'max_size': 25000,
        'risk_pct_day': 0.04,      # 4%
        'risk_pct_swing': 0.06,    # 6%
        'max_contracts': 5,
        'min_confidence': 0.55,
        'min_volume_ratio': 1.5
    },
    'large': {
        'max_size': 999999999,
        'risk_pct_day': 0.01,      # 1% - professional
        'risk_pct_swing': 0.02,    # 2%
        'max_contracts': 10,
        'min_confidence': 0.45,
        'min_volume_ratio': 1.2
    }
}

def get_account_tier(buying_power: float) -> tuple:
    """
    Determine account tier based on buying power.
    Returns: (tier_name, tier_config)
    """
    for tier_name in ['tiny', 'small', 'medium', 'large']:
        tier_config = ACCOUNT_TIERS[tier_name]
        if buying_power <= tier_config['max_size']:
            return tier_name, tier_config
    
    # Default to large
    return 'large', ACCOUNT_TIERS['large']
```

### Step 2: Update Position Sizing (15 min)

**File:** `services/dispatcher/alpaca/options.py`

**Find function `calculate_position_size()` around line 269**

**Replace entire function:**
```python
def calculate_position_size(
    option_price: float,
    account_buying_power: float,
    max_risk_pct: float = 5.0,  # Deprecated - will use tier
    strategy: str = 'day_trade'
) -> Tuple[int, float, str]:
    """
    Calculate optimal position size with account tier awareness.
    
    CRITICAL CHANGE: Now uses account tiers!
    - $1K account: 25% per day trade (aggressive growth)
    - $100K account: 1% per day trade (professional)
    
    Args:
        option_price: Premium per contract (e.g., $2.50)
        account_buying_power: Available capital
        max_risk_pct: DEPRECATED (now uses tier)
        strategy: 'day_trade' or 'swing_trade'
    
    Returns:
        Tuple of (num_contracts, total_cost, rationale)
    """
    # Import here to avoid circular dependency
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import get_account_tier
    
    # Get appropriate tier for this account size
    tier_name, tier_config = get_account_tier(account_buying_power)
    
    # Select risk % based on strategy
    if strategy == 'day_trade':
        risk_pct = tier_config['risk_pct_day']
    elif strategy == 'swing_trade':
        risk_pct = tier_config['risk_pct_swing']
    else:
        # Default to conservative
        risk_pct = tier_config['risk_pct_swing'] * 0.5
    
    # Calculate max dollars to risk
    max_risk_dollars = account_buying_power * risk_pct
    
    # Each contract costs: premium × 100 shares
    cost_per_contract = option_price * 100
    
    # Calculate number of contracts
    num_contracts = int(max_risk_dollars / cost_per_contract)
    
    # Apply tier-specific hard cap
    max_contracts = tier_config['max_contracts']
    num_contracts = min(num_contracts, max_contracts)
    
    # Minimum 1 contract, but only if we can afford it
    if num_contracts == 0 and cost_per_contract <= account_buying_power:
        num_contracts = 1
    
    total_cost = num_contracts * cost_per_contract
    
    rationale = (
        f"Tier: {tier_name}, "
        f"Strategy: {strategy}, "
        f"Risk: {risk_pct*100:.1f}% of ${account_buying_power:.0f} = ${max_risk_dollars:.0f}, "
        f"Premium: ${option_price:.2f} × 100 = ${cost_per_contract:.0f}/contract, "
        f"Contracts: {num_contracts} (cap: {max_contracts}), "
        f"Total: ${total_cost:.0f}"
    )
    
    return num_contracts, total_cost, rationale
```

### Step 3: Fix Spread Calculation (10 min)

**File:** `services/dispatcher/alpaca/options.py`

**Find function `validate_option_liquidity()` around line 234**

**Replace with:**
```python
def validate_option_liquidity(
    contract: Dict[str, Any],
    min_volume: int = 100,
    max_spread_pct: float = 10.0
) -> Tuple[bool, str]:
    """
    Validate option contract liquidity.
    
    CRITICAL CHANGES:
    - Fixed spread calc: use MID not BID as denominator
    - Added minimum premium check
    - Stricter for small accounts
    
    Returns:
        Tuple of (is_valid, reason)
    """
    # Check bid-ask spread (PRIMARY liquidity indicator)
    bid = float(contract.get('bid', 0))
    ask = float(contract.get('ask', 0))
    
    if bid <= 0 or ask <= 0:
        return False, f"No valid bid/ask prices (bid={bid}, ask={ask})"
    
    # CRITICAL FIX: Use MID not BID for spread calc
    mid = (bid + ask) / 2
    spread_pct = ((ask - bid) / mid) * 100
    
    if spread_pct > max_spread_pct:
        return False, f"Spread too wide: {spread_pct:.1f}% > {max_spread_pct}%"
    
    # Minimum premium check (avoid lottery tickets)
    min_premium = 0.30  # $0.30 per share = $30 per contract
    if mid < min_premium:
        return False, f"Premium too low: ${mid:.2f} < ${min_premium:.2f} (likely worthless)"
    
    # Check expiration
    expiration = contract.get('expiration_date')
    if expiration:
        exp_date = datetime.strptime(expiration, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        if exp_date < datetime.now(timezone.utc):
            return False, "Contract expired"
    
    return True, "OK"
```

### Step 4: Update Config File (5 min)

**File:** `config/trading_params.json`

**Add new section:**
```json
{
  "existing_params": "...",
  
  "account_tiers": {
    "enabled": true,
    "tiers": {
      "tiny": {
        "max_size": 2000,
        "risk_pct_day": 0.25,
        "risk_pct_swing": 0.15,
        "max_contracts": 2
      },
      "small": {
        "max_size": 5000,
        "risk_pct_day": 0.12,
        "risk_pct_swing": 0.08,
        "max_contracts": 3
      },
      "medium": {
        "max_size": 25000,
        "risk_pct_day": 0.04,
        "risk_pct_swing": 0.06,
        "max_contracts": 5
      },
      "large": {
        "risk_pct_day": 0.01,
        "risk_pct_swing": 0.02,
        "max_contracts": 10
      }
    }
  },
  
  "liquidity_thresholds": {
    "max_spread_pct": 10.0,
    "min_premium": 0.30,
    "min_open_interest": 500,
    "min_volume": 200
  }
}
```

---

## Testing Phase 1 Changes

### Test 1: Account Tier Detection
```python
# Test in Python
from services.dispatcher.config import get_account_tier

# Test each tier
assert get_account_tier(1000)[0] == 'tiny'
assert get_account_tier(1000)[1]['risk_pct_day'] == 0.25

assert get_account_tier(3000)[0] == 'small'
assert get_account_tier(3000)[1]['risk_pct_day'] == 0.12

print("✅ Tier detection working")
```

### Test 2: Position Sizing
```python
from services.dispatcher.alpaca.options import calculate_position_size

# Test $1K account
contracts, cost, reason = calculate_position_size(
    option_price=2.50,
    account_buying_power=1000,
    strategy='day_trade'
)

print(f"$1K account: {contracts} contracts, ${cost:.0f} total")
# Expected: 1-2 contracts (~$250-500)

# Test $100K account
contracts, cost, reason = calculate_position_size(
    option_price=2.50,
    account_buying_power=100000,
    strategy='day_trade'
)

print(f"$100K account: {contracts} contracts, ${cost:.0f} total")
# Expected: 4-10 contracts (~$1,000-2,500)
```

### Test 3: Spread Calculation
```python
from services.dispatcher.alpaca.options import validate_option_liquidity

contract = {
    'bid': 2.50,
    'ask': 2.55,
    'expiration_date': '2026-02-15'
}

valid, reason = validate_option_liquidity(contract)
print(f"Valid: {valid}, Reason: {reason}")
# Expected: Valid=True, spread ~2% (was incorrectly calculating as 2% before)
```

---

## Deployment Process (From Today's Learning)

### Build & Deploy Dispatcher

**1. Build Docker image:**
```bash
cd /home/nflos/workplace/inbound_aigen/services/dispatcher
docker build --no-cache -t ops-pipeline/dispatcher:tier-sizing .
```

**CRITICAL:** Always use `--no-cache` or Docker will use cached old code!

**2. Push to ECR:**
```bash
aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin 160027201036.dkr.ecr.us-west-2.amazonaws.com

docker tag ops-pipeline/dispatcher:tier-sizing 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/dispatcher:tier-sizing

docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/dispatcher:tier-sizing
```

**3. Get new image digest:**
```bash
# From push output, copy the sha256:XXXXX digest
```

**4. Update task definition:**
```bash
# Edit deploy/dispatcher-task-definition.json
# Change image line to new SHA256

# Register new revision
aws ecs register-task-definition --cli-input-json file:///home/nflos/workplace/inbound_aigen/deploy/dispatcher-task-definition.json --region us-west-2 --query 'taskDefinition.revision'

# Should return: 14 (or next number)
```

**5. Update scheduler:**
```bash
aws scheduler update-schedule \
  --name ops-pipeline-dispatcher \
  --region us-west-2 \
  --schedule-expression "rate(1 minute)" \
  --flexible-time-window Mode=OFF \
  --target '{
    "Arn": "arn:aws:ecs:us-west-2:160027201036:cluster/ops-pipeline-cluster",
    "RoleArn": "arn:aws:iam::160027201036:role/ops-pipeline-eventbridge-ecs-role",
    "EcsParameters": {
      "TaskDefinitionArn": "arn:aws:ecs:us-west-2:160027201036:task-definition/ops-pipeline-dispatcher:14",
      "LaunchType": "FARGATE",
      "NetworkConfiguration": {
        "awsvpcConfiguration": {
          "Subnets": ["subnet-0c182a149eeef918a"],
          "SecurityGroups": ["sg-0cd16a909f4e794ce"],
          "AssignPublicIp": "ENABLED"
        }
      }
    },
    "RetryPolicy": {
      "MaximumEventAgeInSeconds": 86400,
      "MaximumRetryAttempts": 185
    }
  }'
```

**6. Verify deployment:**
```bash
# Check scheduler using new revision
aws scheduler get-schedule --name ops-pipeline-dispatcher --region us-west-2 --query 'Target.EcsParameters.TaskDefinitionArn'

# Wait ~60 seconds, then check logs
aws logs tail /ecs/ops-pipeline/dispatcher --region us-west-2 --since 2m | grep -E "(Tier:|contracts)"
```

---

## Verification & Testing

### After Phase 1 Deployment

**Check 1: Verify tier detection in logs**
```bash
aws logs tail /ecs/ops-pipeline/dispatcher --region us-west-2 --since 5m | grep "Tier:"

# Should see something like:
# "Tier: large, Strategy: day_trade, Risk: 1.0% of $182000 = $1820"
```

**Check 2: Verify contract counts**
```bash
# Query recent executions
python3 << 'EOF'
import boto3, json
client = boto3.client('lambda', region_name='us-west-2')
r = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'sql': """
        SELECT ticker, contracts, notional, simulated_ts::text
        FROM dispatch_executions
        WHERE simulated_ts > NOW() - INTERVAL '10 minutes'
        ORDER BY simulated_ts DESC
        LIMIT 5
    """})
)
print(json.loads(json.load(r['Payload'])['body']))
EOF

# For $182K account, should see 4-10 contracts per trade (1-2% sizing)
# For $1K account, should see 1-2 contracts (25% sizing)
```

**Check 3: Test with different account sizes**
```bash
# Can test by temporarily modifying Alpaca paper account balance
# Or by checking logs to see tier detection working
```

---

## Important Notes

### AWS Credentials
```bash
# If expired, refresh with:
ada cred update --account 160027201036 --role IibsAdminAccess-DO-NOT-DELETE --provider conduit --once
```

### Database Queries
**Always use correct format:**
```python
# CORRECT:
Payload=json.dumps({'sql': 'SELECT...'})
result.get('rows', [])

# WRONG:
Payload=json.dumps({'query': 'SELECT...'})
result.get('results', [])
```

### Docker Build
**Always use --no-cache** or it will use old cached code!

### Verification
After every deployment:
1. Check scheduler updated to new revision
2. Wait 60-90 seconds for next run
3. Check logs for new behavior
4. Query database to verify results

---

## Success Criteria - Phase 1

**Must See:**
1. ✅ "Tier: tiny/small/medium/large" in dispatcher logs
2. ✅ Contract counts match tier (2 for tiny, 10 for large)
3. ✅ Risk % matches tier (25% for tiny, 1% for large)
4. ✅ No "can't afford" errors for reasonable options
5. ✅ Spread calculated correctly (using mid)
6. ✅ Minimum premium enforced ($0.30+)

**Logs Should Show:**
```
Tier: large, Strategy: day_trade, Risk: 1.0% of $182000 = $1820
Premium: $2.50 × 100 = $250/contract
Contracts: 7 (cap: 10)
Total: $1750
```

---

## Files Reference

### Critical Files for Phase 1:
- `services/dispatcher/config.py` - Tier system
- `services/dispatcher/alpaca/options.py` - Sizing + validation
- `services/dispatcher/alpaca/broker.py` - Calls sizing function
- `config/trading_params.json` - Configuration
- `deploy/dispatcher-task-definition.json` - Deployment

### Documentation:
- `deploy/SMALL_ACCOUNT_STRATEGY.md` - Complete strategy
- `deploy/PRODUCTION_IMPROVEMENTS_NEEDED.md` - All improvements
- `deploy/HOW_OPTIONS_TRADING_WORKS.md` - Decision flow

### Verification Scripts:
- `scripts/query_db.py` - Database queries
- `AI_AGENT_START_HERE.md` - Query format reference

---

## Common Issues & Solutions

**Issue 1: Docker uses cached code**
→ Solution: Use `--no-cache` flag

**Issue 2: Scheduler not updating**
→ Solution: Check RoleArn matches existing (ops-pipeline-eventbridge-ecs-role)

**Issue 3: Can't query database**
→ Solution: Use 'sql' key, not 'query'; expect 'rows' not 'results'

**Issue 4: Logs show old behavior**
→ Solution: Wait 60+ seconds for next scheduled run, old tasks may still be running

---

## Estimated Timeline

**Phase 1 Implementation:** 45 minutes
- Code changes: 30 min
- Build & deploy: 10 min  
- Verification: 5 min

**Phase 2-4:** Future sessions (10 hours total)

**Total to production-ready:** ~11 hours spread across multiple sessions

---

## Next Task After This

After Phase 1 complete, next agent should:
1. Implement Phase 2 (OI checks, quality scoring)
2. Test with various account sizes
3. Monitor performance for 1-2 weeks
4. Then implement Phase 3 (exits, IV Rank)

**Critical:** Don't rush to live trading. Paper test each phase for at least 1 week.

---

## Questions to Answer

1. What account size will you start with? ($1K, $5K, $100K?)
2. Preferred exit style: Underlying-based or wider % on option price?
3. Risk tolerance: Conservative (0.5%), balanced (1.0%), or aggressive (1.5%)?

**Based on answers, may need to adjust tier thresholds!**
