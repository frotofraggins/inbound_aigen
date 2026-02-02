# Watchlist Strategy Enhancement Plan

**Date:** 2026-01-12  
**Current Status:** Phase 8.0a deployed with basic 36-stock universe  
**Goal:** Upgrade to professional-grade watchlist with 100-300 liquid, options-friendly stocks

---

## Current Universe Analysis

**Existing 36 stocks:**
```
AAPL,MSFT,GOOGL,AMZN,META,NVDA,TSLA,NFLX,ADBE,CRM,ORCL,INTC,AMD,
QCOM,TXN,AVGO,CSCO,IBM,MU,AMAT,LRCX,KLAC,SNPS,CDNS,ASML,TSM,NOW,
PLTR,SNOW,DDOG,ZS,NET,CRWD,PANW,FTNT,OKTA
```

**Strengths:**
- ✅ All mega-cap tech (high liquidity)
- ✅ Most have active options markets
- ✅ Good representation of cloud, cybersecurity, semiconductors

**Gaps:**
- ❌ No financial sector (banks are highly liquid + options-active)
- ❌ No energy sector (XLE, major oils)
- ❌ No ETFs (SPY, QQQ, IWM = best options liquidity)
- ❌ No industrials, healthcare, consumer
- ❌ Too narrow focus = missing outlier opportunities

---

## Proposed Enhanced Universe (120-150 stocks)

### Core Principle: Tradability > Company Quality

**Must-have criteria:**
1. **High share volume** (tight spreads, easy entries/exits)
2. **High options volume/OI** (can actually fill option orders)
3. **Frequent catalysts** (earnings, sector news, macro sensitivity)

### Recommended Universe Composition

#### 1. Major ETFs (15 tickers) - HIGHEST PRIORITY
```
SPY     # S&P 500 (most liquid options in the world)
QQQ     # Nasdaq-100
IWM     # Russell 2000 small caps
DIA     # Dow Jones

XLF     # Financials
XLE     # Energy
XLK     # Technology
XLV     # Healthcare
XLI     # Industrials
XLP     # Consumer Staples
XLY     # Consumer Discretionary
XLU     # Utilities
XLB     # Materials

TLT     # 20+ Year Treasury Bonds
GLD     # Gold
```
**Why ETFs matter:** Most liquid options, tight spreads, sector rotation plays

#### 2. Mega-Cap Tech (Keep existing 36, all excellent)
```
Current 36 stocks - KEEP ALL
```

#### 3. Financial Sector (15 tickers)
```
JPM     # JPMorgan Chase
BAC     # Bank of America
WFC     # Wells Fargo
C       # Citigroup
GS      # Goldman Sachs
MS      # Morgan Stanley
BLK     # BlackRock
V       # Visa
MA      # Mastercard
AXP     # American Express
SCHW    # Charles Schwab
COF     # Capital One
USB     # US Bancorp
PNC     # PNC Financial
TFC     # Truist Financial
```
**Why:** Banks move on Fed policy, earnings, rates = constant catalysts

#### 4. Energy & Commodities (12 tickers)
```
XOM     # Exxon Mobil
CVX     # Chevron
COP     # ConocoPhillips
SLB     # Schlumberger
EOG     # EOG Resources
MPC     # Marathon Petroleum
PSX     # Phillips 66
OXY     # Occidental Petroleum

FCX     # Freeport-McMoRan (copper)
NEM     # Newmont (gold mining)
CLF     # Cleveland-Cliffs (steel)
X       # US Steel
```
**Why:** Oil/commodities have huge volatility + options activity on macro news

#### 5. Healthcare & Pharma (10 tickers)
```
UNH     # UnitedHealth
JNJ     # Johnson & Johnson
PFE     # Pfizer
ABBV    # AbbVie
LLY     # Eli Lilly
MRK     # Merck
TMO     # Thermo Fisher
ABT     # Abbott Labs
BMY     # Bristol Myers Squibb
GILD    # Gilead
```
**Why:** FDA approvals, earnings surprises, policy changes = catalysts

#### 6. Industrials & Transports (10 tickers)
```
BA      # Boeing
CAT     # Caterpillar
GE      # General Electric
HON     # Honeywell
LMT     # Lockheed Martin
RTX     # Raytheon
UPS     # United Parcel Service
FDX     # FedEx
DAL     # Delta Air Lines
AAL     # American Airlines
```
**Why:** Macro-sensitive, earnings volatility

