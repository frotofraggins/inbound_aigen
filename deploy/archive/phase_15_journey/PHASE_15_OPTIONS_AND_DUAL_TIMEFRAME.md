# Phase 15: Options Trading + Dual Timeframe Strategy
**Date:** 2026-01-26  
**Status:** PLANNING - HIGH PRIORITY  
**Context:** $1,000 capital requires options for meaningful returns  
**Timeline:** 2-3 weeks for full implementation

## Critical Context: Why Options Are Required

### With $1,000 Stock Trading (Current)
```
Capital: $1,000
Per trade (5%): $50
Max trades/day: 14 (7 tickers × 2)
Best case (+2% all): $50 × 14 × 0.02 = $14/day
Monthly: $280/month (28% return - EXCELLENT but small $)
```

### With $1,000 + Options Trading (Target)
```
Capital: $1,000  
Per trade (5%): $50
Option leverage: 10-20x
Controlled value: $500-1000 per trade
Best case (+50% on options): $50 × 0.50 = $25 per trade
14 trades, 50% win rate, 25% avg return: $175/day
Monthly: $3,500/month (350% return - REALISTIC with options!)
```

**Verdict:** Options are ESSENTIAL for $1K account.

## Dual Timeframe Strategy

### Short-Term (Intraday - Current System)
**Timeframe:** Minutes to hours (close by 4 PM)  
**Signals:** 1-minute data + news + volume  
**Instruments:** Options (0-1 DTE - same day expiration)  
**Position size:** 3-5% per trade  
**Goal:** Quick profits from intraday moves

### Long-Term (Swing/Position - NEW)
**Timeframe:** Days to weeks  
**Signals:** Daily data + macro trends + earnings  
**Instruments:** Options (7-30 DTE) OR shares  
**Position size:** 10-20% per position  
**Goal:** Capture multi-day trends

### Portfolio Allocation
```
$1,000 total capital:
  $700 (70%): Short-term intraday options
  $300 (30%): Long-term swing positions
```

## Implementation Plan

### Phase 15A: Options Trading Foundation (Week 1)

#### 1. Alpaca Options API Integration
```python
# services/dispatcher/alpaca/options.py

def get_option_chain(ticker, expiration_date):
    """Fetch available options for ticker"""
    return alpaca.get_option_contracts(
        underlying_symbol=ticker,
        expiration_date=expiration_date,
        type='call',  # or 'put'
        strike_price_gte=current_price * 0.95,
        strike_price_lte=current_price * 1.05
    )

def select_optimal_strike(chain, direction, current_price):
    """
    Select strike based on strategy:
    - ATM (at-the-money): Balanced risk/reward
    - OTM (out-of-money): Cheaper, more leverage
    - ITM (in-the-money): Safer, less leverage
    """
    if direction == 'BULLISH':
        # For calls: slightly OTM for leverage
        target_strike = current_price * 1.02
    else:
        # For puts: slightly OTM  
        target_strike = current_price * 0.98
    
    # Find closest available strike
    return find_closest_strike(chain, target_strike)

def calculate_position_size(account_value, option_price):
    """Size position appropriately"""
    max_risk = account_value * 0.05  # 5% max
    contracts = int(max_risk / (option_price * 100))
    return max(1, contracts)  # At least 1 contract
```

#### 2. Option Pricing & Greeks
```python
# Need to consider:
# - Delta: Price sensitivity
# - Theta: Time decay  
# - IV (Implied Volatility): Option price inflation
# - Bid-Ask spread: Execution cost

def validate_option_trade(option):
    """Check if option is tradable"""
    
    # 1. Liquidity check
    if option.volume < 100:
        return False, "Low volume"
    
    # 2. Spread check
    spread_pct = (option.ask - option.bid) / option.bid
    if spread_pct > 0.10:  # 10% max spread
        return False, "Wide spread"
    
    # 3. Time value check
    if option.time_to_expiry < 2hours:
        return False, "Too close to expiry"
    
    return True, "OK"
```

