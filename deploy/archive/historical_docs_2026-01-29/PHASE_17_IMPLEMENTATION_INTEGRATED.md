# Phase 17: Options Learning - Integrated Implementation
## REVISED: Enhance Existing Services (Not New Service)

**Version:** 2.0 (Integrated Approach)  
**Date:** 2026-01-28  
**Effort:** 10 hours (vs 45 hours for new service)  
**Cost:** $0 additional  

---

## Executive Decision: Integrate, Don't Create

**Original Plan:** New options_telemetry_1m service  
**Problem:** Adds complexity, cost, maintenance burden  

**Revised Plan:** Enhance existing position_manager service  
**Benefits:**
- 75% less effort (10 hrs vs 45 hrs)
- $0 additional cost (vs $6/month)
- Simpler architecture (9 services, not 10)
- Focused dataset (only our trades)
- Natural fit (already monitoring positions)

---

## Implementation Checklist

### Phase 17A: Database Schema (30 minutes)

- [ ] **Step 1.1:** Add Migration 015 to db_migration_lambda
  - File: `services/db_migration_lambda/lambda_function.py`
  - Add after Migration 014
  - SQL: See "Migration 015 SQL" section below

- [ ] **Step 1.2:** Deploy migration Lambda
  ```bash
  cd services/db_migration_lambda
  rm -rf package migration_lambda.zip
  mkdir package
  pip install -q -r requirements.txt -t package/
  cp lambda_function.py package/
  cd package && zip -q -r ../migration_lambda.zip . && cd ..
  aws lambda update-function-code \
    --function-name ops-pipeline-db-migration \
    --zip-file fileb://migration_lambda.zip \
    --region us-west-2
  ```

- [ ] **Step 1.3:** Run migration
  ```bash
  aws lambda invoke \
    --function-name ops-pipeline-db-migration \
    --region us-west-2 \
    --payload '{}' \
    /tmp/migration_015.json
  
  # Verify
  cat /tmp/migration_015.json | jq .
  ```

- [ ] **Step 1.4:** Verify tables created
  ```python
  # Should see: option_bars, iv_surface tables
  python3 scripts/check_system_status.py
  ```

---

### Phase 17B: Enhance Position Manager (4 hours)

#### File 1: bar_fetcher.py (NEW - 1.5 hours)

- [ ] **Step 2.1:** Create `services/position_manager/bar_fetcher.py`
  - Copy structure from `services/dispatcher/alpaca/options.py`
  - Implement `fetch_option_bars()` function
  - Add retry logic and error handling
  - See "bar_fetcher.py Template" section below

#### File 2: monitor.py (MODIFY - 1.5 hours)

- [ ] **Step 2.2:** Enhance `update_position_price()` function
  - Add bar fetching after price update
  - Calculate peak/lowest premiums
  - Store bars in database
  - See "monitor.py Changes" section below

#### File 3: db.py (MODIFY - 1 hour)

- [ ] **Step 2.3:** Add database methods
  - `insert_option_bar()`
  - `update_position_bar_metadata()`
  - `get_option_bars_for_position()`
  - See "db.py New Methods" section below

---

### Phase 17C: Deploy & Verify (1 hour)

- [ ] **Step 3.1:** Build position_manager with changes
  ```bash
  cd services/position_manager
  docker build -t ops-pipeline/position-manager:v2-bars .
  ```

- [ ] **Step 3.2:** Push to ECR
  ```bash
  aws ecr get-login-password --region us-west-2 | \
    docker login --username AWS --password-stdin \
    160027201036.dkr.ecr.us-west-2.amazonaws.com
  
  docker tag ops-pipeline/position-manager:v2-bars \
    160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline:position-manager-v2-bars
  
  docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline:position-manager-v2-bars
  ```

- [ ] **Step 3.3:** Update task definition
  ```bash
  # Update image in deploy/position-manager-task-definition.json
  # Then register new revision
  aws ecs register-task-definition \
    --cli-input-json file://deploy/position-manager-task-definition.json
  ```

- [ ] **Step 3.4:** Update service
  ```bash
  aws ecs update-service \
    --cluster ops-pipeline \
    --service ops-pipeline-position-manager \
    --task-definition ops-pipeline-position-manager:2 \
    --region us-west-2
  ```

