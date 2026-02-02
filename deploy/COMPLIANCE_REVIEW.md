# Amazon Internal Standards Compliance Review

**Review Date:** 2026-01-09  
**Project:** ops-pipeline  
**Reviewer:** Automated Compliance Check

---

## ✅ COMPLIANT Areas

### Security Best Practices
- ✅ **RDS Not Publicly Accessible** - Database is VPC-only
- ✅ **Security Groups** - Least privilege (RDS only accessible from app SG)
- ✅ **Secrets Manager** - Database credentials stored securely
- ✅ **SSM Parameters** - Configuration externalized
- ✅ **VPC Endpoints** - Private connectivity to AWS services
- ✅ **No Hardcoded Credentials** - All from Secrets Manager/SSM

### IAM & Access Control
- ✅ **Separate Roles** - Lambda and ECS have distinct roles
- ✅ **Service-Linked Roles** - Using AWS managed policies where appropriate
- ✅ **VPC Lambda** - Lambdas run in VPC with security groups

### Logging & Observability
- ✅ **CloudWatch Logs** - All Lambdas log to CloudWatch
- ✅ **Structured Logging** - JSON format for parsing
- ✅ **Log Events** - Clear event types (smoke_test_start, db_connect_success, etc.)

### Cost Controls
- ✅ **Billing Alarm** - Set at $25/month threshold
- ✅ **Right-Sized Instances** - db.t3.micro (smallest practical)
- ✅ **Single-AZ** - No unnecessary Multi-AZ costs

---

## ⚠️ NON-COMPLIANT / NEEDS IMPROVEMENT

### 1. RDS Encryption at Rest - **HIGH PRIORITY**
**Issue:** RDS storage encryption is OFF  
**Risk:** Data at rest is not encrypted  
**Amazon Standard:** All RDS instances should have encryption enabled  
**Fix Required:** Rebuild RDS instance with `--storage-encrypted` flag  
**Cost Impact:** None (encryption at rest is free for RDS)

**Remediation:**
```bash
# Delete current instance
aws rds delete-db-instance --db-instance-identifier ops-pipeline-db --skip-final-snapshot

# Recreate with encryption
aws rds create-db-instance \
  --db-instance-identifier ops-pipeline-db \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --engine-version 16.11 \
  --master-username ops_pipeline_admin \
  --master-user-password <from-secrets-manager> \
  --allocated-storage 20 \
  --storage-type gp3 \
  --storage-encrypted \
  --kms-key-id alias/aws/rds \
  --db-subnet-group-name ops-pipeline-db-subnet-group \
  --vpc-security-group-ids sg-09379d105ed7901a9 \
  --db-name ops_pipeline \
  --backup-retention-period 1 \
  --no-multi-az \
  --no-publicly-accessible
```

### 2. Resource Tagging - **MEDIUM PRIORITY**
**Issue:** No tags on any resources  
**Amazon Standard:** All resources must have tags:
- `Owner` - Team or individual responsible
- `Environment` - dev/test/prod
- `CostCenter` - Billing allocation
- `Application` - Application name

**Resources Missing Tags:**
- RDS instance
- Lambda functions
- Security groups
- VPC endpoints
- S3 bucket

**Remediation:**
```bash
# Tag RDS instance
aws rds add-tags-to-resource \
  --resource-name arn:aws:rds:us-west-2:160027201036:db:ops-pipeline-db \
  --tags Key=Owner,Value=nflos Key=Environment,Value=dev Key=Application,Value=ops-pipeline

# Tag Lambda functions
aws lambda tag-resource \
  --resource arn:aws:lambda:us-west-2:160027201036:function:ops-pipeline-db-smoke-test \
  --tags Owner=nflos,Environment=dev,Application=ops-pipeline

# Similar for other resources...
```

### 3. IAM Role Permissions Too Broad - **MEDIUM PRIORITY**
**Issue:** Using `SecretsManagerReadWrite` instead of read-only  
**Amazon Standard:** Least privilege - services only need read access  
**Risk:** Services could accidentally modify/delete secrets

**Current:**
```
arn:aws:iam::aws:policy/SecretsManagerReadWrite
```

