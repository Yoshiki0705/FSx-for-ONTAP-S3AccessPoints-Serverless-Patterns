# AGENTS.md

> Project-specific instructions for AI coding agents working in this repository.

## Project Overview

FSx for ONTAP S3 Access Points Serverless Patterns — a library of **28 industry-specific use cases (UC1-UC28)** + **1 SAP/ERP pattern** + **6 FlexCache/FlexClone patterns (FC1-FC6)** + **1 event-driven FPolicy pipeline** using Amazon FSx for ONTAP S3 Access Points. Each pattern is an independent CloudFormation/SAM template with shared Python modules.

**Test coverage**: 1,499+ unit/property tests | 126 test files | cfn-lint + ruff validation

## Core Commands

```bash
# Quick test (key patterns)
make test-quick

# Full test suite
make test

# Lint
make lint

# Single pattern test
make test-uc1    # UC1 legal-compliance
make test-uc6    # UC6 semiconductor-eda
make test-sap    # SAP/ERP adjacent
make test-fc1    # FC1 flexcache-anycast-dr

# Build & deploy (requires samconfig.toml)
make build-uc1
make deploy-uc1

# Security scan
make security

# Clean build artifacts
make clean

# Manual pytest (specific pattern)
python3 -m pytest semiconductor-eda/tests/ -v
python3 -m pytest shared/tests/ -q

# cfn-lint validation
cfn-lint legal-compliance/template.yaml sap-erp-adjacent/template.yaml
```

## Project Layout

```
├── {uc-name}/              # 28 UC + SAP + 6 FC directories
│   ├── template.yaml       # SAM/CloudFormation template
│   ├── functions/          # Lambda function handlers
│   │   └── {func}/handler.py
│   ├── tests/              # UC-specific tests (pytest + hypothesis)
│   ├── docs/               # Architecture, demo guide (8 languages)
│   ├── samconfig.toml.example  # SAM deploy config template
│   └── README.md           # 8 languages (ja/en/ko/zh-CN/zh-TW/fr/de/es)
├── shared/                 # Shared Python modules (imported by all patterns)
│   ├── s3ap_helper.py      # S3 Access Point helper (core abstraction)
│   ├── ontap_client.py     # ONTAP REST API client
│   ├── fsx_helper.py       # AWS FSx API helper
│   ├── exceptions.py       # Common exceptions + error handler decorator
│   ├── observability.py    # EMF metrics + structured logging
│   ├── data_classification.py  # Data classification labels (INTERNAL/CUI/etc.)
│   ├── human_review.py     # Confidence-based Human Review decisions
│   ├── idempotency_checker.py  # HYBRID mode deduplication
│   ├── lineage.py          # Compliance-grade data lineage
│   ├── guardrails.py       # Capacity guardrails
│   ├── slo.py              # SLO monitoring
│   ├── schemas/            # TypedDict event/response schemas
│   │   ├── events.py       # DiscoveryOutput, ProcessingOutput, etc.
│   │   └── fpolicy-event-schema.json
│   ├── fpolicy/            # FPolicy protobuf/XML parsers
│   ├── fpolicy-server/     # FPolicy TCP server (ECS Fargate)
│   ├── cfn/                # Shared CloudFormation snippets
│   ├── lambdas/            # Shared Lambda functions
│   └── tests/              # Shared module tests
├── event-driven-fpolicy/   # FPolicy event-driven infrastructure
├── test-data/              # Sample data per UC (gitignore override)
├── scripts/                # Automation scripts
├── docs/                   # Documentation and guides (40+ docs)
├── security/               # cfn-guard rules
├── Makefile                # Developer workflow commands
└── .github/workflows/      # CI/CD (lint → test → security → deploy)
```

## Architecture Patterns

- **Trigger**: EventBridge Scheduler (polling) OR FPolicy EventBridge Rule (event-driven)
- **Orchestration**: Step Functions state machine per UC
- **Compute**: Lambda functions (Python 3.12, ARM64, 256-1024MB)
- **Storage access**: FSx ONTAP S3 Access Points (read/write via S3ApHelper)
- **AI/ML**: Bedrock (Nova/Claude), Textract, Comprehend, Rekognition, SageMaker
- **Analytics**: Athena + Glue Data Catalog
- **Secrets**: Secrets Manager for ONTAP credentials
- **Networking**: VPC-internal (ONTAP API) + VPC-external (S3 AP Internet Origin)
- **TriggerMode**: POLLING / EVENT_DRIVEN / HYBRID (per-UC parameter)
- **DemoMode**: `true` allows running without FSx ONTAP (regular S3 bucket)

