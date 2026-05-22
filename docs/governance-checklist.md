# Governance Checklist — 規制・公共・医療ワークロード向け

🌐 **Language / 言語**: [日本語](governance-checklist.md) | [English](governance-checklist.en.md)

## 概要

本チェックリストは、Healthcare (UC5)、Government Archives (UC16)、Education/Research (UC13)、Defense (UC15) など、規制対象・公共セクターのワークロードで本パターンを採用する際のガバナンス確認項目を整理したものです。

> **重要**: 本リポジトリの AI/ML 処理出力は **意思決定支援** であり、最終判断は人間が行うことを前提としています。医療診断、行政処分、法的判断など、業務影響の大きい領域では **Human-in-the-loop** を推奨します。

### Executive Summary（意思決定者向け）

本チェックリストは、以下の観点が設計に組み込まれていることを確認するためのものです:

- **データ分類**: 処理対象データの機密レベル（個人情報・医療情報・機微情報・公文書）が特定されている
- **アクセス制御**: AWS IAM とファイルシステム権限の二層認可が設計されている
- **監査可能性**: 処理履歴・アクセスログ・データリネージが保持される
- **クロスリージョン**: 一部 AI サービスのリージョン越境呼び出しの可否が確認されている
- **AI 出力レビュー**: 高リスク出力に対する人間確認プロセスが定義されている
- **運用責任**: 障害対応・パッチ管理・コスト管理の責任者が明確である
- **コンプライアンス**: 適用される規制・ガイドラインとの整合性が確認されている

> 技術詳細は以降のセクションで確認できます。意思決定者は本サマリーと「導入前チェックリスト」（末尾）を中心にご確認ください。

> **注意**: 本チェックリストはアーキテクチャおよび運用レビューを支援するためのものです。法務判断、コンプライアンス評価、プライバシー評価、規制対応の代替ではありません。最終的な法令・規制判断は、責任ある組織の法務・コンプライアンス部門が行ってください。

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

### 人間の確認ポイント（具体例）

| 確認タイミング | 対象 UC | 確認内容 | 確認者 |
|-------------|---------|---------|--------|
| AI 分類結果の確認 | UC1, UC16 | 文書カテゴリが正しいか | 法務担当 / 公文書管理者 |
| 匿名化結果の確認 | UC5, UC16 | PII/PHI が適切に墨消しされているか | プライバシー担当 |
| 要約結果の確認 | UC2, UC14 | 金額・日付・当事者情報が正確か | 業務担当者 |
| アラート通知前の承認 | UC15 | 防衛関連アラートの発報前確認 | セキュリティ担当 |
| 外部共有前のレビュー | UC16 | FOIA 開示文書の最終確認 | 情報公開担当 |
| バリアント分類の確認 | UC7 | 臨床的意義のある変異の確認 | 研究者 / 臨床医 |

### 監査証跡レコードの項目例

DynamoDB（または組織の監査ログ基盤）に記録する項目の例:

| 項目 | 説明 | 例 |
|------|------|-----|
| review_id | レビュー一意 ID | `rev-2026-05-22-001` |
| use_case_id | 対象 UC | `UC16` |
| object_key | 処理対象ファイル | `archives/2026/doc-001.pdf` |
| ai_output_id | AI 処理結果 ID | `step-exec-abc123` |
| reviewer_id | 確認者 ID | `user@example.com` |
| review_timestamp | 確認日時 | `2026-05-22T10:30:00Z` |
| review_decision | 判定 | `approved` / `rejected` / `escalated` |
| review_comment | コメント | 「墨消し範囲を修正」 |
| confidence_score | AI 信頼度スコア | `0.72` |
| escalation_required | エスカレーション要否 | `false` |
| retention_period | 保持期間 | `7 years` |

### 監査証跡の設計考慮事項

| 項目 | 検討内容 |
|------|---------|
| 保存先 | DynamoDB（サンプル実装）。実案件では組織の SIEM、ログ基盤、文書管理基盤に合わせて選択 |
| 保持期間 | 組織のポリシーに依存（例: FISC 7年、HIPAA 6年、NARA 永久） |
| アクセス権限 | 監査担当者のみ参照可能。運用チームは書き込みのみ |
| 削除方針 | 保持期間経過後の自動削除 or アーカイブ |
| 改ざん防止 | S3 Object Lock への定期エクスポート推奨 |
| 既存基盤連携 | CloudWatch Logs → S3 → 既存 SIEM、または EventBridge → 既存監査基盤 |

### 改ざん防止の実装オプション

| オプション | 説明 | 適用シナリオ |
|-----------|------|------------|
| S3 Object Lock (Governance/Compliance) | DynamoDB → Export → S3 (Object Lock) | 長期保管・改ざん防止が必須 |
| CloudTrail Lake | API 呼び出し履歴の不変ストア | AWS API レベルの監査 |
| DynamoDB Streams → Kinesis → S3 | リアルタイムアーカイブ | 高頻度レビューの即時保全 |
| SIEM 連携 (Splunk, Datadog 等) | 既存監査基盤への転送 | 組織の統合ログ管理 |
| CloudWatch Logs → S3 (Lifecycle) | ログの長期保管 | コスト効率重視 |

### 職務分掌（Separation of Duties）

監査証跡のアクセス権限は、以下の職務分掌を前提に設計してください:

| ロール | 権限 | 説明 |
|--------|------|------|
| AI 処理実行者 | Write (レコード作成) | Lambda / Step Functions が自動記録 |
| レビュー担当者 | Write (判定記録) | Human Review の結果を記録 |
| 承認担当者 | Write (承認記録) | エスカレーション案件の最終承認 |
| 監査担当者 | Read-only | 監査時の参照・レポート生成 |
| システム運用担当 | 管理 (テーブル設定) | DynamoDB 設定・バックアップ管理 |

> **原則**: レビューする人と承認する人は同一であってはならない。監査する人は処理・レビュー・承認のいずれも行わない。

> **注意**: 本リポジトリのサンプル実装では DynamoDB を使用していますが、これは一例です。実案件では組織の既存監査ログ基盤（SIEM、Splunk、CloudTrail Lake 等）に合わせて保存先を選択してください。

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
