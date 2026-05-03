# Contributing / コントリビューションガイド

本プロジェクトへの貢献を歓迎します。以下のガイドラインに従ってください。

## Issue の報告

- バグ報告: 再現手順、期待される動作、実際の動作を記載してください
- 機能リクエスト: ユースケースと期待される動作を記載してください
- 質問: Discussions タブを使用してください

## Pull Request

### 前提条件

- Python 3.12+
- AWS CLI v2
- ruff（リンター）
- cfn-lint（CloudFormation テンプレート検証）

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
- [ ] CloudFormation テンプレートが有効 (`cfn-lint */template.yaml`)
- [ ] 機密情報（アカウント ID、IP アドレス等）が含まれていない
- [ ] 必要に応じてドキュメントを更新

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

## ライセンス

本プロジェクトに貢献することで、あなたの貢献が MIT License の下でライセンスされることに同意したものとみなされます。
