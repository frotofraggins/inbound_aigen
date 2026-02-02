# OPS-CLI: Command Line Interface Guide

## 🎯 Quick Start

```bash
# Make executable (already done)
chmod +x ops-cli

# Check system health
./ops-cli status

# View recent signals
./ops-cli logs signal --since 5m

# Query database
./ops-cli data --query trades

# Enable options-only mode
./ops-cli mode options-only
```

---

## 📋 All Commands

### **1. System Status**

```bash
./ops-cli status
```

Shows:
- ECS cluster health (services, tasks)
- Service status (running/stopped)
- Database availability
- Recent signal activity

**Example Output:**
```
================================================================================
                            SYSTEM STATUS CHECK                              
================================================================================

ECS Cluster:
✓ Cluster: ops-pipeline-cluster (6 services, 8 tasks)

Services:
✓ dispatcher          Running: 1/1
✓ dispatcher-tiny     Running: 1/1
✓ telemetry          Running: 1/1
✓ classifier         Running: 1/1
✓ position-manager   Running: 1/1
✓ trade-stream       Running: 1/1

Database:
✓ RDS: ops-pipeline-db (available)

Recent Activity:
ℹ Last 3 signals:
  2026-02-02T14:18:55 {"event": "signal_computed", "data": {"ticker": "AAPL", "action": "HOLD"}}
```

---

### **2. View Logs**

```bash
# View recent logs
./ops-cli logs <service> [--since <time>] [--follow]

# Available services:
# - dispatcher   (trade execution)
# - signal       (signal generation) 
# - telemetry    (price data)
# - classifier   (sentiment analysis)
# - position     (position monitoring)
# - trade-stream (WebSocket trades)
```

**Examples:**
```bash
# Last 10 minutes
./ops-cli logs dispatcher

# Last hour
./ops-cli logs signal --since 1h

# Follow live (Ctrl+C to stop)
./ops-cli logs dispatcher --follow

# Last 5 minutes, follow
./ops-cli logs signal --since 5m --follow
```

---

### **3. Query Database**

```bash
# Predefined queries
./ops-cli data --query <query_name>

# Custom SQL
./ops-cli data --custom "SELECT * FROM dispatch_executions LIMIT 10"

# Available predefined queries:
# - signals    (recent trading signals)
# - trades     (executed trades)
# - positions  (open positions)
# - features   (technical indicators)
# - telemetry  (price/volume data)
```

**Examples:**
```bash
# View recent trades
./ops-cli data --query trades

# View open positions
./ops-cli data --query positions

# View technical features
./ops-cli data --query features --limit 50

# Custom query
./ops-cli data --custom "SELECT ticker, COUNT(*) FROM dispatch_executions GROUP BY ticker"
```

**Output:**
```
ticker              action              instrument_type     confidence          
--------------------------------------------------------------------------------
TSLA                BUY                 CALL                0.62                
NVDA                BUY                 PUT                 0.58                
SPY                 HOLD                None                0.0                 

3 rows returned
```

---

### **4. Configuration Management**

```bash
# View current config
./ops-cli config get

# Update parameter
./ops-cli config set <param> <value>

# Available parameters:
# - confidence    (confidence_min_options_daytrade)
# - volume        (min_volume_ratio)
# - max_trades    (max_trades_per_ticker_per_day)
```

**Examples:**
```bash
# View all config
./ops-cli config get

# Lower confidence threshold
./ops-cli config set confidence 0.45

# Require higher volume
./ops-cli config set volume 2.5

# Allow more trades per ticker
./ops-cli config set max_trades 6
```

**Important:** Changes take effect on next dispatcher run (< 5 minutes)

---

### **5. Service Management**

```bash
# List all services
./ops-cli services list

# Stop a service
./ops-cli services stop <service>

# Start a service  
./ops-cli services start <service>

# Available services:
# - dispatcher
# - dispatcher-tiny
# - telemetry
# - classifier
# - position-manager
# - trade-stream
```

**Examples:**
```bash
# List all services with status
./ops-cli services list

# Stop dispatcher temporarily
./ops-cli services stop dispatcher

# Start it again
./ops-cli services start dispatcher

# Stop trading (keep monitoring)
./ops-cli services stop dispatcher
./ops-cli services stop dispatcher-tiny
```

---

### **6. Trading Mode**

```bash
# Enable options-only mode (CALL/PUT only)
./ops-cli mode options-only

# Enable hybrid mode (options + stocks)
./ops-cli mode hybrid
```

**Options-Only Mode:**
- ✅ Allowed: BUY_CALL, BUY_PUT
- ❌ Blocked: BUY_STOCK, SELL_STOCK
- Use case: Pure options day trading

**Hybrid Mode:**
- ✅ Allowed: BUY_CALL, BUY_PUT, BUY_STOCK, SELL_STOCK
- Use case: Flexible trading strategy

---

### **7. Deployment**

```bash
# Deploy updated service
./ops-cli deploy <service>

# Available services:
# - dispatcher
# - signal-engine
# - telemetry
# - position-manager
# - classifier
# - trade-stream
```

**Example:**
```bash
# Deploy updated dispatcher
./ops-cli deploy dispatcher
```

**What it does:**
1. Builds Docker image from source
2. Tags for ECR
3. Logs into ECR
4. Pushes image
5. ECS automatically deploys

**Note:** Takes 2-5 minutes total

---

## 🔧 Common Workflows

### **Morning Routine:**

```bash
# 1. Check system health
./ops-cli status

# 2. View overnight activity
./ops-cli logs dispatcher --since 12h | grep EXECUTED

# 3. Check positions
./ops-cli data --query positions

# 4. View recent signals
./ops-cli logs signal --since 30m
```

