# 業界カバレッジマップ

> **最終更新**: 2026-06-03

本ドキュメントは、AWS 公式 Industries 分類に対する FSx for ONTAP S3 Access Points サーバーレスパターンの対応状況を一覧化する。

## ステータス定義

| ステータス | 説明 |
|-----------|------|
| Covered | 実装済み・テスト完了 |
| Planned-P0 | 即時着手（最優先） |
| Planned-P1 | P0 完了後に着手 |
| Planned-P2 | P1 完了後に着手 |
| Not Covered | 未対応・計画なし |

---

## AWS 公式 Industries カテゴリ

| # | 業界名 (日本語) | Industry (EN) | UC/FC | ステータス | 更新日 |
|---|----------------|---------------|-------|----------|--------|
| 1 | 広告・マーケティング | Advertising & Marketing | UC19 | Covered | 2026-06-02 |
| 2 | 航空宇宙・防衛 | Aerospace & Defense | UC15 | Covered | 2026-05-10 |
| 3 | 自動車 | Automotive | UC9, FC4 | Covered | 2026-01-15 |
| 4 | 消費財 | Consumer Packaged Goods | — | Not Covered | 2026-06-02 |
| 5 | 教育 | Education | UC13 | Covered | 2026-03-20 |
| 6 | エネルギー・ユーティリティ | Energy & Utilities | UC8, UC25 | Covered | 2026-06-03 |
| 7 | 金融サービス | Financial Services | UC2, UC14 | Covered | 2026-03-20 |
| 8 | ゲーム | Games | FC6 | Covered | 2026-05-15 |
| 9 | 政府・公共 | Government | UC16 | Covered | 2026-05-10 |
| 10 | 医療・ヘルスケア | Healthcare & Life Sciences | UC5, UC7, FC5 | Covered | 2026-05-15 |
| 11 | 製造業 | Manufacturing | UC3 | Covered | 2026-01-15 |
| 12 | メディア・エンターテインメント | Media & Entertainment | UC4 | Covered | 2026-01-15 |
| 13 | 鉱業・天然資源 | Mining & Natural Resources | — | Not Covered | 2026-06-02 |
| 14 | 非営利団体 | Nonprofit | UC24 | Covered | 2026-06-03 |
| 15 | 電力・ユーティリティ | Power & Utilities | UC25 | Covered | 2026-06-03 |
| 16 | 小売 | Retail | UC11 | Covered | 2026-03-20 |
| 17 | 半導体 | Semiconductor | UC6 | Covered | 2026-03-20 |
| 18 | ソフトウェア・インターネット | Software & Internet | FC7 | Covered | 2026-06-07 |
| 19 | サステナビリティ | Sustainability | UC23 | Covered | 2026-06-03 |
| 20 | 通信 | Telecommunications | UC18 | Covered | 2026-06-02 |
| 21 | 旅行・ホスピタリティ | Travel & Hospitality | UC20 | Covered | 2026-06-03 |
| 22 | 運輸・物流 | Transportation & Logistics | UC12, UC22 | Covered | 2026-06-03 |

---

## AWS Japan 重点領域（グローバル分類外）

以下は AWS Japan の業界チーム体制に基づく重点領域であり、AWS グローバルの公式 Industries 分類には含まれないが、日本市場で高い需要がある。

| # | 領域名 | Industry (EN) | UC/FC | ステータス | 更新日 |
|---|--------|---------------|-------|----------|--------|
| 1 | 農業・食品 | Agriculture & Food | UC21 | Covered | 2026-06-03 |
| 2 | 建設・土木 | Construction & Civil Engineering | UC10 | Covered | 2026-03-20 |
| 3 | 法務・コンプライアンス | Legal & Compliance | UC1 | Covered | 2026-01-15 |
| 4 | 物流・倉庫 | Logistics & Warehousing | UC12 | Covered | 2026-03-20 |
| 5 | 不動産 | Real Estate | UC26 | Covered | 2026-06-03 |
| 6 | 人材・HR | Human Resources | UC27 | Covered | 2026-06-03 |
| 7 | 化学・素材 | Chemicals & Materials | UC28 | Covered | 2026-06-03 |
| 8 | スマートシティ | Smart City & Geospatial | UC17 | Covered | 2026-05-10 |
| 9 | SAP / ERP | SAP & ERP Adjacent | SAP | Covered | 2026-04-01 |
| 10 | GenAI / RAG | Enterprise GenAI | FC3 | Covered | 2026-05-15 |
| 11 | 保険 | Insurance | UC14 | Covered | 2026-03-20 |

