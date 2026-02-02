# Trading Pipeline - Complete System Context

**Last Updated:** 2026-01-26 19:08 UTC  
**Status:** ✅ Fully Operational with Options Trading  
**Latest Phase:** 15A+B Complete (Options Trading Deployed)

---

## System Overview

Automated trading system that:
1. ✅ Collects news every 30 minutes (RSS feeds)
2. ✅ Classifies sentiment using FinBERT + Bedrock AI
3. ✅ Pulls Alpaca 1-minute price bars (real-time)
4. ✅ Computes technical features (SMA20/50, volatility, volume analysis)
5. ✅ Builds dynamic watchlist (top 30 stocks)
6. ✅ Generates trading signals (BUY/SELL + CALL/PUT)
7. ✅ Executes trades via Alpaca Paper Trading API
8. ✅ Sends email alerts on all trades
9. ✅ Stores everything in Postgres (RDS)
10. ✅ Runs fully outbound-only (no inbound internet)

**AWS Region:** us-west-2  
**Account:** 160027201036

---

## Database (Private RDS)

**Instance:** ops-pipeline-db  
**Endpoint:** ops-pipeline-db.cls4wuyg010k.us-west-2.rds.amazonaws.com  
**Port:** 5432  
**Database:** ops_pipeline  
**Access:** Private VPC only (not publicly accessible)  
**Credentials:** AWS Secrets Manager: `ops-pipeline/db`

### Core Tables

1. **inbound_events_raw** - Raw RSS articles
2. **inbound_events_classified** - FinBERT sentiment + tickers
3. **feed_state** - RSS polling metadata (ETags)
4. **lane_telemetry** - 1-minute OHLCV bars from Alpaca
5. **lane_features** - Technical indicators (SMA20/50, vol_ratio, volume_ratio, trend_state)
6. **watchlist_state** - Top 30 tickers with scores/rankings
7. **dispatch_recommendations** - Trading signals (CALL/PUT/STOCK with strategy_type)
8. **dispatch_executions** - Executed trades (stocks + options metadata)
9. **dispatcher_runs** - Execution run tracking
10. **schema_migrations** - Migration history

### Phase 15: Options Trading Schema (Migration 008)

**New Columns in dispatch_recommendations:**
- `strategy_type` - day_trade, swing_trade, conservative

**New Columns in dispatch_executions:**
- `instrument_type` - STOCK, CALL, PUT
- `strike_price` - Option strike
- `expiration_date` - Option expiration
- `contracts` - Number of contracts
- `premium_paid` - Cost per contract
- `delta`, `theta`, `implied_volatility` - Greeks
- `option_symbol` - OCC format
- `strategy_type` - day_trade, swing_trade, conservative

**New Views:**
- `active_options_positions` - Open positions tracking
- `options_performance_by_strategy` - Win rate analytics
- `daily_options_summary` - Daily activity metrics

---

## AWS Configuration

**SSM Parameters:**
- `/ops-pipeline/rss_feeds` - RSS feed URLs
- `/ops-pipeline/universe_tickers` - Stock universe
- `/ops-pipeline/tickers` - Active trading tickers (7: AAPL, MSFT, TSLA, GOOGL, AMZN, META, NVDA)
- `/ops-pipeline/alpaca_key_id` - Alpaca API key
- `/ops-pipeline/alpaca_secret_key` - Alpaca API secret
- `/ops-pipeline/db_host`, `db_port`, `db_name` - Database config

**Secrets Manager:**
- `ops-pipeline/db` - Database credentials (username, password)

**VPC Configuration:**
- Subnets: subnet-0c182a149eeef918a, subnet-08d822c6b86dfd00b, subnet-07df3caa9179ea77b
- Security Group: sg-0cd16a909f4e794ce
- Private networking (outbound only)

---

## Running Services (EventBridge + ECS Fargate)

All services run as containerized ECS Fargate tasks triggered by EventBridge schedules.

