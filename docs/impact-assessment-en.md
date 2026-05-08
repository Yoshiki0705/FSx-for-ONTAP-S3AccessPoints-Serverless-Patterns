# Existing Environment Impact Assessment Guide

🌐 **Language / 言語**: [日本語](impact-assessment.md) | [English](impact-assessment-en.md) | [한국어](impact-assessment-ko.md) | [简体中文](impact-assessment-zh-CN.md) | [繁體中文](impact-assessment-zh-TW.md) | [Français](impact-assessment-fr.md) | [Deutsch](impact-assessment-de.md) | [Español](impact-assessment-es.md)

## Overview

This document evaluates the impact on existing environments when enabling features across all phases, and provides safe enablement procedures and rollback methods.

> **Scope**: Phase 1–5 (this document will be updated as new phases are added)

Design principles:
- **Phase 1 (UC1–UC5)**: Independent CloudFormation stacks. Impact limited to ENI creation in VPC/subnets
- **Phase 2 (UC6–UC14)**: Independent stacks with cross-region API calls
- **Phase 3 (Cross-cutting enhancements)**: Extensions to existing UCs. All features opt-in via CloudFormation Conditions (disabled by default)
- **Phase 4 (Production SageMaker, Multi-Account, Event-Driven)**: UC9 extensions + new templates. All opt-in
- **Phase 5 (Serverless Inference, Cost Optimization, CI/CD, Multi-Region)**: All opt-in (disabled by default). No impact unless explicitly enabled

---

## Phase 1: Foundation UCs (UC1–UC5)

### Parameters That Affect Existing Environments

| Parameter | Default | Scope | Impact When Enabled |
|-----------|---------|-------|---------------------|
| VpcId / PrivateSubnetIds | — (required) | Target VPC | Lambda ENIs are created |
| EnableS3GatewayEndpoint | "true" | VPC route tables | ⚠️ Conflicts if existing S3 Gateway EP exists |
| EnableVpcEndpoints | "false" | VPC | Interface VPC Endpoints created (Secrets Manager, FSx, CloudWatch, SNS) |
| PrivateRouteTableIds | — (required) | Route tables | S3 Gateway EP associated with route tables |
| ScheduleExpression | "rate(1 hour)" | EventBridge | Periodically executes Step Functions |
| NotificationEmail | — (required) | SNS | Subscription confirmation email sent |
| EnableCloudWatchAlarms | "false" | CloudWatch | New alarms created (no impact on existing) |

### Considerations

1. **EnableS3GatewayEndpoint**: Set to `false` if existing S3 Gateway Endpoint exists in same VPC.
2. **VpcId / PrivateSubnetIds**: Watch for IP address exhaustion in specified subnets.
3. **ScheduleExpression**: Scheduled execution starts immediately after deployment.

---

## Phase 2: Extended UCs (UC6–UC14)

### Additional Parameters

| Parameter | Default | Scope | Impact When Enabled |
|-----------|---------|-------|---------------------|
| CrossRegion | "us-east-1" | Cross-region API | Sends Textract / Comprehend Medical API to specified region |
| MapConcurrency | 10 | Step Functions Map | Parallel Lambda count. Affects concurrency quota |
| LambdaMemorySize | 256–1024 | Lambda | Memory allocation. Direct cost impact |

### Considerations

1. **MapConcurrency**: Ensure total doesn't exceed Lambda concurrency quota (default 1000).
2. **CrossRegion**: Adds latency (50–200ms) and data transfer costs.
3. **VPC Endpoints sharing**: First UC creates endpoints; subsequent UCs in same VPC can share them.

---

## Phase 3: Cross-Cutting Enhancements

### Parameters

#### Theme A: Kinesis Streaming (UC11 only)

| Parameter | Default | Scope | Impact |
|-----------|---------|-------|--------|
| EnableStreamingMode | "false" | UC11 | New resources only. No impact on existing polling path |
| KinesisShardCount | 1 | Kinesis | Direct cost ($0.015/shard/hour) |

#### Theme B: SageMaker Batch Transform (UC9 only)

| Parameter | Default | Scope | Impact |
|-----------|---------|-------|--------|
| EnableSageMakerTransform | "false" | UC9 Step Functions | ⚠️ Adds SageMaker path to workflow |
| MockMode | "true" | SageMaker Invoke Lambda | Mock mode doesn't create real jobs |

#### Theme C: Observability (All 14 UCs)

| Parameter | Default | Scope | Impact |
|-----------|---------|-------|--------|
| EnableXRayTracing | "true" | All Lambda + Step Functions | ⚠️ X-Ray trace transmission begins ($5/million traces) |

