# Production Improvements for Options Trading

**Date:** 2026-01-29  
**Status:** PAPER TRADING READY, NOT LIVE READY  
**Expert Feedback:** Critical improvements needed before real money

---

## Verdict: Solid Foundation, Needs Safety Upgrades

**✅ Good:** Price+trend decides direction, sentiment scales confidence, volume confirms  
**❌ Issues:** Position sizing too aggressive, exits will chop, liquidity incomplete

**Would I run live?** Not yet. 7 changes needed.

---

## Priority 1: Position Sizing (CRITICAL - 10x too aggressive!)

### Current (DANGEROUS)
```python
# Day trade: 5% of $182K = $9,100 risk
# Swing trade: 10% of $182K = $18,200 risk

# Example: $2.50 premium
# Day: 36 contracts ($9,000)
# Swing: 72 contracts ($18,000)
```

### Production (SAFE)
```python
# Day trade: 0.25-0.75% of account
# Swing trade: 0.5-1.5% of account

# Example: $2.50 premium, $182K account
# Day: 0.5% = $910 → 3-4 contracts
# Swing: 1.0% = $1,820 → 7 contracts

# PLUS hard cap: 1-5 contracts initially
```

**Why:** Options variance is brutal. A few bad fills + theta + chop can wipe days of gains.

**Fix in:** `services/dispatcher/alpaca/options.py` - `calculate_position_size()`

---

## Priority 2: Liquidity Validation (Incomplete)

### Current (Weak)
```python
# Only checks:
- Spread < 10%
- Has bid/ask

# Missing:
- Volume check
- Open interest check
- Premium floor
- Spread calc wrong (uses bid as denominator)
```

### Production (Robust)
```python
# Spread (FIX CALC)
mid = (bid + ask) / 2
spread_pct = (ask - bid) / mid  # NOT bid!

# Thresholds
MAX_SPREAD_DAY = 8%      # Tighter for day trades
MAX_SPREAD_SWING = 10%   # Slightly wider for swings
MIN_OI = 500             # Better than 100
MIN_VOLUME = 200         # Or dynamic by ticker  
MIN_PREMIUM = 0.30       # Avoid $0.05 lottery tickets

# Validation
if spread_pct > max_spread: REJECT
if open_interest < 500: REJECT
if volume < 200: REJECT
if mid_price < 0.30: REJECT
```

**Why:** Spread alone isn't enough. Need volume, OI, and minimum premium to avoid garbage fills.

**Fix in:** `services/dispatcher/alpaca/options.py` - `validate_option_liquidity()`

---

## Priority 3: Contract Selection (Closest ≠ Best)

### Current (Naive)
```python
# Just picks closest strike to target
best = min(contracts, key=lambda c: abs(c['strike'] - target))
```

### Production (Quality-First)
```python
# Score top N contracts near target
def score_contract(contract):
    spread_score = 1 - (spread_pct / MAX_SPREAD)  # Lower is better
    oi_score = min(contract['oi'] / 1000, 1.0)   # Higher is better
    volume_score = min(contract['vol'] / 500, 1.0)
    delta_score = 1 - abs(abs(contract['delta']) - target_delta) / 0.3
    
    return (spread_score * 0.4 +
            oi_score * 0.3 +
            volume_score * 0.2 +
            delta_score * 0.1)

# Filter to strikes within 2% of target
near_target = [c for c in contracts 
               if abs(c['strike'] - target) / target < 0.02]

# Pick highest scoring
best = max(near_target, key=score_contract)
```

**Why:** Closest strike might have terrible liquidity. Score by quality first.

**Fix in:** `services/dispatcher/alpaca/options.py` - `select_optimal_strike()`

---

## Priority 4: Exit Logic (Options ≠ Stocks)

### Current (Will Chop)
```python
STOP_LOSS = -2%      # Too tight - noise
TAKE_PROFIT = +10%   # May work but inconsistent

# Options swing ±10-30% on noise
# -2% stop = death by 1000 cuts
```

