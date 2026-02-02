# Phase 18: Options Risk Gates - Refactoring Design

## ⚠️ IMPORTANT: This is a REFACTORING Phase

**Options gates already exist and are working!** This phase moves existing validation code from `services/dispatcher/alpaca/options.py` into the unified `risk/gates.py` framework.

### What EXISTS Now (Phase 3-4):
- ✅ `validate_iv_rank()` in options.py - IV > 80th percentile check
- ✅ `validate_option_liquidity()` in options.py - Spread + volume checks
- ✅ `validate_option_contract()` in options.py - OI + comprehensive checks
- ✅ Called from `broker.py._execute_option()` - Works correctly

### What We're CHANGING:
- 🔄 Move functions to `risk/gates.py` (centralized location)
- 🔄 Integrate with `evaluate_all_gates()` (unified framework)
- 🔄 Rename to match convention (validate_* → check_*)
- 🔄 Add consistent observability
- 🔄 Restore volume threshold to 100 (currently 10 for testing)

## 🏗️ Refactoring Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      Dispatcher                              │
│  services/dispatcher/alpaca/broker.py                        │
│                                                              │
│  _execute_option()                                           │
│         │                                                    │
│         ▼                                                    │
│  ┌────────────────────────────────────┐                    │
│  │   Get option contract from Alpaca  │                    │
│  │   (bid, ask, IV, volume, OI)       │                    │
│  └────────────┬───────────────────────┘                    │
│               │                                             │
│               ▼                                             │
│  ┌────────────────────────────────────┐                    │
│  │    Evaluate Options Gates          │                    │
│  │    (NEW - call risk/gates.py)      │                    │
│  └────────────┬───────────────────────┘                    │
│               │                                             │
│        ┌──────┴──────┐                                     │
│        │ Pass │ Fail │                                     │
│        ▼      ▼      ▼                                     │
│     Execute  Fallback to                                   │
│     Order    Simulation                                    │
└─────────────────────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│              Risk Gates Module                               │
│  services/dispatcher/risk/gates.py                           │
│                                                              │
│  check_iv_percentile(ticker, strike, exp, iv, config)       │
│       │                                                      │
│       ▼                                                      │
│  ┌─────────────────────────────────┐                       │
│  │  Query iv_surface for history   │                       │
│  │  Calculate percentile            │                       │
│  │  Compare to threshold            │                       │
│  └─────────────────────────────────┘                       │
│                                                              │
│  check_bid_ask_spread(bid, ask, config)                     │
│       │                                                      │
│       ▼                                                      │
│  ┌─────────────────────────────────┐                       │
│  │  Calculate mid-price             │                       │
│  │  Calculate spread %              │                       │
│  │  Compare to threshold            │                       │
│  └─────────────────────────────────┘                       │
│                                                              │
│  check_option_liquidity(volume, oi, config)                 │
│       │                                                      │
│       ▼                                                      │
│  ┌─────────────────────────────────┐                       │
│  │  Check volume >= min             │                       │
│  │  Check OI >= min                 │                       │
│  │  Both must pass                  │                       │
│  └─────────────────────────────────┘                       │
└─────────────────────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                  Database                                    │
│  iv_surface table (migration 010)                           │
│                                                              │
│  Columns: ticker, strike, expiration, implied_volatility,   │
│           captured_at, bid, ask, volume, open_interest      │
│                                                              │
│  Index: (ticker, strike, expiration, captured_at DESC)      │
│  Retention: 30 days for percentile calculation              │
└─────────────────────────────────────────────────────────────┘
```

## 📝 Detailed Design

### 1. IV Percentile Gate

**Location:** `services/dispatcher/risk/gates.py`

**Function Signature:**
```python
def check_iv_percentile(
    ticker: str,
    strike: float,
    expiration: date,
    current_iv: float,
    config: Dict[str, Any]
) -> GateResult:
    """
    Check if IV is not at extreme highs.
    
    Returns:
        (passed, reason, observed_percentile, threshold_percentile)
    """
```

**Algorithm:**
```python
# 1. Query 30 days of IV history for this strike
sql = """
    SELECT implied_volatility
    FROM iv_surface
    WHERE ticker = %s
      AND strike = %s
      AND expiration = %s
      AND captured_at > NOW() - INTERVAL '30 days'
    ORDER BY captured_at DESC
"""

# 2. Calculate percentile
historical_ivs = [row['implied_volatility'] for row in results]
if len(historical_ivs) < 10:
    # Not enough history, use conservative fallback
    # Reject if IV > 1.0 (100% annualized volatility)
    passed = current_iv < 1.0
    return (passed, "Insufficient history, using static threshold", current_iv, 1.0)

