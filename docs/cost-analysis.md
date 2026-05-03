# コスト構造分析書

## 概要

本ドキュメントは、FSxN S3 Access Points Serverless Patterns リポジトリで使用する全 AWS サービスのコスト構造を分析し、デフォルト有効/オプショナル（opt-in）の判断基準を文書化する。

**対象リージョン**: ap-northeast-1（東京）
**価格基準日**: 2026年1月（AWS 公式料金ページ準拠）

---

## 1. サービス分類

### 1.1 リクエストベース（従量課金）

リクエストが発生しない限りコストが発生しないサービス。デモ/PoC 環境でも安全に有効化できる。

| サービス | 課金単位 | 使用ユースケース |
|---------|---------|----------------|
| AWS Lambda | リクエスト数 + 実行時間 | 全 UC (UC1〜UC5) |
| AWS Step Functions | ステート遷移数 | 全 UC (UC1〜UC5) |
| Amazon S3 API | リクエスト数 + ストレージ | 全 UC (UC1〜UC5) |
| Amazon Textract | ページ数 | UC2（金融・保険） |
| Amazon Comprehend | ユニット数（100文字単位） | UC2（金融・保険）、UC5（医療） |
| Amazon Rekognition | 画像数 | UC3（製造業）、UC4（メディア）、UC5（医療） |
| Amazon Bedrock (Claude/Nova) | トークン数 | UC1（法務）、UC2（金融・保険） |
| Amazon Athena | スキャンデータ量 | UC1（法務）、UC3（製造業） |
| Amazon EventBridge Scheduler | 呼び出し回数（無料枠あり） | 全 UC (UC1〜UC5) |
| Amazon SNS | メッセージ数 | 全 UC (UC1〜UC5) |

### 1.2 常時稼働（固定費）

リソースが存在する限り課金が発生するサービス。デモ/PoC 環境では不要な場合がある。

| サービス | 課金単位 | 月額概算 | 使用ユースケース |
|---------|---------|---------|----------------|
| VPC Endpoints（Interface 型） | 時間課金 ~$0.01/hr/EP | ~$7.20/月/EP | 全 UC（Lambda VPC 内実行時） |
| CloudWatch Alarms | アラーム数 | $0.10/アラーム/月 | 全 UC（オプショナル） |
| CloudWatch Logs | データ取り込み量 | $0.50/GB | 全 UC |
| AWS Glue Data Catalog | オブジェクト数 | 無料（100万オブジェクトまで） | UC1、UC3 |

---

## 2. 月額コスト概算（ap-northeast-1）

### 2.1 インフラ基盤コスト（全ユースケース共通）

#### Interface VPC Endpoints（最大の固定費）

| リソース | タイプ | 月額コスト |
|---------|-------|-----------|
| Secrets Manager Endpoint | Interface | ~$7.20/月 |
| FSx Endpoint | Interface | ~$7.20/月 |
| CloudWatch Endpoint | Interface | ~$7.20/月 |
| SNS Endpoint | Interface | ~$7.20/月 |
| **Interface VPC Endpoints 合計** | | **~$28.80/月** |
| S3 Gateway Endpoint | Gateway | **無料** |

> ⚠️ **重要**: Interface VPC Endpoints は常時稼働の固定費であり、本プロジェクトにおける最大の固定コストです。デモ/PoC 環境では opt-in（デフォルト無効）を推奨します。

> **注意**: VPC Endpoints は VPC 単位で共有されます。複数のユースケーススタックを同一 VPC にデプロイする場合、VPC Endpoints は 1 セットのみ必要です（最初のスタックで作成し、2 番目以降は `EnableVpcEndpoints=false` で共有）。

#### EventBridge Scheduler

| 項目 | コスト |
|------|-------|
| 無料枠 | 月間 14,000,000 回の呼び出し |
| 超過分 | $1.00/100万回 |

> ✅ 本プロジェクトの全ユースケースを合わせても無料枠内に収まるため、実質無料。

#### SNS

| 項目 | コスト |
|------|-------|
| 最初の 100万リクエスト | 無料 |
| Email 通知 | $2.00/100,000 通 |

> ✅ 通知頻度が低いため、実質無料〜数セント/月。

#### Glue Data Catalog

| 項目 | コスト |
|------|-------|
| 最初の 100万オブジェクト | 無料 |
| 超過分 | $1.00/100,000 オブジェクト/月 |

> ✅ 本プロジェクトの規模では無料枠内。