### Non-Destructive Guarantee

- Optional imports — no impact on existing Lambdas when unused
- Default values maintain Phase 2 identical behavior

---

## Phase 4: Production SageMaker, Multi-Account, Event-Driven

### Parameters

#### Theme A: DynamoDB Task Token Store (UC9)

| Parameter | Default | Scope | Impact |
|-----------|---------|-------|--------|
| EnableDynamoDBTokenStore | "false" | UC9 Lambda | New DynamoDB table. Changes token management |
| TOKEN_STORAGE_MODE | "direct" | SageMaker Lambda | "dynamodb" switches to DynamoDB-based management |

#### Theme B: Real-time Inference + A/B Testing (UC9)

| Parameter | Default | Scope | Impact |
|-----------|---------|-------|--------|
| EnableRealtimeEndpoint | "false" | UC9 | ⚠️ Creates always-on SageMaker Endpoint |
| EnableABTesting | "false" | UC9 | Multi-Variant Endpoint configuration |
| EnableModelRegistry | "false" | UC9 | Creates Model Package Group |

#### Theme C/D: Multi-Account / Event-Driven

No impact unless templates are deployed. Event-Driven is an independent stack.

### Considerations

1. **EnableRealtimeEndpoint**: Always-on cost (~$166/month for ml.m5.xlarge).
2. **EnableDynamoDBTokenStore**: Running jobs may fail callbacks during switchover.
3. **Multi-Account**: Cross-account IAM roles created. Always set External ID + Permission Boundary.

---

## Phase 5: Serverless Inference, Cost Optimization, CI/CD, Multi-Region

### Parameters

#### Theme A: SageMaker Serverless Inference

| Parameter | Default | Scope | Impact |
|-----------|---------|-------|--------|
| InferenceType | "none" | UC9 Step Functions | "serverless" modifies Choice State routing |
| ServerlessMemorySizeInMB | 4096 | SageMaker | New resources (no impact on existing endpoints) |
| ServerlessMaxConcurrency | 5 | SageMaker | New resources |

#### Theme B: Cost Optimization

| Parameter | Default | Scope | Impact |
|-----------|---------|-------|--------|
| EnableScheduledScaling | "false" | Existing SageMaker Endpoint | ⚠️ Modifies scaling of existing endpoints |
| EnableBillingAlarms | "false" | CloudWatch | New alarms (no impact on existing) |
| EnableAutoStop | "false" | Existing SageMaker Endpoint | ⚠️ Automatically stops idle endpoints |

#### Theme C: CI/CD

| Parameter | Default | Scope | Impact |
|-----------|---------|-------|--------|
| N/A | — | GitHub Actions | Workflow files only. No impact on existing deployments |

#### Theme D: Multi-Region

| Parameter | Default | Scope | Impact |
|-----------|---------|-------|--------|
| EnableMultiRegion | "false" | DynamoDB, Route 53 | ⚠️ Converts DynamoDB tables to Global Tables (irreversible) |

### Considerations

