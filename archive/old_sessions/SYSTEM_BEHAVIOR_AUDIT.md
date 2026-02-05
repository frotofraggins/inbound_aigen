# System Behavior Audit (Current State)
Date: 2026-02-02
Scope: Describe what the system does today (no redesign, no new features)

---

## 0) Executive Summary (Plain English)

This system is a **rule‑based, options‑focused trading pipeline** built around 1‑minute telemetry and short‑horizon signals. It ingests news, computes technical features, scores a watchlist, generates trade recommendations, runs them through risk gates, and executes either real paper orders (Alpaca paper) or simulated fallbacks. Positions are then monitored and closed by a dedicated position manager using explicit stop/take‑profit and time‑based exit rules.

It is **deterministic** given inputs: the same telemetry + sentiment produces the same signal. “Statistical” components exist (FinBERT sentiment, volatility computation, IV rank), but they are used in **hard‑coded rules** rather than learned models. The system is **partially adaptive** (tier‑based sizing, adaptive confidence threshold, volume multipliers), but it is not fully quant/ML‑driven yet.

---

## 1) What Data the System Collects

### Market/Price Data
- **lane_telemetry**: 1‑minute OHLCV candles per ticker (Alpaca or yfinance).
- **lane_features** / **lane_features_clean** view: computed features (SMA20/50, vol ratios, distance to SMA, trend_state, volume ratio, etc.).
- **option_bars**: option OHLCV bars captured for open option positions (learning/analytics).

### News/Sentiment Data
- **inbound_events_raw**: raw RSS news items.
- **inbound_events_classified**: FinBERT sentiment + extracted tickers.
- **feed_state**: RSS feed metadata (etag, last_modified, last_seen_published).

### Trading/Execution Data
- **dispatch_recommendations**: actionable signals only (HOLD signals are *not* stored).
- **dispatch_executions**: execution ledger (simulated or paper), includes options metadata.
- **dispatcher_runs**: run‑level metrics for the dispatcher.
- **active_positions**: open positions tracked by position manager.
- **position_events**: detailed audit trail of position updates, exits, partial fills.
- **account_activities**: Alpaca account activities (fills, exercises, etc.).

### Learning/Analytics Tables (mostly data capture, not decision drivers yet)
- **iv_history**: historical implied volatility samples per ticker.
- **ticker_universe**: AI‑recommended ticker list (Bedrock Sonnet).
- **missed_opportunities**: AI analysis of skipped volume surges.
- **learning_recommendations**: model‑generated parameter suggestions (not auto‑applied).
- **position_history** (schema columns for MAE/MFE, R‑multiple, exit reasons; not fully populated by current code paths).

---

## 2) What Decisions are Rule‑Based vs Statistical vs Adaptive

### Rule‑Based (Deterministic)
- Signal direction from **price vs SMA20 + trend_state**.
- Breakout confirmation: **distance_sma20 must exceed ±1%**.
- Volume confirmation: **hard gate** at volume_ratio < 0.5.
- Confidence thresholds: fixed per strategy type (day vs swing vs stock).
- Trading hours gate: block open/close windows and outside market hours.
- Risk gates: cooldown, max trades per ticker, max positions, max exposure, daily loss limit.
- Option exits: +50% profit / −25% loss / theta decay / expiration risk.
- Trailing stop: lock 75% of peak gains.

### Statistical (but used in rules)
- **FinBERT sentiment** (ProsusAI/finbert) → aggregated and used as a **confidence multiplier**.
- **Volatility** as stddev of returns → used in vol_ratio and confidence weighting.
- **IV rank** (when history exists) → used as a trade filter in options selection.
- **Kelly sizing** (only if ≥20 historical trades in ai_option_trades).

### Fixed Thresholds (hard‑coded in code/config)
- Volume kill: **< 0.5x** = hold.
- Breakout threshold: **1% from SMA20**.
- Confidence min (options day/swing/stock): **0.60 / 0.45 / 0.35** (defaults; dispatcher overrides possible).
- Trading hours: **9:30–16:00 ET**, block **9:30–9:35** and **15:45–16:00**.
- Options liquidity: **spread ≤ 10%**, **min premium $0.30**, **min volume** (default 10 in code).
- Option exits: **+50% / −25%**.
- Default max hold: **240 minutes**.

