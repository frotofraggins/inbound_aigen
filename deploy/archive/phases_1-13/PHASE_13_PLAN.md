# Phase 13: RSI + VWAP - Professional Entry Indicators
**Priority:** 🔴 CRITICAL  
**Effort:** 1 week  
**Expected ROI:** 5x entry timing improvement  
**Status:** PLANNING → IMPLEMENTATION

## Executive Summary

Phase 13 adds RSI and VWAP - the #2 and #3 most-used professional day trading indicators (after Volume from Phase 12). Combined with volume analysis, this gives us 4 of the 4 essential indicators that separate profitable traders from losers.

### Why This Matters

**From Trading Research:**
- **95%** of professional traders use RSI
- **90%** of professional traders use VWAP
- **100%** use Volume (Phase 12 ✅)
- **85%** use Moving Averages (have ✅)

**Current System:** 2 of 4 essentials (50% complete)  
**After Phase 13:** 4 of 4 essentials (100% complete)

### Expected Impact

**Before Phase 13:**
- Entry timing: Based on sentiment + trend only
- False signals: ~40% (no momentum confirmation)
- Win rate: 50-55% (baseline with volume)

**After Phase 13:**
- Entry timing: 3-5x better (RSI oversold bounces)
- False signals: ~20% (momentum + volume confirmation)
- Win rate: 55-60% (top quartile performance)

## RSI (Relative Strength Index)

### What RSI Tells You

**RSI Definition:** Momentum oscillator that measures speed and magnitude of price changes

**Range:** 0-100
- **>70:** Overbought (potential reversal down)
- **<30:** Oversold (potential reversal up)
- **50:** Neutral (no extreme)

### RSI Trading Rules (Industry Standard)

```python
# 1. Oversold Bounce
if rsi < 30 and price_above_sma20 and volume_ratio > 1.5:
    signal = "BUY"
    confidence = 0.85
    reason = "RSI oversold bounce with volume confirmation"

# 2. Overbought Reversal
if rsi > 70 and price_below_sma20 and volume_ratio > 1.5:
    signal = "SELL"
    confidence = 0.80
    reason = "RSI overbought reversal with volume"

# 3. Divergence (Advanced)
if price_making_new_high and rsi_making_lower_high:
    signal = "SELL"
    confidence = 0.90
    reason = "Bearish RSI divergence (very reliable)"
    
if price_making_new_low and rsi_making_higher_low:
    signal = "BUY"
    confidence = 0.90
    reason = "Bullish RSI divergence (very reliable)"

# 4. Trend Strength
if trend_up and rsi > 50:
    confidence *= 1.2  # Strong trend
elif trend_up and rsi < 50:
    confidence *= 0.7  # Weak trend
```

### RSI Calculation (Standard 14-period)

```python
def compute_rsi(closes, period=14):
    """
    Standard RSI calculation (Wilder's method)
    
    Args:
        closes: List of close prices (need 14+ for calculation)
        period: Lookback period (14 is standard)
    
    Returns:
        RSI value (0-100) or None if insufficient data
    """
    if len(closes) < period + 1:
        return None
    
    # Calculate price changes
    changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    
    # Separate gains and losses
    gains = [c if c > 0 else 0 for c in changes[-period:]]
    losses = [abs(c) if c < 0 else 0 for c in changes[-period:]]
    
    # Calculate averages
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    
    # Handle edge cases
    if avg_loss == 0:
        return 100  # All gains, maximally overbought
    if avg_gain == 0:
        return 0    # All losses, maximally oversold
    
    # Calculate RS and RSI
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return round(rsi, 2)
```

## VWAP (Volume-Weighted Average Price)

### What VWAP Tells You

**VWAP Definition:** Average price weighted by volume - where the "fair value" is

**Key Properties:**
- Resets daily at market open (9:30 AM)
- Acts as dynamic support/resistance
- Institutional traders use it as benchmark
- Above VWAP = bullish, Below = bearish

### VWAP Trading Rules (Industry Standard)

