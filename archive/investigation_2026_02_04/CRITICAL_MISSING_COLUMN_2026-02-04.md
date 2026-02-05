# CRITICAL: Missing account_name Column in active_positions

**Date:** February 4, 2026  
**Time:** 15:15 UTC  
**Status:** ❌ BLOCKING ALL TRADES

---

## Problem Summary

The `active_positions.account_name` column is **MISSING** from the database, causing **617 FAILED recommendations** in the last 24 hours.

### Error Message
```
UndefinedColumn: column "account_name" does not exist
LINE 7:               AND account_name = 'large-default'
```

### Impact
- ❌ 617 recommendations FAILED (87% failure rate)
- ❌ System cannot track positions by account
- ❌ Risk gates cannot enforce account-level limits
- ❌ Multi-account isolation broken
- ✅ 16 trades executed (before failures started)
- ✅ 59 simulated fallback trades

---

## Root Cause

Migration 1001 (`db/migrations/1001_add_account_name_to_active_positions.sql`) was **NOT applied** to the database.

### Why Migration Failed

The migration Lambda (`ops-pipeline-db-migration`) only runs **embedded migrations** hardcoded in its code. Migration 1001 is a file-based migration that was never added to the Lambda's embedded migrations list.

### Current State

| Table | Column Exists | Status |
|-------|--------------|--------|
| `dispatch_executions` | ✅ YES | Working (migration 1002 applied) |
| `active_positions` | ❌ NO | **BROKEN** |

---

## Solution

### Option 1: Add Migration to Lambda (RECOMMENDED)

Update the migration Lambda to include migration 1001 in its embedded migrations:

1. Edit `services/db_migration_lambda/lambda_function.py`
2. Add migration 1001 to the `MIGRATIONS` dictionary:

```python
'1001_add_account_name_to_active_positions': """
-- Migration 1001: Add account_name column to active_positions table
ALTER TABLE active_positions 
ADD COLUMN IF NOT EXISTS account_name VARCHAR(50) DEFAULT 'large';

CREATE INDEX IF NOT EXISTS idx_active_positions_account_name 
ON active_positions(account_name);

CREATE INDEX IF NOT EXISTS idx_active_positions_status_account 
ON active_positions(status, account_name);

UPDATE active_positions 
SET account_name = 'large' 
WHERE account_name IS NULL;

INSERT INTO schema_migrations (version) VALUES ('1001_add_account_name_to_active_positions') ON CONFLICT (version) DO NOTHING;
"""
```

3. Deploy updated Lambda
4. Invoke Lambda to apply migration

### Option 2: Direct Database Access (TEMPORARY FIX)

If you have direct database access (psycopg2 connection):

```python
import psycopg2
import boto3
import json

# Get credentials
secrets = boto3.client('secretsmanager', region_name='us-west-2')
response = secrets.get_secret_value(SecretId='ops-pipeline/db')
creds = json.loads(response['SecretString'])

# Connect
conn = psycopg2.connect(
    host='ops-pipeline-db.cluster-cfahtqkurmtb.us-west-2.rds.amazonaws.com',
    database='ops_pipeline',
    user=creds['username'],
    password=creds['password']
)

# Apply migration
cur = conn.cursor()
cur.execute("""
    ALTER TABLE active_positions 
    ADD COLUMN IF NOT EXISTS account_name VARCHAR(50) DEFAULT 'large';
    
    CREATE INDEX IF NOT EXISTS idx_active_positions_account_name 
    ON active_positions(account_name);
    
    CREATE INDEX IF NOT EXISTS idx_active_positions_status_account 
    ON active_positions(status, account_name);
    
    UPDATE active_positions 
    SET account_name = 'large' 
    WHERE account_name IS NULL;
""")
conn.commit()
```

### Option 3: Use RDS Query Editor (AWS Console)

1. Go to RDS Console → Query Editor
2. Connect to `ops-pipeline-db` cluster
3. Run migration SQL directly

---

## Verification

After applying the fix, verify with:

```bash
aws lambda invoke --function-name ops-pipeline-db-query --region us-west-2 \
  --payload '{"sql":"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '\''active_positions'\'' AND column_name = '\''account_name'\'';"}' \
  /tmp/verify.json && cat /tmp/verify.json
```

Expected result:
```json
{
  "statusCode": 200,
  "body": "{\"success\": true, \"rows\": [{\"column_name\": \"account_name\", \"data_type\": \"character varying\"}]}"
}
```

---

## Files Involved

### Migration File (Exists)
- `db/migrations/1001_add_account_name_to_active_positions.sql` ✅

### Code That Needs the Column
- `services/dispatcher/db/repositories.py` - `get_account_state()` function
- `services/position_manager/db.py` - Position tracking queries

### Migration Lambda
- `services/db_migration_lambda/lambda_function.py` - Needs update

---

## Timeline

| Time | Event |
|------|-------|
| Feb 3, 2026 19:20 UTC | Migration 1002 applied (dispatch_executions.account_name) ✅ |
| Feb 3, 2026 19:20 UTC | Migration 1001 NOT applied (active_positions.account_name) ❌ |
| Feb 4, 2026 15:00 UTC | Discovered 617 FAILED recommendations |
| Feb 4, 2026 15:15 UTC | Root cause identified |

---

## Next Steps

1. **IMMEDIATE:** Apply migration 1001 using one of the options above
2. **VERIFY:** Check that column exists
3. **MONITOR:** Watch for FAILED recommendations to stop
4. **RESTART:** Restart dispatcher services to clear any cached errors
5. **UPDATE:** Add migration 1001 to Lambda for future deployments

---

## Related Documents

- `SQL_TRANSACTION_FIX_COMPLETE_2026-02-03.md` - Previous fix (dispatch_executions)
- `SESSION_COMPLETE_2026-02-03.md` - Session context
- `db/migrations/1001_add_account_name_to_active_positions.sql` - Migration file
- `db/migrations/1002_add_account_name_to_dispatch_executions.sql` - Related migration

---

## Status After Fix

Once migration 1001 is applied:

- ✅ Both tables will have account_name column
- ✅ Position tracking will work by account
- ✅ Risk gates will enforce account-level limits
- ✅ Multi-account isolation will be restored
- ✅ FAILED recommendations will stop
- ✅ System will resume normal trading

**Priority:** P0 - CRITICAL - Blocking all trades
**Estimated Fix Time:** 5-10 minutes
