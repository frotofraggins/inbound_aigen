# Next Session Task List

**Created:** 2026-01-29  
**Session Length:** 10+ hours  
**Context:** 65% used  

---

## 🎯 MISSION: Fix Alpaca Integration + Complete Phase 17

### Priority 1: Enable Real Alpaca Trading (P0 - 1-2 hours)

**Problem:** All trades using SIMULATED_FALLBACK despite EXECUTION_MODE=ALPACA_PAPER

**Root Cause:** AlpacaPaperBroker tries to execute options but fails → falls back to simulation

**Evidence:**
- 31 trades executed, ALL SIMULATED_FALLBACK
- Dispatcher logs show: "simulated": 1 (not "alpaca": 1)
- Task definition has EXECUTION_MODE=ALPACA_PAPER (correct)
- Manual test order worked (SPY260130C00609000)

**Investigation Steps:**
```bash
# 1. Check full dispatcher logs during execution
aws logs tail /ecs/ops-pipeline/dispatcher --region us-west-2 --since 30m | grep -B10 "SIMULATED_FALLBACK"

# Look for:
# - "No suitable option contract found"
# - "AlpacaPaperBroker failed"
# - API errors from Alpaca

# 2. Check AlpacaPaperBroker code
cat services/dispatcher/alpaca/broker.py | grep -A20 "def _execute_option"

# 3. Check option chain fetching
cat services/dispatcher/alpaca/options.py | grep -A20 "def get_option_chain"
```

**Likely Fixes:**
1. **Options API returns no contracts** - Relax strike/expiration filters
2. **Validation too strict** - Lower min_volume, max_spread requirements
3. **API credentials issue** - Verify Alpaca key has options access

**Files to Check:**
- `services/dispatcher/alpaca/broker.py` - Execution logic
- `services/dispatcher/alpaca/options.py` - Contract fetching
- `services/dispatcher/risk/gates.py` - Risk validation

---

### Priority 2: Fix Phase 16 Table Check Error (P1 - 30 min)

**Error:**
```
⏳ Phase 16 snapshot columns not yet added
❌ learning_recommendations table missing
```

**This is a FALSE ERROR from outdated check script!**

**Verification (from earlier):**
```sql
-- These columns DO exist (verified earlier):
SELECT column_name FROM information_schema.columns
WHERE table_name = 'dispatch_recommendations'
  AND column_name IN ('features_snapshot', 'sentiment_snapshot');
-- Returns 2 rows ✅

-- This table DOES exist:
SELECT tablename FROM pg_tables WHERE tablename = 'learning_recommendations';
-- Returns 1 row ✅
```

**Fix:**
Update `scripts/check_system_status.py` to use correct query format:
- Use `'sql'` key (not `'query'`)
- Use `'rows'` response (not `'results'`)
- See `AI_AGENT_START_HERE.md` for correct format

---

### Priority 3: Complete Phase 17 Deployment (P2 - 30 min)

**Status:** Code 100% complete, Docker in ECR, needs deployment

**What's Ready:**
- Migration 015 applied ✅
- option_bars and iv_surface tables exist ✅
- bar_fetcher.py code complete ✅
- monitor.py enhanced ✅
- Docker image pushed to ECR ✅
- Task definition registered (position-manager:2) ✅

**Deployment Method:**
Position manager runs via **EventBridge Scheduler** (not ECS service)

**Steps:**
```bash
# 1. Find the scheduler
aws scheduler get-schedule --name ops-pipeline-position-manager --region us-west-2

# 2. Update to use new task definition
# (May need to delete and recreate if immutable)

# 3. Or: The service may not exist yet - check documentation in deploy/PHASE_17_IMPLEMENTATION_INTEGRATED.md
```

**Reference:** `deploy/PHASE_17_IMPLEMENTATION_INTEGRATED.md` (complete guide)

---

### Priority 4: Security Issue (P2 - 1 hour)

**NOC-CAZ Ticket:** ops-ticker-discovery Lambda has secrets in environment variables

**Fix:**
1. Check what secrets are in env vars
2. Move to AWS Secrets Manager
3. Update code to fetch from Secrets Manager
4. Close ticket

---

## 📚 KEY DOCUMENTS FOR NEXT AGENT

### Start Here (MUST READ)
1. **AI_AGENT_START_HERE.md** ⭐
   - Correct database query format (`'sql'` not `'query'`)
   - Table names reference
   - Common pitfalls
   - Quick diagnostic commands

### System Understanding
2. **CURRENT_SYSTEM_STATUS.md**
   - What's deployed (9 services)
   - Current revisions
   - Infrastructure overview

3. **TROUBLESHOOTING_GUIDE.md**
   - How to diagnose issues
   - Service log locations
   - Database access methods

### Implementation Guides
4. **deploy/PHASE_17_IMPLEMENTATION_INTEGRATED.md** ⭐
   - Complete Phase 17 deployment steps
   - Code already written, just needs deployment

5. **deploy/HOW_TO_APPLY_MIGRATIONS.md**
   - How to apply database migrations
   - Lambda vs ECS methods

