# Bedrock Managed Knowledge Base vs Custom KB + S3 Vectors — 設計判断記録

- 作成日: 2026-06-18
- 対象リリース: Amazon Bedrock Managed Knowledge Base (GA 2026-06-17, AWS Summit NYC)
- ADR ステータス: **Decided — Custom KB + S3 Vectors を継続採用**
- 一次情報: https://aws.amazon.com/blogs/aws/introducing-amazon-bedrock-managed-knowledge-base-for-faster-more-accurate-enterprise-ai-applications/
- What's New: https://aws.amazon.com/about-aws/whats-new/2026/06/amazon-bedrock-managed-knowledge-base/

---

## 1. 背景

AWS Summit NYC 2026 で **Amazon Bedrock Managed Knowledge Base** が GA になった。本プロジェクトでは既に Bedrock Knowledge Base + S3 Vectors を採用済みであるため、Managed KB への移行が必要かを評価する。

---

## 2. 比較表

| 項目 | Managed Knowledge Base | Custom KB + S3 Vectors (現採用) |
|------|----------------------|-------------------------------|
| ベクトルストア | AWS 管理（選択不可、最適化済み） | **S3 Vectors を明示選択** |
| ベクトルストアコスト | 一体型（価格非公開、高め見込み） | **最大 90% 削減**（S3 Vectors 公式ブログ） |
| データコネクタ | S3, SharePoint, Confluence, Google Drive, OneDrive, Web Crawler (6種) | S3 (S3 AP 経由で FSx ONTAP 接続) |
| Smart Parsing | マルチフォーマット自動判別 ✅ | Textract + Lambda で自前実装 |
| Agentic Retriever | マルチステップ・条件分岐検索 ✅ | Step Functions + 条件分岐で自前実装 |
| AgentCore Gateway 統合 | ネイティブ（コネクタターゲット） | MCP ツールとして手動接続 |
| メタデータフィルタリング | 利用可能（範囲未確認） | **完全制御** — S3 Vectors の metadata filter API |
| ACL ベースのフィルタ | 非対応（推測）※NTFS ACL 未サポート | **対応** — department/owner/group を metadata に保持 |
| チャンキング制御 | AWS 管理（カスタマイズ制限あり） | **完全制御** — chunking strategy を自前設計 |
| Embedding モデル選択 | 制限あり（Managed 内で最適化） | **任意選択** — Titan, Cohere, 3rd party |
| インデックス再構築 | AWS 管理（ユーザー制御なし） | **完全制御** — StartIngestionJob を任意タイミング |
| 差分インデックス | データソース同期（間隔は AWS 管理） | **EventBridge Scheduler / FPolicy** で制御 |
| 削除ファイルの即時除外 | AWS 管理タイミング | **FPolicy + 即時削除処理** |
| 権限変更の反映 | 非対応（推測） | **再同期ワークフロー** で対応 |
| リージョン | 主要リージョン（GA） | **任意リージョン** (S3 Vectors GA 済み) |
| コスト透明性 | ブラックボックス | **各コンポーネント個別計測** |
| FSx ONTAP S3 AP 統合 | S3 コネクタ経由で可能 | **検証済み・本番運用実績** |

---

## 3. 判断理由

### S3 Vectors を継続採用する理由（4 点）

#### 3.1 コスト

S3 Vectors は OpenSearch Serverless 比で最大 90% のコスト削減を実現する。Managed KB の一体型価格は公開されていないが、マネージド最適化ストレージのコストは S3 Vectors より高いと推測される。28 UC + FC パターンの PoC 〜 本番展開を考えると、コスト差の累積影響は大きい。

#### 3.2 Permission-Aware RAG の制御

本プロジェクトの核心は **NTFS ACL / AD Group ベースの権限フィルタリング**。Managed KB がこの粒度の metadata filtering をサポートする保証がない。S3 Vectors では metadata に `department`, `owner`, `allowed_groups`, `denied_principals` を自由に付与し、検索時にフィルタできる。

#### 3.3 FSx ONTAP ライフサイクルとの連動

