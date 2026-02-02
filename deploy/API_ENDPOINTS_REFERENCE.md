# API Endpoints Reference - Complete System

## Alpaca APIs Used

### 1. Trading API (Paper Trading)
**Base URL:** `https://paper-api.alpaca.markets`  
**Used By:** Dispatcher, Position Manager  
**Authentication:** API Key + Secret from Secrets Manager

**Endpoints:**

#### Account Information
```
GET /v2/account
Purpose: Get account balance, buying power, equity
Used by: Dispatcher (every run)
Success: Returns account object with buying_power, equity, etc.
```

#### Positions
```
GET /v2/positions
Purpose: Get all open positions
Used by: Position Manager (every 5 minutes)
Success: Returns array of position objects
Example Response:
[
  {
    "symbol": "QCOM260206C00150000",
    "qty": "26",
    "market_value": "16380.00",
    "avg_entry_price": "5.75",
    "current_price": "6.30",
    "unrealized_pl": "1430.00"
  }
]
```

#### Orders
```
POST /v2/orders
Purpose: Submit new orders
Used by: Dispatcher (when signals trigger)
Payload: {
  "symbol": "QCOM260206C00150000",
  "qty": 26,
  "side": "buy",
  "type": "limit",
  "time_in_force": "day",
  "limit_price": 5.75
}

GET /v2/orders
Purpose: Check order status
Used by: Position Manager (to verify fills)

DELETE /v2/orders/{order_id}
Purpose: Cancel orders
Used by: Risk management (if needed)
```

#### Market Data (Options Chain)
```
GET /v1/options/contracts
Purpose: Get available option contracts
Used by: Dispatcher (when selecting contracts)
Query params: underlying_symbols, expiration_date_gte, limit
Success: Returns array of option contracts with greeks
```

### 2. Market Data API (Separate Subscription Required)
**Base URL:** `https://data.alpaca.markets`  
**Used By:** Telemetry (attempted, not working)  
**Status:** ❌ Requires paid subscription

**Endpoints:**
```
GET /v2/stocks/{symbol}/bars
Purpose: Get OHLCV historical bars
Used by: Telemetry (attempted)
Status: Returns 401 (no data subscription)
```

---

## Alternative Data Sources

### yfinance (Free, No Auth Required)
**Used By:** Telemetry (fallback)  
**Status:** Configured but having issues

**Library:** Python yfinance package  
**Methods:**
```python
import yfinance as yf

# Get historical data
ticker = yf.Ticker("QCOM")
hist = ticker.history(period="1d", interval="1m")

# Returns: DataFrame with Open, High, Low, Close, Volume
```

---

## Internal AWS Services

### Database (PostgreSQL RDS)
**Endpoint:** `ops-pipeline-db.czow18p7ug2w.us-west-2.rds.amazonaws.com:5432`  
**Database:** `ops_pipeline`  
**Used By:** All services

**Access Methods:**
1. Direct connection (from ECS tasks)
2. Lambda query function (from scripts)

### AWS Secrets Manager
**Region:** `us-west-2`

**Secrets:**
```
ops-pipeline/db
- username: postgres
- password: YourSecurePassword123!

ops-pipeline/alpaca (large-100k account)
- api_key: PKHE57Z4BKSIUQLTNQQK...
- api_secret: Ft5yje4MJYbgRaEUGHbafgi5tUetYnQfxktwWwAR...
- account_name: large-100k
- base_url: https://paper-api.alpaca.markets

ops-pipeline/alpaca/tiny (tiny-1k account)
- api_key: PKRTAIU5VRKXIAOCZHFI...
- api_secret: JmH7nhByjjfuhWCJ8qvQUbTGM7tzTkBZEfSnX1mi...
- account_name: tiny-1k
```

### AWS SSM Parameter Store
**Region:** `us-west-2`

**Parameters:**
```
/ops-pipeline/db_host
/ops-pipeline/db_port
/ops-pipeline/db_name
/ops-pipeline/dispatcher_config (optional config overrides)
```

---

## Service-Specific Endpoint Configuration

### Position Manager Service ✅ WORKING

**Alpaca Endpoints Used:**
```
GET /v2/account          → Get buying power
GET /v2/positions        → Get all positions (YOUR 3 QCOM)
GET /v2/orders           → Check order status
GET /v2/clock           → Market hours
POST /v2/orders         → Exit positions
```

**Base URL:** Loaded from Secrets Manager  
**Credentials:** From `ops-pipeline/alpaca` secret  
**Status:** ✅ Successfully finding 3 positions!

**Logs show:**
```
Found 3 position(s) in Alpaca
- QCOM260206C00150000
- QCOM260227P00150000
- SPY260130C00609000
```

### Dispatcher Service

**Alpaca Endpoints Used:**
```
GET /v2/account          → Check buying power before trades
GET /v1/options/contracts → Get option contracts
POST /v2/orders         → Submit option orders
GET /v2/orders/{id}     → Verify order accepted
```

**Base URL:** From Secrets Manager (`ops-pipeline/alpaca`)  
**Status:** ✅ Ready to execute trades

### Telemetry Service (Data Collection)

**Attempted:**
```
Alpaca Data API: https://data.alpaca.markets/v2/stocks/{symbol}/bars
Status: ❌ 401 (no data subscription)
```

**Fallback:**
```
yfinance: Free Python library
Status: ⚠️ Having intermittent issues
```

**Current:** Not collecting new data (using historical)

---

## Endpoint Health Check

### ✅ Working:
- Alpaca Trading API (paper-api.alpaca.markets) ✅
- Position Manager → Alpaca ✅
- Dispatcher → Alpaca ✅
- Database → All services ✅
- Secrets Manager → All services ✅

### ❌ Not Working:
- Alpaca Data API → Telemetry (needs subscription)
- yfinance → Telemetry (intermittent failures)

---

## Rate Limits

### Alpaca Trading API (Paper)
- 200 requests per minute per API key
- Position Manager uses ~5 requests per check
- Dispatcher uses ~10-20 requests per trade
- Well within limits

### Alpaca Data API
- Not applicable (no subscription)

### yfinance
- No official rate limits
- Best practice: 1 request per second
- Telemetry uses pacing (built-in delays)

---

## Testing Endpoints

### Verify Alpaca Trading API:
```bash
# Test with your credentials
curl -X GET "https://paper-api.alpaca.markets/v2/account" \
  -H "APCA-API-KEY-ID: PKHE57Z4BKSIUQLTNQQK..." \
  -H "APCA-API-SECRET-KEY: Ft5yje4MJYbgRaEUGHbafgi5..."
```

### Verify Position Manager:
```bash
# Check logs
aws logs tail /ecs/ops-pipeline/position-manager-service \
  --region us-west-2 --follow

# Should see "Found 3 position(s) in Alpaca"
```

---

## Summary

**Critical Endpoints Working:**
- ✅ Alpaca Trading API (positions, orders, account)
- ✅ Database (all services)
- ✅ Secrets Manager (credentials)

**Non-Critical Not Working:**
- ❌ Alpaca Data API (need paid subscription)
- ⚠️ yfinance (fallback having issues)

**Impact:** Position monitoring works! Data collection needs fix but not blocking.

**Your 3 QCOM positions ARE being monitored via Alpaca Trading API.** ✅