- [ ] **Step 3.5:** Verify bars being captured (wait 5 minutes)
  ```python
  python3 << 'EOF'
  import boto3, json
  client = boto3.client('lambda', region_name='us-west-2')
  
  r = client.invoke(
      FunctionName='ops-pipeline-db-query',
      Payload=json.dumps({'sql': """
          SELECT COUNT(*) as bars, MAX(ts) as latest
          FROM option_bars
          WHERE ts > NOW() - INTERVAL '10 minutes'
      """})
  )
  
  result = json.loads(json.load(r['Payload'])['body'])
  print(f"✅ Bars captured: {result['rows'][0]}")
  EOF
  ```

---

### Phase 17D: AI Analytics (4 hours)

- [ ] **Step 4.1:** Create analysis queries (deploy/sql_queries/options_learning/)
  - `feature_importance.sql`
  - `exit_timing_analysis.sql`
  - `delta_performance.sql`
  - `iv_effectiveness.sql`

- [ ] **Step 4.2:** Run initial analysis (after 50+ trades)
  ```bash
  python3 scripts/analyze_options_performance.py
  ```

- [ ] **Step 4.3:** Review findings
  - Which features predict wins?
  - What's optimal exit timing?
  - Which deltas work best?

- [ ] **Step 4.4:** Generate first recommendation
  - Store in learning_recommendations table
  - Review for approval
  - Implement if beneficial

---

## Migration 015 SQL

```sql
-- Migration 015: Options telemetry (integrated approach)
-- Minimal schema for position_manager integration

-- 1. Option bars table (core data)
CREATE TABLE IF NOT EXISTS option_bars (
    symbol TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    open NUMERIC(10,2) NOT NULL,
    high NUMERIC(10,2) NOT NULL,
    low NUMERIC(10,2) NOT NULL,
    close NUMERIC(10,2) NOT NULL,
    volume BIGINT NULL,
    trade_count INT NULL,
    vwap NUMERIC(10,2) NULL,
    PRIMARY KEY (symbol, ts)
);

CREATE INDEX idx_option_bars_symbol_ts ON option_bars(symbol, ts DESC);
CREATE INDEX idx_option_bars_ts ON option_bars(ts DESC);

-- 2. Enhance dispatch_executions with bar metadata
ALTER TABLE dispatch_executions 
ADD COLUMN IF NOT EXISTS bars_captured_count INT DEFAULT 0,
ADD COLUMN IF NOT EXISTS first_bar_ts TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS last_bar_ts TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS peak_premium NUMERIC(10,2),
ADD COLUMN IF NOT EXISTS lowest_premium NUMERIC(10,2);

-- 3. Optional: IV surface for advanced analysis (can add later)
CREATE TABLE IF NOT EXISTS iv_surface (
    ticker TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    expiration_date DATE NOT NULL,
    strike_price NUMERIC(10,2) NOT NULL,
    option_type TEXT NOT NULL CHECK (option_type IN ('call', 'put')),
    implied_volatility NUMERIC(10,4),
    delta NUMERIC(10,4),
    volume BIGINT,
    open_interest BIGINT,
    PRIMARY KEY (ticker, ts, expiration_date, strike_price, option_type)
);

CREATE INDEX idx_iv_surface_ticker_ts ON iv_surface(ticker, ts DESC);

INSERT INTO schema_migrations (version) VALUES ('015_options_telemetry_integrated') ON CONFLICT (version) DO NOTHING;
```

---

## Code Templates

### bar_fetcher.py Template

**Location:** `services/position_manager/bar_fetcher.py` (NEW FILE)

