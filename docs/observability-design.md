# Observability and Operational Readiness Design (Phase 8 Theme N)

**Status**: DRAFT (2026-05-12)
**Scope**: Phase 8 Theme N — Observability baseline, CloudWatch Alarms, Step
Functions DLQ, EventBridge failure notifications, operational runbooks.
**Reference implementation**: UC1 (legal-compliance).

---

## 1. Goals

Existing Phase 1-7 UCs already emit EMF metrics, X-Ray traces and CloudWatch
Logs. What they lack for production readiness:

1. No alarm definitions — failures surface only via manual log inspection.
2. No DLQ for failed Step Functions executions — re-execution has no
   automated path.
3. No EventBridge → SNS failure fan-out — on-call has no push notifications.
4. No documented runbooks for common failure scenarios.

Theme N closes these gaps while keeping everything opt-in so existing
deployments are unaffected.

## 2. Non-goals

- Prometheus / Grafana / third-party APM integration.
- Detailed SLO / error budget definition per UC (deferred to a future phase).
- Auto-remediation (scope is notification + manual runbook).
- Proactive anomaly detection (CloudWatch Anomaly Detector can be layered
  on later via the `shared/cfn/observability-alarms.yaml` module).

## 3. Architecture

```
  Step Functions execution
         │
         ├── on success → (no-op)
         └── on failure
              │
              ├── Step Functions ExecutionsFailed metric → CloudWatch Alarm → SNS Topic
              ├── EventBridge rule (source=aws.states, detail-type=Step Functions Execution Status Change, status=FAILED)
              │     └── SNS publish with execution details (ARN, name, input, error)
              └── SQS DLQ (optional) for retry orchestration at state level

  Lambda function
         │
         ├── Errors metric → CloudWatch Alarm → SNS Topic
         ├── Throttles metric → CloudWatch Alarm → SNS Topic
         └── Duration p99 metric → optional CloudWatch Alarm (UC-tunable)

  DynamoDB table
         │
         ├── ReadThrottleEvents → CloudWatch Alarm → SNS Topic
         └── WriteThrottleEvents → CloudWatch Alarm → SNS Topic
```

All alarms publish to a single per-UC SNS Topic (or a shared topic when the
shared-infra stack is deployed). Subscriptions are configured at deploy time
via `AlarmNotificationEmail` parameter (email subscription) or passed via
existing SNS Topic ARN (for integrations with PagerDuty/Opsgenie).

## 4. Alarm definitions (shared baseline)

| Metric | Threshold | Period | Statistic | Comparison |
|--------|-----------|--------|-----------|------------|
| `AWS/States/ExecutionsFailed` | `>= 1` | 5 min | `Sum` | `>=` |
| `AWS/Lambda/Errors` | `>= 3` | 5 min | `Sum` | `>=` |
| `AWS/Lambda/Throttles` | `>= 1` | 5 min | `Sum` | `>=` |
| `AWS/Lambda/Duration` (p99) | function timeout × 0.8 | 15 min | `p99` | `>=` |
| `AWS/DynamoDB/ReadThrottleEvents` | `>= 1` | 5 min | `Sum` | `>=` |
| `AWS/DynamoDB/WriteThrottleEvents` | `>= 1` | 5 min | `Sum` | `>=` |

Rationale:
- Step Functions and Lambda errors are treated as "any failure is an alarm"
  because demo-grade traffic is low; production workloads may want to raise
  thresholds proportional to expected execution volume.
- p99 duration uses 80% of function timeout to catch slow degradations
  before they become timeouts (leading indicator, not lagging).
- DynamoDB throttle alarms are set at `>= 1` because throttling under
  on-demand mode indicates hot-partition or request spike issues that
  almost always warrant operator attention.

## 5. Opt-in Conditions

The alarms + DLQ + EventBridge notifications are OFF by default. Each UC
template will expose:

```yaml
Parameters:
  EnableObservability:
    Type: String
    Default: "false"
    AllowedValues: ["true", "false"]
    Description: Enable CloudWatch Alarms, Step Functions DLQ, and EventBridge failure notifications.
  AlarmNotificationEmail:
    Type: String
    Default: ""
    Description: Email address for alarm notifications. Leave empty to reuse existing SNS topic via AlarmSnsTopicArn.
  AlarmSnsTopicArn:
    Type: String
    Default: ""
    Description: Existing SNS topic ARN for alarm notifications. Ignored if AlarmNotificationEmail is set.

Conditions:
  ObservabilityEnabled: !Equals [!Ref EnableObservability, "true"]
  CreateSnsTopic: !And
    - !Condition ObservabilityEnabled
    - !Equals [!Ref AlarmSnsTopicArn, ""]
    - !Not [!Equals [!Ref AlarmNotificationEmail, ""]]
```

