# UC16: 政府機関 — 公文書デジタルアーカイブ・FOIA 対応

🌐 **Language / 言語**: 日本語 | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)
📚 **ドキュメント**: [アーキテクチャ](docs/uc16-architecture.md) | [デモスクリプト](docs/uc16-demo-script.md) | [トラブルシューティング](../docs/phase7-troubleshooting.md)

## 概要

FSx for NetApp ONTAP S3 Access Points を活用した政府機関の公文書
デジタルアーカイブおよび情報公開請求（FOIA: Freedom of Information Act）
対応の自動化パイプライン。

## ユースケース

政府機関が保有する大量の公文書（PDF、スキャン画像、電子メール）を
自動的にデジタル化・分類・墨消し（リダクション）し、情報公開請求に
迅速に対応する。

### 処理フロー

```
FSx ONTAP (公文書格納 — 部署別 NTFS ACL)
  → S3 Access Point
    → Step Functions ワークフロー
      → Discovery: 新規文書検出（PDF, TIFF, EML, MSG）
      → OCR: Textract による文書デジタル化（ap-northeast-1 未対応のためクロスリージョン）
      → Classification: Comprehend による文書分類（機密レベル判定）
      → EntityExtraction: PII 検出（氏名、住所、SSN、電話番号）
      → Redaction: 機密情報の自動墨消し（リダクション）
      → IndexGeneration: 全文検索インデックス生成（OpenSearch、無効化可能）
      → ComplianceCheck: 保存期間・廃棄スケジュール確認（NARA GRS）
```

### 対象データ

| データ形式 | 説明 | 典型サイズ |
|-----------|------|-----------|
| PDF | 公文書、報告書、契約書 | 100 KB – 50 MB |
| TIFF | スキャン文書 | 1 – 100 MB |
| EML / MSG | 電子メールアーカイブ | 10 KB – 10 MB |
| DOCX / XLSX | Office 文書 | 50 KB – 20 MB |

### AWS サービス

| サービス | 用途 |
|---------|------|
| FSx for NetApp ONTAP | 公文書の永続ストレージ（部署別 NTFS ACL） |
| S3 Access Points | サーバーレスからの文書アクセス |
| Step Functions | ワークフローオーケストレーション |
| Lambda | 文書分類、PII 検出、墨消し処理 |
| Amazon Textract ⚠️ | 文書 OCR（us-east-1 経由クロスリージョン） |
| Amazon Comprehend | エンティティ抽出、文書分類、PII 検出 |
| Amazon Bedrock | 文書要約、FOIA 回答ドラフト生成 |
| Amazon Macie | 機密データ自動検出 |
| DynamoDB | 文書メタデータ、処理状態管理 |
| OpenSearch Serverless | 全文検索インデックス（オプション、デフォルト無効） |
| SNS | FOIA 期限アラート |

### Public Sector 適合性

- **NARA（国立公文書記録管理局）準拠**: 電子記録管理要件対応
- **FOIA 対応**: 20 営業日以内の回答期限を自動追跡
- **FedRAMP High**: AWS GovCloud で準拠
- **Section 508**: アクセシビリティ対応（OCR + 代替テキスト生成）
- **Records Management**: 保存期間・廃棄スケジュールの自動管理

### FOIA 対応フロー

```
FOIA 請求受付
  → 対象文書検索（OpenSearch）
  → 該当文書の機密レベル判定
  → 自動墨消し（PII、国家安全保障情報）
  → レビュー担当者への通知
  → 回答期限トラッキング（20 営業日）
  → 公開文書パッケージ生成
```

## 検証済みの画面（スクリーンショット）

### 1. 公文書の格納（S3 Access Point 経由）

情報公開請求受付後、対象文書が `archives/YYYY/MM/` プレフィックス配下に格納される。

<!-- SCREENSHOT: phase7-uc16-s3-archives-uploaded.png
     内容: S3 AP の archives/ プレフィックスで PDF 文書一覧
     マスク: アカウント ID、S3 AP ARN、文書名 -->
![UC16: 公文書の格納確認](../docs/screenshots/masked/phase7/phase7-uc16-s3-archives-uploaded.png)

