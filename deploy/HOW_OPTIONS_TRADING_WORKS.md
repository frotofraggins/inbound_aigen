# How Options Trading Works - Complete Decision Flow

**Question:** "How is it choosing contracts and how does it know if one is good or not and when to sell or buy it?"

---

## Complete Flow: From Data → Trade → Exit

```
📊 Price Data
   ↓
🧮 Technical Analysis (SMA, trend, volume)
   ↓
💭 Sentiment (FinBERT news analysis)
   ↓
🎯 DECISION: BUY CALL vs BUY PUT vs HOLD
   ↓
🔍 Select Best Options Contract
   ↓
✅ Validate Quality (spread, greeks)
   ↓
💰 Execute Trade (Alpaca API)
   ↓
📈 Monitor Position (stop loss, take profit)
```

---

## Step 1: When to BUY vs SELL (Signal Generation)

**File:** `services/signal_engine_1m/rules.py`

### Decision Criteria:

#### Buy CALL (Bullish on stock going UP)
```
Conditions:
✅ Price above SMA20 (support level)
✅ Trend state = +1 (strong uptrend)
✅ Price breaking up (> 1% above SMA20)
✅ Volume > 1.2x average (confirms move)
✅ Confidence > 0.45-0.60 (depending on strategy)

Optional Boost:
- Positive sentiment (+25% confidence)
- Volume surge 2x+ (+35% confidence)
```

#### Buy PUT (Bearish on stock going DOWN)
```
Conditions:
✅ Price below SMA20 (resistance level)
✅ Trend state = -1 (strong downtrend)
✅ Price breaking down (> 1% below SMA20)
✅ Volume > 1.2x average (confirms move)
✅ Confidence > 0.45-0.60

Optional Boost:
- Negative sentiment (+25% confidence)
- Volume surge 2x+ (+35% confidence)
```

#### HOLD (Don't Trade)
```
Reasons:
❌ No clear trend (state = 0)
❌ Volume too low (< 0.5x average)
❌ Confidence too low (< thresholds)
❌ Price not at support/resistance
❌ Recent trade in same ticker (15 min cooldown)
```

**Code Example:**
```python
# From services/signal_engine_1m/rules.py

# Determine direction from PRICE + TREND (not sentiment!)
if above_sma20 and trend_state == TREND_BULL:
    primary_direction = "BULL"  # → BUY CALL
elif below_sma20 and trend_state == TREND_BEAR:
    primary_direction = "BEAR"  # → BUY PUT
else:
    primary_direction = "NONE"  # → HOLD
```

---

## Step 2: Which Options Contract to Choose

**File:** `services/dispatcher/alpaca/options.py`

### Contract Selection Process:

#### 1. Fetch All Available Contracts
```python
# Get contracts from Alpaca API
contracts = api.get_option_chain(
    ticker="TSLA",
    expiration_date_gte="2026-02-05",  # 7 days out
    expiration_date_lte="2026-02-28",  # 30 days out
    option_type="put",  # or "call"
    strike_price_gte=380,  # -10% from current
    strike_price_lte=465   # +10% from current
)
# Returns: 165 contracts for TSLA
```

#### 2. Select Strike Based on Strategy

**Day Trade (0-1 DTE):** OTM (Out-of-Money) - More leverage
```python
if option_type == 'call':
    target_strike = current_price * 1.015  # 1.5% ABOVE (cheaper, more risk)
else:  # put
    target_strike = current_price * 0.985  # 1.5% BELOW
    
# Example: TSLA at $420
# CALL day trade → $426 strike (OTM)
# PUT day trade → $414 strike (OTM)
```

**Swing Trade (7-30 DTE):** ATM (At-the-Money) - Balanced
```python
target_strike = current_price  # Right at current price

# Example: TSLA at $420
# CALL swing → $420 strike (ATM)
# PUT swing → $420 strike (ATM)
```

**Conservative (Rare):** ITM (In-the-Money) - Less risk
```python
if option_type == 'call':
    target_strike = current_price * 0.97  # 3% BELOW (more expensive, safer)
else:  # put
    target_strike = current_price * 1.03  # 3% ABOVE
```

#### 3. Find Closest Match
```python
best_contract = min(
    contracts,
    key=lambda c: abs(c['strike_price'] - target_strike)
)

# Example: Target $420, available strikes: $415, $420, $425
# → Selects $420 strike (exact match)
```

---

## Step 3: How to Know if Contract is GOOD

**File:** `services/dispatcher/alpaca/options.py` - `validate_option_liquidity()`

### Quality Checks:

