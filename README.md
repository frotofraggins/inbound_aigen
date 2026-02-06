# Inbound AI Options Trading System

**Production-Ready AI-Powered Options Trading Platform**  
**Current Status:** 85% Complete | Paper Trading Enabled | Multi-Account Support

---

## 🎯 Quick Start

### For New Users
1. Read [`AI_AGENT_START_HERE.md`](AI_AGENT_START_HERE.md) - Onboarding guide
2. Read [`CURRENT_SYSTEM_STATUS.md`](CURRENT_SYSTEM_STATUS.md) - Current state
3. Read [`deploy/SYSTEM_COMPLETE_GUIDE.md`](deploy/SYSTEM_COMPLETE_GUIDE.md) - Complete overview

### For Operations
- **Deploy/Monitor:** [`deploy/RUNBOOK.md`](deploy/RUNBOOK.md)
- **Troubleshoot:** [`deploy/TROUBLESHOOTING_GUIDE.md`](deploy/TROUBLESHOOTING_GUIDE.md)
- **Multi-Account:** [`deploy/MULTI_ACCOUNT_OPERATIONS_GUIDE.md`](deploy/MULTI_ACCOUNT_OPERATIONS_GUIDE.md)

### For Development
- **Next Features:** [`deploy/NEXT_SESSION_PHASES_3_4.md`](deploy/NEXT_SESSION_PHASES_3_4.md)
- **Architecture:** [`deploy/AI_PIPELINE_EXPLAINED.md`](deploy/AI_PIPELINE_EXPLAINED.md)

---

## 📚 Core Documentation (3 Essential Files)

### 🌟 **Start Here - Read These First**

1. **[SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md)** ⭐ **COMPLETE TECHNICAL REFERENCE**
   - Complete system architecture and how it works
   - All 11 services explained
   - Trading strategy and decision logic
   - AWS infrastructure details
   - Database schema
   - Performance metrics

2. **[OPERATIONS_GUIDE.md](OPERATIONS_GUIDE.md)** 🔧 **HOW TO DEPLOY & MONITOR**
   - Daily operations checklist
   - Deploying code changes (step-by-step)
   - Deploying database migrations (PROVEN method)
   - Monitoring and health checks
   - Troubleshooting common issues
   - Emergency procedures

3. **[CURRENT_STATUS.md](CURRENT_STATUS.md)** 📊 **FEB 6, 2026 STATE**
   - Current system status (10/11 features = 91%)
   - What's working, what's not
   - Recent changes (Feb 4-6)
   - Trading performance analysis
   - Open positions and monitoring
   - Next steps

### 📖 **Supporting Documentation**

4. **[AI_AGENT_START_HERE.md](AI_AGENT_START_HERE.md)** - AI agent onboarding guide
5. **[docs/ECS_DOCKER_ARCHITECTURE.md](docs/ECS_DOCKER_ARCHITECTURE.md)** - AWS infrastructure
6. **[docs/DATABASE_ACCESS_GUIDE.md](docs/DATABASE_ACCESS_GUIDE.md)** - Database queries
7. **[deploy/RUNBOOK.md](deploy/RUNBOOK.md)** - Additional operations reference
8. **[deploy/TROUBLESHOOTING_GUIDE.md](deploy/TROUBLESHOOTING_GUIDE.md)** - Problem resolution
9. **[deploy/AI_PIPELINE_EXPLAINED.md](deploy/AI_PIPELINE_EXPLAINED.md)** - AI/ML details

> **Note:** 35 historical status documents archived to `archive/status_docs_feb_2026/`

---

## 🏗️ System Architecture

### 10 Production Services (All Active)
```
┌─────────────────────────────────────────────────────────────┐
│                   DATA INGESTION LAYER                       │
├─────────────────────────────────────────────────────────────┤
│ 1. RSS Ingest (1min)      → News articles                   │
│ 2. Telemetry (1min)       → Price/volume data (Alpaca)      │
│ 3. Ticker Discovery (weekly) → AI watchlist (Bedrock)       │
├─────────────────────────────────────────────────────────────┤
│                   PROCESSING LAYER                           │
├─────────────────────────────────────────────────────────────┤
│ 4. Classifier (5min)      → Sentiment analysis (FinBERT)    │
│ 5. Feature Computer (1min) → Technical indicators          │
│ 6. Watchlist Engine (5min) → Scoring & ranking             │
├─────────────────────────────────────────────────────────────┤
│                   DECISION LAYER                             │
├─────────────────────────────────────────────────────────────┤
│ 7. Signal Engine (1min)   → BUY/SELL signals               │
│ 8. Dispatcher (1min) × 2  → Risk gates + execution         │
│    ├─ Large account ($121K) - Tier-based sizing            │
│    └─ Tiny account ($1K)    - Conservative sizing           │
├─────────────────────────────────────────────────────────────┤
│                   MONITORING LAYER                           │
├─────────────────────────────────────────────────────────────┤
│ 9. Position Manager (1min) → Exit monitoring               │
└─────────────────────────────────────────────────────────────┘
```

### Data Sources
- **News:** RSS feeds (configurable via SSM Parameter Store)
- **Market Data:** Alpaca Market Data API (1-minute bars)
- **AI/ML:** 
  - AWS Bedrock Claude 3.5 Sonnet (ticker discovery)
  - FinBERT (sentiment analysis)
- **Fundamentals:** NOT CURRENTLY USED (technical trading only)

### Technology Stack
- **Compute:** AWS ECS Fargate (Docker containers)
- **Scheduling:** EventBridge Scheduler (cron-based)
- **Storage:** PostgreSQL (RDS), S3 (artifacts)
- **Broker:** Alpaca Markets (paper trading API)
- **Monitoring:** CloudWatch Logs
- **IaC:** Task definitions + bash deployment scripts

