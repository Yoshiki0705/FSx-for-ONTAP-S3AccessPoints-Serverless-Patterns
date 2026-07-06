# Solutions Directory / ソリューションディレクトリ

このディレクトリには全43パターンがカテゴリ別に整理されています。

| カテゴリ | ディレクトリ | パターン数 | 概要 |
|---------|-------------|-----------|------|
| 🏭 Industry | [`industry/`](industry/) | 28 | UC1-UC28 業界別 AI/ML パターン |
| 🔧 SAP | [`sap/`](sap/) | 1 | SAP/ERP 連携パターン |
| ⚡ FlexCache | [`flexcache/`](flexcache/) | 7 | FlexCache/FlexClone 活用パターン |
| 🤖 GenAI | [`genai/`](genai/) | 2 | Bedrock KB / Agentic AI パターン |
| 🛡️ HA | [`ha/`](ha/) | 1 | 高可用性監視パターン (LifeKeeper) |
| 📡 Event-Driven | [`event-driven/`](event-driven/) | 2 | FPolicy イベント駆動パターン |
| 🌐 Edge | [`edge/`](edge/) | 2 | CDN / エッジ配信 + Amazon IVS VOD 配信パターン |

## パターン選択ガイド

→ [docs/pattern-selection-guide.md](../docs/pattern-selection-guide.md)

## 新規パターン追加

→ [CONTRIBUTING.md](../CONTRIBUTING.md#新規パターンの追加方法)

## 共通アーキテクチャ

全パターンは以下の共通基盤を使用:
- **データアクセス**: `shared/s3ap_helper.py` (FSx for ONTAP S3 AP)
- **可観測性**: `shared/observability.py` (EMF + X-Ray)
- **データ分類**: `shared/data_classification.py`
- **Human Review**: `shared/human_review.py`
- **エラーハンドリング**: `shared/exceptions.py`

各パターンの詳細は個別の README を参照してください。