#### Check 1: Bid-Ask Spread (PRIMARY)
```python
bid = 2.50  # What market makers will PAY you
ask = 2.55  # What market makers will CHARGE you
spread_pct = (ask - bid) / bid * 100 = 2%

if spread_pct > 10%:
    return False, "Spread too wide"  # REJECT

# Good: < 10% spread
# Bad: > 10% spread (hard to exit, loses money on entry/exit)
```

**Why it matters:** Tight spread = active market = easy to buy/sell

#### Check 2: Valid Prices
```python
if bid <= 0 or ask <= 0:
    return False, "No valid prices"  # REJECT
    
# Contract must have real bids and asks
```

#### Check 3: Not Expired
```python
if expiration_date < today:
    return False, "Contract expired"  # REJECT
```

### What Makes a "Good" Contract:

✅ **Tight Spread** - < 10% (can exit easily)  
✅ **Valid Prices** - Real bids/asks (market is active)  
✅ **Right Strike** - Matches strategy (OTM/ATM/ITM)  
✅ **Right Expiration** - 0-1 DTE for day trade, 7-30 DTE for swing  
✅ **Decent Greeks** - Delta, IV in reasonable ranges

**Example Good Contract:**
```
TSLA260215P00420000 (TSLA Feb 15 $420 Put)
- Strike: $420 (ATM for swing trade)
- Bid: $12.50, Ask: $12.75 (spread = 2% ✅)
- Expiration: 17 days (good for swing ✅)
- Delta: -0.48 (will move with stock ✅)
→ ACCEPT and buy
```

**Example Bad Contract:**
```
TSLA260131C00500000 (TSLA Jan 31 $500 Call)
- Strike: $500 (way OTM, TSLA at $420)
- Bid: $0.05, Ask: $0.15 (spread = 200% ❌)
- Expiration: 2 days
- Delta: 0.02 (barely moves ❌)
→ REJECT, fall back to simulation
```

---

## Step 4: Position Sizing (How Many Contracts)

**File:** `services/dispatcher/alpaca/options.py` - `calculate_position_size()`

### Formula:

```python
# Account: $182,000 buying power
# Strategy: Day trade = 5% risk max

risk_dollars = $182,000 * 0.05 = $9,100
contract_cost = premium * 100  # Each contract = 100 shares

# Premium: $2.50 per share
contract_cost = $2.50 * 100 = $250 per contract

num_contracts = $9,100 / $250 = 36 contracts
total_cost = 36 * $250 = $9,000
```

### Risk by Strategy:
- **Day Trade:** 5% of capital
- **Swing Trade:** 10% of capital (2x day trade)
- **Conservative:** 3% of capital

**Example:**
```
Account: $182,000
Strategy: Swing trade PUT on TSLA
Premium: $12.50 per share

Risk: 10% = $18,200
Cost per contract: $12.50 * 100 = $1,250
Contracts: $18,200 / $1,250 = 14 contracts
Total: 14 * $1,250 = $17,500
```

---

## Step 5: When to EXIT (Sell the Position)

**File:** `services/position_manager/monitor.py` + `exits.py`

### Automatic Exits:

#### Exit 1: Stop Loss Hit (Protect Capital)
```python
# Set at entry (2% below for CALL, 2% above for PUT)
if current_price <= stop_loss:
    force_close("STOP_LOSS_HIT")
    
# Example: Bought CALL at $2.50, stop at $2.45
# If drops to $2.45 → AUTO SELL
```

#### Exit 2: Take Profit Hit (Lock Gains)
```python
# Set at entry (5-10% target)
if current_price >= take_profit:
    force_close("TAKE_PROFIT_HIT")
    
# Example: Bought CALL at $2.50, target $2.75
# If reaches $2.75 → AUTO SELL
```

#### Exit 3: Max Hold Time (Time Decay)
```python
# Day trades: max 1 day
# Swing trades: max 7-14 days

if hold_time > max_hold_minutes:
    force_close("MAX_HOLD_TIME")
    
# Options lose value over time (theta decay)
# Don't hold too long!
```

#### Exit 4: Expiration Approaching
```python
# Close 1 day before expiration
if days_to_expiration <= 1:
    force_close("EXPIRATION_RISK")
```

#### Exit 5: Risk Limits
```python
# Daily loss limit
if daily_pnl < -$500:
    force_close_all("DAILY_LOSS_LIMIT")
    
# Max positions
if num_positions >= 5:
    reject_new_trades()
```

---

## Real Example: TSLA PUT Trade