### Adaptive / Dynamic
- **Adaptive confidence**: raises required confidence when vol_ratio > 1.2.
- **Volume multiplier**: scales confidence by volume_ratio bands.
- **Sentiment weight**: boost/penalty scaled by sentiment strength and news count.
- **Account tier sizing**: risk % and max contracts depend on buying power tiers.
- **Paper training overrides**: can ignore buying power and override risk tier caps.

---

## 3) Current Behavior by System Area

### SIGNALS
**Entry decision**
1. Pull top 30 watchlist tickers (watchlist engine).
2. For each ticker, load latest features + recent sentiment (last 30 min).
3. Compute signal with deterministic rules:
   - Direction: price vs SMA20 + trend_state.
   - Breakout confirmation (±1% from SMA20).
   - Volume gate (volume_ratio).
   - Base confidence from trend, setup quality, vol appropriateness.
   - Sentiment scales confidence (not a gate).
4. If confidence < threshold → HOLD (HOLD is *not* stored).
5. If actionable, store recommendation with feature/sentiment snapshots.

**Most important features**
- distance_sma20, trend_state
- vol_ratio (volatility regime)
- volume_ratio (hard gate)
- sentiment_score & news_count (confidence scalar)

**Deterministic or probabilistic?**
- Deterministic: given the same features/sentiment, the signal output is the same.

### RISK (Dispatcher Gates)
- Confidence gate (instrument‑aware).
- Action allowed (BUY_CALL/BUY_PUT/BUY_STOCK; SELL_STOCK optional).
- Recommendation freshness (default 5 min).
- Bar and feature freshness (default 120s / 300s).
- Ticker daily trade limit + cooldown.
- Shorting gate (SELL_STOCK only if open position unless allow_shorting).
- Account‑level kill switches: max daily loss, max positions, max exposure.
- Trading hours gate (open/close windows).

### EXITS (Position Manager)
- Stop loss / take profit (ATR‑based from compute_stops).
- Options‑specific exits: +50% profit, −25% loss, theta decay, expiry risk.
- Trailing stop: locks 75% of peak gains.
- Day‑trade time exit at 3:55 PM ET.
- Max hold time (default 240 minutes).
- Missing bracket orders → forced close.
- Partial exits: 50% off at +50%, another 25% at +75%.

### SIZING
- **Stocks (sim path)**: risk‑based sizing using paper_equity and stop distance.
- **Options (paper path)**:
  - Tier‑based sizing (risk % by account tier, max contracts cap).
  - Kelly sizing if sufficient history (≥20 trades).
  - Paper override can ignore buying power.

### OPTIONS LOGIC
- Contracts from Alpaca options snapshots.
- Strategy maps to DTE:
  - day_trade: 0‑1 DTE
  - swing_trade: 7‑30 DTE
- Strike selection by quality score:
  - Spread tightness, volume, delta, strike proximity (score ≥ 40).
- Liquidity checks:
  - Spread ≤ 10%, premium ≥ $0.30, volume ≥ min.
- IV rank filter (if history exists; allow if insufficient history).
- Orders are market orders (no brackets in options execution).

### STATISTICS
- Stored: feature snapshots, sentiment snapshots, account activities, option bars, iv_history.
- Used in decisions today:
  - Sentiment (FinBERT) → confidence scaler.
  - vol_ratio → confidence + options/stock decision.
  - volume_ratio → hard gate + confidence scaling.
  - IV rank → option filter (if history exists).
  - Kelly sizing (if historical stats available).
- Logged but not currently decision‑making:
  - missed_opportunities analysis, learning_recommendations, many views.

---

## 4) What the System Does NOT Measure (Blind Spots)

### Missing or incomplete observability
- **MAE/MFE tracking** exists in schema but not populated by code paths reviewed.
- **Holding‑time stats** (position_history) not clearly populated.
- **True daily P&L**: daily_pnl is hard‑coded to 0.0 in dispatcher account state.
- **Execution quality**: no systematic slippage/price improvement attribution.
- **Option‑specific metrics**: IV rank coverage depends on iv_history; may be sparse.
- **Order lifecycle audit**: limited tracking of partial fills beyond position events.
- **No consistent per‑ticker baseline stats** (ATR distributions, typical moves).
- **No systematic drawdown/Sharpe tracking** in live loop.