**Should Be:**
Custom policy with only:
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret"
    ],
    "Resource": "arn:aws:secretsmanager:us-west-2:160027201036:secret:ops-pipeline/db-*"
  }]
}
```

### 4. Secrets Manager KMS Encryption - **LOW PRIORITY**
**Issue:** Using AWS managed key instead of customer-managed KMS key  
**Amazon Standard:** Use customer-managed keys for audit trail and key rotation control  
**Current:** Default AWS managed key  
**Should Be:** Customer-managed KMS key

### 5. Lambda X-Ray Tracing Disabled - **LOW PRIORITY**
**Issue:** Lambda functions have `TracingConfig.Mode: PassThrough`  
**Amazon Standard:** Enable X-Ray for distributed tracing  
**Fix:** Add `--tracing-config Mode=Active` when creating functions

### 6. No Dead Letter Queues - **LOW PRIORITY**
**Issue:** Lambda failures are not captured for retry  
**Amazon Standard:** Configure DLQ (SQS or SNS) for failed invocations  
**Risk:** Lost events on transient failures

### 7. Lambda Timeout Settings - **INFO**
**Current:**
- Smoke test: 15 seconds
- Migration: 60 seconds

**Best Practice:** Set timeout based on actual execution time + buffer  
**Recommendation:** Monitor CloudWatch metrics and adjust if needed

### 8. No Backup Verification - **MEDIUM PRIORITY**
**Issue:** 1-day backup retention but no restore testing  
**Amazon Standard:** Regular backup restore tests to verify recoverability  
**Recommendation:** Document restore procedure and test monthly

---

## 📋 Compliance Checklist

### Security ✅ Mostly Compliant
- [x] RDS not publicly accessible
- [x] VPC security groups properly configured
- [x] Secrets Manager for credentials
- [ ] ⚠️ RDS encryption at rest (NEEDS FIX)
- [ ] ⚠️ Customer-managed KMS keys
- [x] VPC endpoints for AWS services
- [x] No hardcoded credentials

### IAM & Access Management ⚠️ Needs Improvement
- [x] Separate roles per service type
- [ ] ⚠️ IAM roles too permissive (ReadWrite vs ReadOnly)
- [x] Service-linked roles used appropriately
- [x] No inline policies

### Observability ⚠️ Partial
- [x] CloudWatch Logs enabled
- [x] Structured JSON logging
- [ ] ⚠️ X-Ray tracing disabled
- [ ] No CloudWatch alarms yet (Phase 10)
- [ ] No dashboards yet

### Tagging ❌ Non-Compliant
- [ ] ⚠️ No resource tags (Owner, Environment, CostCenter, Application)

### Cost Management ✅ Compliant
- [x] Billing alarm configured
- [x] Right-sized resources
- [x] Single-AZ deployment for dev/test
- [x] Cost-optimized storage (gp3)

### Disaster Recovery ⚠️ Minimal
- [x] Automated backups enabled (1 day)
- [ ] ⚠️ No restore testing documented
- [ ] No multi-region considerations

---

## Priority Actions Before Production

### Must Fix (Security)
1. **Enable RDS encryption at rest** - Rebuild with encryption
2. **Add resource tags** - All resources need Owner, Environment, Application
3. **Tighten IAM permissions** - Use read-only policies

### Should Fix (Operational Excellence)
4. **Enable Lambda X-Ray tracing** - For debugging
5. **Add dead letter queues** - Capture failed Lambda invocations
6. **Document backup restore procedure** - Test recovery

### Nice to Have (Cost/Observability)
7. **Customer-managed KMS keys** - Better audit trail
8. **CloudWatch dashboards** - Visualize system health
9. **Consider Aurora Serverless** - If scaling needed later

---

## Recommendation

**For MVP/Development:** Current setup is acceptable with these two changes:
1. ✅ Keep existing setup to maintain momentum
2. ⚠️ **MUST ADD:** Resource tags (takes 5 minutes)
3. ⚠️ **PLAN TO FIX:** RDS encryption when moving to production

**For Production:** Address all HIGH and MEDIUM priority items above.

---

**Should I:**
- **A)** Add resource tags now (5 minutes)?
- **B)** Continue with Phase 5 and document encryption fix for later?
- **C)** Rebuild RDS with encryption now (~10 minutes downtime)?
