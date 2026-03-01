# Database Query Reference
**Last Updated:** February 11, 2026  
**Access Method:** Lambda `ops-pipeline-db-query` (read-only) or `db-migrator` ECS task (DDL/DML)

---

## How to Query

### Via AWS CLI (recommended)

```bash
aws lambda invoke --function-name ops-pipeline-db-query --region us-west-2 \
  --payload '{"sql": "SELECT * FROM active_positions WHERE status = '\''open'\'' LIMIT 5"}' \
  /tmp/result.json && python3 -c "
import json
d = json.load(open('/tmp/result.json'))
rows = json.loads(d['body'])['rows']
for r in rows: print(r)
"
```

### Via Python

```python
import boto3, json

def query(sql):
    client = boto3.client('lambda', region_name='us-west-2')
    resp = client.invoke(
        FunctionName='ops-pipeline-db-query',
        Payload=json.dumps({'sql': sql})
    )
    body = json.loads(resp['Payload'].read())
    return json.loads(body['body'])['rows']

rows = query("SELECT ticker, current_price, current_pnl_percent FROM active_positions WHERE status = 'open'")
for r in rows:
    print(f"{r['ticker']}: ${float(r['current_price']):.2f} ({float(r['current_pnl_percent']):+.1f}%)")
```

### ❌ What Does NOT Work

- Direct `psycopg2` connection (RDS is in private VPC)
- RDS Query Editor (not available for non-Aurora)
- Any local database tool

### For Write Operations (DDL/DML)

Use the `db-migrator` ECS task. See `OPERATIONS_GUIDE.md` → "Deploying Database Changes".

---

## Tables

### active_positions
**Purpose:** Current and recently closed positions. Updated every minute by position manager.  
**Rows:** ~11,594 (includes closed)

| Column | Type | Description |
|--------|------|-------------|
| id | integer PK | Auto-increment position ID |
| ticker | varchar | Stock ticker (e.g., NVDA) |
| instrument_type | varchar | STOCK, CALL, or PUT |
| option_symbol | text | Full OCC symbol (e.g., NVDA260227P00187500) |
| strategy_type | varchar | swing_trade or day_trade |
| side | varchar | buy or sell |
| quantity | numeric | Number of contracts or shares |
| entry_price | numeric | Price at entry |
| current_price | numeric | Latest price (from Market Data API quotes) |
| current_pnl_dollars | numeric | Unrealized P&L in dollars |
| current_pnl_percent | numeric | Unrealized P&L as percentage |
| stop_loss | numeric | Stop loss price |
| take_profit | numeric | Take profit price |
| peak_price | numeric | Highest price reached (for trailing stops) |
| trailing_stop_price | numeric | Current trailing stop level |
| status | varchar | open, closed, closing |
| close_reason | varchar | option_profit_target, stop_loss, trailing_stop, etc. |
| account_name | varchar | large-100k, tiny-1k |
| last_checked_at | timestamp | Last time position manager checked this |
| entry_time | timestamp | When position was opened |
| closed_at | timestamp | When position was closed |
| strike_price | numeric | Option strike price |
| expiration_date | date | Option expiration |
| entry_features_json | jsonb | Market features at entry time |

**Common Queries:**

```sql
-- Open positions with P&L
SELECT id, ticker, instrument_type, option_symbol, entry_price, current_price,
       current_pnl_percent, account_name, entry_time
FROM active_positions WHERE status = 'open' ORDER BY id;

-- Positions for a specific account
SELECT * FROM active_positions WHERE status = 'open' AND account_name = 'large-100k';

-- Recently closed positions
SELECT id, ticker, close_reason, entry_price, current_price, current_pnl_percent, closed_at
FROM active_positions WHERE status = 'closed'
ORDER BY closed_at DESC LIMIT 10;

-- Positions approaching take-profit
SELECT id, ticker, current_pnl_percent, take_profit, current_price
FROM active_positions WHERE status = 'open' AND current_pnl_percent > 50
ORDER BY current_pnl_percent DESC;

-- Positions in the red
SELECT id, ticker, current_pnl_percent, stop_loss, current_price
FROM active_positions WHERE status = 'open' AND current_pnl_percent < 0
ORDER BY current_pnl_percent ASC;
```