---

## 📈 Current Performance

### System Health
- ✅ **All 10 services ENABLED and running**
- ✅ **Multi-account support** (2 dispatcher instances)
- ✅ **Position monitoring** active
- ✅ **AI pipeline** generating signals every minute

### Trading Results (Paper Trading)
- **Large Account:** $93K → $121K (+30% growth)
- **META Position:** +100% profit ($11-14K gain)
- **Executions Today:** 28 trades
- **Zero Errors:** Both accounts operational

### Quality Metrics
- **System Grade:** B+ (85%)
- **Contract Selection:** A- (90%)
- **Position Sizing:** A- (90%)
- **Risk Management:** B (80%)
- **Exit Strategies:** C (65%) ← Phase 3 target
- **Greeks/IV:** C+ (70%) ← Phase 3 target

---

## 🚀 Phases 3-4 Roadmap (To Reach A+)

**Time to Complete:** 5-7 hours  
**Target Grade:** A+ (100%)

### Phase 3: Advanced Exit Management
- Trailing stop losses
- Partial exits (50% at +50% profit)
- Position rolling (near expiration)
- Enhanced Greeks monitoring

### Phase 4: Options Selection Optimization
- IV Rank filtering (only trade IV > 30th percentile)
- Dynamic contract selection based on IV
- Kelly Criterion position sizing
- Options-specific risk metrics

**Full Implementation Guide:** See [`deploy/NEXT_SESSION_PHASES_3_4.md`](deploy/NEXT_SESSION_PHASES_3_4.md)

---

## 🎓 Key Features

### ✅ Implemented (Phase 1-2)
- Multi-tier risk system (day trade vs swing)
- Account-based position sizing (5-20% of capital)
- Quality scoring algorithm for contract selection
- Real-time market data (1-minute updates)
- Sentiment-adjusted confidence scores
- 11 risk gates before every trade
- Multi-account support (different risk profiles)
- Position exit monitoring

### ⏳ Coming Next (Phase 3-4)
- Trailing stop losses
- IV Rank filtering
- Partial profit taking
- Position rolling
- Kelly Criterion
- Enhanced Greeks analysis

---

## 📞 Support & Resources

### Monitoring Commands
```bash
# Check system health
aws scheduler list-schedules --region us-west-2 \
  --query 'Schedules[?contains(Name, `ops-pipeline`)].{Name: Name, State: State}' \
  --output table

# View recent logs (any service)
aws logs tail /ecs/ops-pipeline/<service-name> \
  --region us-west-2 --since 10m --follow

# Check dispatcher activity
aws logs tail /ecs/ops-pipeline/dispatcher \
  --region us-west-2 --since 5m | grep "Buying power"
```

### Common Tasks
- **Enable/Disable Trading:** `scripts/switch_trading_mode.sh`
- **Check System Status:** `scripts/check_system_status.py`
- **View Positions:** Check Alpaca dashboard
- **Deploy Updates:** See RUNBOOK.md

---

## 🏆 Best Practices

### This System is Built For
✅ Short-term options trading (1-7 days)  
✅ Technical + sentiment analysis  
✅ Automated execution with human oversight  
✅ Paper trading validation before live deployment  

### This System is NOT For
❌ Long-term investing  
❌ Fundamental analysis (no SEC data integration)  
❌ High-frequency trading (1-minute granularity)  
❌ Unmonitored autonomous trading  

---

## 📁 Project Structure

```
inbound_aigen/
├── services/           # 10 microservices (ECS tasks)
│   ├── dispatcher/           # Trade execution (2 instances)
│   ├── position_manager/     # Exit monitoring
│   ├── signal_engine_1m/     # Signal generation
│   ├── classifier_worker/    # Sentiment (FinBERT)
│   ├── feature_computer_1m/  # Technical indicators
│   ├── telemetry_ingestor_1m/ # Market data
│   ├── rss_ingest_task/      # News ingestion
│   ├── ticker_discovery/     # AI watchlist (Bedrock)
│   ├── watchlist_engine_5m/  # Opportunity scoring
│   └── [7 Lambda functions]  # Support services
├── deploy/             # 12 essential docs + task definitions
├── scripts/           # Deployment & verification scripts
├── db/migrations/     # PostgreSQL schema (12 migrations)
└── config/            # Trading parameters (position sizing, etc.)
```

---

## 🔒 Security & Compliance

- **Paper Trading Only:** No real money at risk
- **API Keys:** Stored in AWS Secrets Manager
- **IAM Roles:** Least-privilege access
- **Audit Trail:** All trades logged to database
- **Risk Gates:** 11 checks before every trade
- **Compliance:** See [COMPLIANCE_REVIEW.md](deploy/COMPLIANCE_REVIEW.md)

---

## 📜 License & Disclaimer

**For educational and research purposes only.**  
This system is in paper trading mode. Do not use with real money without proper testing, regulatory compliance, and risk management protocols.

Trading options involves substantial risk of loss. Past performance does not guarantee future results.

---

## 🤝 Contributing

For system improvements:
1. Read [NEXT_SESSION_PHASES_3_4.md](deploy/NEXT_SESSION_PHASES_3_4.md)
2. Follow the implementation guide
3. Test thoroughly in paper trading
4. Document changes in relevant guides

---

**Last Updated:** 2026-02-06  
**System Version:** v16 (91% Complete - Trailing Stops Active)  
**Next Milestone:** 50 trades for AI learning activation
