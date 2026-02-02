# Next Session: Implement Phases 3-4 to Reach 100%

**Created:** 2026-01-29  
**Estimated Time:** 5-7 hours  
**Current Status:** 85% Complete (B+ grade)  
**Goal:** Reach 100% (A+ grade)

---

## What's Already Done (Don't Redo!)

### Phases 1-2: COMPLETE ✅
- Account tier system
- Dynamic position sizing
- Quality-based contract selection
- Spread calculation fix
- Volume validation

### Multi-Account: COMPLETE ✅
- 2 accounts trading (tiny $1K, large $121K)
- Both verified working
- Separate schedulers

### Position Manager: DEPLOYED ✅
- Revision 3 active
- Scheduled every 5 minutes
- Will monitor META position

### Current Accounts Working:
- Large: PKHE57Z4BKSIUQLTNQQKXOWEN7 (ops-pipeline/alpaca)
- Tiny: PKRTAIU5VRKXIAOCZHFIGK3CT7 (ops-pipeline/alpaca/tiny)

---

## Phase 3: Critical Improvements (2-3 hours)

### Part 1: Fix Exit Logic for Options (1 hour)

**Problem:** Exit targets use stock prices, but we trade options

**Current Code:** `services/position_manager/monitor.py`
```python
# Lines 60-70: check_exit_conditions()
if current_price <= stop_loss:  # Stock price
    exit()
if current_price >= take_profit:  # Stock price
    exit()
```

**New Code Needed:**
```python
def check_exit_conditions_options(position: Dict) -> List:
    """
    Option-specific exit logic
    """
    exits = []
    
    # Get current option price from Alpaca
    current_option_price = get_option_price(position['option_symbol'])
    entry_option_price = position['premium_paid']
    
    option_pnl_pct = ((current_option_price / entry_option_price) - 1) * 100
    
    # Exit 1: Option profit target (+50%)
    if option_pnl_pct >= 50:
        exits.append({'reason': 'option_profit_target', 'priority': 1})
    
    # Exit 2: Option stop loss (-25%)
    if option_pnl_pct <= -25:
        exits.append({'reason': 'option_stop_loss', 'priority': 1})
    
    # Exit 3: Underlying moved enough
    current_stock = get_stock_price(position['ticker'])
    entry_stock = position['entry_underlying_price']  # Need to store this!
    
    stock_move_pct = ((current_stock / entry_stock) - 1) * 100
    
    if position['instrument_type'] == 'CALL' and stock_move_pct >= 3:
        exits.append({'reason': 'underlying_target_call', 'priority': 1})
    elif position['instrument_type'] == 'PUT' and stock_move_pct <= -3:
        exits.append({'reason': 'underlying_target_put', 'priority': 1})
    
    # Exit 4: Time decay risk (theta burn)
    days_to_expiry = (position['expiration_date'] - datetime.now().date()).days
    
    if days_to_expiry <= 7 and option_pnl_pct < 20:
        exits.append({'reason': 'theta_decay_risk', 'priority': 2})
    
    return sorted(exits, key=lambda x: x['priority'])
```

**Testing:**
```python
# Test with META position:
entry_option = $17.15
current_option = $35 (estimated)
pnl = (+103%)

# Should trigger: option_profit_target (+50% exceeded)
# Exits immediately
```

### Part 2: Add Trailing Stops (1 hour)

**New Code:** `services/position_manager/monitor.py`

```python
def check_trailing_stop(position: Dict) -> Optional[Dict]:
    """
    Trailing stop: Lock in 75% of peak gains
    """
    current_price = position['current_price']
    peak_price = position.get('peak_price', current_price)
    entry_price = position['entry_price']
    
    # Update peak if new high
    if current_price > peak_price:
        peak_price = current_price
        db.update_position_peak(position['id'], peak_price)
    
    # Calculate trailing stop
    # Lock in 75% of gains from peak
    peak_gain = peak_price - entry_price
    trailing_stop = peak_price - (peak_gain * 0.25)
    
    if current_price <= trailing_stop:
        return {
            'reason': 'trailing_stop',
            'priority': 1,
            'message': f'Trailed from peak ${peak_price:.2f}, stop ${trailing_stop:.2f}'
        }
    
    return None
```

