# Contributing / コントリビューションガイド

本プロジェクトへの貢献を歓迎します。以下のガイドラインに従ってください。

## Issue の報告

- バグ報告: 再現手順、期待される動作、実際の動作を記載してください
- 機能リクエスト: ユースケースと期待される動作を記載してください
- 質問: Discussions タブを使用してください

## Pull Request

### 前提条件

- Python 3.13+
- AWS CLI v2
- ruff（リンター）
- cfn-lint（CloudFormation テンプレート検証）
- SAM CLI v1.93.0+（ローカルテスト用、オプション）
- Docker or Finch（ローカルテスト用、オプション）

### 開発フロー

```bash
# 1. リポジトリをフォーク & クローン
git clone https://github.com/<your-username>/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns.git
cd FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns

# 2. 依存関係のインストール
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 3. ブランチを作成
git checkout -b feature/your-feature-name

# 4. コードを変更

# 5. テストを実行
pytest shared/tests/ -v

# 6. リンターを実行
ruff check .
ruff format --check .

# 7. CloudFormation テンプレートを検証
cfn-lint */template.yaml

# 8. コミット & プッシュ
git add .
git commit -m "feat: your feature description"
git push origin feature/your-feature-name
```

### コーディング規約

- **Python**: ruff のデフォルト設定に従う
- **CloudFormation**: cfn-lint でエラーなし
- **命名規則**: 
  - Python: snake_case（変数、関数）、PascalCase（クラス）
  - CloudFormation: PascalCase（リソース論理名、パラメータ）
- **ドキュメント**: 日本語（README、コメント）、英語（コード内の識別子）
- **テスト**: 新機能には pytest テストを追加

### コミットメッセージ

[Conventional Commits](https://www.conventionalcommits.org/) に従ってください:

- `feat:` 新機能
- `fix:` バグ修正
- `docs:` ドキュメントのみの変更
- `test:` テストの追加・修正
- `refactor:` リファクタリング
- `chore:` ビルドプロセスやツールの変更

### PR チェックリスト

- [ ] テストが全て通る (`pytest shared/tests/ -v`)
- [ ] リンターエラーなし (`ruff check .`)
- [ ] CloudFormation テンプレートが有効 (`cfn-lint */template-deploy.yaml`)
- [ ] 機密情報（アカウント ID、IP アドレス等）が含まれていない
- [ ] 必要に応じてドキュメントを更新
- [ ] 新しいパラメータを追加した場合、全 UC の README（8 言語）に反映

## 新しいユースケースの追加

新しい業界別パターンを追加する場合:

1. `<uc-name>/` ディレクトリを作成
2. `shared/` の共通モジュールを活用
3. `template.yaml` で CloudFormation テンプレートを定義
4. `README.md` に概要、アーキテクチャ、デプロイ手順を記載
5. `tests/` にユニットテストを追加
6. トップレベル README.md のユースケース一覧に追加

## セキュリティ

セキュリティに関する問題を発見した場合は、Issue ではなく直接メンテナーに連絡してください。

## CI/CD パイプライン要件

### ローカルテスト実行

PR を作成する前に、以下のテストをローカルで実行してください:

```bash
# 1. ユニットテスト + プロパティベーステスト（カバレッジ 80% 以上）
pytest shared/tests/ use-cases/*/tests/ --cov=shared --cov-report=term-missing --cov-fail-under=80 -v

# 2. 特定のテストファイルのみ実行
pytest shared/tests/test_routing.py -v
pytest shared/tests/test_cost_validation.py -v

# 3. プロパティベーステストのみ（Hypothesis）
pytest shared/tests/ -k "property" -v

# 4. 全テスト実行（Phase 1–5）
pytest shared/tests/ use-cases/*/tests/ security/tests/ -v
```

### テンプレートバリデーション

```bash
# cfn-lint: CloudFormation テンプレートの構文・ベストプラクティスチェック
pip install cfn-lint
cfn-lint use-cases/*/template.yaml use-cases/*/template-deploy.yaml
cfn-lint shared/cfn/*.yaml

# cfn-guard: セキュリティコンプライアンスチェック
# インストール: https://github.com/aws-cloudformation/cloudformation-guard
cfn-guard validate \
  --data use-cases/*/template-deploy.yaml \
  --rules security/cfn-guard-rules/

# 個別ルールの実行
cfn-guard validate \
  --data use-cases/uc09-autonomous-driving/template-deploy.yaml \
  --rules security/cfn-guard-rules/iam-least-privilege.guard
```

### セキュリティスキャン

```bash
# Bandit: Python コードのセキュリティスキャン
pip install bandit
bandit -r shared/ use-cases/ -c .bandit --severity-level medium

# pip-audit: 依存関係の脆弱性チェック
pip install pip-audit
pip-audit -r requirements.txt
pip-audit -r requirements-dev.txt

# ruff: リンター + フォーマッター
ruff check .
ruff format --check .
```

### CI パイプラインのステージ

GitHub Actions CI パイプライン（`.github/workflows/ci.yml`）は以下の 4 ステージで構成されます:

| ステージ | ツール | 失敗条件 |
|---------|--------|---------|
| Stage 1 | cfn-lint | テンプレートエラー |
| Stage 2 | pytest + Hypothesis | テスト失敗 or カバレッジ < 80% |
| Stage 3 | cfn-guard | セキュリティルール違反 |
| Stage 4 | Bandit + pip-audit | High/Critical findings |

**全ステージがパスしない限り、PR はマージできません。**

### デプロイワークフロー

本番デプロイ（`.github/workflows/deploy.yml`）は以下のフローで実行されます:

1. **Staging デプロイ**: main ブランチへの push で自動実行
2. **スモークテスト**: Step Functions テストデータ実行
3. **Manual Approval**: GitHub Environment Protection Rules（最低 1 名承認）
4. **Production デプロイ**: 承認後に実行

### ブランチ戦略

```
feature/* → PR → main (staging auto-deploy) → manual promotion → production
```

- `feature/*` ブランチで開発
- PR 作成時に CI パイプラインが自動実行
- main マージ後に staging 自動デプロイ
- staging 検証後に手動承認で production デプロイ

## ライセンス

本プロジェクトに貢献することで、あなたの貢献が MIT License の下でライセンスされることに同意したものとみなされます。
