# 🗄️ Database Access - Quick Reference for New AI Agents
**Date:** 2026-02-09
**Purpose:** Fast reference on how to query and update the database

---

## ⚡ The 3 Ways to Access Database

### Method 1: Query via Lambda (SELECT only) ✅ RECOMMENDED

```python
import boto3
import json

client = boto3.client('lambda', region_name='us-west-2')

# Simple query
response = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({
        'sql': 'SELECT COUNT(*) FROM active_positions WHERE status = \'open\''
    })
)

result = json.loads(response['Payload'].read())
data = json.loads(result['body'])
print(data)
```

**Pros:** Fast, always works, no network issues
**Cons:** SELECT only (no INSERT, UPDATE, ALTER)
**Use for:** Quick checks, monitoring, dashboards

---

### Method 2: Migrate via ECS Task (DDL/DML) ✅ FOR SCHEMA CHANGES

```bash
# Step 1: Create migration file
cat > db/migrations/1005_my_change.sql << 'EOF'
ALTER TABLE active_positions 
ADD COLUMN my_column VARCHAR(50);
EOF

# Step 2: Rebuild db-migrator
docker build --no-cache \
  -f services/db_migrator/Dockerfile \
  -t 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/db-migrator:latest .

# Step 3: Push
aws ecr get-login-password --region us-west-2 | \
  docker login --username AWS --password-stdin 160027201036.dkr.ecr.us-west-2.amazonaws.com

docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/db-migrator:latest

# Step 4: Run migration
aws ecs run-task \
  --cluster ops-pipeline-cluster \
  --task-definition ops-pipeline-db-migrator \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-0c182a149eeef918a],securityGroups=[sg-0cd16a909f4e794ce],assignPublicIp=ENABLED}" \
  --region us-west-2

# Step 5: Check logs
aws logs tail /ecs/ops-pipeline/db-migrator --since 2m --region us-west-2
```

**Pros:** Can do ALTER, INSERT, UPDATE, DELETE
**Cons:** Slower, requires Docker rebuild
**Use for:** Schema changes, data fixes, migrations

---

### Method 3: Direct Connection (DOESN'T WORK) ❌

```python
# This WILL FAIL with timeout:
import psycopg2

conn = psycopg2.connect(
    host='ops-pipeline-db.cls4wuyg010k.us-west-2.rds.amazonaws.com',
    port=5432,
    ...
)
# Error: "connection timeout"
```

**Why it fails:** Database is in private VPC, not publicly accessible

**When it works:** Only from:
- ECS tasks (inside VPC)
- EC2 instances (inside VPC)
- Lambda functions (with VPC config)

---

## 📊 Common Queries (Copy-Paste Ready)

### Check Active Positions
```python
import boto3, json

client = boto3.client('lambda', region_name='us-west-2')
response = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({
        'sql': '''
        SELECT 
            id, ticker, instrument_type, account_name,
            entry_price, current_price, 
            EXTRACT(EPOCH FROM (NOW() - entry_time))/60 as age_minutes
        FROM active_positions 
        WHERE status = 'open'
        ORDER BY entry_time DESC
        '''
    })
)
print(json.loads(json.loads(response['Payload'].read())['body']))
```

### Check position_history (Learning Data)
```python
# Same pattern:
client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({
        'sql': '''
        SELECT COUNT(*) as total_records FROM position_history
        '''
    })
)
```

### Check Recent Signals
```python
client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({
        'sql': '''
        SELECT ticker, signal_type, confidence_score, created_at
        FROM signals
        WHERE generated_at > NOW() - INTERVAL '1 hour'
        ORDER BY generated_at DESC
        LIMIT 10
        '''
    })
)
```

---

## 🔧 Verification Scripts

### Script 1: Check If position_history Working

```python
# File: scripts/verify_learning_data.py
import boto3, json

client = boto3.client('lambda', region_name='us-west-2')

# Count position_history records
response = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({
        'sql': 'SELECT COUNT(*) as count FROM position_history'
    })
)

result = json.loads(json.loads(response['Payload'].read())['body'])
count = result[0]['count']

print(f"position_history records: {count}")

if count == 0:
    print("⚠️  NO LEARNING DATA - Bug may still exist")
else:
    print(f"✅ Learning data accumulating ({count} trades recorded)")

# Show recent
response2 = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({
        'sql': '''
        SELECT ticker, instrument_type, pnl_pct, exit_reason, exit_time
        FROM position_history
        ORDER BY exit_time DESC
        LIMIT 5
        '''
    })
)

recent = json.loads(json.loads(response2['Payload'].read())['body'])
print("\nRecent closes:")
for r in recent:
    print(f"  {r['ticker']} {r['instrument_type']}: {r['pnl_pct']:.1f}% - {r['exit_reason']}")
```

### Script 2: Check Trade Quality

```python
# File: scripts/check_trade_quality.py
import boto3, json

client = boto3.client('lambda', region_name='us-west-2')

response = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({
        'sql': '''
        SELECT 
            instrument_type,
            COUNT(*) as trades,
            COUNT(*) FILTER (WHERE pnl_pct > 0) as wins,
            AVG(pnl_pct) as avg_return,
            MIN(pnl_pct) as worst_loss,
            MAX(pnl_pct) as best_win
        FROM position_history
        WHERE exit_time > NOW() - INTERVAL '7 days'
        GROUP BY instrument_type
        '''
    })
)

result = json.loads(json.loads(response['Payload'].read())['body'])
print("7-Day Performance:")
for row in result:
    win_rate = (row['wins'] / row['trades'] * 100) if row['trades'] > 0 else 0
    print(f"\n{row['instrument_type']}:")
    print(f"  Trades: {row['trades']}")
    print(f"  Win Rate: {win_rate:.1f}%")
    print(f"  Avg Return: {row['avg_return']:.1f}%")
    print(f"  Best: {row['best_win']:.1f}%")
    print(f"  Worst: {row['worst_loss']:.1f}%")
```

---

## 📚 Full Documentation References

**Complete guides (read in order):**
1. **docs/START_HERE_NEW_AI.md** - This guide (you're here!)
2. **docs/SYSTEM_OVERVIEW.md** - Architecture deep dive
3. **docs/OPERATIONS_GUIDE.md** - Day-to-day operations
4. **docs/DATABASE_ACCESS_GUIDE.md** - Full database reference

**Troubleshooting:**
- **docs/POSITION_SYNC_TROUBLESHOOTING.md** - Position issues
- **deploy/TROUBLESHOOTING_GUIDE.md** - General issues

---

## 🎯 When You're Stuck

### "How do I query X?"
→ Use Lambda pattern above, change SQL

### "How do I change schema?"
→ Use db-migrator pattern above

### "Service won't connect to database"
→ Check VPC/security groups, verify secrets exist

### "Can't connect from my machine"
→ Correct! Use Lambda or ECS task

### "Timeout errors"
→ Normal for direct connections, use Lambda

---

**KEY TAKEAWAY:** Database is private. Use Lambda for queries, db-migrator for changes. Simple!