**Add to database:**
```sql
-- Migration 013: Add trailing stop support
ALTER TABLE active_positions 
ADD COLUMN IF NOT EXISTS peak_price DECIMAL(12, 4),
ADD COLUMN IF NOT EXISTS trailing_stop_price DECIMAL(12, 4);
```

**Testing:**
```python
# META example:
entry = $17.15
peak = $40 (if it went higher)
current = $35
trailing_stop = $40 - (($40 - $17.15) × 0.25) = $34.29

# If drops to $34.29 → Exit
# Locks in $17.14 gain (100% profit)
```

### Part 3: IV Rank Calculation (1 hour)

**New Code:** `services/feature_computer_1m/features.py`

```python
def calculate_iv_rank(ticker: str, current_iv: float) -> float:
    """
    IV Rank = (Current IV - 52-week Low IV) / (52-week High IV - 52-week Low IV)
    
    Returns: 0.0 to 1.0 (0 = lowest, 1 = highest IV in year)
    """
    # Get 52-week IV history
    iv_history = db.get_iv_history(ticker, days=252)
    
    if not iv_history or len(iv_history) < 30:
        return 0.5  # Unknown, assume mid-range
    
    iv_high = max(iv_history)
    iv_low = min(iv_history)
    
    if iv_high == iv_low:
        return 0.5
    
    iv_rank = (current_iv - iv_low) / (iv_high - iv_low)
    
    return max(0.0, min(1.0, iv_rank))
```

**Add to options.py:**
```python
def validate_iv_rank(contract: Dict, ticker: str) -> Tuple[bool, str]:
    """
    Don't buy options when IV is expensive
    """
    current_iv = contract.get('implied_volatility', 0)
    
    # Calculate IV Rank
    iv_rank = calculate_iv_rank(ticker, current_iv)
    
    # Reject if IV is in top 20% of year (expensive)
    if iv_rank > 0.80:
        return False, f"IV Rank too high: {iv_rank:.2f} > 0.80 (options expensive)"
    
    return True, f"IV Rank OK: {iv_rank:.2f}"
```

**Testing:**
```python
# Example:
META current_iv = 0.45
META 52-week range: 0.20 to 0.60

iv_rank = (0.45 - 0.20) / (0.60 - 0.20) = 0.625 (62nd percentile)
# OK to trade (< 80%)
```

---

## Phase 4: Professional Features (3-4 hours)

### Part 1: Kelly Criterion (1 hour)

**Theory:**
```
Kelly % = (Win Rate × Avg Win - Loss Rate × Avg Loss) / Avg Win

Example:
Win Rate = 60%
Avg Win = +40%
Loss Rate = 40%  
Avg Loss = -20%

Kelly = (0.60 × 0.40 - 0.40 × 0.20) / 0.40
      = (0.24 - 0.08) / 0.40
      = 0.40 = 40%

But use fraction: 40% × 0.5 = 20% (safer)
```

**Implementation:**
```python
def calculate_kelly_size(
    win_rate: float,
    avg_win_pct: float,
    avg_loss_pct: float
) -> float:
    """
    Calculate Kelly criterion position size
    Returns: Optimal % of capital to risk
    """
    if avg_win_pct <= 0:
        return 0.0
    
    kelly = (win_rate * avg_win_pct - (1 - win_rate) * abs(avg_loss_pct)) / avg_win_pct
    
    # Use fractional Kelly (50% of full Kelly for safety)
    return max(0, min(kelly * 0.5, 0.25))  # Cap at 25%
```

**Get historical stats:**
```sql
-- Calculate from ai_option_trades
SELECT 
    account_tier,
    COUNT(*) FILTER (WHERE exit_pnl > 0) / COUNT(*)::float as win_rate,
    AVG(exit_pnl_pct) FILTER (WHERE exit_pnl > 0) as avg_win,
    AVG(exit_pnl_pct) FILTER (WHERE exit_pnl < 0) as avg_loss
FROM ai_option_trades
WHERE closed_at > NOW() - INTERVAL '30 days'
GROUP BY account_tier;
```

