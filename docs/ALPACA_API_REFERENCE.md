# 📚 Alpaca API Complete Reference
**Last Updated:** 2026-02-04
**Purpose:** Comprehensive reference for all Alpaca API usage in this project

---

## 🎯 Quick Reference

### What We Use
- **Trading API** (not Broker API)
- **Paper Trading** environment
- **Subscriptions:** Basic plan (free, IEX real-time for stocks)
- **Asset classes:** Stocks and Options

### Base URLs
- **Trading:** `https://paper-api.alpaca.markets`
- **Market Data:** `https://data.alpaca.markets`
- **WebSocket:** `wss://stream.data.alpaca.markets`

---

## 📊 Market Data API

### Subscription Plans (Trading API)

#### Basic Plan (FREE - What We Have)
**Equities:**
- Real-time: IEX exchange only (~2.5% of market)
- Historical: Since 2016, but latest 15 minutes delayed
- API calls: 200/min
- WebSocket: 30 symbols

**Options:**
- Real-time: **Indicative Pricing Feed** (NOT OPRA)
- Historical: **Latest 15 minutes delayed**
- WebSocket: 200 quotes
- **NO OPTIONS BARS DATA** in paper trading

#### Algo Trader Plus ($99/month)
**Equities:**
- Real-time: All US exchanges (100% coverage)
- Historical: Since 2016, no restrictions
- API calls: 10,000/min
- WebSocket: Unlimited

**Options:**
- Real-time: OPRA Feed (full options data)
- Historical: No restrictions
- WebSocket: 1000 quotes
- **Options bars available**

---

## 🎯 Options Trading

### Paper Trading
- ✅ Options enabled by default
- ✅ All trading levels available
- ✅ Can place orders
- ✅ Can get positions
- ❌ **Options bars NOT available** (explains our 403!)
- ⚠️ NTAs synced next day (not real-time)

### Trading Levels (All Available in Paper)
1. **Level 0:** Disabled
2. **Level 1:** Covered calls, cash-secured puts
3. **Level 2:** Buy calls/puts
4. **Level 3:** Spreads, iron condors

### Order Requirements
- **time_in_force:** Must be "day" (not gtc, ioc, fok)
- **Quantity:** Must be whole numbers
- **No extended hours**
- **No notional orders**
- **Order types:** market, limit (stop/stop_limit only for single-leg)

### Expiration Handling
**Our Code:**
- ✅ Checks expiration_date field
- ✅ Force exit at < 24 hours
- ✅ Theta decay warning at < 7 days
- ✅ Automatic ITM exercise by Alpaca

**Alpaca's Handling:**
- Auto-exercises ITM contracts (>$0.01)
- Sells position 1 hour before expiry if insufficient buying power
- OTM contracts expire worthless

---

## 🔧 Why We're Getting 403 on Options Bars

### The Issue
```
403 Forbidden: https://data.alpaca.markets/v1beta1/options/bars
```

### Root Cause
**Paper trading Basic plan does NOT include options bars historical data.**

From Alpaca docs:
- Basic plan: "Indicative Pricing Feed" for options
- Options bars: Only in Algo Trader Plus ($99/month)
- Paper trading: Uses indicative feed (not full OPRA)

### What This Means
- ❌ Can't fetch historical bars for options
- ❌ Can't collect bar patterns for learning
- ✅ Can still get current option price (from positions API)
- ✅ Can still monitor positions
- ✅ Can still execute trades
- ✅ Exit logic still works perfectly

### Is This a Blocker?
**NO** - Our core functionality works without options bars:
- Position monitoring: Uses positions API ✅
- Current price: From positions.current_price ✅
- Exit logic: Based on P&L, not bars ✅
- Trade execution: Works fine ✅

**What we lose:**
- Can't learn from intraday bar patterns for options
- Can't backtest options with bars
- Can't do advanced technical analysis on options

### Solutions

#### Option 1: Accept Limitation (RECOMMENDED)
- Keep using Basic plan (free)
- Focus on entry/exit price learning
- Use stock bars for underlying analysis
- Options learning from outcomes, not bars