# Calculate percentile rank
count_below = sum(1 for iv in historical_ivs if iv < current_iv)
percentile = (count_below / len(historical_ivs)) * 100

# 3. Check threshold
max_percentile = config.get('max_iv_percentile', 80)
passed = percentile < max_percentile

# 4. Return result
reason = f"IV at {percentile:.0f}th percentile, threshold {max_percentile}"
return (passed, reason, percentile, max_percentile)
```

**Performance Optimization:**
```python
# Cache historical IVs in memory for 5 minutes
# Key: (ticker, strike, expiration)
_iv_history_cache = {}
_cache_ttl = 300  # seconds

def get_iv_history_cached(ticker, strike, expiration):
    cache_key = (ticker, strike, expiration)
    cached_data = _iv_history_cache.get(cache_key)
    
    if cached_data and (time.time() - cached_data['timestamp']) < _cache_ttl:
        return cached_data['ivs']
    
    # Fetch from DB
    ivs = fetch_iv_history(ticker, strike, expiration)
    _iv_history_cache[cache_key] = {
        'ivs': ivs,
        'timestamp': time.time()
    }
    return ivs
```

---

### 2. Bid/Ask Spread Gate

**Location:** `services/dispatcher/risk/gates.py`

**Function Signature:**
```python
def check_bid_ask_spread(
    bid: float,
    ask: float,
    config: Dict[str, Any]
) -> GateResult:
    """
    Check if bid/ask spread is reasonable.
    
    Returns:
        (passed, reason, observed_spread_pct, threshold_spread_pct)
    """
```

**Algorithm:**
```python
# 1. Validate inputs
if bid <= 0 or ask <= 0 or ask < bid:
    return (False, f"Invalid prices: bid={bid}, ask={ask}", None, None)

# 2. Calculate spread percentage
mid = (bid + ask) / 2
spread_pct = ((ask - bid) / mid) * 100

# 3. Check threshold
max_spread = config.get('max_bid_ask_spread_pct', 10.0)
passed = spread_pct <= max_spread

# 4. Return result
reason = f"Spread {spread_pct:.1f}% {'<=' if passed else '>'} threshold {max_spread}%"
return (passed, reason, spread_pct, max_spread)
```

**Edge Cases:**
- Bid = 0: Reject (no one willing to buy)
- Ask = 0: Reject (invalid data)
- Bid > Ask: Reject (crossed market, invalid)
- Bid = Ask: Pass (perfect liquidity, theoretical)

---

### 3. Liquidity Gate

**Location:** `services/dispatcher/risk/gates.py`

**Function Signature:**
```python
def check_option_liquidity(
    volume: int,
    open_interest: int,
    config: Dict[str, Any]
) -> GateResult:
    """
    Check if option has sufficient liquidity.
    
    Returns:
        (passed, reason, (volume, oi), (min_vol, min_oi))
    """
```

**Algorithm:**
```python
# 1. Get thresholds
min_volume = config.get('min_option_volume', 100)
min_oi = config.get('min_open_interest', 100)

# 2. Check both conditions
volume_ok = volume >= min_volume
oi_ok = open_interest >= min_oi
passed = volume_ok and oi_ok

# 3. Build reason
if not volume_ok and not oi_ok:
    reason = f"Low volume ({volume}/{min_volume}) AND low OI ({open_interest}/{min_oi})"
elif not volume_ok:
    reason = f"Low volume: {volume}/{min_volume}"
elif not oi_ok:
    reason = f"Low open interest: {open_interest}/{min_oi}"
else:
    reason = f"Liquidity OK: vol={volume}, OI={open_interest}"

