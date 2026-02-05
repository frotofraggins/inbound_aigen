# Guidance for Fixing Position Manager Missing Columns

## 🎯 The Problem

Position Manager is crashing because `active_positions` table is missing columns:
- `original_quantity`
- `peak_price`
- `trailing_stop_price`  
- `entry_underlying_price`

These should have been added by migration 013, but weren't applied.

---

## ✅ THE CORRECT SOLUTION

### **Use the Existing db-migration Lambda**

The `ops-pipeline-db-migration` Lambda is specifically designed for this. Here's how:

### **Step 1: Update Lambda Code with Migration**

**File:** `services/db_migration_lambda/lambda_function.py`

Add migration to the `MIGRATIONS` dictionary:

```python
MIGRATIONS = {
    # ... existing migrations ...
    
    '019_add_phase3_columns': '''
        -- Add columns for Phase 3 behavior learning
        ALTER TABLE active_positions 
        ADD COLUMN IF NOT EXISTS original_quantity INTEGER,
        ADD COLUMN IF NOT EXISTS peak_price DECIMAL(12, 4),
        ADD COLUMN IF NOT EXISTS trailing_stop_price DECIMAL(12, 4),
        ADD COLUMN IF NOT EXISTS entry_underlying_price DECIMAL(12, 4);
        
        -- Add indexes for performance
        CREATE INDEX IF NOT EXISTS idx_active_positions_peak 
            ON active_positions(peak_price) 
            WHERE peak_price IS NOT NULL;
    '''
}
```

### **Step 2: Deploy Updated Lambda**

```bash
cd services/db_migration_lambda

# Package dependencies
pip install -r requirements.txt -t package/
cp lambda_function.py package/

# Create deployment package
cd package
zip -r ../migration_lambda.zip .
cd ..

# Deploy to AWS
aws lambda update-function-code \
  --function-name ops-pipeline-db-migration \
  --zip-file fileb://migration_lambda.zip \
  --region us-west-2
```

### **Step 3: Invoke Lambda**

```bash
aws lambda invoke \
  --function-name ops-pipeline-db-migration \
  --region us-west-2 \
  response.json

cat response.json
```

The Lambda will:
1. Read all MIGRATIONS
2. Check schema_migrations table
3. Apply any new migrations
4. Return success/failure

---

## 🔧 ALTERNATIVE: Fix the Code (Workaround)

If you can't modify the Lambda, make the code handle missing columns gracefully.

### **In services/position_manager/db.py:**

**Find the `create_position_from_alpaca` function:**

```python
def create_position_from_alpaca(...):
    # Instead of:
    INSERT INTO active_positions (... original_quantity, peak_price ...)
    
    # Use defensive SQL:
    sql = """
        INSERT INTO active_positions (
            ticker, instrument_type, side, quantity, 
            entry_price, current_price, ...
    """
    
    # Only add optional columns if they exist
    if has_column('active_positions', 'original_quantity'):
        sql += ", original_quantity"
        values.append(quantity)
    
    if has_column('active_positions', 'peak_price'):
        sql += ", peak_price"
        values.append(entry_price)
```

**Add helper function:**

```python
def has_column(table_name, column_name):
    """Check if column exists"""
    try:
        cursor.execute("""
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = %s AND column_name = %s
        """, (table_name, column_name))
        return cursor.fetchone() is not None
    except:
        return False
```

---

## 🚨 QUICKEST FIX (For Now)

### **Make Code Work Without Columns:**

**In `services/position_manager/db.py`, line ~150:**

Change from:
```python
INSERT INTO active_positions (
    ticker, instrument_type, side, quantity, 
    entry_price, current_price, unrealized_pnl,
    stop_loss, take_profit, entered_at, last_checked,
    strike_price, expiration_date, option_symbol,
    status, original_quantity, peak_price, trailing_stop_price
) VALUES (...)
```

To:
```python
INSERT INTO active_positions (
    ticker, instrument_type, side, quantity, 
    entry_price, current_price, unrealized_pnl,
    stop_loss, take_profit, entered_at, last_checked,
    strike_price, expiration_date, option_symbol,
    status
) VALUES (...)
-- Remove: original_quantity, peak_price, trailing_stop_price
```

Then redeploy Position Manager:
```bash
cd services/position_manager
docker build -t position-manager .
# Push to ECR and update task definition
```

---

## 📋 RECOMMENDATION

### **Option A: Add Columns (Proper Fix)**
1. Update db-migration Lambda code
2. Deploy Lambda
3. Invoke to run migration
4. Restart Position Manager
**Time:** 10-15 minutes

### **Option B: Remove Column Usage (Quick Fix)**
1. Edit position_manager/db.py
2. Remove references to missing columns
3. Redeploy Position Manager
**Time:** 5 minutes

### **Option C: Add Columns Manually (Hacky)**

Use existing Python script approach but via Lambda invoke:

```python
import boto3, json

# Create migration in Lambda code
lambda_code = '''
def lambda_handler(event, context):
    import psycopg2
    import os
    conn = psycopg2.connect(
        host=os.environ['DB_HOST'],
        database=os.environ['DB_NAME'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD']
    )
    cur = conn.cursor()
    cur.execute("""
        ALTER TABLE active_positions 
        ADD COLUMN IF NOT EXISTS original_quantity INTEGER,
        ADD COLUMN IF NOT EXISTS peak_price DECIMAL(12, 4),
        ADD COLUMN IF NOT EXISTS trailing_stop_price DECIMAL(12, 4);
    """)
    conn.commit()
    return {"statusCode": 200, "body": "Columns added"}
'''

# Deploy as new Lambda, invoke once, delete
```

---

## 🎯 MY RECOMMENDATION

**Do Option B (Quick Fix) NOW** so Position Manager works, then **Option A (Proper Fix)** in next session.

**Why:**
- Option B: 5 minutes, Position Manager works immediately
- Option A: Can do properly later with testing
- Don't need trailing stops immediately (basic stops work)

**The columns are for advanced features (trailing stops, behavior learning). Position Manager works fine without them for basic stop/profit exits.**

---

## 📝 Commands for Option B

```bash
# 1. Edit the code
vim services/position_manager/db.py
# Remove original_quantity, peak_price, trailing_stop_price from INSERT

# 2. Edit monitor.py if it references these
vim services/position_manager/monitor.py
# Comment out any peak_price or trailing_stop_price logic

# 3. Rebuild and deploy
cd services/position_manager
docker build -t position-manager .
docker tag position-manager:latest 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/position-manager:latest
aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin 160027201036.dkr.ecr.us-west-2.amazonaws.com
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/position-manager:latest

# 4. Force ECS to pick up new image
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service position-manager-service \
  --force-new-deployment \
  --region us-west-2
```

**Position Manager will work in 5 minutes!**

---

## 🔑 Key Insight

The columns are for **Phase 3 enhancements** (trailing stops, adaptive exits). They're NOT required for basic Position Manager functionality.

**Basic Position Manager needs:**
- ticker, quantity, entry_price, stop_loss, take_profit ✅ These exist
- Can monitor and close positions ✅ Works

**Phase 3 additions (missing):**
- original_quantity (for partial exits)
- peak_price (for trailing stops)
- trailing_stop_price (for dynamic stops)

**Conclusion:** Make code work without Phase 3 columns now. Add them properly later.

---

**Tell Kiro:** Remove the missing columns from the INSERT statement, redeploy Position Manager, it'll work immediately.
