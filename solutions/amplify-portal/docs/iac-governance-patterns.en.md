# IaC Governance Patterns — Guardrail Design for the AI Era

🌐 **Language / 言語**: [日本語](iac-governance-patterns.md) | English

> Reflects takeaways from the CDK Conference Japan 2026 keynote "IaC in the Agentic World" (CDK team) and related sessions.

## 1. IaC as AI Guardrail pattern

### Concept

In an era where AI agents (Kiro, DevOps Agent, GitHub Copilot and others) generate infrastructure code, IaC acts as a safety net that validates whatever the AI produces.

```
An AI agent generates CDK/SAM code
    │
    ▼
A PR is opened
    │
    ├── cfn-lint: template syntax validation        ── PR gate
    ├── cfn-guard: custom rules (under security/)   ── PR gate
    ├── IAM Access Analyzer: over-permissive policy ── PR gate
    ├── CDK harness tests: structural assertions    ── PR gate
    ├── ruff / pytest / vitest                      ── PR gate
    └── cdk-nag: AwsSolutionsChecks                 ── manual (see below)
    │
    ▼
All PR gates pass → mergeable
Any failure → merge blocked
```

> **cdk-nag is a PR gate as of 2026-08-28.** CI's Stage 2b synthesises and compares against `security/cdk-nag-baseline.txt`, failing on a finding that is not recorded. It stays off in the deployment path, for the reason below. This section previously said it was not a gate. Its application in `backend.ts` is opt-in and only takes effect with `CDK_NAG=1` (`const enableNag = process.env.CDK_NAG === "1"`), and no workflow under `.github/workflows/` sets that variable. It is therefore a manual check.
>
> ```bash
> npm run nag   # synthesises the backend; deploys nothing
> ```
>
> The reason it is opt-in is an Amplify Gen2 constraint. Applying cdk-nag as an always-on Aspect produces `[AssemblyError]` from findings on Amplify-managed resources the consumer cannot configure (Cognito, AppSync, internal S3 buckets, DynamoDB), which stops the deployment itself. See "cdk-nag Design Decision" in AGENTS.md.

#### Three things measured while getting cdk-nag to run at all (2026-08-27)

**The command this section used to give never ran cdk-nag.** It was `CDK_NAG=1 npx ampx generate outputs`, which reads the outputs of an already-deployed stack and does not synthesise the backend. It reported nothing, and reported nothing whether or not there were findings. `ampx` has no synth-only command and the AWS CDK CLI is not a dependency here, so `scripts/cdk-nag.sh` executes `amplify/backend.ts` as the CDK app it is — CDK synthesises on exit when `CDK_OUTDIR` is set, and `CDK_CONTEXT_JSON` supplies the three context keys Amplify reads for its backend identity.

**A coarse acknowledgment suppresses nothing.** cdk-nag reports each finding under a granular name — `AwsSolutions-IAM5[Resource::arn:aws:s3:*:*:accesspoint/*]` — and `Validations.of(stack).acknowledge({ id: "AwsSolutions-IAM5" })` matches none of them. Measured: acknowledging the coarse id left all 18 findings on the auth roles in place. The acknowledgments listed at the end of `backend.ts` are coarse, which is why findings remain in the data stack despite being described there as accepted. Acknowledging the granular ids for the access-point wildcards dropped the auth-stack count from 18 to 6.

**`Validations.acknowledge` rejects an id containing more than one `::`.** It splits on that delimiter to separate an optional prefix. A granular id carries one inside `[Resource::…]`, so it is accepted — unless the ARN contributes another, which `arn:aws:s3:::bucket/*` does. Those findings cannot be expressed through this API at all; the six that remain above are a DemoMode bucket ARN in the local configuration, and the shipped example leaves those lines commented out.

#### Why a baseline

Three of the 108 were fixed rather than recorded: point-in-time recovery on the two tables holding authored content, and a TLS-only policy on the alarm topic. The remaining 121 need either a decision that cannot be validated without deploying, or a change to a resource Amplify owns.

**They are not all Amplify's.** 58 are Lambda roles we declare in `backend.ts` — the `AWSLambdaBasicExecutionRole` managed policy, and resource wildcards covering ARNs that only resolve at deploy time. Narrowing each needs a per-endpoint review that has not been done. The baseline is per finding, so **an unrecorded one fails and a recorded one that gets fixed also fails**; it cannot become a one-way allowlist.

A baselined finding is not a fixed finding. `REASONS` in `scripts/check_cdk_nag_baseline.py` carries the reason for each category.

### Implementation status in this project

| Guardrail | Tool | Status |
|------------|-------|:---:|
| Template syntax | cfn-lint | ✅ Integrated in CI |
| Security rules | cfn-guard (security/) | ✅ Integrated in CI |
| AWS best practices | cdk-nag (AwsSolutionsChecks) | ✅ Compared against the baseline in CI (121 recorded) |
| IAM permission validation | Access Analyzer ValidatePolicy | ✅ CI workflow added |
| Structural regression | CDK harness tests (114 tests) | ✅ Integrated with vitest |
| Secret leakage | gitleaks | ✅ pre-commit hook |
| GitHub Actions security | zizmor | ✅ pre-commit hook |
| Dependency updates | Renovate | ✅ Automated PRs |
| Python code quality | ruff | ✅ Integrated in CI |

### What these guardrails mean for an AI agent