### Part 2: Partial Exits (1 hour)

**Implementation:**
```python
def check_partial_exit(position: Dict) -> Optional[Dict]:
    """
    Take 50% off at 50% profit
    Take another 25% at 75% profit
    Let 25% ride
    """
    pnl_pct = position['current_pnl_percent']
    quantity = position['quantity']
    
    # Track how much already exited
    original_qty = position.get('original_quantity', quantity)
    pct_remaining = quantity / original_qty
    
    # First partial: 50% at +50% profit
    if pnl_pct >= 50 and pct_remaining > 0.75:
        return {
            'type': 'partial',
            'quantity': original_qty * 0.50,
            'reason': 'first_profit_target',
            'message': 'Taking 50% off at +50% profit'
        }
    
    # Second partial: 25% more at +75% profit
    if pnl_pct >= 75 and pct_remaining > 0.35:
        return {
            'type': 'partial',
            'quantity': original_qty * 0.25,
            'reason': 'second_profit_target',
            'message': 'Taking 25% off at +75% profit'
        }
    
    return None
```

**Example:**
```
META position:
Entry: 6 contracts @ $17.15
At $25.75 (+50%): Sell 3 contracts, keep 3
At $30 (+75%): Sell 1.5 contracts, keep 1.5
Final 1.5 rides to stop/target
```

### Part 3: Auto-Rolling (1.5 hours)

**Implementation:**
```python
def check_rolling_opportunity(position: Dict) -> Optional[Dict]:
    """
    Roll positions approaching expiration
    """
    days_to_expiry = (position['expiration_date'] - datetime.now().date()).days
    
    # Roll threshold
    if position['instrument_type'] in ('CALL', 'PUT'):
        # For long options: roll at 21 DTE
        if days_to_expiry <= 21 and position['current_pnl_percent'] > -10:
            return {
                'action': 'roll',
                'reason': 'approaching_expiration',
                'target_expiration': position['expiration_date'] + timedelta(days=30)
            }
    
    return None

def execute_roll(position: Dict, target_expiration: date):
    """
    Close current position and open new one at later expiration
    """
    # 1. Close current position
    close_order = alpaca.close_position(position['option_symbol'])
    
    # 2. Find new contract at target_expiration
    new_contract = find_contract_at_expiration(
        ticker=position['ticker'],
        option_type=position['instrument_type'],
        strike=position['strike'],  # Keep same strike
        expiration=target_expiration
    )
    
    # 3. Open new position
    if new_contract:
        open_order = alpaca.buy_option(new_contract['symbol'], position['quantity'])
        
        # Log the roll
        db.log_position_event(position['id'], 'rolled', {
            'from': position['option_symbol'],
            'to': new_contract['symbol'],
            'pnl_locked': position['current_pnl_dollars']
        })
```

---

## Testing & Verification Plan

### Test 1: Trailing Stop

**Setup:**
```python
# Create test position with profit
test_position = {
    'ticker': 'AAPL',
    'entry_price': 10.00,
    'current_price': 20.00,  # +100%
    'peak_price': 25.00,     # Was at +150%
    'quantity': 10
}

# Calculate trailing stop
trailing = 25 - ((25 - 10) × 0.25) = $21.25

# Test: current $20 < trailing $21.25
# Should trigger exit
```

**Verify:**
- Position exits at $21.25
- Locks in $11.25 gain (112.5%)
- Doesn't exit too early

### Test 2: IV Rank Filtering

**Setup:**
```python
# High IV scenario
contract = {
    'ticker': 'TSLA',
    'implied_volatility': 0.80,
    'strike': 250
}

# TSLA 52-week IV: 0.30 to 0.90
iv_rank = (0.80 - 0.30) / (0.90 - 0.30) = 0.833 (83rd percentile)

# Should reject: IV Rank > 0.80
```

**Verify:**
- High IV contracts rejected
- Logs show "IV Rank too high"
- Only trades reasonable IV

### Test 3: Partial Exits

