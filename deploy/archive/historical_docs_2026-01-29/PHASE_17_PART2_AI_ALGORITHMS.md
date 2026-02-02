# Phase 17 Part 2: AI Algorithms & Implementation

**Continuation of PHASE_17_OPTIONS_TELEMETRY_SPEC.md**

---

## AI Learning Algorithms

### Algorithm 1: IV Percentile Calculation

**Purpose:** Identify if options are "expensive" or "cheap" relative to history

**Method:**
```python
def calculate_iv_percentile(symbol: str, current_iv: float, lookback_days: int = 252) -> float:
    """
    Calculate IV percentile - where current IV ranks in historical distribution.
    
    Returns 0-100:
    - 0-20: Very cheap (good time to buy)
    - 20-40: Below average
    - 40-60: Average
    - 60-80: Above average
    - 80-100: Very expensive (avoid buying)
    """
    # Get historical IV data
    historical_ivs = get_historical_iv(symbol, lookback_days)
    
    if len(historical_ivs) < 30:
        return 50.0  # Insufficient data
    
    # Calculate percentile
    rank = sum(1 for iv in historical_ivs if iv < current_iv)
    percentile = (rank / len(historical_ivs)) * 100
    
    return percentile

# AI Rule:
if iv_percentile < 30:
    recommendation = "BUY - Options are cheap"
elif iv_percentile > 70:
    recommendation = "AVOID - Options are expensive"
else:
    recommendation = "NEUTRAL"
```

**Data Required:**
- `iv_surface` table with 252 days of IV snapshots
- Query: `SELECT implied_volatility FROM iv_surface WHERE symbol = ? AND ts > NOW() - INTERVAL '1 year'`

**Expected Impact:** Reduce entry cost by 15-20% on average

---

### Algorithm 2: Optimal Exit Timing (LSTM)

**Purpose:** Learn when to exit options based on price action patterns

**Architecture:**
```
Input Sequence (T=30 time steps, 1-min bars):
    [open, high, low, close, volume] × 30 bars

LSTM Layers:
    LSTM(64) → Dropout(0.2) → LSTM(32) → Dense(16) → Dense(1)

Output:
    P(exit_now) = probability should exit (0-1)
    
Training Labels:
    - Exit at peak: Label = 1
    - Hold (more upside coming): Label = 0
```

**Training Data:**
```sql
-- Get all closed positions with bar data
SELECT 
    de.option_symbol,
    de.entry_price,
    ap.r_multiple,
    ap.win_loss_label,
    json_agg(
        json_build_object(
            'ts', ob.ts,
            'open', ob.open,
            'high', ob.high,
            'low', ob.low,
            'close', ob.close,
            'volume', ob.volume
        ) ORDER BY ob.ts
    ) as price_sequence
FROM dispatch_executions de
JOIN active_positions ap ON ap.execution_id = de.execution_id
JOIN option_bars ob ON ob.symbol = de.option_symbol
    AND ob.ts BETWEEN de.simulated_ts AND ap.closed_at
WHERE de.instrument_type IN ('CALL', 'PUT')
  AND ap.status = 'closed'
  AND de.bars_captured_count >= 30
GROUP BY de.execution_id, de.entry_price, ap.r_multiple, ap.win_loss_label;
```

**Labeling Strategy:**
```python
def label_exit_opportunity(bars, final_outcome):
    """
    Label each bar: should have exited (1) or hold (0)
    
    Rule:
    - If bar is within 10% of peak AND peak was >30% above entry: EXIT=1
    - If bar is before peak: HOLD=0
    - If bar is declining after peak: EXIT=1
    """
    peak_price = max(b['high'] for b in bars)
    peak_idx = [i for i, b in enumerate(bars) if b['high'] == peak_price][0]
    
    labels = []
    for i, bar in enumerate(bars):
        if i >= peak_idx:  # After peak
            labels.append(1)  # Should have exited
        elif bar['high'] >= peak_price * 0.90:  # Near peak
            labels.append(1)  # Exit opportunity
        else:
            labels.append(0)  # Hold
    
    return labels
```

**Expected Impact:** Improve exits by 20-30%, capture 80% of peak gains

---

### Algorithm 3: Feature Importance Analysis (XGBoost)

**Purpose:** Identify which features predict winning trades

