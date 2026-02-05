# Critical Missing Column - active_positions.account_name

## 🚨 What Kiro Found

**Data Check Results:**
```
✅ 16 real trades executed (ALPACA_PAPER)
❌ 617 FAILED recommendations (UndefinedColumn error)
❌ No active positions showing
✅ dispatch_executions.account_name EXISTS
❌ active_positions.account_name MISSING
```

**The Problem:**
- Position Manager queries: `WHERE account_name = 'large'`
- But column doesn't exist!
- 617 failures in 24 hours

---

## ✅ Why Kiro Is Stuck

**What Kiro Tried:**

1. **db-query Lambda** ❌ Only allows SELECT
2. **db-migration Lambda** ❌ Only runs embedded migrations  
3. **Direct database connection** ❌ Network not reachable
4. **Migration 1001 script** ❌ Can't execute ALTER TABLE

**The Issue:** Can't execute ALTER TABLE through any existing Lambda!

---

## ✅ THE SOLUTION (Two Options)

### **Option 1: Add to Embedded Migrations (Proper)**

**File:** `services/db_migration_lambda/lambda_function.py`

**Add to MIGRATIONS dictionary:**
```python
MIGRATIONS = {
    # ... existing migrations ...
    
    '1001_add_account_name_to_active_positions': '''
        -- Add account_name to active_positions for multi-account support
        ALTER TABLE active_positions 
        ADD COLUMN IF NOT EXISTS account_name VARCHAR(50) DEFAULT 'large';
        
        -- Create indexes for performance
        CREATE INDEX IF NOT EXISTS idx_active_positions_account_name 
        ON active_positions(account_name);
        
        CREATE INDEX IF NOT EXISTS idx_active_positions_status_account 
        ON active_positions(status, account_name);
        
        -- Update existing rows
        UPDATE active_positions 
        SET account_name = 'large' 
        WHERE account_name IS NULL;
    '''
}
```

**Then deploy Lambda:**
```bash
cd services/db_migration_lambda
pip install -r requirements.txt -t package/
cp lambda_function.py package/
cd package && zip -r ../migration_lambda.zip . && cd ..
aws lambda update-function-code \
  --function-name ops-pipeline-db-migration \
  --zip-file fileb://migration_lambda.zip \
  --region us-west-2
```

**Then invoke:**
```bash
aws lambda invoke \
  --function-name ops-pipeline-db-migration \
  --region us-west-2 \
  response.json
```

---

### **Option 2: Temporary Fix in Code (Quick)**

**If can't deploy Lambda, make code handle missing column:**

**In `services/position_manager/db.py`:**

**Find all queries with `account_name` and make them conditional:**

```python
# Check if column exists
def has_account_name_column():
    cur.execute("""
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'active_positions' 
        AND column_name = 'account_name'
    """)
    return cur.fetchone() is not None

# Then in queries:
if has_account_name_column():
    query = "SELECT * FROM active_positions WHERE account_name = %s"
    params = [account_name]
else:
    query = "SELECT * FROM active_positions"  # No filter
    params = []
```

**This makes code work without column, but loses multi-account support.**

---

## 🎯 Why This Matters for Two Configs

**User's Question:** "Need 2 configs for 2 accounts?"  
**Answer:** YES! But active_positions needs account_name column first!

**Without column:**
- Position Manager can't filter by account
- Both dispatchers see ALL positions
- Creates duplicates
- Risk gates see wrong counts

**With column:**
- Position Manager filters: `WHERE account_name = 'large'`
- Large dispatcher sees only large positions
- Tiny dispatcher sees only tiny positions
- Clean separation ✅

---

## 📋 Immediate Actions for Kiro

### **Quick Fix (Until Lambda Deployed):**

**Stop Position Manager temporarily:**
```bash
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service position-manager-service \
  --desired-count 0 \
  --region us-west-2
```

**Why:** It's failing 617 times trying to query missing column!

### **Proper Fix (After Hours):**

1. Add migration to db-migration Lambda
2. Deploy Lambda
3. Invoke to create column
4. Restart Position Manager
5. System works with multi-account

---

## 🏆 Summary

**Critical Bug:** active_positions.account_name missing  
**Impact:** 617 failed recommendations, Position Manager broken  
**Kiro's Stuck:** Can't ALTER TABLE through Lambda  
**Solution:** Add migration to Lambda code, deploy, invoke  
**Quick Fix:** Stop Position Manager until proper fix  
**User Question:** YES need 2 configs, but column needed first!

**For User:** Tell Kiro to add migration 1001 to db-migration Lambda's embedded migrations, deploy Lambda, invoke. Column will be created and system will work! 🎯
