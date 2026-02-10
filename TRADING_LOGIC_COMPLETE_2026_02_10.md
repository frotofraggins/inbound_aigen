# Complete Trading Logic & System Architecture
**For AI Optimization & Performance Improvement**

**Date:** 2026-02-10  
**Purpose:** Comprehensive reference for AI agents to understand and optimize trading system  
**Current Performance:** 28.6% win rate, -15.8% avg P&L (Target: 50-60% win rate)

---

## Executive Summary

This document explains EVERY decision the trading system makes from raw data to executed trades. Use this to identify optimization opportunities and improve the 28.6% win rate.

**System Flow:**
```
Market Data → Technical Indicators → Signal Generation → Risk Gates → Position Sizing → Execution → Exit Monitoring
```

---

## 1. Data Ingestion Layer

### 1.1 Market Data (lane_telemetry)
- **Source:** Alpaca Market Data API
- **Frequency:** 1-minute bars
- **Data:** OHLCV (Open, High, Low, Close, Volume)
- **Storage:** 145,415 records currently
- **Service:** market-data-stream (1/1 running)

### 1.2 News Data (inbound_events_raw)
- **Sources:** 
  - RSS feeds (active, 7,400 articles)
  - Alpaca WebSocket (disabled, can be enabled)
- **Frequency:** Every minute
- **Storage:** Raw articles with metadata
- **Service:** rss-ingest (scheduled), news-stream (disabled)

### 1.3 Sentiment Analysis (inbound_events_classified)
- **Engine:** FinBERT (financial BERT model)
- **Output:** Sentiment score -1.0 to +1.0
- **Storage:** 7,400 classified articles
- **Service:** classifier (scheduled every 5 minutes)

### 1.4 AI Watchlist (ticker_universe)
- **Engine:** AWS Bedrock Claude 3.5 Sonnet
- **Frequency:** Weekly
- **Output:** 25-50 tickers with high potential
- **Storage:** 88 tickers, 54 active in watchlist
- **Service:** ticker-discovery (scheduled weekly)

---

## 2. Feature Engineering (lane_features)

**Service:** feature-computer-1m (runs every minute)  
**Records:** 61,469 computed features

### 2.1 Computed Indicators

```python
# Moving Averages
sma20 = mean(close, 20)  # 20-period simple moving average
sma50 = mean(close, 50)  # 50-period simple moving average

# Price Distance (Relative Position)
distance_sma20 = (close - sma20) / sma20  # % above/below SMA20
distance_sma50 = (close - sma50) / sma50  # % above/below SMA50

# Trend State (Directional Bias)
if close > sma20 AND sma20 > sma50:
    trend_state = +1  # UPTREND (bullish)
elif close < sma20 AND sma20 < sma50:
    trend_state = -1  # DOWNTREND (bearish)
else:
    trend_state = 0   # NO CLEAR TREND (neutral)

# Volume Analysis
volume_ratio = current_volume / avg_volume_20  # Volume surge detection
vol_ratio = current_volatility / baseline_volatility  # Volatility regime
```

### 2.2 Feature Interpretation

| Feature | Range | Meaning |
|---------|-------|---------|
| distance_sma20 | -0.05 to +0.05 | Price position relative to SMA20 |
| distance_sma50 | -0.10 to +0.10 | Price position relative to SMA50 |
| trend_state | -1, 0, +1 | Strong downtrend, neutral, strong uptrend |
| volume_ratio | 0 to 5+ | Current vs average volume (2.0+ = surge) |
| vol_ratio | 0.5 to 2.0 | Volatility regime (1.0 = normal) |

---

## 3. Signal Generation Logic (signal_engine_1m)

**Service:** signal-engine-1m (scheduled every minute)  
**Output:** dispatch_recommendations (16,893 signals generated)

### 3.1 Signal Generation Process

```
1. Get top 30 tickers from watchlist
2. For each ticker:
   a. Load latest features (required)
   b. Load recent sentiment (optional)
   c. Check cooldown (30 minutes after last trade)
   d. Check gap fade opportunity (morning only)
   e. Compute signal (main logic)
   f. If actionable (not HOLD), save to dispatch_recommendations
```