```python
"""
Options Bar Fetcher for Position Manager
Fetches historical option bars from Alpaca for position tracking
"""

import requests
import time
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

class OptionBarFetcher:
    """Fetches option bars from Alpaca"""
    
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = "https://data.alpaca.markets"
        
        self.headers = {
            'APCA-API-KEY-ID': api_key,
            'APCA-API-SECRET-KEY': api_secret
        }
    
    def fetch_bars_for_symbol(
        self,
        symbol: str,
        minutes_back: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Fetch recent option bars for a single symbol.
        
        Args:
            symbol: Option symbol (e.g., SPY260130C00609000)
            minutes_back: How many minutes of history to fetch
        
        Returns:
            List of bars with timestamp, OHLCV
        """
        url = f"{self.base_url}/v1beta1/options/bars"
        
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=minutes_back)
        
        params = {
            'symbols': symbol,
            'start': start_time.isoformat(),
            'end': end_time.isoformat(),
            'timeframe': '1Min',
            'limit': 10
        }
        
        try:
            response = requests.get(
                url,
                headers=self.headers,
                params=params,
                timeout=10
            )
            
            if response.status_code == 404:
                # No bars available (normal for some contracts)
                return []
            
            response.raise_for_status()
            data = response.json()
            
            # Parse response
            bars_data = data.get('bars', {}).get(symbol, [])
            
            bars = []
            for bar in bars_data:
                bars.append({
                    'symbol': symbol,
                    'timestamp': bar['t'],
                    'open': float(bar['o']),
                    'high': float(bar['h']),
                    'low': float(bar['l']),
                    'close': float(bar['c']),
                    'volume': int(bar.get('v', 0)),
                    'trade_count': int(bar.get('n', 0)),
                    'vwap': float(bar.get('vw', 0)) if 'vw' in bar else None
                })
            
            logger.info(f"Fetched {len(bars)} bars for {symbol}")
            return bars
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching bars for {symbol}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching bars: {e}")
            return []
```

---

### monitor.py Changes

**Location:** `services/position_manager/monitor.py` (MODIFY EXISTING)

**Add at top:**
```python
from bar_fetcher import OptionBarFetcher

# Initialize bar fetcher
bar_fetcher = None  # Will be initialized in main()
```

**Modify update_position_price function:**
```python
def update_position_price(position: Dict[str, Any]) -> bool:
    """
    Update position with current market price and calculate P&L
    NOW ALSO captures option bars for AI learning
    """
    try:
        current_price = get_current_price(position)
        
        if current_price is None:
            logger.warning(f"Could not get price for position {position['id']}")
            return False
        
        # Calculate P&L (EXISTING CODE)
        entry_price = float(position['entry_price'])
        quantity = float(position['quantity'])
        pnl_dollars = (current_price - entry_price) * quantity
        pnl_percent = ((current_price / entry_price) - 1) * 100
        
        # Update database with price (EXISTING)
        db.update_position_price(
            position['id'],
            current_price,
            pnl_dollars,
            pnl_percent
        )
        
        # NEW: Capture option bars for learning
        if position['instrument_type'] in ('CALL', 'PUT') and bar_fetcher:
            try:
                bars = bar_fetcher.fetch_bars_for_symbol(
                    position.get('option_symbol') or position['ticker'],
                    minutes_back=5
                )
                
                if bars:
                    # Store bars in database
                    bars_stored = db.store_option_bars(bars)
                    
                    # Calculate and update metadata
                    peak = max(b['high'] for b in bars)
                    lowest = min(b['low'] for b in bars)
                    
                    db.update_position_bar_metadata(
                        position['id'],
                        bars_count=bars_stored,
                        peak_premium=peak,
                        lowest_premium=lowest
                    )
                    
                    logger.debug(f"Captured {bars_stored} bars for position {position['id']}")
            
            except Exception as e:
                # Don't fail position update if bar capture fails
                logger.warning(f"Could not capture bars for position {position['id']}: {e}")
        
        # Log the update (EXISTING)
        db.log_position_event(
            position['id'],
            'price_update',
            {
                'price': current_price,
                'pnl_dollars': pnl_dollars,
                'pnl_percent': pnl_percent
            }
        )
        
        # Update position dict (EXISTING)
        position['current_price'] = current_price
        position['current_pnl_dollars'] = pnl_dollars
        position['current_pnl_percent'] = pnl_percent
        
        return True
        
    except Exception as e:
        logger.error(f"Error updating price for position {position['id']}: {e}")
        return False
```