---

### dispatch_recommendations
**Purpose:** Signal engine output. Every BUY/SELL/HOLD recommendation.  
**Rows:** ~18,539

| Column | Type | Description |
|--------|------|-------------|
| id | bigint PK | Auto-increment recommendation ID |
| ts | timestamptz | When signal was generated |
| ticker | text | Stock ticker |
| action | text | BUY, SELL, or HOLD |
| instrument_type | text | CALL, PUT, or STOCK |
| confidence | float | Signal confidence (0.0 - 1.0) |
| reason | jsonb | Why this signal was generated |
| status | text | pending, claimed, executed, skipped |
| strategy_type | text | swing_trade, day_trade |
| features_snapshot | jsonb | Market features at signal time |

**Common Queries:**

```sql
-- Recent BUY signals
SELECT id, ts, ticker, action, instrument_type, confidence, strategy_type
FROM dispatch_recommendations
WHERE action = 'BUY' AND ts >= NOW() - INTERVAL '30 minutes'
ORDER BY ts DESC;

-- Signal distribution today
SELECT action, instrument_type, COUNT(*), AVG(confidence)::numeric(4,2) as avg_conf
FROM dispatch_recommendations
WHERE ts::date = CURRENT_DATE
GROUP BY action, instrument_type ORDER BY count DESC;

-- High confidence signals
SELECT id, ts, ticker, action, instrument_type, confidence
FROM dispatch_recommendations
WHERE confidence > 0.7 AND ts >= NOW() - INTERVAL '1 hour'
ORDER BY confidence DESC;

-- Signals per ticker today
SELECT ticker, COUNT(*) as signals,
       SUM(CASE WHEN action = 'BUY' THEN 1 ELSE 0 END) as buys,
       SUM(CASE WHEN action = 'HOLD' THEN 1 ELSE 0 END) as holds
FROM dispatch_recommendations WHERE ts::date = CURRENT_DATE
GROUP BY ticker ORDER BY signals DESC;
```

---

### dispatch_executions
**Purpose:** Every trade the dispatchers attempted (both ALPACA_PAPER and SIMULATED_FALLBACK).  
**Rows:** ~485  
**Unique Index:** `(recommendation_id, account_name)` — allows both dispatchers to process same signal.

| Column | Type | Description |
|--------|------|-------------|
| execution_id | uuid PK | Unique execution ID |
| recommendation_id | bigint | FK to dispatch_recommendations.id |
| ticker | text | Stock ticker |
| action | text | BUY or SELL |
| instrument_type | text | CALL, PUT, or STOCK |
| execution_mode | text | ALPACA_PAPER or SIMULATED_FALLBACK |
| account_name | varchar | large-100k, tiny-1k |
| entry_price | numeric | Fill price |
| qty | numeric | Quantity (contracts or shares) |
| notional | numeric | Total dollar value |
| stop_loss_price | numeric | Stop loss set |
| take_profit_price | numeric | Take profit set |
| option_symbol | text | Full OCC symbol |
| strike_price | numeric | Option strike |
| expiration_date | date | Option expiry |
| simulated_ts | timestamptz | When execution happened |
| explain_json | jsonb | Gate evaluation details |
| risk_json | jsonb | Risk assessment |

**Common Queries:**