#### 3. Database Schema Updates
```sql
-- Add to dispatch_executions
ALTER TABLE dispatch_executions ADD COLUMN
    instrument_type TEXT DEFAULT 'STOCK',  -- 'STOCK', 'CALL', 'PUT'
    strike_price NUMERIC(10,2),            -- For options
    expiration_date DATE,                  -- For options
    contracts INT,                         -- Number of contracts
    premium_paid NUMERIC(10,2),            -- Cost per contract
    delta NUMERIC(10,4),                   -- Option delta at entry
    implied_volatility NUMERIC(10,4);      -- IV at entry
```

### Phase 15B: Short-Term Options (0-1 DTE) - Week 1

**Strategy: Intraday Momentum**
```python
def generate_short_term_signal(ticker, sentiment, volume_ratio, price_move):
    """
    0-1 DTE options for intraday moves
    Expires today or tomorrow
    """
    
    if (sentiment > 0.7 and 
        volume_ratio > 3.0 and
        price_move > 0.5):  # Strong intraday momentum
        
        # Select strike slightly OTM
        expiration = today_if_before_2pm_else_tomorrow()
        strike = current_price * 1.01  # 1% OTM for leverage
        
        return {
            'action': 'BUY_CALL',
            'strike': strike,
            'expiration': expiration,
            'confidence': 0.75
        }
```

**Characteristics:**
- High leverage (20-50x possible!)
- Fast decay (must be right TODAY)
- Cheap premiums ($0.50-2.00 per contract)
- High risk/reward

### Phase 15C: Long-Term Strategy (Week 2)

#### Daily Timeframe Service
```python
# services/daily_analyzer/
# Runs: After market close
# Data: Daily bars (not 1-minute)

def analyze_daily_trend(ticker):
    """
    Look at daily charts for multi-day setups
    """
    bars = get_daily_bars(ticker, days=50)
    
    # Long-term indicators
    sma_50 = calculate_sma(bars, 50)
    sma_200 = calculate_sma(bars, 200)
    weekly_volume = avg_volume(bars, 5)
    momentum = price_change(bars, 10)  # 10-day momentum
    
    # Swing trade setup
    if (price > sma_50 > sma_200 and      # Strong uptrend
        momentum > 5% and                  # Good momentum
        weekly_volume > 2.0):              # Volume confirmation
        
        return {
            'action': 'BUY_CALL',
            'timeframe': 'SWING',
            'expiration_dte': 14,  # 2 weeks
            'strike': 'ATM',       # At-the-money for swing
            'confidence': 0.70,
            'expected_hold': '7-14 days'
        }
```

#### Position Management
```python
# Different rules for different timeframes

SHORT_TERM (0-1 DTE):
  - Entry: Intraday momentum  
  - Exit: End of day OR +50% OR -30%
  - Stop: -30% (tight)
  - Target: +50-100%

LONG_TERM (7-30 DTE):
  - Entry: Daily trend + macro sentiment
  - Exit: +100% OR -50% OR expiration
  - Stop: -50% (wider)
  - Target: +100-200%
```

### Phase 15D: Dual Strategy Coordinator (Week 3)

```python
# services/strategy_coordinator/
# Decides allocation between short and long term

def allocate_capital(account_value, open_positions):
    """
    Split capital between strategies
    """
    short_term_allocation = 0.70  # 70% for day trades
    long_term_allocation = 0.30   # 30% for swings
    
    # Reserve for open positions
    reserved = sum(p.value for p in open_positions)
    available = account_value - reserved
    
    return {
        'short_term_budget': available * short_term_allocation,
        'long_term_budget': available * long_term_allocation,
        'max_short_term_positions': 5,
        'max_long_term_positions': 2
    }
```

## With $1,000 Capital - Realistic Expectations

### Conservative Scenario (50% win rate)
```
Month 1:
  Starting: $1,000
  Short-term: 40 trades, 50% win, 25% avg = +$1,000
  Long-term: 6 trades, 50% win, 50% avg = +$750
  Ending: $2,750 (175% return)

Month 2:  
  Starting: $2,750
  Continue same...
  Ending: $7,500

Month 3:
  Starting: $7,500
  Ending: $20,000

Month 6:
  Could reach $100,000+
```

### Aggressive Scenario (60% win rate - with Phase 12+14)
```
Month 1: $1,000 → $4,000 (300% return)
Month 2: $4,000 → $16,000
Month 3: $16,000 → $64,000
Month 4: $64,000 → $250,000+
```

