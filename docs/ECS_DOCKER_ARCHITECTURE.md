# ECS & Docker Architecture - How We Connect

## 🏗️ Current Architecture

### **NO Local Docker Containers**

**IMPORTANT:** This system does NOT run Docker locally. All services run in **AWS ECS Fargate** (serverless containers in the cloud).

### Architecture Diagram

```
Local Machine (Your Computer)
    │
    ├─ AWS CLI ───────────────────────┐
    ├─ Python Scripts ────────────────┤
    └─ ops-cli (NEW) ─────────────────┤
                                      │
                                      ▼
                            ┌─────────────────────┐
                            │   AWS Account       │
                            │   (160027201036)    │
                            └─────────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
                    ▼                 ▼                 ▼
            ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
            │  ECS Fargate │  │     RDS      │  │    Lambda    │
            │   Cluster    │  │   Database   │  │  Functions   │
            └──────────────┘  └──────────────┘  └──────────────┘
                    │
        ┌───────────┼───────────┐
        │           │           │
        ▼           ▼           ▼
    Service 1   Service 2   Service 3...
    (Docker)    (Docker)    (Docker)
```

---

## 🔗 How We Connect to ECS Services

### **Method 1: AWS CLI (What We Use)**

All our scripts use AWS CLI to interact with ECS:

```bash
# List services
aws ecs list-services \
  --cluster ops-pipeline-cluster \
  --region us-west-2

# Check service status
aws ecs describe-services \
  --cluster ops-pipeline-cluster \
  --services dispatcher-service \
  --region us-west-2

# View logs (no SSH needed!)
aws logs tail /ecs/ops-pipeline/dispatcher \
  --region us-west-2 \
  --since 5m \
  --follow
```

### **Method 2: AWS Console (Web UI)**

URL: https://us-west-2.console.aws.amazon.com/ecs/v2/clusters/ops-pipeline-cluster/services

- View service status
- See running tasks
- Check logs
- Restart services

### **Method 3: ECS Exec (Interactive Shell)**

For debugging, you can get a shell inside a running container:

```bash
# Enable ECS Exec on service (one-time setup)
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service dispatcher-service \
  --enable-execute-command \
  --region us-west-2

# Connect to running task
aws ecs execute-command \
  --cluster ops-pipeline-cluster \
  --task <task-arn> \
  --container dispatcher \
  --command "/bin/sh" \
  --interactive \
  --region us-west-2
```

---

## 🐳 Docker Workflow

### **Local Development:**

```bash
# Build Docker image locally
cd services/dispatcher
docker build -t dispatcher:local .

# Test locally (connects to RDS via VPN/tunnel)
docker run -e AWS_REGION=us-west-2 dispatcher:local

# NO kubernetes, NO docker-compose
# Each service has its own Dockerfile
```

### **Deployment to AWS:**

```bash
# 1. Build image
docker build -t dispatcher .

# 2. Tag for ECR (AWS Docker registry)
docker tag dispatcher:latest \
  160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/dispatcher:latest

# 3. Login to ECR
aws ecr get-login-password --region us-west-2 | \
  docker login --username AWS --password-stdin \
  160027201036.dkr.ecr.us-west-2.amazonaws.com

# 4. Push to ECR
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/dispatcher:latest

# 5. ECS automatically pulls new image
# No manual restart needed - ECS sees the new image digest
```

---

## 📊 How Services Communicate

### **Service-to-Service:**

Services do NOT talk directly to each other. They communicate via:

1. **Database (Primary):**
   ```
   Signal Engine → Writes to dispatch_recommendations
   Dispatcher → Reads from dispatch_recommendations
   ```

2. **Shared RDS:**
   - All services connect to same PostgreSQL database
   - Database is in private VPC
   - Services use ENI (Elastic Network Interface) to access

3. **EventBridge (Scheduling):**
   ```
   EventBridge → Triggers ECS task
   ECS Task → Runs, writes to DB, exits
   ```

### **Service-to-AWS APIs:**

```
Dispatcher → Alpaca API (internet)
Telemetry → Alpaca Data API (internet)
All Services → RDS (private VPC)
```

---

## 🔐 Why No Direct Access?

### **Security by Design:**

1. **RDS in Private VPC**
   - Database has NO public IP
   - Only ECS services can reach it
   - We use Lambda to query (Lambda is in same VPC)

2. **ECS Tasks in Private Subnets**
   - Tasks have ENI in private subnet
   - NAT Gateway for internet (Alpaca API)
   - NO SSH, NO public IP

