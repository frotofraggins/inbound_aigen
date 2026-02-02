# Phase 16: Learning Infrastructure - COMPLETE ✅

**Date:** 2026-01-28  
**Status:** ✅ Fully Deployed and Verified

---

## Migration 011: Applied Successfully ✅

**Tables:**
- ✅ learning_recommendations (created)

**Columns Added:**
- ✅ dispatch_recommendations: features_snapshot, sentiment_snapshot
- ✅ dispatch_executions: features_snapshot, sentiment_snapshot  
- ✅ active_positions: win_loss_label, r_multiple, mae_pct, mfe_pct, holding_minutes, exit_reason_norm

**Method:** Lambda migration (ops-pipeline-db-migration)  
**Applied:** Already in database (verified 2026-01-28)

---

## For Future AIs: How to Deploy

### Database Migrations

**Method 1: Lambda (Fastest - Use This)**
```bash
# Migration 011 is ALREADY in Lambda function
# Just invoke it:
aws lambda invoke \
  --function-name ops-pipeline-db-migration \
  --region us-west-2 \
  --payload '{}' \
  /tmp/migration_result.json
```

**How Lambda Migrations Work:**
1. Migration SQL is embedded in `services/db_migration_lambda/lambda_function.py`
2. Lambda has VPC access to private RDS
3. Invoke Lambda → It applies any pending migrations
4. Returns: migrations_applied, migrations_skipped, tables

**To Add New Migration:**
1. Edit `services/db_migration_lambda/lambda_function.py`
2. Add migration to MIGRATIONS dict
3. Rebuild Lambda package
4. Deploy Lambda
5. Invoke to apply

### ECS Service Deployment

**Pattern:**
```bash
cd services/SERVICE_NAME

# 1. Build
docker build -t SERVICE_NAME .

# 2. Tag
docker tag SERVICE_NAME:latest \
  160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/SERVICE_NAME:latest

# 3. Push
aws ecr get-login-password --region us-west-2 | \
  docker login --username AWS --password-stdin \
  160027201036.dkr.ecr.us-west-2.amazonaws.com
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/SERVICE_NAME:latest

# 4. Get digest
aws ecr describe-images \
  --repository-name ops-pipeline/SERVICE_NAME \
  --region us-west-2 \
  --query 'imageDetails[0].imageDigest' \
  --output text

# 5. Update deploy/SERVICE_NAME-task-definition.json with new digest

# 6. Register
aws ecs register-task-definition \
  --cli-input-json file://deploy/SERVICE_NAME-task-definition.json \
  --region us-west-2

# 7. Restart (automatic via EventBridge on next schedule)
```

### Verification

```bash
# Test all phases
python3 scripts/verify_all_phases.py

# Check specific service logs
aws logs tail /ecs/ops-pipeline/SERVICE_NAME --region us-west-2

# Query database
python3 -c "import boto3, json; \
client = boto3.client('lambda', region_name='us-west-2'); \
r = client.invoke(FunctionName='ops-pipeline-db-query', \
  Payload=json.dumps({'sql': 'YOUR_SQL_HERE'})); \
print(json.loads(json.load(r['Payload'])['body']))"
```

---

## Key Files for Understanding

**Start Here:**
- `README.md` - System overview
- `CURRENT_SYSTEM_STATUS.md` - Infrastructure and parameters
- `deploy/COMPLETE_TRADING_LOGIC_EXPLAINED.md` - How trading works

**Config:**
- `config/trading_params.json` - All tunable parameters

**Deployment:**
- `deploy/HOW_TO_APPLY_MIGRATIONS.md` - Migration guide
- `services/*/Dockerfile` - Service configs
- `deploy/*-task-definition.json` - ECS configs

---

## Phase 16 Complete ✅

All learning infrastructure is deployed and ready:
- Feature snapshots at signal generation time
- Outcome normalization for ML training
- Learning recommendations table for AI tuning
- Analytical capabilities enabled

**System Status:** Fully operational with learning capabilities
