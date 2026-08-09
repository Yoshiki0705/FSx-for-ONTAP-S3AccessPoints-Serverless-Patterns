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
| 2 | cdk-nag (AwsSolutionsChecks) | AWS compliance checks (**CI-only**, see below) |
| 3 | gitleaks + zizmor | Secrets + Actions security |
| 4 | IAM Access Analyzer | Over-permissive policy detection |
| 5 | CDK harness tests (38 assertions) | Structural regression prevention |
| 6 | floci integration tests (9 tests) | S3 AP runtime behavior |

### cdk-nag Design Decision (Amplify Gen2 Constraint)

**Problem**: cdk-nag applied as a CDK `Aspect` during synth causes `[AssemblyError] Found errors` and blocks deployment. Amplify Gen2 creates resources (AppSync, Cognito, internal S3 buckets, DynamoDB) that produce Non-Compliant findings (ASC3, S1, S10, COG1, COG7, COG8, IAM4, IAM5) which are **NOT user-configurable** — Amplify controls their creation and does not expose configuration hooks for these properties.

**Solution**: cdk-nag is **opt-in via `CDK_NAG=1` environment variable** and executed only in CI:

```
┌─────────────────────────────────────────────────────────────┐
│ Deployment Flow (sandbox & production)                       │
│ npx ampx sandbox / amplify deploy                           │
│ → synth → deploy (NO cdk-nag → no blocking)                │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ CI Quality Gate (PR checks)                                  │
│ CDK_NAG=1 npx ampx generate outputs                        │
│ → synth WITH cdk-nag → NagReport CSVs                      │
│ → suppressions resolve all custom-code findings             │
│ → Amplify-managed findings suppressed with documented reason│
│ → PR blocked if NEW un-suppressed findings appear           │
└─────────────────────────────────────────────────────────────┘
```

**What this means for new code:**
- Adding a Lambda with `resources: ["*"]` → cdk-nag will catch it in CI → add suppression with reason
- Adding a new IAM policy → CI validates least-privilege compliance
- Amplify-managed resources (Cognito, AppSync, internal buckets) → suppressed, documented, unchangeable

**Suppressions location**: `amplify/backend.ts` bottom section, with `applyToNestedStacks: true`.

**Why NOT always-on nag:**
1. `addStackSuppressions` cannot reliably suppress Amplify Gen2 nested stack resources
2. Amplify updates may introduce new internal resources with new findings, breaking unrelated deploys
3. The `[AssemblyError]` mechanism has no "warning-only" mode — it's all-or-nothing

**Key rules for AI agents writing CDK/SAM code:**
- `resources: ["*"]` MUST have `// Restrict to ... in production` comment
- cdk-nag suppressions MUST include `reason` explaining why it's acceptable
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
