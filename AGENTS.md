# AGENTS.md

> Project-specific instructions for AI coding agents working in this repository.

## Project Overview

FSx for ONTAP S3 Access Points Serverless Patterns — a library of **28 industry-specific use cases (UC1-UC28)** + **1 SAP/ERP pattern** + **7 FlexCache/FlexClone patterns** + **2 GenAI patterns** + **1 HA monitoring pattern** + **2 event-driven patterns** + **1 edge delivery pattern** + **6 operations optimization patterns (OPS1-OPS6)** using Amazon FSx for ONTAP S3 Access Points. Each pattern is an independent CloudFormation/SAM template with shared Python modules.

**Two pillars**: `solutions/` (S3 AP data processing patterns) + `operations/` (FS operational optimization patterns).

**Test coverage**: 2,162+ unit/property tests | 126 test files | cfn-lint + ruff validation

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
make test-ops1   # OPS1 capacity-rightsizing

# Build & deploy (requires samconfig.toml)
make build-uc1
make deploy-uc1
make build-ops1
make deploy-ops1

# Security scan
make security

# Clean build artifacts
make clean

# Manual pytest (specific pattern)
python3 -m pytest solutions/industry/semiconductor-eda/tests/ -v
python3 -m pytest shared/tests/ -q

# cfn-lint validation
cfn-lint solutions/industry/legal-compliance/template.yaml solutions/sap/erp-adjacent/template.yaml
```

## Project Layout

```
├── solutions/
│   ├── industry/                     # UC1-UC28 industry-specific patterns
│   │   └── {pattern-name}/
│   │       ├── template.yaml         # SAM/CloudFormation template
│   │       ├── functions/            # Lambda function handlers
│   │       │   └── {func}/handler.py
│   │       ├── tests/                # Pattern-specific tests (pytest + hypothesis)
│   │       ├── docs/                 # Architecture, demo guide (8 languages)
│   │       ├── samconfig.toml.example
│   │       └── README.md             # 8 languages (ja/en/ko/zh-CN/zh-TW/fr/de/es)
│   ├── sap/erp-adjacent/            # SAP/ERP pattern
│   ├── flexcache/                    # FlexCache/FlexClone patterns (7)
│   │   ├── anycast-dr/
│   │   ├── dynamic-render-workflow/
│   │   ├── rag-enterprise-files/
│   │   ├── automotive-cae/
│   │   ├── life-sciences-research/
│   │   ├── gaming-build-pipeline/
│   │   └── devops-cicd/
│   ├── genai/                        # GenAI patterns (2)
│   │   ├── kb-selfservice-curation/
│   │   └── quick-agentic-workspace/
│   ├── ha/lifekeeper-monitoring/     # HA monitoring pattern
│   ├── event-driven/                 # Event-driven patterns (2)
│   │   ├── fpolicy/
│   │   └── prototype/
│   └── edge/content-delivery/        # CDN/edge delivery pattern
├── operations/             # Operational optimization patterns (NEW)
│   ├── README.md           # Category overview + adoption roadmap
│   ├── docs/               # Cross-pattern docs (metrics-mapping, SLO, etc.)
│   ├── capacity-rightsizing/   # OPS1: Volume/throughput monitoring + AI recommendations
│   ├── snapshot-lifecycle/     # OPS4: Retention compliance + cleanup (planned)
│   ├── tiering-optimizer/      # OPS3: FabricPool policy optimization (planned)
│   ├── storage-efficiency/     # OPS2: Dedup/compression tracking (planned)
│   ├── cost-optimization/      # OPS5: FinOps integration (planned)
│   └── qos-monitoring/         # OPS6: QoS policy compliance (planned)
├── infrastructure/         # Shared infrastructure templates (not per-pattern)
│   └── demo-ad-environment.yaml  # AD + EC2 for WINDOWS S3 AP testing
├── shared/                 # Shared Python modules (imported by all patterns)
│   ├── s3ap_helper.py      # S3 Access Point helper (core abstraction)
│   ├── ontap_client.py     # ONTAP REST API client (SVM scope)
│   ├── ontap_metrics.py    # ONTAP metrics collector (Cluster scope, for operations/)
│   ├── fsx_helper.py       # AWS FSx API helper
│   ├── demo_data_loader.py # DemoMode mock data loader (for operations/)
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
│   │   ├── ops_events.py   # OPS pattern TypedDicts (VolumeSpaceMetric, etc.)
│   │   └── fpolicy-event-schema.json
│   ├── fpolicy/            # FPolicy protobuf/XML parsers
│   ├── fpolicy-server/     # FPolicy TCP server (ECS Fargate)
│   ├── cfn/                # Shared CloudFormation snippets
│   ├── lambdas/            # Shared Lambda functions
│   └── tests/              # Shared module tests
├── test-data/              # Sample data per UC (gitignore override)
├── scripts/                # Automation scripts
│   └── demo-ad-join-svm.sh  # Join SVM to AD domain (WINDOWS S3 AP enablement)
├── docs/                   # Documentation and guides (40+ docs)
│   ├── en/                 # English docs (deployment-guide.md, etc.)
│   └── ja/                 # Japanese docs (deployment-guide.md, etc.)
├── cfn-params/             # Sample CloudFormation parameter files (*.example.json)
├── params/                 # Additional parameter files (infrastructure templates)
├── security/               # cfn-guard rules
├── Makefile                # Developer workflow commands
├── renovate.json           # Automated dependency updates (requires Renovate GitHub App)
└── .github/workflows/      # CI/CD (lint → test → security → deploy)
```

## Architecture Patterns

- **Trigger**: EventBridge Scheduler (polling) OR FPolicy EventBridge Rule (event-driven)
- **Orchestration**: Step Functions state machine per UC
- **Compute**: Lambda functions (Python 3.12, ARM64, 256-1024MB)
- **Storage access**: FSx for ONTAP S3 Access Points (read/write via S3ApHelper)
- **AI/ML**: Bedrock (Nova/Claude), Textract, Comprehend, Rekognition, SageMaker
- **Analytics**: Athena + Glue Data Catalog
- **Secrets**: Secrets Manager for ONTAP credentials
- **Networking**: VPC-internal (ONTAP API) + VPC-external (S3 AP Internet Origin)
- **TriggerMode**: POLLING / EVENT_DRIVEN / HYBRID (per-UC parameter)
- **DemoMode**: `true` allows running without FSx for ONTAP (regular S3 bucket)

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
# Root conftest.py adds project root to sys.path automatically.
# Pattern tests only need to add their local functions dir:
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "functions" / "discovery"))
```

