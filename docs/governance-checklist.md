# Governance Checklist — 規制・公共・医療ワークロード向け

🌐 **Language / 言語**: [日本語](governance-checklist.md) | [English](governance-checklist.en.md)

## 概要

本チェックリストは、Healthcare (UC5)、Government Archives (UC16)、Education/Research (UC13)、Defense (UC15) など、規制対象・公共セクターのワークロードで本パターンを採用する際のガバナンス確認項目を整理したものです。

> **重要**: 本リポジトリの AI/ML 処理出力は **意思決定支援** であり、最終判断は人間が行うことを前提としています。医療診断、行政処分、法的判断など、業務影響の大きい領域では **Human-in-the-loop** を推奨します。

---

## 1. データ分類

| 分類 | 説明 | 該当 UC 例 | 追加対策 |
|------|------|-----------|---------|
| 個人情報 (PII) | 氏名、住所、電話番号、メールアドレス | UC2, UC14, UC16 | Comprehend PII 検出 + 墨消し |
| 医療情報 (PHI) | 患者 ID、診断情報、DICOM メタデータ | UC5, UC7 | Comprehend Medical + 匿名化 |
| 機微情報 | 防衛関連、セキュリティクリアランス対象 | UC15 | VPC 内処理限定、暗号化必須 |
| 公文書 | 行政文書、FOIA 対象、保管期限付き | UC16 | 改ざん防止、保管期限管理 |
| 一般業務データ | 製造ログ、メディアファイル、研究データ | UC1-4, UC6-14 | 標準的な暗号化・アクセス制御 |

---

## 2. データフロー・保存場所の確認

| データ | 保存場所 | 暗号化 | アクセス制御 |
|--------|---------|--------|------------|
| 入力ファイル（原本） | FSx for ONTAP Volume | SSE-FSX (KMS managed) | NTFS ACL / UNIX permissions + S3 AP dual-layer |
| AI/ML 処理結果 | S3 Output Bucket or FSxN S3AP | SSE-KMS or SSE-FSX | IAM + Bucket/AP Policy |
| 実行ログ | CloudWatch Logs | SSE (default) | IAM + Log Group Policy |
| 実行履歴 | Step Functions | SSE (default) | IAM |
| メトリクス | CloudWatch Metrics | — | IAM |
| AI サービス呼び出し | Bedrock / Textract / Comprehend | TLS in-transit | IAM + Service Policy |

---

## 3. リージョン越境の確認

| AI サービス | ap-northeast-1 対応 | クロスリージョン呼び出し | 確認事項 |
|------------|--------------------|-----------------------|---------|
| Amazon Bedrock | ✅ | 不要 | — |
| Amazon Rekognition | ✅ | 不要 | — |
| Amazon Comprehend | ✅ | 不要 | — |
| Amazon Textract | ❌ | us-east-1 等へルーティング | データが一時的に別リージョンへ送信される |
| Comprehend Medical | ❌ | us-east-1 等へルーティング | PHI が別リージョンへ送信される |


> **規制対象データのクロスリージョン呼び出し**: Textract / Comprehend Medical を使用する UC (UC2, UC5, UC7, UC10, UC12, UC13, UC14) では、入力データが一時的に対応リージョンへ送信されます。医療情報や個人情報を含む場合、組織のデータレジデンシー要件との整合性を確認してください。

---

## 4. 監査ログ・証跡

| ログソース | 記録内容 | 保管期間（推奨） | 改ざん防止 |
|-----------|---------|----------------|-----------|
| AWS CloudTrail | API 呼び出し履歴 | 1 年以上 | S3 Object Lock |
| Step Functions 実行履歴 | ワークフロー実行結果 | 90 日（デフォルト） | — |
| CloudWatch Logs | Lambda 実行ログ | 要件に応じて設定 | — |
| S3 Access Logs | S3 AP 経由のアクセス記録 | 1 年以上 | S3 Object Lock |
| DynamoDB (Lineage) | データリネージ | 7 年（Compliance profile） | S3 Object Lock export |
| FPolicy イベントログ | ファイル操作イベント | 要件に応じて | Persistent Store + SQS |

---

## 5. Human-in-the-loop 設計

### AI 出力の信頼性レベル

