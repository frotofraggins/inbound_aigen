# Phase 12 Implementation Context - Complete System Reference
**Created:** 2026-01-16 19:52 UTC  
**Purpose:** Comprehensive context for implementing volume analysis  
**Status:** Phase 11 complete, Phase 12 ready to start

## Executive Summary

You have a **functional end-to-end sentiment-based trading pipeline** that:
- Ingests news from 10 RSS feeds
- Classifies sentiment with AI/FinBERT
- Computes technical features (SMAs, volatility)
- Generates BUY/SELL recommendations
- Processes through risk-gated dispatcher

**Critical Gap:** No volume analysis (the #1 indicator professional traders use)

**Next Task:** Add volume features to make system profitable

## System Architecture Map

```
┌─────────────────────────────────────────────────────────────────────┐
│ DATA INGESTION LAYER                                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  RSS Feeds (10 total)                                                │
│  ├── 3 Macro: CNBC, WSJ, MarketWatch                                │
│  └── 7 Ticker-Specific: Yahoo Finance (AAPL, MSFT, etc.)            │
│                    ↓                                                 │
│  RSS Ingest Service (ECS, every 1 min)                              │
│  └──> inbound_events_raw table                                      │
│                    ↓                                                 │
│  Classifier Service (ECS, every 1 min)                              │
│  ├── Regex ticker extraction (fast path)                            │
│  ├── AI ticker inference (Bedrock fallback)                         │
│  └── FinBERT sentiment classification                               │
│  └──> inbound_events_classified table                               │
│                                                                       │
├─────────────────────────────────────────────────────────────────────┤
│ TELEMETRY & FEATURES LAYER                                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  Telemetry Ingestor (ECS, every 1 min)                             │
│  ├── Fetches 1-minute OHLCV bars                                    │
│  ├── Sources: yfinance (primary), Alpaca (backup)                   │
│  └──> lane_telemetry table                                          │
│         Columns: ticker, ts, open, high, low, close, VOLUME ⚠️      │
│                                                                       │
│  Feature Computer (ECS, every 1 min)                                │
│  ├── Reads last 120 bars from lane_telemetry                        │
│  ├── Computes: SMA20, SMA50, volatility, trends                     │
│  ├── MISSING: Volume features ← PHASE 12 ADDS THIS                  │
│  └──> lane_features table                                           │
│         Columns: ticker, ts, sma20, sma50, recent_vol,              │
│                  baseline_vol, vol_ratio, distance_sma20,           │
│                  distance_sma50, trend_state, close, computed_at    │
│                                                                       │
├─────────────────────────────────────────────────────────────────────┤
│ SIGNAL GENERATION LAYER                                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  Signal Engine (ECS Scheduler, every 1 min)                         │
│  ├── Queries: latest features + ticker-specific sentiment           │
│  ├── Evaluates rules:                                               │
│  │   ├── Sentiment strength (from news)                             │
│  │   ├── Technical alignment (SMAs, trend)                          │
│  │   ├── Volatility regime                                          │
│  │   └── MISSING: Volume confirmation ← PHASE 12 ADDS THIS          │
│  ├── Generates: BUY/SELL with confidence score                      │
│  └──> dispatch_recommendations table                                │
│         Columns: id, ts, ticker, action, confidence, reason,        │
│                  status, instrument_type, created_at                │
│                                                                       │
├─────────────────────────────────────────────────────────────────────┤
│ EXECUTION LAYER                                                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  Dispatcher (ECS Scheduler, every 1 min)                            │
│  ├── Claims PENDING recommendations                                 │
│  ├── Evaluates risk gates:                                          │
│  │   ├── Confidence threshold (70%+)                                │
│  │   ├── Feature freshness (<5 min)                                 │
│  │   ├── Bar freshness (<2 min)                                     │
│  │   ├── Action allowed (BUY_CALL/BUY_PUT/BUY_STOCK)                │
│  │   └── Ticker daily limit (max 2/day)                             │
│  ├── Simulates execution or skips                                   │
│  └──> Updates status to SIMULATED or SKIPPED                        │
│  └──> dispatch_executions table (if executed)                       │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

## Database Schema Reference

### Core Tables & Their Purposes

#### 1. `lane_telemetry` - Raw price/volume bars
```sql
CREATE TABLE lane_telemetry (
  ticker TEXT NOT NULL,
  ts TIMESTAMPTZ NOT NULL,
  open NUMERIC(18,8),
  high NUMERIC(18,8),
  low NUMERIC(18,8),
  close NUMERIC(18,8),
  volume BIGINT,              -- ⚠️ THIS EXISTS but isn't used yet!
  PRIMARY KEY (ticker, ts)
);

-- Current data: ~385 bars/ticker in 24h
-- Volume field: POPULATED but IGNORED by features/signals
```

#### 2. `lane_features` - Computed technical indicators
```sql
CREATE TABLE lane_features (
  ticker TEXT NOT NULL,
  ts TIMESTAMPTZ NOT NULL,
  
  -- Moving averages
  sma20 NUMERIC,              -- 20-period simple moving average
  sma50 NUMERIC,              -- 50-period simple moving average
  
  -- Volatility (price-based, NOT volume-based)
  recent_vol NUMERIC,         -- Recent 20-bar volatility
  baseline_vol NUMERIC,       -- Baseline 50-bar volatility  
  vol_ratio NUMERIC,          -- recent_vol / baseline_vol (price volatility)
  
  -- Trend indicators
  distance_sma20 NUMERIC,     -- (close - sma20) / sma20
  distance_sma50 NUMERIC,     -- (close - sma50) / sma50
  trend_state INT,            -- -1=down, 0=neutral, 1=up
  
  -- Current price
  close NUMERIC,              -- Latest closing price
  computed_at TIMESTAMPTZ,    -- When features were computed
  
  -- ⚠️ MISSING: Volume features (Phase 12 will add these)
  -- volume_current BIGINT      -- Current bar volume
  -- volume_avg_20 BIGINT       -- 20-bar average volume
  -- volume_ratio NUMERIC       -- current / average (THIS IS DIFFERENT FROM vol_ratio!)
  -- volume_surge BOOLEAN       -- TRUE if volume_ratio > 2.0
  
  PRIMARY KEY (ticker, ts)
);

-- Current data: ~325 computations/ticker in 24h
-- All fields populated except volume features
```

#### 3. `inbound_events_classified` - News with sentiment
```sql
CREATE TABLE inbound_events_classified (
  id SERIAL PRIMARY KEY,
  raw_event_id BIGINT,
  tickers TEXT[],             -- Array: ["AAPL", "MSFT"]
  sentiment_label TEXT,       -- "positive", "negative", "neutral"
  sentiment_score NUMERIC,    -- 0.0-1.0 (confidence, NOT direction)
  event_type TEXT,            -- Not used currently
  urgency TEXT,               -- Not used currently
  created_at TIMESTAMPTZ
);

-- Current data: 162 items/24h, 28.4% with tickers
-- Sentiment score is CONFIDENCE, not directional (-1 to +1)
-- Directional sentiment computed in signal engine
```

#### 4. `dispatch_recommendations` - Generated signals
```sql
CREATE TABLE dispatch_recommendations (
  id SERIAL PRIMARY KEY,
  ts TIMESTAMPTZ,
  ticker TEXT,
  action TEXT,                -- "BUY" or "SELL"
  confidence NUMERIC,         -- 0.0-1.0
  reason JSONB,               -- Full reasoning chain
  status TEXT,                -- PENDING → PROCESSING → SIMULATED/SKIPPED/FAILED
  instrument_type TEXT,       -- "CALL", "PUT", "STOCK"
  created_at TIMESTAMPTZ,
  processed_at TIMESTAMPTZ,
  dispatcher_run_id UUID,
  failure_reason TEXT,
  risk_gate_json JSONB
);

-- Current data: 10 recommendations (2 hours)
-- All SKIPPED by risk gates (no volume confirmation)
```

#### 5. `dispatch_executions` - Trade ledger
```sql
CREATE TABLE dispatch_executions (
  execution_id UUID PRIMARY KEY,
  recommendation_id BIGINT REFERENCES dispatch_recommendations(id),
  ticker TEXT,
  action TEXT,
  entry_price NUMERIC,
  qty NUMERIC,
  simulated_ts TIMESTAMPTZ,
  execution_mode TEXT DEFAULT 'SIMULATED'
);

-- Current data: 0 executions (all recommendations skipped)
```

## Critical Variable Naming - AVOID CONFUSION! ⚠️

### The Volatility Confusion

**TWO DIFFERENT "VOLATILITY" CONCEPTS:**

#### 1. Price Volatility (vol_ratio in lane_features)
```python
# THIS IS WHAT YOU CURRENTLY HAVE
vol_ratio = recent_price_volatility / baseline_price_volatility

# Measures: How much is price fluctuating?
# Example: vol_ratio = 2.0 means price swings 2x more than normal
# Used for: Position sizing, regime detection
# Location: lane_features.vol_ratio
```

#### 2. Volume Ratio (Phase 12 adds this)
```python
# THIS IS WHAT YOU'RE ADDING IN PHASE 12
volume_ratio = current_bar_volume / avg_20_bar_volume

# Measures: Is trading volume higher than normal?
# Example: volume_ratio = 3.0 means 3x more shares traded
# Used for: Signal confirmation, breakout validation
# Location: lane_features.volume_ratio (NEW COLUMN)
```

**CRITICAL: These are COMPLETELY DIFFERENT metrics!**

### Naming Convention Going Forward

```python
# Price-based volatility (EXISTING)
price_volatility_ratio = recent_vol / baseline_vol
# Column: lane_features.vol_ratio

# Volume-based indicator (PHASE 12)
trading_volume_ratio = volume_current / volume_avg_20
# Column: lane_features.volume_ratio

# Keep these distinct in all code!
```

### The Sentiment Confusion

**TWO SENTIMENT REPRESENTATIONS:**

#### 1. FinBERT Output (in classified table)
```python
# What FinBERT gives you:
sentiment_label = "positive" | "negative" | "neutral"  # DIRECTION
sentiment_score = 0.85  # CONFIDENCE (how sure FinBERT is)

# Example: 
# label="positive", score=0.93 means "Very confident it's positive news"
# label="negative", score=0.88 means "Confident it's negative news"
```

#### 2. Directional Score (computed in signal engine)
```python
# What signal engine converts it to:
directional_sentiment = convert_to_directional_score(label, score)

# Conversion logic:
if label == "positive":
    directional = +1.0 * score  # +0.93
elif label == "negative":
    directional = -1.0 * score  # -0.88
else:  # neutral
    directional = 0.0

# This gives you: -1.0 to +1.0 range
# Positive numbers = bullish, negative = bearish
```

**CRITICAL: Don't treat sentiment_score as directional!**
- sentiment_score from FinBERT = confidence (0.0-1.0)
- directional_sentiment in signal engine = direction+strength (-1.0 to +1.0)

## Service Deployment Reference

### Current Deployments (All Running)

#### 1. RSS Ingest
- **Task Definition:** ops-pipeline-rss-ingest:latest
- **Schedule:** EventBridge Rule, every 1 minute
- **Purpose:** Pull news from 10 RSS feeds
- **Writes to:** inbound_events_raw

#### 2. Classifier  
- **Task Definition:** ops-pipeline-classifier-worker:2 (DIGEST-PINNED)
- **Digest:** sha256:906557742dc...
- **Schedule:** EventBridge Rule, every 1 minute
- **Purpose:** Extract tickers (regex + AI), classify sentiment
- **Writes to:** inbound_events_classified
- **Phase 11:** Added AI ticker inference with Bedrock

#### 3. Telemetry Ingestor
- **Task Definition:** ops-pipeline-telemetry-1m:latest
- **Schedule:** EventBridge Rule, every 1 minute
- **Purpose:** Fetch 1-minute OHLCV bars
- **Writes to:** lane_telemetry (INCLUDING VOLUME!)

#### 4. Feature Computer
- **Task Definition:** ops-pipeline-feature-computer:1 (DIGEST-PINNED)
- **Digest:** sha256:ef7abf043b...
- **Schedule:** EventBridge Rule, every 1 minute
- **Purpose:** Compute SMAs, volatility, trends
- **Reads:** lane_telemetry (uses OHLC, IGNORES volume)
- **Writes to:** lane_features
- **Phase 12 Changes:** ADD volume_ratio computation

#### 5. Signal Engine
- **Task Definition:** ops-pipeline-signal-engine-1m:1 (DIGEST-PINNED)
- **Digest:** sha256:a8e92cd48d...
- **Schedule:** EventBridge Scheduler, every 1 minute
- **Purpose:** Generate BUY/SELL recommendations
- **Reads:** lane_features + inbound_events_classified
- **Writes to:** dispatch_recommendations
- **Phase 12 Changes:** USE volume_ratio in confidence calculation

#### 6. Dispatcher
- **Task Definition:** ops-pipeline-dispatcher:latest
- **Schedule:** EventBridge Scheduler, every 1 minute
- **Purpose:** Process recommendations through risk gates
- **Reads:** dispatch_recommendations (status=PENDING)
- **Writes to:** dispatch_recommendations (updates status), dispatch_executions
- **No changes needed** (uses confidence scores)

#### 7. Watchlist
- **Task Definition:** ops-pipeline-watchlist-engine:latest
- **Schedule:** EventBridge Scheduler, every 5 minutes
- **Purpose:** Track which tickers are active
- **No changes needed**

### Supporting Infrastructure

- **RDS PostgreSQL:** ops-pipeline-db.cls4wuyg010k.us-west-2.rds.amazonaws.com
- **ECR Repositories:** 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/*
- **CloudWatch Logs:** /ecs/ops-pipeline/* (one per service)
- **Lambda Functions:** 
  - ops-pipeline-db-query (read-only queries)
  - ops-pipeline-healthcheck (metrics emission)
  - ops-pipeline-db-cleanup (housekeeping)

## Data Flow with Field Names

### Flow 1: News → Sentiment → Signals

```
RSS Feed: <item><title>Apple iPhone 16 breaks sales records</title></item>
     ↓
inbound_events_raw.title = "Apple iPhone 16 breaks sales records"
     ↓ Classifier Service
inbound_events_classified {
  tickers = ["AAPL"]          -- Extracted by regex or AI
  sentiment_label = "positive"    -- FinBERT classification
  sentiment_score = 0.89          -- FinBERT confidence (NOT direction!)
}
     ↓ Signal Engine (aggregates by ticker)
Aggregated Sentiment for AAPL {
  bias = +0.89                -- Directional score (+ is bullish)
  label = "bullish"           -- Aggregated label
  score = 0.89                -- Average confidence
  news_count = 3              -- How many news items
}
     ↓ Signal Engine (evaluates rules)
dispatch_recommendations {
  ticker = "AAPL"
  action = "BUY"
  confidence = 0.88           -- Based on sentiment + technicals
  reason = {
    "sentiment": {"bias": 0.89, "label": "bullish"},
    "technicals": {"above_sma20": true, "trend_state": 1},
    "confidence_components": {...}
  }
}
```

### Flow 2: Telemetry → Features → Signals

```
Telemetry Ingestor: Fetches bars from yfinance
     ↓
lane_telemetry {
  ticker = "AAPL"
  ts = "2026-01-16 19:34:00"
  open = 258.10
  high = 258.45
  low = 258.05
  close = 258.29
  volume = 892453              -- ⚠️ THIS IS CAPTURED but NOT USED!
}
     ↓ Feature Computer (every 1 min)
Read last 120 bars for AAPL
     ↓ Compute features
lane_features {
  ticker = "AAPL"
  ts = "2026-01-16 19:34:00"
  sma20 = 258.40              -- Mean of last 20 closes
  sma50 = 257.89              -- Mean of last 50 closes
  recent_vol = 0.023          -- Stddev of last 20 returns (PRICE volatility)
  baseline_vol = 0.018        -- Stddev of last 50 returns
  vol_ratio = 1.28            -- recent_vol / baseline_vol (PRICE VOLATILITY RATIO)
  distance_sma20 = -0.0004    -- (258.29 - 258.40) / 258.40
  distance_sma50 = 0.0016     -- (258.29 - 257.89) / 257.89
  trend_state = 1             -- Above both SMAs = uptrend
  close = 258.29              -- Current price
  computed_at = "2026-01-16 19:34:30"
  
  -- ⚠️ PHASE 12 WILL ADD:
  -- volume_current = 892453
  -- volume_avg_20 = 650000
  -- volume_ratio = 1.37        -- 892453 / 650000 (VOLUME RATIO)
  -- volume_surge = FALSE       -- 1.37 < 2.0
}
     ↓ Signal Engine
Reads features + sentiment → Generates recommendation
```

## Feature Computer Adaptive Lookback

**IMPORTANT: Feature computer has special logic from Day 6 fix**

```python
# Adaptive lookback windows (from Day 6 incident resolution)
# Problem: Some tickers don't have 120 minutes of data
# Solution: Try progressively longer lookbacks

def fetch_bars_with_adaptive_lookback(ticker):
    """
    Try: 120 min → 6h → 12h → 24h → 3 days → all available
    """
    lookbacks = [120, 360, 720, 1440, 4320, None]
    
    for lookback in lookbacks:
        bars = fetch_bars(ticker, lookback)
        if len(bars) >= 50:  # Need minimum 50 for SMA50
            return bars
    
    return []  # Not enough data
```

**Why this matters:** Don't remove this logic when adding volume features!

## Signal Confidence Calculation

**Current Formula (Phase 11):**
```python
def compute_confidence(features, sentiment):
    """
    Confidence = weighted combination of:
    - setup_quality (0-1): How good technicals are
    - trend_alignment (0-1): Trend agrees with signal
    - sentiment_strength (0-1): Abs(sentiment bias)
    - vol_appropriateness (0-1): Volatility in acceptable range
    
    NO VOLUME COMPONENT! (Phase 12 adds this)
    """
    setup = evaluate_setup_quality(features)
    trend = evaluate_trend_alignment(features, action)
    sent = abs(sentiment['bias'])  # Directional sentiment strength
    vol = evaluate_volatility_regime(features)
    
    # Weighted average
    confidence = (
        0.35 * setup +
        0.25 * trend +
        0.25 * sent +
        0.15 * vol
    )
    
    return confidence
```

**Phase 12 Enhancement:**
```python
def compute_confidence_with_volume(features, sentiment):
    """
    Add volume as 5th component
    Reweight: setup=0.30, trend=0.20, sent=0.20, vol=0.15, VOLUME=0.15
    """
    base_confidence = compute_confidence(features, sentiment)
    
    # NEW: Volume multiplier
    volume_multiplier = get_volume_multiplier(features['volume_ratio'])
    
    final_confidence = base_confidence * volume_multiplier
    return min(1.0, final_confidence)  # Cap at 1.0


def get_volume_multiplier(volume_ratio):
    """
    From research: Volume is make-or-break
    """
    if volume_ratio < 0.5:
        return 0.0  # Kill signal
    elif volume_ratio < 1.2:
        return 0.3  # Drastically reduce
    elif volume_ratio < 1.5:
        return 0.6  # Moderately reduce
    elif volume_ratio < 2.0:
        return 1.0  # No change
    elif volume_ratio < 3.0:
        return 1.2  # Boost
    else:
        return 1.3  # Significant boost
```

## Risk Gates Reference

**Dispatcher evaluates 5 gates before execution:**

```python
# 1. Confidence Gate
if confidence < 0.70:
    skip("Low confidence")

# 2. Feature Freshness Gate  
if feature_age_seconds > 300:  # 5 minutes
    skip("Stale features")

# 3. Bar Freshness Gate
if no_recent_bar_data:
    skip("No bar data available")

# 4. Action Allowed Gate
if action not in ["BUY_CALL", "BUY_PUT", "BUY_STOCK"]:
    skip("Action not allowed")
    
# ⚠️ CURRENT BUG: Signal engine outputs "CALL"/"PUT"
#    Dispatcher expects "BUY_CALL"/"BUY_PUT"
#    This is why all 10 current recommendations skipped

# 5. Ticker Daily Limit Gate
if ticker_trades_today >= 2:
    skip("Daily limit reached")
```

## Phase 11 Achievements

### What Was Fixed on Day 6
1. **Feature computation stalled** - Added adaptive lookback
2. **Signal engine crashing** - Fixed column name (classified_at → created_at)
3. **Sentiment scoring backwards** - Treat score as confidence, label as direction
4. **Zero ticker associations** - Added AI inference + ticker-specific feeds

### What Was Deployed in Phase 11
1. **Enhanced classifier** with AI ticker inference
2. **7 new RSS feeds** (Yahoo Finance ticker-specific)
3. **Bedrock integration** for intelligent ticker extraction
4. **Migration 006** to fix dispatcher status constraint

### Current State (Post-Phase 11)
- ✅ Ticker associations: 0% → 28.4% (46 of 162 items)
- ✅ Recommendations generating: 10 in 2 hours
- ✅ Dispatcher processing: 100% success (no errors)
- ⚠️ Execution rate: 0% (all skipped - need volume!)

## Known Issues & Quirks

### Issue 1: Action Naming Mismatch (Minor)
**Problem:** Signal engine outputs "CALL", dispatcher expects "BUY_CALL"  
**Impact:** Causes skips  
**Fix:** Align naming in signal engine or dispatcher  
**Priority:** Low (volume is more important)

### Issue 2: All Recommendations Skipped (Expected)
**Problem:** None executed, all skipped by risk gates  
**Root Cause:** No volume confirmation = low quality signals  
**Impact:** 0% execution rate  
**Fix:** Phase 12 volume analysis  
**Priority:** CRITICAL

### Issue 3: Unfinished Runs Count (Cosmetic)
**Problem:** 6 unfinished runs in database  
**Root Cause:** Pre-migration 006 failures  
**Impact:** None (cleanup lambda handles)  
**Fix:** None needed (will auto-clean)  
**Priority:** None

## Configuration Reference

### Key SSM Parameters
```bash
/ops-pipeline/db_host              # RDS endpoint
/ops-pipeline/db_port              # 5432
/ops-pipeline/db_name              # ops_pipeline
/ops-pipeline/rss_feeds            # JSON array of 10 feeds
```

### Key Secrets
```bash
ops-pipeline/db                    # DB credentials (username/password)
```

### EventBridge Schedules
```bash
# Rules (EventBridge Rules - for ECS tasks)
ops-pipeline-rss-ingest-schedule        # rate(1 minute)
ops-pipeline-classifier-batch-schedule  # rate(1 minute)
ops-pipeline-telemetry-1m-schedule      # rate(1 minute)
ops-pipeline-feature-compute-schedule   # rate(1 minute)

# Schedules (EventBridge Scheduler - new service)
ops-pipeline-signal-engine-schedule     # rate(1 minute)
ops-pipeline-dispatcher-schedule        # rate(1 minute)
ops-pipeline-watchlist-schedule         # rate(5 minutes)
```

## Common Commands

### Check Data
```bash
# Telemetry (has volume!)
aws lambda invoke --function-name ops-pipeline-db-query --region us-west-2 \
  --payload '{"sql":"SELECT ticker, COUNT(*), MAX(ts), MAX(volume) FROM lane_telemetry WHERE ts >= NOW() - INTERVAL '\''1 hour'\'' GROUP BY ticker"}' \
  /tmp/check.json && cat /tmp/check.json | jq '.body | fromjson'

# Features (missing volume_ratio!)
aws lambda invoke --function-name ops-pipeline-db-query --region us-west-2 \
  --payload '{"sql":"SELECT ticker, sma20, close, vol_ratio, computed_at FROM lane_features WHERE computed_at >= NOW() - INTERVAL '\''10 minutes'\'' ORDER BY computed_at DESC LIMIT 10"}' \
  /tmp/check.json && cat /tmp/check.json | jq '.body | fromjson'

# Recommendations
aws lambda invoke --function-name ops-pipeline-db-query --region us-west-2 \
  --payload '{"sql":"SELECT ticker, action, confidence, status FROM dispatch_recommendations ORDER BY created_at DESC LIMIT 10"}' \
  /tmp/check.json && cat /tmp/check.json | jq '.body | fromjson'
```

### Deploy Service
```bash
# Build
cd services/<service-name>
docker build -t ops-pipeline-<service>:phase12 .

# Push
docker tag ops-pipeline-<service>:phase12 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/<service>:phase12
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/<service>:phase12

# Get digest from push output, update task definition
# Register new task definition
aws ecs register-task-definition --region us-west-2 --cli-input-json file://deploy/<service>-task-definition.json

# Update EventBridge rule/schedule with new revision
```

## Phase 12 Implementation Checklist

### Files to Create
- [ ] `db/migrations/007_add_volume_features.sql`
- [ ] `scripts/apply_migration_007.py`

### Files to Modify
- [ ] `services/feature_computer_1m/features.py` - Add compute_volume_features()
- [ ] `services/feature_computer_1m/main.py` - Call volume computation
- [ ] `services/feature_computer_1m/db.py` - Store volume features
- [ ] `services/signal_engine_1m/db.py` - Query volume features
- [ ] `services/signal_engine_1m/rules.py` - Use volume in confidence
- [ ] `deploy/feature-computer-task-definition.json` - Update for new image
- [ ] `deploy/signal-engine-task-definition.json` - Update for new image

### Files NOT to Touch
- ✅ `services/telemetry_ingestor_1m/*` - Already has volume
- ✅ `services/classifier_worker/*` - Just deployed Phase 11
- ✅ `services/dispatcher/*` - Uses confidence, no changes needed
- ✅ `services/watchlist_engine_5m/*` - Independent
- ✅ `services/rss_ingest_task/*` - Independent

## Testing Strategy

### Unit Tests
```python
# Test volume feature computation
def test_volume_features():
    bars = create_test_bars(volume=[100, 150, 200, 180, 220])
    features = compute_volume_features(bars)
    
    assert features['volume_current'] == 220
    assert features['volume_avg_20'] == 170  # Average
    assert features['volume_ratio'] == 1.29  # 220/170
    assert features['volume_surge'] == False # 1.29 < 2.0
```

### Integration Tests
```bash
# After deployment, check logs
aws logs tail /ecs/ops-pipeline/feature-computer-1m --since 5m | grep volume_ratio

# Check database
aws lambda invoke --function-name ops-pipeline-db-query --region us-west-2 \
  --payload '{"sql":"SELECT COUNT(*) FROM lane_features WHERE volume_ratio IS NOT NULL"}' \
  /tmp/check.json

# Should see: {"count": <increasing number>}
```

### Validation Tests
```bash
# Wait 10 minutes after deployment
# Check if recommendations have volume in reasoning
aws lambda invoke --function-name ops-pipeline-db-query --region us-west-2 \
  --payload '{"sql":"SELECT reason FROM dispatch_recommendations ORDER BY created_at DESC LIMIT 1"}' \
  /tmp/check.json

# Look for: "volume" in reason JSON
```

## Success Metrics

### Phase 12 Success Criteria
- [ ] Migration 007 applied successfully
- [ ] Feature computer computing volume_ratio
- [ ] Signal engine using volume in rules
- [ ] Recommendations show volume-based confidence
- [ ] Execution rate improves from 0% to 30-50%

### Data Quality Checks
```sql
-- All features should have volume data
SELECT COUNT(*) as without_
