# UC16 デモスクリプト（30 分枠）

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

> Hinweis: Diese Übersetzung ist ein automatisch generierter Entwurf basierend auf dem japanischen Original. Beiträge zur Verbesserung der Übersetzungsqualität sind willkommen.

## 前提

- AWS アカウント、ap-northeast-1
- FSx for NetApp ONTAP + S3 Access Point
- `government-archives/template-deploy.yaml` をデプロイ（`OpenSearchMode=none` でコスト抑制）

## タイムライン

### 0:00 - 0:05 イントロ（5 分）

- ユースケース: 自治体・行政の公文書管理デジタル化
- FOIA / 情報公開請求の法定期限（20 営業日）の負荷
- 課題: PII 検出・墨消しは手動で数時間かかる

### 0:05 - 0:10 アーキテクチャ（5 分）

- Textract + Comprehend + Bedrock の組み合わせ
- OpenSearch の 3 モード（none / serverless / managed）
- NARA GRS 保存期間の自動管理

### 0:10 - 0:15 デプロイ（5 分）

```bash
aws cloudformation deploy \
  --template-file government-archives/template-deploy.yaml \
  --stack-name fsxn-uc16-demo \
  --parameter-overrides \
    DeployBucket=<your-deploy-bucket> \
    S3AccessPointAlias=<your-ap-ext-s3alias> \
    VpcId=<vpc-id> \
    PrivateSubnetIds=<subnet-ids> \
    NotificationEmail=ops@example.com \
    OpenSearchMode=none \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

### 0:15 - 0:22 処理実行（7 分）

```bash
# サンプル PDF（機密情報含む）アップロード
aws s3 cp sample-foia-request.pdf \
  s3://<s3-ap-arn>/archives/2026/05/req-001.pdf

# Step Functions 実行
aws stepfunctions start-execution \
  --state-machine-arn <uc16-StateMachineArn> \
  --input '{"opensearch_enabled": "none"}'
```

結果を確認:
- `s3://<output-bucket>/ocr-results/archives/2026/05/req-001.pdf.txt`（生テキスト）
- `s3://<output-bucket>/classifications/archives/2026/05/req-001.pdf.json`（分類結果）
- `s3://<output-bucket>/pii-entities/archives/2026/05/req-001.pdf.json`（PII 検出）
- `s3://<output-bucket>/redacted/archives/2026/05/req-001.pdf.txt`（墨消し版）
- `s3://<output-bucket>/redaction-metadata/archives/2026/05/req-001.pdf.json`（sidecar）

### 0:22 - 0:27 FOIA 期限トラッキング（5 分）

```bash
# FOIA 請求登録
aws dynamodb put-item \
  --table-name <fsxn-uc16-demo>-foia-requests \
  --item '{
    "request_id": {"S": "REQ-001"},
    "status": {"S": "PENDING"},
    "deadline": {"S": "2026-05-25"},
    "requester": {"S": "jane@example.com"}
  }'

# FOIA Deadline Lambda 手動実行
aws lambda invoke \
  --function-name <fsxn-uc16-demo>-foia-deadline \
  --payload '{}' \
  response.json && cat response.json
```

SNS 通知メールを確認。

### 0:27 - 0:30 Wrap-up（3 分）

- OpenSearch 有効化（`serverless` で本格検索）のパス
- GovCloud 移行（FedRAMP High 要件）
- 次ステップ: Bedrock エージェントで対話型 FOIA 回答生成

## よくある質問と回答

**Q. 日本の情報公開法（30 日）に対応可能？**  
A. `REMINDER_DAYS_BEFORE` と 20 営業日のハードコードを修正すれば対応可（US 連邦祝日→日本の祝日へ）。

**Q. 原文 PII はどこに保存される？**  
A. どこにも保存しません。`pii-entities/*.json` は SHA-256 hash のみ、`redaction-metadata/*.json` も hash + offset のみ。復元は原文から再実行が必要。

**Q. OpenSearch Serverless のコスト削減方法？**  
A. 最低 2 OCU = 月 $350 ほど。本番以外は停止推奨。