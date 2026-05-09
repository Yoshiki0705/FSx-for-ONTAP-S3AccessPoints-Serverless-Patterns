# UC16: 政府機関 — 公文書デジタルアーカイブ・FOIA 対応

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
      → OCR: Textract による文書デジタル化
      → Classification: Comprehend による文書分類（機密レベル判定）
      → EntityExtraction: PII 検出（氏名、住所、SSN、電話番号）
      → Redaction: 機密情報の自動墨消し（リダクション）
      → IndexGeneration: 全文検索インデックス生成
      → ComplianceCheck: 保存期間・廃棄スケジュール確認
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
| Amazon Textract | 文書 OCR（手書き含む） |
| Amazon Comprehend | エンティティ抽出、文書分類、PII 検出 |
| Amazon Bedrock | 文書要約、FOIA 回答ドラフト生成 |
| Amazon Macie | 機密データ自動検出 |
| DynamoDB | 文書メタデータ、処理状態管理 |
| OpenSearch Serverless | 全文検索インデックス |
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

## デプロイ

```bash
aws cloudformation deploy \
  --template-file government-archives/template-deploy.yaml \
  --stack-name fsxn-gov-archives \
  --parameter-overrides \
    S3AccessPointAlias=<alias> \
    OntapSecretName=<secret> \
    OntapManagementIp=<ip> \
  --capabilities CAPABILITY_NAMED_IAM
```

## ディレクトリ構成

```
government-archives/
├── template.yaml              # SAM テンプレート（開発用）
├── template-deploy.yaml       # CloudFormation テンプレート（デプロイ用）
├── functions/
│   ├── discovery/handler.py   # 新規文書検出
│   ├── ocr/handler.py         # Textract OCR
│   ├── classification/handler.py    # 文書分類・機密レベル判定
│   ├── entity_extraction/handler.py # PII 検出
│   ├── redaction/handler.py         # 自動墨消し
│   ├── index_generation/handler.py  # 全文検索インデックス生成
│   └── compliance_check/handler.py  # 保存期間・廃棄確認
├── tests/
│   └── test_discovery.py
└── README.md
```