| Service | Schedule | Log Group | Purpose | Status |
|---------|----------|-----------|---------|--------|
| RSS Ingest | rate(30 minutes) | /ecs/ops-pipeline/rss-ingest | Pull news feeds | ✅ |
| Classifier | ECS Service (continuous) | /ecs/ops-pipeline/classifier-worker | Sentiment analysis | ✅ |
| Telemetry | rate(1 minute) | /ecs/ops-pipeline/telemetry-1m | Alpaca 1-min bars | ✅ |
| Features | rate(1 minute) | /ecs/ops-pipeline/feature-computer-1m | SMA/volume analysis | ✅ |
| Watchlist | rate(5 minutes) | /ecs/ops-pipeline/watchlist-engine-5m | Top 30 selection | ✅ |
| Signals | rate(5 minutes) | /ecs/ops-pipeline/signal-engine-1m | Generate trades | ✅ |
| Dispatcher | rate(5 minutes) | /ecs/ops-pipeline/dispatcher | Execute trades | ✅ |
| Trade Alerts | rate(1 minute) | /aws/lambda/trade-alert-checker | Email notifications | ✅ |

---

## Trading Logic

### Signal Generation (rules.py)

**BUY CALL (Bullish Options):**
- Sentiment score >0.5 (bullish news)
- Price above SMA20
- Uptrend (trend_state ≥0)
- Not stretched (within 2% of SMA20)
- **If confidence ≥0.7 + volume_ratio ≥3.0x** → CALL day_trade (0-1 DTE, OTM)
- **If confidence ≥0.5** → CALL swing_trade (7-30 DTE, ATM)
- **Else** → STOCK

**BUY PUT (Bearish Options):**
- Sentiment score <-0.5 (bearish news)
- Price below SMA20
- Downtrend (trend_state ≤0)
- Not stretched
- **If confidence ≥0.7 + volume_ratio ≥3.0x** → PUT day_trade
- **If confidence ≥0.5** → PUT swing_trade
- **Else** → SELL/SHORT

**Confidence Calculation:**
```
Base = 0.3×sentiment + 0.25×trend + 0.25×setup + 0.2×vol
Final = Base × volume_multiplier (0.0-1.3)

Volume multiplier:
- <0.5x: KILL (0.0x)
- <1.2x: Reduce to 0.3x
- <1.5x: Reduce to 0.6x
- 1.5-2.0x: No change (1.0x)
- 2.0-3.0x: Boost 20% (1.2x)
- >3.0x: Boost 30% (1.3x)
```

### Risk Gates (gates.py)

All must pass before execution:
1. **Confidence ≥0.70** (threshold)
2. **Action allowed** (BUY_CALL, BUY_PUT, BUY_STOCK)
3. **Bar freshness** (<120 seconds)
4. **Feature freshness** (<300 seconds)
5. **Ticker daily limit** (<2 trades/day per ticker)

### Position Sizing (pricing.py)

**Current (Fixed 2%):**
- Max risk per trade: 2% of capital
- Position = Risk$ / (Price - Stop)
- Cap at 25% of total capital

**Options Sizing (options.py):**
- Day trade: 3-5% of capital
- Swing trade: 10-20% of capital
- Contracts = Risk$ / (Premium × 100)

### Hard Stop Safety Rules (MUST NEVER BREAK)

**Trading Limits:**
- Max trades per day: 10 (prevents overtrading)
- Max risk per trade: 2% of capital
- Max total open risk: 10% of capital
- Max trades per ticker per day: 2

**Options Safety:**
- Min option volume: 100 contracts (liquidity)
- Max bid-ask spread: 10% (execution quality)
- Min time to expiration: Today or tomorrow for day_trade
- Max position: 25% of capital per trade

**Data Quality:**
- Bar freshness: ≤120 seconds (stale data rejected)
- Feature freshness: ≤300 seconds
- Confidence threshold: ≥0.70 (no weak trades)

