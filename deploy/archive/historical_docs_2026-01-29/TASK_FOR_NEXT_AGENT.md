# Task for Next AI Agent

**Priority:** P0 - Critical  
**Estimated Time:** 2-3 hours  
**Created:** 2026-01-29  

---

## 🎯 YOUR MISSION

**Fix Alpaca options trading** - System is generating 679 options signals per day but ALL trades use SIMULATED_FALLBACK instead of real Alpaca Paper Trading API.

**User wants:** Trades to appear in Alpaca dashboard with real position tracking.

---

## 📋 TASKS IN PRIORITY ORDER

### Task 1: Fix AlpacaPaperBroker Fallback (P0 - 1-2 hours)

**Current State:**
- System IS trading (6 trades today)
- But using SIMULATED_FALLBACK (simulation)
- Should be using ALPACA_PAPER (real API)

**Why:**
When dispatcher tries to execute options:
1. Calls AlpacaPaperBroker._execute_option()
2. Tries to get_option_chain() from Alpaca
3. Returns no contracts → falls back to simulation
4. Records as SIMULATED_FALLBACK

**Investigation:**
```bash
# Check recent dispatcher executions
aws logs tail /ecs/ops-pipeline/dispatcher --region us-west-2 --since 30m | grep -B5 -A5 "option"

# Look for error messages about:
# - "No suitable option contract found"
# - "Option chain empty"
# - API errors

# Check the code:
cat services/dispatcher/alpaca/broker.py | grep -A30 "_execute_option"
```

**Likely Root Causes:**
1. **Alpaca options API returning no contracts**
   - Check if API actually has data for our tickers
   - Test manually: `python3 scripts/test_options_api.py`

2. **Strike selection too restrictive**
   - Code filters by expiration (0-1 DTE for day trades)
   - May need to widen search window

3. **Validation failing**
   - min_volume, max_spread, open_interest checks
   - Consider temporarily relaxing in `services/dispatcher/alpaca/options.py`

**Fix Strategy:**
A. Test if Alpaca has ANY option contracts for our tickers
B. If yes: Relax filters to find them
C. If no: Stick with stocks until Alpaca provides options data

**Files:**
- `services/dispatcher/alpaca/broker.py`
- `services/dispatcher/alpaca/options.py`

---

### Task 2: Fix check_system_status.py False Errors (P1 - 15 min)

**Error Message (FALSE):**
```
⏳ Phase 16 snapshot columns not yet added
❌ learning_recommendations table missing
```

**Reality:** These DO exist (verified with correct query format)

**The Bug:**
`scripts/check_system_status.py` uses WRONG query format:
```python
# WRONG (what script uses):
Payload=json.dumps({'query': 'SELECT...'})
result.get('results', [])

# CORRECT (see AI_AGENT_START_HERE.md):
Payload=json.dumps({'sql': 'SELECT...'})
result.get('rows', [])
```

**Fix:**
Update `scripts/check_system_status.py` lines that query database:
- Change `'query'` to `'sql'`
- Change `.get('results')` to `.get('rows')`

**Reference:** See examples in `AI_AGENT_START_HERE.md`

---

### Task 3: Complete Phase 17 Deployment (P2 - 30 min)

**Status:** Code 100% complete, Docker in ECR, just needs deployment

**What It Does:**
Captures historical option price bars for AI learning

**Already Done:**
- ✅ Migration 015 applied (option_bars table exists)
- ✅ bar_fetcher.py created
- ✅ monitor.py enhanced
- ✅ Docker built: 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/position-manager:phase17

**Deploy:**
Position manager uses EventBridge Scheduler (check if it exists):
```bash
# Check if scheduler exists
aws scheduler list-schedules --region us-west-2 | grep position

# If exists: Update to use task definition position-manager:2
# If not: May run differently - check logs for how it's triggered
```

**Verify:**
After deployment, wait 10 minutes then:
```python
import boto3, json
client = boto3.client('lambda', region_name='us-west-2')

r = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'sql': 'SELECT COUNT(*) FROM option_bars WHERE ts > NOW() - INTERVAL \'10 minutes\''}})
)
print(json.loads(json.load(r['Payload'])['body']))
# Should see bars if positions are open
```

