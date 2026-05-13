# New UC Template Checklist (Phase 9 Baseline)

After Phase 9, new UCs should start from the unified baseline. Use this
checklist when adding a new UC to the pattern library.

---

## Template Parameters (required)

- [ ] `OutputDestination` (STANDARD_S3 / FSXN_S3AP, default: STANDARD_S3)
- [ ] `OutputS3APAlias` (empty default, fallback to S3AccessPointAlias)
- [ ] `OutputS3APPrefix` (default: "ai-outputs/")
- [ ] `EnableCloudWatchAlarms` (default: "false")
- [ ] `EnableVpcEndpoints` (default: "false")
- [ ] `EnableS3GatewayEndpoint` (default: "true")
- [ ] `LambdaMemorySize` (default: 512)
- [ ] `LambdaTimeout` (default: 900)
- [ ] `NotificationEmail`
- [ ] `TriggerMode` (POLLING / EVENT_DRIVEN / HYBRID, default: POLLING) — Phase 10
- [ ] `AlarmProfile` (BATCH / REALTIME / HIGH_VOLUME / CUSTOM, default: UC 別) — Phase 10
- [ ] `CustomFailureThreshold` (default: 10) — Phase 10
- [ ] `CustomErrorThreshold` (default: 3) — Phase 10
- [ ] `MaxConcurrencyUpperBound` (default: 40) — Phase 10
- [ ] `OntapApiRateLimit` (default: 100) — Phase 10
- [ ] `EnableCostScheduling` (default: "false") — Phase 10
- [ ] `BusinessHoursStart` (default: 9) — Phase 10
- [ ] `BusinessHoursEnd` (default: 18) — Phase 10

## Conditions (required)

- [ ] `UseStandardS3` / `UseFsxnS3AP` / `HasOutputS3APAlias`
- [ ] `CreateCloudWatchAlarms`
- [ ] `HasS3AccessPointName`
- [ ] `EnablePolling` / `EnableEventDriven` / `EnableIdempotency` — Phase 10
- [ ] `UseCustomProfile` — Phase 10
- [ ] `EnableCostSchedulingCondition` — Phase 10

## Lambda Functions

- [ ] Discovery Lambda: 512MB / 900s, VPC-attached
- [ ] AI/ML output Lambdas: use `OutputWriter.from_env()` (not direct s3_client)
- [ ] All Lambdas: `OUTPUT_DESTINATION`, `OUTPUT_S3AP_ALIAS`, `OUTPUT_S3AP_PREFIX` env vars

## Observability (gated by CreateCloudWatchAlarms)

- [ ] `StepFunctionsFailureAlarm` (AWS::CloudWatch::Alarm)
- [ ] `DiscoveryErrorAlarm` (AWS::CloudWatch::Alarm)
- [ ] `StepFunctionsFailureEventRule` (AWS::Events::Rule)
- [ ] `EventBridgeToSnsPolicy` (AWS::SNS::TopicPolicy)

## IAM

- [ ] S3AP write policies use dual-format (alias + full ARN via `!If HasS3AccessPointName`)
- [ ] No `s3:*` or `Resource: "*"` in Lambda execution roles
- [ ] Secrets Manager access scoped to specific secret ARN

## Deployment

- [ ] No assumption that shared VPC Endpoints already exist
- [ ] `deploy_generic_ucs.sh` auto-detection handles endpoint creation
- [ ] Template passes `cfn-lint` with 0 real errors
- [ ] Template passes `check_s3ap_iam_patterns.py`
- [ ] Template passes `check_conditional_refs.py`

## Testing

- [ ] Unit tests for all handler functions
- [ ] Tests do NOT patch `handler.boto3` if handler doesn't import boto3
- [ ] `check_handler_names.py` reports 0 undefined names

## Documentation

- [ ] `<uc>/docs/demo-guide.md` (Japanese) + 7 language variants
- [ ] Screenshot section with recommended capture list
- [ ] Processing time estimates (if applicable)