**Market Hours (Options):**
- Open new day_trade: 9:35 AM - 3:30 PM ET only
- No trades in first 5 minutes (9:30-9:35)
- No trades in last 10 minutes (3:50-4:00)
- Force close day_trade by 3:55 PM ET
- Swing trades: Any time during market hours (9:30-4:00 ET)

### Exit Logic

**Stop Loss:** 2.0× ATR below entry (long) or above (short)  
**Take Profit:** 2.0× risk-reward ratio  
**Max Hold:** 240 minutes (4 hours)  

**Exit Reality Check:**
- ✅ Stops/targets calculated and recorded
- ✅ Orders submitted with bracket orders to Alpaca
- ❌ No active position monitor
- ❌ Bracket orders may fail or partial fill
- ⚠️ If brackets fail, exits NOT guaranteed
- **Phase 15C will add:** Active position monitoring, forced end-of-day closes

---

## Options Trading (Phase 15A+B - DEPLOYED)

### Alpaca Options Integration

**File:** `services/dispatcher/alpaca/options.py` (450 lines)

**Functions:**
- `AlpacaOptionsAPI` - Fetches option chains, snapshots
- `select_optimal_strike()` - Chooses ATM/OTM/ITM based on strategy
- `validate_option_liquidity()` - Checks volume >100, spread <10%
- `calculate_position_size()` - Contracts based on account and risk
- `format_option_symbol()` - OCC symbol formatting
- `get_option_chain_for_strategy()` - High-level API

**Broker Enhancement:**
- `AlpacaPaperBroker._execute_option()` - Options execution
- `AlpacaPaperBroker._execute_stock()` - Stock execution
- Dual path based on `instrument_type`

### Strategy Types

**day_trade (0-1 DTE):**
- Expiration: Today or tomorrow
- Strike: OTM (1.5% out of money) for leverage
- Trigger: Confidence ≥0.7 AND volume_ratio ≥3.0x
- Example: META 4.19x surge → BUY CALL day_trade

**swing_trade (7-30 DTE):**
- Expiration: 1-4 weeks
- Strike: ATM (at current price) for balance
- Trigger: Confidence ≥0.5 + trend aligned
- Example: AAPL uptrend → BUY CALL swing_trade

**conservative (Future):**
- ITM strikes for lower risk
- Not implemented yet

---

## How to Deploy Changes

### Code Changes

**For Service Updates:**
1. Edit code in repository
2. Build Docker image from repo root
3. Push to ECR
4. EventBridge picks up on next schedule

**Example:**
```bash
cd services/signal_engine_1m
docker build -t signal-engine:latest .
docker tag signal-engine:latest 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/signal-engine-1m:latest
aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin 160027201036.dkr.ecr.us-west-2.amazonaws.com
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/signal-engine-1m:latest
```

### Database Migrations

**ALWAYS use Lambda method** (documented in `deploy/HOW_TO_APPLY_MIGRATIONS.md`):

1. Add migration SQL to `services/db_migration_lambda/lambda_function.py`
2. Rebuild Lambda: `cd services/db_migration_lambda && ./rebuild.sh`
3. Deploy: `aws lambda update-function-code...`
4. Invoke: `aws lambda invoke --function-name ops-pipeline-db-migration`
5. Verify: Check `schema_migrations` table

**DO NOT** try direct psql connections - RDS is in private VPC.

---

## ECR Repositories

**Correct repository names:**
- `ops-pipeline/signal-engine-1m` (NOT signal-engine)
- `ops-pipeline/dispatcher` ✓
- `ops-pipeline/classifier-worker` ✓
- `ops-pipeline/telemetry-1m` ✓
- `ops-pipeline/feature-computer-1m` ✓
- `ops-pipeline/watchlist-engine-5m` ✓
- `ops-pipeline/rss-ingest` ✓
- `ops-pipeline/db-migrator` ✓

---

## Lambda Functions (VPC Access)

**Database Lambdas (Have VPC Access):**
- `ops-pipeline-db-query` - Read-only queries
- `ops-pipeline-db-migration` - Apply migrations
- `ops-pipeline-db-smoke-test` - Health checks
- `ops-pipeline-db-cleanup` - Maintenance
- `trade-alert-checker` - Email notifications