```bash
# Run from repo root (PYTHONPATH auto-resolved via root conftest.py)
python3 -m pytest solutions/sap/erp-adjacent/tests/ -v
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
- [ ] DemoMode=true execution succeeds (no FSx for ONTAP dependency)
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
- `OutputDestination=FSXN_S3AP` — write back to FSx for ONTAP via S3 AP (NFS/SMB users see results)

### Human Review Pattern

```python
from shared.human_review import evaluate_confidence
decision = evaluate_confidence(confidence=0.72)
# decision.action: "AUTO_APPROVE" | "HUMAN_REVIEW" | "REJECT"
```

## Documentation Design Principles

All README and documentation files follow these UX principles:

### Hub & Spoke Model
- **README.md is the hub**: It links OUT to everything, never contains full details inline
- **docs/ files are spokes**: Each answers ONE specific question in depth
- **Maximum visible content in README**: ~150 lines (before `<details>` expansion)

### Progressive Disclosure
- Use `<details><summary>` for everything not immediately needed on first read
- First-time visitors need: (1) What is this? (2) How do I start? (3) Where are details?
- Returning visitors need: (1) What changed? (2) Where's the specific doc?

### Action-First Headings
- ✅ "はじめる" / "Get Started" — action verb
- ❌ "Prerequisites" / "前提条件" — static noun (move to deployment guide)
- The first visible section should be a "Get Started" table with time estimates

### 7±2 Rule
- No more than 7 items visible at any single navigation level
- If a table has >7 rows, collapse it into `<details>`
- If a section has >7 bullet points, restructure into a table or sub-sections

### Multi-Language Consistency
- All language README files (JA, EN, KO, ZH-CN, ZH-TW, FR, DE, ES) use IDENTICAL structure
- Translate: headings, descriptions, table content
- Never translate: file paths, commands, badge URLs, anchor IDs
- Language switcher at BOTH top and bottom of README

### No Dead Weight
- Phase-based development history → belongs in CHANGELOG.md or blog articles, NOT README
- Verification screenshots → belong in docs/verification-results*.md
- Full deploy commands → belong in docs/guides/deployment-guide.md
- API compatibility tables → belong in docs/s3ap-compatibility-notes.md
- If content will never be updated again, it should not be in README

### Mobile & Scanning Readability
- Tables with >5 columns are unreadable on mobile → split or use key-value format
- Code blocks should be copy-pasteable without horizontal scrolling
- Use emoji as visual markers for quick scanning (📂, 🚀, ⚠️, 📚, 🔧)

### Cross-Repository Consistency
- All Yoshiki0705 repos should follow this same README structure
- Same language switcher format, same badge style, same `<details>` patterns
- Related repositories link to each other in a consistent "Related Repositories" section

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
| `from functions.xxx import` collision in batch test runs | Run patterns with `handler` module imports in separate pytest invocations (Makefile splits these) |
| `SsmAssociations` + `aws:domainJoin` → schema error | Use separate `AWS::SSM::Association` resource with `AWS-JoinDirectoryServiceDomain` document (see below) |
| IVS Auto-Record to FSx for ONTAP S3 AP → `Recording Start Failure` | IVS does not support S3 AP as recording destination (confirmed by AWS service team). Use IVS → standard S3 bucket → FSx for ONTAP path |
| WINDOWS S3 AP `AccessDenied` on data-plane | `WindowsUser.Name` must be username only (`Admin`), NOT `DOMAIN\Admin` — domain prefix silently breaks data-plane |
| WINDOWS S3 AP creation fails | SVM must be AD-joined first; use `scripts/demo-ad-join-svm.sh` |
| AD-joined SVM + S3 AP data ops → `AccessDenied` | AD DC must be reachable for all data operations (ListObjectsV2/GetObject/PutObject). ONTAP performs `unix→win` reverse name-mapping on every data op. HeadBucket succeeds (false positive) — always verify with a data operation |
| HeadBucket success but data operations fail on S3 AP | HeadBucket is metadata-only (S3 layer). If AD DC is unreachable, data ops fail at the file-system layer. Check CIFS domain discovery: `GET /api/protocols/cifs/domains?svm.name=<svm>&fields=discovered_servers` |
| AD-joined SVM + S3 AP data ops → AD DC unreachable | AccessDenied on ListObjectsV2 (HeadBucket OK = false positive). Pre-flight check: `GET /api/protocols/cifs/domains?svm.name=<svm>&fields=discovered_servers` — if `discovered_servers == []`, AD DC is unreachable. Use `shared/ad_health_check.py` for programmatic verification |
| CFn deploy with `CAPABILITY_IAM` → InsufficientCapabilitiesException | Use `CAPABILITY_NAMED_IAM` (template creates named IAM roles). `--capabilities CAPABILITY_NAMED_IAM` |
| Volume name `quick-test-data` → BadRequest | Volume names allow only alphanumeric + underscore. Use `quick_test_data` (no hyphens) |
| Existing SVM with stale AD → "SVM is already joined to a domain" | Cannot re-join via FSx API. Either unjoin via ONTAP CLI (`vserver cifs delete`) or create a new SVM with AD config |
| `aws fsx create-and-attach-s3-access-point` positional args fail | Use `--cli-input-json file://create-ap.json`. Positional `--ontap-configuration` parsing is fragile |
| Delete volume while S3 AP attached → BadRequest | Delete S3 AP first (`detach-and-delete-s3-access-point`), wait for deletion, then delete volume |
| Quick S3 Knowledge base not visible in ap-northeast-1 | S3 KB feature only available in us-east-1, us-west-2, ap-southeast-2, eu-west-1. Use Bedrock KB for Tokyo region, or cross-region Quick account |
| Presigned URL `SignatureDoesNotMatch` from Lambda | boto3 defaults to SigV2 for presign. Use `Config(signature_version="s3v4")` explicitly |
| Presigned URL `PermanentRedirect` from Lambda | Global endpoint `s3.amazonaws.com` redirects. Use `endpoint_url=f"https://s3.{region}.amazonaws.com"` |
| Presigned URL `HEAD` returns 403 but `GET` works | Some S3 AP configurations don't support HEAD on presigned URLs. Use GET for verification |
| Bedrock `InvokeModel` with `inputText` → ValidationException | Nova/Claude models require Messages API. Use `bedrock.converse()` (not `invoke_model` with `inputText`). Add `bedrock:Converse` to IAM policy |
| AgentCore Gateway us-east-1 only assumption | **ap-northeast-1 で利用可能（検証済み 2026-07）**。Workshop が us-east-1 を使うのは簡便性のため。Gateway + Lambda + S3 AP を同一リージョンに配置すること |
| AgentCore Lambda event format: `event.toolName` で取得 | ❌ 正しくは `context.client_context.custom['bedrockAgentCoreToolName']`。event はフラットなパラメータ辞書。ツール名は `targetName___toolName` 形式 |
| AgentCore Gateway + Quick Desktop: Remote MCP 追加が永続化されない | **Import 方式**（JSON ファイルからの読み込み）を使う。Local/Remote 直接追加は Quick Desktop v0.1000.1495 で不安定 |
| Quick Web コンソール MCP コネクタ Step 2 エラー | Previous で Step 1 に戻ると OAuth フィールドがクリアされる。一度で全フィールド入力を完了すること。再現しない場合もある（間欠的） |
| AgentCore Gateway CUSTOM_JWT + Quick Desktop → 403 | NONE auth を PoC に使用。CUSTOM_JWT は認可ポリシー設定が必要（未解決、`docs/agentcore-mcp-remaining-issues.md` 参照） |
| AgentCore Gateway `create-gateway-target` で Lambda not found | Gateway と Lambda は**同一リージョン**に配置必須。クロスリージョン Lambda 呼び出しは不可 |
| Quick Desktop サインインで「account name is invalid」 | IAM ユーザー名 ≠ QuickSight ユーザー名。`aws quicksight list-users` で確認。Email ベースのサインインが最もシンプル |

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
NOT supported: GetBucketNotificationConfiguration.
Presigned URLs: Listed as "Not supported" in AWS docs, but observed working (client-side SigV4 calculation → standard GetObject). AWS Support advises against production reliance. See docs/s3ap-compatibility-notes.md for details.