---

## DAIS 2026 業界事例参照

以下の公開事例が、既存パターンの業界適用を裏付けるリファレンスとなる。

| 事例企業 | 業界 | 対応 UC | 概要 | Evidence Tier |
|---------|------|---------|------|--------------|
| 7-Eleven | Retail & Consumer Goods | UC22, UC11 | 設備メンテナンス技術者向け GenAI アシスタント。検索時間 −60%、初回修理成功率 +25% | Public (DAIS 2026 Session + Blog) |
| AstraZeneca | Healthcare & Life Sciences | UC7, UC5 | マルチエージェントシステム。Supervisor + 治療領域別サブエージェント。5 → 20+ エージェントスケール | Public (DAIS 2026 Session + Blog) |

詳細分析: [DAIS 2026 Agent Bricks 事例分析](investigations/dais2026-agent-bricks-industry-cases.md)

---

## 実装優先順位

### P0（即時着手）

| UC | 業界 | ディレクトリ | 概要 |
|----|------|------------|------|
| UC18 | 通信 | `solutions/industry/telecom-network-analytics/` | CDR/ネットワークログ分析・異常検知 |
| UC19 | 広告・マーケティング | `solutions/industry/adtech-creative-management/` | クリエイティブアセット管理・ブランドコンプライアンス |

**着手条件**: なし（即時着手可能）

### P1（P0 完了後）

| UC | 業界 | ディレクトリ | 概要 |
|----|------|------------|------|
| UC20 | 旅行・ホスピタリティ | `solutions/industry/travel-document-processing/` | 予約文書処理・施設点検画像分析 |
| UC21 | 農業・食品 | `solutions/industry/agri-food-traceability/` | 農地航空画像・トレーサビリティ文書管理 |
| UC22 | 運輸・鉄道 | `solutions/industry/transportation-maintenance/` | 設備点検画像・保守レポート分析 |

**着手条件**: UC18 + UC19 の実装完了

### P2（P1 完了後）

| UC | 業界 | ディレクトリ | 概要 |
|----|------|------------|------|
| UC23 | サステナビリティ・ESG | `solutions/industry/sustainability-esg-reporting/` | ESG メトリクス抽出・レポーティング |
| UC24 | NPO・非営利団体 | `solutions/industry/nonprofit-grant-management/` | 助成金申請分類・成果マッチング |
| UC25 | 電力・ユーティリティ | `solutions/industry/utilities-asset-inspection/` | ドローン画像・SCADA ログ分析 |
| UC26 | 不動産 | `solutions/industry/real-estate-portfolio/` | 物件画像分析・契約書データ抽出 |
| UC27 | 人材・HR | `solutions/industry/hr-document-screening/` | 履歴書スクリーニング・候補者評価 |
| UC28 | 化学・素材 | `solutions/industry/chemical-sds-management/` | SDS 管理・ラボノート分析 |

**着手条件**: UC20 + UC21 + UC22 の実装完了

---

## カバレッジサマリ

| ステータス | UC/FC 数 | 割合 |
|-----------|---------|------|
| Covered | 28 UC + 6 FC = 34 | — |
| Planned-P0 | 0 | — |
| Planned-P1 | 0 | — |
| Planned-P2 | 0 | — |
| Not Covered | 3 (消費財, 鉱業, ソフトウェア) | — |

**目標**: 全 AWS Industries カテゴリで少なくとも 1 つの UC/FC を提供する。

---

## 更新履歴

| 日付 | 変更内容 |
|------|---------|
| 2026-06-18 | DAIS 2026 業界事例参照を追加 — 7-Eleven (Retail, UC22), AstraZeneca (Healthcare & Life Sciences, UC7)。[詳細分析](investigations/dais2026-agent-bricks-industry-cases.md) |
| 2026-06-03 | P2 完了 — UC23 (サステナビリティ), UC24 (NPO), UC25 (電力), UC26 (不動産), UC27 (HR), UC28 (化学) を Covered に更新。全 28 UC + 6 FC = 34 パターン |
| 2026-06-03 | P1 完了 — UC20 (旅行), UC21 (農業), UC22 (運輸) を Covered に更新 |
| 2026-06-02 | P0 完了 — UC18 (通信), UC19 (広告) を Covered に更新 |
| 2026-06-02 | 初版作成 — UC18–UC28 の計画ステータスを追加 |