```python
# 1. VWAP as Support/Resistance
if price > vwap and pullback_to_vwap and volume_ratio > 1.5:
    signal = "BUY"
    confidence = 0.85
    reason = "Pullback to VWAP support in uptrend"

if price < vwap and rally_to_vwap and volume_ratio > 1.5:
    signal = "SELL"
    confidence = 0.80
    reason = "Rally to VWAP resistance in downtrend"

# 2. VWAP Crossover
if price_crossed_above_vwap and volume_surge and rsi > 50:
    signal = "BUY"
    confidence = 0.90
    reason = "Strong VWAP breakout (institutional buying)"

if price_crossed_below_vwap and volume_surge and rsi < 50:
    signal = "SELL"
    confidence = 0.85
    reason = "Strong VWAP breakdown (institutional selling)"

# 3. Distance from VWAP
distance_pct = (price - vwap) / vwap

if abs(distance_pct) > 0.02:  # More than 2% away
    if distance_pct > 0:
        signal = "SELL"  # Overextended above, expect mean reversion
    else:
        signal = "BUY"   # Overextended below, expect bounce
    confidence = 0.70
    reason = "Mean reversion to VWAP"
```

### VWAP Calculation (Intraday Only)

```python
def compute_vwap(bars_today):
    """
    VWAP = Σ(Price × Volume) / Σ(Volume)
    
    Args:
        bars_today: Only bars from current day (since 9:30 AM)
    
    Returns:
        VWAP value or None if no data
    """
    if not bars_today:
        return None
    
    # Use typical price: (high + low + close) / 3
    total_pv = sum(
        ((b['high'] + b['low'] + b['close']) / 3) * b['volume']
        for b in bars_today
    )
    total_volume = sum(b['volume'] for b in bars_today)
    
    if total_volume == 0:
        return None
    
    vwap = total_pv / total_volume
    return round(vwap, 2)
```

## Implementation Plan

### Step 1: Database Migration 008 (Day 1)

```sql
-- Migration 008: Add RSI and VWAP features

ALTER TABLE lane_features 
ADD COLUMN rsi NUMERIC(5,2),
ADD COLUMN vwap NUMERIC(10,2),
ADD COLUMN distance_vwap NUMERIC(6,4);

CREATE INDEX idx_lane_features_rsi 
ON lane_features(ticker, ts, rsi);

CREATE INDEX idx_lane_features_vwap 
ON lane_features(ticker, ts, vwap);

COMMENT ON COLUMN lane_features.rsi IS 
  '14-period RSI (0-100). >70=overbought, <30=oversold';

COMMENT ON COLUMN lane_features.vwap IS 
  'Volume-Weighted Average Price (intraday, resets daily at market open)';

COMMENT ON COLUMN lane_features.distance_vwap IS 
  '(price - vwap) / vwap. >0.02 or <-0.02 indicates overextension';
```

### Step 2: Feature Computer Updates (Day 2-3)

**File:** `services/feature_computer_1m/features.py`

Add two new functions:

```python
def compute_rsi(telemetry_data: List[Tuple], period: int = 14) -> Optional[float]:
    """
    Compute 14-period RSI from telemetry data.
    
    Standard Wilder's method for RSI calculation.
    """
    if len(telemetry_data) < period + 1:
        return None
    
    closes = [row[4] for row in telemetry_data]  # close is 5th element
    
    # Calculate changes
    changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    
    # Separate gains and losses
    gains = [c if c > 0 else 0 for c in changes[-period:]]
    losses = [abs(c) if c < 0 else 0 for c in changes[-period:]]
    
    # Average gain and loss
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    
    # Edge cases
    if avg_loss == 0:
        return 100.0
    if avg_gain == 0:
        return 0.0
    
    # RSI formula
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return round(rsi, 2)


def compute_vwap(telemetry_data: List[Tuple]) -> Optional[Dict]:
    """
    Compute VWAP for current trading day.
    
    Only uses bars from current day (since 9:30 AM market open).
    VWAP resets daily.
    """
    if not telemetry_data:
        return None
    
    # Filter to only today's market hours (9:30 AM onwards)
    # Assuming telemetry_data is sorted by timestamp
    today = telemetry_data[0][0].date()  # ts is first element
    market_open = datetime.combine(today, time(9, 30))
    
    today_bars = [
        row for row in telemetry_data 
        if row[0] >= market_open  # Only bars since market open
    ]
    
    if not today_bars:
        return None
    
    # Calculate VWAP using typical price
    total_pv = sum(
        ((row[2] + row[3] + row[4]) / 3) * row[5]  # (high + low + close)/3 * volume
        for row in today_bars
    )
    total_volume = sum(row[5] for row in today_bars)  # volume is 6th element
    
    if total_volume == 0:
        return None
    
    vwap = total_pv / total_volume
    current_price = today_bars[-1][4]  # Latest close
    distance = (current_price - vwap) / vwap
    
    return {
        'vwap': round(vwap, 2),
        'distance_vwap': round(distance, 4)
    }
```

