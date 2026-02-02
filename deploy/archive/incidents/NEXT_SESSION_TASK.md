# Next Session Task - Deploy Signal Fix + Documentation Cleanup

**Date:** 2026-01-27  
**Estimated Time:** 30-45 minutes  
**Prerequisites:** Read this entire file first

---

## Context: What Was Accomplished

### Phase 14A: Ticker Discovery - DEPLOYED ✅
- AI-powered ticker selection using Bedrock Sonnet
- Runs every 6 hours, recommends 28-35 tickers
- Fully operational with all permissions fixed

### System Diagnosis - COMPLETE ✅
- Verified all Phases 1-15 working
- Found why no trades: NVDA 8.63x surge + 0.91 sentiment blocked
- Root cause: Price 18 cents below SMA20 = rejected
- **Signal logic too strict**

### Signal Fix - READY TO DEPLOY ✅
- Applied ±0.5% tolerance to SMA20 checks
- Allows trades AT support/resistance zones
- File: `services/signal_engine_1m/rules.py`
- **Not yet deployed - this is your task**

---

## Project Overview

### Complete Data Flow
```
1. RSS feeds → inbound_events_raw (every 30 min)
2. FinBERT → inbound_events_classified (sentiment -1 to +1)
3. Alpaca API → lane_telemetry (1-min bars)
4. Feature Computer → lane_features (SMA, volume_ratio, etc.)
5. Signal Engine → dispatch_recommendations (CALL/PUT/STOCK)
6. Dispatcher → Alpaca API → Trade execution
7. Position Manager → Monitors positions (stops, targets)
```

### How Signal Generation Works

**Current Logic (in services/signal_engine_1m/rules.py):**

```python
# For BULLISH CALL:
1. Check sentiment > 0.5 (very bullish)
2. Check trend_state >= 0 (uptrend)
3. Check near_or_above_sma20 (NEW: ±0.5% tolerance)
4. Check not_stretched (<2% from SMA)
5. Compute confidence (sentiment + trend + setup + vol)
6. Apply volume multiplier (boost if >3.0x)
7. If confidence >= 0.55 and volume >= 2.0x:
   → BUY CALL (day_trade)

# For BEARISH PUT:
Same logic but reversed (sentiment < -0.5, below SMA20)
```

**The Fix You're Deploying:**
- **Before:** Required strictly above_sma20 (NVDA -18 cents rejected)
- **After:** Allows near_or_above_sma20 (within 0.5% = at support)
- **Impact:** NVDA and similar setups will now qualify

### How Config System Works

**File:** `config/trading_params.json`

**All tunable parameters:**
```json
{
  "sentiment_threshold": 0.50,    // Bullish/bearish requirement
  "sma_tolerance": 0.005,         // ±0.5% from SMA20
  "confidence_min": 0.55,         // Day trade threshold
  "volume_min": 2.0,              // Volume surge minimum
  "volume_multipliers": {...},   // Boost/reduce based on volume
  "risk_management": {...},      // Stops, targets, sizing
  "feature_computation": {...}   // SMA periods, RSI, etc.
}
```

**Current Status:**
- File created with all parameters
- NOT yet in SSM (manual editing for now)
- Future: Store in SSM for dynamic adjustment

### How Deployment Works

**ECS Services:**
```
All services are ECS Fargate tasks
Deployment pattern:
1. Update code in services/SERVICE_NAME/
2. docker build -t SERVICE_NAME .
3. docker tag and push to ECR
4. Get image digest from ECR
5. Update deploy/SERVICE_NAME-task-definition.json with new digest
6. aws ecs register-task-definition --cli-input-json file://...
7. ECS automatically picks up new revision
8. EventBridge scheduler triggers with new code
```

**Key Files:**
- `services/SERVICE_NAME/Dockerfile` - Build config
- `deploy/SERVICE_NAME-task-definition.json` - ECS config
- EventBridge Scheduler - Trigger config

---

## Your Tasks

### Task 1: Deploy Signal Engine Fix (15 min)

**What Changed:**
- `services/signal_engine_1m/rules.py` now has ±0.5% SMA tolerance
- Allows trades at $186.86 when SMA20 is $187.20
- Will enable trading tomorrow

**Steps:**
```bash
cd /home/nflos/workplace/inbound_aigen/services/signal_engine_1m

# 1. Build Docker image
docker build -t signal-engine .

# 2. Login to ECR
aws ecr get-login-password --region us-west-2 | \
  docker login --username AWS --password-stdin \
  160027201036.dkr.ecr.us-west-2.amazonaws.com

# 3. Tag image
docker tag signal-engine:latest \
  160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/signal-engine-1m:latest

# 4. Push to ECR
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/signal-engine-1m:latest

# 5. Get new image digest
aws ecr describe-images \
  --repository-name ops-pipeline/signal-engine-1m \
  --region us-west-2 \
  --query 'imageDetails[0].imageDigest' \
  --output text

# 6. Update deploy/signal-engine-task-definition.json
# Replace image digest with output from step 5

# 7. Register new task definition
aws ecs register-task-definition \
  --cli-input-json file://deploy/signal-engine-task-definition.json \
  --region us-west-2

# 8. Verify new revision
aws ecs describe-task-definition \
  --task-definition signal-engine-1m \
  --region us-west-2 \
  --query 'taskDefinition.{Family:family,Revision:revision}'

# 9. Wait for next scheduled run (every 5 minutes)
# Check logs for signals:
aws logs tail /ecs/ops-pipeline/signal-engine-1m \
  --region us-west-2 --follow
```