6. **deploy/COMPLETE_TRADING_LOGIC_EXPLAINED.md**
   - How signal generation works
   - Risk gates explained
   - Trading thresholds

---

## 🏗️ ARCHITECTURE OVERVIEW

### Lambda Functions (Simple Operations)
**Purpose:** Database admin, simple HTTP
- db_migration_lambda (DDL)
- db_query_lambda (SELECT only)
- db_cleanup_lambda
- inbound_dock_lambda (RSS)
- healthcheck_lambda
- trade_alert_lambda

### Docker/ECS Services (AI & Trading)
**Purpose:** Complex AI, ML models, trading

**Scheduled via EventBridge:**
1. **signal-engine-1m** - Generates trading signals (revision 11)
2. **dispatcher** - Executes trades (revision 10) ← **USING FALLBACK MODE**
3. **watchlist-engine-5m** - Scores opportunities
4. **telemetry-ingestor-1m** - Fetches price data
5. **feature-computer-1m** - Computes indicators
6. **classifier-worker** - FinBERT sentiment
7. **ticker-discovery** - Bedrock AI recommendations
8. **position-manager** - Monitors positions (needs Phase 17 deployment)
9. **rss-ingest-task** - News collection

**Key:** All AI work in Docker/ECS, not Lambda!

---

## 🔧 DEPLOYMENT METHODS

### For Database Changes
```bash
# 1. Edit services/db_migration_lambda/lambda_function.py
# 2. Add migration to MIGRATIONS dict
# 3. Deploy:
cd services/db_migration_lambda
rm -rf package *.zip
mkdir package
pip install -q -r requirements.txt -t package/
cp lambda_function.py package/
cd package && zip -q -r ../migration_lambda.zip . && cd ..
aws lambda update-function-code \
  --function-name ops-pipeline-db-migration \
  --zip-file fileb://migration_lambda.zip \
  --region us-west-2

# 4. Run migration:
aws lambda invoke \
  --function-name ops-pipeline-db-migration \
  --region us-west-2 \
  --payload '{}' \
  /tmp/result.json
```

### For Service Changes
```bash
# 1. Build Docker image
cd services/SERVICE_NAME
docker build -t ops-pipeline/SERVICE_NAME:new-version .

# 2. Push to ECR
aws ecr get-login-password --region us-west-2 | \
  docker login --username AWS --password-stdin \
  160027201036.dkr.ecr.us-west-2.amazonaws.com

docker tag ops-pipeline/SERVICE_NAME:new-version \
  160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/SERVICE_NAME:new-version

docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/SERVICE_NAME:new-version

# 3. Update task definition JSON file
# Edit deploy/SERVICE_NAME-task-definition.json
# Change image tag to :new-version

# 4. Register new task definition
aws ecs register-task-definition \
  --cli-input-json file://deploy/SERVICE_NAME-task-definition.json \
  --region us-west-2

# 5. Update scheduler (for scheduled services)
aws scheduler update-schedule \
  --name ops-pipeline-SERVICE_NAME \
  --target '{"Arn": "...with new task definition revision..."}'
  --region us-west-2
```

---

## 🔍 HOW TO VERIFY SYSTEMS

### Check Service is Running
```bash
# For scheduled services (most of them)
aws scheduler get-schedule --name ops-pipeline-SERVICE_NAME --region us-west-2

# Check logs
aws logs tail /ecs/ops-pipeline/SERVICE_NAME --region us-west-2 --since 5m
```

### Check Database
```python
# ALWAYS use this format (see AI_AGENT_START_HERE.md):
import boto3, json
client = boto3.client('lambda', region_name='us-west-2')

r = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'sql': 'YOUR SQL HERE'})  # 'sql' not 'query'!
)

result = json.loads(json.load(r['Payload'])['body'])
rows = result.get('rows', [])  # 'rows' not 'results'!
```

### Check Alpaca
- Dashboard: https://app.alpaca.markets/paper/dashboard
- Or use scripts/check_system_status.py (but query format is wrong in it)

---

## 📊 CURRENT DEPLOYMENT STATUS

### What's Working
- ✅ All 9 services deployed and running
- ✅ Generating 767 signals per day
- ✅ 6 trades executed today
- ✅ Options schema complete (10 columns)
- ✅ Phase 17 database ready (2 new tables)

### What's Using Fallback
- ❌ Dispatcher using SIMULATED_FALLBACK (not ALPACA_PAPER)
- Configured for Alpaca but execution failing
- Falls back to simulation when options logic fails

### What's Not Deployed
- ⏳ Phase 17 position-manager enhancement (code in Git, Docker in ECR)
- ⏳ Signal engine with snapshots (revision 12 exists but not deployed)

---

## 🐛 KNOWN BUGS

### Bug 1: AlpacaPaperBroker Fallback
**Symptom:** All trades SIMULATED_FALLBACK  
**Root Cause:** Options execution fails in AlpacaPaperBroker._execute_option()  
**Impact:** No trades appear in Alpaca dashboard  
**Fix:** Debug why option contracts not found/validated  

### Bug 2: check_system_status.py Wrong Query Format  
**Symptom:** Reports Phase 16 tables missing (false)  
**Root Cause:** Uses 'query'/'results' instead of 'sql'/'rows'  
**Impact:** Misleading error messages  
**Fix:** Update script to use correct format  