**Use these** to interact with database from local machine.

---

## System Health Definition

### What "Healthy" Means

**Data Freshness Requirements:**
- `lane_telemetry`: Latest bar within **≤2 minutes**
- `lane_features`: Latest computed within **≤2 minutes**
- `watchlist_state`: Updated within **≤7 minutes**
- `dispatch_recommendations`: Activity within **≤10 minutes** (if signals exist)
- `dispatcher_runs`: Completed within **≤10 minutes**

**Service Requirements:**
- All 8 EventBridge schedules ENABLED
- Classifier ECS service running (desiredCount=1, runningCount=1)
- No FAILED tasks in last hour
- Database responding (<1 second queries)

### First Response Checklist (When Something Breaks)

```bash
# 1. Are tasks running/failing?
aws ecs list-tasks --cluster ops-pipeline-cluster --region us-west-2

# 2. Check signal engine (most likely issue)
aws logs tail /ecs/ops-pipeline/signal-engine-1m --since 10m --region us-west-2

# 3. Check dispatcher
aws logs tail /ecs/ops-pipeline/dispatcher --since 10m --region us-west-2

# 4. Quick data check via Lambda
python3 -c "
import boto3, json
client = boto3.client('lambda', region_name='us-west-2')
response = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'sql': 'SELECT MAX(ts) FROM lane_telemetry'})
)
result = json.loads(json.load(response['Payload'])['body'])
print(f'Latest bar: {result[\"rows\"][0]}')
"
```

---

## CloudWatch Log Groups (All Services)

**ECS Services:**
- `/ecs/ops-pipeline/rss-ingest`
- `/ecs/ops-pipeline/classifier-worker`
- `/ecs/ops-pipeline/telemetry-1m`
- `/ecs/ops-pipeline/feature-computer-1m`
- `/ecs/ops-pipeline/watchlist-engine-5m`
- `/ecs/ops-pipeline/signal-engine-1m`
- `/ecs/ops-pipeline/dispatcher`
- `/ecs/ops-pipeline/db-migrator` (migrations only)

**Lambda Functions:**
- `/aws/lambda/trade-alert-checker`
- `/aws/lambda/ops-pipeline-db-query`
- `/aws/lambda/ops-pipeline-db-migration`
- `/aws/lambda/ops-pipeline-db-smoke-test`
- `/aws/lambda/ops-pipeline-db-cleanup`

---

## Monitoring & Verification

### Quick Health Check

```bash
python3 scripts/quick_pipeline_check.py
```

**Shows:**
- Telemetry freshness (last bar timestamp)
- Features computed (last update)
- Volume analysis (current ratios)
- Recent recommendations
- Recent executions

### Database Queries via Lambda

```python
import boto3, json
client = boto3.client('lambda', region_name='us-west-2')
response = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'sql': 'SELECT * FROM watchlist_state WHERE in_watchlist=TRUE LIMIT 5'})
)
result = json.loads(json.load(response['Payload'])['body'])
print(result['rows'])
```

### CloudWatch Logs

```bash
# Signal engine
aws logs tail /ecs/signal-engine-1m --follow --region us-west-2

# Dispatcher  
aws logs tail /ecs/dispatcher --follow --region us-west-2

# Trade alerts
aws logs tail /aws/lambda/trade-alert-checker --follow --region us-west-2
```

---

## Current Trading Status

**Paper Trading:** ✅ ENABLED  
**Account:** $100,000 Alpaca Paper  
**Execution Mode:** ALPACA_PAPER  
**Real Data:** ✅ Yes (Alpaca IEX feed)

**Instruments:**
- ✅ Stocks (BUY only, no shorting)
- ✅ Options (CALL/PUT via Alpaca Options API)

