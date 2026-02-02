# Phase 18: Options Risk Gates - Refactoring Tasks

## ⚠️ IMPORTANT: This is a REFACTORING Phase

**Options gates already exist and work!** (Deployed in Phase 3-4)

This phase consolidates existing validation code from `services/dispatcher/alpaca/options.py` into the unified `risk/gates.py` framework.

### Existing Functions to Refactor:
- ✅ `validate_iv_rank()` in options.py → move to `check_iv_percentile()` in gates.py
- ✅ `validate_option_liquidity()` in options.py → extract to `check_bid_ask_spread()` + `check_option_liquidity()` in gates.py
- ✅ `validate_option_contract()` in options.py → consolidate into gates.py

## 📋 Refactoring Checklist

Total Estimated Time: **3-4 hours** (refactoring, not building from scratch)

---

## Phase 1: Setup & Configuration (30 min)

### Task 1.1: Add Configuration Parameters
- [ ] Open `config/trading_params.json`
- [ ] Add new `options_gates` section:
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
- [ ] Commit changes: `git commit -m "feat(config): add options gates configuration"`

### Task 1.2: Verify Database Schema
- [ ] Confirm `iv_surface` table exists from migration 010
- [ ] Run query to check table structure:
  ```sql
  \d iv_surface
  ```
- [ ] Verify index on `(ticker, strike, expiration, captured_at)`
- [ ] Document any missing columns (should be none)

**Estimated Time:** 30 minutes  
**Verification:** Configuration file updated, database schema confirmed

---

## Phase 2: Implement Gate Functions (2 hours)

### Task 2.1: Add IV Percentile Gate
- [ ] Open `services/dispatcher/risk/gates.py`
- [ ] Add import at top:
  ```python
  from typing import Dict, Any, Tuple, Optional, List
  from datetime import datetime, timedelta
  import time
  ```
- [ ] Add global cache dictionary after imports:
  ```python
  # IV history cache (5 min TTL)
  _iv_history_cache = {}
  ```
- [ ] Implement `check_iv_percentile()` function (see DESIGN.md section 1)
- [ ] Implement helper `get_iv_history_cached()` function
- [ ] Add database query function `fetch_iv_history()`
- [ ] Test function with mock data

**Code Template:**
```python
def check_iv_percentile(
    ticker: str,
    strike: float,
    expiration: str,
    current_iv: float,
    config: Dict[str, Any]
) -> GateResult:
    """Check if IV is not at extreme highs."""
    # Implementation from DESIGN.md
    pass
```

**Estimated Time:** 1 hour  
**Verification:** Function returns correct (passed, reason, percentile, threshold)

### Task 2.2: Add Bid/Ask Spread Gate
- [ ] In `services/dispatcher/risk/gates.py`
- [ ] Implement `check_bid_ask_spread()` function (see DESIGN.md section 2)
- [ ] Handle edge cases (bid=0, ask=0, bid>ask)
- [ ] Test with sample data

**Code Template:**
```python
def check_bid_ask_spread(
    bid: float,
    ask: float,
    config: Dict[str, Any]
) -> GateResult:
    """Check if bid/ask spread is reasonable."""
    # Implementation from DESIGN.md
    pass
```

**Estimated Time:** 20 minutes  
**Verification:** Function correctly calculates spread percentage

### Task 2.3: Add Liquidity Gate
- [ ] In `services/dispatcher/risk/gates.py`
- [ ] Implement `check_option_liquidity()` function (see DESIGN.md section 3)
- [ ] Test with various volume/OI combinations
- [ ] Verify reason strings are clear

**Code Template:**
```python
def check_option_liquidity(
    volume: int,
    open_interest: int,
    config: Dict[str, Any]
) -> GateResult:
    """Check if option has sufficient liquidity."""
    # Implementation from DESIGN.md
    pass
```

**Estimated Time:** 20 minutes  
**Verification:** Function checks both volume AND open interest

### Task 2.4: Update evaluate_all_gates()
- [ ] In `services/dispatcher/risk/gates.py`
- [ ] Add `option_contract` parameter to function signature
- [ ] Add conditional check for `instrument in ('CALL', 'PUT')`
- [ ] Call three new gate functions when option detected
- [ ] Add results to gates dictionary
- [ ] Test with stock vs option recommendations

**Modification:**
```python
def evaluate_all_gates(
    recommendation: Dict[str, Any],
    bar: Optional[Dict[str, Any]],
    features: Optional[Dict[str, Any]],
    # ... existing parameters ...
    option_contract: Optional[Dict[str, Any]] = None  # NEW
) -> Tuple[bool, Dict[str, Any]]:
    # ... existing code ...
    
    # NEW: Options-specific gates
    if instrument in ('CALL', 'PUT') and option_contract:
        gates['iv_percentile'] = check_iv_percentile(...)
        gates['bid_ask_spread'] = check_bid_ask_spread(...)
        gates['option_liquidity'] = check_option_liquidity(...)
```

