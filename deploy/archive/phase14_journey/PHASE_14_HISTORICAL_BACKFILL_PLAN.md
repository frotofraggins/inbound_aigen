# Phase 14: Historical Data Backfill & Analysis

**Date:** 2026-01-27  
**Purpose:** Backfill historical data for AI-recommended tickers and analyze patterns  
**Status:** Plan Ready for Implementation

---

## Objective

**Use Alpaca historical API to:**
1. Backfill 7-30 days of 1-minute bars for all 28 AI tickers
2. Compute historical features (volume_ratio, RSI, Bollinger Bands)
3. Identify historical volume surges and setups
4. Use Bedrock to analyze what would have worked
5. Optimize signal thresholds based on real patterns

---

## Backfill Strategy

### Data to Load

**For each of 28 AI tickers:**
- 1-minute bars for last 7 days
- ~390 minutes/day × 7 days = ~2,730 bars per ticker
- 28 tickers × 2,730 bars = ~76,000 total bars

**Alpaca API:**
```python
from alpaca_trade_api import REST
import pandas as pd

api = REST(key_id, secret_key, base_url='https://paper-api.alpaca.markets')

# Get 7 days of 1-minute bars
bars = api.get_bars(
    symbols=['NVDA', 'MSFT', ...],  # All 28 AI tickers
    timeframe='1Min',
    start='2026-01-20T09:30:00-05:00',  # 7 days ago
    end='2026-01-27T16:00:00-05:00',    # Today
    limit=10000
)
```

### Storage Approach

**1. Load to lane_telemetry:**
```sql
INSERT INTO lane_telemetry (ticker, ts, open, high, low, close, volume)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (ticker, ts) DO NOTHING
```

**2. Trigger feature computation:**
- Run feature_computer_1m on historical data
- Compute volume_ratio, RSI, Bollinger Bands
- Identify historical volume surges

**3. Identify missed opportunities:**
- Find volume surges >2.0x that weren't traded
- Measure actual price movement after surge
- Calculate what profit/loss would have been

---

## Analysis With Bedrock

### Phase 1: Pattern Discovery

**For each historical volume surge, ask Bedrock:**

```
"Analyze this volume surge from {date}:
Ticker: {ticker}
Time: {time}
Volume: {ratio}x surge
Price action: {price_before} → {price_after} ({pct_change}%)
Duration: {minutes} minutes
News context: {headlines}

Questions:
1. Was this a tradeable setup? (yes/no with confidence)
2. What type of setup was it? (news-driven, technical, sector momentum)
3. What would optimal entry/exit have been?
4. What patterns made it tradeable or not?
5. How could we detect this type earlier?

Return JSON with analysis."
```

### Phase 2: Threshold Optimization

**Aggregate patterns and ask Bedrock:**

```
"Analyzed 100 historical volume surges. Results:

Traded and won: {count}
Traded and lost: {count}  
Skipped (would have won): {count}
Skipped (correctly): {count}

Patterns of winning setups:
- Volume ratio: {avg}x average
- Sentiment: {avg} typical
- RSI: {avg} typical
- Time of day: {distribution}

Patterns of losing setups:
- Volume ratio: {avg}x average  
- Sentiment: {avg} typical
- RSI: {avg} typical

Current thresholds:
- Volume: 2.0x minimum
- Sentiment: 0.10 absolute minimum
- Confidence: 0.55 minimum

Question: What threshold adjustments would improve win rate?

Return JSON with specific recommendations."
```

---

## Implementation Plan

### Script 1: Backfill Historical Data (30 min)

**File:** `scripts/backfill_ai_tickers.py`

```python
"""
Backfill historical 1-minute bars for AI-recommended tickers
"""
import boto3
import psycopg2
from alpaca_trade_api import REST
from datetime import datetime, timedelta

# Load AI tickers from SSM
ssm = boto3.client('ssm', region_name='us-west-2')
tickers = ssm.get_parameter(Name='/ops-pipeline/tickers')['Parameter']['Value'].split(',')

# Load Alpaca credentials
secrets = boto3.client('secretsmanager', region_name='us-west-2')
alpaca_creds = json.loads(secrets.get_secret_value(SecretId='ops-pipeline/alpaca')['SecretString'])

# Initialize Alpaca
api = REST(alpaca_creds['key_id'], alpaca_creds['secret_key'], base_url='...')

# Backfill last 7 days
end_date = datetime.now()
start_date = end_date - timedelta(days=7)

for ticker in tickers:
    print(f"Backfilling {ticker}...")
    bars = api.get_bars(
        ticker,
        timeframe='1Min',
        start=start_date.isoformat(),
        end=end_date.isoformat(),
        limit=10000
    )
    
    # Store to database
    for bar in bars:
        # INSERT INTO lane_telemetry ...
        pass
    
    print(f"  {ticker}: {len(bars)} bars loaded")

print(f"✅ Backfilled {len(tickers)} tickers")
```

**Run once:**
```bash
python scripts/backfill_ai_tickers.py
```

### Script 2: Compute Historical Features (20 min)

**Trigger feature_computer_1m to process historical data:**

```python
"""
Compute features for all historical telemetry data
"""
# For each ticker
# For each timestamp
# Compute volume_ratio, RSI, BB, etc
# INSERT INTO lane_features
```

### Script 3: Historical Surge Analysis (1 hour)

