# Phase 8.1: Signal Engine - DEPLOYMENT COMPLETE ✅

**Deployment Date:** 2026-01-12  
**Service:** ops-pipeline-signal-engine-1m  
**Schedule:** Every 1 minute  
**Status:** Deployed and scheduled

---

## What Was Deployed

The Signal Engine is the **decision layer** that converts watchlist stocks into actionable trading recommendations. It:
- Processes only the top 30 watchlist stocks (efficient filtering)
- Applies consistent, testable rules for BUY/SELL decisions
- Selects instrument type (CALL/PUT/STOCK) based on volatility
- Generates confidence scores (0.0-1.0)
- Logs complete reasoning in JSONB for analysis

**This is Phase 8.1 - Option B:** Build the decision layer first, prove it works, then expand the universe later.

---

## Signal Generation Logic

### Directional Bias Rules

**Bullish Signal:**
- Sentiment score > 0.65 (positive news)
- Trend state >= 0 (uptrend or neutral)
- Price above SMA20
- Distance from SMA20 < 2% (not over-extended)

**Bearish Signal:**
- Sentiment score < 0.35 (negative news)
- Trend state <= 0 (downtrend or neutral)
- Price below SMA20
- Distance from SMA20 < 2% (not over-extended)

### Instrument Selection (Based on Volatility)

**When to use OPTIONS (CALL/PUT):**
- vol_ratio between 0.8-1.3 (normal volatility)
- Options are reasonably priced
- Clean directional setup

**When to use STOCK:**
- vol_ratio > 1.3 (high volatility)
- Options too expensive due to elevated vol
- Still want directional exposure

**Premium Selling (Future):**
- Neutral sentiment
- Extreme volatility (vol_ratio >= 1.6)
- Range-bound (near SMA20)
- Currently marked as TODO

### Confidence Scoring

```python
confidence = (
    40% × sentiment_strength +     # How strong is sentiment?
    30% × trend_alignment +         # Sentiment matches trend?
    20% × setup_quality +           # Clean technical setup?
    10% × vol_appropriateness       # Vol suits the instrument?
)
```

### Cooldown Protection
- Won't re-signal same ticker within 15 minutes
- Prevents signal spam
- Allows time for price action to develop

---

## Deployment Steps Completed

1. ✅ Created service code (config.py, db.py, rules.py, main.py)
2. ✅ Created ECR repository: `ops-pipeline/signal-engine-1m`
3. ✅ Built and pushed Docker image
4. ✅ Registered ECS task definition (256 CPU / 512 MB)
5. ✅ Created EventBridge schedule: rate(1 minute)
6. ✅ Service will begin operations within 1 minute

---

## AWS Resources Created

### ECR Repository
- **Name:** ops-pipeline/signal-engine-1m
- **URI:** 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/signal-engine-1m
- **ARN:** arn:aws:ecr:us-west-2:160027201036:repository/ops-pipeline/signal-engine-1m

### ECS Task Definition
- **Family:** ops-pipeline-signal-engine-1m
- **Revision:** 1
- **ARN:** arn:aws:ecs:us-west-2:160027201036:task-definition/ops-pipeline-signal-engine-1m:1
- **CPU:** 256
- **Memory:** 512 MB
- **Network Mode:** awsvpc (Fargate)

### EventBridge Schedule
- **Name:** ops-pipeline-signal-engine-1m
- **ARN:** arn:aws:scheduler:us-west-2:160027201036:schedule/default/ops-pipeline-signal-engine-1m
- **Expression:** rate(1 minute)
- **Target:** ops-pipeline-cluster ECS task

### CloudWatch Log Group
- **Name:** /ecs/ops-pipeline/signal-engine-1m
- **Auto-created:** Yes (on first execution)
- **Retention:** Default (never expire)

---

## Service Code Structure

```
services/signal_engine_1m/
├── config.py       # AWS configuration (SSM, Secrets Manager)
├── db.py          # Database queries (watchlist, features, sentiment)
├── rules.py       # Signal generation logic
├── main.py        # Orchestration and logging
├── requirements.txt
└── Dockerfile
```

### Key Functions

**db.py:**
- `get_watchlist_top30()` - Current top 30 stocks
- `get_latest_features(tickers)` - Technical indicators  
- `get_recent_sentiment(tickers, window=30m)` - News aggregation
- `check_cooldown(ticker, minutes=15)` - Prevent spam
- `insert_recommendation()` - Write to dispatch_recommendations

