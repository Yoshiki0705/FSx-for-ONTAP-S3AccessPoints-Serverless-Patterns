# SAP/ERP Adjacent — デモガイド

## デモ概要

SAP IDoc エクスポートファイルを FSx for ONTAP に配置し、S3 Access Point 経由で
自動検出・Bedrock 要約・SNS 通知を実行するデモ。

## 前提条件

- FSx for ONTAP ファイルシステム（S3 Access Point 設定済み）
- SAM CLI インストール済み
- AWS CLI 設定済み（ap-northeast-1）
- SNS サブスクリプション確認済み

## デモ手順

### Step 1: テストデータの配置

NFS/SMB 経由で FSx for ONTAP ボリュームにサンプルファイルを配置:

```bash
# NFS マウント経由
cp test-data/sap-erp-adjacent/sample-idoc-orders.txt /mnt/fsxn/idoc-export/
cp test-data/sap-erp-adjacent/sample-hulft-transfer.csv /mnt/fsxn/idoc-export/
cp test-data/sap-erp-adjacent/sample-edi-x12.edi /mnt/fsxn/idoc-export/
```

### Step 2: ワークフロー手動実行

```bash
aws stepfunctions start-execution \
  --state-machine-arn <STATE_MACHINE_ARN> \
  --input '{}'
```

### Step 3: 実行結果確認

```bash
# Step Functions コンソールで実行状態を確認
aws stepfunctions describe-execution \
  --execution-arn <EXECUTION_ARN>

# 出力バケットの結果確認
aws s3 ls s3://<OUTPUT_BUCKET>/processed/
aws s3 ls s3://<OUTPUT_BUCKET>/reports/
```

### Step 4: レポート確認

```bash
# 最新レポートをダウンロード
aws s3 cp s3://<OUTPUT_BUCKET>/reports/sap-erp-summary-<TIMESTAMP>.json ./report.json
cat report.json | python3 -m json.tool
```

## 期待される出力

### Discovery Lambda 出力
```json
{
  "status": "completed",
  "object_count": 3,
  "objects": [
    {"key": "idoc-export/sample-idoc-orders.txt", "size": 2048, "category": "sap_idoc"},
    {"key": "idoc-export/sample-hulft-transfer.csv", "size": 1024, "category": "hulft_transfer"},
    {"key": "idoc-export/sample-edi-x12.edi", "size": 512, "category": "edi_document"}
  ]
}
```

### Processing Lambda 出力（1 ファイルあたり）
```json
{
  "key": "idoc-export/sample-idoc-orders.txt",
  "status": "completed",
  "category": "sap_idoc",
  "summary": "受注 IDoc (ORDERS05)。取引先: サンプル株式会社...",
  "output_key": "processed/sample-idoc-orders.txt.json"
}
```

### Report Lambda 出力
```json
{
  "status": "completed",
  "report": {
    "total_files": 3,
    "succeeded": 3,
    "failed": 0,
    "success_rate_pct": 100.0,
    "category_breakdown": {"sap_idoc": 1, "hulft_transfer": 1, "edi_document": 1}
  }
}
```

## トラブルシューティング

| 症状 | 原因 | 対処 |
|------|------|------|
| Discovery で 0 files | プレフィックスが不一致 | `FILE_PREFIX` 環境変数を確認 |
| AccessDenied | IAM ポリシーの ARN 形式が不正 | `arn:aws:s3:{region}:{account}:accesspoint/{name}` 形式を使用 |
| Bedrock InvokeModel 失敗 | モデルアクセス未有効化 | Bedrock コンソールでモデルアクセスを有効化 |
| SNS 通知が届かない | サブスクリプション未確認 | SNS コンソールでサブスクリプションを確認 |
| タイムアウト | ファイルサイズが大きい | `MAX_FILES` を減らすか Lambda タイムアウトを延長 |

## 実行時間目安

| ファイル数 | 推定実行時間 |
|-----------|------------|
| 5 files | ~30 秒 |
| 50 files | ~3 分 |
| 100 files | ~6 分 |

> **注記**: 上記は sizing reference であり、service limit ではありません。実際の実行時間は Bedrock レスポンスタイム、ファイルサイズ、ネットワーク条件により異なります。


## スクリーンショット

![Phase 13 — CloudFormation Stacks](../../docs/screenshots/masked/phase13-cloudformation-stacks.png)
![Phase 13 — Lambda Functions](../../docs/screenshots/masked/phase13-lambda-functions.png)
