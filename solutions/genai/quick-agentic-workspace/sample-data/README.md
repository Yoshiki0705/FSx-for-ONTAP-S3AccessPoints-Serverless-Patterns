# サンプルデータ — Amazon Quick ワークスペース シード

FSx for ONTAP の **AI 専用ボリューム（Quick ワークスペース領域）** に投入するシードデータ。
**ロール（部門）× 利用サービス** の2軸で整理している。

> すべて **架空・マスク済み** のサンプルです。

## 2軸構成

### 利用サービス軸（Amazon Quick Suite / Bedrock）

| サブツリー | 対応サービス | データ種別 |
|-----------|------------|-----------|
| `quick-workspace/index/<role>/` | Quick Index / Quick Research | 非構造化（md）— 横断検索・調査 |
| `quick-workspace/analytics/<role>/` | Quick Sight（BI、Glue/Athena 経由） | 構造化（csv）— 数値分析 |
| `quick-workspace/flows/<role>/` | Quick Flows（アクション API + Bedrock） | アクションサンプル（json） |

### ロール軸（Amazon Quick 想定ロール）

sales / marketing / finance / information-technology / operations / legal / developers
（Quick FAQ の sales・marketing・IT・operations・finance・legal ＋ developers 専用ページ）

> 本UCはロール構成を **UC29（genai-kb-selfservice-curation）** と揃えている。

## 使い方（デモ）

```
# AI 専用ボリューム（SMB 共有）へコピー（例）
\\fsxn-share\quick-workspace\  ← この sample-data/quick-workspace/ 配下を丸ごとコピー
```

- `index/` … Amazon Quick の Quick Index データソースに接続（非構造化検索）
- `analytics/` … Glue テーブル化し Athena/Quick Sight で分析（DDL は [demo-guide](../docs/demo-guide.md) 参照）
- `flows/` … Quick Flows が Action API（API Gateway + Lambda）を呼ぶ際の入力例

## ディレクトリ

```
sample-data/quick-workspace/
├── index/<role>/*.md       … Quick Index / Quick Research
├── analytics/<role>/*.csv  … Quick Sight (Athena)
└── flows/<role>/*.json     … Quick Flows (Action API)
```

> 情報・料金・サービス仕様は time-sensitive。最新は [aws.amazon.com/quick](https://aws.amazon.com/quick/) を参照。
