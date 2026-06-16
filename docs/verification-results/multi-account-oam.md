# Multi-Account OAM Verification Results

## Configuration

| Item | Monitoring Account | Workload Account |
|------|-------------------|-----------------|
| Account ID | 123456789012 | 234567890123 |
| Account Name | `<management-account>` | `<workload-account>` |
| Region | ap-northeast-1 | ap-northeast-1 |
| OAM Role | Sink | Link |
| Sink ARN | `arn:aws:oam:ap-northeast-1:123456789012:sink/<sink-id>` | — |
| Link ARN | — | `arn:aws:oam:ap-northeast-1:234567890123:link/<link-id>` |
| Resource Types | — | CloudWatch::Metric, Logs::LogGroup, XRay::Trace |

## Setup Method

OAM Sink + Link を AWS CLI で直接作成（CloudFormation テンプレートではなく）:

```bash
# 1. Management account: Create Sink
aws oam create-sink --name fsxn-observability-sink --region ap-northeast-1

# 2. Management account: Set Sink Policy (allow workload account)
aws oam put-sink-policy --sink-identifier <SINK_ARN> --policy '<POLICY_JSON>'

# 3. Workload account (via AssumeRole): Create Link
aws sts assume-role --role-arn arn:aws:iam::234567890123:role/OrganizationAccountAccessRole ...
aws oam create-link --label-template '$AccountName' \
  --resource-types "AWS::CloudWatch::Metric" "AWS::Logs::LogGroup" "AWS::XRay::Trace" \
  --sink-identifier <SINK_ARN> --region ap-northeast-1
```

## Verification Steps

| # | Step | Expected Result | Actual Result | Status |
|---|------|-----------------|---------------|:---:|
| 1 | Create OAM Sink in management account | Sink created | ✅ Sink ID: `<sink-id>` | ✅ |
| 2 | Set Sink Policy (allow workload account) | Policy applied | ✅ Policy set | ✅ |
| 3 | AssumeRole to workload account | Credentials obtained | ✅ Session active | ✅ |
| 4 | Create OAM Link in workload account | Link created | ✅ Link ID: `<link-id>` | ✅ |
| 5 | Verify Link visible from management account | Link appears in list | ✅ Label: `<workload-account>` | ✅ |
| 6 | Verify Resource Types shared | Metric + Logs + XRay | ✅ All 3 types confirmed | ✅ |

## Cross-Account Observability Capabilities

| Capability | Status | Notes |
|-----------|:---:|------|
| CloudWatch Metrics (cross-account view) | ✅ | Workload account metrics visible in management console |
| CloudWatch Logs Insights (cross-account query) | ✅ | Can query workload account log groups |
| X-Ray Traces (cross-account) | ✅ | Distributed traces span accounts |
| CloudWatch Dashboard (cross-account widgets) | ✅ | Dashboard can reference workload account metrics |

## Observations

1. **OAM Link creation is instant** — no propagation delay for the link itself
2. **Metric visibility**: Cross-account metrics appear in CloudWatch console within minutes of link creation
3. **No additional IAM configuration needed** in workload account beyond the OrganizationAccountAccessRole
4. **Sink Policy is the access control** — only explicitly allowed accounts can create links
5. **Cost**: OAM itself is free. Cross-account metric/log delivery follows standard CloudWatch pricing.

## Cleanup

```bash
# Workload account: Delete Link
aws oam delete-link --identifier <LINK_ARN> --region ap-northeast-1

# Management account: Delete Sink
aws oam delete-sink --identifier <SINK_ARN> --region ap-northeast-1
```

## Verification Date

**2026-05-25** — All steps completed successfully.

> **Governance Caveat**: OAM クロスアカウント共有は組織のデータガバナンスポリシーに従って設定してください。共有する Resource Types は必要最小限に制限することを推奨します。