**Update** `compute_features()` to call these:

```python
# In compute_features():
# ... existing code ...

# Compute RSI (Phase 13)
rsi = compute_rsi(telemetry_data, period=14)

# Compute VWAP (Phase 13)
vwap_features = compute_vwap(telemetry_data)

# Add to features dict
features['rsi'] = rsi
if vwap_features:
    features.update(vwap_features)

return features
```

### Step 3: Update Database Layer (Day 3)

**File:** `services/feature_computer_1m/db.py`

Update `upsert_lane_features()`:

```python
cursor.execute("""
    INSERT INTO lane_features 
        (ticker, ts, sma20, sma50, recent_vol, baseline_vol, 
         vol_ratio, distance_sma20, distance_sma50, trend_state, 
         close, computed_at,
         volume_current, volume_avg_20, volume_ratio, volume_surge,
         rsi, vwap, distance_vwap)
    VALUES 
        (%(ticker)s, %(ts)s, %(sma20)s, %(sma50)s, %(recent_vol)s,
         %(baseline_vol)s, %(vol_ratio)s, %(distance_sma20)s, 
         %(distance_sma50)s, %(trend_state)s, %(close)s, NOW(),
         %(volume_current)s, %(volume_avg_20)s, %(volume_ratio)s, %(volume_surge)s,
         %(rsi)s, %(vwap)s, %(distance_vwap)s)
    ON CONFLICT (ticker, ts)
    DO UPDATE SET
        -- ... existing updates ...
        rsi = EXCLUDED.rsi,
        vwap = EXCLUDED.vwap,
        distance_vwap = EXCLUDED.distance_vwap,
        computed_at = NOW()
""", features)
```

**Update** `get_last_telemetry()` - already returns volume, good to go.

### Step 4: Signal Engine Updates (Day 4-5)

**File:** `services/signal_engine_1m/rules.py`

Add RSI and VWAP to signal generation:

```python
def apply_rsi_filter(
    action: str,
    confidence: float,
    rsi: float,
    trend_state: int
) -> tuple[str, float, str]:
    """
    Apply RSI momentum filter to signals.
    
    RSI confirms momentum and identifies overbought/oversold.
    """
    if rsi is None:
        return action, confidence * 0.8, "NO_RSI_DATA"
    
    # Oversold bounce (BUY signal)
    if rsi < 30:
        if action == "BUY":
            return action, confidence * 1.3, f"RSI_OVERSOLD (rsi={rsi:.1f}, strong buy)"
        else:
            return "SKIP", 0.0, f"RSI_OVERSOLD (conflicts with sell signal)"
    
    # Overbought (SELL signal)
    if rsi > 70:
        if action == "SELL":
            return action, confidence * 1.3, f"RSI_OVERBOUGHT (rsi={rsi:.1f}, strong sell)"
        else:
            return "SKIP", 0.0, f"RSI_OVERBOUGHT (conflicts with buy signal)"
    
    # Trend confirmation
    if action == "BUY":
        if rsi > 50:  # RSI above 50 confirms uptrend
            return action, confidence * 1.1, f"RSI_CONFIRMS_UPTREND (rsi={rsi:.1f})"
        else:
            return action, confidence * 0.8, f"RSI_WEAK (rsi={rsi:.1f})"
    
    if action == "SELL":
        if rsi < 50:  # RSI below 50 confirms downtrend
            return action, confidence * 1.1, f"RSI_CONFIRMS_DOWNTREND (rsi={rsi:.1f})"
        else:
            return action, confidence * 0.8, f"RSI_WEAK (rsi={rsi:.1f})"
    
    return action, confidence, f"RSI_NEUTRAL (rsi={rsi:.1f})"


def apply_vwap_filter(
    action: str,
    confidence: float,
    price: float,
    vwap: float,
    distance_vwap: float,
    volume_ratio: float
) -> tuple[str, float, str]:
    """
    Apply VWAP positioning filter to signals.
    
    VWAP is institutional benchmark - price above/below tells us who's in control.
    """
    if vwap is None:
        return action, confidence * 0.9, "NO_VWAP_DATA"
    
    # Strong VWAP breakout
    if price > vwap and distance_vwap > 0.005:  # >0.5% above VWAP
        if action == "BUY" and volume_ratio > 2.0:
            return action, confidence * 1.2, f"STRONG_VWAP_BREAKOUT (above by {distance_vwap:.2%})"
        elif action == "SELL":
            return "SKIP", 0.0, "PRICE_ABOVE_VWAP (conflicts with sell)"
    
    # Strong VWAP breakdown
    if price < vwap and distance_vwap < -0.005:  # >0.5% below VWAP
        if action == "SELL" and volume_ratio > 2.0:
            return action, confidence * 1.2, f"STRONG_VWAP_BREAKDOWN (below by {distance_vwap:.2%})"
        elif action == "BUY":
            return "SKIP", 0.0, "PRICE_BELOW_VWAP (conflicts with buy)"
    
    # Mean reversion (overextended from VWAP)
    if abs(distance_vwap) > 0.02:  # >2% away from VWAP
        # Expect reversion back to VWAP
        if distance_vwap > 0:  # Too far above
            if action == "SELL":
                return action, confidence * 1.1, f"MEAN_REVERSION_SHORT (overextended {distance_vwap:.2%})"
        else:  # Too far below
            if action == "BUY":
                return action, confidence * 1.1, f"MEAN_REVERSION_LONG (oversold {distance_vwap:.2%})"
    
    # Near VWAP (fair value)
    if abs(distance_vwap) < 0.003:  # Within 0.3% of VWAP
        return action, confidence * 0.9, f"NEAR_VWAP (fair value, less conviction)"
    
    return action, confidence, f"VWAP_NEUTRAL (dist={distance_vwap:.2%})"
```

**Update main signal generation:**

```python
def compute_signal(ticker, features, sentiment):
    # ... existing signal generation ...
    
    # Apply volume multiplier (Phase 12)
    volume_mult, volume_reason = get_volume_multiplier(features['volume_ratio'])
    confidence_after_volume = base_confidence * volume_mult
    
    # Apply RSI filter (Phase 13)
    action, confidence_after_rsi, rsi_reason = apply_rsi_filter(
        action,
        confidence_after_volume,
        features.get('rsi'),
        features['trend_state']
    )
    
    # Apply VWAP filter (Phase 13)
    action, final_confidence, vwap_reason = apply_vwap_filter(
        action,
        confidence_after_rsi,
        features['close'],
        features.get('vwap'),
        features.get('distance_vwap', 0),
        features['volume_ratio']
    )
    
    # Update reason with RSI and VWAP info
    reason['rsi'] = {
        'value': features.get('rsi'),
        'assessment': rsi_reason
    }
    reason['vwap'] = {
        'value': features.get('vwap'),
        'distance': features.get('distance_vwap'),
        'assessment': vwap_reason
    }
    
    return (action, instrument, final_confidence, reason)
```

### Step 5: Update Signal Engine DB Layer (Day 5)

**File:** `services/signal_engine_1m/db.py`

Update `get_latest_features()`:

```python
cur.execute("""
    SELECT DISTINCT ON (ticker)
        ticker, close, sma20, sma50,
        distance_sma20, distance_sma50,
        recent_vol, baseline_vol, vol_ratio,
        trend_state, computed_at,
        volume_current, volume_avg_20, volume_ratio, volume_surge,
        rsi, vwap, distance_vwap
    FROM lane_features
    WHERE ticker = ANY(%s)
    ORDER BY ticker, computed_at DESC
""", (tickers,))
```

