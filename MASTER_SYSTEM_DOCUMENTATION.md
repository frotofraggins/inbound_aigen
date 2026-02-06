# MASTER SYSTEM DOCUMENTATION
**Last Updated:** February 6, 2026, 15:19 UTC  
**Status:** Active Production System - Learning Mode

---

## 🎯 START HERE - Quick Status

### Current Performance:
- **Total trades:** 11 (learning phase)
- **Win rate:** 18% (2 winners, 9 losers)
- **Best winner:** GOOGL +84.4%
- **Issues:** Late entries, no trailing stops, overnight reversals

### What's Working ✅:
- All services deployed and operational
- Data capture: 100% (features + outcomes)
- Price tracking: Accurate, every minute
- Learning infrastructure: Fully functional

### Critical Fixes Needed 🚨:
1. **Trailing stops** (10 min) - Prevents +15% → -40% reversals
2. **Momentum urgency** (30 min) - Enter at breakout START
3. **Gap fade strategy** (1 hour) - Profit from overnight gaps
4. **Accumulate 39 more trades** - Enable AI auto-learning

---

## 📊 System Architecture

### Data Flow:
```
RSS News → classifier_worker (FinBERT) → sentiment
Market Data → feature_computer → technical indicators
             ↓
Sentiment + Features → signal_engine → recommendations
             ↓
Recommendations → dispatcher → Alpaca execution
             ↓
Executions → position_manager → track & close
             ↓
Closes → position_history → AI learning (future)
```

### Services Running:
1. **ticker_discovery** - Bedrock selects tickers (25-50/day)
2. **telemetry_1m** - Captures market data every minute
3. **feature_computer_1m** - Computes SMA, trend, volume
4. **classifier_worker** - FinBERT sentiment from news
5. **signal_engine_1m** - Generates trade signals
6. **dispatcher** - Executes on Alpaca (paper)
7. **position_manager** - Tracks positions, manages exits

---

## 🔧 Core Components

### Signal Generation (signal_engine_1m)
**Logic:**
- Direction: From trend + price (NOT sentiment)
- Sentiment: Confidence modifier (±20%)
- Volume: Hard gate (>1.5x required)
- Confidence: 0.65 for options

**Thresholds:**
- Confidence: 0.65 (day trade), 0.50 (swing), 0.40 (stock)
- Volume: 1.5x minimum (raised from 1.2x)
- Take profit: +80%
- Stop loss: -40%

### Position Management (position_manager)
**Monitoring:**
- Check every: 1 minute
- Track: Price, P&L, peak, low
- Auto-close at: +80%, -40%, 4 hours, 3:55 PM

**Exit Rules:**
1. Take profit: +80%
2. Stop loss: -40%
3. Max hold: 4 hours
4. Market close: 3:55 PM (ALL options)
5. Catastrophic: -50% (early exit override)
6. Trailing stops: NOT YET ENABLED (needs migration 013)

### Learning System (position_history)
**Captures:**
- Entry/exit times and prices
- P&L (dollars and percent)
- Hold duration
- Peak gains (MFE - Maximum Favorable Excursion)
- Worst drawdown (MAE - Maximum Adverse Excursion)
- Exit reason (tp, sl, time_stop, market_close_protection)
- Entry features: trend, volume, sentiment, price levels

**Current Data:** 11 trades, 100% capture rate

---

## 💡 Discovered Patterns (From Your Analysis)

### 1. Overnight Reversals ✅ FIXED
**Pattern:** Late afternoon entries → overnight gaps → morning stop losses
**Evidence:** 4 trades, 100% failure, -43% average
**Solution:** Close all options at 3:55 PM (DEPLOYED)

### 2. Peak-Then-Crash 🚨 CRITICAL
**Pattern:** Winners peak, then reverse and hit stop losses
**Evidence:** NVDA +15.7% → -40.7%, GOOGL +7.7% → -50%
**Solution:** Trailing stops (READY, needs migration 013)

### 3. Late Entry Problem
**Pattern:** Enter after breakout mature, catch tail end
**Evidence:** BAC chart shows breakout at 1:30, entry at 2:30
**Solution:** Momentum urgency (DESIGNED, needs coding)

### 4. Morning Gap Opportunities
**Pattern:** Overnight gaps fade in first hour
**Evidence:** Your CRM/BAC charts show reversals
**Solution:** Gap fade strategy (DESIGNED, needs coding)

---

## 🎓 AI/ML Usage

### Currently Active:
1. **FinBERT** - Sentiment analysis (confidence modifier)
2. **Bedrock Claude** - Ticker selection (what to watch)
3. **Bedrock Claude** - Post-trade analysis (what we missed)

### Not Yet Implemented:
- ❌ Historical performance queries
- ❌ Automated confidence adjustment
- ❌ Pattern-based learning
- ⏳ Waiting for 50 trades to implement

---

## 📁 Key Files

### Core Logic:
- `services/signal_engine_1m/rules.py` - Signal generation
- `services/position_manager/monitor.py` - Exit logic
- `services/dispatcher/alpaca_broker/broker.py` - Order execution

### Database:
- `position_history` table - Learning data (11 trades)
- `dispatch_recommendations` - Signals (1,668/day)
- `dispatch_executions` - Orders (13/day real)
- `active_positions` - Current positions (2 open)

### Scripts:
- `scripts/verify_all_fixes.py` - Complete verification
- `scripts/complete_data_audit.py` - Pipeline audit
- `scripts/apply_013_direct.py` - Enable trailing stops
- `scripts/deploy_option_price_fix.sh` - Deploy position manager

---

## 🚀 Next Steps (Priority Order)

### Immediate (Today):
1. **Enable trailing stops** - Run migration 013 & redeploy
2. **Verify working** - Check next profitable position

### This Week:
3. **Add momentum urgency** - Fast entry on volume breakouts
4. **Implement gap fade** - Morning reversal strategy
5. **Accumulate 30 more trades** - Build learning dataset

### Week 2 (After 50 Trades):
6. **Implement AI auto-adjustment** - Query-based confidence tuning
7. **Verify improvement** - Win rate should climb to 50%+

---

## 📝 Documentation Structure

**THIS FILE:** Master reference (all you need)
**GitHub:** All code changes committed (8870ba6)
**Next Steps:** NEXT_SESSION_CRITICAL_IMPROVEMENTS.md

**Archive:** Old status docs moved to `archive/` folder

---

## ✅ Verification Commands

```bash
# Check all systems
python3 scripts/verify_all_fixes.py

# Check specific position tracking
python3 scripts/check_msft_tracking.py

# Query database
python3 scripts/query_via_lambda.py

# Complete audit
python3 scripts/complete_data_audit.py
```

---

**Everything you need to know is in THIS document. Old scattered docs archived. Ready to continue improvements!**
