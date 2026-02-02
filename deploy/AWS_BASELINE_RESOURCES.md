# AWS Baseline Infrastructure - Resource Summary

**Created:** 2026-01-09  
**Region:** us-west-2  
**Account:** 160027201036

---

## Phase 2 Complete ✅

All baseline AWS infrastructure for ops-pipeline has been successfully created.

---

## 1. Storage Resources

### S3 Bucket
- **Bucket Name:** `ops-pipeline-backups-160027201036`
- **Purpose:** Store nightly database backups
- **Versioning:** Enabled
- **Region:** us-west-2

---

## 2. Networking Resources

### VPC
- **VPC ID:** `vpc-0444cb2b7a3457502`
- **CIDR:** 172.31.0.0/16
- **Type:** Default VPC

### Subnets (4 across different AZs)
1. **subnet-06bb5f5b338a60e88** - us-west-2d (172.31.48.0/20)
2. **subnet-08d822c6b86dfd00b** - us-west-2b (172.31.16.0/20)
3. **subnet-07df3caa9179ea77b** - us-west-2c (172.31.0.0/20)
4. **subnet-0c182a149eeef918a** - us-west-2a (172.31.32.0/20)

### Security Groups

#### Application Security Group
- **Group ID:** `sg-0cd16a909f4e794ce`
- **Name:** `ops-pipeline-app-sg`
- **Purpose:** Lambda functions and ECS tasks
- **Ingress Rules:** None (outbound only for external API calls)
- **Egress Rules:** Default (all traffic)

#### RDS Security Group
- **Group ID:** `sg-09379d105ed7901a9`
- **Name:** `ops-pipeline-rds-sg`
- **Purpose:** PostgreSQL database
- **Ingress Rules:** 
  - TCP port 5432 from `sg-0cd16a909f4e794ce` (app security group)
- **Egress Rules:** Default

---

## 3. IAM Resources

### Lambda Execution Role
- **Role Name:** `ops-pipeline-lambda-role`
- **Role ARN:** `arn:aws:iam::160027201036:role/ops-pipeline-lambda-role`
- **Role ID:** `AROASKQS5JYGFR4A76QYT`
- **Purpose:** Execution role for all Lambda functions
- **Attached Policies:**
  - `arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole` (VPC networking + CloudWatch Logs)
  - `arn:aws:iam::aws:policy/SecretsManagerReadWrite` (database credentials)
  - `arn:aws:iam::aws:policy/AmazonSSMReadOnlyAccess` (configuration parameters)

### ECS Task Role
- **Role Name:** `ops-pipeline-ecs-task-role`
- **Role ARN:** `arn:aws:iam::160027201036:role/ops-pipeline-ecs-task-role`
- **Role ID:** `AROASKQS5JYGER2SK6RV3`
- **Purpose:** Execution role for ECS container tasks
- **Attached Policies:**
  - `arn:aws:iam::aws:policy/SecretsManagerReadWrite` (database credentials)
  - `arn:aws:iam::aws:policy/AmazonSSMReadOnlyAccess` (configuration parameters)
  - `arn:aws:iam::aws:policy/CloudWatchLogsFullAccess` (logging)

---

## 4. Secrets Manager

### Database Credentials Secret
- **Secret Name:** `ops-pipeline/db`
- **Secret ARN:** `arn:aws:secretsmanager:us-west-2:160027201036:secret:ops-pipeline/db-l4GRCY`
- **Version ID:** `793d0b7d-4e35-4e84-9dae-4b2f15958165`
- **Purpose:** PostgreSQL database credentials
- **Contents:**
  ```json
  {
    "username": "ops_pipeline_admin",
    "password": "<strong-password>",
    "engine": "postgres",
    "port": 5432
  }
  ```
- **Access:** Lambda and ECS roles have read access

---

## 5. Systems Manager (SSM) Parameters

### Configuration Parameters

#### RSS Feed URLs
- **Parameter Name:** `/ops-pipeline/rss_feeds`
- **Type:** StringList
- **Version:** 1
- **Value:** 
  ```
  [
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&CIK=&type=&company=&dateb=&owner=include&start=0&count=40&output=atom"
  ]
  ```
- **Purpose:** RSS feeds to poll for financial news

#### Stock Tickers
- **Parameter Name:** `/ops-pipeline/tickers`
- **Type:** String
- **Version:** 1
- **Value:** `AAPL,MSFT,TSLA,GOOGL,AMZN,META,NVDA`
- **Purpose:** Stock symbols to track for market data

#### Signal Cooldown
- **Parameter Name:** `/ops-pipeline/signal_cooldown_minutes`
- **Type:** String
- **Version:** 1
- **Value:** `60`
- **Purpose:** Minutes to wait before generating another signal for same ticker

---

## Next Steps

With Phase 2 complete, we can now proceed to:

**Phase 3:** Create RDS Postgres Database
- Instance type: db.t3.micro (cheapest)
- Storage: 20GB GP2
- Backup retention: 7 days
- Security group: `sg-09379d105ed7901a9`
- Credentials: From Secrets Manager `ops-pipeline/db`

**Quick Reference Commands:**

```bash
# View Secrets Manager secret
aws secretsmanager get-secret-value --secret-id ops-pipeline/db --region us-west-2

# View SSM parameters
aws ssm get-parameter --name /ops-pipeline/rss_feeds --region us-west-2
aws ssm get-parameter --name /ops-pipeline/tickers --region us-west-2
aws ssm get-parameter --name /ops-pipeline/signal_cooldown_minutes --region us-west-2

# List security groups
aws ec2 describe-security-groups --group-ids sg-0cd16a909f4e794ce sg-09379d105ed7901a9 --region us-west-2

# View IAM roles
aws iam get-role --role-name ops-pipeline-lambda-role
aws iam get-role --role-name ops-pipeline-ecs-task-role
```

---

## Cost Estimate (Monthly)

**Phase 2 Resources:**
- S3 Bucket: $0.00 (no data yet)
- Secrets Manager: $0.40 (1 secret × $0.40/month)
- SSM Parameters: $0.00 (Standard tier is free)
- Security Groups: $0.00 (free)
- IAM Roles: $0.00 (free)

**Total Phase 2:** ~$0.40/month

**Note:** Phase 3 (RDS) will add ~$15-20/month for db.t3.micro instance.
