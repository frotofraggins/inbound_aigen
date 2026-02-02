# Current System Status - January 30, 2026

**Update (Jan 30, 2026 ~5:06 PM ET):** Trades are not firing after market close due to the `trading_hours` gate.  
Dispatchers are running and generating signals, but recent recommendations are **SKIPPED** with `trading_hours` (and sometimes `confidence` for tiny tier).

**Last real trades:** Jan 29, 2026 ~11:17–11:36 AM ET (ALPACA_PAPER).

**Last Updated:** Jan 30, 2026 10:06 PM UTC (5:06 PM ET)  
**System:** Fully operational (Phases 1-17 complete)  
**Trading:** Options API fixed, Phase 17 learning deployed  
**Latest:** Shorting enabled, trade-stream WebSocket fixed and running

---

## 🔥 Latest Updates - January 30, 2026

### Trading Hours Gate (CURRENT) ⚠️
- **Dispatcher blocks trades outside 9:30–16:00 ET** (and 9:30–9:35 / 15:45–16:00).
- This is the primary reason no trades are happening after market close.
- Tiny tier now uses **min confidence = 0.60**, which still blocks some options signals.
- SELL_STOCK is allowed and **shorting is enabled** (no long position required).

### Trade-Stream WebSocket (FIXED) ✅
- No-cache rebuilds applied.
- Secrets Manager references corrected.
- DB host corrected to SSM value; DB user now sourced from secret.
- Trade-stream is running; account activities are inserting.

### DB Hygiene for AI Training (Jan 30) ✅
- Removed 8,379 `lane_features` rows with NULL `volume_ratio`; remaining rows: 15,385.
- Created view `lane_features_clean` (filters to complete feature rows).
- Fixed NULL `transaction_time` in `account_activities` (now 0 nulls).
- `dispatch_executions` still pending fills (85 rows have NULL executed_at) — expected until trades execute.

---

## 🔥 Historical Updates - January 29, 2026

### Options API Fix (CRITICAL) ✅
**Problem:** Dispatcher using wrong endpoint → 404 errors  
**Fix:** Corrected to `/v1beta1/options/snapshots/{ticker}`  
**Result:** Now fetching 165+ contracts per ticker!  
**Deployed:** Dispatcher revision 13

### Phase 17 AI Learning (DEPLOYED) ✅
**Purpose:** Captures options bars for ML training (NOT trade validation)  
**Deployed:** position-manager revision 2  
**Tables:** option_bars, iv_surface ready  
**Status:** Bar capture active when positions open

### AI Pipeline Clarification ✅
**Bedrock:** Ticker discovery (weekly)  
**FinBERT:** Sentiment (confidence modifier)  
**Trade Validation:** Rule-based gates (NOT AI) - industry standard

**See:** `deploy/AI_PIPELINE_EXPLAINED.md` for complete details

---

## Quick Reference

### What's Running Now (Verified 17:10 UTC)
```
✅ Database: 15 tables, 12 migrations
✅ Data Ingestion: 422 events today, 3,864 bars (6h)
✅ Features: 1,233 computed, 104 volume surges
✅ Sentiment: FinBERT analyzing (418 classified today)
✅ Watchlist: 16 active tickers
✅ Signals: Running every 60s (generating HOLD - low volume)
✅ Alpaca: Options integration working (test order proven)
✅ Trade-stream: WebSocket connected, account activity inserts active
```

### Current Status
```
Signal Engine: Running (last: 17:10:40)
- Generating HOLD due to low volume (< 0.5x threshold)
- This is CORRECT behavior during low volume periods

Alpaca Integration: PROVEN WORKING
- Test order: SPY260130C00609000 FILLED
- Position tracking: -$404 P/L (real-time)
- Dashboard: https://app.alpaca.markets/paper/dashboard

Automated Trades: Pending
- 25 historical trades (before Alpaca deployment)
- System generating HOLD signals (volume/confidence gates)
- Will trade when conditions improve
```

---

## Complete Data Flow