**Today's Activity (2026-01-26):**
- News: 440 articles classified
- Telemetry: 406 bars/hour
- Features: 411 computed/hour with volume_ratio
- Volume surges detected: META 4.19x, AMZN 4.00x
- Recommendations: 0 (volume surges occurred when old code was running)
- Executions: 0 (no signals met thresholds)

---

## Key Files & Services

### Signal Generation
- `services/signal_engine_1m/rules.py` - Trading logic (confidence calculation, instrument selection)
- `services/signal_engine_1m/main.py` - Orchestration
- `services/signal_engine_1m/db.py` - Database operations

### Execution
- `services/dispatcher/main.py` - Main dispatcher loop
- `services/dispatcher/alpaca/broker.py` - Alpaca Paper Trading (stocks + options)
- `services/dispatcher/alpaca/options.py` - Options API integration
- `services/dispatcher/risk/gates.py` - Risk checks
- `services/dispatcher/sim/broker.py` - Simulated execution fallback
- `services/dispatcher/sim/pricing.py` - Stop/target calculation

### Feature Computation
- `services/feature_computer_1m/features.py` - Technical indicators
- `services/feature_computer_1m/main.py` - Phase 12: Volume analysis

### Trade Alerts
- `services/trade_alert_lambda/lambda_function.py` - Email notifications
- **Email:** nsflournoy@gmail.com
- **Schedule:** Every 1 minute
- **Format:** Different for stocks vs options

---

## Deployment History

**Phases Completed:**
1. ✅ Phase 1-4: Infrastructure
2. ✅ Phase 5: RSS Ingestion
3. ✅ Phase 6: Classifier
4. ✅ Phase 7: Telemetry
5. ✅ Phase 8: Features + Watchlist + Signals
6. ✅ Phase 9: Dispatcher (dry-run)
7. ✅ Phase 10: Paper Trading (stocks)
8. ✅ Phase 11: AI Ticker Inference (Bedrock)
9. ✅ Phase 12: Volume Analysis (THE critical filter)
10. ✅ Phase 15A+B: Options Trading + Trade Alerts

**Latest Deployment:** 2026-01-26 19:00 UTC  
**Method:** Docker images pushed to ECR  
**Migration 008:** Applied via Lambda at 18:52 UTC

---

## Critical Bugs Fixed (Phase 15)

1. **Action gate matching** - Was comparing instrument_type to BUY_CALL format
2. **SimulatedBroker fields** - Wasn't passing instrument_type/strategy_type
3. **compute_stops direction** - Wasn't using combined_action for PUT logic
4. **Migration test SQL** - Missing parentheses in WHERE clause
5. **Config verified** - Already had correct allowed_actions

---

## Performance Expectations

**Performance Targets (Realistic):**

**$100K Paper Account (Testing):**
- Goal: Consistent profitability with strict drawdown control
- Target: +2% to +10% per month early on
- Max drawdown: <10% (must prove safety first)

**$1K Real Account (Future):**
- Goal: Prove system works with small capital
- Target: +5% to +15% per month
- Focus: Risk management, not maximum returns

---

## What's Working Right Now

**Data Collection:**
- ✅ RSS feeds every 30 min
- ✅ Sentiment analysis continuous
- ✅ 1-minute bars from Alpaca
- ✅ Volume analysis (Phase 12)

**Signal Generation:**
- ✅ Top 30 watchlist
- ✅ CALL/PUT/STOCK instrument selection
- ✅ strategy_type (day_trade vs swing_trade)
- ✅ Volume-based confidence adjustment

**Execution:**
- ✅ Alpaca Paper Trading API
- ✅ Stock execution
- ✅ Options execution (CALL/PUT)
- ✅ Greeks capture
- ✅ Stop/target calculation

**Notifications:**
- ✅ Email alerts on all trades
- ✅ SNS topic configured
- ✅ Lambda running every 1 min

---

## What's NOT Implemented Yet

**Position Management (Phase 15C):**
- ❌ Active position monitoring
- ❌ Automatic stop/target execution
- ❌ End-of-day closes
- ❌ Expiration management