### 3.2 Core Signal Logic (rules.py)

#### Step 1: Determine Primary Direction (FROM PRICE + TREND, NOT SENTIMENT!)

```python
# CRITICAL: Direction comes from technical analysis, NOT news sentiment

# Strong Uptrend (Options Allowed)
if (close above SMA20) AND (trend_state == +1) AND (not stretched beyond 2%):
    primary_direction = "BULL"
    can_trade_options = True

# Weak Uptrend (Stocks Only)
elif (close above SMA20) AND (trend_state >= 0) AND (not stretched):
    primary_direction = "BULL"
    can_trade_options = False

# Strong Downtrend (Options Allowed)
elif (close below SMA20) AND (trend_state == -1) AND (not stretched):
    primary_direction = "BEAR"
    can_trade_options = True

# Weak Downtrend (Stocks Only)
elif (close below SMA20) AND (trend_state <= 0) AND (not stretched):
    primary_direction = "BEAR"
    can_trade_options = False

# No Setup
else:
    primary_direction = "NONE"  # HOLD signal
```

#### Step 2: Check Breakout Confirmation

```python
# Require price movement to filter choppy markets

breakout_threshold = 1.0%  # 1% from SMA20

if primary_direction == "BULL":
    if distance_sma20 > +0.01:  # +1% above SMA20
        breakout_confirmed = True
        move_penalty = 1.0  # No penalty
    else:
        breakout_confirmed = False
        move_penalty = 0.5  # 50% confidence reduction

if primary_direction == "BEAR":
    if distance_sma20 < -0.01:  # -1% below SMA20
        breakout_confirmed = True
        move_penalty = 1.0
    else:
        breakout_confirmed = False
        move_penalty = 0.5  # 50% confidence reduction
```

#### Step 3: Volume Confirmation (HARD GATE)

```python
# Volume thresholds (CRITICAL for quality)
VOLUME_KILL_THRESHOLD = 0.5x    # Block if < 0.5x average (no liquidity)
VOLUME_MIN_FOR_TRADE = 1.5x     # Minimum for any trade
VOLUME_SURGE_THRESHOLD = 2.0x   # Strong confirmation

if volume_ratio < 0.5:
    return HOLD  # HARD BLOCK - no trade

elif volume_ratio < 1.5:
    volume_mult = 0.6  # 40% confidence reduction (weak volume)

elif volume_ratio < 2.0:
    volume_mult = 1.0  # No adjustment (normal volume)

elif volume_ratio < 3.0:
    volume_mult = 1.15  # +15% boost (strong volume)

elif volume_ratio < 5.0:
    volume_mult = 1.25  # +25% boost (volume surge)

else:
    volume_mult = 1.35  # +35% boost (extreme surge)
```

#### Step 4: Compute Base Confidence (FROM TECHNICALS ONLY)

```python
# Trend alignment (0.0 to 1.0)
if trend_state == primary_direction:
    trend_alignment = 1.0  # Strong trend
else:
    trend_alignment = 0.5  # Weak trend

# Setup quality (0.0 to 1.0)
# Better entry = closer to SMA20
setup_quality = 1.0 - min(abs(distance_sma20) / 0.02, 1.0)

# Volatility appropriateness (0.5 to 1.0)
if 0.8 <= vol_ratio <= 1.3:
    vol_appropriateness = 1.0  # Normal regime
elif vol_ratio < 0.8:
    vol_appropriateness = 0.7  # Compressed (options cheap but low movement)
else:
    vol_appropriateness = 0.5  # High (options expensive)

# BASE CONFIDENCE (before sentiment, volume, move penalties)
base_confidence = (
    0.35 * trend_alignment +      # 35% weight - trend strength
    0.25 * setup_quality +         # 25% weight - entry quality
    0.20 * vol_appropriateness +   # 20% weight - volatility regime
    0.20 * 1.0                     # 20% weight - base conviction
)
```