### 2.2 コンピュートコスト

#### Lambda

| 項目 | 単価 |
|------|------|
| リクエスト | $0.20/100万リクエスト |
| 実行時間（128MB） | $0.0000000021/ms |
| 実行時間（256MB） | $0.0000000042/ms |

**概算**（128MB、平均実行時間 1秒）:
- 1,000 回実行: ~$0.0002（リクエスト）+ ~$0.0021（実行時間）= **~$0.003**
- 10,000 回実行: ~$0.002 + ~$0.021 = **~$0.023**
- 100,000 回実行: ~$0.02 + ~$0.21 = **~$0.23**

#### Step Functions（Standard Workflow）

| 項目 | 単価 |
|------|------|
| ステート遷移 | $0.025/1,000 遷移 |
| 無料枠 | 月間 4,000 遷移 |

**概算**（1ワークフロー = 約 5 ステート遷移）:
- 100 ファイル/月: 500 遷移 → **無料枠内**
- 1,000 ファイル/月: 5,000 遷移 → **~$0.025**
- 10,000 ファイル/月: 50,000 遷移 → **~$1.15**

### 2.3 ストレージ・データアクセスコスト

#### S3 API

| 操作 | 単価 |
|------|------|
| PUT/COPY/POST/LIST | $0.005/1,000 リクエスト |
| GET/SELECT | $0.0004/1,000 リクエスト |
| ストレージ（S3 Standard） | $0.025/GB/月 |

#### Athena

| 項目 | 単価 |
|------|------|
| クエリスキャン | $5.00/TB |
| 最小課金 | 10MB/クエリ |

**概算**:
- 100MB スキャン/クエリ × 10 クエリ/月 = 1GB → **~$0.005**
- 1GB スキャン/クエリ × 30 クエリ/月 = 30GB → **~$0.15**

#### CloudWatch Logs

| 項目 | 単価 |
|------|------|
| データ取り込み | $0.76/GB |
| データ保存 | $0.033/GB/月 |

#### CloudWatch Alarms

| 項目 | 単価 |
|------|------|
| Standard Alarm | $0.10/アラーム/月 |

### 2.4 AI/ML サービスコスト

#### Amazon Textract（UC2）

| API | 単価 |
|-----|------|
| AnalyzeDocument（同期） | $1.50/1,000 ページ |
| StartDocumentAnalysis（非同期） | $1.50/1,000 ページ |

#### Amazon Comprehend（UC2, UC5）

| API | 単価 |
|-----|------|
| Entity Detection | $0.0001/ユニット（100文字） |
| 最小課金 | 3 ユニット/リクエスト |

#### Amazon Rekognition（UC3, UC4, UC5）

| API | 単価 |
|-----|------|
| DetectLabels | $1.00/1,000 画像 |
| DetectText | $1.00/1,000 画像 |

#### Amazon Bedrock（UC1, UC2）

| モデル | 入力トークン | 出力トークン |
|-------|------------|------------|
| Claude 3.5 Sonnet | $0.003/1K tokens | $0.015/1K tokens |
| Claude 3 Haiku | $0.00025/1K tokens | $0.00125/1K tokens |
| Amazon Nova Pro | $0.0008/1K tokens | $0.0032/1K tokens |
| Amazon Nova Lite | $0.00006/1K tokens | $0.00024/1K tokens |

---

## 3. デフォルト有効/オプショナル判断基準

### 3.1 判断基準

| 基準 | デフォルト有効 | オプショナル（opt-in） |
|------|-------------|---------------------|
| 課金モデル | リクエストベース（使わなければ $0） | 常時稼働（存在するだけで課金） |
| 月額固定費 | $0 または無料枠内 | $1/月 以上の固定費 |
| 必須性 | ワークフロー実行に必須 | 運用監視・セキュリティ強化用 |
| PoC 適合性 | デモ環境で安全に使用可能 | 本番環境向け |

### 3.2 デフォルト有効リソース

以下のリソースはリクエストベースまたは無料枠内のため、デフォルトで有効化する。

| リソース | 理由 |
|---------|------|
| Lambda 関数 | リクエストベース課金。実行しなければ $0 |
| Step Functions ステートマシン | リクエストベース課金。月間 4,000 遷移まで無料 |
| S3 出力バケット | ストレージ課金のみ。空なら $0 |
| EventBridge Scheduler | 月間 1,400万回まで無料 |
| SNS Topic | 月間 100万リクエストまで無料 |
| IAM ロール | 完全無料 |
| S3 Gateway VPC Endpoint | 完全無料 |
| Glue Data Catalog | 100万オブジェクトまで無料 |