### NetworkOrigin (Immutable After Creation)

- `Internet`: Accessible from anywhere with valid credentials. NOT via S3 Gateway VPC Endpoint.
- `VPC`: Accessible only from bound VPC via S3 Gateway/Interface Endpoint.

### AD-Joined SVM: AD DC Reachability Required for Data Operations

On AD-joined SVMs (CIFS enabled), **every S3 AP data operation** (ListObjectsV2, GetObject, PutObject) requires the SVM to successfully contact its AD domain controllers. ONTAP's multiprotocol identity pipeline performs a `unix→win` reverse lookup for every file system operation when CIFS is enabled — even on UNIX security style volumes accessed via S3 AP.

**Diagnostic pattern**:
| Test | AD DC Reachable | AD DC Unreachable |
|------|:---:|:---:|
| HeadBucket | ✅ | ✅ (false positive) |
| ListObjectsV2 | ✅ | ❌ AccessDenied |
| GetObject | ✅ | ❌ AccessDenied |
| PutObject | ✅ | ❌ AccessDenied |

**Pre-flight check** (recommended for Step Functions workflows on AD-joined SVMs):
```python
# 1. Check if SVM has CIFS enabled (= AD-joined)
cifs = ontap_request("GET", f"/protocols/cifs/services?svm.name={svm}&fields=ad_domain.fqdn")
if cifs["records"]:
    # 2. Verify DC discovery
    domains = ontap_request("GET", f"/protocols/cifs/domains?svm.name={svm}&fields=discovered_servers")
    if not domains["records"] or domains["records"][0].get("discovered_servers") == []:
        raise RuntimeError("AD DC unreachable — S3 AP data operations will fail with AccessDenied")
```

