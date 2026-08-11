# ポータル CDK / 品質ゲートの罠

> このファイルはリポジトリに含まれる（GitHub から読める）。ローカルの Kiro では
> `.kiro/steering/portal-cdk-quality-gates.md` が読み込み条件だけを持ち、
> 該当する作業をしているときにこの内容へ誘導する。`.kiro/` は公開しないため、
> 知識の本体は常にこちら側に置く。

| Pitfall | Solution |
|---------|----------|
| ポータルの Lambda が `shared/` を import できない | `functions/<name>/` の asset にはそのディレクトリしか入らない。`shared.*` を使う関数には `amplify/backend.ts` の `SharedPythonLayer` を `layers:` で付与する。レイヤーは `/opt` にマウントされ Python が見るのは `/opt/python` なので、アーカイブに `python/` プレフィックスが必要（`Code.fromAsset` の `bundling.local` で再配置している） |
| `shared/` を変更しても sandbox のレイヤーが更新されない | `ampx sandbox` は hotswap で Lambda を更新し、LayerVersion の内容変更をスキップする（hotswap 無効化フラグは存在しない）。テンプレート側に変更がある場合のみ CloudFormation が走る。確実に反映するには `ampx sandbox delete` → 再デプロイ、またはパイプラインデプロイ |
| 例外メッセージからエラー原因を推測する実装 | `str(IndexError(4))` は `"4"` で HTTP 404 に見える。実際に `Path(__file__).parents[4]`（Lambda では親が 3 つ）の IndexError を「CIFS 未設定」と誤報告していた。`type(e).__name__` を含めて報告し、文字列パターンで原因を決めない |

## CDK / IaC Quality Gates

This project implements a 6-layer defense architecture for infrastructure code quality:

| Layer | Tool | Purpose |
|:---:|------|---------|
| 1 | cfn-lint | Template syntax validation |
| 2 | cdk-nag (AwsSolutionsChecks) | AWS compliance checks (**manual opt-in, not a PR gate**, see below) |
| 3 | gitleaks + zizmor | Secrets + Actions security |
| 4 | IAM Access Analyzer | Over-permissive policy detection |
| 5 | CDK harness tests (46 assertions) | Structural regression prevention |
| 6 | floci integration tests (9 tests) | S3 AP runtime behavior |

### cdk-nag Design Decision (Amplify Gen2 Constraint)

**Problem**: registering cdk-nag during synth makes any reported violation interrupt synthesis and block deployment (v2 raised `[AssemblyError] Found errors`; v3 raises `ValidationFailed`). Amplify Gen2 creates resources (AppSync, Cognito, internal S3 buckets, DynamoDB) that produce Non-Compliant findings (ASC3, S1, S10, COG1, COG7, COG8, IAM4, IAM5) which are **NOT user-configurable** — Amplify controls their creation and does not expose configuration hooks for these properties.

**Solution**: cdk-nag is **opt-in via the `CDK_NAG=1` environment variable**, run by hand:

```
┌─────────────────────────────────────────────────────────────┐
│ Deployment Flow (sandbox & production)                       │
│ npx ampx sandbox / amplify deploy                           │
│ → synth → deploy (NO cdk-nag → no blocking)                │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Manual run (local, needs Amplify credentials)                │
│ CDK_NAG=1 npx ampx generate outputs                        │
│ → synth WITH cdk-nag → NagReport CSVs                      │
└─────────────────────────────────────────────────────────────┘
```

**`CDK_NAG=1` is not run by any workflow.** It appears in no file under
`.github/workflows/`, so nothing about it blocks a pull request. It used to be
described here as "CI-only", which reads as a gate. Verify before relying on it:

```bash
grep -rn CDK_NAG .github/workflows/    # no output means no gate
```

It is not wired up because `ampx generate outputs` needs credentials for a real
Amplify app, which the PR workflows do not have. What *is* gated on every PR is
`tests/infrastructure/`, including `cdk-nag-v3.test.ts` — that runs the real
`AwsSolutionsChecks` pack over real constructs offline, so the API wiring and the
acknowledgment mechanism are checked even though the portal's own synth is not.

**What this means for new code:**
- Adding a Lambda with `resources: ["*"]` → cdk-nag reports it on a manual run → acknowledge with a reason
- The harness assertion capping wildcard count (`backend-assertions.test.ts`) is the part that runs on a PR
- Amplify-managed resources (Cognito, AppSync, internal buckets) → acknowledged, documented, unchangeable

**Acknowledgments location**: `amplify/backend.ts` bottom section, via
`Validations.of(dataStack).acknowledge(...)`. cdk-nag v3 removed `NagSuppressions`, and
there is no `applyToNestedStacks` or `applyToChildren` flag — scope is the whole
mechanism, and acknowledging on a stack covers the constructs beneath it.

**Why NOT always-on nag:**
1. Amplify Gen2 nested stack resources cannot be reliably acknowledged
2. Amplify updates may introduce new internal resources with new findings, breaking unrelated deploys
3. Synthesis is interrupted by any reported violation — there is no "warning-only" mode

**Key rules for AI agents writing CDK/SAM code:**
- `resources: ["*"]` MUST have `// Restrict to ... in production` comment
- cdk-nag acknowledgments MUST include `reason` explaining why it's acceptable
- Lambda env vars for external infra MUST use `config.<property>` from `portal-config.ts` (not bare `process.env`)
- AppSync Data Sources MUST be in the same stack as the API (cross-stack = deploy failure)
- All Lambda functions: Python 3.13, ARM64, explicit timeout, description field
- No `@aws-cdk/*-alpha` modules — use L1 + escape hatches instead

**Validation commands:**
```bash
# amplify-portal CDK checks
cd solutions/amplify-portal
npx tsc --noEmit            # Type check
npx vitest run              # CDK harness + component tests
npm run build               # Vite production build

# cdk-nag (CI or manual validation — does NOT block deploy)
CDK_NAG=1 npx ampx generate outputs 2>&1 | grep -i "error\|non-compliant"

# SAM template checks
cfn-lint solutions/industry/*/template.yaml
python scripts/validate-iam-policies.py solutions/industry/*/template.yaml

# Integration tests (requires floci running)
docker run -d -p 4566:4566 floci/floci:latest
python -m pytest shared/tests/integration/ -v
```
