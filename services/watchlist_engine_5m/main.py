#!/usr/bin/env python3
"""
Watchlist Engine - Dynamic Stock Selection
Scores universe tickers and selects top 30
Runs every 5 minutes
"""

import json
import sys
from datetime import datetime, timezone

from config import load_config
from db import WatchlistDB
from scoring import compute_watch_score

def log(event: str, **kwargs):
    """Structured JSON logging"""
    print(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **kwargs
    }, default=str), flush=True)

def main():
    """Score universe and select top 30"""
    
    log("watchlist_run_start")
    
    try:
        config = load_config()
        universe = config['tickers']
        
        log("config_loaded", universe_size=len(universe))
        
        db = WatchlistDB(config['db'])
        db.connect()
        log("db_connected")
        
        # Get data
        features = db.fetch_latest_features(universe)
        news = db.fetch_news_agg(universe, 60)  # 60-minute window
        current = db.fetch_current_watchlist()
        
        log("data_fetched",
            features_count=len(features),
            tickers_with_news=len([n for n in news.values() if n['news_count'] > 0]))
        
        # Score all tickers
        scores = {}
        reasons_map = {}
        missing = 0
        
        for ticker in universe:
            f = features.get(ticker)
            if not f:
                missing += 1
                continue
            
            n = news.get(ticker, {"news_count": 0})
            score, reasons = compute_watch_score(f, n)
            scores[ticker] = score
            reasons_map[ticker] = reasons
        
        log("scoring_complete", scored=len(scores), missing_features=missing)
        
        # Rank and select top 30
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        # Apply entry threshold and select top 30
        candidates = [(t, s) for t, s in ranked if s >= config['entry_threshold']][:30]
        
        # Backfill if < 30
        if len(candidates) < 30:
            backfill = [
                (t, s) for t, s in ranked 
                if t not in {c[0] for c in candidates}
            ][:(30 - len(candidates))]
            candidates.extend(backfill)
        
        selected_tickers = {t for t, _ in candidates[:30]}
        active_now = set(current.keys())
        
        entered = sorted(selected_tickers - active_now)
        exited = sorted(active_now - selected_tickers)
        
        log("watchlist_selected",
            selected=len(selected_tickers),
            entered=entered,
            exited=exited)
        
        # Prepare upserts
        now = datetime.now(timezone.utc)
        rows = []
        
        # Top 30 active
        for rank, (ticker, score) in enumerate(candidates[:30], start=1):
            rows.append({
                "ticker": ticker,
                "watch_score": score,
                "rank": rank,
                "reasons": reasons_map.get(ticker, {}),
                "active": True,
                "computed_at": now
            })
        
        # Rest inactive
        not_selected = [t for t in universe if t not in selected_tickers]
        for ticker in not_selected:
            rows.append({
                "ticker": ticker,
                "watch_score": scores.get(ticker, 0.0),
                "rank": 999,
                "reasons": reasons_map.get(ticker, {}),
                "active": False,
                "computed_at": now
            })
        
        db.upsert_watchlist_state(rows)
        log("watchlist_upsert_complete", rows_upserted=len(rows))
        
        db.close()
        log("watchlist_run_complete", success=True)
        
        sys.exit(0)
        
    except Exception as e:
        log("watchlist_run_failed", error=str(e), error_type=type(e).__name__)
        sys.exit(1)

if __name__ == '__main__':
    main()
