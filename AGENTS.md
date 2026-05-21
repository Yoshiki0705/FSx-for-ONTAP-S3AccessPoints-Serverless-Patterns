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

## Security & Privacy (Public Repository)

This is a **public repository**. All committed content is visible to the world.

### Placeholder Rules

| Real Data | Placeholder |
|-----------|-------------|
| AWS Account ID (12-digit) | `123456789012` or `111111111111` / `222222222222` (multi-account) |
| Secret ARN suffix | `-XXXXXX` |
| VPC ID | `vpc-0123456789abcdef0` |
| Subnet ID | `subnet-0123456789abcdef0` |
| Security Group ID | `sg-0123456789abcdef0` |
| File System ID | `fs-0123456789abcdef0` |
| Real IP addresses | `10.0.x.x` or `<management-ip>` |
| SSH key paths | `<your-ssh-key.pem>` |
| Personal file paths (`/Users/...`) | Relative paths or `${PROJECT_DIR}` |
| S3 AP Alias (real) | `fsxn-{uc}-s3ap-{hash}-ext-s3alias` (use parameter reference) |
| ECR Registry | `${AWS::AccountId}.dkr.ecr.${AWS::Region}.amazonaws.com` |

### Coding Rules

- Never hardcode AWS account IDs in templates (use `${AWS::AccountId}`)
- Never commit secrets, credentials, or `.env` files
- ONTAP credentials: always via Secrets Manager
- IAM policies: least-privilege, scoped to specific resources
- Scripts: use environment variables (`${VAR:-default}`) instead of hardcoded paths
- Screenshots: mask account IDs, resource IDs, IP addresses before committing

### 🚫 Never

- Commit real AWS account IDs, resource IDs, or IP addresses (use placeholders)
- Commit screenshots without masking personal information
- Commit `.pem` files or SSH keys
- Commit `.env`, `.env.local`, or any environment-specific config
- Commit personal file paths (`/Users/<username>/...`)
- Reference real S3 AP aliases in documentation without parameterization

### Pre-Commit Checklist

1. Run `bash scripts/pre-push-security-check.sh` — all checks PASS
2. Run `python3 scripts/_check_sensitive_leaks.py` — 0 leaks (if screenshots modified)
3. Verify `git ls-files .kiro/ .env '*.pem'` returns empty
4. Verify no `/Users/` paths in staged files: `git diff --cached | grep '/Users/'`

### Screenshot Masking

Before committing any screenshot:
1. Run `python3 scripts/mask_uc_demos.py <directory>`
2. Run `python3 scripts/_check_sensitive_leaks.py` — confirm 0 leaks
3. Only commit files from `docs/screenshots/masked/`

## Phase 13 Operational Knowledge (Lessons Learned)

### ONTAP REST API Access

- **fsxadmin authenticates on the filesystem management IP only** — NOT the SVM management IP
  - Filesystem mgmt IP: `aws fsx describe-file-systems --query 'FileSystems[0].OntapConfiguration.Endpoints.Management.IpAddresses[0]'`
  - SVM mgmt IP (different): `aws fsx describe-storage-virtual-machines --query 'StorageVirtualMachines[0].Endpoints.Management.IpAddresses[0]'`
- **Password reset**: Use `aws fsx update-file-system --ontap-configuration '{"FsxAdminPassword": "..."}'` then update Secrets Manager
- **SSH to ONTAP CLI**: `ssh fsxadmin@<FS_MGMT_IP>` (requires VPC-internal access via Bastion)

### FPolicy Protobuf Mode

- **Format switch is REST API only** — ONTAP 9.17.1 CLI does not support `-format` parameter
  - `PATCH /api/protocols/fpolicy/{svm_uuid}/engines/{name}` with `{"format": "protobuf"}`
- **Procedure**: disable policy → PATCH format → re-enable policy
- **Keep-alive interval is the same** in both XML and protobuf modes (PT2M)
- **Buffer sizes**: recv=262144 (256KB), send=1048576 (1MB)
- **ProtobufFrameReader max_message_size** should be ≥ 1MB to match ONTAP send_buffer

### S3 Access Point Data Plane

- **ConnectionClosedError ≠ AccessDenied** — FSx S3AP returns connection close (not 403) when:
  1. S3AP resource policy does not Allow the caller
  2. S3AP attachment lifecycle is not AVAILABLE
  3. ONTAP data plane is not serving (node health issue)
- **Diagnostic sequence**: Check policy → Check lifecycle → Check ONTAP REST API → Check volume state
- **S3AP resource policy is separate from IAM identity policy** — both must Allow
- **Internet-origin S3AP cannot be accessed from VPC Lambda via S3 Gateway Endpoint** — use VPC-external Lambda or NAT Gateway

### FlexClone via REST API

- **`nas.security_style` cannot be specified** during FlexClone creation — inherited from parent volume
- **Use filesystem management IP** (not SVM IP) for fsxadmin authentication
- **FlexClone is instant** (< 1 second) regardless of parent volume size

### CloudFormation / Lambda Patterns

- **VPC-internal Lambda**: For ONTAP REST API access (management LIF is private)
- **VPC-external Lambda**: For Internet-origin S3AP access (no VpcConfig)
- **Never mix**: A single Lambda cannot access both ONTAP mgmt LIF and Internet-origin S3AP
- **Timeout**: S3AP calls need 30s+ timeout (FSx data plane can be slow)
- **Deploy script must set S3AP resource policy** after stack creation (not manageable via CloudFormation)

### Testing

- **Hypothesis property tests**: Use `deadline=None` for tests involving moto DynamoDB (mock is slow)
- **108 tests total**: 91 unit + 17 property (Phase 12 + 13)
- **moto `@mock_aws`**: Use context manager (`with mock_aws():`) inside Hypothesis tests, not decorator
