# AI/ML Pipeline in Trading System

**Date:** 2026-01-29  
**Question:** "Are we using Bedrock to check these stages and verify results before making a trade?"

---

## Quick Answer

**AI is used in 2 EARLY stages** (ticker selection + sentiment), but **NOT for final trade verification**. The dispatcher uses **rule-based risk gates** before execution, not AI.

---

## Complete AI/ML Pipeline

### 🤖 Stage 1: Ticker Discovery (Bedrock Sonnet - Weekly)

**Service:** `ticker_discovery`  
**AI Model:** AWS Bedrock Claude 3.5 Sonnet  
**Purpose:** Select which stocks to watch  
**Frequency:** Weekly (not real-time)

**What It Does:**
```
Input: Market news, volume trends, sector analysis
AI Analysis: "Which 25-50 tickers have highest potential this week?"
Output: Watchlist of recommended tickers
```

**Code Location:** `services/ticker_discovery/discovery.py`

**NOT used for:** Trade validation, just ticker selection

---

### 🧠 Stage 2: Sentiment Analysis (FinBERT - Real-time)

**Service:** `classifier_worker`  
**AI Model:** FinBERT (Financial NLP model)  
**Purpose:** Analyze news sentiment  
**Frequency:** Every 5 minutes as news arrives

**What It Does:**
```
Input: RSS news articles about each ticker
AI Analysis: Sentiment score (-1 to +1) per article
Output: Average sentiment + news count per ticker
```

**Code Location:** `services/classifier_worker/nlp/model.py`

**How Sentiment is Used:**
- ✅ Boosts confidence if aligns with trade direction (up to +25%)
- ⚠️ Reduces confidence if opposes trade direction (up to -20%)
- ❌ NOT a hard gate - won't block trades
- ✅ Weighted by news count (more news = stronger signal)

**From `services/signal_engine_1m/rules.py`:**
```python
def calculate_sentiment_boost(sentiment_score, sentiment_direction, primary_direction, news_count):
    """
    Calculate sentiment boost/penalty as confidence multiplier.
    Sentiment is confidence scaler, NOT gate.
    """
    if sentiment_aligns:
        boost = 1 + (0.25 * sentiment_strength * news_weight)  # Up to +25%
    else:
        boost = 1 - (0.20 * sentiment_strength * news_weight)  # Up to -20%
```

---

### 📊 Stage 3: Signal Generation (Rule-Based - Real-time)

**Service:** `signal_engine_1m`  
**Method:** Mathematical rules (NO AI)  
**Purpose:** Generate BUY/SELL signals  
**Frequency:** Every 1 minute

**What It Uses:**
1. **Price Action:** SMA20, SMA50, breakouts
2. **Trend State:** Uptrend (+1), Downtrend (-1), Neutral (0)
3. **Volume:** Current vs 20-bar average
4. **Volatility:** Price variance
5. **Sentiment:** As confidence modifier (from Stage 2)

**Logic Type:** Mathematical/Statistical  
**NOT AI-based:** Uses fixed formulas, not machine learning

**Key Rules:**
```python
# Direction from PRICE + TREND (not sentiment!)
if above_sma20 and trend_state == TREND_BULL:
    primary_direction = "BULL"
    
# Sentiment just modifies confidence
confidence = base_confidence * sentiment_boost * volume_mult
```

---

### 🛡️ Stage 4: Risk Gates (Rule-Based - Before Trade)

**Service:** `dispatcher`  
**Method:** Risk management rules (NO AI)  
**Purpose:** Final validation before execution  
**Frequency:** Every trade

**11 Risk Gates Checked:**
1. **Confidence Threshold:** Min 0.45-0.60 depending on strategy
2. **Action Allowed:** BUY_CALL, BUY_PUT, BUY_STOCK only
3. **Recommendation Freshness:** < 5 minutes old
4. **Bar Freshness:** Price data < 2 hours old
5. **Feature Freshness:** Technicals < 2 hours old
6. **Ticker Daily Limit:** Max 2 trades per ticker per day
7. **Ticker Cooldown:** Min 15 minutes between trades
8. **Position Check:** Don't sell if no position
9. **Daily Loss Limit:** Stop if down $500
10. **Max Positions:** Max 5 concurrent positions
11. **Trading Hours:** 9:30 AM - 4:00 PM EST only

**Code Location:** `services/dispatcher/risk/gates.py`

**Gate Evaluation Example (from logs):**
```json
{
  "gates_passed": true,
  "confidence": {"passed": true, "observed": 0.51, "threshold": 0.45},
  "daily_loss_limit": {"passed": true, "observed": 0.0, "threshold": 500},
  "max_positions": {"passed": true, "observed": 0, "threshold": 5}
}
```

**NOT AI-based:** These are fixed rules, not machine learning

---

### 📈 Stage 5: Options Contract Selection (Alpaca API)

**Service:** `dispatcher` (AlpacaPaperBroker)  
**Method:** Alpaca Options API + rule-based validation  
**Purpose:** Find best options contract  
**When:** After risk gates pass