```sql
-- Today's executions
SELECT ticker, action, instrument_type, execution_mode, account_name,
       entry_price, qty, notional, simulated_ts
FROM dispatch_executions WHERE simulated_ts::date = CURRENT_DATE
ORDER BY simulated_ts DESC;

-- Real paper trades only (not simulated)
SELECT * FROM dispatch_executions
WHERE execution_mode = 'ALPACA_PAPER' AND simulated_ts::date = CURRENT_DATE
ORDER BY simulated_ts DESC;

-- Executions per account
SELECT account_name, execution_mode, COUNT(*) as trades, SUM(notional)::numeric(10,2) as total_notional
FROM dispatch_executions WHERE simulated_ts::date = CURRENT_DATE
GROUP BY account_name, execution_mode;

-- Last 10 executions
SELECT ticker, action, instrument_type, execution_mode, account_name, notional, simulated_ts
FROM dispatch_executions ORDER BY simulated_ts DESC LIMIT 10;
```

---

### lane_telemetry
**Purpose:** 1-minute OHLCV bars from Alpaca. Updated by telemetry service.  
**Rows:** ~151,813

| Column | Type | Description |
|--------|------|-------------|
| ticker | text | Stock ticker |
| ts | timestamptz | Bar timestamp |
| open | float | Open price |
| high | float | High price |
| low | float | Low price |
| close | float | Close price |
| volume | bigint | Volume |

**Common Queries:**

```sql
-- Latest bar per ticker
SELECT DISTINCT ON (ticker) ticker, ts, close, volume
FROM lane_telemetry ORDER BY ticker, ts DESC;

-- Check data freshness (how old is the latest bar?)
SELECT ticker, MAX(ts) as latest_bar,
       EXTRACT(EPOCH FROM NOW() - MAX(ts))::int as age_seconds
FROM lane_telemetry GROUP BY ticker
ORDER BY age_seconds DESC;

-- Recent bars for a ticker
SELECT ts, open, high, low, close, volume
FROM lane_telemetry WHERE ticker = 'NVDA'
ORDER BY ts DESC LIMIT 20;

-- Tickers with stale data (>3 min old)
SELECT ticker, MAX(ts) as latest,
       EXTRACT(EPOCH FROM NOW() - MAX(ts))::int as age_sec
FROM lane_telemetry GROUP BY ticker
HAVING EXTRACT(EPOCH FROM NOW() - MAX(ts)) > 180
ORDER BY age_sec DESC;
```

---

### lane_features
**Purpose:** Computed technical indicators. Updated by feature-computer-1m.  
**Rows:** ~64,682

| Column | Type | Description |
|--------|------|-------------|
| ticker | text | Stock ticker |
| ts | timestamptz | Feature timestamp |
| sma20 | float | 20-period simple moving average |
| sma50 | float | 50-period simple moving average |
| trend_state | integer | +1 (uptrend), 0 (neutral), -1 (downtrend) |
| vol_ratio | float | Current volume / baseline volume |
| volume_surge | boolean | True if volume > 2x average |
| close | float | Close price at computation time |
| computed_at | timestamptz | When features were computed |

**Common Queries:**

```sql
-- Latest features per ticker
SELECT DISTINCT ON (ticker) ticker, close, sma20, sma50, trend_state, vol_ratio, volume_surge, computed_at
FROM lane_features ORDER BY ticker, computed_at DESC;

-- Tickers in uptrend with volume surge
SELECT DISTINCT ON (ticker) ticker, close, sma20, trend_state, vol_ratio
FROM lane_features
WHERE trend_state = 1 AND volume_surge = true
ORDER BY ticker, computed_at DESC;

-- Feature freshness
SELECT ticker, MAX(computed_at) as latest,
       EXTRACT(EPOCH FROM NOW() - MAX(computed_at))::int as age_sec
FROM lane_features GROUP BY ticker ORDER BY age_sec DESC;
```

**View: `lane_features_clean`** — Same data but filtered to only the latest row per ticker.

---

### position_history
**Purpose:** Closed trades with full P&L. Used for learning.  
**Rows:** ~31