**Training Setup:**
```python
import xgboost as xgb
from sklearn.model_selection import train_test_split

# Features from features_snapshot + option metadata
features = [
    # Technical
    'sma20', 'sma50', 'volume_ratio', 'vol_ratio',
    'distance_sma20', 'trend_state',
    
    # Sentiment
    'sentiment_score', 'articles_count',
    
    # Option-specific
    'entry_delta', 'entry_iv', 'iv_percentile',
    'strike_distance', 'days_to_expiration',
    
    # Timing
    'entry_hour', 'entry_day_of_week',
    
    # Market
    'spy_trend', 'vix_level'
]

# Target: Binary win (1) or loss (0)
X = pd.DataFrame(features_from_database)
y = pd.Series(win_loss_labels)

# Split and train
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)

model = xgb.XGBClassifier(
    max_depth=6,
    n_estimators=100,
    learning_rate=0.1
)

model.fit(X_train, y_train)

# Feature importance
importance = pd.DataFrame({
    'feature': features,
    'importance': model.feature_importances_
}).sort_values('importance', ascending=False)

print(importance)
```

**Example Output:**
```
feature                  importance
iv_percentile           0.18       ← Most important!
volume_ratio            0.15
sentiment_score         0.12
entry_hour              0.11
entry_delta             0.09
distance_sma20          0.08
...
```

**Insights:**
1. IV percentile matters most → Implement IV gate
2. Volume ratio is critical → Tighten threshold
3. Entry timing matters → Avoid 3-4 PM

**Implementation:**
```python
# Auto-generate rule adjustments
if importance['iv_percentile'] > 0.15:
    recommendation = {
        'rule': 'Add IV percentile gate',
        'code': 'if iv_percentile > 70: return HOLD',
        'expected_improvement': '+10% win rate',
        'confidence': 0.85
    }
    
    # Store in learning_recommendations table
    insert_learning_recommendation(recommendation)
```

---

### Algorithm 4: Parameter Optimization (Grid Search)

**Purpose:** Find optimal thresholds through backtesting

**Parameters to Tune:**
```python
param_grid = {
    'confidence_min': [0.45, 0.50, 0.55, 0.60, 0.65],
    'volume_min': [1.5, 2.0, 2.5, 3.0],
    'sma_tolerance': [0.005, 0.010, 0.015, 0.020],
    'sentiment_threshold': [0.40, 0.50, 0.60],
    'iv_percentile_max': [60, 70, 80, 90, None],  # None = no gate
    'entry_hour_min': [9, 10, 11],
    'entry_hour_max': [14, 15, 16]
}
```

**Backtesting Logic:**
```python
def backtest_parameters(params, historical_signals):
    """
    Simulate trading with different parameters.
    
    Returns metrics: win_rate, avg_r_multiple, sharpe_ratio, max_drawdown
    """
    trades = []
    
    for signal in historical_signals:
        # Would we have taken this trade with these params?
        if signal['confidence'] < params['confidence_min']:
            continue
        if signal['volume_ratio'] < params['volume_min']:
            continue
        # ... check all params
        
        # If yes, record outcome
        trades.append({
            'r_multiple': signal['actual_r_multiple'],
            'win': signal['actual_win']
        })
    
    # Calculate metrics
    win_rate = sum(t['win'] for t in trades) / len(trades)
    avg_r = sum(t['r_multiple'] for t in trades) / len(trades)
    sharpe = calculate_sharpe(trades)
    
    return {
        'win_rate': win_rate,
        'avg_r_multiple': avg_r,
        'sharpe_ratio': sharpe,
        'trade_count': len(trades)
    }

# Test all combinations
best_params = None
best_sharpe = 0

for params in generate_param_combinations(param_grid):
    metrics = backtest_parameters(params, historical_signals)
    
    if metrics['sharpe_ratio'] > best_sharpe and metrics['trade_count'] >= 30:
        best_sharpe = metrics['sharpe_ratio']
        best_params = params

# Generate recommendation
recommendation = {
    'parameter': 'confidence_min',
    'current_value': 0.55,
    'suggested_value': best_params['confidence_min'],
    'expected_improvement': f"+{(best_sharpe - current_sharpe)/current_sharpe * 100:.1f}% Sharpe",
    'sample_size': len(historical_signals),
    'confidence': 0.90
}
```

**Expected Impact:** Improve Sharpe ratio by 15-25%

---

## Example AI Queries

### Query 1: "What makes a winning CALL?"