**File:** `scripts/analyze_historical_surges.py`

```python
"""
Identify and analyze historical volume surges
Use Bedrock to determine if they were tradeable
"""

# 1. Find all volume surges >2.0x in last 7 days
surges = query_db("""
    SELECT ticker, ts, volume_ratio, close, 
           -- Price 30 min later
           LEAD(close, 30) OVER (PARTITION BY ticker ORDER BY ts) as price_after_30m
    FROM lane_features
    WHERE volume_ratio > 2.0
      AND ts > NOW() - INTERVAL '7 days'
    ORDER BY volume_ratio DESC
    LIMIT 100
""")

# 2. For each surge, calculate actual outcome
for surge in surges:
    pct_change = ((surge.price_after_30m - surge.close) / surge.close) * 100
    
    # 3. Get news context from that time
    news = query_db("SELECT headline, sentiment FROM inbound_events_classified WHERE...")
    
    # 4. Ask Bedrock to analyze
    analysis = bedrock.invoke_model(prompt=f"""
        Analyze this historical volume surge:
        {ticker} at {ts}: {volume_ratio}x surge
        Price moved {pct_change}% in next 30 minutes
        News: {headlines}
        
        Was this tradeable? What made it work or not work?
    """)
    
    # 5. Store analysis
    # INSERT INTO missed_opportunities ...

# 6. Aggregate insights
summary = aggregate_patterns(analyses)

# 7. Get threshold recommendations from Bedrock
recommendations = bedrock.invoke_model(prompt=f"""
    Based on 100 historical surges:
    - {win_rate}% would have won
    - {loss_rate}% would have lost
    
    Winning patterns: {patterns}
    Losing patterns: {patterns}
    
    Recommend threshold adjustments
""")
```

---

## Benefits

### 1. Historical Pattern Recognition
- Identify which setups consistently work
- Identify which setups to avoid
- Understand time-of-day patterns
- Recognize sector-specific behaviors

### 2. Threshold Optimization
- Adjust volume_ratio minimum (currently 2.0x)
- Adjust sentiment requirement (currently 0.10)
- Adjust confidence threshold (currently 0.55)
- Add time-of-day filters

### 3. Strategy Validation
- Test current rules against historical data
- Measure theoretical win rate
- Calculate theoretical profit
- Identify improvement opportunities

### 4. Risk Management
- Identify common failure modes
- Set better stop losses
- Improve position sizing
- Avoid known bad setups

---

## Expected Outcomes

**After Backfill + Analysis:**

**Quantitative:**
- Win rate: X% of historical surges were profitable
- Average gain: +Y% on winners
- Average loss: -Z% on losers
- Best time of day: Morning vs afternoon
- Best setup type: News vs technical vs volume

**Qualitative (from Bedrock):**
- "Tech stocks respond best to AI news in first hour"
- "Financial stocks need >3.0x volume for reliable moves"
- "Healthcare requires strong sentiment (>0.15) to work"
- "Avoid end-of-day surges except on strong news"

**Actionable:**
- Recommended threshold: Volume 2.5x (not 2.0x)
- Recommended sentiment: 0.12 (not 0.10)
- Recommended filters: Avoid last 30 min of day
- Recommended additions: Check if news <1 hour old

---

## Timeline

**Phase 1: Backfill (1-2 hours)**
1. Create backfill script
2. Load 7 days × 28 tickers
3. ~76,000 bars to database
4. Verify data quality

**Phase 2: Feature Computation (1 hour)**
1. Run feature_computer on historical data
2. Generate volume_ratio, RSI, etc
3. ~76,000 feature records

**Phase 3: Surge Analysis (2-3 hours)**
1. Identify ~100-200 historical surges
2. Calculate actual outcomes
3. Bedrock analysis of each
4. Store in missed_opportunities table

**Phase 4: Optimization (1 hour)**
1. Aggregate patterns
2. Bedrock recommendations
3. Document findings
4. Implement threshold changes

**Total: 5-7 hours** (can split across sessions)

---

## Cost Estimate

**Alpaca API:**
- Free (historical data included)

**Bedrock API:**
- 100-200 surge analyses × 500 tokens = ~100K tokens
- ~$0.30 one-time

**Database:**
- 76K telemetry rows = ~50MB
- 76K feature rows = ~100MB
- Negligible cost

**Total: ~$0.30 one-time**

---

## Next Steps

**Option A: Full Implementation (5-7 hours)**
1. Build backfill script
2. Load all historical data
3. Analyze with Bedrock
4. Optimize thresholds
5. Deploy improvements

**Option B: Pilot (2 hours)**
1. Backfill just 2-3 days
2. Analyze top 20 surges
3. Get initial insights
4. Decide if worth full analysis

**Option C: Defer to Phase 14B**
1. Deploy opportunity_analyzer first
2. Let it collect data going forward
3. Do historical analysis later

---

## Recommendation

**Start with Option B (Pilot):**
- 2 hours of work
- Quick insights
- Validates approach
- Then decide on full backfill

**This would make Phase 14 incredibly powerful:**
- Real-time AI ticker selection ✅ (Phase 14A complete)
- Historical pattern analysis (New)
- Nightly missed trade reports (Phase 14B pending)
- Continuous optimization loop

---

**Ready to implement if you want to continue tonight, or can be next session!**