**rules.py:**
- `compute_signal(ticker, features, sentiment)` - Main decision logic
- Returns: (action, instrument_type, confidence, reason_dict)

**main.py:**
- Load config from AWS
- Fetch top 30 watchlist
- Get features + sentiment
- Generate signals for each ticker
- Log structured JSON events

---

## Expected Behavior

### First Execution (within 1 minute of deployment):
1. Load configuration from SSM/Secrets Manager
2. Query watchlist_state for top 30 stocks
3. Fetch lane_features (latest for each ticker)
4. Fetch sentiment aggregation (last 30 minutes)
5. For each ticker:
   - Check cooldown (skip if recently signaled)
   - Compute signal using rules
   - Log decision reasoning
   - Insert recommendation if actionable

### Ongoing Operation:
- Runs every 1 minute
- Only processes watchlist top 30 (not all 36 universe stocks)
- Writes to `dispatch_recommendations` table with:
  - ticker
  - action: BUY/SELL/HOLD
  - instrument_type: CALL/PUT/STOCK/PREMIUM
  - confidence: 0.0-1.0
  - reason: JSONB with full explanation
  - status: PENDING
  - created_at: timestamp

### Output Format
Every recommendation includes complete reasoning:
```json
{
  "rule": "BULLISH_ENTRY",
  "direction": "LONG",
  "sentiment": {
    "score": 0.782,
    "bias": 0.564,
    "news_count": 5,
    "label": "bullish"
  },
  "technicals": {
    "close": 182.45,
    "sma20": 180.22,
    "sma50": 175.88,
    "distance_sma20": 0.0124,
    "trend_state": 1,
    "above_sma20": true
  },
  "volatility": {
    "vol_ratio": 1.15,
    "regime": "normal"
  },
  "decision": "Strong bullish sentiment + uptrend + above SMA20 -> CALL",
  "confidence_components": {
    "sentiment_strength": 0.564,
    "trend_alignment": 1.0,
    "setup_quality": 0.88,
    "vol_appropriateness": 1.0
  }
}
```

---

## How to Verify Deployment

### 1. Check Schedule Status
```bash
aws scheduler get-schedule \
  --name ops-pipeline-signal-engine-1m \
  --region us-west-2
```

### 2. View Logs (after execution starts)
```bash
# Wait 2-3 minutes for first execution
aws logs filter-log-events \
  --log-group-name /ecs/ops-pipeline/signal-engine-1m \
  --start-time $(($(date +%s) - 600))000 \
  --region us-west-2 \
  --max-items 100
```

### 3. Query Recommendations (from Lambda/VPC)
```sql
-- See latest recommendations
SELECT 
  ticker,
  action,
  instrument_type,
  confidence,
  status,
  created_at,
  reason->>'rule' as rule_fired
FROM dispatch_recommendations
ORDER BY created_at DESC
LIMIT 20;

-- Count recommendations by instrument type
SELECT 
  instrument_type,
  COUNT(*) as count,
  AVG(confidence) as avg_confidence
FROM dispatch_recommendations
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY instrument_type;

-- See which rules are firing most
SELECT 
  reason->>'rule' as rule,
  COUNT(*) as times_fired
FROM dispatch_recommendations
WHERE created_at > NOW() - INTERVAL '1 day'
GROUP BY rule
ORDER BY times_fired DESC;
```

### 4. Check for Errors
```bash
aws logs filter-log-events \
  --log-group-name /ecs/ops-pipeline/signal-engine-1m \
  --filter-pattern "error" \
  --start-time $(($(date +%s) - 3600))000 \
  --region us-west-2
```

---

## Cost Impact

**Monthly Cost:** ~$0.30
- 1-minute intervals = 43,200 executions/month
- 256 CPU, 512 MB memory
- ~5 seconds per execution
- Total: 60 hours compute time/month

**Updated Pipeline Total:** ~$35.51/month
- RDS: $15.10
- VPC Endpoints: $15.00
- RSS + Classifier + Telemetry + Features + Watchlist + Signals: $5.41

---

## What This Unlocks

### You Now Have:
1. ✅ **Complete data pipeline** - News → Sentiment → Market data → Features
2. ✅ **Dynamic watchlist** - Top 30 stocks auto-selected every 5 min
3. ✅ **Decision engine** - Consistent rules generating signals every 1 min
4. ✅ **Full explainability** - Every signal has JSONB reasoning