**Setup:**
```python
# Position at +60% profit
position = {
    'quantity': 10,
    'original_quantity': 10,
    'entry_price': 15.00,
    'current_price': 24.00,  # +60%
    'pnl_percent': 60
}

# Should trigger: first_profit_target
# Exit: 5 contracts (50%)
# Keep: 5 contracts
```

**Verify:**
- Sells exactly 50%
- Keeps rest for further gains
- Logs partial exit event

### Test 4: End-to-End with Real Position

**Use META position:**
```
1. Position Manager syncs META from Alpaca
2. Sees: Entry $17.15, Current $35, Peak $40 (if it was)
3. Calculates: Trailing stop $34.25
4. Current $35 > $34.25 → Hold
5. If drops to $34.25 → EXIT
6. Locks in $17.10 gain (99.7%)
```

---

## Files to Modify (Exact List)

### Phase 3:

**1. services/position_manager/monitor.py**
- Add: `check_exit_conditions_options()`
- Add: `check_trailing_stop()`
- Modify: `check_exit_conditions()` to use both

**2. services/position_manager/exits.py**
- Update: `execute_exit()` for option-specific logic

**3. services/feature_computer_1m/features.py**
- Add: `calculate_iv_rank()`
- Store: IV history for lookback

**4. services/dispatcher/alpaca/options.py**
- Add: `validate_iv_rank()` to validation chain

**5. db/migrations/013_phase3_improvements.sql**
- Add: `peak_price` column
- Add: `iv_rank` column
- Add: `entry_underlying_price` column

### Phase 4:

**6. services/dispatcher/alpaca/options.py**
- Add: `calculate_kelly_size()`
- Add: `calculate_atr_adjusted_size()`

**7. services/position_manager/monitor.py**
- Add: `check_partial_exit()`
- Add: `check_rolling_opportunity()`

**8. services/position_manager/exits.py**
- Add: `execute_partial_exit()`
- Add: `execute_roll()`

---

## Deployment Process

### Step 1: Code Changes (2 hours)

Make all modifications listed above.

### Step 2: Build & Deploy (30 min)

**Position Manager:**
```bash
cd services/position_manager
docker build --no-cache -t ops-pipeline/position-manager:phase3-4 .
docker tag ops-pipeline/position-manager:phase3-4 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/position-manager:phase3-4
aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin 160027201036.dkr.ecr.us-west-2.amazonaws.com
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/position-manager:phase3-4
```

**Update task definition:**
```bash
# Edit deploy/position-manager-task-definition.json with new SHA256
aws ecs register-task-definition --cli-input-json file://deploy/position-manager-task-definition.json --region us-west-2
# Returns: 4

# Update scheduler
aws scheduler update-schedule \
  --name ops-pipeline-position-manager \
  --region us-west-2 \
  --target '{"EcsParameters": {"TaskDefinitionArn": "...position-manager:4", ...}}'
```

**Dispatcher (if needed):**
```bash
cd services/dispatcher
docker build --no-cache -t ops-pipeline/dispatcher:phase3-4 .
# (Same process)
# Returns: revision 17
```

### Step 3: Testing (2 hours)

**Test Script:** `scripts/test_phase3_4.py`

```python
#!/usr/bin/env python3
import boto3, json, time

client = boto3.client('lambda', region_name='us-west-2')

print("=== Phase 3-4 Testing ===\n")

# Test 1: Check IV Rank filtering
print("1. IV Rank Filtering:")
# Look at next contract selection in logs
# Should see: "IV Rank: 0.XX" in quality scoring

# Test 2: Check trailing stops
print("2. Trailing Stop Logic:")
# Check active_positions for peak_price column
r = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'sql': """
        SELECT ticker, entry_price, current_price, peak_price, trailing_stop_price
        FROM active_positions
        WHERE status = 'OPEN'
    """})
)
print(json.dumps(json.loads(json.load(r['Payload'])['body']), indent=2))

# Test 3: Monitor META exit
print("\n3. META Position Exit:")
# Should exit soon with trailing stop or profit target
# Check position_events table for exit
time.sleep(300)  # Wait 5 minutes
r = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'sql': """
        SELECT event_type, event_data::text, created_at::text
        FROM position_events
        WHERE position_id IN (
            SELECT id FROM active_positions WHERE ticker = 'META'
        )
        ORDER BY created_at DESC
        LIMIT 5
    """})
)
print(json.dumps(json.loads(json.load(r['Payload'])['body']), indent=2))

print("\n=== Testing Complete ===")
```

