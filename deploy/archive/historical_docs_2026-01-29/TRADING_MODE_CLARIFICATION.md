# Trading Mode Clarification - STOCKS NOT OPTIONS
**Date:** 2026-01-26 15:42 UTC  
**CRITICAL:** System trades STOCKS, not options

## What We're Actually Trading

### Current: STOCK Trading (Shares)
```
When signal says "BUY TSLA":
  → Buys SHARES of Tesla stock
  → Example: Buy 10 shares @ $442.50
  → Hold during day, sell at close
  → Max loss: Position size (5% of portfolio)
```

### NOT: Options Trading (Calls/Puts)
```
Options would be:
  → Buy CALL option on TSLA (right to buy at strike)
  → Buy PUT option on TSLA (right to sell at strike)
  → Leverage: Control 100 shares per contract
  → Max profit: Unlimited (calls) or limited (puts)
  → Max loss: Premium paid
```

## Why Stocks Not Options (Currently)

### Stock Trading Pros
✅ Simpler to implement (done!)
✅ Lower risk (no time decay)
✅ No expiration dates
✅ Easier to understand
✅ Alpaca supports stocks directly

### Options Trading Pros  
💰 Higher leverage (control more with less)
💰 Can profit from up OR down moves
💰 Limited risk (max loss = premium)
💰 More strategies (spreads, straddles, etc.)

### Options Trading Cons
❌ Much more complex to code
❌ Time decay (theta) erodes value
❌ Need to pick strike prices
❌ Need to pick expiration dates
❌ Alpaca options API more complex
❌ Higher transaction costs

## Current Profit Potential (Stocks)

### Maximum Daily Gain (Stock Trading)
```
Portfolio: $100,000
Max per trade: 5% = $5,000
Max trades/day: 14 (7 tickers × 2 each)
If ALL win +2%: $5,000 × 14 × 0.02 = $1,400/day
Realistic (50% win): ~$300-500/day
Monthly (20 days): $6,000-10,000/month (6-10% return)
```

### With Options (If We Built It)
```
Portfolio: $100,000
Leverage: 10-20x with options
Per trade: 5% = $5,000 buying power = $50,000-100,000 controlled
If win +50% on options: $5,000 × 0.50 = $2,500 per trade
Max trades/day: 14
If ALL win: $35,000/day (UNREALISTIC)
Realistic (50% win, 25% avg): $6,000-8,000/day
Monthly: $120,000-160,000/month (120-160% return!)
```

**But:** Options are MUCH riskier and harder to get right.

## Current Ticker Discovery

### Fixed List (Currently)
```
Tickers: AAPL, MSFT, TSLA, GOOGL, AMZN, META, NVDA
Source: Hard-coded in SSM parameter
How set: Manually chosen (Magnificent 7 tech stocks)
```

### Watchlist Engine (Exists But Limited)
```
What it does:
  - Ranks the 7 tickers by activity
  - Prioritizes which to focus on
  - Scores based on news volume, volatility

What it DOESN'T do:
  - Discover new tickers
  - Add/remove tickers dynamically
  - Scan broader market
```

## How to Add More Tickers

### Option 1: Manual Addition (Easy - 5 minutes)
```bash
# 1. Update SSM parameter
aws ssm put-parameter \
  --name "/ops-pipeline/tickers" \
  --value "AAPL,MSFT,TSLA,GOOGL,AMZN,META,NVDA,NFLX,AMD,INTC" \
  --type "String" \
  --overwrite \
  --region us-west-2

# 2. Add RSS feeds for new tickers (optional)
# Edit services/rss_ingest_task/ingest.py
# Add: "https://finance.yahoo.com/rss/headline?s=NFLX"

# 3. Done! System will pick them up on next run
```

### Option 2: Automated Discovery (Phase 15 - 1-2 weeks)

**Market Scanner Service:**
```python
# services/market_scanner/
# Runs: Every 5 minutes during market hours
# Purpose: Find hot movers

def scan_market():
    # 1. Get top volume gainers from Alpaca
    movers = alpaca.get_market_movers(
        top=50,
        min_price=50,        # $50+ stocks only
        min_volume=1000000   # 1M+ volume
    )
    
    # 2. Filter by criteria
    candidates = []
    for stock in movers:
        if (stock.price > 50 and 
            stock.volume_ratio > 3.0 and  # 3x avg volume
            stock.price_change_pct > 2):  # 2%+ move
            candidates.append(stock)
    
    # 3. Check news coverage
    for candidate in candidates:
        news_count = count_news_articles(candidate.symbol)
        if news_count >= 5:  # Must have news
            add_to_watchlist(candidate.symbol)
    
    # 4. Auto-expire after 24 hours if quiet
    remove_stale_tickers()
```