## Coding Conventions

### Python

- Python 3.12 target (ARM64 Lambda)
- Type hints on all function signatures (use `shared/schemas/events.py` TypedDicts)
- Docstrings on all public functions (Google style)
- `from __future__ import annotations` at top of every module
- No wildcard imports
- Use `logging` module, never `print()` in Lambda handlers
- Error handling: raise domain exceptions from `shared/exceptions.py`
- Use `shared/observability.py` EmfMetrics for CloudWatch metrics
- Use `shared/human_review.py` for confidence-based review decisions
- Use `shared/data_classification.py` for output data labeling

### CloudFormation / SAM

- Each UC template is self-contained (deployable independently)
- Use `!Sub` for all resource names (include `${AWS::StackName}`)
- Conditions for optional resources (VPC Endpoints, CloudWatch Alarms, X-Ray)
- TriggerMode Conditions: `IsPollingOrHybrid`, `IsEventDrivenOrHybrid`
- Tags on all resources: `UseCase`, `Phase`
- IAM: least-privilege, per-function roles
- Log retention: `LogRetentionInDays` parameter (default 90, compliance: 2557)
- Step Functions: always include Retry/Catch on Task states
- Step Functions ASL: prefer `DefinitionUri` over inline `DefinitionBody` (cfn-lint compat)
- `RecursiveDeleteOption: true` on Athena WorkGroups (single key, no duplicates)
- `SNSPublishMessagePolicy` requires `TopicName` (not `TopicArn`)

### Naming

- UC directories: kebab-case (`legal-compliance`, `financial-idp`)
- Lambda functions: `{stack-name}-{function-name}`
- Python modules: snake_case
- CloudFormation resources: PascalCase
- Environment variables: UPPER_SNAKE_CASE
- Handler files: `handler.py` (not `index.py`)
- Handler entry: `handler.handler` (not `index.handler`)

## Testing

- Framework: pytest + hypothesis (property-based)
- Mocking: moto (AWS services)
- Coverage threshold: 80%
- Test location: `shared/tests/` (shared) + `{uc}/tests/` (UC-specific)
- Run before every commit: `make test-quick`
- conftest.py in each test dir for sys.path + fixtures

### shared/ Module Resolution

```python
# In conftest.py (each pattern's tests/)
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))  # repo root
sys.path.insert(0, str(Path(__file__).parent.parent / "functions" / "discovery"))
```

```bash
# Run from repo root (PYTHONPATH auto-resolved)
python3 -m pytest sap-erp-adjacent/tests/ -v
```

### Known test exclusions

- `tests/e2e/` — requires deployed AWS stacks
- `tests/load/` — requires deployed infrastructure
- `shared/tests/test_canary_properties.py` — requires live S3 AP

## Verification Checklist

Before submitting changes, run:

1. `make test-quick` — key tests pass
2. `make lint` — no lint errors
3. `cfn-lint` on modified templates
4. If modifying UC templates: verify TriggerMode params + conditions present
5. If adding new shared module: add tests in `shared/tests/`
6. If modifying README: ensure Governance Note + Performance Considerations present
7. If adding output: include `data_classification` field

## New Pattern: Field-Shareable Definition of Done

A new industry pattern is considered field-shareable (ready for Partner/SI customer conversations) only when ALL of the following are met:

- [ ] CloudFormation template passes `cfn-lint` with zero errors
- [ ] DemoMode=true execution succeeds (no FSx ONTAP dependency)
- [ ] Unit tests + property-based tests pass
- [ ] Success Metrics defined (Business Outcome / Technical KPI / Quality KPI / Cost KPI / Go-No-Go)
- [ ] Data classification labels documented
- [ ] Human review thresholds defined and documented
- [ ] README in JP + EN at minimum
- [ ] `samconfig.toml.example` included
- [ ] Governance Note present (for regulated/safety-critical domains)

## Key Design Decisions

### S3ApHelper is the Core Abstraction

