# Current System Behavior (Baseline Snapshot)
Date: 2026-02-02

This is a **short, edit‑friendly snapshot** of how the system behaves today. It is intentionally concise; for full detail see `SYSTEM_BEHAVIOR_AUDIT.md`.

## Core Pipeline
1) **News ingestion** (RSS) → `inbound_events_raw` → FinBERT classification → `inbound_events_classified`.
2) **Telemetry ingestion** (1‑min OHLCV) → `lane_telemetry`.
3) **Feature computation** (SMA/vol/volume ratio/trend) → `lane_features_clean`.
4) **Watchlist** (top 30) via weighted score → `watchlist_state`.
5) **Signal engine** generates actionable recommendations only (HOLD not stored) → `dispatch_recommendations`.
6) **Dispatcher** applies risk gates and executes (Alpaca paper or simulated fallback) → `dispatch_executions`.
7) **Trade stream** + **position manager** track open positions, enforce exits → `active_positions`, `position_events`.

## Key Decision Rules (Today)
- **Direction**: price relative to SMA20 + trend_state (sentiment does not set direction).
- **Breakout**: requires ±1% from SMA20; otherwise confidence halved.
- **Volume**: hard gate below 0.5x average; otherwise confidence scaled.
- **Options vs stock**: options only when trend_state = ±1 and volatility not high.
- **Strategy type**: day_trade if confidence ≥ adaptive threshold and volume ≥ 2.0x, else swing.
- **Risk gates**: trading hours, cooldowns, max trades per ticker, max positions, max exposure, daily loss.
- **Exits**: stop/take‑profit (ATR‑based), option +50%/‑25%, trailing stop, time‑based, expiry risk.

## Current Threshold Anchors
- Volume kill: **< 0.5x**
- Breakout: **±1%** from SMA20
- Confidence thresholds (defaults): **0.60 day‑trade**, **0.45 swing**, **0.35 stock**
- Trading hours: **9:30–16:00 ET**, block **9:30–9:35** and **15:45–16:00**

## Where to Look (Code Map)
- Signal logic: `services/signal_engine_1m/rules.py`
- Dispatcher + gates: `services/dispatcher/main.py`, `services/dispatcher/risk/gates.py`
- Options selection: `services/dispatcher/alpaca/options.py`
- Exits: `services/position_manager/monitor.py`, `services/position_manager/exits.py`

