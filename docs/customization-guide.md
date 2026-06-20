# カスタマイズガイド — パターンを自社ワークロードに適用する

## 概要

各パターンは「そのまま使える」設計ですが、自社のワークロードに合わせて
以下の 3 つのカスタマイズポイントを変更できます。

## カスタマイズポイント 1: ファイルフィルタ条件

### 変更箇所
- `functions/discovery/handler.py` の `SUPPORTED_EXTENSIONS` 定数
- template.yaml の `FilePrefix` パラメータ

### 変更例

```python
# Before: 法務文書のみ
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".pptx"}

# After: CAD ファイルを追加
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".dwg", ".dxf", ".step", ".iges"}
```

### template.yaml での変更

```yaml
Parameters:
  FilePrefix:
    Type: String
    Default: "legal-docs/"  # ← 自社のプレフィックスに変更
```

## カスタマイズポイント 2: AI/ML モデルの変更

### 変更箇所
- template.yaml の `BedrockModelId` パラメータ
- `functions/*/handler.py` のプロンプト文

### モデル選択ガイド

| ユースケース | 推奨モデル | 理由 |
|-------------|-----------|------|
| コスト重視 | amazon.nova-lite-v1:0 | 最安、日本語対応 |
| 品質重視 | anthropic.claude-3-5-sonnet-20241022-v2:0 | 高精度、長文対応 |
| バランス | amazon.nova-pro-v1:0 | コスト/品質のバランス |
| 高速応答 | amazon.nova-micro-v1:0 | 最速、簡易タスク向け |

### プロンプトのカスタマイズ

```python
# functions/report_generation/handler.py
SYSTEM_PROMPT = """
あなたは{業界}の専門家です。
以下のデータを分析し、{出力形式}でレポートを生成してください。
重要な指標: {KPI リスト}
"""
```

## カスタマイズポイント 3: 出力フォーマットの変更

### 変更箇所
- `functions/*/handler.py` の return 文
- Step Functions ASL 定義の ResultPath

### 出力先の変更

```yaml
# template.yaml
Parameters:
  OutputDestination:
    Type: String
    Default: "STANDARD_S3"      # 通常 S3 バケット
    AllowedValues:
      - "STANDARD_S3"           # 新規 S3 バケットに出力
      - "FSXN_S3AP"             # FSx for ONTAP に書き戻し（NFS/SMB ユーザーが閲覧可能）
```

### 出力 JSON の拡張

```python
# 自社固有のフィールドを追加
result = {
    "key": key,
    "status": "completed",
    # ↓ 自社固有フィールド
    "department": os.environ.get("DEPARTMENT", "engineering"),
    "cost_center": os.environ.get("COST_CENTER", "CC-001"),
    "retention_days": int(os.environ.get("RETENTION_DAYS", "90")),
}
```

## 高度なカスタマイズ

### 新しい処理ステップの追加

Step Functions の ASL 定義にステップを追加:

```json
{
  "States": {
    "ExistingStep": { "Next": "NewCustomStep" },
    "NewCustomStep": {
      "Type": "Task",
      "Resource": "${CustomFunctionArn}",
      "Next": "GenerateReport",
      "Retry": [{"ErrorEquals": ["States.TaskFailed"], "MaxAttempts": 2}]
    }
  }
}
```

### shared/ モジュールの拡張

```python
# shared/my_custom_helper.py
from shared.s3ap_helper import S3ApHelper
from shared.observability import EmfMetrics

class MyCustomHelper:
    def __init__(self, s3ap_alias: str):
        self._helper = S3ApHelper(s3ap_alias)
        self._metrics = EmfMetrics(namespace="MyApp")

    def process(self, key: str) -> dict:
        response = self._helper.get_object(key)
        # カスタム処理
        self._metrics.put_metric("CustomProcessed", 1.0, "Count")
        return {"key": key, "status": "completed"}
```

### 新しい UC パターンの作成

既存パターンをテンプレートとして新しい UC を作成:

```bash
# UC1 をベースに新パターンを作成
cp -r legal-compliance/ my-custom-pattern/

# 以下を変更:
# 1. template.yaml の Description, Parameters
# 2. functions/discovery/handler.py の SUPPORTED_EXTENSIONS
# 3. functions/processing/handler.py のプロンプト
# 4. README.md の説明
# 5. tests/ のテストケース
```

## FAQ

**Q: shared/ モジュールを変更したら全パターンに影響しますか？**
A: はい。shared/ は全パターンで共有されています。変更前に `python3 -m pytest */tests/` で全テストを実行してください。

**Q: Bedrock 以外の LLM を使えますか？**
A: はい。`functions/*/handler.py` の Bedrock 呼び出し部分を SageMaker Endpoint や外部 API に置き換えてください。

**Q: Lambda のメモリサイズを変更すべきですか？**
A: ファイルサイズが大きい場合は増やしてください。目安: < 1MB → 256MB、1-10MB → 512MB、10-100MB → 1024MB。

---

> **Governance Caveat**: カスタマイズ時は IAM ポリシーの最小権限原則を維持してください。新しいサービスを追加する場合は、対応する IAM アクションのみを許可してください。