#### Step 5: Apply Sentiment as Confidence Scaler (NOT GATE!)

```python
# CRITICAL: Sentiment modifies confidence, does NOT determine direction

# Sentiment alignment check
if (primary_direction == "BULL" AND sentiment_score > 0) OR \
   (primary_direction == "BEAR" AND sentiment_score < 0):
    sentiment_aligns = True
    # Boost: +0% to +25% based on strength and news count
    sentiment_boost = 1 + (0.25 * abs(sentiment_score) * min(news_count/5, 1.0))
else:
    sentiment_aligns = False
    # Penalty: -0% to -20% based on strength and news count
    sentiment_boost = 1 - (0.20 * abs(sentiment_score) * min(news_count/5, 1.0))

# If no news or neutral sentiment
if news_count == 0 OR sentiment_score == 0:
    sentiment_boost = 1.0  # No adjustment
```

#### Step 6: Detect Momentum Urgency (NEW - Feb 6, 2026)

```python
# Urgent momentum = enter immediately at breakout START, not end

if (volume_ratio >= 2.5) AND \
   (abs(distance_sma20) >= 0.01) AND \
   (trend_state == primary_direction):
    # URGENT: Volume surge + breakout + strong trend
    momentum_boost = 1.25  # +25% confidence boost
    entry_urgency = "IMMEDIATE"
    
elif (volume_ratio >= 2.0) AND (abs(distance_sma20) >= 0.008):
    # Good momentum but not urgent
    momentum_boost = 1.10  # +10% boost
    entry_urgency = "NORMAL"
    
else:
    momentum_boost = 1.0  # No boost
    entry_urgency = "NORMAL"
```

#### Step 7: Calculate Final Confidence

```python
final_confidence = (
    base_confidence * 
    sentiment_boost * 
    volume_mult * 
    move_penalty * 
    momentum_boost
)

# Clamp to 0.0 - 1.0
final_confidence = min(max(final_confidence, 0.0), 1.0)
```

#### Step 8: Instrument Selection & Strategy Type

```python
# Options require strong trend AND normal/low volatility
if (can_trade_options) AND (vol_ratio <= 1.3):
    instrument = 'CALL' if primary_direction == "BULL" else 'PUT'
    
    # Adaptive confidence threshold (higher when vol is high)
    if vol_ratio > 1.2:
        threshold_adjustment = 0.05 * ((vol_ratio - 1.2) / 0.2)
        adaptive_threshold = 0.65 + threshold_adjustment  # Up to 0.75 max
    else:
        adaptive_threshold = 0.65
    
    # Day trade vs Swing trade
    if (confidence >= adaptive_threshold) AND (volume_ratio >= 2.0):
        strategy_type = 'day_trade'  # 0-1 DTE options, aggressive
        min_confidence = adaptive_threshold
    elif confidence >= 0.50:
        strategy_type = 'swing_trade'  # 7-30 DTE options, moderate
        min_confidence = 0.50
    else:
        # Confidence too low for options
        instrument = 'STOCK'
        strategy_type = None
        min_confidence = 0.40

else:
    # No options (weak trend or high volatility)
    instrument = 'STOCK'
    strategy_type = None
    min_confidence = 0.40

# Final threshold check
if confidence < min_confidence:
    return HOLD  # Below threshold
```

### 3.3 Gap Fade Strategy (Morning Only)

**Enabled:** 9:30 AM - 10:30 AM ET  
**Logic:** Fade overnight gaps that overextend

```python
# Gap detection (pre-market move)
gap_size = (open - prev_close) / prev_close

# Gap fade conditions
if abs(gap_size) >= 0.02:  # 2%+ gap
    if gap_size > 0:
        # Gap UP → Fade DOWN (buy puts or sell stock)
        gap_fade_direction = "BEAR"
    else:
        # Gap DOWN → Fade UP (buy calls or buy stock)
        gap_fade_direction = "BULL"
    
    # Volume confirmation still required
    if volume_ratio >= 1.5:
        return gap_fade_signal(direction, confidence=0.60)
```