3. **Logs via CloudWatch**
   - All logs go to CloudWatch
   - We tail logs via AWS CLI
   - No need to SSH into containers

---

## 🎯 How to Monitor Services

### **1. Check Service Health:**

```bash
# Our script does this:
python3 scripts/check_system_status.py

# Manually:
aws ecs describe-services \
  --cluster ops-pipeline-cluster \
  --services dispatcher-service position-manager-service \
  --region us-west-2 \
  --query 'services[*].{Name:serviceName,Status:status,Running:runningCount,Desired:desiredCount}'
```

### **2. View Logs:**

```bash
# Last hour
aws logs tail /ecs/ops-pipeline/dispatcher \
  --region us-west-2 \
  --since 1h

# Follow live
aws logs tail /ecs/ops-pipeline/signal-engine-1m \
  --region us-west-2 \
  --since 5m \
  --follow
```

### **3. Check Recent Activity:**

```bash
# Via Lambda (database query)
python3 -c "
import boto3, json
client = boto3.client('lambda', region_name='us-west-2')
response = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({
        'sql': 'SELECT * FROM dispatch_executions ORDER BY simulated_ts DESC LIMIT 10'
    })
)
result = json.loads(json.load(response['Payload'])['body'])
for row in result['rows']:
    print(row)
"
```

---

## 🚀 Deployment Flow

### **Complete CI/CD Pipeline:**

```
1. Code Change (local)
   ↓
2. Build Docker Image (local)
   ↓
3. Push to ECR (AWS Docker Registry)
   ↓
4. Update Task Definition
   ↓
5. ECS Automatically Deploys
   ↓
6. Health Checks Pass
   ↓
7. Service Running New Code
```

### **No Downtime Deployments:**

ECS does rolling updates:
- Starts new task with new code
- Waits for health check
- Stops old task
- Zero downtime!

---

## 🎛️ Service Control

### **Start Service:**

```bash
# Services are always running (desired count = 1)
# If stopped, ECS automatically restarts

# Force new task:
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service dispatcher-service \
  --force-new-deployment \
  --region us-west-2
```

### **Stop Service:**

```bash
# Set desired count to 0
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service dispatcher-service \
  --desired-count 0 \
  --region us-west-2
```

### **Scale Service:**

```bash
# Run multiple copies
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service dispatcher-service \
  --desired-count 2 \
  --region us-west-2
```

---

## 📝 Key Differences from Local Docker

| Aspect | Local Docker | Our ECS Setup |
|--------|--------------|---------------|
| **Where runs** | Your computer | AWS cloud |
| **Networking** | localhost | Private VPC + NAT |
| **Database access** | localhost:5432 | RDS in VPC |
| **Logs** | docker logs | CloudWatch |
| **Restart** | docker restart | ECS auto-restart |
| **SSH/Exec** | docker exec | ECS exec (rarely needed) |
| **Cost** | $0 | ~$76-126/month |
| **Scaling** | Manual | Auto-scale possible |

---

## 🔧 Troubleshooting

### **"Can't connect to database"**

✅ **Correct:** Use Lambda to query
```python
# Via ops-pipeline-db-query Lambda
```

❌ **Wrong:** Try to connect directly
```python
# This will FAIL - RDS is private
psycopg2.connect(host='ops-pipeline-db.abc.us-west-2.rds.amazonaws.com')
```

### **"Can't see logs"**

✅ **Correct:** Use CloudWatch
```bash
aws logs tail /ecs/ops-pipeline/dispatcher --region us-west-2
```

❌ **Wrong:** Try to SSH
```bash
ssh user@container  # No SSH available!
```

### **"Service won't start"**

Check:
1. Task definition valid (JSON syntax)
2. ECR image exists
3. IAM roles have permissions
4. Security groups allow traffic
5. Subnets have NAT gateway

---

## 🎯 Bottom Line

**How we connect to ECS:**
- ✅ AWS CLI commands (what scripts use)
- ✅ AWS Console (web UI)
- ✅ CloudWatch Logs (for debugging)
- ✅ Lambda functions (for DB queries)

**NOT:**
- ❌ Local docker-compose
- ❌ Direct database connections
- ❌ SSH into containers
- ❌ Docker containers on your machine

**Everything runs in AWS Cloud (ECS Fargate + RDS + Lambda)**

The `ops-cli` tool (next) will wrap all these AWS CLI commands into an easy interface!