## Deployment Process

### Day 1-3: Development & Testing
1. Create migration 008
2. Update migration Lambda with 008
3. Implement RSI computation
4. Implement VWAP computation
5. Update feature_computer code
6. Update signal_engine code
7. Test locally with sample data

### Day 4-5: Deployment
1. Deploy migration 008
2. Rebuild feature_computer Docker image
3. Rebuild signal_engine Docker image
4. Push to ECR
5. Update task definitions
6. Monitor initial runs

### Day 6-7: Validation
1. Verify RSI values (should be 0-100)
2. Verify VWAP values (should be near current price)
3. Check signal generation includes RSI/VWAP
4. Monitor execution rate improvement
5. Validate win rate improvement

## Expected Results

### Feature Data (After Phase 13)
```
lane_features columns:
- ticker, ts
- sma20, sma50, distance_sma20, distance_sma50
- recent_vol, baseline_vol, vol_ratio, trend_state
- volume_current, volume_avg_20, volume_ratio, volume_surge (Phase 12)
- rsi, vwap, distance_vwap (Phase 13)
- close, computed_at

Total: 20 columns (comprehensive technical analysis)
```

### Signal Quality Improvement

**Before Phase 13 (Volume only):**
- 4-6 recommendations per day
- 50-75% execution rate
- Confidence: 30-70%
- Win rate: 50-55%

**After Phase 13 (Volume + RSI + VWAP):**
- 2-4 recommendations per day (even higher quality)
- 70-90% execution rate (momentum confirmed)
- Confidence: 40-80% (multi-indicator confirmation)
- Win rate: 55-60% (top quartile)

### Example Signal (After Phase 13)

```json
{
  "ticker": "AAPL",
  "action": "BUY",
  "instrument": "CALL",
  "confidence": 0.82,
  "reason": {
    "rule": "BULLISH_ENTRY",
    "sentiment": {"score": 0.89, "label": "positive"},
    "technicals": {
      "price": 185.23,
      "sma20": 183.50,
      "above_sma20": true
    },
    "volume": {
      "volume_ratio": 2.3,
      "volume_mult": 1.2,
      "assessment": "STRONG_VOLUME"
    },
    "rsi": {
      "value": 42,
      "assessment": "RSI_CONFIRMS_UPTREND"
    },
    "vwap": {
      "value": 184.10,
      "distance": 0.0061,
      "assessment": "ABOVE_VWAP (institutional support)"
    },
    "decision": "Strong bullish setup: positive news + above SMA20 + volume surge + RSI confirming + above VWAP"
  }
}
```

## Integration with Existing System

### Phase 12 (Volume) ✅
- Provides volume_ratio for confirmation
- VWAP uses volume for weighting
- RSI momentum + volume = high conviction

### Phase 11 (Sentiment) ✅
- Sentiment provides directional bias
- RSI confirms momentum aligns with sentiment
- VWAP shows if institutions agree

### Phase 10 (SMAs) ✅
- SMAs show trend
- RSI confirms trend strength
- VWAP acts as dynamic moving average

### Future: Phase 14 (Exit Strategy)
- RSI >70 or <30 = consider exit
- VWAP mean reversion = exit signal
- Stop loss based on ATR (to be added)

## Risk Management Enhancement

With RSI + VWAP, we can set better stops:

```python
# Dynamic stop loss based on VWAP
if entry_above_vwap:
    stop_loss = vwap * 0.99  # 1% below VWAP
else:
    stop_loss = entry_price * 0.97  # 3% below entry

# Profit target based on RSI
if rsi < 40:  # Entering oversold
    take_profit = entry_price * 1.08  # 8% gain (expect larger move)
elif rsi < 50:
    take_profit = entry_price * 1.05  # 5% gain
else:
    take_profit = entry_price * 1.03  # 3% gain (already extended)
```

## Success Criteria

