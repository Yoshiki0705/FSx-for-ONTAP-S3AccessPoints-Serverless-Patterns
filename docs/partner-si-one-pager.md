# Partner/SI 1 枚要約: FSx for ONTAP S3 Access Points Serverless Patterns

🌐 **Language / 言語**: [日本語](partner-si-one-pager.md) | [English](partner-si-one-pager.en.md)

---

## What — このリポジトリが提供するもの

| 項目 | 内容 |
|------|------|
| 業界別ユースケース | 28 UC（Legal, Healthcare, Manufacturing, Public Sector 等） |
| FlexCache/FlexClone パターン | 6 FC（DR, Render, RAG, CAE, Life Sciences, Gaming） |
| テンプレート形式 | CloudFormation (SAM Transform) — 独立デプロイ可能 |
| トリガーモード | POLLING (default) / EVENT_DRIVEN (FPolicy) / HYBRID |
| 成熟度モデル | 4 段階（Sandbox → Scheduled → Monitored → Production） |
| テスト | 1,499+ unit/property tests, cfn-lint, ruff validation |

## When — いつ使うか

以下の条件に当てはまる顧客に提案可能:

- ✅ FSx for ONTAP にファイルデータを保有している
- ✅ ファイルデータに対するサーバーレス自動処理が必要
- ✅ S3 API 経由の読み書き（GetObject, PutObject, ListObjectsV2 等）が必要
- ✅ NTFS ACL / AD SID によるアクセス制御が必要（権限考慮型処理）
- ✅ AI/ML（Bedrock, Textract, Comprehend, Rekognition）を活用したい
- ✅ イベント駆動またはスケジュール実行でファイル処理を自動化したい

> **Note**: S3 Access Points は読み取り専用ではありません。PutObject（最大 5 GB）、DeleteObject、MultipartUpload もサポートされています。ただし FSX_ONTAP ストレージクラスのみ、SSE-FSX 暗号化のみ等の制約があります。詳細は [S3AP Compatibility Notes](s3ap-compatibility-notes.md) を参照。

## How — PoC の進め方

```
Step 1: 最も近い UC を特定 → Success Metrics を確認
Step 2: テンプレートをデプロイ → S3AP アクセスを検証
Step 3: Customer-Specific Baseline を測定
Step 4: Go/No-Go 基準で評価
```

**所要時間の目安**:
- Level 1 (Sandbox): 1-2 時間
- Level 2 (Scheduled): 1-2 日
- Level 3 (Monitored): 1-2 週間

**詳細手順**: [Partner/SI Delivery Checklist](partner-si-delivery-checklist.md)

## Where — 主要リソースの場所

| リソース | パス |
|---------|------|
| Success Metrics | 各 UC の README.md |
| ガバナンス | [docs/governance-checklist.md](governance-checklist.md) |
| 本番化基準 | [docs/production-readiness.md](production-readiness.md) |
| ベンチマーク | [docs/s3ap-benchmark-results.md](s3ap-benchmark-results.md) |
| 顧客ヒアリング | [docs/customer-discovery-template.md](customer-discovery-template.md) |
| トリガー選択 | [docs/trigger-mode-decision-guide.md](trigger-mode-decision-guide.md) |
| 公共セクター | [docs/public-sector-adoption-roadmap.md](public-sector-adoption-roadmap.md) |
| ワークショップ | [docs/workshop-guide.md](workshop-guide.md) |

---

> **注意**: 本リポジトリは「設計判断を学ぶためのリファレンス実装」です。本番環境への適用には顧客固有のセキュリティレビュー、コンプライアンス評価、性能検証が必要です。
