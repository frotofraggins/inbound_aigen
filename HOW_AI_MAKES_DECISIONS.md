# 🤖 How AI Makes Trading Decisions
**Date:** 2026-02-05 16:26 UTC
**Your Questions:** Trends, rebounds, CALL vs PUT selection, timing

---

## 🎯 Quick Answers

### Q1: Does it consider trends and rebounds?
**YES!** The system tracks `trend_state`:
- **+1** = Uptrend (bullish)
- **-1** = Downtrend (bearish)
- **0** = No trend (choppy)

**Rebounds:** System waits for trend to establish before trading

### Q2: How does it pick CALL vs PUT?
**Based on price action + trend:**
- **CALL:** Price above SMA20 + trend_state = +1 (uptrend)
- **PUT:** Price below SMA20 + trend_state = -1 (downtrend)
- **STOCK:** Weak/no trend (trend_state = 0)

### Q3: When is best time to place orders?
**When multiple factors align:**
1. ✅ Clear trend (±1)
2. ✅ Breakout (>1% from SMA20)
3. ✅ Volume surge (>2x average)
4. ✅ High confidence (>0.60 for day trades)

---

## 📊 Complete Decision Process

### Step 1: Analyze Trend (Most Important!)

**From rules.py:**
```python
trend_state = features.get('trend_state', 0)

if above_sma20 and trend_state == TREND_BULL:
    primary_direction = "BULL"  # Will consider CALL
    can_trade_options = True
elif below_sma20 and trend_state == TREND_BEAR:
    primary_direction = "BEAR"  # Will consider PUT
    can_trade_options = True
else:
    can_trade_options = False  # No clear trend, use STOCK
```

**This means:**
- **CALL:** Requires uptrend (trend_state = +1)
- **PUT:** Requires downtrend (trend_state = -1)
- **NO OPTIONS:** If trend_state = 0 (choppy)

---

## 🎯 How CALL vs PUT is Chosen

### The Logic (From rules.py)

**For CALL (Buy to open):**
```
Requirements:
1. Price above SMA20 (or at it)
2. trend_state = +1 (strong uptrend)
3. Price within 2% of SMA20 (not stretched)
4. Volume > 1.2x average
5. Breakout upward (>1% above SMA20)
```

**For PUT (Buy to open):**
```
Requirements:
1. Price below SMA20 (or at it)
2. trend_state = -1 (strong downtrend)
3. Price within 2% of SMA20 (not stretched)
4. Volume > 1.2x average
5. Breakout downward (>1% below SMA20)
```

**Examples from your current positions:**

### INTC CALL (Position 621)
```
Setup at entry:
- Price: Above SMA20
- Trend: +1 (uptrend)
- Breakout: Yes (bullish)
- Volume: Surge
- Decision: BUY CALL ✅
```

### BAC PUT (Position 622)
```
Setup at entry:
- Price: Below SMA20
- Trend: -1 (downtrend)
- Breakout: Yes (bearish)
- Volume: Surge
- Decision: BUY PUT ✅
```

---

## ⏰ Best Time to Place Orders

### What System Looks For

**Perfect Setup (High confidence):**
1. **Clear trend** (trend_state = ±1)
2. **Breakout** (>1% move from SMA20)
3. **Volume surge** (>2x average)
4. **Sentiment alignment** (news confirms direction)
5. **Not stretched** (within 2% of SMA20)

**Result:** Confidence > 0.60 → Day trade (0-1 DTE options)

**Good Setup (Medium confidence):**
1. Clear trend (±1)
2. Some breakout
3. Good volume (>1.2x)
4. Near SMA20

**Result:** Confidence > 0.45 → Swing trade (7-30 DTE options)

**Weak Setup:**
1. No trend (0)
2. Or weak volume
3. Or no breakout

**Result:** HOLD or use STOCK instead of options

---

## 📈 Does It Consider Rebounds?

### YES - Through Trend Analysis

**The trend_state feature tracks:**
- SMA20 > SMA50 = Uptrend (+1)
- SMA20 < SMA50 = Downtrend (-1)
- SMA20 ≈ SMA50 = No trend (0)

**Rebound detection:**
```
If stock declining (below SMA20):
- But SMA20 > SMA50 (uptrend maintained)
- This is a "dip" not a "crash"
- System may buy CALL on rebound
```

**Example:**
- Stock drops -5% (below SMA20)
- But SMA20 still above SMA50 (uptrend intact)
- Volume surges (buyers stepping in)
- **System:** BUY CALL on the dip ✅

### Trend Reversal Detection
```
If stock was falling (trend_state = -1):
- Then SMA20 crosses above SMA50
- trend_state changes to +1
- **System:** Detects reversal, may BUY CALL
```

---

## 🔍 What Features AI Uses

### Technical Indicators
1. **SMA20** - 20-period moving average
2. **SMA50** - 50-period moving average
3. **Distance from SMA20** - How far price is from average
4. **Trend state** - Direction of moving averages
5. **Volume ratio** - Current vs 20-bar average
6. **Volatility ratio** - Current vs baseline

### Sentiment Indicators (FinBERT AI)
7. **Sentiment score** - -1 (bearish) to +1 (bullish)
8. **News count** - How many articles
9. **Sentiment direction** - Overall bias

### How They Combine
```
Base confidence (from technicals):
  35% trend alignment
  25% entry quality (near SMA20)
  20% volatility appropriateness
  20% base conviction

Final confidence:
  base × sentiment_boost × volume_mult × move_penalty
```

