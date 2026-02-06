# Missing Features Analysis - What Was Planned But Not Implemented
**Date:** February 6, 2026, 16:24 UTC

## Your Question: "Are we using Alpaca news WebSocket?"

**Short Answer:** NO - It was PLANNED (Phase 5) but never implemented.

---

## Current News Infrastructure

### What's Actually Running: RSS Feeds
**Service:** rss_ingest_task (scheduled, not identified in running services)  
**Method:** Polling RSS feeds every 5 minutes  
**Sources:** Configurable RSS feeds (stored in SSM Parameter Store)  
**Status:** Working, but not optimal

**Issues:**
- 5-minute delay (not real-time)
- Manual deduplication needed
- Limited sources (RSS only)
- No structured data

### What Was Planned But NOT Implemented: Alpaca News WebSocket
**Document:** deploy/PHASE_5_WEBSOCKETS_WEBHOOKS_PLAN.md  
**Status:** Documented but never built  
**Would Provide:**
- Real-time news (instant, not 5-min delay)
- Professional sources (Benzinga, Reuters)
- Pre-parsed with ticker extraction
- Automatic deduplication
- Better quality than RSS

**Why Not Implemented:**
- Phase 5 planned for future
- Current RSS working "well enough"
- WebSocket complexity deferred

---

## Trade Stream Status (For Comparison)

### ✅ trade_stream IS Deployed and Working
**Service:** trade-stream (running as ECS service)  
**Purpose:** Real-time trade fill notifications  
**Status:** ACTIVE, working perfectly  
**Evidence:** Logs show fills at 14:30 UTC today

**What It Does:**
- Subscribes to trade updates ONLY
- Instant position sync on order fills
- Does NOT handle news

**What It Doesn't Do:**
- No news stream subscription
- Only trade events, not news events

---

## Gap Analysis: Planned vs Implemented

### Phase 5 WebSocket Plan (From Documentation)

| Component | Status | Notes |
|-----------|--------|-------|
| **5A: Trade Stream** | ✅ IMPLEMENTED | Working! Syncs positions <1 sec |
| **5B: News Stream** | ❌ NOT IMPLEMENTED | Still using RSS feeds |
| **5C: Market Data Stream** | ❌ NOT IMPLEMENTED | Still polling prices |
| **5D: Architecture Migration** | ⏸️ PAUSED | Only trade stream done |

**Progress:** 1 of 4 WebSocket streams implemented (25%)

---

## What Should Be Implemented (My Recommendation)

### HIGH Priority: Alpaca News WebSocket
**Why:**
- Instant breaking news (vs 5-min delay)
- Better sources (professional feeds)
- Pre-structured data
- 300x faster than RSS polling

**Effort:** 4-6 hours  
**Impact:** HIGH - Better sentiment signals  
**Risk:** LOW - Can run alongside RSS as hybrid

### Medium Priority: Market Data WebSocket  
**Why:**
- Real-time price updates (vs 60-sec delay)
- Better exit timing
- Sub-second trailing stops

**Effort:** 6-8 hours  
**Impact:** MEDIUM - Better execution  
**Risk:** MEDIUM - More complex than news

---

## How To Implement News WebSocket

### Step 1: Create news_stream Service (2 hours)
```python
# services/news_stream/main.py
from alpaca.data.live import NewsDataStream

news_stream = NewsDataStream(
    api_key=ALPACA_API_KEY,
    secret_key=ALPACA_API_SECRET
)

@news_stream.on_news
async def handle_news(news_item):
    # Store in database
    await db.store_news_from_alpaca(news_item)
    
    # Trigger sentiment analysis
    await analyze_sentiment_immediate(news_item)

news_stream.subscribe_news(['*'])  # All news
await news_stream._run_forever()
```

### Step 2: Deploy to ECS (1 hour)
```bash
# Build & push
cd services/news_stream
docker build -t news-stream:latest .
docker push ...

# Create ECS service (long-running, not scheduled)
aws ecs create-service \
  --service-name news-stream \
  --task-definition news-stream:1 \
  --desired-count 1
```

### Step 3: Test & Validate (1 hour)
- Run alongside RSS (hybrid mode)
- Compare news quality
- Verify no duplicates
- Check sentiment accuracy

### Step 4: Phase Out RSS (30 min)
- Disable RSS scheduler
- Keep code as backup
- Monitor for 24 hours

**Total Time:** 4-5 hours for complete news WebSocket implementation

---

## Current System vs Optimal

### Current (What's Running):
```
News: RSS feeds (5-min polling)
      ↓
      Classifier (sentiment)
      ↓
      Watchlist Engine
      ↓
      Signal Engine
      ↓
      Dispatcher
```

### Optimal (With Phase 5 Complete):
```
News: Alpaca WebSocket (instant)
      ↓
      Instant sentiment
      ↓
      Immediate watchlist update
      ↓
      Signal Engine (faster signals)
      ↓
      Dispatcher (better timing)
```

**Latency Improvement:**
- Current: 5-10 minutes from news → trade
- Optimal: 10-30 seconds from news → trade
- **20x faster reaction time**

---

## What You Should Know

### Trade Stream: ✅ DONE
- You have trade WebSocket working
- Positions sync instantly
- This part of Phase 5 is complete

### News Stream: ❌ NOT DONE (Yet)
- Still using RSS feeds
- Phase 5B planned but not built
- Would be HIGH value addition
- Relatively easy to implement

### Market Data Stream: ❌ NOT DONE
- Still polling prices every minute
- Would enable sub-second exits
- More complex than news
- Lower priority than news

---

## Recommendation

### For News (HIGH Value, Low Effort):
**Yes, implement Alpaca news WebSocket!**

**Benefits:**
- 20x faster news reaction
- Better sources (professional)
- Clean structured data
- No RSS parsing bugs

**Effort:** 4-6 hours total  
**Risk:** LOW - run alongside RSS first

### Implementation Order:
1. Build news_stream service (2 hours)
2. Deploy to ECS (1 hour)
3. Test hybrid mode (1 hour)
4. Phase out RSS (30 min)

**Worth it?** YES! Professional trading systems use real-time news.

---

## Bottom Line

**What You Remembered:**
✅ You're right - there WAS a plan for news WebSocket  
✅ It's in Phase 5 documentation  
✅ It would be valuable

**What's Actually Deployed:**
✅ trade_stream WebSocket (working!)  
❌ news_stream WebSocket (planned, not built)  
❌ market_data WebSocket (planned, not built)

**Current News:**
- RSS feeds (working but slow)
- 5-minute polling
- Adequate but not optimal

**Should You Implement News WebSocket?**
**YES** - It's a high-value, low-risk improvement that would make the system significantly more competitive. Phase 5B from the plan is solid and ready to implement.

---

## Files Referenced
- `deploy/PHASE_5_WEBSOCKETS_WEBHOOKS_PLAN.md` - Complete plan
- `services/trade_stream/main.py` - Working example
- `services/rss_ingest_task/` - Current news source

**Current Status:** 1/4 WebSocket streams implemented (trade only)  
**Recommendation:** Add news stream next (Phase 5B)