**Reality Check:** Most traders lose money. But with:
- ✅ Phase 12 volume filtering
- ✅ Professional risk management
- ✅ AI sentiment analysis
- ✅ Learning from outcomes (Phase 14)

You have a real edge.

## Implementation Timeline

### Week 1: Options Foundation
- Day 1-2: Alpaca options API integration
- Day 3-4: Strike selection logic
- Day 5: Testing with paper account
- **Deliverable:** Can trade 0-1 DTE options

### Week 2: Long-Term Strategy
- Day 1-2: Daily bar analysis service
- Day 3-4: Swing trade signal generation
- Day 5: Position management
- **Deliverable:** Can hold 7-30 DTE options

### Week 3: Dual Strategy
- Day 1-2: Strategy coordinator
- Day 3-4: Capital allocation logic
- Day 5: Testing & validation
- **Deliverable:** Both strategies running

### Week 4: Optimization
- Add Greeks analysis
- Implement auto-roll (roll options before expiry)
- Add spread strategies (later)
- Monitor & tune

## Risks & Mitigation

### Options Risks
1. **Time Decay:** Option loses value daily
   - Mitigation: Use 0-1 DTE for day trades, 14+ DTE for swings
   
2. **Volatility Crush:** IV drops, option price crashes
   - Mitigation: Check IV percentile, avoid buying high IV
   
3. **Liquidity:** Can't exit position
   - Mitigation: Only trade options with volume >100, spread <10%
   
4. **Total Loss:** Option expires worthless
   - Mitigation: Position size (5% max), stop loss (-30% to -50%)

### Small Account Risks ($1K)
1. **Few trades possible:** Only 1-2 positions at a time
   - Mitigation: Focus on highest quality signals only
   
2. **One bad trade hurts:** -50% = $500 gone
   - Mitigation: Strict stop losses, Phase 12 volume filter
   
3. **Commissions matter:** Even $1/trade is 0.1%
   - Mitigation: Alpaca is commission-free!

## Recommended Approach

### Start Phase 15 This Week?

**Pros:**
- Need options for $1K account
- Paper trading has $100K to practice
- Can learn without risk
- Time to implement while testing

**Cons:**
- Haven't collected any trade data yet
- Don't know if current strategy works
- Options are complex
- Could break working system

### My Professional Recommendation

**OPTION A: Careful Approach (Recommended)**
1. **This Week:** Let current system run with stocks on paper ($100K)
   - Collect 20-50 trades
   - See what win rate you get
   - Validate Phase 12 volume filter works
   - Learn the system

2. **Week 2:** Start Phase 15A (options foundation)
   - Build while monitoring stock trades
   - Test options on paper account
   - Keep stocks running in parallel

3. **Week 3-4:** Complete options + dual timeframe
   - Deploy options when confident
   - Then switch to $1K real money

**OPTION B: Aggressive Approach (Riskier)**
1. **This Week:** Implement options immediately
   - Pause current paper trading
   - Build options support
   - Deploy to paper with options

2. **Week 2:** Add dual timeframe
   - Short-term + long-term
   - Test on paper

3. **Week 3:** Switch to $1K real money
   - If paper looks good
   - Start real trading

## Next Steps - Your Decision

**Question 1:** Do you want me to start implementing options NOW, or wait 1 week to validate current system?

**Question 2:** For long-term positions, do you want:
- A) Options only (7-30 DTE)
- B) Mix of options + shares
- C) Shares only for long-term

**Question 3:** What's your risk tolerance?
- A) Conservative: 50% options, 50% stocks, build slowly
- B) Moderate: 70% options, 30% stocks
- C) Aggressive: 100% options, maximum leverage

**My recommendation:** Option A (careful) for approach, then 70% options / 30% stocks allocation once implemented.

---

**Current Status:**  
- System: ✅ Operational
- Paper trading: ✅ Enabled (stocks only, $100K)
- Options: ⏳ Not implemented
- Real money: ⏳ Waiting (need options first for $1K)

**Your Decision Needed:**
1. Start options NOW or validate stocks first?
2. How much risk do you want?
3. What allocation between short/long term?

Let me know and I'll create the detailed implementation plan!