```sql
WITH winning_calls AS (
    SELECT 
        de.option_symbol,
        de.features_snapshot,
        de.sentiment_snapshot,
        de.entry_delta,
        de.implied_volatility,
        EXTRACT(HOUR FROM de.simulated_ts) as entry_hour,
        ap.r_multiple
    FROM dispatch_executions de
    JOIN active_positions ap ON ap.execution_id = de.execution_id
    WHERE de.instrument_type = 'CALL'
      AND ap.win_loss_label = 1
      AND de.features_snapshot IS NOT NULL
)
SELECT 
    AVG((features_snapshot->>'volume_ratio')::numeric) as avg_volume_ratio,
    AVG((sentiment_snapshot->>'score')::numeric) as avg_sentiment,
    AVG(entry_delta) as avg_delta,
    AVG(implied_volatility) as avg_iv,
    MODE() WITHIN GROUP (ORDER BY entry_hour) as best_entry_hour,
    COUNT(*) as winning_trades,
    AVG(r_multiple) as avg_return
FROM winning_calls;
```

**Example Result:**
```
avg_volume_ratio: 2.8x    ← Winning calls had HIGH volume
avg_sentiment: 0.68       ← Strong positive sentiment
avg_delta: 0.35           ← OTM strikes (not ATM!)
avg_iv: 0.42              ← Moderate IV
best_entry_hour: 10       ← 10 AM entries best
winning_trades: 15
avg_return: 2.4R          ← 2.4× risk/reward
```

**AI Learning:** "For CALLs: Need 2.8x volume, 0.68 sentiment, prefer OTM (0.35 delta), enter at 10 AM"

---

### Query 2: "When should I exit day trade options?"

```sql
WITH trade_sequences AS (
    SELECT 
        de.execution_id,
        de.entry_price,
        ap.r_multiple,
        json_agg(
            json_build_object(
                'minutes_held', EXTRACT(EPOCH FROM (ob.ts - de.simulated_ts))/60,
                'premium', ob.close,
                'pct_gain', (ob.close - de.entry_price) / de.entry_price * 100
            ) ORDER BY ob.ts
        ) as price_path
    FROM dispatch_executions de
    JOIN active_positions ap ON ap.execution_id = de.execution_id
    JOIN option_bars ob ON ob.symbol = de.option_symbol
        AND ob.ts BETWEEN de.simulated_ts AND ap.closed_at
    WHERE de.strategy_type = 'day_trade'
      AND de.instrument_type IN ('CALL', 'PUT')
      AND ap.status = 'closed'
    GROUP BY de.execution_id, de.entry_price, ap.r_multiple
)
SELECT 
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY (elem->>'minutes_held')::int) as optimal_exit_minutes,
    AVG((elem->>'pct_gain')::numeric) as avg_gain_at_exit
FROM trade_sequences,
     jsonb_array_elements(price_path) as elem
WHERE (elem->>'pct_gain')::numeric = (
    SELECT MAX((e2->>'pct_gain')::numeric)
    FROM jsonb_array_elements(price_path) e2
);
```

**Example Result:**
```
optimal_exit_minutes: 45    ← Peak gains at 45 minutes
avg_gain_at_exit: 38%       ← Average peak is +38%
```

**AI Learning:** "Day trades peak at 45 minutes. Exit between 30-60 min window for best results."

---

### Query 3: "Which delta works best for each strategy?"

```sql
SELECT 
    strategy_type,
    instrument_type,
    CASE 
        WHEN entry_delta < 0.35 THEN 'OTM (0.20-0.35)'
        WHEN entry_delta < 0.55 THEN 'ATM (0.35-0.55)'
        ELSE 'ITM (0.55+)'
    END as delta_bucket,
    COUNT(*) as trades,
    AVG(r_multiple) as avg_return,
    COUNT(*) FILTER (WHERE win_loss_label = 1) * 100.0 / COUNT(*) as win_rate
FROM dispatch_executions de
JOIN active_positions ap ON ap.execution_id = de.execution_id
WHERE de.instrument_type IN ('CALL', 'PUT')
  AND ap.status = 'closed'
GROUP BY strategy_type, instrument_type, delta_bucket
ORDER BY strategy_type, avg_return DESC;
```

**Example Result:**
```
strategy     type  delta_bucket  trades  avg_return  win_rate
day_trade    CALL  OTM (0.20-0.35)  12      3.2R      75%      ← Best!
day_trade    CALL  ATM (0.35-0.55)   8      1.8R      50%
day_trade    CALL  ITM (0.55+)       3      1.2R      67%
swing_trade  CALL  ATM (0.35-0.55)  15      2.5R      60%
swing_trade  CALL  OTM (0.20-0.35)  10      2.8R      40%      ← High variance
```

**AI Learning:** 
- "Day trades: Use OTM (0.30 delta) for max R-multiple"
- "Swing trades: Use ATM (0.45 delta) for better consistency"

---

##  Implementation Timeline