**Reference:** `deploy/PHASE_17_IMPLEMENTATION_INTEGRATED.md`

---

## 📚 ESSENTIAL READING (Before Starting)

### 1. AI_AGENT_START_HERE.md ⭐ MUST READ FIRST
**Contains:**
- Correct database query format
- Table name reference  
- Common mistakes to avoid
- Quick diagnostic commands

**Why Critical:** Without this, you'll use wrong query format and get confusing results

### 2. TROUBLESHOOTING_GUIDE.md
**Contains:**
- How to check service logs
- How to verify deployments
- Common issues and solutions

### 3. CURRENT_SYSTEM_STATUS.md
**Contains:**
- What's currently deployed
- Service revisions
- Infrastructure overview

---

## 🔧 HOW TO USE THE SYSTEMS

### Check Database (CORRECT METHOD)
```python
import boto3, json

client = boto3.client('lambda', region_name='us-west-2')

# ALWAYS use this format:
r = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'sql': 'YOUR_SQL_HERE'})  # 'sql' key
)

result = json.loads(json.load(r['Payload'])['body'])
rows = result.get('rows', [])  # 'rows' key

for row in rows:
    print(row)
```

**Common Tables:**
- dispatch_recommendations (signals)
- dispatch_executions (trades)
- option_bars (Phase 17 - historical prices)
- active_positions (open positions)

### Check Service Logs
```bash
# Format:
aws logs tail /ecs/ops-pipeline/SERVICE_NAME --region us-west-2 --since 10m

# Examples:
aws logs tail /ecs/ops-pipeline/dispatcher --region us-west-2 --since 10m
aws logs tail /ecs/ops-pipeline/signal-engine-1m --region us-west-2 --since 5m
```

### Check What's Deployed
```bash
# EventBridge schedulers (most services use this)
aws scheduler list-schedules --region us-west-2 --output json | jq -r '.Schedules[] | select(.Name | startswith("ops-pipeline")) | .Name'

# Get scheduler details
aws scheduler get-schedule --name ops-pipeline-SERVICE_NAME --region us-west-2
```

### Deploy Service Changes
```bash
# Full example in deploy/NEXT_SESSION_TASK_LIST.md
# Summary:
1. Build Docker: cd services/NAME && docker build -t ops-pipeline/NAME:tag .
2. Push to ECR
3. Update task definition JSON
4. Register: aws ecs register-task-definition --cli-input-json file://deploy/NAME-task-definition.json
5. Update scheduler to use new revision
```

---

## 🏗️ WHAT'S CURRENTLY DEPLOYED

### Services (9 total, all via EventBridge)
1. **signal-engine-1m** (revision 11)
   - Generates trading signals
   - Runs every 1 minute
   
2. **dispatcher** (revision 10) ← **PROBLEM HERE**
   - Executes trades
   - Using SIMULATED_FALLBACK (should use ALPACA_PAPER)
   - Runs every 1 minute

3. **watchlist-engine-5m** (revision 1)
4. **telemetry-ingestor-1m**
5. **feature-computer-1m**
6. **classifier-worker** (FinBERT sentiment)
7. **ticker-discovery** (Bedrock AI)
8. **rss-ingest-task**
9. **position-manager** (needs Phase 17 update)

### Database
- 17 tables total
- All migrations 001-015 applied ✅
- Options columns exist ✅
- Phase 17 tables exist ✅

### Alpaca Account
- Paper trading account
- Options Level 3 (highest)
- Manual test order worked
- But no automated trades appearing

---

## ✅ WHAT'S COMPLETE (DON'T REDO!)

**Options Infrastructure:**
- ✅ Database schema (Migration 014) - 10 columns
- ✅ Dispatcher has Alpaca code
- ✅ Task definition has EXECUTION_MODE=ALPACA_PAPER
- ✅ Manual test order proven working

**Phase 17:**
- ✅ Database (Migration 015) - 2 tables
- ✅ Code complete - bar_fetcher.py, enhanced monitor.py
- ✅ Docker built and pushed to ECR
- ✅ Task definition registered
- ⏳ Just needs deployment (scheduler update)