**Process:**
1. Fetch 100+ contracts from Alpaca API
2. Select strike based on strategy (ATM/OTM/ITM)
3. Validate liquidity (spread < 10%)
4. Calculate position size (5-20% of capital)

**Code Location:** `services/dispatcher/alpaca/options.py`

**NOT AI-based:** Uses mathematical formulas for strike selection

---

## ❌ Where AI Is NOT Used (Yet)

### Trade Execution Validation
**Current:** Rule-based risk gates  
**NOT using:** AI to validate each trade  
**Why:** Rules are fast, deterministic, auditable

### Options Contract Selection
**Current:** Mathematical strike selection (ATM, OTM, ITM formulas)  
**NOT using:** AI to pick optimal strikes  
**Why:** Standard options theory works well

### Position Sizing
**Current:** Fixed % of capital (5% day trade, 10% swing)  
**NOT using:** AI-based Kelly Criterion  
**Why:** Fixed sizing is safer for initial deployment

---

## 🔮 Future AI Enhancements (Phase 17+)

### Already Planned - Phase 17:
1. **Options Bar Analysis:** Capture historical options prices
2. **IV Surface Modeling:** Track implied volatility patterns
3. **AI Learning Tables:** Store trade outcomes for ML training

### Could Add - Future Phases:
1. **Pre-Trade AI Validation:**
   - Bedrock Sonnet reviews each trade before execution
   - Checks: "Does this make sense given market context?"
   - Veto power on risky trades

2. **Options Strike Optimization:**
   - ML model predicts best strike/expiration
   - Based on historical outcomes
   - Adaptive to market regime

3. **Dynamic Position Sizing:**
   - AI calculates optimal position size
   - Based on current portfolio, correlations, volatility
   - Kelly Criterion with safety factors

---

## 📋 Current AI Usage Summary

| Stage | Service | AI/ML Used | Purpose | Frequency |
|-------|---------|------------|---------|-----------|
| Ticker Selection | ticker_discovery | ✅ Bedrock Sonnet | Pick watchlist | Weekly |
| Sentiment Analysis | classifier_worker | ✅ FinBERT NLP | Analyze news | 5 minutes |
| Signal Generation | signal_engine_1m | ❌ Rules | Create signals | 1 minute |
| Risk Validation | dispatcher | ❌ Rules | Pre-trade gates | Per trade |
| Options Selection | dispatcher | ❌ Math | Pick contracts | Per options trade |

**Bottom Line:** AI helps with INPUTS (which tickers, sentiment context) but NOT with DECISIONS (whether to trade, which options).

---

## 🎯 Why This Design?

### Advantages of Rule-Based Trade Validation:
1. **Deterministic:** Same inputs = same output (auditable)
2. **Fast:** No API latency (< 1ms vs AI's 500ms)
3. **Transparent:** Can explain every decision
4. **Regulatorily Sound:** Clear logic, not "black box"
5. **No Hallucinations:** Rules never "imagine" things

### When AI Makes Sense:
1. **Ticker Discovery:** Too many stocks to analyze manually
2. **Sentiment:** Natural language is AI's strength
3. **Pattern Recognition:** Future - finding subtle patterns in data

### When Rules Make Sense:
1. **Risk Management:** Must be deterministic
2. **Position Sizing:** Fixed formulas are safer
3. **Execution Timing:** Speed matters

---

## 💡 Recommendation: Add AI Pre-Trade Review?

### Option A: Keep Current Design (Recommended)
**Pros:**
- Fast, deterministic, auditable
- Rules work well for technical trading
- No AI costs per trade

**Cons:**
- No AI "second opinion" before trades
- Can't adapt to novel market conditions

### Option B: Add Bedrock Pre-Trade Validation
**Implementation:**
```python
# In dispatcher, before execute_trade():
bedrock_review = await bedrock_validate_trade(
    ticker, action, instrument_type, 
    technicals, sentiment, market_context
)

if bedrock_review.score < 0.7:
    log_trade_blocked(bedrock_review.reason)
    return skip_trade()
```

**Pros:**
- AI "sanity check" before each trade
- Can catch unusual market conditions
- Learns from broader context

**Cons:**
- Adds 300-500ms latency per trade
- Bedrock API costs (~$0.01 per trade)
- Less deterministic (harder to debug)

---

## 🔍 Current System Validation Flow

```
[News] → [FinBERT AI] → [Sentiment Score]
                              ↓
[Price Data] → [Rules Engine] → [Signal] → [11 Risk Gates] → [Trade]
                                              ↑
                                         Rule-Based
                                         (Not AI)
```

**AI validates:**  ✅ News sentiment (confidence modifier)  
**AI does NOT validate:** ❌ Final trade decision

---

## Conclusion

**Current State:** AI used for ticker selection (Bedrock) and sentiment (FinBERT), but **rule-based validation before trades**. This is INDUSTRY STANDARD for quantitative trading.

**If you want AI trade validation:** We can add Bedrock review before execution, but it's not common practice. Most quant funds use rules for execution, AI for research.

**Options-specific AI** (Phase 17): Will analyze options price patterns, IV surfaces, and Greeks using ML models for strategy optimization.
