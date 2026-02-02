# Phase 14: AI-Powered Ticker Discovery & Learning - AGGRESSIVE APPROACH

**Date:** 2026-01-26 20:13 UTC  
**Approach:** Aggressive - Expand ticker universe, lower thresholds, learn fast  
**Since:** Paper money - safe to experiment  
**Timeline:** Build NOW, deploy within 2 hours

---

## 🎯 Objectives

**Problem:** Only 7 tickers, waiting for rare >3.0x volume surges  
**Solution:** Use Bedrock AI to discover 20-30 tickers daily, lower thresholds, generate more trades

**Goal:** 5-10 trades per day for rapid learning

---

## 🚀 Phase 14A: Bedrock Ticker Discovery (Build Now)

### Service: `services/ticker_discovery/`

**Purpose:** Use Bedrock Claude to analyze market and recommend tickers  
**Schedule:** Every 6 hours (4x per day)  
**Output:** 20-30 ticker recommendations → Updates classifier ticker universe

### Implementation

```python
# services/ticker_discovery/main.py
import boto3
import json
from datetime import datetime

def discover_tickers_with_bedrock():
    """
    Use Claude Sonnet to analyze market and recommend tickers
    """
    
    bedrock = boto3.client('bedrock-runtime', region_name='us-west-2')
    
    prompt = """You are a day trading analyst finding opportunities.

Task: Recommend 25 US stocks for intraday options trading TODAY.

Criteria (ALL REQUIRED):
- Market cap >$5B (liquid)
- Average volume >500K shares/day  
- Has weekly options (0-7 DTE available)
- Price >$20 (avoids penny stocks)
- Current catalyst OR recent volume surge

Consider RIGHT NOW:
1. Stocks with news in last 24 hours
2. Stocks with volume >2x average today
3. Sector momentum (AI, semiconductors, EVs, etc.)
4. Earnings this week (pre/post market movers)
5. Technical breakouts (new highs, support bounces)

For each ticker, provide:
- ticker: Symbol (REQUIRED)
- sector: Industry/sector
- catalyst: Why tradeable today (news, volume, technical, earnings)
- confidence: 0.0-1.0 (how strong is opportunity)
- expected_volume: "high" | "medium" | "low"

Return JSON array of 25 tickers, sorted by confidence (highest first).

Only include liquid names with options. Avoid illiquid, no-option stocks.

JSON Response:"""
    
    try:
        response = bedrock.invoke_model(
            modelId="anthropic.claude-3-5-sonnet-20241022-v2:0",  # Sonnet for better analysis
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 2000,
                "temperature": 0.4,
                "messages": [{
                    "role": "user",
                    "content": prompt
                }]
            })
        )
        
        result = json.loads(response['body'].read())
        content = result['content'][0]['text']
        
        # Parse JSON
        if content.startswith('```'):
            lines = content.split('\n')
            content = '\n'.join(lines[1:-1])
        
        tickers = json.loads(content)
        
        # Filter for confidence >0.5
        high_conf = [t for t in tickers if t.get('confidence', 0) > 0.5]
        
        return high_conf[:25]  # Top 25
        
    except Exception as e:
        print(f"Bedrock discovery error: {e}")
        # Fallback to expanded static list
        return get_fallback_tickers()

def get_fallback_tickers():
    """
    Fallback: Expanded static list of 25 liquid stocks
    """
    return [
        # Mega caps (current 7)
        {'ticker': 'AAPL', 'sector': 'Tech', 'confidence': 0.9},
        {'ticker': 'MSFT', 'sector': 'Tech', 'confidence': 0.9},
        {'ticker': 'NVDA', 'sector': 'Semiconductors', 'confidence': 0.9},
        {'ticker': 'GOOGL', 'sector': 'Tech', 'confidence': 0.9},
        {'ticker': 'AMZN', 'sector': 'Retail/Cloud', 'confidence': 0.9},
        {'ticker': 'META', 'sector': 'Social Media', 'confidence': 0.9},
        {'ticker': 'TSLA', 'sector': 'EV', 'confidence': 0.9},
        
        # Semiconductors
        {'ticker': 'AMD', 'sector': 'Semiconductors', 'confidence': 0.8},
        {'ticker': 'INTC', 'sector': 'Semiconductors', 'confidence': 0.7},
        {'ticker': 'QCOM', 'sector': 'Semiconductors', 'confidence': 0.7},
        {'ticker': 'AVGO', 'sector': 'Semiconductors', 'confidence': 0.8},
        
        # Software/Cloud
        {'ticker': 'CRM', 'sector': 'Software', 'confidence': 0.7},
        {'ticker': 'ORCL', 'sector': 'Software', 'confidence': 0.7},
        {'ticker': 'ADBE', 'sector': 'Software', 'confidence': 0.7},
        {'ticker': 'NOW', 'sector': 'Software', 'confidence': 0.7},
        
        # Consumer/Streaming
        {'ticker': 'NFLX', 'sector': 'Streaming', 'confidence': 0.8},
        {'ticker': 'DIS', 'sector': 'Media', 'confidence': 0.7},
        {'ticker': 'UBER', 'sector': 'Gig Economy', 'confidence': 0.7},
        {'ticker': 'ABNB', 'sector': 'Travel', 'confidence': 0.7},
        
        # Finance
        {'ticker': 'JPM', 'sector': 'Banking', 'confidence': 0.7},
        {'ticker': 'BAC', 'sector': 'Banking', 'confidence': 0.6},
        {'ticker': 'GS', 'sector': 'Investment Bank', 'confidence': 0.7},
        
        # Healthcare
        {'ticker': 'UNH', 'sector': 'Healthcare', 'confidence': 0.7},
        {'ticker': 'JNJ', 'sector': 'Pharma', 'confidence': 0.6},
        {'ticker': 'PFE', 'sector': 'Pharma', 'confidence': 0.6}
    ]

