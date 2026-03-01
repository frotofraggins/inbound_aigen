# Inbound AI Options Trading System - Complete Overview
**Last Updated:** February 11, 2026  
**System Version:** v17 (EOD Engine + Learning Pipeline)  
**Status:** Production-Ready, Paper Trading Active

---

## 📋 Table of Contents

1. [What This System Does](#what-this-system-does)
2. [System Architecture](#system-architecture)
3. [Services & Components](#services--components)
4. [How Trading Decisions Are Made](#how-trading-decisions-are-made)
5. [Data Flow](#data-flow)
6. [AWS Infrastructure](#aws-infrastructure)
7. [Technology Stack](#technology-stack)
8. [Trading Strategy](#trading-strategy)
9. [Risk Management](#risk-management)
10. [Database Schema](#database-schema)

---

## What This System Does

An AI-powered options trading system that:

1. **Selects Tickers** - AI (Bedrock Claude) picks 25-50 stocks weekly
2. **Ingests News** - RSS feeds → FinBERT sentiment analysis
3. **Captures Market Data** - 1-minute price/volume bars from Alpaca
4. **Computes Features** - Technical indicators (SMA, trend, volume ratios)
5. **Generates Signals** - Rule-based engine with AI confidence adjustment
6. **Executes Trades** - Alpaca Paper Trading API (options)
7. **Monitors Positions** - Real-time tracking with automatic exits
8. **Learns from Outcomes** - Captures trade data for future AI improvements

**Current Performance:**
- **Accounts:** 2 (large $121K, tiny $1K)
- **Trades:** 35+ closed positions analyzed
- **Win Rate:** Improving (trailing stops + EOD engine active)
- **Services:** 11 components, 10 working (91%)
- **Learning Pipeline:** Fully automated (Trade Analyzer → Learning Applier → SSM updates)

---

## System Architecture

### High-Level Architecture
```
┌──────────────────────────────────────────────────────────────┐
│                    DATA INGESTION (3 services)                │
├──────────────────────────────────────────────────────────────┤
│ • RSS News           (1min)  → Articles                      │
│ • Market Data        (1min)  → Price/volume bars             │
│ • Ticker Discovery   (weekly)→ AI watchlist (Bedrock)        │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│                    PROCESSING (3 services)                    │
├──────────────────────────────────────────────────────────────┤
│ • Sentiment Analysis (5min)  → FinBERT scores                │
│ • Feature Computer   (1min)  → Technical indicators          │
│ • Watchlist Engine   (5min)  → Opportunity scoring           │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│                    DECISION (3 services)                      │
├──────────────────────────────────────────────────────────────┤
│ • Signal Engine      (1min)  → BUY/SELL recommendations      │
│ • Dispatcher (large) (1min)  → Trade execution               │
│ • Dispatcher (tiny)  (1min)  → Trade execution (8% risk)     │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│                    MONITORING (2 services)                    │
├──────────────────────────────────────────────────────────────┤
│ • Position Manager (large) (1min) → Exit monitoring          │
│ • Position Manager (tiny)  (1min) → Exit monitoring          │
│ • Trade Stream WebSocket      → Real-time position sync      │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│                    STORAGE & LEARNING                         │
├──────────────────────────────────────────────────────────────┤
│ • PostgreSQL RDS      → All data (position history, features)│
│ • Future AI Learning  → Pattern recognition (50+ trades)     │
└──────────────────────────────────────────────────────────────┘
```

### Deployment Model
- **All services run in AWS ECS Fargate** (serverless containers)
- **NO local Docker** - everything in cloud
- **Database in private VPC** - accessed via Lambda or ECS services
- **EventBridge scheduling** - triggers tasks every 1-5 minutes
- **CloudWatch logs** - centralized logging

---

## Services & Components

### Persistent Services (6)
Run 24/7 in ECS:

1. **dispatcher-service** (large account)
   - Executes trades on Alpaca
   - Risk gates and position sizing
   - Tier-based allocation (5-20% of capital)

2. **dispatcher-tiny-service** (tiny account)
   - Conservative risk (8% max position size)
   - Same logic as large account
   - Learning/testing environment

3. **position-manager-service** (large)
   - Monitors open positions every minute
   - Tracks P&L, peak gains, trailing stops
   - EOD Exit Engine: graduated close windows, theta scoring, VIX regime, earnings calendar
   - Close-Loop Monitor: detects stuck closes, retries, queues for next open
   - Overnight outcome logging for learning pipeline
   - Key modules: `monitor.py`, `exits.py`, `eod_engine.py`, `eod_config.py`, `eod_models.py`, `close_loop.py`, `earnings_client.py`

4. **position-manager-tiny-service** (tiny)
   - Same monitoring + EOD engine for tiny account
   - Tighter overnight hold thresholds (15% P&L, $200 exposure limit)

5. **telemetry-service**
   - Captures 1-minute market data from Alpaca
   - Stores in lane_telemetry table

6. **trade-stream**
   - WebSocket connection to Alpaca
   - Real-time position updates
   - Syncs position status instantly

### Scheduled Tasks (5)
Run on EventBridge schedules:

### One-Shot Tasks
Run manually or on-demand:

1. **trade-analyzer** (ops-pipeline-trade-analyzer:1)
   - Statistical analysis of trade outcomes
   - Joins position_history → dispatch_executions → dispatch_recommendations
   - Analyzes: instrument bias, confidence thresholds, volume surge impact, exit reasons, trend alignment, volatility
   - Writes findings to `learning_recommendations` table (status='pending')
   - Never auto-applies changes — human review required
   - Run after market close or when trade count increases significantly

2. **learning-applier** (ops-pipeline-learning-applier:1)
   - Reads pending `learning_recommendations`
   - Uses Bedrock Claude 3.5 Sonnet to evaluate each finding
   - SSM-configurable params: auto-applies if AI approves (saves rollback value)
   - Code-level params: marks as 'ai_approved' for human deploy
   - Pre-filters: rejects if sample_size < 10 or confidence < 0.5
   - Scheduled 15 min after trade-analyzer

### Scheduled Tasks (continued)

7. **signal-engine-1m** (every minute)
   - Version 16: Momentum urgency + gap fade
   - Generates BUY/SELL/HOLD recommendations
   - Writes to dispatch_recommendations table

8. **feature-computer-1m** (every minute)
   - Computes technical indicators
   - SMA20, SMA50, trend_state, volume ratios
   - Stores in lane_features table

9. **watchlist-engine-5m** (every 5 minutes)
   - Scores opportunities across watchlist
   - Ranks tickers by setup quality

10. **ticker-discovery** (weekly)
    - AI (Bedrock Claude 3.5 Sonnet) selects tickers
    - Analyzes sectors, volatility, liquidity
    - Updates watchlist (25-50 stocks)

11. **rss-ingest-task** (every minute)
    - Fetches news from RSS feeds
    - Stores raw articles
    - Feeds classifier for sentiment

### Disabled Services (1)

12. **news-stream** (DISABLED)
    - NewsDataStream API not in alpaca-py 0.21.0
    - RSS feeds serve as backup
    - Not critical for trading

---

## How Trading Decisions Are Made

### Decision Process

**Step 1: Trend Analysis**
```python
if price > SMA20 and SMA20 > SMA50:
    trend_state = +1  # Uptrend (bullish)
elif price < SMA20 and SMA20 < SMA50:
    trend_state = -1  # Downtrend (bearish)
else:
    trend_state = 0   # No clear trend
```

**Step 2: Direction Selection**
```python
if trend_state == +1 and price_breakout_up:
    direction = "CALL"  # Buy call options
elif trend_state == -1 and price_breakout_down:
    direction = "PUT"   # Buy put options
else:
    direction = "STOCK"  # or HOLD
```

**Step 3: Confidence Calculation**
```
base_confidence = (
    0.35 * trend_alignment +
    0.25 * entry_quality +
    0.20 * volatility_fit +
    0.20 * base_conviction
)

final_confidence = base_confidence × sentiment_boost × volume_mult
```

**Step 4: Risk Gates (11 checks)**
1. Buying power available?
2. Position limit not exceeded?
3. Daily loss limit OK?
4. Ticker not on cooldown?
5. Volume sufficient (>1.5x average)?
6. Confidence above threshold?
7. Market hours?
8. Not too close to expiration?
9. Contract quality acceptable?
10. Spread reasonable?
11. No conflicting positions?

**Step 5: Execution**
- If all gates pass → Place order on Alpaca
- If any gate fails → Log rejection reason, HOLD

### AI Components

**Currently Active:**
1. **Bedrock Claude 3.5 Sonnet** - Ticker selection (weekly)
2. **FinBERT** - Sentiment analysis (news articles)

**Future (after 50 trades):**
3. **Confidence Adjustment** - Learn from outcomes
4. **Pattern Recognition** - Identify setup types
5. **Risk Calibration** - Adjust position sizing

---

## Data Flow

### Minute-by-Minute Flow
```
00:00 → Telemetry fetches market data
00:10 → Feature computer calculates indicators
00:20 → Signal engine generates recommendations
00:30 → Dispatcher evaluates risk gates
00:40 → If approved, place order on Alpaca
00:45 → Position manager checks open positions
00:50 → Update trailing stops, check exits
01:00 → Cycle repeats
```

### Communication Pattern

Services don't talk to each other directly. They use the database:

```
Signal Engine → Writes to dispatch_recommendations
     ↓
Dispatcher → Reads unprocessed recommendations (non-exclusive, filtered by account_name)
     ↓                  Both dispatchers can process the same recommendation independently.
     ↓                  Idempotency enforced by UNIQUE(recommendation_id, account_name).
Dispatcher → Writes to dispatch_executions
     ↓
Position Manager → Reads from active_positions
     ↓
Position Manager → Updates active_positions (live option quotes from Market Data API)
     ↓
On close → Writes to position_history
```

---

## AWS Infrastructure

### Core Resources

**Compute:**
- ECS Cluster: `ops-pipeline-cluster`
- Task Execution Role: `ops-pipeline-ecs-task-role`
- Container Registry: ECR (11 repositories)

**Database:**
- RDS PostgreSQL 14.9
- Instance: db.t3.micro
- VPC: Private subnets only
- Security Group: Restricts to ECS services only
- Endpoint: `ops-pipeline-db.cls4wuyg010k.us-west-2.rds.amazonaws.com`

**Scheduling:**
- EventBridge Scheduler
- 5 schedules (signal, features, watchlist, ticker, rss)
- Cron expressions for timing

**Networking:**
- VPC: `vpc-0444cb2b7a3457502`
- Private Subnets: ECS tasks + RDS
- NAT Gateway: Outbound internet (Alpaca API)
- Security Groups: Least-privilege access

**Secrets:**
- Secrets Manager: Alpaca API keys
- `ops-pipeline/alpaca` — Large account (account_name: large-100k)
- `ops-pipeline/alpaca/large` — Same (dispatcher loads by tier name)
- `ops-pipeline/alpaca/tiny` — Tiny account

**Logging:**
- CloudWatch Logs
- Log Groups: `/ecs/ops-pipeline/*`
- Retention: 30 days

**Storage:**
- S3: Build artifacts (optional)
- RDS: All operational data

---

## Technology Stack

**Languages:**
- Python 3.11 (all services)

**Key Libraries:**
- `alpaca-py` 0.43.2 - Alpaca API client
- `psycopg2` - PostgreSQL driver
- `transformers` + `torch` - FinBERT sentiment
- `boto3` - AWS SDK
- `requests` - Alpaca Market Data API (option quotes)
- `pandas`, `numpy` - Data processing

**AWS Services:**
- ECS Fargate
- RDS PostgreSQL
- EventBridge
- CloudWatch
- Secrets Manager
- ECR
- Lambda (db queries)

**External APIs:**
- Alpaca Markets - Trading & market data
- RSS Feeds - News articles
- AWS Bedrock - AI ticker selection

**Infrastructure:**
- Docker containers
- ECS task definitions
- EventBridge schedules
- Bash deployment scripts

---

## Trading Strategy

### Signal Types

**1. Momentum Urgency (v16)**
- Detects breakouts at the START (not tail end)
- 25% confidence boost for early entry
- Volume surge + strong trend required

**2. Gap Fade Strategy (v16)**
- Trades morning gaps (9:30-10:30 AM ET)
- Fades overnight moves that overextend
- Mean reversion play

**3. Trend Following**
- Core strategy: Follow SMA trends
- Enter on pullbacks in uptrends
- Exit on trend exhaustion

### Position Types

**Day Trades (0-1 DTE options):**
- High confidence (>0.60)
- Volume surge (>2x average)
- Strong breakout
- Aggressive exits: 4-hour max hold

**Swing Trades (7-30 DTE options):**
- Medium confidence (>0.45)
- Good volume (>1.2x average)
- Clear trend
- Longer hold: up to market close

**Stock Positions:**
- Weak or no clear trend
- Lower confidence
- Alternative when options don't fit

### Exit Strategy

**Take Profit:** +80% gain
**Stop Loss:** -40% loss (widened from -40% based on backtest)
**Trailing Stops:** Lock 75% of peak gains (active since Feb 6)
**Time Stop:** 4 hours for day trades (max_hold_minutes)

**EOD Exit Engine (NEW — Feb 11):**
Replaces the blanket 3:55 PM force-close with a strategy-aware, P&L-aware system:

- **Graduated Close Windows:** 4 evaluation checkpoints (2:30, 3:00, 3:30, 3:55 PM ET) with progressively stricter criteria
- **Strategy Routing:** Day trades close at final window; swing trades evaluated against overnight hold criteria
- **Overnight Hold Criteria:** Swing trades can hold overnight if they pass DTE (≥3), P&L (≥10%), and position size (≤5% of equity) checks
- **Theta Scoring:** High theta decay (>5% daily premium loss) lowers P&L threshold; DTE ≤2 + high theta forces close
- **VIX Regime Adjustment:** Elevated VIX tightens P&L threshold (1.5x); high VIX tightens further (2x) and halves exposure; extreme VIX forces close all
- **Earnings Calendar:** Positions with earnings within 1 trading day are force-closed
- **Overnight Exposure Limit:** Aggregate overnight notional capped ($5K large, $200 tiny); least profitable closed first
- **Close-Loop Monitor:** Detects stuck closing positions, retries once, queues for next open if market closed
- **Duplicate Prevention:** One position per ticker/account/instrument type enforced

**Entry Cutoff Gates (NEW — Feb 11):**
- Day trade cutoff: 2 PM ET (large), 1 PM ET (tiny)
- Swing trade cutoff: 3 PM ET (large), 2 PM ET (tiny)
- After-hours blocking: No entries outside 9:30 AM - 4:00 PM ET
- Duplicate position blocking: No new position if ticker already open/closing

All EOD parameters are SSM-configurable (JSON in Parameter Store) per account tier.

---

## Risk Management

### Position Sizing

**Large Account ($121K):**
- Tier 1 (highest confidence): 20% of capital
- Tier 2: 15% of capital
- Tier 3: 10% of capital
- Tier 4: 5% of capital

**Tiny Account ($1K):**
- Maximum: 8% of capital per position
- Conservative risk for learning

### Risk Gates

**Daily Limits:**
- Max loss per day: -10% of account
- Max positions: 5 concurrent
- Ticker cooldown: 30 minutes after close

**Entry Cutoff Gates (NEW — Feb 11):**
- Day trade cutoff: 2 PM ET (large), 1 PM ET (tiny)
- Swing trade cutoff: 3 PM ET (large), 2 PM ET (tiny)
- After-hours blocking: No entries outside 9:30 AM - 4:00 PM ET
- Duplicate position blocking: No new position if ticker already open/closing

**Quality Filters:**
- Contract bid/ask spread < 10%
- Option volume > 100 contracts/day
- Open interest > 500
- Days to expiration: 0-30 only

**Volume Requirements:**
- Minimum: 0.5x average (safety gate)
- Target: 1.5x average (normal entry)
- Ideal: 2x average (day trade)

---

## Database Schema

### Key Tables

**1. active_positions**
- Current open positions
- Real-time P&L tracking
- Peak price, trailing stops (NEW as of Feb 6)
- Entry features snapshot

**2. position_history**
- Closed positions
- Learning dataset (13 trades captured)
- Entry/exit prices, P&L, hold duration
- Peak gains (MFE), worst drawdown (MAE)

**3. dispatch_recommendations**
- Generated signals (1-2 per minute)
- BUY/SELL/HOLD with confidence scores
- Ticker, direction, reasoning

**4. dispatch_executions**
- Executed orders
- Alpaca order IDs
- Execution details, fill prices

**5. lane_telemetry**
- 1-minute market data
- OHLCV bars, volume, timestamps

**6. lane_features**
- Technical indicators
- SMA20, SMA50, trend_state
- Volume ratios, volatility

**7. news_articles & sentiment**
- Raw news articles
- FinBERT sentiment scores
- Article timestamps, sources

**8. position_events** (expanded Feb 11)
- `eod_decision` — full EOD evaluation per position (strategy, P&L, theta, VIX, window, criteria)
- `overnight_hold` — positions qualifying for overnight hold with criteria snapshot
- `overnight_outcome` — next-day open vs previous close P&L for held positions
- `close_retry` — stuck position retry attempts
- `close_failed` — positions requiring manual review
- `duplicate_cleanup` — duplicate position cleanup events

**9. learning_recommendations**
- Trade Analyzer statistical findings
- Bedrock Claude AI review decisions
- SSM parameter change history

---

## System Capabilities

### ✅ What It Does Well

1. **Automated Trading** - 24/7 signal generation
2. **Risk Management** - 11 gates before every trade
3. **Multi-Account** - Different risk profiles
4. **Real-Time Monitoring** - 1-minute position checks
5. **Options Trading** - Calls and puts selection
6. **Trailing Stops** - Protect winners (NEW)
7. **Data Capture** - 100% of trades logged

### ⚠️ Limitations

1. **No news WebSocket** - alpaca-py limitation
2. **No Greeks analysis** - IV, delta, gamma (planned)
3. **1-minute granularity** - not high-frequency
4. **Paper trading only** - real money requires compliance

### 🚀 Planned Improvements

1. **AI Learning** - Adjust confidence from outcomes
2. **IV Rank filtering** - Only trade high IV (>30th percentile)
3. **Partial exits** - Take 50% at +50% profit
4. **Position rolling** - Extend profitable trades
5. **Kelly Criterion** - Optimal position sizing

---

## Performance Metrics

**As of February 11, 2026:**

**System Health:**
- Services running: 10/11 (91%)
- Uptime: 99.9%
- Signal generation: 1-4 per minute
- Execution latency: <5 seconds
- Learning pipeline: Fully automated (daily)

**Trading Performance:**
- Closed trades: 35+
- Win rate: Improving (trailing stops + EOD engine active)
- Best winner: +84% (GOOGL)
- Worst loser: -52% (AMD)
- Learning: Automated daily analysis + AI-reviewed parameter tuning

**Data Quality:**
- Market data: 39/39 tickers OK
- Feature computation: 100% success rate
- Position tracking: Live option quotes via Market Data API
- Learning data: 100% capture rate

---

## Key Insights

**What Causes Losses:**
1. **Peak reversals** (31%) - Fixed with trailing stops
2. **Late entries** (46%) - Fixed with momentum urgency v16
3. **Proper exits** (23%) - Working correctly

**What Causes Wins:**
1. Early entry on breakouts
2. Strong trends
3. Take profit at +80%

**Expected Improvement:**
- Trailing stops save ~$600-700 per trading cycle
- Momentum urgency reduces late entries
- Combined: Win rate from 23% → 50-60%

---

## Documentation Map

**This Document:** Complete system overview

**Operations:** See OPERATIONS_GUIDE.md

**Current Status:** See CURRENT_STATUS.md

**Source Code:** `/services/` directory

**Deployment:** `/deploy/` task definitions + scripts

---

**System is production-ready, actively trading, and continuously improving through captured learning data.**