---

## 💾 FILES MODIFIED THIS SESSION

**Migrations:**
- services/db_migration_lambda/lambda_function.py
  - Migration 014 (options columns - separate ALTER)
  - Migration 015 (option_bars, iv_surface tables)

**Phase 17:**
- services/position_manager/bar_fetcher.py (NEW)
- services/position_manager/monitor.py (ENHANCED)
- services/position_manager/db.py (ENHANCED)
- services/position_manager/main.py (ENHANCED)
- services/position_manager/requirements.txt (UPDATED)
- services/position_manager/Dockerfile (FIXED)
- deploy/position-manager-task-definition.json (UPDATED)

**Documentation:**
- 8 new comprehensive documents in deploy/

---

## 🎓 LESSONS FOR NEXT AGENT

### Database Migrations
1. **Multi-column ALTER with CHECK fails silently**
   - Use separate ALTER statements (Migration 014 pattern)
   - Always verify columns exist after migration

2. **Lambda migrations have constraints**
   - Good for CREATE TABLE, ALTER TABLE
   - Check for existing constraints before adding
   - Use DO $$ blocks for conditional logic

### Query Format
**CRITICAL:** db-query Lambda uses specific format:
```python
# CORRECT:
Payload=json.dumps({'sql': 'SELECT...'})
result.get('rows', [])

# WRONG:
Payload=json.dumps({'query': 'SELECT...'})
result.get('results', [])
```

### Deployment Architecture
- Lambda = Simple ops (migrations, queries)
- Docker/ECS = AI & trading logic
- Scheduled via EventBridge (not persistent services)

---

## 📋 IMMEDIATE TODO LIST

**Before starting any fixes, verify current state:**

- [ ] Run `python3 scripts/verify_all_phases.py`
- [ ] Check Alpaca dashboard for positions
- [ ] Verify database columns with correct query format

**Then fix in order:**

1. [ ] **Fix check_system_status.py** (30 min)
   - Update query format to 'sql'/'rows'
   - Verify Phase 16 tables actually exist
   
2. [ ] **Debug AlpacaPaperBroker** (1-2 hours)
   - Find why options execution fails
   - Check option chain API responses
   - Relax validation if needed
   - Verify trades go to Alpaca

3. [ ] **Complete Phase 17 Deployment** (30 min)
   - Deploy position-manager with bar capture
   - Verify bars accumulating in option_bars table

4. [ ] **Security Fix** (1 hour)
   - Fix ticker-discovery Lambda env vars
   - Move secrets to Secrets Manager

---

## 📖 REFERENCE DOCUMENTS (IN ORDER OF IMPORTANCE)

### Must Read First
1. **AI_AGENT_START_HERE.md** - Query format, common mistakes
2. **CURRENT_SYSTEM_STATUS.md** - What's deployed
3. **TROUBLESHOOTING_GUIDE.md** - Diagnostic procedures

### For Fixes
4. **deploy/ALPACA_OPTIONS_INTEGRATION_COMPLETE.md** - How Alpaca integration works
5. **deploy/HOW_TO_APPLY_MIGRATIONS.md** - Migration procedures
6. **deploy/PHASE_17_IMPLEMENTATION_INTEGRATED.md** - Phase 17 deployment

### For Understanding
7. **deploy/COMPLETE_TRADING_LOGIC_EXPLAINED.md** - Trading logic
8. **README.md** - System overview

---

## ✅ WHAT'S COMPLETE (DON'T REDO)

- ✅ Options schema (Migration 014) - 10 columns verified
- ✅ Phase 17 database (Migration 015) - 2 tables created
- ✅ Phase 17 code - All files written, Docker built
- ✅ All services deployed and running
- ✅ Generating 767 signals per day
- ✅ Risk gates functioning correctly

---

## ⚠️ WHAT NEEDS FIXING (DO THIS)

- ❌ AlpacaPaperBroker falling back to simulation
- ❌ check_system_status.py using wrong query format
- ⏳ Phase 17 position-manager needs deployment
- ⏳ Security ticket (ticker-discovery Lambda)

---

## 🚀 SUCCESS METRICS

**You'll know it's working when:**

1. **Trades show in Alpaca dashboard** (not just database)
2. **Execution mode = ALPACA_PAPER** (not SIMULATED_FALLBACK)
3. **Email alerts sent** (trade notifications)
4. **option_bars table populated** (if Phase 17 deployed)

---

## 📞 GETTING HELP

**If stuck, check these in order:**

1. Service logs: `aws logs tail /ecs/ops-pipeline/SERVICE_NAME --region us-west-2 --since 10m`
2. Database query: Use format from AI_AGENT_START_HERE.md
3. Alpaca dashboard: https://app.alpaca.markets/paper/dashboard
4. Documentation: All specs in deploy/ directory

**Common Issues:**
- Expired credentials: Run ada cred update
- Wrong query format: Check AI_AGENT_START_HERE.md
- Service not updating: Force new deployment with --force-new-deployment

---

**Session handoff complete. All information documented. Good luck!** 🚀