## 6. Shared infrastructure: `shared/cfn/observability-alarms.yaml`

A reusable nested stack / exportable template that creates:

1. `AWS::SNS::Topic` (if `CreateSnsTopic` true)
2. `AWS::SNS::Subscription` for `AlarmNotificationEmail`
3. Outputs that UC templates reference via `!ImportValue`:
   - `ObservabilitySnsTopicArn`

UC templates decide per resource whether to attach alarms using
`!If [ObservabilityEnabled, {alarm resource}, !Ref AWS::NoValue]`.

## 7. Step Functions failure handling

Two complementary mechanisms:

### 7a. Internal Retry + Catch in ASL

Every Lambda task state gets a standard Retry block:

```
"Retry": [
  {
    "ErrorEquals": ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException", "Lambda.TooManyRequestsException"],
    "IntervalSeconds": 2,
    "MaxAttempts": 3,
    "BackoffRate": 2.0
  }
],
"Catch": [
  {
    "ErrorEquals": ["States.ALL"],
    "Next": "MarkFailed",
    "ResultPath": "$.error"
  }
]
```

Most UCs already have per-task Catch blocks; this theme standardises the
Retry block across all UCs.

### 7b. External EventBridge notification

```yaml
FailureEventRule:
  Type: AWS::Events::Rule
  Condition: ObservabilityEnabled
  Properties:
    EventPattern:
      source: ["aws.states"]
      detail-type: ["Step Functions Execution Status Change"]
      detail:
        status: ["FAILED", "TIMED_OUT", "ABORTED"]
        stateMachineArn: [!Ref StateMachine]
    Targets:
      - Arn: !If [CreateSnsTopic, !Ref NotificationTopic, !Ref AlarmSnsTopicArn]
        Id: SnsTarget
        InputTransformer:
          InputPathsMap:
            execName: $.detail.name
            execStatus: $.detail.status
            execArn: $.detail.executionArn
          InputTemplate: |
            "Step Functions execution <execName> finished with status <execStatus>. Execution ARN: <execArn>"
```

## 8. Runbooks

Three new operational runbooks will live under
`docs/operational-runbooks/`:

1. `alarm-response.md` — What to do when an alarm fires
2. `sfn-rerun.md` — How to safely re-execute a failed Step Functions workflow
3. `cost-monitoring.md` — How to monitor and attribute cost per UC

## 9. UC1 reference implementation

UC1 (legal-compliance) is the smallest UC and already deployed in all
Phase 8 testing, making it the best reference implementation target.

Changes to `legal-compliance/template-deploy.yaml`:

- Add `EnableObservability`, `AlarmNotificationEmail`, `AlarmSnsTopicArn`
  parameters
- Add `ObservabilityEnabled`, `CreateSnsTopic` conditions
- Add SNS Topic + Subscription resources with `CreateSnsTopic`
- Add 6 alarm resources (SFN failed, Lambda errors/throttles/p99, DDB
  read/write throttles) — each with `ObservabilityEnabled` condition
- Add EventBridge failure rule + target
- Update ASL to include standard Retry block on every Lambda task

## 10. Rollout plan

- **Phase 8.1**: Design doc (this file) + shared template skeleton.
- **Phase 8.2**: UC1 reference implementation + e2e verification with
  intentional failure.
- **Phase 8.3**: Runbooks + operational-runbooks directory completion.
- **Phase 9**: Roll out to remaining UCs as they are re-deployed.

## 11. Rollback

All changes are behind the `EnableObservability=false` default. Existing
deployments remain unchanged unless operators explicitly opt in. The
shared-infra template is a standalone nested stack; destroying it does not
affect UC stacks as long as `EnableObservability=false`.

## 12. Open questions

1. Should alarms use `TreatMissingData: notBreaching` or `ignore`? Current
   recommendation: `notBreaching` for error-count metrics (missing == no
   errors), `ignore` for latency metrics (missing == no invocations).
2. Should the shared SNS topic be regional or cross-region? Recommendation:
   regional (per-region alarms aggregate to regional topic, operators can
   subscribe to multiple regions).
3. Should failure events trigger auto-retry via EventBridge → Lambda →
   StartExecution? Deferred to a later phase as it requires careful
   idempotency analysis per UC.