# 4. Return result
return (passed, reason, (volume, open_interest), (min_volume, min_oi))
```

---

### 4. Integration with evaluate_all_gates()

**Location:** `services/dispatcher/risk/gates.py`

**Modification:**
```python
def evaluate_all_gates(
    recommendation: Dict[str, Any],
    bar: Optional[Dict[str, Any]],
    features: Optional[Dict[str, Any]],
    # ... existing parameters ...
    # NEW: Option contract data
    option_contract: Optional[Dict[str, Any]] = None
) -> Tuple[bool, Dict[str, Any]]:
    """
    Evaluate all risk gates for a recommendation.
    
    NEW: If recommendation is for options, evaluate options-specific gates.
    """
    
    # Extract instrument type
    instrument = (recommendation.get('instrument_type') or '').upper()
    
    # Standard gates (all instruments)
    gates = {
        'confidence': check_confidence_gate(recommendation, config),
        'action_allowed': check_action_allowed(recommendation, config),
        # ... existing gates ...
    }
    
    # Options-specific gates (only for CALL/PUT)
    if instrument in ('CALL', 'PUT') and option_contract:
        gates['iv_percentile'] = check_iv_percentile(
            ticker=recommendation['ticker'],
            strike=option_contract['strike_price'],
            expiration=option_contract['expiration_date'],
            current_iv=option_contract.get('implied_volatility', 0),
            config=config
        )
        
        gates['bid_ask_spread'] = check_bid_ask_spread(
            bid=option_contract.get('bid', 0),
            ask=option_contract.get('ask', 0),
            config=config
        )
        
        gates['option_liquidity'] = check_option_liquidity(
            volume=option_contract.get('volume', 0),
            open_interest=option_contract.get('open_interest', 0),
            config=config
        )
    
    # Build results
    gate_results = {}
    all_passed = True
    
    for gate_name, (passed, reason, observed, threshold) in gates.items():
        gate_results[gate_name] = {
            'passed': passed,
            'reason': reason,
            'observed': observed,
            'threshold': threshold
        }
        if not passed:
            all_passed = False
    
    return (all_passed, gate_results)
```

---

### 5. Dispatcher Integration

**Location:** `services/dispatcher/alpaca/broker.py`

**Modification in `_execute_option()`:**
```python
def _execute_option(self, ...):
    """Execute options trade on Alpaca."""
    
    # ... existing code to get best_contract ...
    
    # NEW: Evaluate options-specific gates
    from risk.gates import evaluate_all_gates
    
    all_passed, gate_results = evaluate_all_gates(
        recommendation=recommendation,
        bar=bar,
        features=features,
        # ... existing parameters ...
        option_contract=best_contract  # NEW parameter
    )
    
    if not all_passed:
        # Log which gate(s) failed
        failed_gates = [
            name for name, result in gate_results.items()
            if not result['passed']
        ]
        
        logger.warning(f"Options gates failed: {', '.join(failed_gates)}")
        for gate_name in failed_gates:
            logger.warning(f"  {gate_name}: {gate_results[gate_name]['reason']}")
        
        # Fallback to simulation
        return self._simulate_execution(
            recommendation, run_id, entry_price, fill_model,
            slippage_bps, qty, notional, stop_loss, take_profit,
            max_hold_minutes, explain_json, risk_json,
            reason=f"Options gates failed: {', '.join(failed_gates)}"
        )
    
    # Gates passed - proceed with order submission
    # ... existing order execution code ...
```

---

### 6. IV Data Collection

**New Function:** `services/dispatcher/alpaca/options.py`

```python
def store_iv_surface_data(contract: Dict[str, Any], db_config: Dict[str, Any]):
    """
    Store IV and contract data for historical percentile calculations.
    
    Called every time we fetch option contracts from Alpaca.
    """
    import psycopg2
    
    conn = psycopg2.connect(**db_config)
    cursor = conn.cursor()
    
    try:
        sql = """
            INSERT INTO iv_surface (
                ticker, strike, expiration,
                implied_volatility, delta, theta, gamma, vega,
                bid, ask, last_price,
                volume, open_interest,
                captured_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (ticker, strike, expiration, captured_at)
            DO UPDATE SET
                implied_volatility = EXCLUDED.implied_volatility,
                bid = EXCLUDED.bid,
                ask = EXCLUDED.ask,
                volume = EXCLUDED.volume,
                open_interest = EXCLUDED.open_interest
        """
        
        cursor.execute(sql, (
            contract.get('underlying_symbol'),
            float(contract.get('strike_price', 0)),
            contract.get('expiration_date'),
            float(contract.get('implied_volatility', 0)),
            float(contract.get('delta', 0)),
            float(contract.get('theta', 0)),
            float(contract.get('gamma', 0)),
            float(contract.get('vega', 0)),
            float(contract.get('bid', 0)),
            float(contract.get('ask', 0)),
            float(contract.get('last_price', 0)),
            int(contract.get('volume', 0)),
            int(contract.get('open_interest', 0))
        ))
        
        conn.commit()
    finally:
        cursor.close()
        conn.close()
```

**Call Site:** In `get_option_chain_for_strategy()` after fetching contracts:
```python
# After getting contracts from Alpaca API
for contract in contracts:
    # Store for IV history
    store_iv_surface_data(contract, db_config)