### Production Option A (Underlying-Based) - RECOMMENDED
```python
# Exit when UNDERLYING moves, not option price

# Stop Loss:
- CALL: underlying breaks back below SMA20
- PUT: underlying breaks back above SMA20
- OR: trend_state flips
- OR: underlying moves -0.6% against position

# Take Profit:
- CALL: underlying moves +0.8-1.2% up
- PUT: underlying moves +0.8-1.2% down  
- AND: option profit > 20% minimum

# Time:
- Day trade: exit if no follow-through in 30-60 min
- Swing: exit after 7-14 days or 1 day before expiration
```

### Production Option B (Option-Based)
```python
# Wider stops for option price variance

STOP_LOSS = -25% to -40%      # Depends on DTE/vol
TAKE_PROFIT = +35% to +80%    # Asymmetric (3:1 or better)

# Time stops
- Exit if no profit in X minutes
- Exit 1 day before expiration
```

**Why:** -2% on options is noise. Need structure-based or much wider percentage stops.

**Fix in:** `services/position_manager/monitor.py` - `check_exit_conditions()`

---

## Priority 5: Breakout Confirmation (Late Entry)

### Current (Proxy, Can Be Late)
```python
# "1% away from SMA20" = breakout
# Can fire AFTER move already happened
```

### Production (Real Momentum)
```python
# Use actual momentum indicators
ret_5m = (close - close_5m_ago) / close_5m_ago
ret_15m = (close - close_15m_ago) / close_15m_ago

# Breakout confirmed if:
- ret_5m > 0.003 (0.3% in 5 min)
- ret_15m > 0.008 (0.8% in 15 min)
- AND volume_ratio > 1.5 for 2-3 consecutive bars

# Better entry timing, catches momentum early
```

**Why:** Real momentum indicators catch moves earlier and more reliably.

**Fix in:** `services/feature_computer_1m/features.py` + `services/signal_engine_1m/rules.py`

---

## Priority 6: Chop Filter (Avoid Whipsaws)

### Current (Missing)
```python
# Options trade even in chop
# → Get chopped to death in ranging markets
```

### Production (Essential)
```python
# Add chop detection
sma20_slope = (sma20_now - sma20_20bars_ago) / sma20_20bars_ago

if abs(sma20_slope) < 0.002:  # Flat SMA
    if price_oscillating_around_sma20:
        can_trade_options = False  # Stock only or HOLD
```

**Why:** Options hate chop. Need trending markets.

**Fix in:** `services/signal_engine_1m/rules.py` - `compute_signal()`

---

## Priority 7: Option Quote Monitoring (Critical for Exits)

### Current Status
```python
# position_manager says it checks "option price every minute"
# BUT: Need to verify we're fetching option quotes, not just underlying
```

### Required
```python
# For each open option position:
option_snapshot = alpaca.get_option_snapshot(option_symbol)
mid_price = (snapshot['quote']['bp'] + snapshot['quote']['ap']) / 2

# Fallback if quotes unavailable:
# → Use underlying-based exits instead
```

**Why:** Can't exit based on option price if you don't have option prices!

**Fix in:** `services/position_manager/monitor.py` - `update_position_price()`

---

## Implementation Priority

### CRITICAL (Before Live Trading)
1. ✅ Position sizing: 0.5-1.5% (from 5-10%)
2. ✅ Liquidity: Add OI, volume, premium floor
3. ✅ Exits: Underlying-based or wider %

### IMPORTANT (Within Week)
4. ⚠️ Liquidity ranking: Score contracts by quality
5. ⚠️ Momentum: Use ret_5m/ret_15m instead of distance_sma20
6. ⚠️ Chop filter: Detect ranging markets

### NICE TO HAVE
7. 📋 Option quote monitoring: Verify implementation

---

## Suggested Fix Order

**Session 1 (30 minutes):**
- Fix position sizing (0.5-1.5%)
- Add contract quantity hard cap (1-5)
- Fix spread calculation (use mid)

**Session 2 (45 minutes):**
- Add OI/volume/premium checks
- Implement liquidity scoring
- Rank contracts by quality

**Session 3 (60 minutes):**
- Rewrite exit logic (underlying-based)
- Add chop filter
- Improve momentum confirmation

---