### 2. 墨消し済み文書の閲覧

処理完了後の `redacted/` プレフィックスに格納されたテキストで、PII が
`[REDACTED]` マーカーに置換されている。**一般職員が公開前にレビューする画面**。

<!-- SCREENSHOT: phase7-uc16-redacted-text-preview.png
     内容: S3 コンソールでの redacted テキストプレビュー、[REDACTED] マーカー可視
     マスク: アカウント ID、墨消し対象文書名（サンプル名のみ表示） -->
![UC16: 墨消し済み文書プレビュー](../docs/screenshots/masked/phase7/phase7-uc16-redacted-text-preview.png)

### 3. 墨消しメタデータ（sidecar JSON）

監査用の sidecar データ。原文 PII は保存せず SHA-256 ハッシュのみ。
オフセット、エンティティタイプ（NAME / EMAIL / SSN 等）、信頼度が記録される。

<!-- SCREENSHOT: phase7-uc16-redaction-metadata-json.png
     内容: redaction-metadata/*.json の整形ビュー
     マスク: アカウント ID、元文書名 -->
![UC16: 墨消しメタデータ JSON](../docs/screenshots/masked/phase7/phase7-uc16-redaction-metadata-json.png)

### 4. FOIA 期限リマインダー（SNS メール通知）

FOIA 担当者が期限 3 営業日前に受信するリマインダーメール。
期限超過時は severity=HIGH の OVERDUE 通知。

<!-- SCREENSHOT: phase7-uc16-foia-reminder-email.png
     内容: メールクライアントで FOIA_DEADLINE_APPROACHING メールを表示
     マスク: 受信者・送信者メール、request_id（サンプル ID のみ表示） -->
![UC16: FOIA 期限リマインダーメール](../docs/screenshots/masked/phase7/phase7-uc16-foia-reminder-email.png)

### 5. NARA GRS 保存スケジュール（DynamoDB Explorer）

`fsxn-uc16-demo-retention` テーブル。文書ごとに NARA GRS コード
（GRS 2.1 / 2.2 / 1.1）と保存年数（3 / 7 / 30 年）、廃棄予定日が記録される。

<!-- SCREENSHOT: phase7-uc16-dynamodb-retention.png
     内容: DynamoDB Explorer で retention テーブルの項目一覧
     マスク: アカウント ID、document_key（サンプル名のみ） -->
![UC16: 保存スケジュールテーブル](../docs/screenshots/masked/phase7/phase7-uc16-dynamodb-retention.png)

## デプロイ

### 事前検証

```bash
bash scripts/verify_phase7_prerequisites.sh
```

### ワンショットデプロイ

```bash
bash scripts/deploy_phase7.sh government-archives
```

### 手動デプロイ

```bash
aws cloudformation deploy \
  --template-file government-archives/template-deploy.yaml \
  --stack-name fsxn-gov-archives \
  --parameter-overrides \
    S3AccessPointAlias=<alias> \
    S3AccessPointName=<name> \
    OpenSearchMode=none \
    CrossRegion=us-east-1 \
    UseCrossRegion=true \
    OntapSecretName=<secret> \
    OntapManagementIp=<ip> \
  --capabilities CAPABILITY_NAMED_IAM
```

### OpenSearch モード

| モード | 用途 | 月次コスト（試算） |
|--------|------|-------------------|
| `none` | 検証・低コスト運用（デフォルト） | $0 |
| `serverless` | 可変ワークロード、従量課金 | $350 – $700 |
| `managed` | 固定ワークロード、安価 | $35 – $100 |

## ディレクトリ構成

```
government-archives/
├── template.yaml
├── template-deploy.yaml
├── functions/
│   ├── discovery/handler.py
│   ├── ocr/handler.py                # クロスリージョン Textract
│   ├── classification/handler.py
│   ├── entity_extraction/handler.py
│   ├── redaction/handler.py
│   ├── index_generation/handler.py
│   ├── compliance_check/handler.py   # NARA GRS 保存期間
│   └── foia_deadline_reminder/handler.py  # 20 営業日トラッキング
├── tests/                            # 52 pytest (Hypothesis 含む)
└── README.md
```