```

---

### 7. Configuration Schema

**Location:** `config/trading_params.json`

**New Section:**
```json
{
  "options_gates": {
    "max_iv_percentile": 80,
    "max_bid_ask_spread_pct": 10.0,
    "min_option_volume": 100,
    "min_open_interest": 100,
    "iv_history_days": 30,
    "iv_cache_ttl_seconds": 300
  }
}
```

---

## 🧪 Testing Strategy

### Unit Tests

**File:** `tests/test_options_gates.py`

```python
import pytest
from services.dispatcher.risk.gates import (
    check_iv_percentile,
    check_bid_ask_spread,
    check_option_liquidity
)

def test_iv_percentile_high():
    """Test IV percentile gate rejects high IV"""
    # Mock IV history: [0.3, 0.4, 0.5, 0.6, 0.7]
    # Current IV: 0.75 (> 80th percentile)
    passed, reason, observed, threshold = check_iv_percentile(
        ticker="SPY",
        strike=600.0,
        expiration="2026-02-15",
        current_iv=0.75,
        config={'max_iv_percentile': 80}
    )
    
    assert not passed
    assert observed > 80
    assert "percentile" in reason.lower()

def test_bid_ask_spread_wide():
    """Test spread gate rejects wide spreads"""
    passed, reason, observed, threshold = check_bid_ask_spread(
        bid=2.00,
        ask=2.30,  # 13% spread
        config={'max_bid_ask_spread_pct': 10.0}
    )
    
    assert not passed
    assert observed > 10.0
    assert "spread" in reason.lower()

def test_liquidity_low_volume():
    """Test liquidity gate rejects low volume"""
    passed, reason, observed, threshold = check_option_liquidity(
        volume=50,  # Below threshold
        open_interest=200,
        config={'min_option_volume': 100, 'min_open_interest': 100}
    )
    
    assert not passed
    assert "volume" in reason.lower()
```

### Integration Tests

**File:** `tests/test_options_gates_integration.py`

```python
def test_dispatcher_rejects_high_iv_option():
    """Test that dispatcher rejects option with high IV"""
    # Setup: Option with IV at 95th percentile
    recommendation = create_option_recommendation()
    option_contract = {
        'strike_price': 600.0,
        'expiration_date': '2026-02-15',
        'implied_volatility': 0.95,  # Very high
        'bid': 5.00,
        'ask': 5.10,
        'volume': 1000,
        'open_interest': 5000
    }
    
    # Execute
    result = dispatcher._execute_option(recommendation, option_contract)
    
    # Verify
    assert result['execution_mode'] == 'SIMULATED_FALLBACK'
    assert 'iv_percentile' in result['explain_json']['fallback_reason'].lower()
```

---

## 📊 Monitoring & Observability

### Metrics to Track

1. **Gate Pass/Fail Rates** (CloudWatch custom metrics)
   ```python
   cloudwatch.put_metric_data(
       Namespace='OpsOptions/Gates',
       MetricName='IVPercentileBlocks',
       Value=1,
       Unit='Count'
   )
   ```

2. **Gate Evaluation Time** (logs)
   ```python
   start = time.time()
   result = check_iv_percentile(...)
   duration_ms = (time.time() - start) * 1000
   logger.info(f"IV gate evaluated in {duration_ms:.1f}ms")
   ```

3. **False Positive Analysis** (periodic review)
   - Query blocked trades that would have been profitable
   - Tune thresholds based on results

### Dashboard Queries

```sql
-- Options gates effectiveness (last 7 days)
SELECT 
    DATE(simulated_ts) as date,
    COUNT(*) as total_options_signals,
    COUNT(*) FILTER (WHERE execution_mode = 'ALPACA_PAPER') as executed,
    COUNT(*) FILTER (WHERE execution_mode = 'SIMULATED_FALLBACK' 
                      AND explain_json->>'fallback_reason' LIKE '%iv%') as iv_blocks,
    COUNT(*) FILTER (WHERE execution_mode = 'SIMULATED_FALLBACK' 
                      AND explain_json->>'fallback_reason' LIKE '%spread%') as spread_blocks,
    COUNT(*) FILTER (WHERE execution_mode = 'SIMULATED_FALLBACK' 
                      AND explain_json->>'fallback_reason' LIKE '%liquidity%') as liquidity_blocks
FROM dispatch_executions
WHERE instrument_type IN ('CALL', 'PUT')
  AND simulated_ts > NOW() - INTERVAL '7 days'
GROUP BY DATE(simulated_ts)
ORDER BY date DESC;
```

---

**Next:** See [TASKS.md](./TASKS.md) for implementation checklist