1. **EnableScheduledScaling**: Instance count is reduced to the configured minimum outside business hours. Note: `DesiredInstanceCount=0` is only supported for endpoints hosting [Inference Components](https://docs.aws.amazon.com/sagemaker/latest/dg/endpoint-auto-scaling-zero-instances.html). Standard endpoints have a minimum of 1.
2. **EnableAutoStop**: Protect critical endpoints with `DoNotAutoStop=true` tag.
3. **EnableMultiRegion**: **Irreversible operation**. DynamoDB Streams must be enabled first.

---

## Verification Methods

### Pre-Deployment Checklist

1. [ ] Verify VPC IP address availability
2. [ ] Check for existing S3 Gateway Endpoints
3. [ ] Verify Lambda concurrency quota headroom
4. [ ] Verify AI/ML service availability in target region
5. [ ] Check CloudFormation stack count limit (default 2000)
6. [ ] All existing tests pass: `pytest shared/tests/ use-cases/*/tests/ -v`
7. [ ] No cfn-lint errors: `cfn-lint use-cases/*/template-deploy.yaml`
8. [ ] Opt-in parameters at default values (disabled)
9. [ ] Existing Step Functions workflows operate without changes
10. [ ] Existing Lambda functions don't import new phase modules

### Post-Deployment Verification

1. [ ] Manually execute existing Step Functions workflows — confirm success
2. [ ] No anomalies in CloudWatch metrics
3. [ ] Lambda error rate has not increased
4. [ ] VPC Endpoint status is "available"
5. [ ] No changes in existing DynamoDB table throughput

---

## Rollback Procedures

### Phase 1/2: Stack Deletion

```bash
aws s3 rm s3://<output-bucket> --recursive
aws cloudformation delete-stack --stack-name <stack-name>
aws cloudformation wait stack-delete-complete --stack-name <stack-name>
```

### Phase 3: Feature Disablement

```bash
aws cloudformation update-stack --stack-name <stack> --use-previous-template \
  --parameters ParameterKey=EnableStreamingMode,ParameterValue=false
aws cloudformation update-stack --stack-name <stack> --use-previous-template \
  --parameters ParameterKey=EnableSageMakerTransform,ParameterValue=false
aws cloudformation update-stack --stack-name <stack> --use-previous-template \
  --parameters ParameterKey=EnableXRayTracing,ParameterValue=false
```

### Phase 4: Feature Disablement

```bash
aws sagemaker delete-endpoint --endpoint-name <endpoint-name>
aws cloudformation update-stack --stack-name <stack> --use-previous-template \
  --parameters ParameterKey=EnableDynamoDBTokenStore,ParameterValue=false
aws cloudformation delete-stack --stack-name <event-driven-stack>
```

### Phase 5: Feature Disablement

```bash
aws application-autoscaling delete-scheduled-action --service-namespace sagemaker \
  --scheduled-action-name ScaleUpBusinessHours \
  --resource-id endpoint/<name>/variant/AllTraffic \
  --scalable-dimension sagemaker:variant:DesiredInstanceCount
aws events disable-rule --name <auto-stop-rule-name>
aws cloudformation delete-stack --stack-name <billing-alarm-stack>
aws sagemaker delete-endpoint --endpoint-name <serverless-endpoint>
```

---

## Safe Enablement Order

| Order | Feature | Phase | Risk | Notes |
|-------|---------|-------|------|-------|
| 1 | UC1 deployment (minimal) | 1 | Low | Independent stack |
| 2 | Observability (X-Ray + EMF) | 3 | Low | Graceful degradation |
| 3 | CI/CD pipeline | 5 | None | Workflow files only |
| 4 | Kinesis streaming (UC11) | 3 | Low | No impact on polling path |
| 5 | SageMaker Batch Transform (UC9) | 3 | Low | MockMode=true |
| 6 | DynamoDB Task Token Store | 4 | Low | New table only |
| 7 | Serverless Inference | 5 | Low | New resources only |
| 8 | Event-Driven Prototype | 4 | Low | Independent stack |
| 9 | Billing Alarms | 5 | Low | New alarms only |
| 10 | Real-time Endpoint | 4 | Medium | ⚠️ Always-on cost |
| 11 | Scheduled Scaling | 5 | Medium | ⚠️ Modifies existing endpoints |
| 12 | Auto-Stop | 5 | Medium | ⚠️ Stops idle endpoints |
| 13 | Multi-Account | 4 | Medium | ⚠️ Cross-account IAM roles |
| 14 | Multi-Region | 5 | High | ⚠️ **Irreversible** — Global Table conversion |

---

## Cost Impact Summary

| Phase | Feature | Default | Additional Cost |
|-------|---------|---------|-----------------|
| 1/2 | VPC Endpoints | Disabled | ~$29/month (shareable per VPC) |
| 1/2 | Lambda execution | Enabled | Pay-per-use (~$0.20/M requests) |
| 3 | Kinesis Data Stream | Disabled | ~$11/shard/month |
| 3 | X-Ray | Enabled | ~$5/M traces |
| 4 | DynamoDB Token Store | Disabled | PAY_PER_REQUEST |
| 4 | Real-time Endpoint | Disabled | ⚠️ ~$166/month |
| 5 | Serverless Inference | Disabled | Pay-per-use (with cold starts) |
| 5 | Scheduled Scaling | Disabled | None (schedule change only) |
| 5 | Billing Alarms | Disabled | ~$0.30/month |
| 5 | Multi-Region | Disabled | DynamoDB Global Table costs |

---

## Related Documents

- [Cost Analysis](cost-analysis.md)
- [Streaming vs Polling Guide](streaming-vs-polling-guide-en.md)
- [Inference Cost Comparison](inference-cost-comparison.md)
- [Cost Optimization Guide](cost-optimization-guide.md)
- [CI/CD Guide](ci-cd-guide.md)
- [Multi-Region Disaster Recovery](multi-region/disaster-recovery.md)
- [Deployment Guide](guides/deployment-guide.md)

---

*This document is the Existing Environment Impact Assessment Guide for FSxN S3AP Serverless Patterns.*