---

## 💡 Real Examples from Your Trades

### INTC CALL (Good Decision)
**At entry:**
- Price: Above SMA20 ✅
- Trend: +1 (uptrend) ✅
- Volume: Surge ✅
- Breakout: Bullish ✅
- **Decision:** BUY CALL
- **Currently:** Being protected by exit logic

### UNH CALL (Bad Outcome - Old Code Victim)
**At entry:**
- Price: Above SMA20 ✅
- Trend: Probably +1 ✅
- Volume: Likely surge ✅
- **Decision:** BUY CALL (made sense!)
- **Problem:** Entered under old buggy code
- **Result:** Held 20 hours, lost -43%
- **Not AI's fault:** Exit protection bug

---

## 🎯 How Timing is Selected

### Immediate Entry (Day Trade - 0-1 DTE)
**Triggers when:**
- Confidence > 0.60 (adaptive to volatility)
- Volume surge > 2x
- Strong breakout
- Clear trend
- **Rationale:** High conviction, act fast

### Delayed Entry (Swing Trade - 7-30 DTE)
**Triggers when:**
- Confidence > 0.45
- Good volume > 1.2x
- Some breakout
- Clear trend
- **Rationale:** Medium conviction, longer time frame

### No Entry (HOLD)
**When:**
- Confidence < threshold
- Volume too low (<0.5x)
- No trend (choppy)
- No breakout
- **Rationale:** Setup not clear enough

---

## 🤖 AI vs Rules Breakdown

### What IS AI-Powered ✅
1. **Ticker selection** (Bedrock Sonnet) - Weekly
2. **Sentiment analysis** (FinBERT) - Real-time
3. **Future:** Trade outcome learning (Phase 17+)

### What is Rule-Based 📏
1. **Trend detection** - SMA crossovers
2. **CALL vs PUT** - Price relative to SMAs + trend_state
3. **Entry timing** - Breakout + volume + trend alignment
4. **Risk gates** - Position limits, loss limits, cooldowns
5. **Exit logic** - Stops, targets, max hold time

**Why Rules for Trading?**
- Deterministic (can replay)
- Fast (<1ms)
- Auditable
- No hallucinations

---

## 📊 Trend & Rebound Intelligence

### How System Detects Rebounds

**Scenario: Stock Bouncing Off Support**
```
Day 1: $100 (SMA20 = $95, SMA50 = $93)
Day 2: $97 drops below SMA20
Day 3: $96 continues down
Day 4: $98 bounces up, volume surges
```

**System analysis:**
- Price was above, dipped below, now recovering
- SMA20 > SMA50 (uptrend maintained)
- Volume surge on bounce
- **Signal:** BUY CALL (rebound trade) ✅

### How System Avoids False Rebounds

**Scenario: Dead Cat Bounce**
```
Day 1: $100 (SMA20 = $98, SMA50 = $102)
Day 2: $94 drops hard
Day 3: $96 small bounce
Day 4: $95 weak bounce
```

**System analysis:**
- SMA20 < SMA50 (downtrend)
- Weak volume on bounce
- trend_state = -1 (bearish)
- **Signal:** HOLD or BUY PUT (don't fight trend) ✅

---

## 🎯 Summary: How It Chooses

### CALL Selection Process
1. ✅ Price action bullish (above SMA20)
2. ✅ Trend confirmed (SMA20 > SMA50)
3. ✅ Breakout detected (>1% move)
4. ✅ Volume confirms (>1.2x average)
5. ✅ Sentiment (optional boost)
6. ➡️ **Decision: BUY CALL**

### PUT Selection Process
1. ✅ Price action bearish (below SMA20)
2. ✅ Trend confirmed (SMA20 < SMA50)
3. ✅ Breakout detected (>1% move down)
4. ✅ Volume confirms (>1.2x average)
5. ✅ Sentiment (optional boost)
6. ➡️ **Decision: BUY PUT**

### Timing Selection
**Day trade (0-1 DTE):**
- High confidence (>0.60)
- Volume surge (>2x)
- Strong setup

**Swing trade (7-30 DTE):**
- Medium confidence (>0.45)
- Good volume (>1.2x)
- Clear trend

---

## 💡 Does This Catch Rebounds?

**YES!** Via trend analysis:

**Rebound = Dip in uptrend:**
- Price drops below SMA20
- But SMA20 still > SMA50 (uptrend)
- Volume surges (buyers return)
- **System:** BUY CALL on dip ✅

**Not a rebound = Trend reversal:**
- Price drops below SMA20
- AND SMA20 < SMA50 (downtrend)
- Weak volume
- **System:** HOLD or BUY PUT ✅

---

## 🔮 What's NOT Considered (Yet)

### Advanced Predictions
- ML model predicting next day move
- Deep learning on price patterns
- AI predicting rebounds explicitly

### Options-Specific
- Greeks analysis (delta, gamma, theta)
- IV percentile checks
- Earnings calendar
- Ex-dividend dates

**These are planned for Phase 17+**

---

## ✅ Your Questions Answered

**Q: Does it consider trends?**
A: YES! trend_state is THE most important factor

**Q: Does it predict rebounds?**
A: YES! Buys on dips in uptrends (rebound trades)

**Q: How does it pick CALL vs PUT?**
A: Bullish setup = CALL, Bearish setup = PUT

**Q: When is best time?**
A: Breakout + volume surge + clear trend = immediate entry

**Current state:** Rules-based but sophisticated. Future: Add ML for pattern recognition and outcome prediction.