---

## Expected Results

### After Phase 3:

**Exit Logic:**
```
META position:
- Entry: $17.15
- Peak: $40 (if it went there)
- Current: $35
- Trailing Stop: $34.25 (75% of peak gain locked)
- Action: HOLD (above trail)
- If drops to $34.25: EXIT with $17.10 profit (99%)
```

**IV Rank:**
```
Next contract selection:
"IV Rank: 0.45 (OK)"
"IV: 0.35, 52-week range: 0.20-0.65"
"Below 80th percentile, safe to trade"
```

### After Phase 4:

**Kelly Sizing:**
```
Historical performance:
- Win rate: 65%
- Avg win: +45%
- Avg loss: -18%

Kelly = (0.65 × 0.45 - 0.35 × 0.18) / 0.45 = 0.506
Fractional Kelly (50%): 25.3%

Tiny account: Uses 25.3% (close to current 25%)
Large account: Should use 1.0% (conservative override)
```

**Partial Exits:**
```
Trade at 10 contracts:
- At +50%: Sell 5, keep 5
- At +75%: Sell 2.5, keep 2.5
- Final 2.5 ride to target/stop
```

---

## Verification Checklist

### System Health:
- [ ] All 10 schedulers ENABLED
- [ ] No errors in any service
- [ ] Both accounts trading
- [ ] Position Manager monitoring

### Phase 3 Features:
- [ ] Trailing stops working (see peak_price in DB)
- [ ] IV Rank calculated (see in logs)
- [ ] Option-based exits (not stock-based)
- [ ] META position exited correctly

### Phase 4 Features:
- [ ] Kelly criterion referenced
- [ ] Partial exits triggered
- [ ] ATR-adjusted sizing
- [ ] Rolling logic ready

### End-to-End:
- [ ] News → Signal → Execute → Monitor → Exit
- [ ] Verified with real trade
- [ ] All data flows working
- [ ] Grade reached: A+

---

## Documentation Status

**Primary Documents (Keep):**
1. SYSTEM_COMPLETE_GUIDE.md - This file
2. AI_PIPELINE_EXPLAINED.md
3. PRODUCTION_IMPROVEMENTS_NEEDED.md
4. MULTI_ACCOUNT_OPERATIONS_GUIDE.md
5. BEST_IN_CLASS_COMPARISON.md

**Archive (Old Deployment Notes):**
- PHASE_1_2_DEPLOYMENT_COMPLETE.md
- EXIT_LOGIC_EXPLAINED.md
- TINY_ACCOUNT_DEPLOYMENT_STEPS.md
- MULTI_ACCOUNT_DESIGN.md
- MULTI_ACCOUNT_STATUS.md

**Total:** 15 files, well-organized

---

## Success Criteria

**To Declare Phase 3-4 Complete:**

1. ✅ IV Rank filtering active (logs show filtering)
2. ✅ Trailing stops working (peak tracked in DB)
3. ✅ Option-based exits (not stock price)
4. ✅ Partial exits triggered (verified with position)
5. ✅ Kelly criterion benchmarked
6. ✅ End-to-end test passes
7. ✅ Grade: A+ (95%+)

---

## Current Status Summary

**What Works (B+ Grade):**
- Contract selection: A- (90%)
- Position sizing: A- (90%)
- Risk management: B (80%)
- Exit strategies: C (65%)
- Greeks/IV: C+ (70%)

**What's Needed (A+ Grade):**
- Trailing stops
- IV Rank filtering
- Partial exits
- Rolling logic
- Kelly criterion

**Time to A+:** 5-7 hours in next dedicated session

**Next Agent:** Start with this file, implement Phase 3-4, test thoroughly, reach 100%!