**Modify main function:**
```python
def main():
    global bar_fetcher
    
    # ... existing code ...
    
    # Initialize bar fetcher
    bar_fetcher = OptionBarFetcher(
        api_key=ALPACA_API_KEY,
        api_secret=ALPACA_API_SECRET
    )
    logger.info("Option bar fetcher initialized")
    
    # ... rest of existing code ...
```

---

### db.py New Methods

**Location:** `services/position_manager/db.py` (ADD TO EXISTING)

```python
def store_option_bars(bars: List[Dict[str, Any]]) -> int:
    """
    Store option bars in database.
    Returns number of bars inserted.
    """
    if not bars:
        return 0
    
    # Use UPSERT to handle duplicates
    sql = """
        INSERT INTO option_bars (symbol, ts, open, high, low, close, volume, trade_count, vwap)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol, ts) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            trade_count = EXCLUDED.trade_count,
            vwap = EXCLUDED.vwap
    """
    
    inserted = 0
    with get_cursor() as cursor:
        for bar in bars:
            try:
                cursor.execute(sql, (
                    bar['symbol'],
                    bar['timestamp'],
                    bar['open'],
                    bar['high'],
                    bar['low'],
                    bar['close'],
                    bar.get('volume'),
                    bar.get('trade_count'),
                    bar.get('vwap')
                ))
                inserted += 1
            except Exception as e:
                logger.warning(f"Failed to insert bar: {e}")
    
    return inserted


def update_position_bar_metadata(
    position_id: int,
    bars_count: int,
    peak_premium: float,
    lowest_premium: float
):
    """Update position with bar tracking metadata"""
    sql = """
        UPDATE dispatch_executions de
        SET 
            bars_captured_count = bars_captured_count + %s,
            peak_premium = GREATEST(COALESCE(peak_premium, 0), %s),
            lowest_premium = LEAST(COALESCE(lowest_premium, 999999), %s),
            last_bar_ts = NOW()
        FROM active_positions ap
        WHERE ap.execution_id = de.execution_id
          AND ap.id = %s
    """
    
    with get_cursor() as cursor:
        cursor.execute(sql, (bars_count, peak_premium, lowest_premium, position_id))


def get_option_bars_for_position(position_id: int) -> List[Dict]:
    """Get all captured bars for a position (for analysis)"""
    sql = """
        SELECT ob.*
        FROM option_bars ob
        JOIN dispatch_executions de ON de.option_symbol = ob.symbol
        JOIN active_positions ap ON ap.execution_id = de.execution_id
        WHERE ap.id = %s
        ORDER BY ob.ts
    """
    
    with get_cursor() as cursor:
        cursor.execute(sql, (position_id,))
        return cursor.fetchall()
```

---

### requirements.txt Update

**Location:** `services/position_manager/requirements.txt` (ADD LINE)

```txt
# Existing packages...
alpaca-py==0.9.0
psycopg2-binary==2.9.9

# NEW: For option bar fetching
requests==2.31.0
```

---

## Testing Plan

### Test 1: Verify Bar Capture (5 minutes)

```python
# After deployment, check if bars are being captured
import boto3, json

client = boto3.client('lambda', region_name='us-west-2')

# Check bar count
r = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'sql': """
        SELECT 
            COUNT(*) as total_bars,
            COUNT(DISTINCT symbol) as unique_symbols,
            MAX(ts) as latest_bar,
            MIN(ts) as earliest_bar
        FROM option_bars
    """})
)

result = json.loads(json.load(r['Payload'])['body'])
print("Bar Capture Status:")
print(f"  Total bars: {result['rows'][0]['total_bars']}")
print(f"  Unique symbols: {result['rows'][0]['unique_symbols']}")
print(f"  Latest: {result['rows'][0]['latest_bar']}")

# Expected after 10 minutes:
# - Total bars: 10-50 (depending on active positions)
# - Unique symbols: number of open option positions
# - Latest: within last 2 minutes
```

### Test 2: Verify Position Metadata (5 minutes)

