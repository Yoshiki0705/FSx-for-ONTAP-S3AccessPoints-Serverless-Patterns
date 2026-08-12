# ポータル CDK / 品質ゲートの罠

> このファイルはリポジトリに含まれる（GitHub から読める）。ローカルの Kiro では
> `.kiro/steering/portal-cdk-quality-gates.md` が読み込み条件だけを持ち、
> 該当する作業をしているときにこの内容へ誘導する。`.kiro/` は公開しないため、
> 知識の本体は常にこちら側に置く。

| Pitfall | Solution |
|---------|----------|
| ポータルの Lambda が `shared/` を import できない | `functions/<name>/` の asset にはそのディレクトリしか入らない。`shared.*` を使う関数には `amplify/backend.ts` の `SharedPythonLayer` を `layers:` で付与する。レイヤーは `/opt` にマウントされ Python が見るのは `/opt/python` なので、アーカイブに `python/` プレフィックスが必要（`Code.fromAsset` の `bundling.local` で再配置している） |
| `shared/` を変更しても sandbox のレイヤーが更新されない | `ampx sandbox` は hotswap で Lambda を更新し、LayerVersion の内容変更をスキップする（無効化フラグは無い）。テンプレートに変更がある場合のみ CFn が走る。下の論理 ID 対策で作成扱いにすれば飛ばされない |
| **`shared/` がずれた sandbox では、無関係な変更のデプロイも失敗する** | hotswap でレイヤーが飛ばされ続けると deployed layer と作業ツリーの `shared/` がずれる。次に**テンプレートに変更がある**デプロイで CFn が走り、置換になって `Replacement type updates not supported on stack with disable-rollback` で拒否され、スタックは `UPDATE_FAILED` で残る。**失敗したのは自分の変更ではない**。下の論理 ID 対策を入れてあればこのずれ自体が起きない |
| **LayerVersion は論理 ID にフィンガープリントを入れて「置換」を避ける** | 内容が変わった LayerVersion は置換になり、`DisableRollback=true` の sandbox では拒否される。論理 ID に含めれば別リソースなので作成 + 削除になり、作成は disable-rollback でも通る。**作成は hotswap で飛ばせない**のでずれも起きず、ARN で一致を確認できる（`SharedPythonLayer4dc7cbd5285c…`）。両レイヤーに適用済み |
| **`ampx` は失敗しても exit 0 を返す。デプロイの判定に使ってはいけない** | 2 例。(a) `UPDATE_FAILED` のまま `--once` を打つと `✔ Deployment completed in 2.574 seconds` と表示して終わるが、スタックは `UPDATE_FAILED` のまま Lambda のコードも古い。(b) `sandbox delete` 直後の再デプロイは削除済みスタックを指すローカルキャッシュのため `StackNotFound` で落ちる。**判定は `describe-stacks` の `StackStatus` と、対象関数の `LastModified`（`get-function-configuration`）で行う。** (b) は `rm -rf solutions/amplify-portal/.amplify/artifacts/cdk.out` で通るので、**削除〜再作成は 3 手順**（`delete` / キャッシュ削除 / `--once`）になる |
| `UPDATE_FAILED` からの復旧 API は両方使えない | `continue-update-rollback` は `cannot be called from stack with UPDATE_FAILED status`、`rollback-stack` は `not supported for stacks that were last updated using EXPRESS deployment mode` を返す。CFn の案内は「last known stable template で UpdateStack」だが `ampx` にその手段はなく、実際の復旧は `sandbox delete` → 再作成のみ。**Cognito ユーザーと DynamoDB が消える**ので、上の行の手順で消える対象を件数付きで先に確定する。**ただし削除の前に、落ちたリソースの論理 ID を変えて置換を回避できないか見る**。`UPDATE_FAILED` からでも作成 + 削除なら通る（実例: 下の対策だけで復旧した） |
| `DisableRollback=true` で `UPDATE_FAILED` のとき、成功したリソースは適用済みで残る | ロールバックが無効なので、置換で落ちたリソース以外の更新は生きている。実例: IAM ポリシーの修正は反映され（`aws iam get-role-policy` で確認）、同じデプロイの LayerVersion だけが失敗した。「デプロイが失敗した」から「何も変わっていない」を導かない。反映されたかは**スタックのステータスではなくリソースを直接見て**判定する |
| **認可規則が参照する Cognito グループが IaC に無い** | `amplify/data/resource.ts` の `allow.groups(["storage-admin"])` は、そのグループが存在しない場合でも synth もデプロイも通る。`defineAuth` に `groups` を書き忘れると、**長く動いている sandbox には手作業で作られたグループが残っているので動き、新規デプロイでは管理セクションが丸ごと消える**。しかも失敗ではなくセクションの非表示として現れるため「まだ実装されていない」ように見える。実例: 再作成した sandbox で「リソース管理」「分析」が消え、`aws cognito-idp list-groups` が空だった。認可で参照する名前は `amplify/auth/resource.ts` の `groups` に必ず宣言する（所属付与は引き続き `admin-add-user-to-group` で個別に行う） |
| 長く動いている sandbox は「手作業で足したもの」を隠し持つ | 上のグループがまさにそれ。**IaC の欠落は、既存環境では症状が出ない**。`ampx sandbox delete` → 再デプロイは、この種の欠落を洗い出す唯一の確実な方法である一方で Cognito ユーザーと DynamoDB を消す。実行前に、消える対象を件数付きで確定し、DynamoDB を `scan` してバックアップし、owner 系フィールドは**新しい sub へ付け替えてから**戻す（旧 sub のまま戻すと owner スコープの認可で誰からも見えなくなる） |
| **`GROUP_PATH_PREFIXES` を「設定した」ことと「効いている」ことは別** | このプレフィックスがマルチテナント境界だが、`functions/list-files` では**フォルダー監視の受信箱にしか適用されていなかった**。`renameFile` / `trashFile` / `restoreFromTrash` / `createUploadLink` と `listFiles` はキーを未検査で受けており、他チームのキーを直接指定すれば操作でき、他チームの prefix への署名付き PUT も発行できた。エンドポイントは認証済みなので、認可が抜けていても誰も気づかない。**キーを取る操作を追加するときは、境界を通る経路に載っているかをテストで固定する**（`functions/list-files/tests/test_write_guardrails.py`）。境界のコードを無効化してテストが落ちることを確認するまで、そのテストは境界を守っていない |
| コピー系の宛先チェックが無いと、データ破壊が「成功」として返る | `copy_object` は宛先の既存オブジェクトを黙って上書きする。`renameFile` は既存キーへの改名で相手を消していた。宛先の存在確認は `head_object` で行い、`overwrite` を明示しない限り拒否する。なお `head_object` は「無い」と「権限が無い」を区別できないが、権限が無ければ続く copy も失敗するので、判定を誤って上書きすることはない |
| **`s3:CopyObject` を IAM ポリシーに書いても何も許可されない** | そんなアクションは存在しない。`copy_object` が要求するのは source の `s3:GetObject` と **`s3:GetObjectTagging`**、destination の `s3:PutObject` と `s3:PutObjectTagging`。実例: ポータルの list-files ロールに `s3:CopyObject` が書かれていて `GetObjectTagging` が無く、**名前の変更とごみ箱からの復元が AccessDenied で常に失敗していた**。同じロールでの**ごみ箱への移動は成功していた**（同一 source・同一バケットでも要求されないケースがある）ため、最初に試した操作が通ってしまい欠陥が残った。copy を含む経路は**往復の両方向**を実際に叩いて確認する |
| 例外メッセージからエラー原因を推測する実装 | `str(IndexError(4))` は `"4"` で HTTP 404 に見える。実際に `Path(__file__).parents[4]`（Lambda では親が 3 つ）の IndexError を「CIFS 未設定」と誤報告していた。`type(e).__name__` を含めて報告し、文字列パターンで原因を決めない |

## CDK / IaC Quality Gates

This project implements a 6-layer defense architecture for infrastructure code quality:

| Layer | Tool | Purpose |
|:---:|------|---------|
| 1 | cfn-lint | Template syntax validation |
| 2 | cdk-nag (AwsSolutionsChecks) | AWS compliance checks (**manual opt-in, not a PR gate**, see below) |
| 3 | gitleaks + zizmor | Secrets + Actions security |
| 4 | IAM Access Analyzer | Over-permissive policy detection |
| 5 | CDK harness tests (47 assertions) | Structural regression prevention |
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