**Documentation:**
- ✅ 10+ comprehensive guides created
- ✅ Architecture explained
- ✅ Deployment procedures documented

---

## ⚠️ WHAT NEEDS FIXING (YOUR JOB)

### Critical (Do First)
1. ❌ **AlpacaPaperBroker using fallback** - Debug why options execution fails
2. ❌ **check_system_status.py false errors** - Fix query format

### Optional (If Time)
3. ⏳ **Deploy Phase 17 position-manager** - Enable bar capture for AI learning
4. ⏳ **Fix security ticket** - ticker-discovery Lambda env vars

---

## 🧪 TESTING & VERIFICATION

### After Fixing Alpaca Integration

**Test 1: Check execution mode**
```python
import boto3, json
client = boto3.client('lambda', region_name='us-west-2')

r = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'sql': """
        SELECT execution_mode, COUNT(*)
        FROM dispatch_executions
        WHERE simulated_ts > NOW() - INTERVAL '1 hour'
        GROUP BY execution_mode
    """})
)

result = json.loads(json.load(r['Payload'])['body'])
print(result['rows'])

# Expected: ALPACA_PAPER (not SIMULATED_FALLBACK)
```

**Test 2: Check Alpaca dashboard**
- URL: https://app.alpaca.markets/paper/dashboard
- Should see positions beyond the manual test order
- Should see orders in order history

**Test 3: Verify data flow**
```bash
# Dispatcher logs should show Alpaca API calls
aws logs tail /ecs/ops-pipeline/dispatcher --region us-west-2 --since 5m | grep -i alpaca

# Should see:
# - "AlpacaPaperBroker initialized"
# - "Placing order via Alpaca"
# - "Order filled"
```

---

## 🎓 KEY INSIGHTS FROM THIS SESSION

### What Worked
1. **Separate ALTER statements** - Multi-column ALTER with CHECK fails silently
2. **DO $$ blocks** - Handle existing constraints gracefully
3. **Integration > new services** - Enhanced position_manager instead of new service

### What Didn't Work
4. **Lambda migrations with complex SQL** - psycopg2 has limitations
5. **Assuming success from logs** - Always verify actual database state

### Critical Knowledge
6. **Query format matters** - 'sql'/'rows' vs 'query'/'results'
7. **Services are scheduled** - EventBridge, not persistent ECS services
8. **Fallback is silent** - AlpacaPaperBroker fails → SimulatedBroker → no error

---

## 🆘 IF YOU GET STUCK

**Problem: Can't query database**
→ Check AI_AGENT_START_HERE.md for correct format

**Problem: Service not updating**
→ Check scheduler using correct task definition revision

**Problem: Logs empty**
→ Service may not have run yet (check schedule)

**Problem: Alpaca dashboard empty**
→ Confirm execution_mode=ALPACA_PAPER (not SIMULATED_FALLBACK)

---

## 📊 QUICK HEALTH CHECK

Run this first to understand current state:
```bash
# 1. Verify all services running
python3 scripts/verify_all_phases.py

# 2. Check recent trades
python3 << 'EOF'
import boto3, json
client = boto3.client('lambda', region_name='us-west-2')
r = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'sql': """
        SELECT ticker, execution_mode, simulated_ts::text
        FROM dispatch_executions
        ORDER BY simulated_ts DESC
        LIMIT 5
    """})
)
print(json.loads(json.load(r['Payload'])['body']))
EOF

# 3. Check Alpaca dashboard
open https://app.alpaca.markets/paper/dashboard
```

---

## 🎯 SUCCESS CRITERIA

**You're done when:**

1. ✅ New trades show execution_mode=ALPACA_PAPER (not SIMULATED_FALLBACK)
2. ✅ Trades appear in Alpaca dashboard automatically
3. ✅ check_system_status.py shows correct Phase 16 status
4. ✅ (Optional) option_bars table populating with Phase 17 data

---

**Good luck! All infrastructure is ready, just needs the Alpaca broker debugged.** 🚀

**Time estimate:** 2-3 hours if you follow the investigation steps above.

**Key file:** `services/dispatcher/alpaca/broker.py` - Find why _execute_option() returns None