def update_ticker_universe(discovered_tickers):
    """
    Update database with new ticker universe
    Classifier will pick up changes on next run
    """
    
    # Store in new table: ticker_universe
    # Columns: ticker, sector, catalyst, confidence, discovered_at, active
    
    conn = get_db_connection()
    
    for t in discovered_tickers:
        conn.execute("""
            INSERT INTO ticker_universe (ticker, sector, catalyst, confidence, active)
            VALUES (%s, %s, %s, %s, true)
            ON CONFLICT (ticker) 
            DO UPDATE SET 
                confidence = EXCLUDED.confidence,
                catalyst = EXCLUDED.catalyst,
                last_updated = NOW()
        """, (t['ticker'], t['sector'], t.get('catalyst'), t['confidence']))
    
    conn.commit()
    
    # Get active ticker list
    active_tickers = conn.execute("""
        SELECT ticker FROM ticker_universe 
        WHERE active = true AND confidence > 0.5
        ORDER BY confidence DESC
        LIMIT 30
    """).fetchall()
    
    return [t[0] for t in active_tickers]
```

---

## 🎯 Phase 14B: Lower Thresholds for More Action

### Aggressive Trading Mode (Paper Money)

**Current thresholds (conservative):**
```python
CONFIDENCE_MIN = 0.70        # High bar
VOLUME_MIN = 3.0             # Very high
sentiment_weight = 0.40      # Balanced
```

**Aggressive thresholds (for learning):**
```python
CONFIDENCE_MIN = 0.50        # Lower bar → More trades
VOLUME_MIN = 2.0             # Lower → More opportunities  
sentiment_weight = 0.30      # Less weight on sentiment
volume_weight = 0.50         # MORE weight on volume
technical_weight = 0.20      # Standard
```

**Expected Impact:**
- Current: 0-2 trades/day (waiting for >3.0x)
- Aggressive: 5-10 trades/day (captures 2.0x-3.0x surges)
- **More learning data, faster iteration**

---

## 📊 Phase 14C: Missed Opportunity Tracker

### Service: `services/opportunity_analyzer/`

**Purpose:** Nightly analysis of what we missed  
**Schedule:** 6 PM ET (after market close)  
**Output:** Daily email report + database records

**What it does:**
```python
def analyze_missed_opportunities():
    """
    Find all volume surges we didn't trade and analyze why
    """
    
    # 1. Find all volume surges >2.0x today
    surges = query("""
        SELECT ticker, ts, volume_ratio, close, sentiment
        FROM lane_features f
        LEFT JOIN (
            SELECT ticker, AVG(sentiment_score) as sentiment
            FROM inbound_events_classified
            WHERE created_at >= CURRENT_DATE
            GROUP BY ticker
        ) s ON s.ticker = f.ticker
        WHERE f.computed_at >= CURRENT_DATE
          AND f.volume_ratio > 2.0
          AND f.ticker NOT IN (
              SELECT ticker FROM dispatch_recommendations
              WHERE ts >= CURRENT_DATE
          )
        ORDER BY volume_ratio DESC
    """)
    
    # 2. For each surge, use Bedrock to analyze
    for surge in surges:
        analysis = bedrock_analyze_missed_trade(surge)
        
        # Store in missed_opportunities table
        save_missed_opportunity(
            ticker=surge['ticker'],
            volume_ratio=surge['volume_ratio'],
            why_skipped=analysis['reason'],
            potential_profit=analysis['estimated_profit'],
            should_have_traded=analysis['recommendation']
        )
    
    # 3. Generate report
    generate_daily_report(surges)
```

**Bedrock analysis:**
```python
def bedrock_analyze_missed_trade(surge):
    """
    Use Claude to understand why we skipped this
    """
    
    prompt = f"""
    We detected but SKIPPED a trading opportunity:
    
    Ticker: {surge['ticker']}
    Volume Surge: {surge['volume_ratio']}x (surge!)
    Price: ${surge['close']}
    Sentiment: {surge['sentiment']} 
    Time: {surge['ts']}
    
    Our rules didn't generate a trade signal.
    
    Analyze:
    1. Was this a real opportunity or false alarm?
    2. If we had bought, what would likely have happened?
    3. Estimate potential profit/loss
    4. Should we have traded this? Why or why not?
    5. What rule adjustment would have caught this?
    
    Return JSON with:
    - real_opportunity: true/false
    - estimated_profit_percent: number (-10 to +10)
    - recommendation: "should_trade" | "correct_skip"
    - reason: explanation
    - rule_adjustment: suggested change
    """
    
    # Call Bedrock
    response = bedrock.invoke_model(...)
    return parse_response(response)
