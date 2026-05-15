# AGENTS.md

> Project-specific instructions for AI coding agents working in this repository.

## Project Overview

FSx for ONTAP S3 Access Points Serverless Patterns — a library of 17 industry-specific serverless automation patterns using Amazon FSx for NetApp ONTAP S3 Access Points. Each use case (UC) is an independent CloudFormation/SAM template with shared Python modules.

## Core Commands

```bash
# Run all tests (from repo root)
pytest shared/tests/ -v

# Run tests with coverage
pytest shared/tests/ --cov=shared --cov-report=term --cov-fail-under=80

# Lint (ruff)
ruff check .

# Validate all CloudFormation templates (Python)
python3 -c "
from cfnlint.decode import cfn_yaml
import glob, sys
for t in sorted(glob.glob('*/template.yaml')):
    try: cfn_yaml.load(t)
    except Exception as e: print(f'FAIL: {t}: {e}'); sys.exit(1)
print('All templates valid')
"
```

## Project Layout

```
├── {uc-name}/              # 17 UC directories (independent CloudFormation templates)
│   ├── template.yaml       # SAM/CloudFormation template
│   ├── functions/          # Lambda function handlers
│   │   └── {func}/handler.py
│   ├── tests/              # UC-specific tests
│   └── README.md
├── shared/                 # Shared Python modules (imported by all UCs)
│   ├── ontap_client.py     # ONTAP REST API client
│   ├── fsx_helper.py       # AWS FSx API helper
│   ├── s3ap_helper.py      # S3 Access Point helper
│   ├── exceptions.py       # Common exceptions + error handler
│   ├── idempotency_checker.py  # HYBRID mode deduplication
│   ├── fpolicy-server/     # FPolicy TCP server (ECS Fargate)
│   ├── cfn/                # Shared CloudFormation snippets
│   ├── lambdas/            # Shared Lambda functions
│   ├── schemas/            # JSON schemas
│   └── tests/              # Shared module tests
├── event-driven-fpolicy/   # FPolicy event-driven infrastructure
├── scripts/                # Automation scripts
├── docs/                   # Documentation and guides
└── .github/workflows/      # CI/CD
```

## Architecture Patterns

- **Trigger**: EventBridge Scheduler (polling) OR FPolicy EventBridge Rule (event-driven)
- **Orchestration**: Step Functions state machine per UC
- **Compute**: Lambda functions (Python 3.13, 256MB, 300s timeout)
- **Storage access**: FSx ONTAP S3 Access Points (read) + S3 AP (write)
- **Secrets**: Secrets Manager for ONTAP credentials
- **Networking**: Lambda in VPC with private subnets
- **TriggerMode**: POLLING / EVENT_DRIVEN / HYBRID (per-UC parameter)

## Coding Conventions

### Python

- Python 3.13 target (3.9+ compatible syntax for local dev)
- Type hints on all function signatures
- Docstrings on all public functions (Google style)
- `from __future__ import annotations` at top of every module
- No wildcard imports
- Use `logging` module, never `print()` in Lambda handlers
- Error handling: raise domain exceptions from `shared/exceptions.py`

### CloudFormation / SAM

- Each UC template is self-contained (deployable independently)
- Use `!Sub` for all resource names (include `${AWS::StackName}`)
- Conditions for optional resources (VPC Endpoints, CloudWatch Alarms, X-Ray)
- TriggerMode Conditions: `IsPollingOrHybrid`, `IsEventDrivenOrHybrid`
- Tags on all resources: `UseCase`, `Phase`
- IAM: least-privilege, per-function roles
- Log retention: 14 days

### Naming

- UC directories: kebab-case (`legal-compliance`, `financial-idp`)
- Lambda functions: `{stack-name}-{function-name}`
- Python modules: snake_case
- CloudFormation resources: PascalCase
- Environment variables: UPPER_SNAKE_CASE

## Testing

- Framework: pytest + hypothesis (property-based)
- Mocking: moto (AWS services)
- Coverage threshold: 80%
- Test location: `shared/tests/` (shared) + `{uc}/tests/` (UC-specific)
- Run before every commit: `pytest shared/tests/ -q`

### Known test exclusions

- `shared/tests/test_fpolicy_engine.py`: 3 tests skipped (handler refactored to IP Updater)

## Verification Checklist

Before submitting changes, run:

1. `pytest shared/tests/ -q` — all tests pass
2. `ruff check .` — no lint errors
3. Validate modified templates with `cfn_yaml.load()`
4. If modifying UC templates: verify TriggerMode params + conditions present
5. If adding new shared module: add tests in `shared/tests/`

## Common Pitfalls

| Pitfall | Solution |
|---------|----------|
| CloudFormation `validate-template` fails for large templates | Use S3 URL upload for templates >51KB |
| `jsonschema` 4.18+ breaks on ARM64 Lambda | Pin to `>=4.17.0,<4.18.0` |
| EventBridge prefix/suffix in same array = OR logic | Use prefix as primary filter to avoid fan-out |
| ONTAP FPolicy protobuf uses different TCP framing | Keep XML format; protobuf framing TBD |
| `AWS::Logs::Destination` requires Kinesis target | Use Log Group directly, not Destination |
| Modifying enabled FPolicy policy fails | Disable → modify → re-enable sequence |
| `mount -o vers=4` negotiates to NFSv4.2 (unsupported) | Always use explicit `vers=4.1` |
| SchedulerRole without Condition wastes resources | Always pair with `Condition: IsPollingOrHybrid` |

## External Dependencies

- **AWS Region**: ap-northeast-1 (Tokyo) — primary deployment target
- **ONTAP version**: 9.17.1P6 (supports FPolicy, Persistent Store, protobuf)
- **Python packages**: boto3, urllib3, jsonschema (<4.18)
- **Dev packages**: pytest, hypothesis, moto, ruff, cfn-lint

## Documentation Language

- Code, variable names, CloudFormation resources: English
- Documentation, comments, README: Japanese (primary) + English
- Commit messages: English

## Security

- Never hardcode AWS account IDs in templates (use `${AWS::AccountId}`)
- Never commit secrets, credentials, or `.env` files
- ONTAP credentials: always via Secrets Manager
- IAM policies: least-privilege, scoped to specific resources
- Screenshots: mask account IDs, resource IDs, IP addresses before committing