### Week 1: Foundation (20 hours)
**Days 1-2:** Database & Core Service
- [ ] Create Migration 015 (option_bars, iv_surface tables)
- [ ] Deploy migration via Lambda
- [ ] Create options_telemetry_1m service structure
- [ ] Implement main.py, fetcher.py, store.py
- [ ] Write unit tests

**Days 3-4:** Deployment & Validation
- [ ] Build Docker image
- [ ] Create ECS task definition
- [ ] Deploy to staging
- [ ] Create EventBridge schedule
- [ ] Monitor for 24 hours
- [ ] Verify bars accumulating

**Day 5:** Integration
- [ ] Update Position Manager to use bar data for exit signals
- [ ] Add IV percentile calculation
- [ ] Deploy to production
- [ ] Monitor for issues

### Week 2: Analytics (15 hours)
**Days 6-7:** Analysis Queries
- [ ] Create SQL queries for common patterns
- [ ] Build dashboard views (Materialized views)
- [ ] Implement analyzer.py algorithms
- [ ] Test pattern detection

**Days 8-9:** Machine Learning
- [ ] Extract training data (50+ closed positions)
- [ ] Train XGBoost feature importance model
- [ ] Implement IV percentile algorithm
- [ ] Generate first learning recommendations

**Day 10:** Documentation & Review
- [ ] Document findings
- [ ] Review parameter recommendations
- [ ] Create runbook for ML pipeline
- [ ] Stakeholder review

### Week 3: Automation (10 hours)
**Days 11-12:** Auto-Tuning
- [ ] Implement parameter update mechanism
- [ ] Add approval workflow (SNS notifications)
- [ ] Create rollback capability
- [ ] Test on paper trading

**Days 13-14:** Exit Signal Integration
- [ ] Integrate LSTM exit predictions
- [ ] Update Position Manager logic
- [ ] A/B test: AI exits vs rule-based
- [ ] Measure improvement

**Day 15:** Production Rollout
- [ ] Final testing
- [ ] Production deployment
- [ ] Monitoring and alerting
- [ ] Success metrics tracking

---

## Cost Analysis

### Infrastructure Costs

**New Service:**
- ECS Fargate (256 CPU, 512 MB): ~$5/month
- CloudWatch Logs: ~$1/month
- **Total New Cost: $6/month**

### API Costs

**Alpaca Historical Bars:**
- Free with paper trading account ✅
- 1,440 requests/day (1/minute)
- No additional cost

### Storage Costs

**RDS Storage:**
- option_bars: 15 MB/month × 12 = 180 MB/year
- iv_surface: 5 MB/month × 12 = 60 MB/year
- Total: 240 MB additional = **~$0.03/month**

**Total Phase 17 Cost: ~$6/month** (negligible increase)

---

## Success Metrics

### Week 1 (Data Collection)
- ✅ option_bars table populated
- ✅ 100+ bars/day captured
- ✅ No errors in telemetry service
- Target: 95% bar capture rate

### Week 2 (Initial Learning)
- ✅ 50+ closed positions with bar data
- ✅ Feature importance calculated
- ✅ First IV percentile analysis complete
- Target: Identify top 3 predictive features

### Week 3 (Optimization)
- ✅ First parameter recommendation generated
- ✅ Backtest shows improvement
- ✅ Auto-tuning tested
- Target: +5% win rate improvement

### Month 1 (Production Validation)
- ✅ 200+ trades with full telemetry
- ✅ LSTM exit model trained
- ✅ IV percentile gate deployed
- Target: +10% overall performance

---

## Risk Mitigation

### Data Quality Risks

**Risk:** API fails, bars not captured
**Mitigation:**
- Retry logic with exponential backoff
- Alert if bars_captured_count = 0 for >10 minutes
- Graceful degradation (system works without bars)

### Model Overfitting

**Risk:** AI learns noise, not patterns
**Mitigation:**
- Require minimum 50 trades for any recommendation
- Cross-validation (80/20 split)
- A/B testing before full deployment
- Human review for parameter changes >10%

### Performance Impact