### 3.4 Confidence Thresholds

| Threshold | Value | Purpose |
|-----------|-------|---------|
| Day Trade Options | 0.65 (adaptive up to 0.75) | High confidence + volume surge |
| Swing Trade Options | 0.50 | Moderate confidence, longer hold |
| Stock Trades | 0.40 | Lower risk fallback |

---

## 4. Risk Management (Dispatcher)

**Service:** dispatcher-service + dispatcher-tiny-service (both 1/1 running)  
**Output:** dispatch_executions (442 trades executed)

### 4.1 The 11 Risk Gates

Every signal passes through 11 gates before execution. ONE failure = SKIP.

#### Gate 1: Market Hours
```python
if not (9:30 AM <= current_time < 4:00 PM ET):
    SKIP "Outside market hours"
```

#### Gate 2: Buying Power
```python
required_capital = entry_price * qty
if required_capital > account.buying_power:
    SKIP "Insufficient buying power"
```

#### Gate 3: Daily Loss Limit (Kill Switch)
```python
if account.daily_pnl < -0.10 * account.equity:  # -10%
    SKIP "Daily loss limit hit (-10%)"
```

#### Gate 4: Position Limit
```python
if account.active_positions >= 5:
    SKIP "Max 5 concurrent positions"
```

#### Gate 5: Ticker Cooldown
```python
if last_trade_time < 30 minutes ago:
    SKIP "Ticker on cooldown (30 min)"
```

#### Gate 6: Volume Confirmation (Already in Signal)
```python
# This is checked in signal generation, but re-validated
if volume_ratio < 0.5:
    SKIP "Volume too low for execution"
```

#### Gate 7: Confidence Threshold
```python
if confidence < required_threshold:
    SKIP "Confidence below threshold"
```

#### Gate 8: Conflicting Position
```python
if has_open_position(ticker):
    if new_direction != current_direction:
        SKIP "Would conflict with open position"
```

#### Gate 9: Total Notional Limit
```python
total_notional = sum(all open positions' notional values)
if total_notional > 0.95 * account.equity:
    SKIP "Total notional at 95% of equity"
```

#### Gate 10: Option Quality (Future)
```python
# TODO: Implement when greeks available
if instrument in ['CALL', 'PUT']:
    if iv_percentile > 80:
        SKIP "IV too high (>80th percentile)"
    if bid_ask_spread > 0.10:
        SKIP "Spread too wide (>10%)"
    if option_volume < 100:
        SKIP "Option volume too low"
```

#### Gate 11: Contract Existence (Options Only)
```python
if instrument in ['CALL', 'PUT']:
    if not contract_exists(ticker, expiration, strike):
        SKIP "Contract not available"
```

### 4.2 Position Sizing

**Multi-Tier System** (Based on confidence)

#### Large Account Tiers
```python
if confidence >= 0.75:
    tier = 1
    allocation = 0.20  # 20% of capital
elif confidence >= 0.65:
    tier = 2
    allocation = 0.15  # 15% of capital
elif confidence >= 0.55:
    tier = 3
    allocation = 0.10  # 10% of capital
else:
    tier = 4
    allocation = 0.05  # 5% of capital

notional = account.equity * allocation
qty = notional / entry_price
```

#### Tiny Account Sizing
```python
# Conservative - fixed percentage
allocation = 0.08  # 8% max per position
notional = account.equity * allocation
qty = notional / entry_price
```

### 4.3 Stop Loss & Take Profit Calculation