#### 7. Consumer & Retail (12 tickers)
```
COST    # Costco
WMT     # Walmart
TGT     # Target
HD      # Home Depot
LOW     # Lowe's
NKE     # Nike
SBUX    # Starbucks
MCD     # McDonald's
DIS     # Disney
UBER    # Uber
LYFT    # Lyft
DASH    # DoorDash
```
**Why:** Consumer sentiment, earnings surprises

#### 8. Communication & Media (8 tickers)
```
T       # AT&T
VZ      # Verizon
TMUS    # T-Mobile
CMCSA   # Comcast
PARA    # Paramount
WBD     # Warner Bros Discovery
SPOT    # Spotify
RBLX    # Roblox
```

**Total: ~120-150 stocks** (manageable for 1-minute data polling)

---

## Enhanced Scoring Algorithm

### Current Scoring (Phase 8.0a)
```
watch_score = 
  0.35 × sentiment_pressure +
  0.25 × setup_quality +
  0.20 × vol_score +
  0.20 × trend_alignment
```

### Proposed Enhanced Scoring (Phase 8.1+)
```
watch_score = 
  0.40 × liquidity_score +
  0.30 × catalyst_score +
  0.30 × movement_score
```

#### Component Definitions

**1. Liquidity Score (40%) - NEW**
```python
liquidity_score = 
  0.6 × volume_rank +           # Share volume vs universe
  0.4 × options_activity_rank   # Options volume (if available)

# Fallback if no options data:
liquidity_score = volume_rank
```

**2. Catalyst Score (30%) - NEW**
```python
catalyst_score = 
  0.5 × earnings_proximity +     # 1.0 if earnings within 7 days, else 0
  0.3 × news_pressure_30m +      # Count of classified news in last 30min
  0.2 × sector_momentum          # Sector ETF trending
```

**3. Movement Score (30%) - ENHANCED**
```python
movement_score = 
  0.4 × vol_expansion +          # vol_ratio (current vs baseline)
  0.3 × price_displacement +     # abs(distance from SMA20)
  0.3 × trend_break_signal       # NEW: recent SMA cross
```

---

## Outlier Detection (NEW Features)

### Add to lane_features table:

#### 1. Trend Break Signals
```python
# Bullish break
trend_break_bullish = (
    close > sma20 and 
    prev_close <= prev_sma20 and
    sma20 > sma20_5bars_ago  # SMA20 is rising
)

# Bearish break  
trend_break_bearish = (
    close < sma20 and
    prev_close >= prev_sma20 and
    sma20 < sma20_5bars_ago  # SMA20 is falling
)
```

#### 2. Volatility Expansion Levels
```python
vol_alert_level = (
    'extreme' if vol_ratio >= 1.6 else
    'high' if vol_ratio >= 1.3 else
    'elevated' if vol_ratio >= 1.1 else
    'normal' if vol_ratio >= 0.8 else
    'compressed'
)
```

#### 3. News Pressure (from inbound_events_classified)
```python
# Aggregate from last 30 minutes
news_count_30m = COUNT(*) WHERE published_at > NOW() - 30 minutes
sentiment_net_30m = AVG(sentiment_score - 0.5) * 2  # Scale to -1 to +1

# Outlier flag
news_spike = news_count_30m >= 3 OR abs(sentiment_net_30m) >= 0.75
```

---

## Enhanced Signal Engine Logic

### Instrument Selection Decision Tree

```python
def select_instrument(ticker, features, sentiment):
    """
    Returns: 'BUY_CALL', 'BUY_PUT', 'BUY_STOCK', 'SELL_PREMIUM', 'NO_TRADE'
    """
    
    vol_ratio = features['vol_ratio']
    trend_state = features['trend_state']
    distance_sma20 = features['distance_sma20']
    sentiment_strength = abs(sentiment['avg_score'] - 0.5) * 2
    
    # Strong directional sentiment
    is_bullish = sentiment['avg_score'] > 0.65
    is_bearish = sentiment['avg_score'] < 0.35
    is_neutral = 0.40 <= sentiment['avg_score'] <= 0.60
    
    # Volatility regime
    vol_normal = 0.8 <= vol_ratio <= 1.3
    vol_high = vol_ratio > 1.4
    vol_compressed = vol_ratio < 0.8
    
    # Trend alignment
    above_sma20 = distance_sma20 > 0
    below_sma20 = distance_sma20 < 0
    
    # BULLISH CASE
    if is_bullish and trend_state >= 0:  # Bullish sentiment + uptrend/neutral
        if vol_normal and above_sma20:
            return 'BUY_CALL'  # Clean setup
        elif vol_high:
            return 'BUY_STOCK'  # Options too expensive, use stock
        elif vol_compressed and above_sma20:
            return 'BUY_CALL'  # Cheap options before breakout
    
    # BEARISH CASE
    if is_bearish and trend_state <= 0:  # Bearish sentiment + downtrend/neutral
        if vol_normal and below_sma20:
            return 'BUY_PUT'  # Clean setup
        elif vol_high:
            return 'BUY_STOCK'  # Short stock (or avoid if can't short)
        elif vol_compressed and below_sma20:
            return 'BUY_PUT'  # Cheap options before breakdown
    
    # NEUTRAL / HIGH VOL = PREMIUM SELLING OPPORTUNITY
    if is_neutral and vol_high and abs(distance_sma20) < 0.02:
        return 'SELL_PREMIUM'  # Range-bound + expensive options
    
    return 'NO_TRADE'
```

