# Scheduler Migration Plan - Convert All to ECS Services

## Current Scheduler Status (Checked 4:22 PM)

### ❌ NOT Working (4 services):
```
dispatcher: 0 tasks (CRITICAL - no trades executing!)
signal-engine-1m: 0 tasks (CRITICAL - no signals!)
watchlist-engine-5m: 0 tasks (CRITICAL - no opportunities!)
classifier: 0 tasks (HIGH - no sentiment analysis!)
```

### ✅ Working (1 service):
```
feature-computer-1m: 1 task running
```

### ✅ Already Converted (2 services):
```
position-manager: Now ECS Service ✅
telemetry: Now ECS Service ✅
```

---

## Critical Services Needing Immediate Conversion

### Priority 1: DISPATCHER (CRITICAL)
**Why:** Executes trades - system can't trade without it!
**Frequency:** Every 1 minute
**Recommendation:** Convert to ECS Service (LOOP mode)
**Accounts:** 2 (large + tiny) - need 2 separate services

### Priority 2: SIGNAL ENGINE (CRITICAL)
**Why:** Generates trade signals - nothing to dispatch without it!
**Frequency:** Every 1 minute  
**Recommendation:** Convert to ECS Service (LOOP mode)

### Priority 3: WATCHLIST ENGINE (HIGH)
**Why:** Scores opportunities - signals need this!
**Frequency:** Every 5 minutes
**Recommendation:** Convert to ECS Service (LOOP mode)

### Priority 4: CLASSIFIER (HIGH)
**Why:** Sentiment analysis on news
**Frequency:** Every 5 minutes
**Recommendation:** Convert to ECS Service (LOOP mode)

### Priority 5: FEATURE COMPUTER (LOW)
**Why:** Already working via scheduler
**Recommendation:** Leave as-is for now, convert if issues

---

## Conversion Strategy

### Services to Convert to ECS Services (LOOP mode):
1. **dispatcher** (2 instances: large + tiny)
2. **signal-engine-1m**
3. **watchlist-engine-5m**  
4. **classifier**

**Why ECS Services (not WebSockets):**
- These are compute jobs (process data periodically)
- Don't need real-time event streams
- Just need reliable execution every N minutes
- LOOP mode with sleep() is perfect

### Services for WebSocket Mode:
1. **Position Manager** - Already has WebSocket code in trade_stream
2. **Trade notifications** - Real-time fill alerts

**Why WebSockets:**
- Need instant notifications (<1 second)
- Event-driven (not time-based)
- Alpaca provides WebSocket APIs for this

---

## Implementation Order

### Phase 1: Critical Services (1 hour)
```
1. Dispatcher (large account) → ECS Service
2. Dispatcher (tiny account) → ECS Service  
3. Signal Engine → ECS Service
4. Watchlist Engine → ECS Service
```

### Phase 2: Supporting Services (30 min)
```
5. Classifier → ECS Service
6. RSS Ingest → Keep scheduler (works, runs every 30 min)
```

### Phase 3: Real-Time (Optional)
```
7. Trade Stream WebSocket (for instant position sync)
8. News Stream WebSocket (for real-time news)
```

---

## Code Changes Needed

### For Each Service:
1. Update `main.py` - Add LOOP/ONCE mode
2. Update `Dockerfile` - Cache bust
3. Build new Docker image
4. Create service task definition
5. Deploy as ECS Service
6. Delete old scheduler
7. Verify in logs

### Pattern (Same as Position Manager/Telemetry):
```python
if __name__ == '__main__':
    run_mode = os.getenv('RUN_MODE', 'LOOP')
    if run_mode == 'ONCE':
        main()
    else:
        while True:
            try:
                main()
                time.sleep(interval_seconds)
            except Exception as e:
                log error
                time.sleep(30)
```

---

## Estimated Time

**1 service conversion:** ~10 minutes
**4 critical services:** ~40 minutes
**Total with testing:** ~1 hour

---

## Recommendation

**Convert all scheduler-based services to ECS Services:**
- Schedulers are fundamentally unreliable (proven today)
- ECS Services work (Position Manager + Telemetry proof)
- Avoids all EventBridge Scheduler issues
- More predictable and debuggable

**Priority Order:**
1. Dispatcher (can't trade without it!)
2. Signal Engine (nothing to dispatch without it!)
3. Watchlist Engine (signals need scored opportunities!)
4. Classifier (sentiment analysis)

**Should I proceed with converting the critical 4 services?**