```python
# Stop Loss (Risk Management)
if instrument == 'STOCK':
    stop_distance = 0.02  # 2% for stocks
elif strategy_type == 'day_trade':
    stop_distance = 0.40  # 40% for day trade options
else:
    stop_distance = 0.30  # 30% for swing trade options

stop_loss = entry_price * (1 - stop_distance) if LONG else entry_price * (1 + stop_distance)

# Take Profit (Profit Target)
if instrument == 'STOCK':
    take_profit_distance = 0.03  # 3% for stocks
elif strategy_type == 'day_trade':
    take_profit_distance = 0.80  # 80% for day trade options
else:
    take_profit_distance = 0.60  # 60% for swing trade options

take_profit = entry_price * (1 + take_profit_distance) if LONG else entry_price * (1 - take_profit_distance)

# Max Hold Time
if strategy_type == 'day_trade':
    max_hold = 240 minutes  # 4 hours
else:
    max_hold = 1440 minutes  # Until market close (1 day)
```

---

## 5. Position Monitoring (position_manager)

**Service:** position-manager-service + position-manager-tiny-service (both 1/1 running)  
**Frequency:** Every minute  
**Monitors:** 14 open positions

### 5.1 Exit Conditions (First Match Wins)

```python
# Check every minute for ALL open positions

# 1. STOP LOSS (Risk management)
if current_price <= stop_loss (for LONG) or current_price >= stop_loss (for SHORT):
    EXIT "Stop loss hit"
    
# 2. TAKE PROFIT (Profit target)
if current_price >= take_profit (for LONG) or current_price <= take_profit (for SHORT):
    EXIT "Take profit hit"

# 3. TRAILING STOP (Protect profits - ENABLED Feb 6, 2026)
if peak_gain >= 0.20:  # 20%+ profit achieved
    trailing_stop = peak_price * 0.75  # Lock in 75% of peak gain
    if current_price <= trailing_stop (for LONG):
        EXIT "Trailing stop (protecting 75% of peak)"

# 4. TIME STOP (Max hold exceeded)
if time_held >= max_hold_minutes:
    EXIT "Max hold time reached"

# 5. MARKET CLOSE (Options must close)
if instrument in ['CALL', 'PUT'] and current_time >= 3:55 PM ET:
    EXIT "Market close (options)"

# 6. CATASTROPHIC LOSS (Emergency)
if current_loss >= 0.50:  # -50%
    EXIT "Catastrophic loss override"
```

### 5.2 Trailing Stop Logic (NEW - Feb 6, 2026)

```python
# Track peak price during position lifetime
peak_price = max(all prices seen since entry)
peak_gain = (peak_price - entry_price) / entry_price

# If position reaches 20%+ gain at any point
if peak_gain >= 0.20:
    trailing_stop_enabled = True
    
    # Lock in 75% of peak gain
    trailing_stop_price = entry_price + (peak_price - entry_price) * 0.75
    
    # Update stop as price rises
    if current_price > peak_price:
        peak_price = current_price
        trailing_stop_price = entry_price + (peak_price - entry_price) * 0.75

# Exit if price falls to trailing stop
if trailing_stop_enabled and current_price <= trailing_stop_price:
    realized_gain = (trailing_stop_price - entry_price) / entry_price
    EXIT f"Trailing stop: Locked in {realized_gain:.1%} gain"
```

---

## 6. Learning System (Future - After 50 Trades)

**Current:** 28 trades in position_history (22 more needed)  
**Status:** Data collection phase

### 6.1 What Gets Captured

For each completed trade:
```python
position_history = {
    'ticker': symbol,
    'entry_price': entry_price,
    'exit_price': exit_price,
    'entry_time': timestamp,
    'exit_time': timestamp,
    'hold_duration_minutes': minutes,
    'pnl_dollars': exit - entry,
    'pnl_pct': (exit - entry) / entry,
    'exit_reason': reason,
    'instrument_type': 'CALL/PUT/STOCK',
    'strategy_type': 'day_trade/swing_trade',
    
    # Peak tracking (for learning)
    'max_favorable_excursion': peak_gain,  # Best unrealized gain
    'max_adverse_excursion': worst_drawdown,  # Worst unrealized loss
    
    # Entry conditions (snapshot)
    'features_at_entry': {...},  # All technical indicators
    'sentiment_at_entry': {...},  # All sentiment data
    'confidence_at_entry': float,
    
    # Exit conditions
    'price_at_exit': float,
    'trailing_stop_triggered': bool
}
```