### 3.3 オプショナル（opt-in）リソース

以下のリソースは固定費が発生するため、CloudFormation Conditions でオプショナルにする。

| リソース | 月額固定費 | CloudFormation パラメータ | デフォルト値 |
|---------|-----------|------------------------|------------|
| Interface VPC Endpoints（4個） | ~$28.80/月 | `EnableVpcEndpoints` | `false` |
| CloudWatch Alarms | ~$0.10/アラーム/月 | `EnableCloudWatchAlarms` | `false` |
| Athena Workgroup | $0（クエリ実行時のみ課金） | `EnableAthenaWorkgroup` | `true` |

> **設計根拠**: 固定費リソースを opt-in にすることで、デモ/PoC デプロイ時の予期しない課金を防止する。本番環境では `EnableVpcEndpoints=true` を推奨する（Lambda が VPC 内で実行される場合、VPC Endpoints がないと AWS サービスにアクセスできない）。

---

## 4. ユースケース別コスト概算

### 4.1 UC1: 法務・コンプライアンス（ファイルサーバー監査・データガバナンス）

**使用サービス**: Lambda, Step Functions, S3, ONTAP REST API, Athena, Glue, Bedrock, SNS

| スケール | ファイル数/月 | Lambda | Step Functions | S3 API | Athena | Bedrock | 合計（変動費） |
|---------|------------|--------|---------------|--------|--------|---------|-------------|
| 小規模 | 100 | ~$0.01 | 無料枠内 | ~$0.01 | ~$0.01 | ~$0.10 | **~$0.13** |
| 中規模 | 1,000 | ~$0.05 | ~$0.03 | ~$0.05 | ~$0.05 | ~$1.00 | **~$1.18** |
| 大規模 | 10,000 | ~$0.50 | ~$1.15 | ~$0.50 | ~$0.50 | ~$10.00 | **~$12.65** |

**固定費（opt-in 時）**: VPC Endpoints ~$28.80/月 + CloudWatch Alarms ~$0.30/月

### 4.2 UC2: 金融・保険（契約書・請求書の自動処理）

**使用サービス**: Lambda, Step Functions, S3, Textract, Comprehend, Bedrock, SNS

| スケール | ドキュメント数/月 | Lambda | Step Functions | S3 API | Textract | Comprehend | Bedrock | 合計（変動費） |
|---------|----------------|--------|---------------|--------|----------|-----------|---------|-------------|
| 小規模 | 100 | ~$0.01 | 無料枠内 | ~$0.01 | ~$0.15 | ~$0.03 | ~$0.10 | **~$0.30** |
| 中規模 | 1,000 | ~$0.05 | ~$0.05 | ~$0.05 | ~$1.50 | ~$0.30 | ~$1.00 | **~$2.95** |
| 大規模 | 10,000 | ~$0.50 | ~$1.50 | ~$0.50 | ~$15.00 | ~$3.00 | ~$10.00 | **~$30.50** |

**固定費（opt-in 時）**: VPC Endpoints ~$28.80/月 + CloudWatch Alarms ~$0.30/月

### 4.3 UC3: 製造業（IoT センサーログ・品質検査画像の分析）

**使用サービス**: Lambda, Step Functions, S3, Athena, Glue, Rekognition, SNS

| スケール | ファイル数/月 | Lambda | Step Functions | S3 API | Athena | Rekognition | 合計（変動費） |
|---------|------------|--------|---------------|--------|--------|------------|-------------|
| 小規模 | 100 | ~$0.01 | 無料枠内 | ~$0.01 | ~$0.01 | ~$0.10 | **~$0.13** |
| 中規模 | 1,000 | ~$0.05 | ~$0.05 | ~$0.05 | ~$0.05 | ~$1.00 | **~$1.20** |
| 大規模 | 10,000 | ~$0.50 | ~$1.50 | ~$0.50 | ~$0.50 | ~$10.00 | **~$13.00** |

**固定費（opt-in 時）**: VPC Endpoints ~$28.80/月 + CloudWatch Alarms ~$0.30/月

### 4.4 UC4: メディア（VFX レンダリングパイプライン）

**使用サービス**: Lambda, Step Functions, S3, Rekognition, Deadline Cloud, SNS