| Column | Type | Description |
|--------|------|-------------|
| id | bigint PK | Auto-increment |
| ticker | text | Stock ticker |
| instrument_type | text | CALL, PUT, STOCK |
| entry_price | numeric | Entry price |
| exit_price | numeric | Exit price |
| pnl_dollars | numeric | Realized P&L in dollars |
| pnl_pct | numeric | Realized P&L percentage |
| exit_reason | text | Why position was closed |
| entry_time | timestamptz | When opened |
| exit_time | timestamptz | When closed |
| holding_seconds | integer | How long held |
| best_unrealized_pnl_pct | numeric | Peak unrealized gain (MFE) |
| worst_unrealized_pnl_pct | numeric | Worst unrealized loss (MAE) |
| entry_features_json | jsonb | Market features at entry |

**Common Queries:**

```sql
-- All closed trades with P&L
SELECT ticker, instrument_type, entry_price, exit_price,
       pnl_dollars, pnl_pct, exit_reason, holding_seconds/60 as hold_min
FROM position_history ORDER BY exit_time DESC;

-- Win/loss summary
SELECT
  COUNT(*) as total,
  SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END) as wins,
  SUM(CASE WHEN pnl_pct <= 0 THEN 1 ELSE 0 END) as losses,
  AVG(pnl_pct)::numeric(6,2) as avg_pnl_pct,
  SUM(pnl_dollars)::numeric(10,2) as total_pnl
FROM position_history;

-- Best and worst trades
SELECT ticker, instrument_type, pnl_pct, pnl_dollars, exit_reason
FROM position_history ORDER BY pnl_pct DESC LIMIT 5;

-- Exit reason breakdown
SELECT exit_reason, COUNT(*), AVG(pnl_pct)::numeric(6,2) as avg_pnl
FROM position_history GROUP BY exit_reason ORDER BY count DESC;
```

---

### learning_recommendations
**Purpose:** Statistical findings from trade analysis. Written by trade-analyzer, reviewed by humans.  
**Rows:** ~6 (growing with each analyzer run)

| Column | Type | Description |
|--------|------|-------------|
| id | serial | Primary key |
| parameter_name | varchar | What to change (e.g., `min_confidence_threshold`) |
| parameter_path | varchar | Where in code/config (e.g., `dispatcher.risk.gates.confidence`) |
| current_value | numeric | Current parameter value |
| suggested_value | numeric | Recommended new value |
| rollback_value | numeric | Value to revert to if change fails |
| sample_size | int | Number of trades analyzed |
| confidence | numeric | Statistical confidence (0-1, higher = more data) |
| avg_return_if_changed | numeric | Expected improvement in avg return % |
| backtest_sharpe | numeric | Sharpe ratio from backtest (if available) |
| recommendation_reason | text | Human-readable explanation |
| status | varchar | `pending` → `approved` / `rejected` / `applied` |
| reviewed_by | varchar | Who reviewed |
| reviewed_at | timestamp | When reviewed |
| generated_at | timestamp | When the analyzer created this |

**Common Queries:**
```sql
-- View all pending recommendations
SELECT parameter_name, current_value, suggested_value,
       sample_size, confidence, avg_return_if_changed,
       recommendation_reason
FROM learning_recommendations WHERE status = 'pending'
ORDER BY confidence DESC;

-- Approve a recommendation
UPDATE learning_recommendations SET status = 'approved',
  reviewed_by = 'your_name', reviewed_at = NOW()
WHERE id = <ID>;

-- View history of all recommendations
SELECT parameter_name, status, generated_at, reviewed_at
FROM learning_recommendations ORDER BY generated_at DESC;
```

---

### watchlist_state
**Purpose:** Scored and ranked tickers. Updated by watchlist-engine-5m.  
**Rows:** ~54

