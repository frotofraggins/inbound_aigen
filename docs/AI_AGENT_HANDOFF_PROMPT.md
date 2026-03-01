# AI Agent Onboarding Prompt — Inbound AI Options Trading System

Copy everything below this line and paste it as your first message to a new AI agent:

---

You are taking over an AI-powered options trading system that runs on AWS ECS Fargate. It manages ~$122K across 2 Alpaca paper trading accounts. Your job is to verify everything is running correctly, fix anything broken, and optionally improve the system — without breaking what works.

## READ THESE FIRST (in order)

1. `docs/START_HERE_NEW_AI.md` — Full onboarding, architecture, troubleshooting (30 min)
2. `docs/CURRENT_STATUS.md` — What was just fixed/deployed, current state
3. `docs/SYSTEM_OVERVIEW.md` — Technical reference for all services
4. `docs/DATABASE_QUERY_REFERENCE.md` — All tables, schemas, common queries
5. `docs/OPERATIONS_GUIDE.md` — How to deploy, monitor, troubleshoot

## CRITICAL CONTEXT

### Architecture (12 services)
- **Data layer:** telemetry (1min bars), RSS ingest, ticker discovery (Bedrock)
- **Processing:** classifier (FinBERT sentiment), feature computer, watchlist engine
- **Decision:** signal engine (1min) → dispatcher (2 instances: large + tiny accounts)
- **Monitoring:** position manager (2 instances) → exit monitoring
- **Learning:** trade analyzer (daily) → learning applier (Bedrock reviews findings)

### AWS Resources
- **Account:** 160027201036, **Region:** us-west-2
- **ECS Cluster:** ops-pipeline-cluster
- **Database:** Query via Lambda `ops-pipeline-db-query` with `{"sql": "SELECT ..."}` — it's read-only
- **Write queries:** Use db-migrator ECS task (build image from repo root with `-f services/db_migrator/Dockerfile`)
- **SSM configs:** `/ops-pipeline/dispatcher_config_large` and `_tiny` (YAML format)
- **Secrets:** `ops-pipeline/alpaca/large`, `ops-pipeline/alpaca/tiny`, `ops-pipeline/db`
- **ECR:** `160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/<service-name>:latest`

### The Learning Loop (runs daily Mon-Fri)
```
9:15 PM UTC — trade-analyzer: analyzes position_history, writes findings to learning_recommendations
9:30 PM UTC — learning-applier: Bedrock Claude reviews findings, auto-applies SSM changes, flags code changes
```

### Known Gotchas (bugs we already fixed — don't reintroduce)
1. **Never use `sys.exit()` in service loops** — use `return` or `raise`. `SystemExit` inherits from `BaseException`, not `Exception`, so `except Exception` won't catch it. Caused crash-loops.
2. **Never use Alpaca positions API for option prices** — returns stale broker valuations. Use `/v1beta1/options/quotes/latest` for live bid/ask.
3. **Position manager sync order matters** — DB sync (Step 1, has features) must run before Alpaca sync (Step 2, no features). Swapping them breaks the feature pipeline.
4. **Dispatcher must save features_snapshot** — `insert_execution()` includes `features_snapshot` column. Without it, the learning pipeline has no data.
5. **Always use `:latest` image tags** — old tags like `:service-mode` or `:account-filter` are stale.

## HEALTH CHECK — Run These First

```bash
# 1. Are all services running?
aws ecs list-services --cluster ops-pipeline-cluster --region us-west-2 --query 'serviceArns' --output table

# 2. Are services healthy (desired = running)?
aws ecs describe-services --cluster ops-pipeline-cluster --services dispatcher-service dispatcher-tiny-service position-manager-service position-manager-tiny-service telemetry-service --region us-west-2 --query 'services[*].{name:serviceName,desired:desiredCount,running:runningCount,status:status}' --output table

# 3. Any recent errors?
aws logs tail /ecs/ops-pipeline/dispatcher --region us-west-2 --since 10m | grep -i "error\|fatal\|exception" | tail -5
aws logs tail /ecs/ops-pipeline/position-manager-service --region us-west-2 --since 10m | grep -i "error\|fatal\|exception" | tail -5

# 4. Are signals being generated?
aws lambda invoke --function-name ops-pipeline-db-query --region us-west-2 --payload '{"sql": "SELECT COUNT(*) as signals_last_hour FROM dispatch_recommendations WHERE ts >= NOW() - INTERVAL '\''1 hour'\''"}' /tmp/q.json && cat /tmp/q.json

# 5. Are trades executing?
aws lambda invoke --function-name ops-pipeline-db-query --region us-west-2 --payload '{"sql": "SELECT COUNT(*) as executions_today, SUM(CASE WHEN execution_mode = '\''ALPACA_PAPER'\'' THEN 1 ELSE 0 END) as real_trades FROM dispatch_executions WHERE simulated_ts >= CURRENT_DATE"}' /tmp/q.json && cat /tmp/q.json

# 6. Open positions and P&L?
aws lambda invoke --function-name ops-pipeline-db-query --region us-west-2 --payload '{"sql": "SELECT ticker, instrument_type, entry_price::float, current_price::float, ROUND(((current_price - entry_price) / entry_price * 100)::numeric, 1) as pnl_pct, account_name FROM active_positions WHERE status = '\''open'\'' ORDER BY account_name, ticker"}' /tmp/q.json && cat /tmp/q.json

# 7. Learning pipeline working?
aws lambda invoke --function-name ops-pipeline-db-query --region us-west-2 --payload '{"sql": "SELECT status, COUNT(*) FROM learning_recommendations GROUP BY status"}' /tmp/q.json && cat /tmp/q.json

# 8. Features flowing through?
aws lambda invoke --function-name ops-pipeline-db-query --region us-west-2 --payload '{"sql": "SELECT COUNT(*) as total_open, SUM(CASE WHEN entry_features_json IS NOT NULL AND entry_features_json != '\''{}'\''::jsonb THEN 1 ELSE 0 END) as with_features FROM active_positions WHERE status = '\''open'\''"}' /tmp/q.json && cat /tmp/q.json
```

## DEPLOYMENT PROCESS (when making changes)

```bash
# 1. Edit code
# 2. Syntax check
python3 -c "import py_compile; py_compile.compile('path/to/file.py', doraise=True)"

# 3. Build and push
cd services/<service_name>
docker build -t 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/<image-name>:latest .
aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin 160027201036.dkr.ecr.us-west-2.amazonaws.com
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/<image-name>:latest

# 4. Deploy (persistent services)
aws ecs update-service --cluster ops-pipeline-cluster --service <service-name> --force-new-deployment --region us-west-2

# 5. Verify
aws logs tail /ecs/ops-pipeline/<service-name> --region us-west-2 --since 5m --follow
```

## RULES

- **Verify before changing** — read the code, check the data, understand the flow
- **Don't assume** — query the database to confirm your understanding
- **Test changes** — run one-shot tasks before deploying persistent services
- **Update docs** — any change should be reflected in CURRENT_STATUS.md at minimum
- **This is paper trading** — we want to learn, so be willing to experiment, but don't break the learning pipeline
- **All code changes are uncommitted** — check `git status` to see what's modified

Start by running the health checks above and reading CURRENT_STATUS.md. Report what you find.