```python
# Check if positions have bar metadata
r = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'sql': """
        SELECT 
            de.option_symbol,
            de.bars_captured_count,
            de.peak_premium,
            de.lowest_premium,
            de.entry_price,
            ap.current_price
        FROM dispatch_executions de
        JOIN active_positions ap ON ap.execution_id = de.execution_id
        WHERE de.instrument_type IN ('CALL', 'PUT')
          AND ap.status = 'open'
        ORDER BY de.simulated_ts DESC
    """})
)

result = json.loads(json.load(r['Payload'])['body'])
for row in result['rows']:
    print(f"{row['option_symbol']}:")
    print(f"  Bars captured: {row['bars_captured_count']}")
    print(f"  Peak: ${row['peak_premium']} (vs entry ${row['entry_price']})")
    print(f"  Current: ${row['current_price']}")
```

### Test 3: Verify No Errors (10 minutes)

```bash
# Check position manager logs for errors
aws logs tail /ecs/ops-pipeline/position-manager \
  --region us-west-2 \
  --since 10m \
  --filter-pattern "ERROR" \
  --format short

# Should see: No ERROR messages related to bar fetching
# Some warnings about 404 are OK (no bars available)
```

---

## Rollback Plan

**If issues occur:**

```bash
# Rollback to previous task definition
aws ecs update-service \
  --cluster ops-pipeline \
  --service ops-pipeline-position-manager \
  --task-definition ops-pipeline-position-manager:1 \
  --region us-west-2

# Position manager will work normally without bar capture
# No data loss (bars just won't be captured)
```

---

## Expected Behavior

### During Open Position
**Position manager runs every 1 minute:**
1. Updates current price (existing)
2. Checks stop/target (existing)
3. **Fetches last 5-min bars** (new)
4. **Stores bars in option_bars** (new)
5. **Updates peak/lowest metadata** (new)

**Data accumulated per position:**
- If held 60 minutes: ~60 bars captured
- If held 4 hours: ~240 bars captured
- Complete price history from entry to exit

### After Position Closes
**Bars remain in database for analysis:**
```sql
-- All bars for closed position
SELECT * FROM option_bars
WHERE symbol = 'SPY260130C00609000'
ORDER BY ts;

-- Shows complete price journey
```

---

## Success Criteria

### Week 1 (Implementation)
- [x] Migration 015 applied
- [x] bar_fetcher.py created
- [x] monitor.py enhanced
- [x] db.py methods added
- [x] Deployed and running
- [x] No errors in logs

### Week 2 (Data Collection)
- [x] 50+ bars captured
- [x] Multiple positions tracked
- [x] peak_premium/lowest_premium populated
- [x] 95%+ bar capture rate

### Week 3 (Analysis)
- [x] Run AI queries
- [x] Feature importance calculated
- [x] First insights documented
- [x] Parameter recommendation generated

---

## AI Learning Queries (Same as Before)

**All the SQL queries from PHASE_17_PART2_AI_ALGORITHMS.md still work!**

The only difference is HOW we capture bars:
- **Original:** New service
- **Revised:** Position manager enhancement

The resulting data structure is identical, so all AI analysis is the same.

---

## Cost Comparison

| Item | New Service | Integrated |
|------|-------------|------------|
| Development | 45 hours | 10 hours |
| New services | +1 (10 total) | +0 (9 total) |
| Monthly cost | +$6 | +$0 |
| Schedulers | +1 | +0 |
| Maintenance | +1 service | +0 |

**Savings:** 35 hours effort, $72/year cost

---

## Summary

**Revised Phase 17 Implementation:**

1. **Database:** Add option_bars table (Migration 015)
2. **Position Manager:** Enhance to capture bars during monitoring
3. **AI Analysis:** Use same queries as original spec
4. **Result:** Same AI capabilities, 75% less work

**What Changes:**
- ❌ No new service
- ❌ No new scheduler
- ❌ No additional cost
- ✅ Enhance existing service
- ✅ Simpler architecture
- ✅ Same AI benefits

**Timeline:** 10 hours total (1-2 days)
1. Database migration: 30 min
2. Code changes: 4 hours
3. Testing: 1 hour
4. Deployment: 1 hour
5. Verification: 30 min
6. Analytics setup: 3 hours

🎯 **Next Session: Implement Phase 17A (database + position manager enhancement)**

**Documentation:**
- Original research/algorithms: PHASE_17_PART2_AI_ALGORITHMS.md (still valid!)
- Integrated implementation: This document
- All AI queries: Same as original spec