## Expert's Offer

> "If you want, paste your current `validate_option_liquidity()` and `calculate_position_size()` 
> and I'll rewrite them into a 'liquidity-first + safe sizing' version"

**Response:** Yes please! Current code is in:
- `services/dispatcher/alpaca/options.py`
- Lines 234-266: `validate_option_liquidity()`
- Lines 269-318: `calculate_position_size()`

Would greatly appreciate production-grade rewrite of these functions!

---

## Current vs Production Comparison

| Aspect | Current (Paper) | Production (Live) |
|--------|----------------|-------------------|
| Position Size | 5-10% | 0.5-1.5% |
| Spread Check | < 10% | < 8-10% with mid calc |
| OI Check | None | ≥ 500 |
| Volume Check | None | ≥ 200 |
| Premium Floor | None | ≥ $0.30 |
| Stop Loss | -2% option | -25-40% or underlying-based |
| Take Profit | +10% option | +35-80% or underlying-based |
| Liquidity Ranking | Closest strike | Quality score |
| Chop Filter | None | SMA slope + oscillation |

---

## Impact Assessment

**Current Risk Level:** HIGH for live trading  
**With Fixes:** LOW-MODERATE for live trading  
**Paper Trading:** ACCEPTABLE as-is (learning/testing)

**Biggest Risks Right Now:**
1. **Position sizing** - Could lose 10% account on bad day
2. **Exit stops** - Will get chopped out repeatedly  
3. **Liquidity** - Might get stuck in illiquid contracts

---

## Files Needing Updates

### Critical:
1. `services/dispatcher/alpaca/options.py`
   - calculate_position_size() - Line 269
   - validate_option_liquidity() - Line 234
   - select_optimal_strike() - Add scoring

2. `services/position_manager/monitor.py`
   - check_exit_conditions() - Rewrite for options
   - update_position_price() - Verify option quotes

### Important:
3. `services/signal_engine_1m/rules.py`
   - Add chop filter
   - Improve momentum confirmation

4. `services/feature_computer_1m/features.py`
   - Add ret_5m, ret_15m
   - Add sma20_slope

---

## Recommendation

**For Paper Trading:** Continue as-is, collect data, learn  
**For Live Trading:** Implement Priority 1-3 fixes first (90 minutes of work)

**Next Steps:**
1. User reviews this assessment
2. Provide expert rewrite of sizing + validation
3. Implement and test in paper
4. Monitor for 1-2 weeks
5. Then consider live with small size

---

---

## Additional Professional Best Practices (Advanced)

### Contract Selection Enhancements

**Delta-Driven Selection:**
- Use delta as probability proxy (~0.50 = 50% ITM probability)
- Directional: 0.50-0.60 delta (ATM to slightly OTM)
- Income: 0.70+ delta for selling (70% OTM probability)
- Target delta range, not just strike proximity

**DTE Best Practices:**
- Short premium: Enter 30-60 DTE, exit at 21 DTE (before gamma spike)
- Long premium: Avoid final week (90% decay), exit 2+ days before expiration
- Vary by strategy: Quick scalps (< 7 DTE), core outlooks (21-45 DTE)

### Position Sizing Advanced

**Kelly Criterion:**
- Optimal growth: Kelly % = (Win% * AvgWin - Loss% * AvgLoss) / AvgWin
- Use half-Kelly (50%) to reduce variance
- Requires backtested win rates

**Volatility-Adjusted:**
- Size inversely to ATR: High ATR = smaller size
- Formula: Position = RiskAmount / (ATR × Factor)
- Keeps dollar risk consistent across volatility regimes

**3-5-7 Rule:**
- 3% max risk per trade
- 5% max total at-risk capital
- 7% target profit per winner

**Scaling In/Out:**
- Start 50% position, add 50% if trade confirms
- Take partial profits (50-75%) at first target
- Trail remainder with wider stop

### Exit Strategy Advanced

**Trailing Stops:**
- Lock in gains: Move stop to +50% after +100% profit
- Trail underlying: Exit if drops X% from peak
- Prevents round-trips (winning → losing)