```
Phase 5-7: DATA INGESTION (Every 1-30 minutes)
RSS → FinBERT → Telemetry → Database

Phase 8-12: FEATURE COMPUTATION & SIGNALS (Every 1-5 minutes)
Telemetry → Features (SMA, volume_ratio, etc.)
Features + Sentiment → Signal Engine → Signals (CALL/PUT/STOCK)

Phase 13-15: TRADING EXECUTION (Every 5 minutes)
Signals → Dispatcher → Alpaca API → Positions
Positions → Position Manager → Stop/Target enforcement

Phase 14: AI LEARNING (Every 6 hours)
Bedrock Sonnet → Ticker recommendations → SSM update
```

---

## Current Infrastructure (As of Jan 28, 2026)

### ECS Services (All ENABLED, Verified Running)
```
telemetry-ingestor-1m: Pulls market data (Alpaca + yfinance)
  Status: ✅ Running, 3,864 bars collected (6h)
  
feature-computer-1m: Computes technical indicators  
  Status: ✅ Running, 1,233 features computed (6h)
  
classifier-worker: FinBERT sentiment analysis
  Status: ✅ Running, 418 classified today
  
signal-engine-1m: Generates trading signals
  Status: ✅ Running (rev 11), last run 17:10:40
  Note: Generating HOLD (low volume - correct behavior)
  
watchlist-engine-5m: Prioritizes tickers
  Status: ✅ Running, 16 tickers active
  
dispatcher: Executes trades (Alpaca API)
  Status: ✅ Running (rev 10 with options)
  Latest: SPY260130C00609000 test order FILLED
  
position-manager: Monitors open positions
  Status: ✅ Running, tracking 1 position
  
ticker-discovery: AI recommendations (Bedrock Sonnet)
  Status: ✅ Running, 10 recommendations active
```

### Lambda Functions
```
ops-pipeline-db-query: Query database (read-only)
  Status: ✅ Operational
  Note: Use 'sql' key, expect 'rows' response
  
ops-pipeline-db-migration: Apply migrations
  Status: ✅ Operational (Migrations 011 & 012 applied)
  
ops-pipeline-healthcheck: System health
  Status: ✅ Operational
  
ops-ticker-discovery: DELETED (security compliance)
  Reason: Secrets in environment variables
```

### EventBridge Schedules (All ENABLED)
```
Every 1 min: signal-engine, dispatcher
Every 5 min: watchlist-engine
Others: As configured per service
```

---

## Pipeline Data Verification (Last 24 Hours)

### ✅ Component 1: RSS Ingestion
- **Events Fetched**: 422 articles
- **Latest**: 2026-01-28 17:06:38
- **Status**: Operational, fetching every 30 min

### ✅ Component 2: AI Sentiment Classification  
- **Classified**: 418 articles (99% coverage)
- **Distribution**: Positive/Negative/Neutral
- **Model**: FinBERT
- **Status**: AI model operational

### ✅ Component 3: Telemetry (Price Data)
- **Tickers**: 30 tracked
- **Bars**: 3,864 (6-hour window)
- **Granularity**: 1-minute OHLCV
- **Status**: Real-time market data flowing

### ✅ Component 4: Feature Computation
- **Features**: 1,233 computed
- **Indicators**: SMA20, SMA50, volatility, volume_ratio (10 total)
- **Volume Surges**: 104 detected
- **Status**: Technical analysis operational

### ✅ Component 5: Watchlist Engine
- **Active Tickers**: 16
- **AI Scored**: 10 recommendations from Bedrock
- **Top**: NVDA, MSFT, AMD, GOOGL, META
- **Status**: AI-based ticker selection working

### ✅ Component 6: Signal Engine
- **Signals Generated**: 785 (last 24h)
- **Latest Run**: 17:10:40 (every 60s)
- **Current Output**: HOLD (volume < 0.5x threshold)
- **Status**: Running correctly, applying risk gates

### ✅ Component 7: Dispatcher
- **Trades Executed**: 25 (historical)
- **Latest**: 15:54:36 (before Alpaca deployment)
- **Mode**: ALPACA_PAPER (with fallback)
- **Status**: Ready to execute via Alpaca