All S3 AP access goes through `shared/s3ap_helper.py`. It accepts both S3 AP aliases and regular S3 bucket names (enabling DemoMode). Never call `boto3.client('s3')` directly in Lambda handlers.

### VPC Split Architecture

- **VPC-internal Lambda**: For ONTAP REST API access (management LIF is private)
- **VPC-external Lambda**: For Internet-origin S3AP access (no VpcConfig)
- **Never mix**: A single Lambda cannot access both ONTAP mgmt LIF and Internet-origin S3AP

### Output Destination Pattern

- `OutputDestination=STANDARD_S3` — write to new S3 bucket (default)
- `OutputDestination=FSXN_S3AP` — write back to FSx ONTAP via S3 AP (NFS/SMB users see results)

### Human Review Pattern

```python
from shared.human_review import evaluate_confidence
decision = evaluate_confidence(confidence=0.72)
# decision.action: "AUTO_APPROVE" | "HUMAN_REVIEW" | "REJECT"
```

## Common Pitfalls

| Pitfall | Solution |
|---------|----------|
| `RecursiveDeleteOption` duplicate key in YAML | Single key only: `RecursiveDeleteOption: true` |
| `SNSPublishMessagePolicy` with TopicArn | Use `TopicName: !GetAtt Topic.TopicName` |
| `Handler: index.handler` but file is `handler.py` | Use `Handler: handler.handler` |
| `DefinitionBody` inline in SAM StateMachine | Use `DefinitionUri: statemachine/workflow.asl.json` |
| CloudFormation `validate-template` fails for large templates | Use S3 URL upload for templates >51KB |
| Internet-origin S3AP from VPC Lambda | Use VPC-external Lambda or NAT Gateway |
| S3 Gateway VPC Endpoint + Internet-origin S3AP | Does NOT work — use NAT or VPC-external |
| ONTAP REST API auth on SVM IP | Use filesystem management IP, not SVM IP |
| FlexClone `nas.security_style` | Cannot specify — inherited from parent volume |
| Modifying enabled FPolicy policy | Disable → modify → re-enable sequence |
| `mount -o vers=4` negotiates NFSv4.2 | Always use explicit `vers=4.1` |
| Hypothesis + moto DynamoDB slow | Use `deadline=None` in `@given()` settings |
| Test file name collision across patterns | Use unique test file names or run per-directory |

## S3 Access Point Critical Knowledge

### IAM ARN Format (Most Common Error)

```yaml
# ✅ Correct
Resource: !Sub "arn:aws:s3:${AWS::Region}:${AWS::AccountId}:accesspoint/${S3AccessPointName}"
Resource: !Sub "arn:aws:s3:${AWS::Region}:${AWS::AccountId}:accesspoint/${S3AccessPointName}/object/*"

# ❌ Wrong (bucket-style ARN does not work for S3 AP)
Resource: !Sub "arn:aws:s3:::${S3AccessPointAlias}"
```

### Dual-Layer Authorization

Both must Allow:
1. **AWS-side**: IAM identity policy + S3 AP resource policy
2. **ONTAP-side**: File system identity (UNIX UID or Windows AD user)

### Supported Operations

PutObject (max 5GB), GetObject, ListObjectsV2, HeadObject, DeleteObject, MultipartUpload.
NOT supported: GetBucketNotificationConfiguration, Presigned URLs (documented as unsupported).

### NetworkOrigin (Immutable After Creation)

- `Internet`: Accessible from anywhere with valid credentials. NOT via S3 Gateway VPC Endpoint.
- `VPC`: Accessible only from bound VPC via S3 Gateway/Interface Endpoint.

## External Dependencies

- **AWS Region**: ap-northeast-1 (Tokyo) — primary deployment target
- **ONTAP version**: 9.17.1P6 (supports FPolicy, Persistent Store, protobuf)
- **Python packages**: boto3, urllib3
- **Dev packages**: pytest, hypothesis, moto, ruff, cfn-lint, bandit

## Documentation Language

- Code, variable names, CloudFormation resources: English
- Documentation, comments, README: Japanese (primary) + English + 6 other languages
- Commit messages: English (conventional commits: `feat:`, `fix:`, `docs:`, `chore:`)
- No persona names in git content (use role-based descriptions)

