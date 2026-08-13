# CI/CD パイプラインガイド

FSx for ONTAP S3 Access Points Serverless Patterns プロジェクトの CI/CD パイプライン設計・運用ガイド。

## パイプラインアーキテクチャ概要

**CI のみで、このリポジトリは CI から AWS へデプロイしない。** 理由は
「[デプロイは CI で行わない](#デプロイは-ci-で行わない)」。

```
┌─────────────────────────────────────────────────────────────┐
│  CI ワークフロー (ci.yml)                                     │
│  トリガー: Pull Request → main                               │
│                                                             │
│  ┌──────┐   ┌──────┐   ┌──────────┐   ┌──────────────┐    │
│  │ Lint │ → │ Test │ → │ Security │ → │ Report/Gate  │    │
│  └──────┘   └──────┘   └──────────┘   └──────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

`.github/workflows/` にはこの他にガードレール用のワークフローが複数ある（命名・中立性・
リーク検査、cfn-guard、IAM ポリシー検証、Bedrock モデルの EOL 検査、Actions の SHA
ピン留め検査など）。いずれも**検査のみで、AWS リソースを変更しない**。

## CI ワークフロー ステージ詳細

### Stage 1: Lint (cfn-lint)

CloudFormation テンプレートの静的解析を実行する。

- **ツール**: cfn-lint
- **対象**: プロジェクト内の全 `*.yaml` テンプレート
- **除外**: `node_modules/` 配下
- **失敗条件**: cfn-lint エラーが 1 件以上

```yaml
- run: pip install cfn-lint
- run: cfn-lint **/*.yaml --ignore-templates '**/node_modules/**'
```

### Stage 2: Test (pytest + Hypothesis)

ユニットテストとプロパティベーステストを実行する。

- **ツール**: pytest + Hypothesis
- **カバレッジ閾値**: 80%（`--cov-fail-under=80`）
- **キャッシュ**: pip + `.hypothesis` ディレクトリ
- **レポート**: XML カバレッジレポート生成

```yaml
- run: pip install -r requirements-dev.txt
- run: pytest --cov=shared --cov-report=xml --cov-fail-under=80
```

### Stage 3: Security (cfn-guard + Bandit + pip-audit)

セキュリティコンプライアンスチェックを実行する。

- **cfn-guard**: IAM least-privilege、暗号化必須、パブリックアクセス禁止
- **Bandit**: Python コードのセキュリティ脆弱性スキャン
- **pip-audit**: 依存パッケージの CVE チェック

```yaml
- run: cfn-guard validate -r security/cfn-guard-rules/ -d **/*.yaml
- run: bandit -r shared/ use-cases/ scripts/ -ll -c .bandit
- run: pip-audit -r requirements.txt
```

### Stage 4: Report / Gate

全ステージの結果を集約し、最終判定を行う。

- **ゲーティングルール**: いずれかのステージが失敗した場合、PR マージをブロック
- **アーティファクト**: カバレッジレポートを PR にアップロード
- **通知**: 失敗時に PR コメントで詳細を報告

## デプロイは CI で行わない

このリポジトリは 52 個の独立したパターンを収めた参照実装ライブラリで、稼働中のサービス
ではない。デプロイは**利用者が自分のアカウントで、必要なパターンだけを選んで行う**もので、
main への push で自動的に行うものではない。したがって staging / production への自動
デプロイワークフローは持たない。

### 撤去の経緯（2026-08-13）

以前は `deploy.yml` があり、`main` への push で変更された `.yaml` を検出して
staging へデプロイ → スモークテスト → production へデプロイする構成だった。
**これは一度も動作したことがなかった。**

- `role-to-assume` は `arn:aws:iam::${{ vars.AWS_ACCOUNT_ID }}:role/...` を組み立てて
  いたが、この変数はリポジトリに設定されたことがない。ARN はアカウント ID が空の
  `arn:aws:iam:::role/...` になり、OIDC の AssumeRole は `Request ARN is invalid` で
  12 回リトライして失敗する。
- それでも CI は緑だった。デプロイジョブは「変更された `.yaml` がある」ときだけ走る
  条件付きで、それまでの push はどれもテンプレートを触っていなかったため、
  ジョブは skipped、ワークフロー全体は success と報告されていた。
- テンプレートを 17 本変更した PR が初めてこのジョブを起動し、そこで初めて露見した。
  ロールバック経路（`Rollback Staging`）も同じ理由で未実行のままだった。

**教訓**: ゲートの成功は、ゲートが走った証拠ではない。条件付きで skip されるジョブは、
skip されている限り緑を報告し続ける。新しいデプロイ経路を作るなら、
**通ってはいけない入力で一度落ちること**を確認してから信用する。

### 実際のデプロイ手順

検証済みの手順は [deployment-guide.md](ja/deployment-guide.md)（[EN](en/deployment-guide.md)）
にある。要点のみ:

```bash
cd solutions/industry/<pattern>
cp samconfig.toml.example samconfig.toml   # <PLACEHOLDER> を実値に置換
sam build && sam deploy
```

UC15-UC28 と OPS1-OPS6 の 20 スタックはすべてこの手順で投入し、E2E で結果を確認した。
ロールバックとクリーンアップの手順も deployment-guide 側にある。

### 自分でパイプラインを作る場合

`deployment-guide.md` の「CI/CD 統合」節に、OIDC を使った GitHub Actions の最小例がある。
長期クレデンシャル（Access Key）を置かず、`permissions: id-token: write` と
`aws-actions/configure-aws-credentials` を使う形。IAM ロールには
`iam:CreateRole` / `iam:AttachRolePolicy` を与えず Permission Boundary を設定すること。

## ブランチ戦略

```
feature/xxx ──PR──→ main ──(必要になったら手元から sam deploy)──→ AWS
     │                 │
     │                 └── CI: Lint → Test → Security → Report/Gate
     │
     └── ローカル開発・テスト
```

### フロー

1. **feature ブランチ作成**: `feature/add-serverless-inference`
2. **PR 作成**: `main` ブランチへの Pull Request
3. **CI 自動実行**: Lint → Test → Security → Report
4. **レビュー・マージ**: CI 全パス + レビュー承認後にマージ
5. **マージ後**: 自動デプロイは行わない。必要なパターンを
   [deployment-guide.md](ja/deployment-guide.md) の手順で手元からデプロイする

### ブランチ命名規則

| プレフィックス | 用途 |
|--------------|------|
| `feature/` | 新機能追加 |
| `fix/` | バグ修正 |
| `docs/` | ドキュメント更新 |
| `refactor/` | リファクタリング |
| `test/` | テスト追加・修正 |

## トラブルシューティング

### cfn-lint エラー

**症状**: CI の Lint ステージが失敗

**一般的な原因と対処**:

| エラーコード | 原因 | 対処 |
|------------|------|------|
| E3001 | リソースタイプ不正 | AWS ドキュメントで正しいリソースタイプを確認 |
| E3012 | プロパティ値の型不一致 | パラメータの型（String/Number）を確認 |
| W2001 | 未使用パラメータ | パラメータを使用するか削除 |
| E1001 | YAML 構文エラー | インデント・構文を修正 |

**ローカルでの事前確認**:

```bash
pip install cfn-lint
cfn-lint shared/cfn/*.yaml use-cases/*/template-deploy.yaml
```

### テスト失敗

**症状**: CI の Test ステージが失敗

**対処手順**:

1. ローカルでテスト再現:
   ```bash
   pip install -r requirements-dev.txt
   pytest shared/tests/ -v --tb=long
   ```

2. Hypothesis テスト失敗時:
   - `.hypothesis/examples/` にカウンターエグザンプルが保存される
   - 失敗入力を確認し、ロジックを修正

3. カバレッジ不足時:
   ```bash
   pytest --cov=shared --cov-report=html
   open htmlcov/index.html
   ```

### デプロイに関する症状

CI からデプロイしないので、デプロイ時の症状はこのガイドの対象外。CloudFormation の
タイムアウト、ロールバック手順、スタックの完全削除、S3 AP の `AccessDenied` などは
[deployment-guide.md のトラブルシューティング](ja/deployment-guide.md#トラブルシューティング)
（[EN](en/deployment-guide.md#troubleshooting)）にまとめてある。「実行は成功するのに結果が
空になる」系の症状も同じ場所にある。

## ローカル開発での CI 再現

```bash
# 依存パッケージインストール
pip install -r requirements-dev.txt

# CI と同じチェックを順番に実行
cfn-lint shared/cfn/*.yaml                                          # Lint
pytest --cov=shared --cov-report=term-missing --cov-fail-under=80   # Test
cfn-guard validate -r security/cfn-guard-rules/ -d shared/cfn/*.yaml # Security
bandit -r shared/ -ll -c .bandit                                    # Bandit
pip-audit -r requirements.txt                                       # Audit
```

## 関連ファイル

| ファイル | 説明 |
|---------|------|
| `.github/workflows/ci.yml` | CI ワークフロー定義 |
| `security/cfn-guard-rules/` | cfn-guard セキュリティルール |
| `.bandit` | Bandit 設定ファイル |
| `params/staging.json` | パラメータファイルの雛形（`flexcache/anycast-dr` がコピー元として参照）|
| `params/production.json` | Production 環境パラメータ |
| `requirements-dev.txt` | 開発・テスト依存パッケージ |
| `pytest.ini` | pytest 設定 |
