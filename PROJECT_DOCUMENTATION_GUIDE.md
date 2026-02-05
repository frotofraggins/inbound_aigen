# 📍 PROJECT DOCUMENTATION GUIDE - Source of Truth
**Last Updated:** 2026-02-04 18:28 UTC

---

## 🎯 START HERE - Quick Navigation

### **For Current Status:**
→ **START_HERE_EXIT_FIX_STATUS.md**

### **For Task Tracking:**
→ **POSITION_EXIT_FIX_TASK_LIST.md** (Master tracker, 85% complete)

### **For Today's Work:**
→ **SESSION_COMPLETE_EXIT_FIX_2026-02-04.md**

---

## 📁 Root Directory (8 Essential Files)

### Navigation & Status (2 files)
1. **START_HERE_EXIT_FIX_STATUS.md** - Quick status and navigation
2. **PROJECT_DOCUMENTATION_GUIDE.md** - This file (master guide)

### Source of Truth (2 files)
3. **POSITION_EXIT_FIX_TASK_LIST.md** - Complete task list (85% done, 61/71)
4. **SESSION_COMPLETE_EXIT_FIX_2026-02-04.md** - Today's full summary

### Project Docs (2 files)
5. **README.md** - Project overview and setup
6. **AI_AGENT_START_HERE.md** - Agent instructions

### Future Work (2 files)
7. **FUTURE_ENHANCEMENT_TRAILING_STOPS.md** - Planned enhancements
8. **SYSTEMATIC_VERIFICATION_PLAN.md** - Testing methodology

---

## 📚 Documentation Folders

### docs/ (Technical Documentation)
**5 useful guides (KEEP):**
- **ECS_DOCKER_ARCHITECTURE.md** - Docker/ECS setup
- **OPTIONS_CLOSING_EXPLAINED.md** - Options trading mechanics
- **CLI_GUIDE.md** - Command-line tools
- **ARCHITECTURE_SECURITY_ANALYSIS.md** - Security review
- **GITHUB_SETUP.md** - Git configuration

### deploy/ (Deployment & Operations)
**11 useful guides (KEEP):**
- **RUNBOOK.md** - Operations playbook
- **TROUBLESHOOTING_GUIDE.md** - Common issues
- **HOW_OPTIONS_TRADING_WORKS.md** - Options mechanics
- **EXIT_LOGIC_EXPLAINED.md** - Exit algorithm
- **AI_PIPELINE_EXPLAINED.md** - AI system overview
- **SYSTEM_COMPLETE_GUIDE.md** - Full system guide
- **MULTI_ACCOUNT_OPERATIONS_GUIDE.md** - Account management
- **API_ENDPOINTS_REFERENCE.md** - API documentation
- **AWS_BASELINE_RESOURCES.md** - AWS infrastructure
- **DOCUMENTATION_INDEX.md** - Deploy docs index
- **COMPLIANCE_REVIEW.md** - Compliance notes

**Archives (already organized):**
- deploy/archive/phases_1-13/ - Phase completion docs
- deploy/archive/phase_15_journey/ - Options implementation
- deploy/archive/phase14_journey/ - AI learning setup
- deploy/archive/historical_docs_2026-01-29/ - Historical docs
- deploy/archive/incidents/ - Incident reports
- deploy/archive/session_2026-01-30/ - Jan 30 session

---

## 🗄️ Archive Folders

### archive/investigation_2026_02_04/ (19 files)
Today's exit fix investigation documents:
- CRITICAL_FINDINGS_EXIT_FIX_2026-02-04.md
- URGENT_POSITION_MANAGER_FAILURE_2026-02-04.md
- ROOT_CAUSE_IDENTIFIED_2026-02-04.md
- ACTUAL_ROOT_CAUSE_FINAL_2026-02-04.md
- EXIT_FIX_DEPLOYED_SUCCESS_2026-02-04.md
- FINAL_STATUS_EXIT_FIX_VERIFIED_2026-02-04.md
- And 13 more intermediate investigation files

**Consolidated into:** SESSION_COMPLETE_EXIT_FIX_2026-02-04.md

### archive/old_sessions/ (28+ files)
Previous session documents:
- Jan 29, Feb 3 session summaries
- Phase 3 migration documents
- Old fix and diagnostic docs
- Bug reports and resolutions
- Deployment histories

**Why archived:** Superseded by current work

### archive/status_docs_2026/ (existing)
- Historical status reports
- Earlier session summaries

---

## 🎯 Current Project Status

### Exit Fix ✅
- **Deployed:** 18:13 UTC (verified working)
- **Code:** 1-minute checks, -40%/+80% exits, 30-min hold
- **Test:** INTC Position 606 monitored every minute
- **Protection:** Working - position not exiting at -4.66%

### Documentation ✅
- **Root files:** 8 essential (was 44+)
- **Archived:** 36+ files organized
- **Reduction:** 82% fewer files in root
- **Result:** Clean, navigable structure

### Remaining Work ⏳
1. Monitor INTC for 30-minute hold (until 18:44 UTC)
2. Fix instrument_type detection (options → STOCK)
3. Fix position_history inserts (learning data)
4. Fix option bars API 403 errors

---

## 📖 How to Use This Documentation

### I Need Current Status
→ START_HERE_EXIT_FIX_STATUS.md

### I Need Task List
→ POSITION_EXIT_FIX_TASK_LIST.md

### I Need Today's Summary
→ SESSION_COMPLETE_EXIT_FIX_2026-02-04.md

### I Need Technical Docs
→ docs/ folder (5 guides)

### I Need Deployment Info
→ deploy/ folder (11 guides + RUNBOOK.md)

### I Need Historical Context
→ archive/ folders (organized by topic/date)

---

## 🔧 Common Tasks

### Monitor Live Position
```bash
aws logs tail /ecs/ops-pipeline/position-manager-service --follow --region us-west-2
```

### Deploy Changes
```bash
./scripts/rebuild_and_deploy_position_manager.sh
```

### Check Service Status
```bash
aws ecs describe-services \
  --cluster ops-pipeline-cluster \
  --services position-manager-service \
  --region us-west-2
```

---

## 📊 Documentation Statistics

### Before Cleanup
- Root markdown files: 44+
- Duplicated information
- Hard to find current status
- Confusing navigation

### After Cleanup
- Root markdown files: 8 essential
- Single source of truth
- Clear navigation with START_HERE
- Organized archives

### Result
- ✅ 82% reduction in root files
- ✅ All historical context preserved
- ✅ Easy to navigate
- ✅ No duplicate information

---

**MASTER GUIDE:** This file explains entire documentation structure

**SOURCE OF TRUTH:** POSITION_EXIT_FIX_TASK_LIST.md for tasks

**QUICK START:** START_HERE_EXIT_FIX_STATUS.md for navigation

**TODAY'S WORK:** SESSION_COMPLETE_EXIT_FIX_2026-02-04.md for summary