### Signal Generation (16:18 UTC)
```
TSLA Price: $418
SMA20: $425 (price BELOW → bearish)
Trend: -1 (downtrend confirmed)
Volume: 2.3x average (strong move)
Sentiment: -0.3 (slightly bearish, boosts confidence)

Base Confidence: 0.42
After Sentiment: 0.42 * 1.15 = 0.48
After Volume: 0.48 * 1.15 = 0.55
Final: 0.55 > 0.45 threshold ✅

DECISION: BUY PUT (swing_trade)
```

### Contract Selection (Dispatcher)
```
1. Fetch contracts from Alpaca:
   - Expiration: Feb 5-28 (7-30 days out)
   - Type: PUT
   - Strike range: $376-$460 (±10%)
   - Result: 83 contracts found

2. Select strike:
   - Strategy: swing_trade → ATM
   - Target: $418 (current price)
   - Closest: $420 strike
   - Selected: TSLA260215P00420000

3. Validate quality:
   - Bid: $12.50, Ask: $12.75
   - Spread: 2% ✅ (< 10% threshold)
   - Expiration: Feb 15 (17 days) ✅
   - APPROVED

4. Position sizing:
   - Account: $182,000
   - Risk: 10% (swing) = $18,200
   - Cost: $12.50 * 100 = $1,250/contract
   - Contracts: 14
   - Total: $17,500

5. Execute:
   - Place order via Alpaca
   - Set stop: $12.25 (-2%)
   - Set target: $13.75 (+10%)
   - Max hold: 14 days
```

### Exit Monitoring
```
Every minute, position-manager checks:
- Current price of TSLA260215P00420000
- If >= $13.75 → SELL (take profit)
- If <= $12.25 → SELL (stop loss)
- If 14 days pass → SELL (time limit)
- If 1 day to expiration → SELL (risk)
```

---

## Key Decision Logic Summary

### Choosing BUY vs SELL:
**Based on:** Price vs SMA20 + Trend direction  
**NOT based on:** Sentiment alone (just modifies confidence)  
**Result:** CALL if bullish setup, PUT if bearish

### Choosing Which Contract:
**Based on:** Strategy type (day/swing)  
**Strike:** OTM for day trades (leverage), ATM for swings (balance)  
**Expiration:** 0-1 DTE for day, 7-30 DTE for swing

### Knowing if Contract is Good:
**Primary:** Bid-ask spread < 10%  
**Secondary:** Valid prices, not expired  
**Future:** Delta, IV percentile when data available

### When to Sell:
**Automatic:** Stop loss (-2%), take profit (+10%)  
**Time-based:** Max hold period, expiration approaching  
**Risk-based:** Daily loss limit, position limits

---

## All Thresholds (Configurable)

### Entry Thresholds
```python
# Confidence required
CONFIDENCE_DAY_TRADE = 0.60    # High bar for 0-1 DTE
CONFIDENCE_SWING_TRADE = 0.45  # Lower for 7-30 DTE
CONFIDENCE_STOCK = 0.35        # Stocks least risky

# Volume required
VOLUME_MIN = 1.2x average      # Minimum for any trade
VOLUME_KILL = 0.5x average     # Below this = HOLD

# Breakout required
BREAKOUT_THRESHOLD = 0.01      # 1% move from SMA20
```

### Contract Quality Thresholds
```python
# Liquidity
MAX_SPREAD = 10%               # Bid-ask spread
MIN_VOLUME = 100               # Daily volume (future)
MIN_OPEN_INTEREST = 100        # Open interest (future, not available)

# Greeks (future when implemented)
MAX_IV_PERCENTILE = 80         # Don't buy expensive options
```

### Exit Thresholds
```python
# Profit targets
STOP_LOSS = -2%                # Protect capital
TAKE_PROFIT = +10%             # Lock gains

# Time limits
DAY_TRADE_MAX = 1 day          # Close before overnight
SWING_TRADE_MAX = 14 days      # Don't hold too long

# Risk limits
DAILY_LOSS_LIMIT = $500        # Stop trading if down
MAX_POSITIONS = 5              # Position limit
MAX_EXPOSURE = $10,000         # Total capital at risk
```

---

## Why These Rules?

### Strike Selection Logic:
- **Day Trades:** OTM for 3-5x leverage (higher risk/reward)
- **Swing Trades:** ATM for 1.5-2x leverage (balanced)
- **Near current price = most liquid = easiest to exit**

### Liquidity Checks:
- **Tight spread** = Easy to buy/sell without losing money
- **Wide spread** = Lose 10%+ just on entry/exit (avoid!)

### Automatic Exits:
- **Options decay over time** (theta) - can't hold forever
- **Stop losses protect** from big losses
- **Take profits lock** gains before reversals

