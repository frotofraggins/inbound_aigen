# Ops Pipeline - AWS Deployment Master Plan

## Architecture Confirmation

**✅ APPROVED ARCHITECTURE:**

```
┌─────────────────────────────────────────────────────────────────┐
│                         AWS CLOUD                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────┐      ┌──────────────────┐                      │
│  │ EventBridge │──1m──▶│ RSS Ingest       │                      │
│  │ Schedules   │      │ Lambda           │────┐                 │
│  │             │──5m──▶│ Telemetry Lambda │    │                 │
│  │             │──5m──▶│ Signal Engine    │    │                 │
│  │             │──5m──▶│ Watchdog Lambda  │    ▼                 │
│  └─────────────┘      └──────────────────┘  ┌──────────────┐   │
│                                               │              │   │
│  ┌──────────────────┐                        │  RDS         │   │
│  │ ECS/Container    │◀───────────────────────│  Postgres    │   │
│  │ Services         │                        │  (Central    │   │
│  │                  │                        │   Store)     │   │
│  │ • FinBERT Worker │───────────────────────▶│              │   │
│  │ • Dispatcher     │                        └──────────────┘   │
│  └──────────────────┘                               │            │
│                                                      │            │
│  ┌──────────────────┐                        ┌──────▼──────┐   │
│  │ Secrets Manager  │                        │ S3 Backups  │   │
│  │ • DB Credentials │                        │ • pg_dumps  │   │
│  └──────────────────┘                        └─────────────┘   │
│                                                                   │
│  ┌──────────────────┐      ┌──────────────────┐                │
│  │ SSM Parameters   │      │ CloudWatch       │                │
│  │ • Config Values  │      │ • Logs + Alarms  │                │
│  └──────────────────┘      └──────────────────┘                │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow Through the System

```
RSS Feed → [Lambda Ingest] → Raw Events DB
                                    ↓
                            [FinBERT Worker]
                                    ↓
                            Classified Events DB ←─┐
                                    ↓              │
Market API → [Telemetry Lambda] → Telemetry DB    │
                                    ↓              │
                            [Signal Engine] ───────┘
                                    ↓
                            Recommendations DB
                                    ↓
                            [Dispatcher]
                                    ↓
                            Executed Trades DB