**Expected Result:**
- Within 30 minutes: First signals generated
- Signals will show in dispatch_recommendations table
- Dispatcher will execute trades
- Check with: `python3 scripts/verify_all_phases.py`

### Task 2: Archive Phase 14 Journey Docs (10 min)

**Problem:** Too many Phase 14 markdown files (confusing)

**Keep These (Essential):**
```
✅ CURRENT_SYSTEM_STATUS.md (main reference)
✅ deploy/COMPLETE_TRADING_LOGIC_EXPLAINED.md (how signals work)
✅ deploy/PHASE_14_TICKER_DISCOVERY_SUCCESS.md (Phase 14 final status)
✅ deploy/SESSION_COMPLETE_2026-01-27.md (today's summary)
✅ config/trading_params.json (parameters)
```

**Archive These (Historical/Redundant):**
```bash
mkdir -p deploy/archive/phase14_journey

# Move intermediate Phase 14 docs
mv deploy/PHASE_14_PARTIAL_DEPLOYMENT_STATUS.md deploy/archive/phase14_journey/
mv deploy/PHASE_14_PROGRESS_TONIGHT.md deploy/archive/phase14_journey/
mv deploy/PHASE_14_BUILD_COMPLETE.md deploy/archive/phase14_journey/
mv deploy/PHASE_14_DEPLOYMENT_GUIDE.md deploy/archive/phase14_journey/
mv deploy/PHASE_14_ARCHITECTURE_EXPLANATION.md deploy/archive/phase14_journey/
mv deploy/PHASE_14_FINAL_STATUS.md deploy/archive/phase14_journey/
mv deploy/PHASE_14_AI_LEARNING_PLAN.md deploy/archive/phase14_journey/
mv deploy/PHASE_14_AGGRESSIVE_IMPLEMENTATION.md deploy/archive/phase14_journey/
mv deploy/PHASE_14_HISTORICAL_BACKFILL_PLAN.md deploy/archive/phase14_journey/

echo "Phase 14 journey docs archived"
```

**Create Archive README:**
```bash
cat > deploy/archive/phase14_journey/README.md << 'EOF'
# Phase 14 Journey Archive

These documents show the 8-hour journey deploying Phase 14A Ticker Discovery.

**Timeline:**
- Sunday 9 PM - Started deployment
- Learned VPC Lambda can't reach Bedrock
- Converted to ECS with AssignPublicIp
- Fixed 8 permission issues
- Monday 2 PM - Diagnosed signal blocker (18 cents)
- Fixed signal logic

**See main docs for current status:**
- CURRENT_SYSTEM_STATUS.md
- deploy/PHASE_14_TICKER_DISCOVERY_SUCCESS.md
EOF
```

### Task 3: Update README.md (5 min)

**Current README is outdated (shows Phase 5)**

**Update to reflect current state:**
```markdown
# Ops Pipeline - AI-Powered Options Trading

**Status:** Fully operational (Phases 1-15 complete)  
**Trading:** Signal fix ready to deploy  
**AI:** Ticker Discovery live (Bedrock Sonnet)

## Quick Start

**Check System Status:**
```bash
python3 scripts/verify_all_phases.py
```

**See Complete Documentation:**
- `CURRENT_SYSTEM_STATUS.md` - System overview
- `deploy/COMPLETE_TRADING_LOGIC_EXPLAINED.md` - How trading works
- `config/trading_params.json` - All parameters

## Architecture

**Data Flow:**
RSS → FinBERT sentiment → Alpaca telemetry → Features → Signals → Trading

**AI Components:**
- Phase 11: Bedrock Haiku (ticker extraction from news)
- Phase 14: Bedrock Sonnet (market analysis, ticker recommendations)
- Sentiment: FinBERT (financial sentiment classification)

**Trading:**
- Options: CALL and PUT (day trade 0-1 DTE, swing 7-30 DTE)
- Stocks: Fallback when volatility high
- Position Manager: Enforces stops, targets, expirations

## Key Metrics (Monday Jan 27)

- Database: 14 tables, 10 migrations
- Data: 351 events/day, 83 bars/6h processed
- Features: 65 computed, 5 volume surges detected
- Sentiment: FinBERT analyzing 350 articles/day
- AI: 35 ticker recommendations every 6 hours
- Signals: 0 (fix pending deployment - 18 cents blocked NVDA)

## Next: Deploy signal fix to enable trading
```

### Task 4: Verify After Deployment (10 min)

**After signal_engine deployed, verify:**