**Why this is confusing**: HeadBucket succeeds because it only validates at the S3 metadata layer. All IAM, AP policy, and network checks also pass. This leads developers to investigate the wrong layers. The root cause is at the ONTAP file-system layer (reverse name-mapping requires AD DC LDAP/Kerberos connectivity).

**When this happens**:
- AD (Managed AD or self-managed) is deleted, stopped, or network-unreachable
- SVM DNS IPs point to old/dead AD DC addresses after AD recreation
- Security Group or NACL blocks AD ports (53/88/389/445/636) from SVM ENIs to DC IPs

> **Note**: This pattern was verified in `fsxn-observability-integrations` (restore-verification workflow). The patterns in this repo work without AD because they typically target pure UNIX SVMs (no CIFS enabled).

## SSM Domain Join — Correct Pattern for Windows EC2 AD Join

```yaml
# ❌ FAILS: EC2 SsmAssociations + aws:domainJoin (any schemaVersion)
# Error: "Document schema version, 2.2, is not supported by association
#         that is created with instance id"
WindowsInstance:
  SsmAssociations:
    - DocumentName: !Ref MyCustomDoc  # ← NEVER do this for AD join

# ✅ CORRECT: Separate AWS::SSM::Association resource
DomainJoinAssociation:
  Type: AWS::SSM::Association
  Properties:
    Name: AWS-JoinDirectoryServiceDomain  # AWS-managed document
    Targets:
      - Key: InstanceIds
        Values:
          - !Ref WindowsInstance
    Parameters:
      directoryId:
        - !Ref ManagedAd
      directoryName:
        - !Ref DomainName
      dnsIpAddresses:
        - !Select [0, !GetAtt ManagedAd.DnsIpAddresses]
        - !Select [1, !GetAtt ManagedAd.DnsIpAddresses]
```