### 6.2 Planned AI Learning (Phase 4+)

Once 50+ trades:
```python
# Pattern Recognition
- Identify which setups win vs lose
- Learn optimal entry timing
- Adjust confidence scoring

# Risk Calibration
- Refine position sizing tiers
- Optimize stop loss distances
- Improve trailing stop triggers

# Feature Importance
- Which indicators matter most
- Sentiment impact quantification
- Volume thresholds optimization
```

---

## 7. Current Performance Analysis

**As of 2026-02-10:**
- **Total Trades:** 28
- **Winners:** 8 (28.6%)
- **Losers:** 20 (71.4%)
- **Avg P&L:** -15.8%

### 7.1 Loss Analysis from Documentation

**From PATTERN_ANALYSIS_FINDINGS_2026_02_07.md:**

**Primary Loss Causes:**
1. **Peak Reversals (31%)** - Positions hit good gains but reversed before take profit
   - **FIX:** Trailing stops enabled Feb 6 ✅
   - **Expected Impact:** Save $600-700 per cycle

2. **Late Entries (46%)** - Entered after move was exhausted
   - **FIX:** Momentum urgency detection added Feb 6 ✅
   - **Boost:** +25% confidence for early breakout entries
   - **Expected Impact:** Reduce late entries significantly

3. **Proper Exits (23%)** - Stop loss correctly triggered
   - **Status:** Working as designed ✅
   - **No changes needed**

### 7.2 Identified Issues to Fix

**From Current Signal Logic Review:**

1. **First Hour Trading**
   - System allows trades 9:30-10:30 AM with reduced confidence
   - Morning volatility = higher risk
   - **Recommendation:** Consider blocking first 30 minutes entirely

2. **Sentiment Weight**
   - Sentiment can boost/penalty up to ±25%/±20%
   - May be too aggressive given 28% win rate
   - **Recommendation:** Reduce sentiment impact to ±15%/±10%

3. **Volume Thresholds**
   - VOLUME_MIN_FOR_TRADE = 1.5x
   - May be letting through marginal setups
   - **Recommendation:** Test raising to 1.8x

4. **Confidence Thresholds**
   - Day trade: 0.65, Swing: 0.50, Stock: 0.40
   - Lower thresholds may generate noise trades
   - **Recommendation:** Test raising by 0.05 across board

5. **Options Greeks Missing**
   - No IV percentile filtering
   - No bid/ask spread checking
   - Buying expensive options reduces profit potential
   - **Recommendation:** Implement IV rank >30th percentile requirement

---

## 8. Optimization Recommendations for AI

### 8.1 Immediate (Can Implement Now)

1. **Raise Volume Threshold**
   ```python
   VOLUME_MIN_FOR_TRADE = 1.8  # From 1.5
   ```
   - **Why:** Filter marginal liquidity trades
   - **Expected:** Fewer but higher quality signals

2. **Raise Confidence Thresholds**
   ```python
   CONFIDENCE_DAY_TRADE = 0.70    # From 0.65
   CONFIDENCE_SWING_TRADE = 0.55  # From 0.50
   CONFIDENCE_STOCK = 0.45        # From 0.40
   ```
   - **Why:** 28% win rate suggests noise in signals
   - **Expected:** Trade less but better quality

3. **Reduce Sentiment Impact**
   ```python
   sentiment_boost_max = 1.15  # From 1.25 (max +15%)
   sentiment_penalty_max = 0.90  # From 0.80 (max -10%)
   ```
   - **Why:** Sentiment may not be as predictive as hoped
   - **Expected:** Less variance from news

4. **Block First 30 Minutes**
   ```python
   if time(9, 30) <= now < time(10, 00):
       confidence *= 0.5  # Heavy penalty instead of block
   ```
   - **Why:** Morning volatility = unpredictable
   - **Expected:** Avoid whipsaw trades