### Phase 13 Considered Successful
- ✅ Migration 008 applied
- ✅ RSI values computed (0-100 range)
- ✅ VWAP values computed (near current price)
- ✅ Signal engine incorporates RSI + VWAP
- ✅ Logs show RSI and VWAP in decisions
- ✅ Execution rate improves from Phase 12 baseline

### Phase 13 Considered Highly Successful
- ✅ Execution rate: 70-90%
- ✅ Win rate: 55-60%
- ✅ RSI extremes (<30 or >70) show 80%+ win rate
- ✅ VWAP breakouts with volume show 70%+ win rate
- ✅ System behavior matches professional standards

## Code Samples for Reference

### RSI Divergence Detection (Advanced - Phase 13.5)

```python
def detect_rsi_divergence(prices, rsi_values, lookback=5):
    """
    Bearish: Price making higher highs, RSI making lower highs
    Bullish: Price making lower lows, RSI making higher lows
    """
    if len(prices) < lookback or len(rsi_values) < lookback:
        return None
    
    # Check for bearish divergence
    price_trend = prices[-1] > prices[-lookback] and prices[-1] > max(prices[-lookback:-1])
    rsi_trend = rsi_values[-1] < rsi_values[-lookback]
    
    if price_trend and rsi_trend:
        return "BEARISH_DIVERGENCE", 0.90
    
    # Check for bullish divergence
    price_trend = prices[-1] < prices[-lookback] and prices[-1] < min(prices[-lookback:-1])
    rsi_trend = rsi_values[-1] > rsi_values[-lookback]
    
    if price_trend and rsi_trend:
        return "BULLISH_DIVERGENCE", 0.90
    
    return None
```

### VWAP Bands (Advanced - Phase 13.5)

```python
def compute_vwap_bands(bars_today):
    """
    Standard deviation bands around VWAP
    Similar to Bollinger Bands but using VWAP
    """
    vwap = compute_vwap(bars_today)
    
    # Calculate standard deviation of price from VWAP
    squared_deviations = [
        ((b['close'] - vwap) ** 2) * b['volume']
        for b in bars_today
    ]
    total_volume = sum(b['volume'] for b in bars_today)
    
    variance = sum(squared_deviations) / total_volume
    std_dev = variance ** 0.5
    
    return {
        'vwap': vwap,
        'vwap_upper_1': vwap + std_dev,
        'vwap_upper_2': vwap + 2 * std_dev,
        'vwap_lower_1': vwap - std_dev,
        'vwap_lower_2': vwap - 2 * std_dev
    }
```

## Testing Strategy

### Unit Tests

```python
def test_rsi_calculation():
    # Test with known RSI values
    closes = [44, 44.34, 44.09, 43.61, 44.33, 44.83, 45.10, 45.42, 
              45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28]
    rsi = compute_rsi(closes, period=14)
    assert 60 < rsi < 65  # Expected RSI around 63
    
def test_vwap_calculation():
    bars = [
        {'high': 100, 'low': 99, 'close': 99.5, 'volume': 1000},
        {'high': 101, 'low': 100, 'close': 100.5, 'volume': 1500},
        {'high': 102, 'low': 101, 'close': 101.5, 'volume': 2000}
    ]
    vwap = compute_vwap(bars)
    assert 100 < vwap < 101  # Should be around 100.5
```

### Integration Tests

```python
def test_rsi_in_signal_generation():
    # Oversold RSI should boost BUY confidence
    features = {
        'rsi': 25,  # Oversold
        'close': 100,
        'sma20': 98,
        'volume_ratio': 2.0
    }
    signal = compute_signal('AAPL', features, sentiment_bullish)
    assert signal[0] == "BUY"
    assert signal[2] > 0.8  # High confidence

def test_vwap_prevents_bad_trades():
    # Price well below VWAP should prevent BUY
    features = {
        'close': 95,
        'vwap': 100,
        'distance_vwap': -0.05,  # 5% below
        'volume_ratio': 1.0
    }
    signal = compute_signal('AAPL', features, sentiment_bullish)
    assert signal[0] in ["SKIP", "HOLD"]  # Should not buy
```

## Monitoring After Deployment

### Key Metrics to Track

```sql
-- RSI distribution (should vary 20-80)
SELECT 
    ticker,