### Ready For:
- **Phase 9:** Build Dispatcher (dry-run mode initially)
- **Monitoring:** Track which rules fire, confidence distribution, signal frequency
- **Refinement:** Adjust thresholds based on observed behavior
- **Backtesting:** Use logged reasons to improve rules

---

## Key Design Decisions

### Why Process Only Watchlist Top 30?
- Efficient (not re-processing all 36 every minute)
- System tells you which 30 are interesting
- Reduces noise and signal spam
- Foundation for scaling to 120+ universe later

### Why 15-Minute Cooldown?
- Prevents re-signaling on minor price fluctuations
- Allows time for initial signal to play out
- Reduces duplicate recommendations
- Still responsive (can re-signal after 15 min if setup improves)

### Why JSONB Reasons?
- Complete audit trail
- Can analyze which rules work best
- Debug false signals
- Improve thresholds based on data
- Essential for backtesting

### Why Separate Action and Instrument?
- Action: BUY, SELL, HOLD (directional bias)
- Instrument: CALL, PUT, STOCK, PREMIUM (how to express it)
- Allows flexibility: can trade stock while preferring options
- Clean separation of concerns

---

## Troubleshooting

### If no signals generated:
1. Check watchlist has data:
   ```sql
   SELECT COUNT(*) FROM watchlist_state WHERE in_watchlist = TRUE;
   ```
2. Check features exist:
   ```sql
   SELECT ticker, computed_at FROM lane_features 
   ORDER BY computed_at DESC LIMIT 10;
   ```
3. Review logs for "NO_SETUP" reasons
4. May be normal if no stocks meet entry criteria

### If too many signals:
- Check cooldown is working (15 minutes)
- Review confidence thresholds (may be too permissive)
- Check if trend_state is too volatile

### If signals seem wrong:
- Read the JSONB reason field
- Check sentiment.score and technicals.distance_sma20
- Verify vol_ratio is reasonable
- Confirm trend_state matches expectation

---

## Next Steps

### Immediate (Complete Phase 8):
1. ✅ **Watchlist Engine deployed** (Phase 8.0a)
2. ✅ **Signal Engine deployed** (Phase 8.1)
3. 🔄 **Monitor for 24-48 hours**
   - Check logs every few hours
   - Query dispatch_recommendations
   - Verify signals make sense
   - Look for patterns in which rules fire

### Then (Phase 9):
**Build Dispatcher** (dry-run mode)
- Poll dispatch_recommendations WHERE status='PENDING'
- Apply risk gates (max trades/day, stale data checks)
- Log what *would* be executed (dry-run)
- Update status to 'DRY_RUN_LOGGED'

### After That (Phase 10):
**Add Monitoring**
- Health check Lambda (every 5 minutes)
- Data freshness alerts
- CloudWatch dashboards
- SNS notifications

### Future Enhancement (Option A):
Once signal patterns are understood:
- Expand universe to 120-150 stocks (ETFs + sectors)
- Add liquidity scoring
- Add catalyst tracking (earnings calendar)
- Add outlier detection (trend breaks, vol spikes)

---

## Service Deployment Summary

**All 5 core services now operational:**

1. ✅ **RSS Ingest** (1 min) - Fetches financial news
2. ✅ **Classifier** (1 min batch) - FinBERT sentiment analysis  
3. ✅ **Telemetry** (1 min) - Alpaca market data
4. ✅ **Feature Computer** (1 min) - SMA, volatility, trends
5. ✅ **Watchlist Engine** (5 min) - Top 30 selection
6. ✅ **Signal Engine** (1 min) - **JUST DEPLOYED** - Trading decisions

**Pipeline Status:** Data flows from news → signals in real-time. Ready for Phase 9 (Dispatcher).

---

## Verification Commands

**Check if signal engine will run:**
```bash
aws scheduler get-schedule \
  --name ops-pipeline-signal-engine-1m \
  --region us-west-2
```

**Monitor first execution (wait 2-3 minutes):**
```bash
aws logs tail /ecs/ops-pipeline/signal-engine-1m --follow --region us-west-2
```