### Confidence Scoring
```python
confidence = (
    0.4 × sentiment_strength +      # How strong is sentiment?
    0.3 × trend_alignment +          # Sentiment matches trend?
    0.2 × vol_appropriateness +      # Vol suits the instrument?
    0.1 × setup_quality              # Clean technical setup?
)
```

---

## Implementation Roadmap

### Phase 8.1: Expand Universe + Add Outlier Detection
**Time:** 2-3 hours

1. **Update universe_tickers SSM parameter**
   - Add 120-150 stocks (ETFs, financials, energy, etc.)
   - Update telemetry ingestor to handle larger universe

2. **Enhance lane_features computation**
   - Add trend_break_bullish, trend_break_bearish flags
   - Add vol_alert_level enum
   - Add news_count_30m, sentiment_net_30m

3. **Update watchlist scoring**
   - Implement liquidity_score (volume_rank)
   - Implement catalyst_score (earnings + news_pressure)
   - Implement movement_score (vol + displacement + trend_break)

### Phase 8.2: Build Enhanced Signal Engine
**Time:** 2-3 hours

1. **Create signal_engine_1m service**
   - Query watchlist_state (top 30 only)
   - Apply instrument selection logic
   - Write to dispatch_recommendations with:
     - instrument_type: CALL/PUT/STOCK/PREMIUM
     - direction: LONG/SHORT
     - confidence: 0.0-1.0
     - reasons: JSONB (why this decision?)

2. **Deploy as ECS task**
   - Run every 1 minute
   - 256 CPU / 512 MB

### Phase 8.3: Add Liquidity Tracking (Future)
**Time:** 1-2 hours

1. **Extend lane_telemetry**
   - Add volume field (from Alpaca)
   - Track daily volume rank

2. **Options volume tracking** (advanced)
   - Requires options data API
   - Can start without this, add later

---

## Data Source Requirements

### Current (✅ Have)
- 1-minute OHLCV from Alpaca (IEX feed)
- RSS news classification with FinBERT
- Technical indicators (SMA, volatility)

### Nice-to-Have (Future)
- Options volume/OI (requires paid API like Tradier, CBOE)
- Earnings calendar API
- IV/Greeks (for premium selling)

### Workarounds Until Then
- Use news_count as proxy for "something happening"
- Use vol_ratio as proxy for options activity
- Manual earnings calendar (updated weekly)

---

## Cost Impact

**Current:** $34.91/month

**After expansion:**
- Telemetry: 120 stocks × 1min = still under Alpaca free tier (200 req/min)
- Feature computer: ~20 seconds compute (still $0.30/month)
- Watchlist engine: ~15 seconds compute (still $0.30/month)
- Signal engine: ~10 seconds compute ($0.30/month)

**New total:** ~$35.50/month (minimal increase)

---

## Testing Strategy

1. **Backtest watchlist selection**
   - Run scoring on historical data
   - Verify top 30 includes "trending" stocks

2. **Validate signal generation**
   - Check instrument_type makes sense
   - Verify confidence scores reasonable
   - Ensure NO_TRADE when appropriate

3. **Monitor for 1 week**
   - Track watchlist rotation
   - Count signals generated
   - Review reasons in JSONB

---

## Next Steps

1. ✅ **Review this strategy** - Are you happy with the approach?
2. ⏭️ **Expand universe_tickers** - Add 120-150 stocks
3. ⏭️ **Implement outlier detection** - Add new features
4. ⏭️ **Update watchlist scoring** - New algorithm
5. ⏭️ **Build signal engine** - Instrument selection logic

---

**Key Insight:** You're building a *filter* (watchlist) → *decision engine* (signals) → *executor* (dispatcher). Each layer should be:
- **Testable** (can backtest rules)
- **Explainable** (JSONB reasons)
- **Improvable** (metrics guide refinement)

This beats "guessing stocks" because you're systematically finding outliers + applying consistent rules.
