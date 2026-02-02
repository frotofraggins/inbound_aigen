# Phase 18: Options Risk Gates - Refactoring & Consolidation

## 🎯 Objective

**REFACTOR existing options validation code into the unified risk gates framework.**

**CRITICAL:** Options gates already exist and are working (deployed in Phase 3-4). This phase consolidates fragmented code into the standard `risk/gates.py` framework for better maintainability and observability.

### Current State
- ✅ IV validation: `validate_iv_rank()` in options.py (WORKING)
- ✅ Spread validation: in `validate_option_liquidity()` (WORKING)
- ✅ Liquidity validation: in multiple functions (WORKING)
- ⚠️ Not integrated with `evaluate_all_gates()` framework
- ⚠️ Scattered across 3+ functions

### Target State
- ✅ All validations in `risk/gates.py` (centralized)
- ✅ Integrated with `evaluate_all_gates()` (unified)
- ✅ Consistent observability with other gates
- ✅ Volume threshold restored to 100 (currently 10 for testing)

## 📋 Requirements

### Functional Requirements

#### FR-1: IV Percentile Gate
- **Description:** Reject options trades when Implied Volatility is at extreme highs
- **Rationale:** High IV = expensive options = poor risk/reward
- **Rule:** IV Percentile < 80th percentile
- **Data Source:** Historical IV from `iv_surface` table (30-day lookback)
- **Calculation:** 
  ```
  IV Percentile = (# of days with IV < current_IV) / (total days) * 100
  ```

#### FR-2: Bid/Ask Spread Gate
- **Description:** Reject options with wide bid/ask spreads
- **Rationale:** Wide spreads = illiquid = large slippage + hard to exit
- **Rule:** Spread < 10% of mid-price
- **Calculation:**
  ```
  spread_pct = ((ask - bid) / mid) * 100
  where mid = (bid + ask) / 2
  ```

#### FR-3: Liquidity Gate
- **Description:** Reject options with insufficient volume or open interest
- **Rationale:** Low liquidity = difficult execution + manipulation risk
- **Rules:**
  - Daily volume ≥ 100 contracts
  - Open interest ≥ 100 contracts
- **Data Source:** Alpaca options API response

### Non-Functional Requirements

#### NFR-1: Performance
- Gate checks must complete in < 50ms per option
- No blocking queries to database
- Use cached IV history when possible

#### NFR-2: Configurability
- All thresholds must be configurable via `config/trading_params.json`
- Default values:
  - `max_iv_percentile`: 80
  - `max_bid_ask_spread_pct`: 10.0
  - `min_option_volume`: 100
  - `min_open_interest`: 100

#### NFR-3: Observability
- Log gate results for all options evaluations
- Track gate failure reasons in `dispatch_executions.risk_json`
- Metrics: gate pass/fail rates by ticker

### Data Requirements

#### DR-1: IV Surface Table
- Already exists from migration 010
- Needs population: Store IV data from Alpaca API
- Retention: 30 days minimum for percentile calculation

#### DR-2: Options Contract Data
- Source: Alpaca `/v1beta1/options/snapshots/{ticker}` API
- Required fields:
  - `bid`, `ask` (for spread check)
  - `volume`, `open_interest` (for liquidity check)
  - `implied_volatility` (for IV check)

### Integration Points

#### IP-1: Dispatcher
- Location: `services/dispatcher/alpaca/broker.py`
- Hook: In `_execute_option()` method, before order submission
- Fallback: If gates fail, fall back to simulation mode

#### IP-2: Risk Gates Module
- Location: `services/dispatcher/risk/gates.py`
- New functions:
  - `check_iv_percentile()`
  - `check_bid_ask_spread()`
  - `check_option_liquidity()`
- Integration: Add to `evaluate_all_gates()` for options only

## 🎓 Success Criteria

1. ✅ All three gates implemented and tested
2. ✅ Gates only apply to options (not stocks)
3. ✅ IV percentile calculated from 30-day history
4. ✅ Spread check uses real-time bid/ask from Alpaca
5. ✅ Liquidity check validates volume + OI
6. ✅ Failed gate trades log detailed reasons
7. ✅ Configuration validated on service startup
8. ✅ Unit tests cover all gate logic
9. ✅ Integration test proves gates block bad options
10. ✅ Documentation updated

## 📊 Test Cases

### TC-1: IV Percentile Gate
- **Setup:** Option with IV at 90th percentile (high)
- **Expected:** Gate fails, trade rejected
- **Verify:** Logged reason mentions IV percentile

### TC-2: Bid/Ask Spread Gate
- **Setup:** Option with bid=$2.00, ask=$2.30 (13% spread)
- **Expected:** Gate fails, trade rejected
- **Verify:** Logged reason mentions wide spread

### TC-3: Liquidity Gate - Volume
- **Setup:** Option with volume=50, OI=200
- **Expected:** Gate fails (low volume)
- **Verify:** Logged reason mentions insufficient volume

### TC-4: Liquidity Gate - OI
- **Setup:** Option with volume=150, OI=80
- **Expected:** Gate fails (low OI)
- **Verify:** Logged reason mentions insufficient open interest

### TC-5: All Gates Pass
- **Setup:** Option with good IV, tight spread, high liquidity
- **Expected:** All gates pass, trade executes
- **Verify:** Order submitted to Alpaca

### TC-6: Stock Trade Bypass
- **Setup:** Stock trade (not option)
- **Expected:** Options gates skipped
- **Verify:** Stock gates apply, options gates do not

## 🔗 Dependencies

- ✅ Migration 010 (iv_surface table exists)
- ✅ Alpaca options API integration working
- ✅ Risk gates infrastructure (gates.py)
- ⏸️ Need: IV data collection (populate iv_surface)

## 📈 Metrics

Track these metrics after deployment:

1. **Gate Hit Rate**
   - IV percentile blocks: N per day
   - Spread blocks: N per day
   - Liquidity blocks: N per day

2. **False Positives**
   - Trades that were blocked but would have been profitable
   - Review weekly to tune thresholds

3. **Performance**
   - Average gate evaluation time
   - P95, P99 latencies

## 🚨 Risks

1. **Insufficient IV History**
   - **Risk:** < 30 days of IV data = inaccurate percentile
   - **Mitigation:** Fallback to static IV threshold (e.g., > 1.0 = reject)

2. **Alpaca API Latency**
   - **Risk:** Slow API = stale bid/ask data
   - **Mitigation:** 2-second timeout, use cached if available

3. **Over-Restrictive Gates**
   - **Risk:** Block too many trades, reduce opportunities
   - **Mitigation:** Monitor metrics, tune thresholds weekly

## 📚 References

- [Alpaca Options API](https://docs.alpaca.markets/reference/optionsnapshots)
- [Options Greeks Explained](https://www.investopedia.com/terms/g/greeks.asp)
- [IV Rank vs IV Percentile](https://www.tastytrade.com/definitions/iv-rank)
- Current implementation: `services/signal_engine_1m/rules.py` (line ~500 comments)

---

**Priority:** MEDIUM (was HIGH) - Refactoring for code quality, gates already work  
**Estimated Effort:** 3-4 hours (refactoring) vs. 4-6 hours (building from scratch)  
**Dependencies:** Existing validation code in options.py, Migration 010, Alpaca API  
**Type:** Code refactoring & consolidation (NOT new feature)  
**Owner:** Next agent/developer

**Note:** See CURRENT_STATE.md for detailed analysis of existing vs. target state.