### Areas where decisions are made “blind”
- Signals assume volume data is present and accurate; missing volume yields conservative hold.
- Options selection uses snapshots without open interest (OI) unless using /contracts endpoint.
- Position sizing is not constrained by realized drawdown or account‑level P&L.

---

## 5) Deterministic vs Statistical Table

| Component | Deterministic? | Statistical? | Notes |
|---|---|---|---|
| Signal rules | Yes | No | Hard‑coded thresholds + feature rules |
| Sentiment classifier | No | Yes | FinBERT model output used as scaler |
| Volatility | Yes (computed) | Yes | Stddev of returns |
| Watchlist scoring | Yes | Mild | Weighted scoring using sentiment + technicals |
| Option selection | Yes | Mild | Score‑based deterministic selection |
| Kelly sizing | Yes (deterministic calc) | Yes | Only if history exists |
| Risk gates | Yes | No | Strict rule checks |
| Exits | Yes | No | Fixed rules |

---

## 6) Decision Flow Diagram

```
[RSS feeds] -> inbound_events_raw
      |-> classifier_worker -> inbound_events_classified

[telemetry_ingestor_1m] -> lane_telemetry
      |-> feature_computer_1m -> lane_features_clean

[watchlist_engine_5m]
      |-> watchlist_state (top 30)

[signal_engine_1m]
      |-> uses watchlist + lane_features + sentiment
      |-> compute_signal() -> actionable recommendations only
      |-> dispatch_recommendations (PENDING)

[dispatcher]
      |-> claim PENDING (idempotent)
      |-> risk gates + freshness + trading hours
      |-> execution:
          - SIMULATED broker OR
          - Alpaca paper broker (real paper)
      |-> dispatch_executions (ledger)

[trade_stream]
      |-> Alpaca WebSocket + account activities
      |-> active_positions + account_activities

[position_manager]
      |-> monitor + exit rules
      |-> force_close via Alpaca API
```

---

## 7) Classification of the System Type

**Type:** Rule‑based / heuristic system with statistical inputs and limited adaptive controls.

**Why:**
- Decisions are made by deterministic rules and thresholds.
- Statistical models (FinBERT, IV rank) are inputs, not learned policies.
- Adaptivity is limited to simple scaling (volume multipliers, adaptive confidence).

This is **not** a fully quant or ML trading system yet.

---

## 8) Readiness Score for Professional Trading (0–100)

**Score: 62 / 100**

**Reasoning**
- **+** End‑to‑end pipeline exists (data → signals → execution → exits).
- **+** Explicit risk gates and time windows.
- **+** Position manager with clear exit logic.
- **+** Options selection with liquidity screening.
- **–** Limited P&L analytics and outcome normalization in live loop.
- **–** Incomplete MAE/MFE and drawdown tracking (schema exists; logic missing).
- **–** Daily P&L used in kill switch is not calculated.
- **–** Some learning/analytics tables exist but not consistently populated.

---

## 9) Key Truths (What is actually happening today)

- **Signals are deterministic** and can be explained from inputs.
- **Sentiment is a confidence scaler**, not a directional gate.
- **Volume is a hard gate**; if volume_ratio < 0.5, no trade.
- **Options are used only when trends are clear** and volatility is not high.
- **Dispatcher can execute real paper trades** when EXECUTION_MODE=ALPACA_PAPER.
- **Positions are closed by position_manager**, independent of dispatcher allowed_actions.
- **Learning infrastructure exists**, but much of it is not wired into decisions yet.

---

## 10) Appendix: Where Each Behavior Comes From (Code Map)

- Signal logic: `services/signal_engine_1m/rules.py`
- Signal orchestration: `services/signal_engine_1m/main.py`
- Features: `services/feature_computer_1m/features.py`
- Telemetry ingestion: `services/telemetry_ingestor_1m/main.py`
- Watchlist: `services/watchlist_engine_5m/*`
- Dispatcher: `services/dispatcher/main.py`
- Risk gates: `services/dispatcher/risk/gates.py`
- Options selection: `services/dispatcher/alpaca/options.py`
- Paper broker: `services/dispatcher/alpaca/broker.py`
- Position manager: `services/position_manager/*`
- Trade stream: `services/trade_stream/*`
- DB schema: `db/migrations/*.sql`
