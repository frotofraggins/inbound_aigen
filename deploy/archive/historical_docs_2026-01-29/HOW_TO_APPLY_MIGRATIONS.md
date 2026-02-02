# How to Apply Database Migrations - PROVEN METHOD

**Last Updated:** 2026-01-26  
**Method:** Lambda-based (bypasses VPC connectivity issues)

## The Problem

RDS database is in private VPC subnet. Local scripts timeout trying to connect:
```
connection to server at "ops-pipeline-db..." (172.31.47.127), port 5432 failed: Connection timed out
```

## The Solution: Use Lambda ✅

The `ops-pipeline-db-migration` Lambda has VPC access and can apply migrations reliably.

### Step-by-Step Process

**1. Add Migration File to Lambda**

Edit `services/db_migration_lambda/lambda_function.py` and add your migration SQL at the end of the `MIGRATIONS` dictionary:

```python
MIGRATIONS = {
    # ... existing migrations ...
    
    "008_add_options_support": """
-- Your migration SQL here
ALTER TABLE dispatch_executions ADD COLUMN instrument_type TEXT;
-- etc...
"""
}
```

**2. Rebuild and Deploy Lambda**

```bash
cd services/db_migration_lambda
rm -rf package
mkdir -p package
pip install -q -r requirements.txt -t package/
cp lambda_function.py package/
cd package
zip -q -r ../migration_lambda.zip .
cd ..

aws lambda update-function-code \
  --function-name ops-pipeline-db-migration \
  --zip-file fileb://migration_lambda.zip \
  --region us-west-2

cd ../..
```

**3. Invoke Lambda to Apply Migration**

```bash
aws lambda invoke \
  --function-name ops-pipeline-db-migration \
  --region us-west-2 \
  --payload '{}' \
  /tmp/migration_result.json

cat /tmp/migration_result.json
```

Expected output:
```json
{
  "success": true,
  "migrations_applied": ["008_add_options_support"],
  "migrations_skipped": ["001_init", "002_...", ...]
}
```

**4. Verify Success**

```bash
python3 << 'EOF'
import boto3, json
client = boto3.client('lambda', region_name='us-west-2')

response = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'sql': "SELECT version, applied_at FROM schema_migrations WHERE version LIKE '008%'"})
)
result = json.loads(json.load(response['Payload'])['body'])
if result['rows']:
    print(f"✅ Migration applied: {result['rows'][0]}")
else:
    print("❌ Migration not found")
EOF
```

## Why This Works

- Lambda is deployed in VPC (has subnet access to RDS)
- Lambda has proper IAM permissions
- No need for bastion host or VPN
- Consistent and reproducible

## For Future Migrations

**Always use this Lambda method for new migrations:**
1. Add SQL to `lambda_function.py`
2. Rebuild package
3. Deploy Lambda
4. Invoke to apply
5. Verify in `schema_migrations` table

**DO NOT** try to connect directly from local machine - it will always timeout.

## Example: How Migration 008 Was Applied

**Date:** 2026-01-26  
**Migration:** 008_add_options_support  
**Method:** Lambda  
**Result:** ✅ Success  
**Columns Added:** 7 (instrument_type, strike_price, expiration_date, contracts, premium_paid, delta, strategy_type)  
**Views Created:** 3 (active_options_positions, options_performance_by_strategy, daily_options_summary)  

This method was proven after Docker/ECS methods failed due to caching issues.

---

**ALWAYS USE LAMBDA FOR MIGRATIONS** - It's the reliable method that works!