## Security & Privacy (Public Repository)

This is a **public repository**. All committed content is visible to the world.

### Placeholder Rules

| Real Data | Placeholder |
|-----------|-------------|
| AWS Account ID | `123456789012` |
| Secret ARN suffix | `-XXXXXX` |
| VPC/Subnet/SG IDs | `vpc-0123456789abcdef0` |
| File System ID | `fs-0123456789abcdef0` |
| Real IP addresses | `10.0.x.x` or `<management-ip>` |
| SSH key paths | `<your-ssh-key.pem>` |
| Personal file paths | Relative paths or `${PROJECT_DIR}` |
| S3 AP Alias | Use parameter reference `!Ref S3AccessPointAlias` |

### 🚫 Never Commit

- Real AWS account IDs, resource IDs, or IP addresses
- Screenshots without masking (use `scripts/mask_uc_demos.py`)
- `.pem` files, SSH keys, `.env` files
- Personal file paths (`/Users/<username>/...`)
- Persona names (use role descriptions: "Storage Specialist lens")
- AWS Support case numbers or internal references

### Pre-Commit

```bash
make lint
make test-quick
git diff --cached | grep -i '/Users/' && echo "LEAK DETECTED" || echo "OK"
```

## Cost Awareness

### High-Cost Resources (monitor actively)

| Resource | Monthly Cost | Notes |
|----------|-------------|-------|
| FSx ONTAP (128 MBps) | ~$194 | Core infrastructure, always running |
| NAT Gateway | ~$32 each | Needed for VPC Lambda → Internet |
| Interface VPC Endpoints | ~$7.20 each | ECR, Logs, STS, SQS, SecretsManager |
| ECS Fargate (FPolicy) | ~$35 | Set desiredCount=0 when not testing |
| Transfer Family | ~$82 | Delete when not needed |

### Cost Optimization Patterns

- Use `EnableVpcEndpoints=false` for PoC (saves ~$43/month)
- Use `DemoMode=true` to test without FSx ONTAP
- Disable EventBridge Schedules when not actively testing
- Set ECS desiredCount=0 for FPolicy server when idle
- Use `amazon.nova-lite-v1:0` (cheapest Bedrock model) for testing

## Persona Review Lenses

When reviewing changes, consider these perspectives:

| Persona | Focus Areas |
|---------|-------------|
| Storage Specialist | Throughput design, shared bandwidth (NFS/SMB/S3AP), tail latency, FlexCache hit rate, Range GET patterns |
| Partner/SI | PoC ease (30-min deploy), cost estimation, customer-facing docs, DemoMode |
| Public Sector / Governance | Data classification, audit trails, Human Review, FISC/HIPAA/NARA compliance, incident response |
| Application Developer | Code readability, TypedDict schemas, shared/ module reuse, Makefile, local testing |

## Key Documentation

| Document | Purpose |
|----------|---------|
| [Demo Mode Guide](docs/demo-mode-guide.md) | Run without FSx ONTAP |
| [Customization Guide](docs/customization-guide.md) | Adapt patterns to your workload |
| [Cost Calculator](docs/cost-calculator.md) | Estimate monthly costs |
| [Comparison Alternatives](docs/comparison-alternatives.md) | S3 AP vs EFS vs NFS vs DataSync |
| [PoC Go/No-Go Template](docs/poc-go-nogo-template.md) | PoC success criteria |
| [Incident Response Playbook](docs/incident-response-playbook.md) | Security incident handling |
| [S3AP Compatibility Notes](docs/s3ap-compatibility-notes.md) | Known constraints + workarounds |
| [S3AP Performance](docs/s3ap-performance-considerations.md) | Throughput design guidance |
| [Local Testing](docs/local-testing-quick-start.md) | sam local + pytest setup |
| [Partner/SI Checklist](docs/partner-si-delivery-checklist.md) | Customer delivery workflow |
| [Pattern Selection Guide](docs/pattern-selection-guide.md) | Customer situation → recommended UC |
| [ONTAP Integration Notes](docs/ontap-integration-notes.md) | NAS coexistence, identity, data protection, OT |
| [S3 Bucket User Guide](docs/s3-bucket-user-guide.md) | Standard S3 vs FSx ONTAP S3 AP differences |
