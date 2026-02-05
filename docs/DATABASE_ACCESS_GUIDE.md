# 🗄️ Database Access Guide - How to Query and Update
**Date:** 2026-02-05
**Purpose:** Complete guide for database operations in this project

---

## 🎯 Quick Reference

### Database Details
- **Type:** PostgreSQL (AWS RDS)
- **Name:** ops-pipeline-db
- **Region:** us-west-2
- **Access:** Private (VPC only, not publicly accessible)

### Connection Info Stored In
- **Host/Port/Name:** AWS Systems Manager (SSM) Parameters
  - `/ops-pipeline/db_host`
  - `/ops-pipeline/db_port`
  - `/ops-pipeline/db_name`
- **Credentials:** AWS Secrets Manager
  - `ops-pipeline/db` (username and password)

---

## 🔧 Method 1: Python Scripts (Most Common)

### Pattern Used Throughout Project

```python
import boto3
import psycopg2
import json

# Get connection info from AWS
ssm = boto3.client('ssm', region_name='us-west-2')
secrets = boto3.client('secretsmanager', region_name='us-west-2')

# Get database parameters
db_host = ssm.get_parameter(Name='/ops-pipeline/db_host')['Parameter']['Value']
db_port = ssm.get_parameter(Name='/ops-pipeline/db_port')['Parameter']['Value']
db_name = ssm.get_parameter(Name='/ops-pipeline/db_name')['Parameter']['Value']

# Get credentials
secret_value = secrets.get_secret_value(SecretId='ops-pipeline/db')
secret_data = json.loads(secret_value['SecretString'])

# Connect to database
conn = psycopg2.connect(
    host=db_host,
    port=int(db_port),
    database=db_name,
    user=secret_data['username'],
    password=secret_data['password'],
    connect_timeout=10
)

# Run queries
cur = conn.cursor()
cur.execute("SELECT * FROM active_positions WHERE status = 'open'")
results = cur.fetchall()

# Clean up
cur.close()
conn.close()
```

### Example Scripts Using This Pattern
- `add_columns_direct.py` - Add database columns
- `scripts/apply_013_direct.py` - Apply migrations
- `check_recent_trades.py` - Query trade data

**Location:** Root directory and scripts/ folder

---

## 🔧 Method 2: Via ECS Services (Production)

### Services That Access Database

**1. position-manager (Python):**
```python
# services/position_manager/db.py
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

# Config loads from Secrets Manager at startup
conn = psycopg2.connect(
    host=DB_HOST,
    port=DB_PORT,
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD
)
```

**2. dispatcher (Python):**
- Similar pattern in services/dispatcher/db/

**3. signal-engine (Python):**
- Similar pattern in services/signal_engine_1m/db.py

**These run inside AWS VPC so they CAN reach the private RDS instance**

---

## 🔧 Method 3: AWS Lambda Functions

### Available Lambda Functions

**1. ops-pipeline-db-query (SELECT only)**
```python
import boto3
import json

lambda_client = boto3.client('lambda', region_name='us-west-2')

payload = {
    'sql': 'SELECT * FROM active_positions LIMIT 10'
}

response = lambda_client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps(payload)
)

result = json.loads(response['Payload'].read())
print(result)
```

**Limitations:**
- Only allows SELECT queries
- Rejects ALTER TABLE, INSERT, UPDATE, DELETE

**2. ops-pipeline-db-migration (ALTER/DDL)**
```python
# This exists but format/usage unclear
# Would need to investigate function code
```

---

## 🔧 Method 4: CloudWatch Logs (Read-Only)

### What You Can See
```bash
# Position manager logs show:
aws logs tail /ecs/ops-pipeline/position-manager-service --since 1h --region us-west-2

# Examples of database operations in logs:
"Database connection established"
"Position 619 closed: max_hold_time"
"Created active position 621"
"✓ Position history saved" (if working)
"❌ Position history insert failed" (if broken)
```

**Use for:**
- Monitoring database operations
- Seeing INSERT/UPDATE results
- Debugging connection issues

**Cannot:**
- Run queries directly
- Modify data
- See table contents

---

## 🚫 What DOESN'T Work (Common Issues)

### Direct Connection from Local Machine
```python
# This FAILS:
conn = psycopg2.connect(host=rds_endpoint, ...)
# Error: "timeout expired"
```

**Why:** RDS is in private VPC, not publicly accessible

**Solutions:**
1. Use Lambda function
2. Use ECS task (run inside VPC)
3. Connect via VPN/bastion
4. Use scripts that use AWS APIs (SSM + Secrets Manager)

### Database Tools (DBeaver, pgAdmin, etc.)
**Problem:** Can't connect directly
**Why:** RDS not public

**Workaround:** Create Lambda or ECS task to proxy

---

## ✅ How to Run Queries (Practical Guide)

### Quick SELECT Query
```python
# Use existing ops-pipeline-db-query Lambda:
import boto3, json

lambda_client = boto3.client('lambda', region_name='us-west-2')
result = lambda_client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({
        'sql': 'SELECT id, ticker, entry_price, current_price FROM active_positions WHERE status = \'open\''
    })
)
print(json.loads(result['Payload'].read()))
```