```

---

## 🏗️ Implementation Plan

### Step 1: Expand Ticker Universe (30 min)

**Quick win: Update classifier with 25 tickers**

```bash
# 1. Edit services/classifier_worker/nlp/tickers.py
# Add 18 more tickers to the 7 existing

# 2. Rebuild classifier
cd /home/nflos/workplace/inbound_aigen
docker build -f services/classifier_worker/Dockerfile -t classifier:latest .
docker tag classifier:latest 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/classifier:latest
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/classifier:latest

# 3. Update task definition and restart
aws ecs update-service --cluster ops-pipeline-cluster \
  --service classifier-worker --force-new-deployment --region us-west-2
```

**Impact:** Immediately start tracking 25 tickers instead of 7

### Step 2: Lower Trading Thresholds (15 min)

**Update Signal Engine config:**

```python
# In services/signal_engine_1m/rules.py or config
CONFIDENCE_MIN = 0.55        # Was 0.70
VOLUME_MIN_FOR_OPTIONS = 2.0 # Was 3.0
```

**Rebuild and redeploy Signal Engine**

**Impact:** 3-5x more trade opportunities

### Step 3: Build Ticker Discovery Service (1 hour)

Create `services/ticker_discovery/` with Bedrock integration  
Deploy as nightly Lambda or ECS task  
Updates ticker universe based on market analysis

### Step 4: Build Opportunity Analyzer (1 hour)

Create `services/opportunity_analyzer/` for nightly missed trade analysis  
Uses Bedrock to understand what we missed  
Generates daily learning reports

---

## 📊 Expected Results

### Before (Today)
- Tickers: 7
- Confidence threshold: 0.70
- Volume threshold: 3.0x
- **Trades per day:** 0-2 (rare setups)

### After Phase 14 (Tomorrow)
- Tickers: 25 (Bedrock can expand to 50+)
- Confidence threshold: 0.55
- Volume threshold: 2.0x  
- **Trades per day:** 5-10 (active learning)

### After 1 Month
- AI learns which tickers work best
- Optimizes confidence weights
- Filters out bad patterns
- **Win rate:** 50-60% (realistic)

---

## 🎯 Quick Start: Expand Tickers NOW

**Fastest path to more trades:**

1. **Add 18 tickers** to classifier (10 minutes)
2. **Lower thresholds** in signal engine (5 minutes)
3. **Rebuild both** Docker images (20 minutes)
4. **Push and redeploy** (10 minutes)

**Total:** 45 minutes to 3-5x more trading opportunities

---

## 🤖 Bedrock Usage Strategy

### Tier 1: Immediate (Uses Bedrock NOW)
- Ticker extraction from news ✅ (Claude Haiku - $0.25/M tokens)
- **ADD:** Ticker discovery (Claude Sonnet - $3/M tokens, 4x per day)

### Tier 2: Nightly (Use Bedrock for Analysis)
- Missed opportunity analysis (Sonnet - once per day)
- Performance pattern detection
- **Cost:** ~$2-5 per day

### Tier 3: Future (Advanced AI)
- Real-time signal enhancement
- Dynamic weight optimization
- **Cost:** ~$10-20 per day

**Total estimated cost:** $5-10/day for aggressive AI learning

---

## 🚦 Action Plan (Next 2 Hours)

### Immediate Actions

**1. Expand Ticker Universe (NOW)**
- Edit `services/classifier_worker/nlp/tickers.py`
- Add 18 more liquid tickers
- Rebuild and redeploy classifier
- **Time:** 30 minutes

**2. Lower Signal Thresholds (NOW)**
- Edit `services/signal_engine_1m/rules.py`
- Confidence: 0.70 → 0.55
- Volume: 3.0x → 2.0x
- Rebuild and redeploy signal engine
- **Time:** 20 minutes

**3. Build Bedrock Ticker Discovery (NEXT)**
- Create `services/ticker_discovery/`
- Bedrock integration for daily ticker recommendations
- Deploy as scheduled Lambda
- **Time:** 1 hour

**4. Build Opportunity Analyzer (NEXT)**
- Create `services/opportunity_analyzer/`
- Nightly analysis of missed trades
- Email reports
- **Time:** 1 hour

---

## ✅ Success Criteria

**Phase 14 Complete When:**
- [ ] 25+ tickers being tracked (up from 7)
- [ ] Confidence threshold lowered (more trades)
- [ ] Bedrock ticker discovery running daily
- [ ] Missed opportunity analyzer running nightly
- [ ] 5+ trades executing per day
- [ ] Learning data accumulating

**After 1 Week:**
- [ ] 30-50 trades executed
- [ ] Win rate calculated
- [ ] Best/worst tickers identified
- [ ] Threshold optimization recommendations ready

---

**Let's build this NOW. You're right - paper money means we should be aggressive and learn fast.**
