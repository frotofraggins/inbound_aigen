# 📚 Documentation Structure - Clean and Organized

## 🎯 START HERE

**New to this project?** Read these 3 documents in order:

1. **START_HERE_EXIT_FIX_STATUS.md** - Quick navigation and current status
2. **POSITION_EXIT_FIX_TASK_LIST.md** - Master task tracker (85% complete)
3. **SESSION_COMPLETE_EXIT_FIX_2026-02-04.md** - Today's work summary

---

## 📁 Current Active Documents (Root Directory)

### Primary Documentation
- **START_HERE_EXIT_FIX_STATUS.md** - Navigation guide and quick status
- **POSITION_EXIT_FIX_TASK_LIST.md** - Complete task list and progress tracking
- **SESSION_COMPLETE_EXIT_FIX_2026-02-04.md** - Today's session summary
- **README.md** - Project overview and setup
- **AI_AGENT_START_HERE.md** - Agent instructions

### Working Scripts
- **scripts/rebuild_and_deploy_position_manager.sh** - Deploy position manager
- **scripts/investigate_exit_fix.py** - Investigation automation
- **scripts/check_intc_position.py** - Position checking
- **scripts/monitor_exit_fix.py** - Monitoring tool
- **scripts/complete_system_test.sh** - System verification

### Future Work
- **FUTURE_ENHANCEMENT_TRAILING_STOPS.md** - Planned enhancements
- **SYSTEMATIC_VERIFICATION_PLAN.md** - Verification approach

---

## 📦 Archived Documents

### archive/investigation_2026_02_04/
**Investigation documents from today's exit fix debugging** (kept for reference):
- CRITICAL_FINDINGS_EXIT_FIX_2026-02-04.md
- URGENT_POSITION_MANAGER_FAILURE_2026-02-04.md
- ROOT_CAUSE_IDENTIFIED_2026-02-04.md (first, incorrect diagnosis)
- ACTUAL_ROOT_CAUSE_FINAL_2026-02-04.md (correct diagnosis)
- EXIT_FIX_DEPLOYED_SUCCESS_2026-02-04.md
- FINAL_STATUS_EXIT_FIX_VERIFIED_2026-02-04.md

**Why archived:** All information consolidated into SESSION_COMPLETE_EXIT_FIX_2026-02-04.md

### archive/old_sessions/
**Documents from previous work sessions** (before today):
- Session summaries from Jan 29, Feb 3
- Old fix documents
- Previous issue investigations  
- Historical status reports

**Why archived:** Superseded by current work

### archive/status_docs_2026/
**Earlier status documents** (from various dates):
- Contains older session reports
- Historical issue tracking
- Previous deployment records

---

## 🎯 Current Status (Quick Reference)

### Exit Fix
- **Status:** ✅ Deployed and working
- **Verification:** Live position (INTC 606) being monitored
- **Code:** 1-minute checks, -40%/+80% exits, 30-min hold
- **Next:** Monitor until 18:44 UTC (30-min mark)

### Remaining Issues
1. Fix instrument_type detection (options → STOCK)
2. Fix position_history inserts (no learning data)
3. Fix option bars API 403 errors

---

## 📖 How to Use This Documentation

### For Quick Status
→ Read **START_HERE_EXIT_FIX_STATUS.md**

### For Task Tracking
→ Read **POSITION_EXIT_FIX_TASK_LIST.md**

### For Today's Work
→ Read **SESSION_COMPLETE_EXIT_FIX_2026-02-04.md**

### For Deployment
→ Use **scripts/rebuild_and_deploy_position_manager.sh**

### For Investigation History
→ Check **archive/investigation_2026_02_04/**

---

## 🔧 Key Commands

### Monitor Live Position
```bash
aws logs tail /ecs/ops-pipeline/position-manager-service --follow --region us-west-2
```

### Check Service Status
```bash
aws ecs describe-services \
  --cluster ops-pipeline-cluster \
  --services position-manager-service \
  --region us-west-2
```

### Deploy Changes
```bash
./scripts/rebuild_and_deploy_position_manager.sh
```

---

## 📊 Document Cleanup Summary

### Before Cleanup
- **60+ markdown files** in root directory
- Duplicate information across many files
- Hard to find current status
- Confusing for new readers

### After Cleanup
- **3 primary documents** in root (START_HERE, TASK_LIST, SESSION_COMPLETE)
- **Investigation docs archived** (13 files moved)
- **Old sessions archived** (7+ files moved)
- **Clear navigation** with START_HERE guide

### Result
- ✅ Easy to find current status
- ✅ Clear task tracking
- ✅ Historical context preserved
- ✅ Less confusion

---

**RECOMMENDATION:** Always start with START_HERE_EXIT_FIX_STATUS.md for navigation