| スケール | アセット数/月 | Lambda | Step Functions | S3 API | Rekognition | Deadline Cloud | 合計（変動費） |
|---------|------------|--------|---------------|--------|------------|---------------|-------------|
| 小規模 | 100 | ~$0.01 | 無料枠内 | ~$0.01 | ~$0.10 | 別途※ | **~$0.12** |
| 中規模 | 1,000 | ~$0.05 | ~$0.05 | ~$0.05 | ~$1.00 | 別途※ | **~$1.15** |
| 大規模 | 10,000 | ~$0.50 | ~$1.50 | ~$0.50 | ~$10.00 | 別途※ | **~$12.50** |

※ AWS Deadline Cloud のコストはレンダリングジョブの規模・時間に依存するため、別途見積もりが必要。

**固定費（opt-in 時）**: VPC Endpoints ~$28.80/月 + CloudWatch Alarms ~$0.20/月

### 4.5 UC5: 医療（DICOM 画像の自動分類・匿名化）

**使用サービス**: Lambda, Step Functions, S3, Rekognition, Comprehend Medical, SNS

| スケール | DICOM ファイル数/月 | Lambda | Step Functions | S3 API | Rekognition | Comprehend Medical | 合計（変動費） |
|---------|-------------------|--------|---------------|--------|------------|-------------------|-------------|
| 小規模 | 100 | ~$0.01 | 無料枠内 | ~$0.01 | ~$0.10 | ~$0.05 | **~$0.17** |
| 中規模 | 1,000 | ~$0.05 | ~$0.05 | ~$0.05 | ~$1.00 | ~$0.50 | **~$1.65** |
| 大規模 | 10,000 | ~$0.50 | ~$1.50 | ~$0.50 | ~$10.00 | ~$5.00 | **~$17.50** |

**固定費（opt-in 時）**: VPC Endpoints ~$28.80/月 + CloudWatch Alarms ~$0.20/月

---

## 5. コスト最適化の推奨事項

### 5.1 デモ/PoC 環境

- Interface VPC Endpoints を**無効化**（`EnableVpcEndpoints=false`）して月額 ~$28.80 を節約
- CloudWatch Alarms を**無効化**（`EnableCloudWatchAlarms=false`）
- Lambda を VPC 外で実行し、インターネット経由で AWS サービスにアクセス
- 小規模テスト（100 ファイル以下）で動作確認

**推定月額コスト**: **$0.13〜$0.30**（変動費のみ）

### 5.2 本番環境

- Interface VPC Endpoints を**有効化**（`EnableVpcEndpoints=true`）してセキュアなプライベート接続を確保
- CloudWatch Alarms を**有効化**（`EnableCloudWatchAlarms=true`）して運用監視を実施
- Lambda を VPC 内で実行し、インターネットアクセスを遮断
- Athena Workgroup を有効化してクエリコスト管理を実施

**推定月額コスト**: **$30〜$75**（固定費 + 中規模変動費）

### 5.3 全体コストサマリー

| 環境 | 固定費/月 | 変動費/月（中規模） | 合計/月 |
|------|----------|-------------------|--------|
| デモ/PoC | ~$0 | ~$1〜$3 | **~$1〜$3** |
| 本番（1 UC） | ~$29 | ~$1〜$3 | **~$30〜$32** |
| 本番（全 5 UC） | ~$29 | ~$5〜$15 | **~$34〜$44** |

> **注意**: VPC Endpoints は全ユースケースで共有されるため、固定費は UC 数に関係なく一定です。変動費のみがスケールに応じて増加します。

---

## 6. 参考リンク

- [AWS Lambda 料金](https://aws.amazon.com/lambda/pricing/)
- [AWS Step Functions 料金](https://aws.amazon.com/step-functions/pricing/)
- [Amazon S3 料金](https://aws.amazon.com/s3/pricing/)
- [Amazon Textract 料金](https://aws.amazon.com/textract/pricing/)
- [Amazon Comprehend 料金](https://aws.amazon.com/comprehend/pricing/)
- [Amazon Rekognition 料金](https://aws.amazon.com/rekognition/pricing/)
- [Amazon Bedrock 料金](https://aws.amazon.com/bedrock/pricing/)
- [Amazon Athena 料金](https://aws.amazon.com/athena/pricing/)
- [Amazon VPC 料金](https://aws.amazon.com/vpc/pricing/)
- [Amazon CloudWatch 料金](https://aws.amazon.com/cloudwatch/pricing/)
- [Amazon EventBridge 料金](https://aws.amazon.com/eventbridge/pricing/)