**Time-Based Exits:**
- Exit longs 2 days before expiration (avoid final decay)
- Exit shorts at 21 DTE (avoid gamma spike)
- Day trades: Exit if no follow-through in 30-60 min

**Rolling Positions:**
- Roll shorts at 21 DTE if still at risk
- Roll longs up to higher strike to bank profits
- Extends trade while managing risk

**Conditional Exits:**
- Exit if trend_state flips (thesis invalidated)
- Exit immediately on big vol spike against position
- Take profits at 50-75% of expected move (high probability zone)

**Partial Exits:**
- Sell 50% at first target
- Trail remaining 50% with wider stop
- Secures some profit while keeping upside

### Greeks & IV Advanced

**Dynamic Greek Monitoring:**
- If delta > 0.85 on long call: Consider profit (acts like stock now)
- If theta per day > 5% of option value: Exit to avoid decay
- Monitor gamma risk near expiration

**Portfolio Greeks:**
- Track net delta (total directional exposure)
- Track net vega (volatility exposure)
- Cap: Net delta ≤ equivalent of X stock shares
- Hedge if exposure too one-sided

**IV Regime Filters:**
- IV Rank = (Current IV - Min IV) / (Max IV - Min IV) over lookback
- High IV (> 80 percentile): Favor short premium, avoid long
- Low IV (< 20 percentile): Favor long premium, avoid short
- Normal IV: Trade both sides

**IV vs Realized Vol:**
- If IV >> Realized Vol: Options overpriced, favor selling
- If IV << Realized Vol: Options underpriced, favor buying
- Mean reversion opportunity

---

## Implementation Roadmap (Professional Grade)

### Phase 1: Critical Safety (Before Live) - 90 minutes
1. **Position Sizing:** 0.5-1.5% (from 5-10%)
2. **Liquidity:** Add OI ≥ 500, volume ≥ 200, premium ≥ $0.30, fix spread calc
3. **Exits:** Underlying-based or -25-40% (from -2%)
4. **Hard caps:** 1-5 contracts max initially

### Phase 2: Quality Improvements - 2 hours
5. **Contract Scoring:** Quality > proximity (spread + OI + volume + delta)
6. **Delta-Driven Selection:** Target 0.50-0.60 delta for directional
7. **Momentum:** Add ret_5m, ret_15m instead of distance_sma20
8. **Chop Filter:** SMA slope + oscillation detection

### Phase 3: Advanced Features - 3 hours
9. **IV Rank:** Calculate and use for trade filtering
10. **Trailing Stops:** Lock profits, let winners run
11. **Time Exits:** 21 DTE for shorts, 2 days before exp for longs
12. **Portfolio Greeks:** Track net delta/vega

### Phase 4: Professional Polish - 4 hours
13. **Kelly Sizing:** Optimal growth with half-Kelly safety
14. **ATR Sizing:** Volatility-adjusted position sizing
15. **Rolling:** Auto-roll shorts at 21 DTE if at risk
16. **Scaling:** 50% entry, add on confirmation
17. **Partial Exits:** Take 50-75% at first target

---

## Priority Assessment

**Must Have (P0):** Phase 1 (safety basics)  
**Should Have (P1):** Phase 2 (quality)  
**Nice to Have (P2):** Phase 3-4 (advanced/professional)

**For Paper Trading:** Current + Phase 1 sufficient  
**For Small Live:** Phase 1 + Phase 2 minimum  
**For Full Live:** All phases recommended

---

## Questions for Expert

1. **Position sizing:** Start at 0.5% and scale up, or jump to 1.0-1.5%?
2. **Exit logic:** Underlying-based or wider % (which do you prefer)?
3. **Liquidity thresholds:** OI 500, volume 200 - adjust by ticker size?
4. **Contract scoring:** Weights (spread 40%, OI 30%, vol 20%, delta 10%) good?
5. **IV Rank lookback:** 252 days (1 year) or 63 days (quarter)?
6. **Delta targets:** 0.50-0.60 for directional, or wider (0.40-0.70)?
7. **Rolling rules:** Always roll at 21 DTE or only if position at risk?

**Ready for production-grade code when you are!**