### ✅ Component 8: Position Manager
- **Tracking**: 1 active position (SPY260130C00609000)
- **Monitoring**: Every 5 minutes
- **Exits**: Stop/profit automated
- **Status**: Operational

### ✅ Component 9: Alpaca Integration
- **Test Order**: SPY260130C00609000 FILLED at $89.35
- **Position P/L**: -$404 (updating real-time)
- **Dashboard**: Live and accessible
- **API**: Account, positions, orders all working
- **Status**: PROVEN WORKING

---

## Key Parameters (config/trading_params.json)

### Signal Generation
```json
{
  "sentiment_threshold": 0.50,  // Requires strong sentiment
  "sma_tolerance": 0.005,       // ±0.5% = AT support/resistance
  "confidence_min": 0.55,       // Day trade threshold
  "volume_min": 2.0             // 2x average volume
}
```

### Current Settings
- **TOO STRICT:** Sentiment 0.50 (very bullish/bearish)
- **FIXED:** SMA tolerance 0.005 (allows at support)
- **GOOD:** Confidence 0.55, Volume 2.0x

### Recommended Adjustments
- Sentiment: Lower to 0.10 (directional vs extreme)
- Would enable 10x more trades
- All other parameters good

---

## What Needs Deployment

### Signal Engine Fix (5 minutes)
```bash
cd services/signal_engine_1m
docker build -t signal-engine .
aws ecr get-login-password | docker login ...
docker tag signal-engine:latest 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/signal-engine-1m:latest
docker push ...

# Get new digest, update signal-engine-task-definition.json
aws ecs register-task-definition --cli-input-json file://deploy/signal-engine-task-definition.json
# ECS will pick up new revision automatically
```

**After Deploy:**
- NVDA ±18 cents will qualify
- Should see 3-5 signals within 30 minutes
- Both CALL and PUT trades
- Tomorrow will be active

---

## All Permissions (Verified Correct)

### ops-pipeline-lambda-role
```
✅ Phase14AdditionalPermissions: Bedrock, SSM write, SES
```

### ops-pipeline-ecs-task-role
```
✅ Phase14BedrockPermissions: Bedrock, SSM write, SES
✅ AllowBedrockInvoke
```

### ops-pipeline-eventbridge-ecs-role
```
✅ RunECSTask: rss-ingest, ticker-discovery
✅ ops-pipeline-eventbridge-ecs-policy
```

---

## Documentation Map

### Current System
- **THIS FILE:** Quick reference
- `deploy/COMPLETE_TRADING_LOGIC_EXPLAINED.md`: Signal logic end-to-end
- `config/trading_params.json`: All tunable parameters

### Phase Completion
- `deploy/PHASE_14_TICKER_DISCOVERY_SUCCESS.md`: Phase 14A details
- `deploy/PHASE_15_DEPLOYMENT_COMPLETE.md`: Trading deployed
- `deploy/PHASE_15C_DEPLOYMENT_COMPLETE.md`: Position Manager

### Verification
- `scripts/verify_all_phases.py`: Test Phases 1-15
- `deploy/SESSION_COMPLETE_2026-01-27.md`: Today's session

### Historical (Archive)
- `deploy/PHASE_*_COMPLETE.md`: Individual phase docs
- `deploy/PHASE_14_*.md`: Phase 14 journey docs

---

## Quick Commands

### Check System Health
```bash
python3 scripts/verify_all_phases.py
```

### Check Recent Activity
```bash
# Recent signals
python3 scripts/check_news_sentiment.py

# Data flow
python3 scripts/quick_pipeline_check.py

# Full verification
python3 scripts/verify_pipeline_e2e.py
```

### Deploy Signal Fix
```bash
# See "What Needs Deployment" section above
cd services/signal_engine_1m && docker build -t signal-engine .
# Then push and update task definition
```

---

## Next Session Tasks

1. **Deploy signal fix** (5 min)
2. **Monitor first signals** (30 min)
3. **Verify first trades** (watch logs)
4. **Tune if needed** (adjust params in config)
5. **Document results** (what worked)

---

**STATUS: Ready to trade after signal_engine deployment**

**See:** `config/trading_params.json` for all tunable parameters