---

## Example Trades with Full Logic

### Trade 1: NVDA CALL (Bullish)
```
Signal: BUY CALL
Reason: Price $186 above SMA20 $183, uptrend, 2.1x volume

Contract Selection:
- Fetch 83 contracts (expirations 7-30 days)
- Strategy: swing_trade → ATM
- Target strike: $186
- Selected: NVDA260215C00186000 ($186 strike, Feb 15)
- Bid $8.20, Ask $8.35 (spread 1.8% ✅)

Position Sizing:
- Account: $182,000
- Risk: 10% = $18,200
- Cost: $8.28 * 100 = $828/contract
- Contracts: 21
- Total: $17,388

Auto Exits:
- Stop: $8.11 (-2%)
- Target: $9.11 (+10%)
- Max hold: 14 days
- Close if < 1 day to expiration
```

### Trade 2: AMD PUT (Bearish)
```
Signal: BUY PUT
Reason: Price $244 below SMA20 $248, downtrend, 1.8x volume

Contract Selection:
- Fetch 67 contracts
- Strategy: day_trade → OTM
- Target strike: $240 (1.5% below)
- Selected: AMD260130P00240000 ($240 strike, Jan 30)
- Bid $2.45, Ask $2.52 (spread 2.9% ✅)

Position Sizing:
- Risk: 5% (day trade) = $9,100
- Cost: $2.49 * 100 = $249/contract
- Contracts: 36
- Total: $8,964

Auto Exits:
- Stop: $2.44 (-2%)
- Target: $2.74 (+10%)
- Max hold: 1 day (expires tomorrow!)
```

---

## What Happens in Logs

### Successful Trade:
```
Fetched 83 option contracts for NVDA
DEBUG first contract: strike=186.0, bid=8.20, ask=8.35
✓ Liquidity check passed
Placing order: NVDA260215C00186000, qty=21
Order filled: avg_price=$8.28
execution_mode: ALPACA_PAPER ✅
```

### Rejected Trade:
```
Fetched 67 option contracts for AMD
Option contract failed liquidity check: Spread too wide: 15.2% > 10%
Falling back to simulation
execution_mode: SIMULATED_FALLBACK
```

---

## Complete Decision Tree

```
Is trend strong (+1 or -1)?
├─ YES → Can trade options
│   │
│   ├─ Trend +1 (UP) → BUY CALL
│   │   ├─ High confidence + volume surge → Day trade (0-1 DTE, OTM)
│   │   └─ Moderate confidence → Swing trade (7-30 DTE, ATM)
│   │
│   └─ Trend -1 (DOWN) → BUY PUT
│       ├─ High confidence + volume surge → Day trade (0-1 DTE, OTM)
│       └─ Moderate confidence → Swing trade (7-30 DTE, ATM)
│
└─ NO → Trade stocks only
    ├─ Price above SMA20 → BUY STOCK
    └─ Price below SMA20 → SELL STOCK (if have position)
```

---

## Files Reference

**Signal Generation:**
- `services/signal_engine_1m/rules.py` - compute_signal()
- Logic: SMA, trend, volume, sentiment

**Contract Selection:**
- `services/dispatcher/alpaca/options.py` - get_option_chain_for_strategy()
- Logic: Strike selection, quality validation

**Execution:**
- `services/dispatcher/alpaca/broker.py` - _execute_option()
- Logic: Place order, position sizing

**Exit Management:**
- `services/position_manager/monitor.py` - check_exit_conditions()
- `services/position_manager/exits.py` - force_close_position()
- Logic: Stop/profit checks, time limits

**Complete Flow:**
- `deploy/COMPLETE_TRADING_LOGIC_EXPLAINED.md` - End-to-end walkthrough

---

## Summary

**How it chooses contracts:**
1. Strategy determines expiration (day=0-1 DTE, swing=7-30 DTE)
2. Strategy determines strike (day=OTM for leverage, swing=ATM for balance)
3. Finds closest strike to target from Alpaca's 100+ contracts

**How it knows if good:**
1. Bid-ask spread < 10% (PRIMARY - ensures liquidity)
2. Valid prices exist (market is active)
3. Not expired (obvious!)

**When to buy/sell:**
- **Buy:** Strong trend + breakout + volume confirmation
- **Sell:** Stop loss (-2%) OR take profit (+10%) OR time limits
- **Direction:** CALL if bullish, PUT if bearish (from price action, not just sentiment)

**All logic is rule-based and deterministic** - same inputs always produce same outputs. This makes the system auditable and explainable.