### **Troubleshooting:**

```bash
# 1. Check what's wrong
./ops-cli status

# 2. View error logs
./ops-cli logs dispatcher --since 1h | grep ERROR

# 3. Check database
./ops-cli data --query trades

# 4. Restart problematic service
./ops-cli services stop dispatcher
./ops-cli services start dispatcher
```

### **Tuning Parameters:**

```bash
# 1. View current settings
./ops-cli config get

# 2. Lower confidence for more trades
./ops-cli config set confidence 0.40

# 3. Monitor results
./ops-cli logs signal --follow

# 4. Check if trades increase
./ops-cli data --query trades
```

### **Deploy New Code:**

```bash
# 1. Make code changes locally
vim services/dispatcher/config.py

# 2. Deploy to AWS
./ops-cli deploy dispatcher

# 3. Monitor deployment
./ops-cli logs dispatcher --follow

# 4. Verify working
./ops-cli status
```

---

## 🎓 Advanced Usage

### **Custom Database Queries:**

```bash
# Count trades by ticker
./ops-cli data --custom "
SELECT 
    ticker,
    COUNT(*) as trades,
    COUNT(*) FILTER (WHERE execution_mode = 'ALPACA_PAPER') as real_trades
FROM dispatch_executions
WHERE simulated_ts > NOW() - INTERVAL '24 hours'
GROUP BY ticker
ORDER BY trades DESC
"

# Average confidence by action
./ops-cli data --custom "
SELECT 
    action,
    instrument_type,
    AVG(confidence) as avg_conf,
    COUNT(*) as count
FROM dispatch_recommendations
WHERE ts > NOW() - INTERVAL '7 days'
GROUP BY action, instrument_type
"
```

### **Service Orchestration:**

```bash
# Stop all trading (keep monitoring)
./ops-cli services stop dispatcher
./ops-cli services stop dispatcher-tiny

# Just data collection (no signals)
./ops-cli services stop dispatcher
./ops-cli services stop dispatcher-tiny
# telemetry, classifier, signal-engine keep running

# Restart everything
./ops-cli services start dispatcher
./ops-cli services start dispatcher-tiny
```

---

## 🚨 Troubleshooting CLI

### **"Command not found"**

```bash
# Make sure you're in project directory
cd /home/nflos/workplace/inbound_aigen

# Make executable
chmod +x ops-cli

# Run with ./
./ops-cli status
```

### **"AWS CLI errors"**

```bash
# Refresh AWS credentials
ada cred update --account 160027201036 --role IibsAdminAccess-DO-NOT-DELETE --provider conduit --once

# Verify access
aws sts get-caller-identity
```

### **"No module named 'boto3'"**

```bash
# Install Python AWS SDK
pip3 install boto3
```

---

## 📚 Behind the Scenes

### **How ops-cli Works:**

1. **Wraps AWS CLI commands**
   - Uses `aws ecs`, `aws logs`, `aws ssm`
   - Formats output nicely
   - Provides shortcuts

2. **Uses Lambda for DB queries**
   - Calls `ops-pipeline-db-query` function
   - Database is in private VPC
   - Lambda has access, we don't

3. **Updates SSM parameters**
   - Configuration stored in Parameter Store
   - Services reload config automatically
   - Changes take effect in < 5 minutes

### **What ops-cli Does NOT Do:**

- ❌ Connect directly to database (uses Lambda)
- ❌ SSH into containers (uses CloudWatch logs)
- ❌ Run Docker locally (services are in AWS)
- ❌ Access Alpaca API directly (services do that)

---

## 🎯 Quick Reference

```bash
# Status
./ops-cli status                               # Full system check

# Logs
./ops-cli logs signal -f                       # Follow signal logs
./ops-cli logs dispatcher --since 1h           # Last hour

# Data
./ops-cli data --query trades                  # Recent trades
./ops-cli data --query positions               # Open positions
./ops-cli data --custom "SELECT * FROM ..."   # Custom SQL

# Config
./ops-cli config get                           # View config
./ops-cli config set confidence 0.50           # Update param

# Services
./ops-cli services list                        # List all
./ops-cli services stop dispatcher             # Stop service
./ops-cli services start dispatcher            # Start service

# Mode
./ops-cli mode options-only                    # Options only
./ops-cli mode hybrid                          # Options + stocks

# Deploy
./ops-cli deploy dispatcher                    # Deploy changes
```

---

## 💡 Pro Tips

1. **Use `--follow` for live debugging**
   ```bash
   ./ops-cli logs signal --follow
   # See signals generated in real-time
   ```

2. **Combine with grep/jq for filtering**
   ```bash
   ./ops-cli logs dispatcher --since 1h | grep EXECUTED
   ./ops-cli config get | jq '.allowed_actions'
   ```

3. **Create aliases for common tasks**
   ```bash
   alias ops-stat="./ops-cli status"
   alias ops-trades="./ops-cli data --query trades"
   ```

4. **Use custom queries for analysis**
   ```bash
   ./ops-cli data --custom "
   SELECT 
       DATE(simulated_ts) as date,
       COUNT(*) as trades,
       SUM(CASE WHEN execution_mode = 'ALPACA_PAPER' THEN 1 ELSE 0 END) as real
   FROM dispatch_executions  
   GROUP BY DATE(simulated_ts)
   "
   ```

---

**For more details, see:**
- [ECS/Docker Architecture](./ECS_DOCKER_ARCHITECTURE.md)
- [System Status](../CURRENT_SYSTEM_STATUS.md)
- [Runbook](../deploy/RUNBOOK.md)