#### Option 2: Upgrade to Algo Trader Plus
- Cost: $99/month
- Gets: Full options bars access
- Gets: All exchanges for stocks
- Gets: Unlimited API calls

#### Option 3: Only Trade Stocks
- Stick to equities where we have full data
- No options bars issues
- Simpler learning pipeline

---

## 📊 What Data We CAN Get (Basic Plan)

### Stocks (Full Data) ✅
- Real-time quotes (IEX)
- Historical bars (all timeframes)
- Latest trades
- Latest quotes
- Snapshots

### Options (Limited Data) ⚠️
- Latest quotes (indicative)
- Latest trades
- Current positions
- ❌ **NO historical bars**
- ❌ **NO intraday bars**

### Our Current Usage
```python
# What works ✅
alpaca.get_all_positions()  # Current option positions
alpaca.get_latest_quote("INTC260220C00049500")  # Current quote

# What fails ❌
alpaca.get_option_bars("INTC260220C00049500")  # 403 Forbidden
```

---

## 🎯 Our Implementation Status

### What We're Using Correctly ✅
1. **Positions API** - Get current positions (works!)
2. **Orders API** - Place/cancel orders (works!)
3. **Latest quotes** - Get current price (works!)
4. **Account API** - Check balance (works!)
5. **Stocks bars** - Historical stock data (works!)

### What We're Trying But Can't (403)
1. **Options bars** - Historical option bars
   - **Why:** Basic plan doesn't include it
   - **Impact:** LOW - position management works without it
   - **Fix:** Upgrade plan OR accept limitation

### Recommendation
**Accept the 403 as a limitation of paper trading Basic plan.**

Our core functionality works perfectly:
- ✅ Monitor positions
- ✅ Track P&L
- ✅ Execute exits
- ✅ Record outcomes

We lose:
- ❌ Options bar pattern learning (advanced feature)

This is acceptable for now. Can upgrade later if needed.

---

## 📝 Code Usage Examples

### Current Position Tracking (What We Do)
```python
# From monitor.py
def update_position_price(position):
    # Get current price from Alpaca positions
    alpaca_positions = alpaca_client.get_all_positions()
    
    for ap in alpaca_positions:
        if ap.symbol == position['option_symbol']:
            current_price = float(ap.current_price)
            # Update our database
            return True
```

**Status:** ✅ Works perfectly without bars

### Option Bars Learning (What Fails)
```python
# From bar_fetcher.py  
def fetch_option_bars(symbol):
    # Try to get historical bars
    bars = alpaca_client.get_option_bars(
        symbol_or_symbols=symbol,
        timeframe="1Min"
    )
```

**Status:** ❌ 403 Forbidden (paper trading limitation)

---

## 🔧 Proper API Usage

### Authentication (What We Do) ✅
```python
ALPACA_API_KEY = from secrets manager
ALPACA_API_SECRET = from secrets manager  
ALPACA_BASE_URL = "https://paper-api.alpaca.markets"
```

### Order Placement (What We Do) ✅
```python
# Single-leg option order
order = alpaca.submit_order(
    symbol="INTC260220C00049500",
    qty=10,
    side="buy",
    type="market",
    time_in_force="day"  # REQUIRED for options
)
```

### Position Monitoring (What We Do) ✅
```python
# Get all positions
positions = alpaca.get_all_positions()

# Filter for our option
for pos in positions:
    if pos.symbol == "INTC260220C00049500":
        current_price = float(pos.current_price)
        qty = float(pos.qty)
```

---

## ✅ Action Items

### Immediate (None Required)
- Current usage is correct
- 403 error is expected with Basic plan
- Position management works perfectly

### Future Consideration
- [ ] Decide if options bars learning is needed
- [ ] If yes, upgrade to Algo Trader Plus ($99/mo)
- [ ] If no, document limitation and continue

### Documentation Added
- [x] Created ALPACA_API_REFERENCE.md
- [x] Explained subscription plans
- [x] Documented 403 root cause
- [x] Confirmed our usage is correct
- [x] Provided code examples

---

**CONCLUSION:** The 403 error is expected and acceptable. Our Basic plan doesn't include options bars, but position management works perfectly without them. We can upgrade later if options bar learning becomes critical.
