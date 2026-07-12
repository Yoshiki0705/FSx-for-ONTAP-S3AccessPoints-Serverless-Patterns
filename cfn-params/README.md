# cfn-params — Sample CloudFormation Parameter Files

This directory contains example parameter files for `aws cloudformation create-stack --parameters file://`.

## Usage

```bash
# Copy and customize for your environment
cp cfn-params/uc1-legal-compliance.example.json cfn-params/uc1-legal-compliance.json
# Edit with your actual resource IDs...

# Deploy
aws cloudformation create-stack \
  --stack-name my-stack \
  --template-body file://solutions/industry/legal-compliance/template.yaml \
  --parameters file://cfn-params/uc1-legal-compliance.json \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND
```

## File Naming Convention

- `*.example.json` — Tracked in git (placeholder values, safe to commit)
- `*.json` — Gitignored (your real values, never commit)

## Available Examples

| File | Scenario | Deployment Path |
|------|----------|----------------|
| `uc1-legal-compliance.example.json` | Full Tier 2 deployment with VPC Endpoints | Path C (Production) |
| `sap-erp-adjacent.example.json` | SAP/ERP pattern (DemoMode off) | Path C (Production) |
| `demo-mode.example.json` | DemoMode evaluation (no FSx for ONTAP) | Path B (DemoMode) |
| `fpolicy-fargate.example.json` | FPolicy event-driven with Fargate | Path E (Tier 3) |
| `multi-stack-second.example.json` | Second stack (VPC EP disabled) | Path D (Multi-stack) |

## Format

CloudFormation standard parameter format for `--parameters file://`:

```json
[
  {
    "ParameterKey": "ParamName",
    "ParameterValue": "value"
  }
]
```

> `aws cloudformation deploy --parameter-overrides` does NOT support `file://`.
> Use `aws cloudformation create-stack --parameters file://` instead.

## Placeholder Values

All example files use safe placeholder values:

- IP addresses: RFC 5737 range `198.51.100.x` (documentation-only addresses)
- VPC/Subnet/SG IDs: `vpc-0123456789abcdef0` format
- UUIDs: `a1b2c3d4-e5f6-7890-abcd-ef1234567890` format
- Account IDs: `123456789012`
- Emails: `*@example.com`
- S3 AP aliases: descriptive names with `-ext-s3alias` suffix
