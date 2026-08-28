# IaC ガバナンスパターン — AI 時代のガードレール設計

🌐 **Language / 言語**: 日本語 | [English](iac-governance-patterns.en.md)

> CDK Conference Japan 2026 Keynote「IaC in the Agentic World」(CDK チーム) + 関連セッションの知見を反映。

## 1. IaC as AI Guardrail パターン

### コンセプト

AI エージェント（Kiro, DevOps Agent, GitHub Copilot 等）がインフラコードを生成する時代において、IaC は「AI が何を作っても検証される安全網」として機能する。

```
AI Agent が CDK/SAM コードを生成
    │
    ▼
PR を開く
    │
    ├── cfn-lint: テンプレート構文検証         ── PR ゲート
    ├── cfn-guard: カスタムルール (security/)  ── PR ゲート
    ├── IAM Access Analyzer: ポリシー過剰検知  ── PR ゲート
    ├── CDK ハーネステスト: 構造アサーション   ── PR ゲート
    ├── ruff / pytest / vitest                 ── PR ゲート
    └── cdk-nag: AwsSolutionsChecks            ── 手動（下記参照）
    │
    ▼
PR ゲートがすべて通過 → マージ可能
いずれか失敗 → マージをブロック
```

> **cdk-nag は現時点で PR ゲートではありません。** `backend.ts` の適用は `CDK_NAG=1` のときだけ有効になる opt-in で（`backend.ts` の `const enableNag = process.env.CDK_NAG === "1"`）、`.github/workflows/` のどのワークフローもこの変数を設定していません。したがって実行は手動です。
>
> ```bash
> npm run nag   # backend を合成する。デプロイはしない
> ```
>
> opt-in にしている理由は Amplify Gen2 の制約です。cdk-nag を Aspect として常時適用すると、利用者が設定できない Amplify 管理リソース（Cognito / AppSync / 内部 S3 バケット / DynamoDB）の findings で `[AssemblyError]` になり、デプロイ自体が止まります。詳細は AGENTS.md の「cdk-nag Design Decision」を参照してください。

#### cdk-nag を走らせるまでに実測した 3 点（2026-08-27）

**この節が以前示していたコマンドは cdk-nag を走らせていませんでした。** `CDK_NAG=1 npx ampx generate outputs` はデプロイ済みスタックの出力を読むだけで、backend を合成しません。findings が有るか無いかに関わらず何も報告しません。`ampx` に合成のみのコマンドは無く、AWS CDK CLI もこのプロジェクトの依存ではないため、`scripts/cdk-nag.sh` は `amplify/backend.ts` を CDK アプリとして直接実行します。`CDK_OUTDIR` が設定されていれば CDK は終了時に合成し、Amplify が backend の識別に読む 3 つの context キーは `CDK_CONTEXT_JSON` で渡せます。

**粒度なしの acknowledge は 1 件も抑制しません。** cdk-nag は各 finding を `AwsSolutions-IAM5[Resource::arn:aws:s3:*:*:accesspoint/*]` のような粒度付きの名前で報告し、`Validations.of(stack).acknowledge({ id: "AwsSolutions-IAM5" })` はそのどれにも一致しません。実測: 粒度なしで acknowledge しても auth ロールの 18 件はすべて残りました。`backend.ts` 末尾に並ぶ acknowledge は粒度なしなので、data スタックの findings は「受容済み」と書かれていながら残っています。アクセスポイントのワイルドカードを粒度付きで acknowledge すると auth スタックは 18 件から 6 件になりました。

**`Validations.acknowledge` は `::` を 2 つ以上含む id を拒否します。** 前置きと規則名を分ける区切りとして `::` で split するためです。粒度付き id は `[Resource::…]` の中に 1 つ持つので通りますが、ARN 側がもう 1 つ持ち込むと通りません（`arn:aws:s3:::bucket/*` が該当）。この形の findings はこの API では表現できません。上に残る 6 件はローカル設定にある DemoMode バケットの ARN で、配布している example ではその行はコメントアウトされています。

### このプロジェクトでの実装状況

| ガードレール | ツール | 状態 |
|------------|-------|:---:|
| テンプレート構文 | cfn-lint | ✅ CI 統合済み |
| セキュリティルール | cfn-guard (security/) | ✅ CI 統合済み |
| AWS ベストプラクティス | cdk-nag (AwsSolutionsChecks) | ⚠️ `CDK_NAG=1` で opt-in（CI 未統合） |
| IAM 権限検証 | Access Analyzer ValidatePolicy | ✅ CI workflow 追加済み |
| 構造リグレッション | CDK ハーネステスト (112 tests) | ✅ vitest 統合済み |
| シークレットリーク | gitleaks | ✅ pre-commit hook |
| GitHub Actions セキュリティ | zizmor | ✅ pre-commit hook |
| 依存関係更新 | Renovate | ✅ 自動 PR |
| Python コード品質 | ruff | ✅ CI 統合済み |

### AI エージェントに対するガードレールの意味

1. **AI が Lambda を追加** → CDK ハーネステストが Lambda 数をチェック（意図しない追加を検知）
2. **AI が IAM wildcard を使用** → `validate-iam-policies.py` が CI で警告（cdk-nag の AwsSolutions-IAM5 は `CDK_NAG=1` を付けたときのみ）
3. **AI が古いランタイムを指定** → cdk-nag が AwsSolutions-L1 を発火（同じく opt-in。CI で自動検知はされない）
4. **AI がシークレットをハードコード** → gitleaks が pre-commit でブロック
5. **AI が Amplify Gen2 のパターンを間違える** → amplify-gen2-cdk-patterns.md で学習ソースを提供