### Add/Modify Columns
```python
# Use pattern from add_columns_direct.py:
# 1. Get connection info from SSM/Secrets
# 2. Connect with psycopg2
# 3. Execute ALTER TABLE
# 4. Commit

# Example:
python3 add_columns_direct.py  # Adds columns if needed
```

### Check Specific Data
```python
# Create custom script following pattern:
import boto3, psycopg2, json

ssm = boto3.client('ssm', region_name='us-west-2')
secrets = boto3.client('secretsmanager', region_name='us-west-2')

host = ssm.get_parameter(Name='/ops-pipeline/db_host')['Parameter']['Value']
# ... get other params

conn = psycopg2.connect(...)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM position_history")
print(f"position_history records: {cur.fetchone()[0]}")
```

---

## 📊 Common Database Operations

### 1. Check Table Schema
```sql
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'active_positions'
ORDER BY ordinal_position;
```

### 2. Count Records
```sql
SELECT COUNT(*) FROM position_history;
SELECT COUNT(*) FROM active_positions WHERE status = 'open';
```

### 3. View Recent Trades
```sql
SELECT 
    ticker,
    instrument_type,
    entry_time,
    exit_time,
    pnl_pct,
    exit_reason
FROM position_history
WHERE created_at > NOW() - INTERVAL '24 hours'
ORDER BY created_at DESC;
```

### 4. Check Win/Loss Record
```sql
SELECT 
    instrument_type,
    COUNT(*) as trades,
    COUNT(*) FILTER (WHERE pnl_pct > 0) as wins,
    COUNT(*) FILTER (WHERE pnl_pct < 0) as losses,
    AVG(pnl_pct) as avg_return
FROM position_history
GROUP BY instrument_type;
```

---

## 🔧 How to Add Columns (Step-by-Step)

### Example: Adding peak_price Column

**Step 1: Create SQL**
```sql
-- File: db/migrations/013_minimal.sql
ALTER TABLE active_positions 
ADD COLUMN IF NOT EXISTS peak_price DECIMAL(12, 4);
```

**Step 2: Create Python Script**
```python
# File: scripts/apply_migration_013.py
import boto3, psycopg2, json

# Get connection (pattern from above)
ssm = boto3.client('ssm', region_name='us-west-2')
secrets = boto3.client('secretsmanager', region_name='us-west-2')

host = ssm.get_parameter(Name='/ops-pipeline/db_host')['Parameter']['Value']
# ... etc

conn = psycopg2.connect(...)
cur = conn.cursor()

# Execute migration
cur.execute("""
    ALTER TABLE active_positions 
    ADD COLUMN IF NOT EXISTS peak_price DECIMAL(12, 4)
""")
conn.commit()

print("✅ Column added!")
cur.close()
conn.close()
```

**Step 3: Run Script**
```bash
python3 scripts/apply_migration_013.py
```

**Note:** May timeout if not on proper network. Use from machine with VPC access.

---

## 🎯 Troubleshooting

### Error: "timeout expired"
**Cause:** Not on network with RDS access
**Solutions:**
1. Run from ECS task (inside VPC)
2. Use Lambda function
3. Connect via VPN
4. Use another method

### Error: "column does not exist"
**Cause:** Schema mismatch between code and database
**Solutions:**
1. Check actual schema: `\d table_name` in psql
2. Or query information_schema.columns
3. Fix code to match actual schema

### Error: "ExpiredTokenException"
**Cause:** AWS credentials expired
**Solution:**
```bash
ada cred update --account 160027201036 --role IibsAdminAccess-DO-NOT-DELETE --provider conduit --once
```

---

## 📚 Key Files for Database Operations

### Schema Definitions
- `db/migrations/*.sql` - All table definitions
- `db/migrations/2026_02_02_0001_position_telemetry.sql` - position_history schema
- `db/migrations/011_add_learning_infrastructure.sql` - Learning views

### Database Access Code
- `services/position_manager/db.py` - Position manager DB ops
- `services/position_manager/config.py` - Connection config
- `add_columns_direct.py` - Example of direct access pattern

### Query Scripts
- `scripts/query_db.py` - Generic query tool (if exists)
- `check_recent_trades.py` - Check trade data
- `scripts/comprehensive_health_check.py` - System health

---

## 🎯 For Next Agent

### To Query Database
1. Check existing scripts in root and scripts/ folder
2. Use pattern from `add_columns_direct.py`
3. Get connection from SSM + Secrets Manager
4. Use psycopg2 for queries

### To Update Database
1. Create SQL migration file in db/migrations/
2. Create Python script following established pattern
3. Test with SELECT first
4. Run ALTER/UPDATE from machine with access

### To Verify Operations
1. Check CloudWatch logs for database operations
2. Look for "Database connection established"
3. Check for error messages
4. Verify INSERT/UPDATE success

---

**KEY PRINCIPLE:** Database is private (VPC only). Access via:
1. Python scripts using AWS APIs (SSM + Secrets Manager)
2. ECS services (run inside VPC)
3. Lambda functions
4. NOT directly from local machine (will timeout)