5. **Tighten Trailing Stops**
   ```python
   trailing_stop_trigger = 0.15  # From 0.20 (trigger at +15% gain)
   trailing_stop_keep = 0.80     # From 0.75 (keep 80% of peak)
   ```
   - **Why:** Lock in gains earlier
   - **Expected:** Convert more reversals to wins

### 8.2 Medium-Term (Need 50+ Trades)

1. **Machine Learning Confidence Adjustment**
   - Train model on 50+ outcomes
   - Learn: `real_probability_win = f(base_confidence, features)`
   - Apply as final multiplier

2. **Feature Importance Analysis**
   - Identify which indicators actually predict wins
   - Remove noise features
   - Weight remaining features properly

3. **Strategy Specialization**
   - Some setups may work better for stocks vs options
   - Some times of day may be more profitable
   - Learn optimal instrument for each setup type

### 8.3 Long-Term (Need 100+ Trades + Greeks Data)

1. **IV Rank Filtering**
   ```python
   if iv_percentile > 80:
       SKIP "Options too expensive"
   ```

2. **Delta-Adjusted Position Sizing**
   ```python
   # Options with higher delta = closer to stock behavior
   if delta > 0.70:
       allocation *= 1.2  # Can size up slightly
   ```

3. **Volatility Smile Analysis**
   - Identify mispriced options
   - Trade options with favorable skew

---

## 9. Expected Improvement Trajectory

**Current State:**
- Win Rate: 28.6%
- Avg P&L: -15.8%
- Grade: D (40%)

**After Immediate Fixes:**
- Win Rate: 40-45% (expected)
- Avg P&L: -5% to -8%
- Grade: C+ (70%)
- **Reason:** Trailing stops + momentum urgency + higher thresholds

**After Medium-Term (50+ trades):**
- Win Rate: 50-55%
- Avg P&L: +5% to +8%
- Grade: B+ (85%)
- **Reason:** ML confidence calibration + feature selection

**After Long-Term (100+ trades + Greeks):**
- Win Rate: 55-60%
- Avg P&L: +12% to +15%
- Grade: A (95%)
- **Reason:** Full Greeks integration + strategy specialization

---

## 10. Testing Methodology

### 10.1 How to Test Changes

1. **Backtest on 28 Historical Trades**
   ```python
   # Apply new rules to existing position_history
   # Count how many outcomes would change
   # Calculate new win rate and avg P&L
   ```

2. **Paper Trading Validation**
   - Keep system running with new rules
   - Collect 10-20 more trades
   - Compare vs previous 28 trades
   - If improvement, keep changes

3. **A/B Testing (Advanced)**
   - Run two dispatchers with different rules
   - Split signals 50/50
   - Compare outcomes after 50 trades each

### 10.2 Metrics to Track

**Per Trade:**
- Entry conditions (all features snapshot)
- Exit conditions (reason, price, timing)
- Peak gain reached (MFE)
- Worst drawdown (MAE)
- Hold duration
- Final P&L

**Aggregate:**
- Win rate %
- Average P&L %
- Median P&L %
- Max drawdown
- Sharpe ratio (once enough trades)
- Profit factor (gross profit / gross loss)

---

## 11. Key Files for AI to Modify

**Signal Generation:**
- `services/signal_engine_1m/rules.py` - Core trading logic
- `services/signal_engine_1m/gap_fade.py` - Morning reversal strategy

**Risk Management:**
- `services/dispatcher/risk/gates.py` - 11 risk gates
- `services/dispatcher/sim/pricing.py` - Position sizing
- `services/dispatcher/config.py` - Thresholds and limits

**Exit Management:**
- `services/position_manager/monitor.py` - Exit conditions
- `services/position_manager/exits.py` - Trailing stop logic

**Configuration:**
- `config/trading_params.json` - All tunable parameters

---

## 12. System Health Indicators

**Database Check:**
```bash
python scripts/check_database_tables.py
```

**Service Status:**
```bash
aws scheduler list-schedules --region us-west-2
aws ecs list-services