| UC | AI 処理内容 | 誤り影響度 | 推奨レビュー方式 |
|----|-----------|-----------|----------------|
| UC5 | DICOM 画像分類・匿名化 | 高（患者プライバシー） | 匿名化結果の人間レビュー必須 |
| UC16 | 公文書 PII 検出・墨消し | 高（FOIA 対応） | 墨消し結果の人間確認必須 |
| UC14 | 保険請求損害評価 | 中（金額影響） | 高額案件は人間レビュー |
| UC2 | 請求書 OCR・データ抽出 | 中（金額影響） | 信頼度スコア閾値以下は人間確認 |
| UC1 | 契約書メタデータ抽出 | 低〜中 | サンプリングレビュー |
| UC3 | 製造ログ異常検知 | 低 | アラート通知のみ |

### 実装パターン

```
AI 処理結果
├── 信頼度 ≥ 閾値 → 自動確定（ログ記録）
└── 信頼度 < 閾値 → Human Review Queue
    ├── SNS 通知 → レビュー担当者
    ├── DynamoDB に pending 状態で保存
    └── 人間が確認・修正 → 確定
```

---

## 6. 責任ある AI (Responsible AI) ガードレール

### 本リポジトリの AI 利用に関する前提

1. **AI 出力は意思決定支援**: 最終判断は人間が行う
2. **医療・行政文書では Human-in-the-loop を推奨**: 自動確定は低リスク処理のみ
3. **バイアス・公平性**: AI モデルの出力に偏りがないか定期的に評価する
4. **透明性**: AI がどの入力からどの出力を生成したかのリネージを保持する
5. **説明責任**: AI 処理の結果に対する責任は運用組織にある

### UC 別ガードレール

| UC | ガードレール | 実装方法 |
|----|------------|---------|
| UC5 (Healthcare) | 匿名化漏れ検出 | Comprehend Medical + 人間レビュー |
| UC16 (Government) | 過剰墨消し防止 | 墨消し前後の diff レビュー |
| UC15 (Defense) | 分類レベル確認 | 出力前の人間承認ゲート |
| UC7 (Genomics) | バリアント誤分類防止 | 既知バリアント DB との照合 |

---

## 7. コンプライアンス対応マッピング

| 規制・基準 | 該当 UC | 主な要件 | 本パターンでの対応 |
|-----------|---------|---------|-----------------|
| FISC 安全対策基準 | UC2, UC14 | データ暗号化、アクセス制御、監査証跡 | KMS 暗号化 + IAM + CloudTrail |
| HIPAA | UC5, UC7 | PHI 保護、アクセスログ、暗号化 | Comprehend Medical + 匿名化 + 監査ログ |
| GDPR | UC1, UC2, UC14 | データ最小化、削除権、処理記録 | PII 検出 + リネージ + 削除追跡 |
| NARA / FOIA | UC16 | 公文書保管、開示対応、墨消し | S3 Object Lock + 墨消し + 保管期限管理 |
| 個人情報保護法 | 全 UC | 利用目的明示、安全管理措置 | IAM 最小権限 + 暗号化 + ログ |
| 医療情報ガイドライン | UC5 | 3 省 2 ガイドライン準拠 | 暗号化 + アクセス制御 + 監査 |

---

## 8. 導入前チェックリスト（意思決定者向け）

- [ ] データ分類は完了しているか（個人情報、医療情報、機微情報の特定）
- [ ] クロスリージョン呼び出しの許容可否を確認したか
- [ ] AI 出力の Human-in-the-loop 要否を決定したか
- [ ] 監査ログの保管期間・改ざん防止方式を決定したか
- [ ] データリネージの保持要件を確認したか
- [ ] 責任分界（AWS 責任共有モデル）を理解しているか
- [ ] Deployment Profile（PoC / Production / Compliance）を選択したか
- [ ] インシデント対応手順を定義したか
- [ ] 定期的な AI 出力品質レビューの仕組みを設計したか

---

## 参考リンク

- [Deployment Profiles](deployment-profiles.md)
- [S3AP 二段階認可モデル](s3ap-authorization-model.md)
- [Partner/SI Delivery Checklist](partner-si-delivery-checklist.md)
- [AWS 責任共有モデル](https://aws.amazon.com/compliance/shared-responsibility-model/)
- [Amazon Bedrock Responsible AI](https://aws.amazon.com/bedrock/responsible-ai/)