```

## Why Modular Architecture? (Separation of Concerns)

### 1. **Ingestion Separated** (RSS Lambda + Telemetry Lambda)
**Why:** 
- **Independent Failure Domains**: If RSS parsing breaks, market data still flows
- **Different Polling Rates**: RSS (1min), Market (5min) - optimized per source
- **Scalability**: Can add new data sources without touching existing ones
- **Cost Efficiency**: Lambda only runs when needed, pays per invocation

**Real-World Analogy**: Like having separate loading docks for different suppliers at a warehouse - if one supplier is late, others keep delivering.

### 2. **Classification Separated** (FinBERT Worker Container)
**Why:**
- **Resource Intensive**: NLP models need GPU/CPU - containers better than Lambda
- **Variable Processing Time**: Some articles take 100ms, others 2s - continuous worker handles this
- **Independent Scaling**: Can run 1 or 10 workers based on backlog
- **Technology Isolation**: Python ML dependencies don't pollute other services

**Real-World Analogy**: Quality inspection station - inspectors work continuously on items from the inbound dock at their own pace.

### 3. **Signal Generation Separated** (Signal Engine Lambda)
**Why:**
- **Business Logic Isolation**: Trading rules change frequently - easy to modify/test
- **Scheduled Computation**: Runs periodically, not event-driven
- **Data Fusion Point**: Combines classified events + market data - clean interface
- **Stateless**: No memory of previous runs needed, just queries DB

**Real-World Analogy**: Manager reviewing quality reports + inventory levels to decide what to ship.

### 4. **Dispatch Separated** (Dispatcher Container)
**Why:**
- **Risk Gates**: Critical financial controls must be isolated and auditable
- **Continuous Operation**: Always-on service for immediate response
- **Atomic Execution**: Needs transaction control to prevent double-trades
- **Dry-Run Mode**: Can test without touching real broker

**Real-World Analogy**: Shipping department with final checks before packages leave the building.

### 5. **Monitoring Separated** (Watchdog Lambda)
**Why:**
- **System Health Oversight**: Independent view of all components
- **Failure Detection**: Catches when other parts stop working
- **Operational Safety**: Separate from production flow - can't break the pipeline

**Real-World Analogy**: Security guard checking that all systems are operational.

---

## Exact Component Implementation Order

### Phase 1: Foundation (Manual Setup)
1. ✅ **S3 Bucket** - `ops-pipeline-backups-<unique>`
2. ✅ **IAM Roles** - Lambda execution role, ECS task role
3. ✅ **Secrets Manager** - `ops-pipeline/db` (username/password)
4. ✅ **SSM Parameters** - Configuration values
5. ✅ **Security Groups** - `sg-rds`, `sg-app`

### Phase 2: Data Layer
6. ✅ **RDS Postgres** - Database instance
7. ✅ **DB Migrator** - Schema creation (one-time container)
   - Tables: `inbound_events_raw`, `inbound_events_classified`, `feed_state`, `lane_telemetry`, `dispatch_recommendations`

### Phase 3: Inbound Data Flow
8. ✅ **RSS Ingest Lambda** (`inbound_dock_lambda`)
   - EventBridge: Every 1 minute
   - Writes to: `inbound_events_raw`
   - Updates: `feed_state`

9. ✅ **FinBERT Classification Worker** (`sortation_worker`)
   - Deployment: ECS Fargate Service (1 task)
   - Reads: `inbound_events_raw` (WHERE processed_at IS NULL)
   - Writes: `inbound_events_classified`
   - Updates: `inbound_events_raw.processed_at`

### Phase 4: Market Context
10. ✅ **Market Telemetry Lambda** (`lane_telemetry_lambda`)
    - EventBridge: Every 5 minutes
    - Writes to: `lane_telemetry` (ticker, ts, OHLCV)

### Phase 5: Decision Making
11. ✅ **Signal Engine Lambda** (`dispatch_engine_lambda`)
    - EventBridge: Every 5 minutes
    - Reads: `inbound_events_classified`, `lane_telemetry`
    - Writes: `dispatch_recommendations`
    - Logic: Sentiment + Price vs SMA20

### Phase 6: Execution (Dry-Run)
12. ✅ **Dispatcher Container** (`dispatcher`)
    - Deployment: ECS Fargate Service (1 task, always-on)
    - Reads: `dispatch_recommendations` (WHERE status='PENDING')
    - Writes: Updates status to 'EXECUTED'
    - Risk Gates: Max trades/day, error kill-switch, stale data checks

### Phase 7: Operations
13. ✅ **Watchdog Lambda** (`watchdog_lambda`)
    - EventBridge: Every 5 minutes
    - Checks: Data freshness in all tables
    - Alerts: SNS topic → Email

14. ✅ **CloudWatch Alarms**
    - Lambda errors > threshold
    - ECS unhealthy tasks > 0
    - Billing > $25/month

15. ✅ **Backup Job**
    - Nightly pg_dump → S3
    - Lifecycle: Keep last 7 backups

---

## Repository Structure (Final State)

```
ops-pipeline/
├── README.md                           # Overview + quick start
├── .env.example                        # Local dev config template
├── docker-compose.yml                  # Local testing setup
├── DEPLOYMENT_PLAN.md                  # This file
│
├── db/
│   └── migrations/
│       └── 001_init.sql                # Database schema
│
├── services/
│   ├── common/                         # Shared code
│   │   ├── common/
│   │   │   ├── __init__.py
│   │   │   ├── config.py               # AWS secrets/SSM loading
│   │   │   ├── logging.py              # Structured logging
│   │   │   └── db.py                   # DB connection pool
│   │   └── requirements.txt
│   │
│   ├── db_migrator/                    # One-time migration job
│   │   ├── Dockerfile
│   │   ├── migrate.py
│   │   └── requirements.txt
│   │
│   ├── inbound_dock_lambda/            # RSS ingestion
│   │   ├── lambda_function.py
│   │   └── requirements.txt
│   │
│   ├── lane_telemetry_lambda/          # Market candles
│   │   ├── lambda_function.py
│   │   └── requirements.txt
│   │
│   ├── sortation_worker/               # FinBERT classifier
│   │   ├── Dockerfile
│   │   ├── main.py
│   │   ├── models/
│   │   │   └── sentiment.py
│   │   ├── extract/
│   │   │   └── tickers.py
│   │   ├── store.py
│   │   └── requirements.txt
│   │
│   ├── dispatch_engine_lambda/         # Signal generation
│   │   ├── lambda_function.py
│   │   ├── signals/
│   │   │   └── sma_sentiment.py
│   │   └── requirements.txt
│   │
│   ├── dispatcher/                     # Trade execution
│   │   ├── Dockerfile
│   │   ├── main.py
│   │   ├── risk/
│   │   │   └── gates.py
│   │   ├── execution/
│   │   │   └── dry_run.py
│   │   ├── store.py
│   │   └── requirements.txt
│   │
│   └── watchdog_lambda/                # Health monitoring
│       ├── lambda_function.py
│       └── requirements.txt
│
└── deploy/
    ├── aws_baseline.sh                 # Create S3, IAM, Secrets, SSM, SG
    ├── create_rds.sh                   # Provision RDS Postgres
    ├── deploy_lambda.sh                # Deploy all Lambdas
    ├── deploy_containers.sh            # Deploy ECS services
    ├── create_alarms.sh                # CloudWatch alarms + SNS
    └── verify_system.sh                # End-to-end health check
```

---

## Key Design Decisions

### 1. **Lambda vs Container Choice**
- **Lambda**: Scheduled/spiky work (RSS polling, signal calc, watchdog)
- **Container**: Continuous/heavy compute (FinBERT, dispatcher)
- **Cost Optimization**: Lambda free tier + ECS spot instances where possible

### 2. **Database First**
- RDS Postgres is the source of truth
- All services read/write through DB, no message queues (yet)
- Simple, reliable, easy to debug
- Can add Kafka/SQS later if throughput demands it

### 3. **Idempotency Everywhere**
- RSS: UNIQUE(event_uid) constraint
- Classification: processed_at flag + SELECT FOR UPDATE SKIP LOCKED
- Signals: Cooldown logic prevents spam
- Dispatcher: Atomic status updates prevent double-execution

### 4. **Observability Built-In**
- Every service logs: counts, latencies, errors
- CloudWatch captures everything
- Watchdog provides active monitoring
- SQL queries for manual inspection

### 5. **Cost Controls**
- Billing alarm at $25/month
- Start with smallest RDS (db.t3.micro)
- Lambda free tier covers most traffic
- Single ECS task per worker initially

---

## Next Steps

After confirming this plan, we proceed to **Prompt 2** (AWS Baseline Infrastructure).

The implementation order is locked and optimized for:
- ✅ Dependencies (can't deploy Lambda before IAM role exists)
- ✅ Testing (can verify each layer works before adding next)
- ✅ Rollback (can undo recent changes without touching stable layers)
- ✅ Learning (each prompt builds on knowledge from previous)

**Ready to start building?** Confirm this architecture, and I'll begin with Prompt 2: AWS Baseline Infrastructure setup using `aws-api-mcp`.