### 設計原則

- **Deny by default**: cdk-nag の suppression は明示的な理由付きでのみ許可
- **Document exceptions**: wildcard リソースには必ず `// Restrict to ... in production` コメント
- **Track drift**: IAM の wildcard リソース宣言数に上限を設ける（`backend-assertions.test.ts` の `expect(cdkWildcards.length).toBeLessThanOrEqual(15)`）。**これは wildcard の数の上限であり、suppression の数の上限ではありません。** suppression 数を制限する仕組みは現時点でありません
- **AI にコンテキストを渡す**: AGENTS.md と steering files で「何が許可され何が禁止か」を明示

> **acknowledgment の網羅性について**: Amplify Gen2 のネストスタック内リソースを確実に抑制できません。これが cdk-nag を常時適用にできない直接の理由でもあります。したがって「全 findings が理由付き acknowledgment で解消されている」とは言えません。自作コード側の findings は解消済み、Amplify 管理リソース側は抑制しきれない、という状態です。cdk-nag v3 で `NagSuppressions` は削除され `Validations.of(scope).acknowledge(...)` になりました。scope 配下へ伝播することは通常のスタックで検証済み（`tests/infrastructure/cdk-nag-v3.test.ts`）ですが、**Amplify のネストスタックに対しては未検証**です。

---

## 2. Alpha モジュール利用方針

### 判断基準

CDK Conference セッション「Alphaモジュール使っていいのかい！？」の知見:

| 判断軸 | 使ってよい | 避けるべき |
|--------|:---:|:---:|
| プロダクション安定性 | Stable (L2) | Experimental (L1.5) |
| API 変更頻度 | 月 1 回以下 | 週次で breaking changes |
| 代替手段の有無 | Alpha が唯一の選択肢 | L1 + escape hatch で代替可 |
| Renovate との相性 | semver 準拠 | 0.x で予告なく breaking |

### このプロジェクトでの方針

| モジュール | バージョン | 方針 |
|-----------|----------|------|
| `aws-cdk-lib` | stable (v2.x) | ✅ Renovate で自動更新、CDK ハーネスで検証 |
| `@aws-amplify/backend` | stable | ✅ Amplify Gen2 の公式パッケージ |
| `cdk-nag` | stable | ✅ cdklabs 管理、広く採用済み |
| `@aws-cdk/aws-*-alpha` | experimental | ❌ 使用しない。L1 + custom resource で代替 |

### Amplify Gen2 内部の Alpha 依存

Amplify Gen2 は内部で experimental な CDK コンストラクトを使用する場合があります（AppSync L2 等）。これは Amplify チームが管理しているため、利用者側で意識する必要はありません。ただし:

- `npx ampx sandbox` の出力で `[WARNING] Using experimental construct` が出る場合がある
- Amplify Gen2 のバージョンアップ時に内部 breaking change が起きる可能性がある
- → Renovate PR + CDK ハーネステストで自動検知

---

## 3. ドリフト検出の仕組み

### 問題

sandbox 環境が手動で変更された場合（Console から Lambda 環境変数を変更、IAM ポリシーを追加等）、CDK の管理下から外れた「ドリフト」が発生する。次の `cdk deploy` でドリフトが上書きされるか、コンフリクトが起きる。

### 検出アプローチ

| 方法 | コスト | 精度 | 自動化 |
|------|:---:|:---:|:---:|
| CloudFormation drift detection API | $0 | 高 | ✅ スケジュール実行可 |
| `cdk diff` (synth vs deployed) | $0 | 中 | ✅ CI で実行可 |
| AWS Config (リソース変更記録) | ~$2/月 | 高 | ✅ ルール違反で通知 |

### 推奨: `cdk diff` を定期実行

```yaml
# .github/workflows/drift-check.yml (週次)
name: Drift Detection
on:
  schedule:
    - cron: "0 9 * * 1"  # 毎週月曜 9:00 UTC
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

### 現時点の判断

- **sandbox 環境**: 使い捨て前提のため、ドリフトは許容（`sandbox delete` で再作成）
- **本番環境**: CloudFormation drift detection を月次で実行（Amplify Hosting パイプラインに組み込み）
- **実装時期**: 本番デプロイ開始時

---

## まとめ: 多層防御アーキテクチャ

```
Layer 1: AI Context (AGENTS.md, steering files)
    → AI が正しいパターンを学習する材料

Layer 2: Static Analysis (cdk-nag, cfn-lint, cfn-guard, ruff)
    → synth 時に違反を検知

Layer 3: Policy Validation (IAM Access Analyzer)
    → 権限の過剰付与を検知

Layer 4: Structural Assertions (CDK harness tests)
    → リソース数・設定のリグレッションを検知

Layer 5: Integration Tests (floci, moto)
    → ランタイム動作を検証

Layer 6: Drift Detection (cdk diff, CloudFormation)
    → デプロイ後の乖離を検知
```

AI がコードを書く時代に IaC が重要性を増す理由: **コードを書くのが簡単になるほど、書かれたコードの検証が重要になる**。

## 参考

- CDK Conference Japan 2026 Keynote: "IaC in the Agentic World" (CDK チーム)
- CDK Conference Japan 2026: "Alphaモジュール使っていいのかい"
- CDK Conference Japan 2026: "ドリフトを絶対に許さないCDK運用"
- [Firefly.ai: AI Won't Kill IaC — It Will Make It Non-Negotiable](https://www.firefly.ai/blog/2026-predictions-ai-wont-kill-iac-it-will-make-it-non-negotiable)
