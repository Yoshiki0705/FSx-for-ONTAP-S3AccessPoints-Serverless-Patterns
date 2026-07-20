# IaC ガバナンスパターン — AI 時代のガードレール設計

> CDK Conference Japan 2026 Keynote「IaC in the Agentic World」(Momo Kornher, CDK Team) + 関連セッションの知見を反映。

## 1. IaC as AI Guardrail パターン

### コンセプト

AI エージェント（Kiro, DevOps Agent, GitHub Copilot 等）がインフラコードを生成する時代において、IaC は「AI が何を作っても検証される安全網」として機能する。

```
AI Agent が CDK/SAM コードを生成
    │
    ▼
cdk synth (CloudFormation テンプレート生成)
    │
    ├── cdk-nag: AwsSolutionsChecks (コンプライアンス)
    ├── cfn-lint: テンプレート構文検証
    ├── cfn-guard: カスタムルール (security/ 配下)
    ├── IAM Access Analyzer: ポリシー過剰検知
    └── CDK ハーネステスト: 構造アサーション
    │
    ▼
すべて通過 → デプロイ許可
いずれか失敗 → PR ブロック
```

### このプロジェクトでの実装状況

| ガードレール | ツール | 状態 |
|------------|-------|:---:|
| テンプレート構文 | cfn-lint | ✅ CI 統合済み |
| セキュリティルール | cfn-guard (security/) | ✅ CI 統合済み |
| AWS ベストプラクティス | cdk-nag (AwsSolutionsChecks) | ✅ backend.ts に適用 |
| IAM 権限検証 | Access Analyzer ValidatePolicy | ✅ CI workflow 追加済み |
| 構造リグレッション | CDK ハーネステスト (17 tests) | ✅ vitest 統合済み |
| シークレットリーク | gitleaks | ✅ pre-commit hook |
| GitHub Actions セキュリティ | zizmor | ✅ pre-commit hook |
| 依存関係更新 | Renovate | ✅ 自動 PR |
| Python コード品質 | ruff | ✅ CI 統合済み |

### AI エージェントに対するガードレールの意味

1. **AI が Lambda を追加** → CDK ハーネステストが Lambda 数をチェック（意図しない追加を検知）
2. **AI が IAM wildcard を使用** → cdk-nag が AwsSolutions-IAM5 を発火 + validate-iam-policies.py が警告
3. **AI が古いランタイムを指定** → cdk-nag が AwsSolutions-L1 を発火
4. **AI がシークレットをハードコード** → gitleaks が pre-commit でブロック
5. **AI が Amplify Gen2 のパターンを間違える** → amplify-gen2-cdk-patterns.md で学習ソースを提供

### 設計原則

- **Deny by default**: cdk-nag の suppression は明示的な理由付きでのみ許可
- **Document exceptions**: wildcard リソースには必ず `// Restrict to ... in production` コメント
- **Track drift**: suppressions の数が増えたら CDK ハーネステストで上限チェック（現在 ≤15）
- **AI にコンテキストを渡す**: AGENTS.md と steering files で「何が許可され何が禁止か」を明示

---

## 2. Alpha モジュール利用方針

### 判断基準

CDK Conference セッション「Alphaモジュール使っていいのかい！？」(watany) の知見:

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
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
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

- CDK Conference Japan 2026 Keynote: "IaC in the Agentic World" (Momo Kornher)
- CDK Conference Japan 2026: "Alphaモジュール使っていいのかい" (watany)
- CDK Conference Japan 2026: "ドリフトを絶対に許さないCDK運用" (アキキー)
- [Firefly.ai: AI Won't Kill IaC — It Will Make It Non-Negotiable](https://www.firefly.ai/blog/2026-predictions-ai-wont-kill-iac-it-will-make-it-non-negotiable)
