# デモモード ガイド — FSx ONTAP なしでパターンを体験する

🌐 **Language / 言語**: [日本語](demo-mode-guide.md) | [English](demo-mode-guide.en.md)

## 概要

本リポジトリのパターンは FSx for ONTAP S3 Access Points を前提としていますが、
**デモモード**を使用すると FSx ONTAP 環境なしでワークフロー全体を体験できます。

デモモードでは:
- 通常の S3 バケットを S3 AP の代わりに使用
- テストデータを S3 バケットに自動配置
- Discovery → Processing → Report の全フローが動作
- ONTAP REST API 呼び出しはスキップ（ACL 収集等）

## 仕組み

S3ApHelper クラスは内部的に boto3 の `Bucket` パラメータに値を渡すだけです。
S3 Access Point Alias も通常の S3 バケット名も、boto3 は同じ S3 API で処理します。

```python
# S3 AP 経由（本番）
helper = S3ApHelper("vol-name-xxxxx-ext-s3alias")

# 通常 S3 バケット経由（デモモード）
helper = S3ApHelper("my-demo-bucket-12345")
```

## クイックスタート（5 分）

### Step 1: デモ用 S3 バケットを作成

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
DEMO_BUCKET="fsxn-s3ap-demo-${ACCOUNT_ID}"

aws s3 mb s3://${DEMO_BUCKET} --region ap-northeast-1
```

### Step 2: テストデータを配置

```bash
# UC1 (legal-compliance) の場合
aws s3 cp test-data/legal-compliance/ s3://${DEMO_BUCKET}/legal-docs/ --recursive

# UC6 (semiconductor-eda) の場合
aws s3 cp test-data/semiconductor-eda/ s3://${DEMO_BUCKET}/eda-designs/ --recursive

# SAP の場合
aws s3 cp test-data/sap-erp-adjacent/ s3://${DEMO_BUCKET}/idoc-export/ --recursive
```

### Step 3: デモモードでデプロイ

```bash
cd legal-compliance/

sam build && sam deploy --guided \
  --parameter-overrides \
    S3AccessPointAlias=${DEMO_BUCKET} \
    DemoMode=true \
    NotificationEmail=your-email@example.com \
    BedrockModelId=amazon.nova-lite-v1:0
```

`DemoMode=true` を指定すると:
- `S3AccessPointAlias` の AllowedPattern バリデーションが緩和される
- ONTAP REST API 関連パラメータ（OntapSecretName, OntapManagementIp 等）が不要になる
- VPC 関連パラメータ（VpcId, PrivateSubnetIds 等）が不要になる
- ACL 収集 Lambda はモックデータを返す

### Step 4: ワークフロー実行

```bash
# Step Functions を手動実行
aws stepfunctions start-execution \
  --state-machine-arn <STATE_MACHINE_ARN> \
  --input '{}'
```

### Step 5: 結果確認

```bash
# 出力バケットの結果を確認
aws s3 ls s3://${DEMO_BUCKET}/reports/ --recursive
```

## デモモード対応パターン

| パターン | DemoMode 対応 | 備考 |
|---------|:---:|------|
| UC1 legal-compliance | ✅ | ACL 収集はモックデータ |
| SAP sap-erp-adjacent | ✅ | ONTAP 不要（S3 AP のみ使用） |
| FC3 genai-rag-enterprise-files | ✅ | ACL 収集はモックデータ |
| その他の UC | 🔄 | 順次対応予定 |

## 制約事項

デモモードでは以下の機能が制限されます:

| 機能 | 本番モード | デモモード |
|------|-----------|-----------|
| S3 AP 経由のファイル読み取り | ✅ FSx ONTAP ボリューム | ✅ 通常 S3 バケット |
| ONTAP REST API (ACL 収集) | ✅ 実データ | ⚠️ モックデータ |
| VPC 内実行 | ✅ | ❌ VPC 外実行 |
| NTFS ACL 解析 | ✅ | ❌ サンプル ACL |
| FPolicy イベント駆動 | ✅ | ❌ ポーリングのみ |

## 本番移行

デモモードで動作確認後、本番環境に移行する手順:

1. FSx for ONTAP ファイルシステムを作成
2. S3 Access Point を設定
3. `DemoMode=false` に変更し、本番パラメータを設定
4. `sam deploy` で再デプロイ

### DemoMode → Production の差分

| 領域 | DemoMode（評価用） | Production（FSx ONTAP） |
|------|-------------------|------------------------|
| 入力ソース | 通常 S3 バケット | FSx ONTAP S3 Access Point |
| 権限モデル | S3 IAM のみ | IAM + S3 AP ポリシー + ONTAP ファイル ID |
| ネットワーク | パブリック AWS サービスパス | Internet-origin or VPC-origin 設計判断（**作成後変更不可 — AP 再作成が必要**） |
| データ | サンプル / 合成データ | 顧客管理 NAS データ |
| ガバナンス | デモラベルのみ | データ分類 + リネージ + 保持ポリシー |
| コスト | ~$0.10/実行 | + FSx ONTAP インフラ (~$194/月 基本) |
| AI 評価 | テストデータでの動作確認 | ドメインバリデーションセットでの精度評価 |

> **Governance Caveat**: デモモードは技術検証用です。本番環境では必ず FSx ONTAP S3 Access Points を使用し、適切な IAM ポリシー、ネットワーク設計、データ分類、人間レビュー閾値を定義してください。各国・地域の規制要件への適合は顧客の責任で検証する必要があります。