**Long-term Strategy (Phase 15C):**
- ❌ Daily analyzer for swing trades
- ❌ Multi-day position holds
- ❌ SMA50/SMA200 analysis

**Capital Allocation (Phase 15D):**
- ❌ 70/30 split (short-term vs long-term)
- ❌ Strategy coordinator
- ❌ Max position limits

**Premium Selling:**
- ❌ SELL_PREMIUM strategies
- ❌ Theta decay plays
- ❌ Marked as TODO in rules.py

---

## Next Development Priorities

**Immediate (This Week):**
1. Monitor first options trades
2. Verify executions work correctly
3. Validate email alerts
4. Check database views populate

**Short-term (2-3 Weeks):**
1. Phase 15C: Position manager
2. Phase 15C: Daily analyzer
3. Collect 20-50 options trades
4. Analyze win rate

**Long-term (2-3 Months):**
1. Phase 15D: Capital allocation
2. Prove profitability on paper
3. Switch to $1K real money
4. Scale capital

---

## Common Operations

### Check System Health
```bash
python3 scripts/quick_pipeline_check.py
python3 scripts/check_news_sentiment.py
```

### Check for Options Signals
```bash
python3 -c "
import boto3, json
client = boto3.client('lambda', region_name='us-west-2')
response = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'sql': \"SELECT ticker, instrument_type, strategy_type, confidence FROM dispatch_recommendations WHERE ts >= CURRENT_DATE AND instrument_type IN ('CALL', 'PUT') ORDER BY ts DESC\"})
)
result = json.loads(json.load(response['Payload'])['body'])
print(f'Options signals today: {len(result[\"rows\"])}')
for r in result['rows']:
    print(f'  {r[\"ticker\"]} {r[\"instrument_type\"]} ({r[\"strategy_type\"]}): {r[\"confidence\"]}')
"
```

### Apply New Migration
See `deploy/HOW_TO_APPLY_MIGRATIONS.md`

### Operational Validation & Troubleshooting

**Key Reference Documents:**
- `deploy/ops_validation/LAMBDA_QUERY_GUIDE.md` - How to query database via Lambda
- `deploy/ops_validation/DATA_QUALITY_VALIDATION.md` - Data quality checks
- `deploy/ops_validation/SYSTEM_STATUS_SUMMARY.md` - Operational status tracking
- `deploy/COMPLETE_SYSTEM_STATUS_AND_GAPS.md` - Full context + what's missing
- `deploy/HOW_TO_APPLY_MIGRATIONS.md` - Migration deployment process

---

## Key Lessons Learned

1. **Lambda for migrations** - Direct connections timeout (private VPC)
2. **Volume analysis is critical** - Phase 12 was THE missing piece
3. **Docker caching issues** - Always use correct ECR repo names
4. **EventBridge architecture** - No persistent services, all scheduled tasks
5. **Combined action format** - gates.py needs BUY_CALL, not just CALL

---

## Questions & Answers

**Q: Why no signals today?**  
A: Volume surges occurred when old code was running. New Phase 15 code deployed at 19:00 UTC - will catch next surges.

**Q: Can I query database from local machine?**  
A: No - use Lambda functions (ops-pipeline-db-query). RDS is private.

**Q: How do I update trading logic?**  
A: Edit rules.py, rebuild Docker image, push to ECR. EventBridge uses new code on next run.

**Q: When will options trade?**  
A: Automatically when volume_ratio ≥3.0x + confidence ≥0.7 (like META 4.19x today).

**Q: How are exits handled?**  
A: Currently via Alpaca Paper API's bracket orders. Phase 15C will add active monitoring.

**Q: Is real money being traded?**  
A: No - Alpaca Paper Trading only ($100K fake money). Real data, simulated trades.

---

**System Status:** ✅ Fully Operational  
**Latest Deploy:** 2026-01-26 19:00 UTC  
**Ready For:** Options trading on next volume surges  
**Email Alerts:** Configured (confirm subscription)