**Result:**
- Automatically find hot stocks
- Add to watchlist if meeting criteria
- Remove if no longer active
- Always focusing on most opportunities

### Option 3: Sector Rotation (Phase 16 - 2 weeks)

**Smart Sector Tracking:**
```python
# Track which sectors are hot
sectors = {
    'tech': ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'AMD', 'INTC'],
    'energy': ['XOM', 'CVX', 'COP', 'SLB'],
    'finance': ['JPM', 'BAC', 'GS', 'MS'],
    'consumer': ['AMZN', 'TSLA', 'NKE', 'SBUX']
}

# Measure sector strength daily
# Trade top 3 sectors, ignore weak sectors
# Rotate tickers within strong sectors
```

## Recommendations

### For Maximum Daily Profit - Choose ONE:

#### Path A: More Stock Tickers (Easy - Start Now)
1. Add 10-20 more liquid stocks manually
2. Focus on high-volume movers
3. Expected: 2-3x more trade opportunities
4. Risk: Still LOW (stock trading)
5. Effort: 5 minutes to add tickers

**Best tickers to add:**
- NFLX, AMD, INTC (more tech)
- SPY, QQQ (index ETFs - very liquid)  
- COIN, SQ (fintech)
- BA, CAT (industrials)

#### Path B: Implement Options Trading (Hard - 2-3 weeks)
1. Learn Alpaca options API
2. Implement option pricing
3. Add strike selection logic
4. Add expiration management
5. Much higher complexity
6. Expected: 5-10x leverage
7. Risk: MUCH HIGHER (can lose faster)

#### Path C: Automated Ticker Discovery (Medium - 1-2 weeks)
1. Implement market scanner (Phase 15)
2. Find top volume gainers automatically
3. Add tickers with news coverage
4. Remove stale tickers after 24h
5. Always focus on hottest opportunities

### My Recommendation: Path A + C

**Week 1:** Add 10-20 more tickers manually (Path A)
- Get more opportunities immediately
- Learn what works with stocks first
- Build up trade history

**Week 2-3:** Implement automated discovery (Path C)
- Let AI find hot movers
- Focus on best opportunities
- Continuous optimization

**Month 2-3:** Consider options (Path B) IF:
- Stock trading profitable (>55% win rate)
- Comfortable with current system
- Want to add leverage
- Willing to handle complexity

## Why Start with Stocks?

**Professional traders typically:**
1. Master stock day trading first (6-12 months)
2. Add options once profitable
3. Use options for specific strategies (earnings, events)
4. Keep 70% in stocks, 30% in options

**You're currently:** Day 1 of paper trading!

**Recommended:** Master stocks for 1-2 months, THEN add options if you want more leverage.

## Quick Win: Add More Tickers NOW

Want me to add 15 more liquid tickers right now? Here's my recommended list:

**Tech (5 more):**
- AMD, INTC, CRM, ORCL, ADBE

**Growth (5 more):**
- NFLX, SHOP, SQ, COIN, SNAP

**Index/ETFs (5 more):**
- SPY, QQQ, IWM, DIA, VOO

This gives 22 total tickers = 3x more opportunities, still stocks only, zero additional code needed!

---

## Answer to Your Questions

### Q: "Is this options trading?"
**A:** NO - This is STOCK trading. Options would require significant additional development (2-3 weeks). Stock trading is simpler, lower risk, and good for learning. Can add options later if you want leverage.

### Q: "How are we finding new tickers?"
**A:** Currently FIXED list of 7 tickers (Magnificent 7 tech stocks). We can:
1. **Add manually** (5 min) - Fastest
2. **Auto-discovery** (1-2 weeks) - Phase 15
3. **Sector rotation** (2 weeks) - Phase 16

**I recommend:** Add 10-20 more manually NOW, then implement auto-discovery in 1-2 weeks.

### Q: "Want to make most money possible each day?"
**A:** For stocks (current): Add more tickers NOW
    For max leverage: Consider options LATER (after stocks profitable)
    For AI optimization: Phase 14 analytics after 1 week

Want me to add more tickers right now? I can do it in 1 minute!