```bash
# 1. Check for signals (should appear within 30 min)
python3 scripts/verify_all_phases.py

# 2. Query dispatch_recommendations
python3 -c "import boto3, json; \
client = boto3.client('lambda', region_name='us-west-2'); \
r = client.invoke(FunctionName='ops-pipeline-db-query', \
  Payload=json.dumps({'sql': 'SELECT ticker, action, instrument_type, confidence FROM dispatch_recommendations WHERE created_at > NOW() - INTERVAL \"1 hour\" ORDER BY created_at DESC LIMIT 10'})); \
print(json.loads(json.load(r['Payload'])['body']))"

# 3. If signals generated, check if dispatcher executed
# 4. If executed, check position_manager tracking
# 5. Document in deploy/SIGNAL_FIX_DEPLOYED.md
```

---

## Important Context for Next Agent

### Why No Trades Currently

**System detected MASSIVE opportunities:**
- NVDA: 8.63x volume surge (43 occurrences!)
- Sentiment: +0.91 (very bullish)
- Watchlist: Actively monitoring

**But 0 signals because:**
- NVDA price was $186.86
- SMA20 was $187.20
- 18 cents below = OLD CODE rejected it
- **Your deployed fix will solve this**

### How to Verify Fix Worked

**Tomorrow during trading hours:**
```python
# If you see NVDA at similar setup:
# - Volume >3x: Should generate signal now
# - Sentiment >0.5: Already meeting threshold
# - At SMA20 (±0.5%): Now allowed with your fix
# = Signal should generate
# = Trade should execute
# = Position Manager should track
```

### Config System (For Future)

**Current:** Parameters hardcoded in rules.py  
**Created:** config/trading_params.json with all parameters  
**Future Enhancement:**
1. Store trading_params.json in SSM: `/ops-pipeline/trading-params`
2. Load in signal_engine at runtime
3. AI can adjust based on performance
4. No redeployment needed for tuning

---

## Critical Files Reference

### Read These First
1. `CURRENT_SYSTEM_STATUS.md` - System overview
2. `services/signal_engine_1m/rules.py` - Signal logic (your changes)
3. `config/trading_params.json` - All parameters

### Deployment Pattern
1. Build: `docker build -t SERVICE .`
2. Push: ECR with image digest
3. Update: task-definition.json
4. Register: `aws ecs register-task-definition`
5. Auto-restart: ECS picks up new revision

### Verification
1. `scripts/verify_all_phases.py` - Test everything
2. CloudWatch logs: `/ecs/ops-pipeline/SERVICE_NAME`
3. Database queries via ops-pipeline-db-query Lambda

---

## Success Criteria

### You'll Know It Worked When:
- [ ] Signal engine deployed (new revision)
- [ ] Within 30 min: Signals in dispatch_recommendations table
- [ ] Signals show NVDA or similar (near SMA20)
- [ ] Dispatcher executes trades
- [ ] Position Manager tracking
- [ ] Old Phase 14 docs archived
- [ ] README.md updated
- [ ] New agent can understand system from docs

---

## Questions You Might Have

**Q: Why were tables empty?**
A: System too strict. NVDA 8.63x surge ignored because 18 cents below SMA. Your fix solves this.

**Q: Can system trade options both ways?**
A: Yes! BUY CALL (bullish) and BUY PUT (bearish). Both coded and ready.

**Q: How does sentiment work?**
A: FinBERT (not Bedrock) analyzes news. Returns positive/negative/neutral + confidence. Stored as -1 to +1.

**Q: Why sentiment 0.50 threshold?**
A: Too conservative for options. Should be 0.10 (directional). But SMA fix is more critical first.

**Q: How to adjust parameters?**
A: Currently: Edit rules.py and redeploy. Future: Store in SSM for dynamic adjustment.

---

## If Something Goes Wrong

**Rollback:**
```bash
# Find previous working revision
aws ecs describe-task-definition \
  --task-definition signal-engine-1m:PREVIOUS_REV

# Update scheduler to use old revision
aws scheduler update-schedule \
  --name signal-engine-1m \
  --target '{...TaskDefinitionArn: "...signal-engine-1m:OLD_REV"}'
```

**Debug:**
```bash
# Check logs
aws logs tail /ecs/ops-pipeline/signal-engine-1m --follow

# Check signals generated
python3 scripts/verify_all_phases.py

# Verify no errors in recent runs
aws ecs list-tasks --cluster ops-pipeline-cluster \
  --family signal-engine-1m --desired-status STOPPED
```

---

## After Successful Deployment

**Document in:** `deploy/SIGNAL_FIX_DEPLOYED.md`

**Include:**
- Deployment timestamp
- New task revision number
- First signals generated (ticker, time, type)
- First trades executed
- Verification results

**Update:** `CURRENT_SYSTEM_STATUS.md`
- Change "Signal fix ready" to "Signal fix deployed"
- Update "Why no trades" section
- Add "Recent signals" section

---

**START HERE:** Read CURRENT_SYSTEM_STATUS.md, then deploy signal_engine, then cleanup docs.

**You have everything you need to succeed!**