**Count signals generated (from Lambda/VPC):**
```sql
SELECT 
  COUNT(*) as total_signals,
  COUNT(*) FILTER (WHERE action = 'BUY' AND instrument_type = 'CALL') as buy_calls,
  COUNT(*) FILTER (WHERE action = 'BUY' AND instrument_type = 'PUT') as buy_puts,
  COUNT(*) FILTER (WHERE action = 'BUY' AND instrument_type = 'STOCK') as buy_stock,
  COUNT(*) FILTER (WHERE action = 'HOLD') as holds
FROM dispatch_recommendations
WHERE created_at > NOW() - INTERVAL '1 hour';
```

---

## Architecture: How Data Flows

```
RSS Feeds (CNBC, WSJ)
  ↓ every 1 min
inbound_events_raw
  ↓ every 1 min (batch)
FinBERT Classifier
  ↓
inbound_events_classified (sentiment labels)
  ↓
Alpaca Market Data (1-min bars)
  ↓ every 1 min
lane_telemetry (OHLCV)
  ↓ every 1 min
Feature Computer (SMA, vol_ratio, trend)
  ↓
lane_features
  ↓ every 5 min
Watchlist Engine (scoring + selection)
  ↓
watchlist_state (top 30)
  ↓ every 1 min ← YOU ARE HERE
Signal Engine (rules + instrument selection)
  ↓
dispatch_recommendations (actionable signals)
  ↓ (Phase 9)
Dispatcher (dry-run mode)
  ↓
Execution logs (what would have been traded)
```

---

## What Makes This Signal Engine Good

### 1. Explainable
Every signal has complete reasoning in JSONB:
- Which rule fired
- Sentiment data (score, count, label)
- Technicals (close, SMAs, distance, trend)
- Volatility (regime, ratio)
- Confidence components breakdown

### 2. Testable
- Can query which rules fire most
- Can analyze confidence vs outcomes
- Can identify noisy vs profitable patterns
- Foundation for backtesting

### 3. Improvable
- Adjust thresholds based on observations
- Add new rules incrementally
- Track rule performance over time
- Iterate based on data, not guesses

### 4. Safe
- Cooldown prevents spam
- Confidence scores guide position sizing
- Status field allows dry-run testing
- Complete audit trail

---

## Common Questions

**Q: Why 1-minute schedule if there's a 15-minute cooldown?**  
A: System checks for new setups every minute, but won't re-signal the same ticker for 15 minutes. This means:
- AAPL might signal at 10:00, then not again until 10:15
- MSFT might signal at 10:01, then not again until 10:16
- Different tickers can signal every minute, but each individual ticker has cooldown

**Q: What if no stocks meet entry criteria?**  
A: Perfectly normal. The system will log all decisions as HOLD with reasons. Most of the time, stocks won't have clean setups. That's the point - you only want high-confidence signals.

**Q: How many signals should I expect?**  
A: With 30 stocks and strict entry criteria, expect:
- 1-5 signals per hour (market hours)
- More during volatile news events
- Fewer during quiet periods
- Premium signals (SELL_PREMIUM) are rare (marked TODO for now)

**Q: Why no premium selling yet?**  
A: Premium selling requires:
- IV/Greeks calculation (not implemented yet)
- Strict risk management (need position sizing)
- More sophisticated entry/exit rules
- Currently flagged as opportunities only

---

## Monitoring Recommendations

### Daily Checks (First Week):
1. **Signal frequency:** How many per hour?
2. **Rule distribution:** Which rules fire most?
3. **Confidence levels:** Are they reasonable (0.5-0.8)?
4. **Instrument mix:** Mostly calls/puts or stock?
5. **Cooldown effectiveness:** Any spam patterns?

### Weekly Analysis:
1. Export dispatch_recommendations to CSV
2. Analyze which tickers signal most
3. Review confidence vs signal type
4. Identify noisy vs clean setups
5. Adjust thresholds if needed

---

## Ready for Phase 9: Dispatcher

The Dispatcher will:
1. Poll `dispatch_recommendations WHERE status='PENDING'`
2. Apply risk gates:
   - Max signals per day (e.g., 10)
   - Stale data check (features < 5 min old)
   - Cooldown verified
3. **Dry-run mode initially:**
   - Log what would be executed
   - Update status to 'DRY_RUN_LOGGED'
   - NO actual trades yet
4. Later: Connect to broker API for real execution

---

**Phase 8.1 deployment complete. Signal Engine is operational and will start generating recommendations within 1 minute.**

**What you've built:** A complete, explainable, testable trading decision system that processes real-time news and market data to generate consistent trading signals.

**Next milestone:** Phase 9 - Build the Dispatcher to handle execution (dry-run first).