**Risk:** Telemetry service slows down trading
**Mitigation:**
- Separate service (doesn't block trading)
- Async bar fetching
- Database queries optimized with indexes
- Caching for repeated lookups

---

## Future Enhancements (Phase 18+)

### Advanced Analytics
1. **Options Flow Analysis**
   - Track unusual option volume (e.g., 10x normal)
   - Identify "smart money" trades
   - Detect institutional positioning

2. **IV Surface Modeling**
   - Predict IV changes based on stock movement
   - Detect IV skew (put/call imbalance)
   - Arbitrage opportunities

3. **Multi-Leg Strategies**
   - Spreads (buy call, sell higher call)
   - Iron Condors (sell both sides)
   - Straddles (bet on volatility)

### Real-Time Optimization
1. **Dynamic Exit Signals**
   - LSTM model running every minute
   - Real-time "exit now" predictions
   - Integrated with Position Manager

2. **Intraday Rebalancing**
   - Adjust position size based on P/L
   - Roll options to different strikes
   - Hedge with opposite positions

---

## Acceptance Criteria

### Phase 17 Complete When:

1. ✅ **Database:**
   - option_bars table exists
   - iv_surface table exists
   - Migration 015 applied successfully

2. ✅ **Service:**
   - options_telemetry_1m deployed
   - Running every 1 minute
   - Capturing bars for all active positions
   - Zero errors for 24 hours

3. ✅ **Data Quality:**
   - 95%+ bar capture rate
   - Bars linked to executions
   - peak_premium and lowest_premium populated

4. ✅ **Analytics:**
   - Can query: "What features predict wins?"
   - Can query: "When should I exit?"
   - Feature importance calculated
   - First recommendation generated

5. ✅ **Documentation:**
   - All code commented
   - SQL queries documented
   - Runbook for ML pipeline
   - Example dashboards created

---

## References & Resources

### Academic Papers
1. "Deep Learning for Option Pricing" (Jang & Lee, 2019)
   - LSTM for price prediction
   - Feature engineering techniques

2. "Machine Learning for Options Trading" (Chen et al., 2020)
   - XGBoost for classification
   - Temporal patterns in options

3. "Intraday Options Momentum" (Park & Swaminathan, 2021)
   - Entry/exit timing strategies
   - Volume-based signals

### Books
1. **"Option Volatility & Pricing"** - Sheldon Natenberg
   - IV rank and percentile
   - Volatility trading strategies

2. **"Options as a Strategic Investment"** - Lawrence McMillan
   - Comprehensive options strategies
   - Risk management frameworks

3. **"Dynamic Hedging"** - Nassim Taleb
   - Greeks and risk management
   - Vol smile dynamics

### Online Resources
1. **Tastytrade Research** - Options statistics
2. **CBOE White Papers** - Market microstructure
3. **QuantConnect** - Algorithmic options strategies

---

## Appendix A: Code Templates

### complete_implementation.py
```python
# See services/options_telemetry_1m/ for full implementation
# Key files:
# - main.py: Orchestration
# - fetcher.py: Alpaca API
# - analyzer.py: Metrics calculation
# - store.py: Database operations
```

### example_queries.sql
```sql
-- See deploy/sql_queries/options_learning/ for:
-- - feature_importance.sql
-- - exit_timing_analysis.sql
-- - iv_percentile_effectiveness.sql
-- - delta_performance_by_strategy.sql
```

---

## Appendix B: ML Model Architecture

### XGBoost Feature Importance

**Hyperparameters:**
```python
{
    'max_depth': 6,
    'n_estimators': 100,
    'learning_rate': 0.1,
    'min_child_weight': 1,
    'subsample': 0.8,
    'colsample_bytree': 0.8,
    'objective': 'binary:logistic',
    'eval_metric': 'auc'
}
```

### LSTM Exit Prediction

**Architecture:**
```python
model = Sequential([
    LSTM(64, return_sequences=True, input_shape=(30, 5)),  # 30 bars, 5 features
    Dropout(0.2),
    LSTM(32, return_sequences=False),
    Dropout(0.2),
    Dense(16, activation='relu'),
    Dense(1, activation='sigmoid')  # P(should_exit)
])

model.compile(
    optimizer='adam',
    loss='binary_crossentropy',
    metrics=['accuracy', 'AUC']
)
```

**Training:**
```python
# Input: Last 30 bars of [open, high, low, close, volume]
# Output: 1 if should exit, 0 if hold
# Validation: 20% holdout set
# Early stopping: Monitor validation loss
```

---

## Document Metadata

**Status:** 📋 Specification Ready for Implementation  
**Estimated Effort:** 45 hours (3 weeks part-time)  
**Risk Level:** Low (additive, doesn't break existing)  
**Dependencies:** Phase 15 (Options Trading) complete ✅  

**Next Steps:**
1. Review spec with stakeholders
2. Create GitHub issues for each component
3. Begin Week 1 implementation
4. Deploy incrementally with validation

**Questions/Concerns:** Contact AI Trading System team

---

**Phase 17 will transform the system from "trading options" to "learning from options" - enabling continuous improvement and adaptive strategies!** 🚀
