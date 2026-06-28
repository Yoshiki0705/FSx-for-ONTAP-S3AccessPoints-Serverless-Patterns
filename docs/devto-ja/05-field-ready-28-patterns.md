---
title: "フィールド展開可能なリファレンスアーキテクチャ — 28業種パターンへの拡張と運用知見"
published: false
description: "FSx for ONTAP S3 AP パターン集を17から28業種に拡張し、フィールド展開に必要なベンチマーク、ガバナンス、パートナー資産を整備した Phase 13〜15。"
tags: aws, netapp, referencearchitecture, benchmark
series: "FSx for ONTAP S3 AP サーバーレスパターン集"
---

## TL;DR

Phase 13〜15 でパターン集は「ライブラリ」から「フィールド展開可能なリファレンスアーキテクチャ」へ昇格。28 業種パターン + ベンチマーク + ガバナンスガイド + パートナーデリバリー資産を備えた、顧客/SI 向けに即座に活用できるパッケージになりました。

| Phase | 成果 |
|-------|------|
| 13 | 成功指標定義、ガバナンスノート、本番レディネスチェック、PoC Go/No-Go テンプレート |
| 14 | Presigned URL 動作確認（公式ドキュメントと矛盾）、スループット変更時の S3 AP 不可用性発見 |
| 15 | 17 → **28 業種パターン**拡張 + FlexCache/FlexClone 6パターン + SAP/ERP 1パターン = 計35パターン |

📦 **リポジトリ**: [GitHub](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)

---

## Phase 13: フィールドレディ基盤

### Success Metrics フレームワーク

各パターンに以下の成功指標を定義：

| カテゴリ | 例 |
|---------|-----|
| Business Outcome | 手動作業時間 80% 削減 |
| Technical KPI | 処理レイテンシ p95 < 10秒 |
| Quality KPI | AI 精度 > 95% |
| Cost KPI | 月額コスト < $200 (DemoMode) |
| Go/No-Go | 4週間 PoC 後に判定 |

### ガバナンスノート

規制業界（金融、医療、公共）向けに、各パターンのガバナンス上の注意点を記載：

- **金融**: FISC 安全対策基準への考慮事項（データ保管場所、アクセスログ、暗号化要件）
- **医療**: 3省2ガイドライン・HIPAA 相当のデータ保護考慮事項（PHI 分離、監査証跡）
- **公共**: ISMAP / ガバメントクラウド要件への注意点

> ⚠️ これらは技術的な考慮事項の整理であり、法的助言やコンプライアンス認証を保証するものではありません。

### パートナー/SI 資産

- PoC Go/No-Go テンプレート (`docs/poc-go-nogo-template.md`)
- パートナーデリバリーチェックリスト (`docs/partner-si-delivery-checklist.md`)
- コスト計算ツール (`docs/cost-calculator.md`)
- パターン選択ガイド (`docs/pattern-selection-guide.md`)

---

## Phase 14: エビデンス強化と運用発見

### Presigned URL が動作する（ドキュメント上は非対応）

AWS ドキュメントでは FSx for ONTAP S3 AP の Presigned URL は「非対応」とされています。しかし実際にテストしたところ**動作しました**。

> ⚠️ これは「ドキュメント上非対応だが現時点で動作する」状態。本番利用にはリスクあり。

### スループット変更時の S3 AP 不可用性

> ⚠️ **運用上の重要な発見**: FSx for ONTAP のスループットキャパシティ変更中（約15〜20分）、S3 Access Points が一時的に利用不可になります。この間 NFS/SMB アクセスは継続しますが、S3 AP 経由のパイプラインは中断します。メンテナンスウィンドウでの実施を推奨します。

| 操作 | S3 AP への影響 | 所要時間 |
|------|---------------|---------|
| スループット増加 (128→256 MBps) | 一時不可用 | 約15〜20分 |
| スループット減少 | 一時不可用 | 約15〜20分 |
| ストレージ容量追加 | 影響なし | — |

**運用上の対策**: スループット変更はメンテナンスウィンドウで実施。Event-Driven パイプラインは Persistent Store + DLQ で耐障害性確保。

---

## Phase 15: 28 業種パターンへ拡張

### 新規 11 パターン (UC18〜UC28)

| UC | 業界 | AI/ML サービス |
|----|------|---------------|
| UC18 | 農業 | Rekognition (作物病害検出) |
| UC19 | 航空宇宙 | SageMaker (構造解析) |
| UC20 | 通信 | Comprehend (ネットワークログ分析) |
| UC21 | 不動産 | Textract + Bedrock (契約書解析) |
| UC22 | ホスピタリティ | Transcribe + Translate |
| UC23 | スポーツ | Rekognition (動作分析) |
| UC24 | 法執行機関 | Rekognition + Comprehend |
| UC25 | 出版 | Bedrock (要約・翻訳) |
| UC26 | 環境 | SageMaker (衛星データ) |
| UC27 | 鉱業 | SageMaker (地質データ) |
| UC28 | 食品安全 | Rekognition (検査画像) |

### FlexCache/FlexClone パターン (6つ)

| パターン | ユースケース |
|---------|-------------|
| Anycast DR | FlexCache による読み取り分散 + DR |
| Dynamic Render | レンダリングワークフローの一時ボリューム |
| RAG Enterprise Files | FlexClone で安全に AI 学習データ提供 |
| Automotive CAE | CAE シミュレーション用一時クローン |
| Life Sciences | 研究データの非破壊コピー |
| Gaming Build | ビルドパイプラインの並列クローン |

### SAP/ERP Adjacent パターン

SAP HANA のバックアップ/リストアと FSx for ONTAP の統合。SnapCenter 連携パターン。

---

## 35 パターンの全体像

```
14 初期業種 (Phase 1-2)
 + 3 パブリックセクター (Phase 7)
 + 11 追加業種 (Phase 15)
 + 6 FlexCache/FlexClone
 + 1 SAP/ERP
─────────────────────
= 35 デプロイ可能パターン
```

すべてのパターンが:
- CloudFormation テンプレート付き
- DemoMode 対応
- 8 言語ドキュメント
- Property-based テスト付き

---

📦 **パターン選択ガイド**: [docs/pattern-selection-guide.md](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/blob/main/docs/pattern-selection-guide.md)
📦 **コスト計算ツール**: [docs/cost-calculator.md](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/blob/main/docs/cost-calculator.md)

---

> **前回の記事**: [#4 — FPolicy Event-Driven パイプライン](./04-event-driven-fpolicy.md)
> **スループット設計** (Storage Specialist lens): S3 AP 不可用性の発見は、FSx for ONTAP のスループット変更がオンライン操作であっても S3 AP レイヤーには影響することを示しています。NFS/SMB は継続するため、メンテナンスウィンドウの計画に S3 AP 依存パイプラインの停止を含めてください。
> **PoC 実施** (Partner/SI lens): PoC Go/No-Go テンプレートは顧客とのマイルストーン合意に直接使えます。4週間 PoC の標準フレームを提供しているため、SI のデリバリー計画にそのまま組み込み可能です。
