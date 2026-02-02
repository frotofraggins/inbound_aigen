# Why Phase 11 Bedrock Works But Phase 14 Doesn't

**Date:** 2026-01-26  
**Question:** How is Bedrock analyzing in Phase 11 (classifier) but not Phase 14 (ticker_discovery)?

---

## The Answer: AssignPublicIp

### Phase 11 Classifier Worker ✅ WORKS

**Architecture:** ECS Fargate Task

**Network Configuration:**
```json
{
  "AssignPublicIp": "ENABLED",
  "SecurityGroups": ["sg-0cd16a909f4e794ce"],
  "Subnets": ["subnet-0c182a149eeef918a"]
}
```

**Why It Works:**
1. ECS task launches in VPC subnet
2. **Gets a public IP address** (AssignPublicIp=ENABLED)
3. Can reach internet services like Bedrock API
4. Can also reach VPC resources like RDS database
5. ✅ Bedrock calls succeed

**Network Flow:**
```
ECS Task (Public IP) 
  ├─→ Internet → Bedrock API ✅
  └─→ VPC → RDS Database ✅
```

### Phase 14 Ticker Discovery ❌ FAILS

**Architecture:** Lambda Function

**Network Configuration:**
```json
{
  "SubnetIds": ["subnet-0c182a149eeef918a", ...],
  "SecurityGroupIds": ["sg-0cd16a909f4e794ce"],
  "VpcId": "vpc-0444cb2b7a3457502"
}
```

**Why It Fails:**
1. Lambda is in VPC (needs database access)
2. **VPC Lambdas CANNOT get public IP** (AWS limitation)
3. Can only reach VPC resources
4. Cannot reach internet services
5. ❌ Bedrock calls timeout after 300 seconds

**Network Flow:**
```
Lambda (VPC, No Public IP)
  ├─→ VPC → RDS Database ✅
  └─→ Internet → Bedrock API ❌ TIMEOUT
```

---

## AWS Networking Facts

### ECS Fargate with AssignPublicIp
- ✅ **Can get public IP even in VPC**
- ✅ Reaches internet + VPC resources
- ✅ Perfect for services needing both
- ✅ No NAT Gateway needed
- ✅ No additional cost

### Lambda in VPC
- ❌ **Cannot get public IP** (AWS doesn't support this)
- ✅ Reaches VPC resources only
- ❌ Cannot reach internet without NAT Gateway
- ❌ NAT Gateway costs $32/month
- ⚠️ VPC Endpoints don't exist for all services (Bedrock has none)

---

## Why Original Architecture Choice

**Phase 11 (Sept 2025):** Chose ECS for classifier_worker
- Reason: "Needs to reach internet for future APIs"
- Result: ✅ Works with Bedrock

**Phase 14 (Jan 2026):** Initially chose Lambda
- Reason: "Simple periodic task, Lambda is easier"
- Oversight: Didn't consider internet access need
- Result: ❌ VPC Lambda can't reach Bedrock

---

## Solution: Convert to ECS

### Why This Is The Right Fix

**Matches proven pattern:**
- ✅ Phase 11 uses ECS + AssignPublicIp for Bedrock
- ✅ Already have ECR repository
- ✅ Already have ECS cluster
- ✅ Already have EventBridge→ECS pattern
- ✅ Just copy classifier_worker deployment

**Cost effective:**
- ✅ No NAT Gateway ($32/month avoided)
- ✅ ECS Fargate: ~$0.50/month for periodic tasks
- ✅ Same as Lambda cost

**Operationally simple:**
- ✅ Consistent architecture
- ✅ Same monitoring pattern
- ✅ Same logging pattern
- ✅ Same IAM roles

---

## Conversion Steps

### 1. Create Dockerfile (5 min)
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY discovery.py .
CMD ["python", "-u", "discovery.py"]
```

### 2. Build & Push to ECR (5 min)
```bash
cd services/ticker_discovery
docker build -t ticker-discovery .
aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin 160027201036.dkr.ecr.us-west-2.amazonaws.com
docker tag ticker-discovery:latest 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/ticker-discovery:latest
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/ticker-discovery:latest
```

### 3. Create ECS Task Definition (10 min)
```json
{
  "family": "ticker-discovery",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "arn:aws:iam::160027201036:role/ops-pipeline-ecs-task-role",
  "taskRoleArn": "arn:aws:iam::160027201036:role/ops-pipeline-ecs-task-role",
  "containerDefinitions": [...]
}
```

### 4. Update EventBridge (10 min)
```bash
# Delete Lambda rule
aws events remove-targets --rule ops-ticker-discovery-6h --ids 1
aws events delete-rule --name ops-ticker-discovery-6h

# Create ECS scheduler
aws scheduler create-schedule \
  --name ops-ticker-discovery-6h \
  --schedule-expression "rate(6 hours)" \
  --target '{
    "Arn": "arn:aws:ecs:us-west-2:160027201036:cluster/ops-pipeline-cluster",
    "RoleArn": "...",
    "EcsParameters": {
      "TaskDefinitionArn": "...",
      "NetworkConfiguration": {
        "awsvpcConfiguration": {
          "AssignPublicIp": "ENABLED",  ← KEY!
          "Subnets": ["subnet-0c182a149eeef918a"],
          "SecurityGroups": ["sg-0cd16a909f4e794ce"]
        }
      }
    }
  }'
```

### 5. Test (5 min)
```bash
# Run task manually
aws ecs run-task \
  --cluster ops-pipeline-cluster \
  --task-definition ticker-discovery \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-0c182a149eeef918a],securityGroups=[sg-0cd16a909f4e794ce],assignPublicIp=ENABLED}"

# Check logs - should complete successfully
```

**Total Time:** 30-45 minutes

---

## Key Takeaway

**VPC Lambda cannot reach internet services. Period.**

**Options:**
1. ✅ Use ECS with AssignPublicIp=ENABLED (Phase 11 pattern)
2. ❌ Add NAT Gateway ($32/month)
3. ❌ Use PrivateLink/VPC Endpoint (doesn't exist for Bedrock)

**Best choice:** Follow Phase 11 ECS pattern that's already proven to work.

---

**Next Step:** Convert ticker_discovery and opportunity_analyzer to ECS tasks following classifier_worker pattern.