EC2 IAM role requires: `AmazonSSMManagedInstanceCore` + `AmazonSSMDirectoryServiceAccess`.

## WINDOWS User Type S3 Access Point — AD Requirements

- SVM must be AD-joined before creating WINDOWS-type S3 AP (fails immediately if not)
- `WindowsUser.Name` = username only (`Admin`), NEVER `DOMAIN\Admin`
- Domain prefix is accepted at API level but causes `AccessDenied` on data-plane (ListObjects/GetObject/PutObject)
- Infrastructure template: `infrastructure/demo-ad-environment.yaml` (3 AD modes)
- Join script: `scripts/demo-ad-join-svm.sh` (auto-resolves from CFn stack outputs)
- Parameter file: `params/demo-ad-environment.example.json`

## CDK / IaC Quality Gates

This project implements a 6-layer defense architecture for infrastructure code quality:

| Layer | Tool | Purpose |
|:---:|------|---------|
| 1 | cfn-lint | Template syntax validation |
| 2 | cdk-nag (AwsSolutionsChecks) | AWS compliance checks |
| 3 | gitleaks + zizmor | Secrets + Actions security |
| 4 | IAM Access Analyzer | Over-permissive policy detection |
| 5 | CDK harness tests (17 assertions) | Structural regression prevention |
| 6 | floci integration tests (9 tests) | S3 AP runtime behavior |

**Key rules for AI agents writing CDK/SAM code:**
- `resources: ["*"]` MUST have `// Restrict to ... in production` comment
- cdk-nag suppressions MUST include `reason` explaining why it's acceptable
- Lambda env vars for external infra MUST use `process.env.VAR || ""` (DemoMode compatible)
- AppSync Data Sources MUST be in the same stack as the API (cross-stack = deploy failure)
- All Lambda functions: Python 3.12, ARM64, explicit timeout, description field
- No `@aws-cdk/*-alpha` modules — use L1 + escape hatches instead

**Validation commands:**
```bash
# amplify-portal CDK checks
cd solutions/amplify-portal
npx tsc --noEmit            # Type check
npx vitest run              # CDK harness + component tests
npm run build               # Vite production build

# SAM template checks
cfn-lint solutions/industry/*/template.yaml
python scripts/validate-iam-policies.py solutions/industry/*/template.yaml

# Integration tests (requires floci running)
docker run -d -p 4566:4566 floci/floci:latest
python -m pytest shared/tests/integration/ -v
```

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

## Dependency Updates

| Tool | File | Purpose |
|------|------|---------|
| Renovate | `renovate.json` | Automated dependency updates (GitHub Actions, `requirements*.txt`/`pyproject.toml`, Dockerfiles). Major bumps require Dependency Dashboard approval. |