**Estimated Time:** 20 minutes  
**Verification:** Options gates only run for CALL/PUT, not for STOCK

---

## Phase 3: Integrate with Dispatcher (1.5 hours)

### Task 3.1: Add IV Data Collection
- [ ] Open `services/dispatcher/alpaca/options.py`
- [ ] Add import: `import psycopg2`
- [ ] Implement `store_iv_surface_data()` function (see DESIGN.md section 6)
- [ ] Add call site in `get_option_chain_for_strategy()`
- [ ] Test with live Alpaca API call

**Code Location:**
```python
# In get_option_chain_for_strategy() after fetching contracts:
for contract in contracts:
    # Store for IV history
    store_iv_surface_data(contract, db_config)
```

**Estimated Time:** 45 minutes  
**Verification:** IV data being inserted into iv_surface table

### Task 3.2: Update Dispatcher Integration
- [ ] Open `services/dispatcher/alpaca/broker.py`
- [ ] In `_execute_option()` method, add gate evaluation
- [ ] Import: `from risk.gates import evaluate_all_gates`
- [ ] Call `evaluate_all_gates()` with option_contract parameter
- [ ] Check if gates pass, fallback to simulation if fail
- [ ] Log detailed failure reasons

**Code Location:**
```python
def _execute_option(self, ...):
    # After getting best_contract...
    
    # NEW: Evaluate options gates
    all_passed, gate_results = evaluate_all_gates(
        recommendation=recommendation,
        bar=bar,
        features=features,
        # ... existing params ...
        option_contract=best_contract  # NEW
    )
    
    if not all_passed:
        # Log and fallback
        failed_gates = [name for name, r in gate_results.items() if not r['passed']]
        return self._simulate_execution(..., reason=f"Gates failed: {failed_gates}")
```

**Estimated Time:** 45 minutes  
**Verification:** Dispatcher rejects options that fail gates

---

## Phase 4: Testing (1.5 hours)

### Task 4.1: Unit Tests
- [ ] Create `tests/test_options_gates.py`
- [ ] Write test for IV percentile gate (high IV rejection)
- [ ] Write test for spread gate (wide spread rejection)
- [ ] Write test for liquidity gate (low volume rejection)
- [ ] Write test for liquidity gate (low OI rejection)
- [ ] Write test for all gates passing
- [ ] Run tests: `python -m pytest tests/test_options_gates.py -v`

**Test Template:**
```python
import pytest
from services.dispatcher.risk.gates import check_iv_percentile

def test_iv_percentile_high():
    """Test IV percentile gate rejects high IV"""
    passed, reason, observed, threshold = check_iv_percentile(
        ticker="SPY",
        strike=600.0,
        expiration="2026-02-15",
        current_iv=0.95,  # Very high
        config={'max_iv_percentile': 80}
    )
    assert not passed
    assert observed > 80
```

**Estimated Time:** 1 hour  
**Verification:** All unit tests pass

### Task 4.2: Integration Test
- [ ] Create test script `scripts/test_options_gates_integration.py`
- [ ] Mock option contract with bad characteristics
- [ ] Call dispatcher._execute_option()
- [ ] Verify it falls back to simulation
- [ ] Verify reason mentions gate failure
- [ ] Test with good option (should execute)

**Estimated Time:** 30 minutes  
**Verification:** Integration test passes

---

## Phase 5: Deployment (45 min)

### Task 5.1: Build and Deploy Dispatcher
- [ ] Navigate to dispatcher directory:
  ```bash
  cd services/dispatcher
  ```
- [ ] Build Docker image:
  ```bash
  docker build --no-cache -t dispatcher .
  ```
- [ ] Tag for ECR:
  ```bash
  docker tag dispatcher:latest 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/dispatcher:latest
  ```
- [ ] Login to ECR:
  ```bash
  aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin 160027201036.dkr.ecr.us-west-2.amazonaws.com
  ```
- [ ] Push to ECR:
  ```bash
  docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/dispatcher:latest
  ```
- [ ] Get new image digest:
  ```bash
  aws ecr describe-images --repository-name ops-pipeline/dispatcher --region us-west-2 --query 'sort_by(imageDetails,& imagePushedAt)[-1].imageDigest' --output text
  ```
- [ ] Update `deploy/dispatcher-task-definition.json` with new digest
- [ ] Register new task definition:
  ```bash
  aws ecs register-task-definition --cli-input-json file://deploy/dispatcher-task-definition.json --region us-west-2
  ```
- [ ] ECS will automatically pick up new revision

**Estimated Time:** 30 minutes  
**Verification:** New dispatcher revision running

### Task 5.2: Deploy Tiny Dispatcher
- [ ] Repeat same steps for tiny dispatcher
- [ ] Use `deploy/dispatcher-task-definition-tiny.json`
- [ ] Verify both dispatchers updated