| Column | Type | Description |
|--------|------|-------------|
| ticker | text PK | Stock ticker |
| watch_score | float | Overall opportunity score |
| rank | integer | Rank (1 = best) |
| in_watchlist | boolean | True if in active watchlist (top 30) |
| trend_alignment | integer | +1, 0, -1 |
| setup_quality | float | Quality of current setup |
| vol_score | float | Volume score |
| sentiment_pressure | float | News sentiment score |
| reasons | jsonb | Why this score |

**Common Queries:**

```sql
-- Current watchlist (what signal engine uses)
SELECT ticker, watch_score, rank, trend_alignment, setup_quality
FROM watchlist_state WHERE in_watchlist = TRUE ORDER BY rank;

-- Top opportunities
SELECT ticker, watch_score, setup_quality, vol_score, sentiment_pressure
FROM watchlist_state ORDER BY watch_score DESC LIMIT 10;
```

---

### schema_migrations
**Purpose:** Tracks which DB migrations have been applied.  
**Rows:** 35

```sql
-- Check applied migrations
SELECT version, applied_at FROM schema_migrations ORDER BY version DESC LIMIT 10;

-- Check if specific migration was applied
SELECT * FROM schema_migrations WHERE version = '1035';
```

---

## Useful Views

| View | Description |
|------|-------------|
| `lane_features_clean` | Latest features per ticker (deduplicated) |
| `v_open_positions_summary` | Summary of open positions |
| `v_position_performance` | Position performance metrics |
| `v_position_health_check` | Positions that may need attention |
| `active_options_positions` | Open options positions only |
| `daily_options_summary` | Daily options trading summary |
| `v_daily_missed_summary` | Missed opportunities summary |

```sql
-- Quick position health check
SELECT * FROM v_position_health_check;

-- Open positions summary
SELECT * FROM v_open_positions_summary;

-- Performance overview
SELECT * FROM v_position_performance;
```

---

## Quick Health Check Queries

```sql
-- 1. System heartbeat (are services writing data?)
SELECT 'telemetry' as service, MAX(ts) as last_write, EXTRACT(EPOCH FROM NOW()-MAX(ts))::int as age_sec FROM lane_telemetry
UNION ALL
SELECT 'features', MAX(computed_at), EXTRACT(EPOCH FROM NOW()-MAX(computed_at))::int FROM lane_features
UNION ALL
SELECT 'signals', MAX(ts), EXTRACT(EPOCH FROM NOW()-MAX(ts))::int FROM dispatch_recommendations
UNION ALL
SELECT 'executions', MAX(simulated_ts), EXTRACT(EPOCH FROM NOW()-MAX(simulated_ts))::int FROM dispatch_executions
UNION ALL
SELECT 'pos_manager', MAX(last_checked_at), EXTRACT(EPOCH FROM NOW()-MAX(last_checked_at))::int FROM active_positions WHERE status='open'
ORDER BY 1;

-- 2. Open positions count per account
SELECT account_name, COUNT(*) FROM active_positions WHERE status = 'open' GROUP BY account_name;

-- 3. Today's trade count
SELECT account_name, execution_mode, COUNT(*) FROM dispatch_executions
WHERE simulated_ts::date = CURRENT_DATE GROUP BY account_name, execution_mode;

-- 4. Signal engine activity (last hour)
SELECT action, COUNT(*), AVG(confidence)::numeric(4,2)
FROM dispatch_recommendations WHERE ts >= NOW() - INTERVAL '1 hour'
GROUP BY action;

-- 5. Ticker coverage check (telemetry vs watchlist)
SELECT w.ticker, MAX(t.ts) as last_bar,
       CASE WHEN MAX(t.ts) IS NULL THEN 'NO DATA' ELSE 'OK' END as status
FROM watchlist_state w
LEFT JOIN lane_telemetry t ON w.ticker = t.ticker AND t.ts >= NOW() - INTERVAL '5 minutes'
WHERE w.in_watchlist = TRUE
GROUP BY w.ticker ORDER BY status DESC, w.ticker;
```