Renovate keeps SHA-pinned Actions pinned (`helpers:pinGitHubActionDigests` + `pinDigests: true` on the `github-actions` packageRule), so it does not conflict with the zizmor/gitleaks/scorecard SHA-pinning policy above. **Requires enabling the [Renovate GitHub App](https://github.com/apps/renovate) on this repository** — the config file alone does not activate it.

## Cost Awareness

### High-Cost Resources (monitor actively)

| Resource | Monthly Cost | Notes |
|----------|-------------|-------|
| FSx for ONTAP (128 MBps) | ~$194 | Core infrastructure, always running |
| NAT Gateway | ~$32 each | Needed for VPC Lambda → Internet |
| Interface VPC Endpoints | ~$7.20 each | ECR, Logs, STS, SQS, SecretsManager |
| ECS Fargate (FPolicy) | ~$35 | Set desiredCount=0 when not testing |
| Transfer Family | ~$82 | Delete when not needed |

### Cost Optimization Patterns

- Use `EnableVpcEndpoints=false` for PoC (saves ~$43/month)
- Use `DemoMode=true` to test without FSx for ONTAP
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
| [Demo Mode Guide](docs/demo-mode-guide.md) | Run without FSx for ONTAP |
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
| [S3 Bucket User Guide](docs/s3-bucket-user-guide.md) | Standard S3 vs FSx for ONTAP S3 AP differences |
| [Bedrock Inference Profiles](docs/bedrock-inference-profiles.md) | Nova/Claude on-demand requirement, IAM (foundation-model + inference-profile), data residency, CI enforcement |
| [AD-Joined SVM S3 AP Prerequisites](docs/en/ad-joined-svm-s3ap-prerequisites.md) | AD DC reachability, Internet-origin AP + VPC-external Lambda, same-account policy |
| [File Portal UI Options](docs/file-portal-amplify-gen2.md) | Amplify Gen2 / Nextcloud / Custom Build comparison, selection guide, implementation roadmap |
| [SaaS Gap Analysis (JA)](docs/aws-feature-requests/file-portal-service-gap.md) | 15 SaaS 比較, AI エージェント動向, プロトコルアクセシビリティ, ペルソナレビュー |
| [SaaS Gap Analysis (EN)](docs/aws-feature-requests/file-portal-service-gap.en.md) | English version of gap matrix + feature requests |
| [Nextcloud External Storage Setup](docs/nextcloud-external-storage-s3ap.md) | Nextcloud + FSx for ONTAP S3 AP step-by-step configuration |
| [Workshop EDA Integration Guide](docs/workshop-eda-integration.md) | AWS Workshop modules mapped to UC patterns (EDA scenarios, Athena, Glue, AgentCore, Quick) |
| [Quick Desktop MCP Setup](docs/quick-desktop-mcp-setup.md) | AgentCore MCP Gateway + Quick Desktop E2E setup (Import method, IaC, lessons learned) |
| [AgentCore MCP Demo Guide](docs/demo-agentcore-mcp-quick-desktop.md) | E2E demo with screenshots: list_files, read_file, search_files results |
| [AgentCore MCP Remaining Issues](docs/agentcore-mcp-remaining-issues.md) | Known issues tracker: Web UI bug, Desktop persistence, CUSTOM_JWT 403 |
| [AgentCore MCP Tools Reference](docs/agentcore-mcp-tools.md) | Lambda tool definitions (list/read/search), input/output schemas, IAM policy |

## Agent Output Standards

> ユーザーレベル Kiro グローバル steering のミラー。steering 未ロードの環境でも従えるようにする。

> CI: `.github/workflows/agent-output-audit.yml`（命名/中立性/リーク/parity）と `gitleaks.yml`（シークレット）。

### Naming (NetApp / AWS)

- 初出は **Amazon FSx for NetApp ONTAP**、以降 **FSx for ONTAP**。`FSxN` / 単独 `FSx` / `FSx ONTAP` は不可。アクセスポイントは **FSx for ONTAP S3 AP**。
- NetApp Workload Factory / NetApp Console / BlueXP は提案しない。native 等価物（CloudWatch, ONTAP REST API, FabricPool, AWS DataSync, Snapshot/FlexClone/SnapMirror）に置換。
- 例外: 外部引用タイトルの逐語引用（その行に `allow:naming` コメントを付与）。

### Vendor neutrality (right-tool-for-the-job)

- ベンダー対決/優劣表現は禁止（"best", "beats X", "X より優れている", "競合ツール", "優位性", "game-changer"）。選択肢として提示し、推奨案自身の制約も含めてトレードオフを対称に記載。

### Public-output safety

- 個人名/ペルソナ名・メール・AWS アカウントID・内部IP/ホスト名・サポートケース番号・ベンダー内部チケットID をコミットしない。role ベース表記（"Storage Specialist lens"）と "an internal product request (tracked)" を使う。
- プロセスメタデータのノイズ禁止（"Persona Review Summary"・レビューラウンド・日付・レンズ数）。レビュー知見は inline の role-based lens note（`> **Topic** (Role lens): ...`）として織り込み、provenance は `.private/`（gitignore）へ。

### Bilingual docs (JA primary + EN)

- JA/EN parity を維持（セクション構成/数の一致、inline note の対応）。片方を変更したら同じ変更で両方に反映。

### Technical reference / guide docs

- 必須要素: エグゼクティブサマリの結論、FAQ/よくある誤解、選択フローチャート（mermaid 可）、OT/IT セキュリティ考慮（該当時）、段階的導入ステップ、Related Documents（逆リンク）、≥10 の inline role-based lens レビュー。

### Before committing docs

```bash
gitleaks detect --config .gitleaks.toml --no-git --source .
# CI が agent-output チェックをミラー: .github/workflows/agent-output-audit.yml
```