**Estimated Time:** 15 minutes  
**Verification:** Both dispatchers on latest revision

---

## Phase 6: Verification & Monitoring (30 min)

### Task 6.1: Verify Gates Are Active
- [ ] Wait for next options signal
- [ ] Check dispatcher logs:
  ```bash
  aws logs tail /ecs/ops-pipeline/dispatcher --region us-west-2 --since 5m --follow
  ```
- [ ] Look for gate evaluation messages
- [ ] Verify options gates run for CALL/PUT
- [ ] Verify they DON'T run for STOCK

**Estimated Time:** 15 minutes  
**Verification:** Logs show gate evaluations

### Task 6.2: Test with Live Data
- [ ] Create test recommendation for option with:
  - High IV (should be rejected)
  - Wide spread (should be rejected)
  - Low volume (should be rejected)
- [ ] Check dispatcher rejects all three
- [ ] Create test with good option (should execute)
- [ ] Verify execution reaches Alpaca

**Estimated Time:** 15 minutes  
**Verification:** Gates correctly filter bad options

---

## Phase 7: Documentation & Monitoring (30 min)

### Task 7.1: Update Documentation
- [ ] Update `deploy/RUNBOOK.md` with new gates
- [ ] Add section "Options-Specific Risk Gates"
- [ ] Document thresholds and how to tune
- [ ] Add troubleshooting for common gate failures

**Estimated Time:** 15 minutes  
**Verification:** Documentation complete

### Task 7.2: Set Up Monitoring Query
- [ ] Create `scripts/monitor_options_gates.sql`:
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
- [ ] Run weekly to monitor effectiveness
- [ ] Adjust thresholds based on results

**Estimated Time:** 15 minutes  
**Verification:** Monitoring query ready

---

## ✅ Final Checklist

### Code Quality
- [ ] All functions have docstrings
- [ ] Type hints on all function parameters
- [ ] Error handling for edge cases
- [ ] Logging at appropriate levels
- [ ] No hardcoded values (use config)

### Testing
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing with live data complete
- [ ] Edge cases tested (bid=0, no IV history, etc.)

### Deployment
- [ ] Both dispatchers deployed successfully
- [ ] Configuration file updated
- [ ] No errors in ECS logs
- [ ] Gates running for options only

### Documentation
- [ ] RUNBOOK.md updated
- [ ] Monitoring queries created
- [ ] Code comments added
- [ ] Commit messages follow convention

### Verification
- [ ] Options with high IV rejected
- [ ] Options with wide spreads rejected
- [ ] Options with low liquidity rejected
- [ ] Good options execute successfully
- [ ] Stock trades unaffected

---

## 🎯 Success Criteria

Phase 18 is complete when:

1. ✅ All three gates implemented and tested
2. ✅ Gates only apply to options (not stocks)
3. ✅ IV percentile calculated from 30-day history
4. ✅ Spread check uses real-time bid/ask
5. ✅ Liquidity check validates volume + OI
6. ✅ Failed trades log detailed reasons
7. ✅ Configuration validated
8. ✅ Unit tests cover all gate logic
9. ✅ Integration test proves gates block bad options
10. ✅ Documentation updated

---

## 🚨 Troubleshooting

### Issue: IV gate always fails
- Check if `iv_surface` has data: `SELECT COUNT(*) FROM iv_surface;`
- Verify 30 days of history exists for ticker/strike
- Check cache TTL (5 minutes)
- Fallback: System uses static IV > 1.0 threshold

### Issue: All options rejected
- Check thresholds in `config/trading_params.json`
- May be too restrictive for current market
- Try: `max_iv_percentile: 90`, `max_bid_ask_spread_pct: 15.0`

### Issue: Gates not running
- Verify dispatcher on latest revision
- Check if option_contract being passed to evaluate_all_gates()
- Look for error logs in dispatcher

### Issue: Performance slow
- Check IV cache is working (< 50ms per gate)
- Verify database index on iv_surface
- Consider increasing cache TTL

---

## 📊 Post-Deployment Monitoring

### Week 1: Watch gate hit rates
```bash
# Run monitoring query daily
python3 scripts/query_db.py < scripts/monitor_options_gates.sql
```

### Week 2-4: Tune thresholds
- If too many blocks: Relax thresholds
- If bad trades: Tighten thresholds
- Target: Block 10-20% of options signals

### Ongoing: False positive analysis
- Review blocked trades that would have been profitable
- Adjust thresholds quarterly based on results

---

**Phase 18 Complete!** 🎉  
**Next:** Phase 19 - Market Data Streaming (HIGH priority)

**Total Time Invested:** 3-4 hours (refactoring existing code)  
**Impact:** Better code organization, unified framework, restored proper volume threshold  
**Note:** Options safety gates were already working (Phase 3-4), now just better organized!
