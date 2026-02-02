#!/bin/bash
# Documentation Consolidation Script
# Moves redundant/historical docs to archive, keeps only essential ones

set -e

DEPLOY_DIR="/home/nflos/workplace/inbound_aigen/deploy"
ARCHIVE_DIR="$DEPLOY_DIR/archive/historical_docs_2026-01-29"

echo "Creating archive directory..."
mkdir -p "$ARCHIVE_DIR"

echo "Moving historical/redundant documents to archive..."

# Phase documentation (historical snapshots)
mv "$DEPLOY_DIR/PHASE_1_2_DEPLOYMENT_COMPLETE.md" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$DEPLOY_DIR/PHASE_14_TICKER_DISCOVERY_SUCCESS.md" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$DEPLOY_DIR/PHASE_16_COMPLETE.md" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$DEPLOY_DIR/PHASE_16_LEARNING_INFRASTRUCTURE_DEPLOYED.md" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$DEPLOY_DIR/PHASE_16_STATUS_AND_NEXT_STEPS.md" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$DEPLOY_DIR/PHASE_17_OPTIONS_TELEMETRY_SPEC.md" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$DEPLOY_DIR/PHASE_17_PART2_AI_ALGORITHMS.md" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$DEPLOY_DIR/PHASE_17_IMPLEMENTATION_INTEGRATED.md" "$ARCHIVE_DIR/" 2>/dev/null || true

# Session handoff documents
mv "$DEPLOY_DIR/SESSION_COMPLETE_2026-01-28.md" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$DEPLOY_DIR/SESSION_HANDOFF_2026-01-27_AFTERNOON.md" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$DEPLOY_DIR/FINAL_STATUS_2026-01-28.md" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$DEPLOY_DIR/FINAL_DEPLOYMENT_STATUS_2026-01-27.md" "$ARCHIVE_DIR/" 2>/dev/null || true

# Deployment/status snapshots
mv "$DEPLOY_DIR/ALL_FEATURES_COMPLETE_2026-01-27.md" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$DEPLOY_DIR/ALPACA_OPTIONS_INTEGRATION_COMPLETE.md" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$DEPLOY_DIR/SIGNAL_FIX_DEPLOYED.md" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$DEPLOY_DIR/PAPER_TRADING_ENABLED.md" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$DEPLOY_DIR/PRODUCTION_LOGIC_V2_DEPLOYED.md" "$ARCHIVE_DIR/" 2>/dev/null || true

# Diagnosis/debugging history
mv "$DEPLOY_DIR/WHY_NO_TRADES_DIAGNOSIS_2026-01-27.md" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$DEPLOY_DIR/ANDES_MCP_FIX_2026-01-29.md" "$ARCHIVE_DIR/" 2>/dev/null || true

# Redundant design/strategy docs (info now in SYSTEM_COMPLETE_GUIDE)
mv "$DEPLOY_DIR/MULTI_ACCOUNT_DESIGN.md" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$DEPLOY_DIR/MULTI_ACCOUNT_STATUS.md" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$DEPLOY_DIR/TINY_ACCOUNT_DEPLOYMENT_STEPS.md" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$DEPLOY_DIR/SMALL_ACCOUNT_STRATEGY.md" "$ARCHIVE_DIR/" 2>/dev/null || true

# Redundant task/todo docs
mv "$DEPLOY_DIR/NEXT_SESSION_TASK_LIST.md" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$DEPLOY_DIR/TASK_FOR_NEXT_AGENT.md" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$DEPLOY_DIR/TASK_IMPLEMENT_PRODUCTION_IMPROVEMENTS.md" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$DEPLOY_DIR/CRITICAL_TODOS_BEFORE_LIVE_TRADING.md" "$ARCHIVE_DIR/" 2>/dev/null || true

# Redundant explanations (consolidated into main docs)
mv "$DEPLOY_DIR/PRODUCTION_LOGIC_V2_SUMMARY.md" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$DEPLOY_DIR/COMPLETE_TRADING_LOGIC_EXPLAINED.md" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$DEPLOY_DIR/TRADING_MODE_CLARIFICATION.md" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$DEPLOY_DIR/HOW_TO_APPLY_MIGRATIONS.md" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$DEPLOY_DIR/TRADE_ALERTS_SETUP.md" "$ARCHIVE_DIR/" 2>/dev/null || true

# Comparison docs (keep BEST_IN_CLASS, archive redundant)
mv "$DEPLOY_DIR/PRODUCTION_IMPROVEMENTS_NEEDED.md" "$ARCHIVE_DIR/" 2>/dev/null || true

# Create archive README
cat > "$ARCHIVE_DIR/README.md" << 'EOF'
# Historical Documentation Archive (2026-01-29)

This directory contains historical documentation that has been superseded by consolidated guides.

## Why These Were Archived

These documents served their purpose during development but are now redundant because:

1. **Phase Documentation** - Historical snapshots of specific deployment phases. Final state is in SYSTEM_COMPLETE_GUIDE.md
2. **Session Handoffs** - Notes from specific work sessions. No longer relevant.
3. **Status Snapshots** - Point-in-time system status. Current status is in main docs.
4. **Debugging History** - Specific troubleshooting sessions. Patterns captured in TROUBLESHOOTING_GUIDE.md
5. **Redundant Explanations** - Information now consolidated into fewer, better-organized docs.

## What to Read Instead

For current information, see the essential docs in `/deploy/`:
- **SYSTEM_COMPLETE_GUIDE.md** - Complete system overview
- **NEXT_SESSION_PHASES_3_4.md** - Implementation roadmap
- **RUNBOOK.md** - Operations guide
- **TROUBLESHOOTING_GUIDE.md** - Debugging reference
- **AI_PIPELINE_EXPLAINED.md** - Architecture details
- **MULTI_ACCOUNT_OPERATIONS_GUIDE.md** - Account management

## Retrieval

If you need information from these archived docs, they're preserved here. However, the essential information has been integrated into the active documentation.
EOF

echo ""
echo "✅ Consolidation complete!"
echo ""
echo "Remaining essential docs: $(ls -1 $DEPLOY_DIR/*.md 2>/dev/null | wc -l)"
echo "Archived docs: $(ls -1 $ARCHIVE_DIR/*.md 2>/dev/null | wc -l)"
echo ""
echo "Archive location: $ARCHIVE_DIR"