ファイル削除・権限変更・Snapshot 復元など、FSx ONTAP 固有のイベントに対して即座にベクトルインデックスを更新する必要がある。Managed KB のインデックス更新タイミングは AWS 管理であり、FPolicy イベント → 即時反映の要件を満たせない可能性がある。

#### 3.4 Embedding / Chunking の制御

業種別 28 パターンでは、ドキュメント種別ごとに最適なチャンキング戦略が異なる（法務文書 vs 半導体 EDA vs 保険約款）。Managed KB の共通チャンキングでは精度が出ない可能性がある。

---

## 4. Managed KB から取り入れるべきアイデア

Managed KB を採用しないが、その設計思想から以下を Custom KB に取り込む:

| Managed KB の特徴 | Custom KB への適用方法 | 実装先 |
|------------------|---------------------|--------|
| Smart Parsing | Textract + Bedrock Document Processing で同等機能を構築 | shared/smart_parser.py (将来) |
| Agentic Retriever | Step Functions で「検索→判断→条件変更→再検索」のマルチステップパイプライン | 各 UC の workflow ASL |
| AgentCore Gateway コネクタ | Gateway に KB Retrieve API を Lambda ターゲットとして登録 | shared/cfn/ (将来) |
| 自動データ同期 | 既存の Scenario B (Scheduler) + Scenario C (FPolicy) で実現済み | UC29 template.yaml |

---

## 5. どのような場合に再評価するか

以下のいずれかが満たされた場合、Managed KB への移行を再検討する:

1. **Managed KB が S3 Vectors をバックエンドとしてサポートした場合**
   - コスト制御 + Managed 機能の両立が可能になる
2. **Managed KB が NTFS ACL / AD Group ベースの metadata filtering をネイティブサポートした場合**
   - Permission-Aware RAG の制御をマネージドに委ねられる
3. **Managed KB のインデックス更新 API が外部から即時トリガー可能になった場合**
   - FPolicy → 即時反映のワークフローが維持できる
4. **プロジェクトの要件が「厳密な ACL 制御」から「部門レベルのざっくりした分離」に変わった場合**
   - Managed KB の簡便さが上回る

---

## 6. Partner/SI 向けガイダンス

### 顧客に Managed KB を推奨するケース

- 小〜中規模のドキュメント QA（< 10,000 ファイル）
- ACL 制御が不要、またはアプリケーション層で十分
- SharePoint / Confluence / Google Drive が主要データソース
- 最速で RAG PoC を立ち上げたい（1-2 日）
- 運用チームが小さく、ベクトルストアの管理を避けたい

### 顧客に Custom KB + S3 Vectors を推奨するケース

- FSx for ONTAP 上のファイルが主要データソース
- NTFS ACL / AD Group ベースの権限制御が必須
- ファイル削除・権限変更の即時反映が必要
- コスト最適化が重要（大量ファイル、高頻度インデックス）
- 業種固有のチャンキング・パース戦略が必要
- FPolicy イベント駆動のリアルタイム同期が必要

---

## 7. 選び方フローチャート

```
Q1: ACL ベースの権限制御が必要か？
  ├── Yes → Custom KB + S3 Vectors
  └── No → Q2

Q2: FSx for ONTAP が主要データソースか？
  ├── Yes → Q3
  └── No → Q4

Q3: ファイル削除/権限変更の即時反映が必要か？
  ├── Yes → Custom KB + S3 Vectors
  └── No → Managed KB (S3 AP をデータソースに指定)

Q4: コスト最適化が最重要か？
  ├── Yes → Custom KB + S3 Vectors
  └── No → Managed KB
```

---

## 8. 関連ドキュメント

- [AgentCore Web Search 統合設計](./agentcore-web-search-fsxn-integration.md)
- [AWS Context メタデータ Graph 連携](./aws-context-fsxn-metadata-graph.md)
- [S3 Annotations × FSx S3 AP 互換性](./s3-annotations-fsxn-compatibility.md)
- [コスト比較: S3 AP vs 代替アプローチ](../comparison-alternatives.md)
- [S3 Vectors + Bedrock KB: Building cost-effective RAG](https://aws.amazon.com/blogs/machine-learning/building-cost-effective-rag-applications-with-amazon-bedrock-knowledge-bases-and-amazon-s3-vectors/) (AWS Blog)