1. **AI adds a Lambda function** → CDK harness tests check the Lambda count (detects unintended additions)
2. **AI uses an IAM wildcard** → `validate-iam-policies.py` warns in CI (cdk-nag's AwsSolutions-IAM5 only fires with `CDK_NAG=1`)
3. **AI specifies an outdated runtime** → cdk-nag raises AwsSolutions-L1 (also opt-in; not detected automatically in CI)
4. **AI hardcodes a secret** → gitleaks blocks it at pre-commit
5. **AI gets an Amplify Gen2 pattern wrong** → `amplify-gen2-cdk-patterns.md` provides the learning source

### Design principles

- **Deny by default**: cdk-nag suppressions are permitted only with an explicit stated reason
- **Document exceptions**: wildcard resources always carry a `// Restrict to ... in production` comment
- **Track drift**: a ceiling is enforced on IAM wildcard resource declarations (`expect(cdkWildcards.length).toBeLessThanOrEqual(15)` in `backend-assertions.test.ts`). **That is a cap on wildcards, not a cap on suppressions.** Nothing currently limits the number of suppressions
- **Give the AI context**: `AGENTS.md` and the steering files state explicitly what is allowed and what is forbidden

> **On acknowledgment coverage**: resources inside Amplify Gen2 nested stacks cannot be reliably suppressed, which is also the direct reason cdk-nag cannot be always-on. So it is not the case that every finding is resolved by a reasoned acknowledgment. Findings in our own code are resolved; findings on Amplify-managed resources cannot be fully suppressed. cdk-nag v3 removed `NagSuppressions` in favour of `Validations.of(scope).acknowledge(...)`. That propagation to constructs beneath the scope is verified on an ordinary stack (`tests/infrastructure/cdk-nag-v3.test.ts`); **it is not verified against Amplify's nested stacks**.

---

## 2. Policy on using alpha modules

### Decision criteria

Takeaways from the CDK Conference session "Is it OK to use alpha modules?!":

| Decision axis | Acceptable | Better avoided |
|--------|:---:|:---:|
| Production stability | Stable (L2) | Experimental (L1.5) |
| API change frequency | Once a month or less | Weekly breaking changes |
| Availability of alternatives | Alpha is the only option | L1 + escape hatch works instead |
| Fit with Renovate | semver compliant | 0.x with unannounced breaking changes |

### This project's policy

| Module | Version | Policy |
|-----------|----------|------|
| `aws-cdk-lib` | stable (v2.x) | ✅ Auto-updated by Renovate, verified by the CDK harness |
| `@aws-amplify/backend` | stable | ✅ The official Amplify Gen2 package |
| `cdk-nag` | stable | ✅ Maintained by cdklabs, widely adopted |
| `@aws-cdk/aws-*-alpha` | experimental | ❌ Not used. Substituted with L1 + custom resource |

### Alpha dependencies inside Amplify Gen2

Amplify Gen2 may use experimental CDK constructs internally (AppSync L2 and similar). These are managed by the Amplify team, so consumers do not need to be aware of them. That said:

- `npx ampx sandbox` output may include `[WARNING] Using experimental construct`
- An internal breaking change may occur when Amplify Gen2 is upgraded
- → Detected automatically by Renovate PRs plus the CDK harness tests

---

## 3. How drift detection works

### The problem

When a sandbox environment is changed by hand (editing a Lambda environment variable from the Console, adding an IAM policy and so on), "drift" occurs outside CDK's control. The next `cdk deploy` either overwrites the drift or hits a conflict.

### Detection approaches

| Method | Cost | Accuracy | Automation |
|------|:---:|:---:|:---:|
| CloudFormation drift detection API | $0 | High | ✅ Can run on a schedule |
| `cdk diff` (synth vs deployed) | $0 | Medium | ✅ Can run in CI |
| AWS Config (resource change recording) | ~$2/month | High | ✅ Notifies on rule violation |

### Recommendation: run `cdk diff` periodically

```yaml
# .github/workflows/drift-check.yml (weekly)
name: Drift Detection
on:
  schedule:
    - cron: "0 9 * * 1"  # Mondays at 09:00 UTC
  workflow_dispatch:

jobs:
  check-drift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-node@v7
      - run: npm install
        working-directory: solutions/amplify-portal
      - name: Check for drift
        working-directory: solutions/amplify-portal
        run: |
          npx ampx sandbox --identifier main --diff-only 2>&1 | tee drift-report.txt
          if grep -q "There are differences" drift-report.txt; then
            echo "::warning::Drift detected in Amplify sandbox"
          fi
```

### Current position

- **Sandbox environments**: treated as disposable, so drift is tolerated (recreate with `sandbox delete`)
- **Production environments**: run CloudFormation drift detection monthly (built into the Amplify Hosting pipeline)
- **Implementation timing**: when production deployment begins

---

## Summary: defence-in-depth architecture

```
Layer 1: AI Context (AGENTS.md, steering files)
    → The material the AI learns the correct patterns from

Layer 2: Static Analysis (cdk-nag, cfn-lint, cfn-guard, ruff)
    → Detects violations at synth time

Layer 3: Policy Validation (IAM Access Analyzer)
    → Detects over-granted permissions

Layer 4: Structural Assertions (CDK harness tests)
    → Detects regressions in resource counts and settings

Layer 5: Integration Tests (floci, moto)
    → Verifies runtime behaviour

Layer 6: Drift Detection (cdk diff, CloudFormation)
    → Detects divergence after deployment
```

Why IaC grows more important in an era where AI writes the code: **the easier it becomes to write code, the more important it becomes to validate the code that was written**.

## References

- CDK Conference Japan 2026 keynote: "IaC in the Agentic World"
- CDK Conference Japan 2026: "Is it OK to use alpha modules?"
- CDK Conference Japan 2026: "CDK operations that never tolerate drift"
- [Firefly.ai: AI Won't Kill IaC — It Will Make It Non-Negotiable](https://www.firefly.ai/blog/2026-predictions-ai-wont-kill-iac-it-will-make-it-non-negotiable)
