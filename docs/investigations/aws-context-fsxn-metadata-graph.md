# AWS Context × FSx for ONTAP — メタデータ Knowledge Graph 連携調査

- 調査開始日: 2026-06-18
- 対象リリース: AWS Context (Coming soon — AWS Summit NYC 2026 キーノート発表)
- 一次情報: https://aws.amazon.com/blogs/machine-learning/context-intelligence-for-your-data-and-ai-agents-at-scale/
- 関連: Glue Data Catalog Business Context & Semantic Search (Preview)
- 関連: Amazon S3 Annotations (GA — 別途調査済み: s3-annotations-fsxn-compatibility.md)

---

## 1. 調査の目的

AWS Context が GA になった際に、FSx for ONTAP の SVM / ボリューム / 共有 / ACL 構造を Knowledge Graph にマッピングし、Permission-Aware RAG のメタデータレイヤーとして活用できるかを事前に設計する。

### 期待する価値

| 現状の課題 | AWS Context で解決できる可能性 |
|-----------|---------------------------|
| ベクトル検索時のメタデータフィルタは手動設定 | Knowledge Graph がファイル→部門→プロジェクト→担当者の関係を自動マッピング |
| 「このファイルはどのプロジェクトに属するか」の判定が静的 | Graph が利用パターンから関係を学習・推論 |
| 新規ファイル投入時にメタデータ付与が人手依存 | Graph の推論で類似ファイルのメタデータを自動提案 |
| ACL 変更の RAG への反映が遅延する | Identity-aware クエリで IAM/Lake Formation 権限をリアルタイム適用 |
| 部門横断検索で「何が見つからないか」が不透明 | Governed graph が権限外データの存在すら隠す |

---

## 2. AWS Context の技術概要

### 2.1 サービス概要

AWS Context は、組織のデータ全体にわたる関係性を**自動的に Knowledge Graph にマッピング**し、AI エージェントが実行時にガバナンス付きのデータ関係・ビジネスルール・ドメイン知識にアクセスできるようにするサービス。

### 2.2 主要特性

| 特性 | 詳細 |
|------|------|
| 自動関係マッピング | データレイク、DWH、DB、ストリーム間の関係を自動検出 |
| Learning from usage | エージェントのクエリパターンから正しい join パスを学習し、組織全体で共有 |
| Identity-aware | 各クエリが呼び出しユーザーの IAM / Lake Formation 権限を継承 |
| Open format | メタデータを Apache Iceberg 形式で S3 Tables に公開 |
| MCP / Agentic Search API | AgentCore、EKS、任意の MCP 互換フレームワークからクエリ可能 |
| Glue Data Catalog 統合 | 既存の Glue テーブル/ビュー/カラムにビジネスコンテキストを付与 |
| Lake Formation 統合 | 行/列レベルのアクセス制御を Graph クエリに適用 |
| SageMaker Unified Studio 統合 | データサイエンティストの作業環境から直接利用可能 |
| Skill Assets (Glue Preview) | URI ベースでスキル（手順書、ベストプラクティス）を Graph に関連付け |
| サードパーティカタログ接続 | AWS 外のカタログも Graph に取り込み可能（設計意図） |

### 2.3 利用可能状況

| 項目 | 状態 |
|------|------|
| AWS Context 本体 | **Coming soon**（GA 時期未定） |
| Glue Data Catalog Business Context & Semantic Search | **Preview** |
| S3 Annotations | **GA** (2026-06-16) |

---

## 3. FSx for ONTAP メタデータの Graph マッピング設計

### 3.1 FSx ONTAP のメタデータ階層

```
Organization (AWS Account)
  └── FSx for ONTAP File System
       └── Storage Virtual Machine (SVM)
            ├── Volume (ai_knowledge)
            │    ├── Share (SMB: \\svm\ai_knowledge$)
            │    │    ├── Folder: sales/
            │    │    │    ├── NTFS ACL: DOMAIN\SalesGroup (Read/Write)
            │    │    │    └── Files: product-spec-*.pdf, pricing-*.xlsx
            │    │    ├── Folder: finance/
            │    │    │    ├── NTFS ACL: DOMAIN\FinanceGroup (Read/Write)
            │    │    │    └── Files: q3-report.pdf, budget-*.xlsx
            │    │    └── Folder: legal/
            │    │         ├── NTFS ACL: DOMAIN\LegalGroup (Read/Write)
            │    │         └── Files: contract-*.docx, compliance-*.pdf
            │    └── Export Policy (NFS: /ai_knowledge)
            │         └── Rules: 10.0.1.0/24 (rw), 10.0.2.0/24 (ro)
            └── Volume (quick-workspace)
                 └── Share / Export...
```

### 3.2 提案する Graph モデル

```
[FileSystem] --hasSVM--> [SVM]
[SVM] --hasVolume--> [Volume]
[Volume] --hasShare--> [Share]
[Share] --hasFolder--> [Folder]
[Folder] --hasFile--> [File]
[Folder] --hasACL--> [ACLEntry]
[ACLEntry] --grantsAccess--> [ADGroup]
[ADGroup] --hasMember--> [User]
[File] --hasClassification--> [DataClassification]
[File] --belongsToProject--> [Project]
[File] --lastModifiedBy--> [User]
[File] --hasEmbedding--> [VectorChunk] (S3 Vectors)
[Project] --ownedByDepartment--> [Department]
[Department] --hasHead--> [User]
```

### 3.3 Graph マッピングのデータソース

| Graph エンティティ | データソース | 取得方法 |
|------------------|-----------|---------|
| FileSystem, SVM, Volume | FSx API (DescribeFileSystems, DescribeStorageVirtualMachines, DescribeVolumes) | shared/fsx_helper.py |
| Share, Export Policy | ONTAP REST API | shared/ontap_client.py |
| Folder, File | S3 AP ListObjectsV2 | shared/s3ap_helper.py |
| ACL, Owner, Group | ONTAP REST API (security descriptors) | 新規実装要 |
| AD Group, User | AWS Managed Microsoft AD / LDAP query | 新規実装要 |
| DataClassification | shared/data_classification.py | 既存 |
| VectorChunk | S3 Vectors metadata | Bedrock KB or 直接 |
| Project, Department | 組織マスタ（手動 or HR 連携） | 設計要 |

---

## 4. 統合パターン

### Pattern 1: Glue Data Catalog + S3 AP テーブル → AWS Context (短期)

S3 AP 経由のファイル一覧を Glue テーブルとして登録し、AWS Context がそのテーブルを Graph に取り込む。

```
FSx ONTAP Volume
  → S3 Access Point (ListObjectsV2)
  → Glue Crawler (S3 AP をデータソースとして登録)
  → Glue Data Catalog テーブル (ファイルパス、サイズ、更新日時)
  → Business Context 付与 (部門、プロジェクト、分類)
  → AWS Context Knowledge Graph (自動マッピング)
  → Agentic Search API / MCP
```

**利点**: 既存の Glue + S3 AP 統合を活用。Glue Business Context Preview が使える。
**制約**: ファイルの ACL メタデータは Glue テーブルに含まれない（追加処理が必要）。

### Pattern 2: カスタム Ingestion → Neptune → AWS Context (中期)

ONTAP REST API から ACL 含むメタデータを抽出し、Neptune Graph DB に格納。AWS Context が Neptune を参照。

```
ONTAP REST API (volumes, shares, security descriptors)
  → Lambda (定期クロール or FPolicy トリガー)
  → Amazon Neptune (RDF/Property Graph)
  → AWS Context 連携 (サードパーティカタログ接続として)
  → Agentic Search (identity-aware)
```

**利点**: ACL を含む完全な権限 Graph を構築可能。
**制約**: Neptune 追加コスト。AWS Context のサードパーティ連携仕様が未公開。

### Pattern 3: S3 Annotations + Glue Semantic Search (即時可能)

S3 Annotations (GA) を使い、S3 AP 経由のファイルにメタデータ annotation を付与。Glue Semantic Search で検索。

```
FSx ONTAP Volume
  → S3 Access Point
  → S3 Annotations API (PutObjectAnnotation)
    annotation: {"department": "sales", "project": "q3-launch", "classification": "INTERNAL"}
  → S3 Metadata (自動 Iceberg テーブル化)
  → Athena / Glue Semantic Search でクエリ
  → エージェントが Agentic Search で利用
```

**利点**: GA 即利用可能。追加インフラ不要。
**制約**: S3 Annotations の FSx S3 AP 互換性は未検証（別途調査中: s3-annotations-fsxn-compatibility.md）。

---

## 5. Permission-Aware RAG への影響

### 5.1 現在の実装（S3 Vectors メタデータフィルタ方式）

```python
# 現在: ベクトル検索時に metadata filter を手動指定
retrieval_config = {
    "vectorSearchConfiguration": {
        "numberOfResults": 5,
        "filter": {
            "equals": {"key": "department", "value": user_department}
        }
    }
}
```

### 5.2 AWS Context 統合後の将来像

```python
# 将来: AWS Context の identity-aware graph query で権限を自動適用
# エージェントは Context に「このユーザーがアクセスできるファイルのうち、
# Q3 レポートに関連するものは？」と聞くだけ

context_results = aws_context_client.agentic_search(
    query="Q3 financial report related documents",
    # identity は呼び出し元の IAM/Lake Formation から自動継承
)
# → 権限のあるファイルのみが返る（Graph が ACL を解決）
```

### 5.3 移行パス

| フェーズ | 方式 | 権限制御 |
|---------|------|---------|
| 現在 | S3 Vectors + metadata filter | Lambda 側で AD group → filter 変換 |
| 短期 | + Glue Business Context | Glue カラムに ACL メタデータ追加 |
| 中期 | + S3 Annotations | ファイル単位のリッチメタデータ |
| 長期 (AWS Context GA) | Knowledge Graph + identity-aware search | Graph が IAM/LF 権限を自動適用 |

---

## 6. Skill Assets の活用

Glue Data Catalog の **Skill Assets** (Preview) は、URI ベースでドキュメント・手順書をデータアセットに関連付ける機能。

### FSx ONTAP パターンでの活用案

| Skill Asset | 対象 | 内容 |
|-------------|------|------|
| `s3://skills/ontap-query-patterns.md` | FSx ONTAP Glue テーブル | S3 AP 経由のクエリパターン、制約事項 |
| `s3://skills/acl-resolution-guide.md` | ACL メタデータテーブル | NTFS ACL → AD Group 解決の手順 |
| `s3://skills/data-classification-rules.md` | 分類メタデータ | INTERNAL/CUI/REGULATED の判定基準 |
| `s3://skills/ingestion-troubleshooting.md` | KB テーブル | インジェスト失敗時の診断手順 |

エージェントがデータを発見した際に、関連する Skill Asset を自動取得し、「このデータをどう使うべきか」の知識を得る。

---

## 7. Glue Data Catalog Business Context — 即時活用可能な範囲 (Preview)

AWS Context 本体が Coming soon の間に、Glue Data Catalog の Business Context & Semantic Search (Preview) を先行活用する。

### 7.1 実装ステップ

```bash
# 1. Glue Crawler で S3 AP のファイル一覧をテーブル化
aws glue create-crawler \
  --name fsxn-s3ap-metadata-crawler \
  --role GlueCrawlerRole \
  --database-name fsxn_metadata \
  --targets '{"S3Targets": [{"Path": "s3://vol-xxx-ext-s3alias/ai_knowledge/"}]}'

# 2. Business Context の付与（テーブルレベル）
aws glue update-table \
  --database-name fsxn_metadata \
  --table-input '{
    "Name": "ai_knowledge_files",
    "Description": "FSx ONTAP AI Knowledge Base source files (7 departments)",
    "Parameters": {
      "business_context.owner_team": "Data Platform",
      "business_context.sensitivity": "INTERNAL",
      "business_context.use_case": "RAG Knowledge Base source data"
    }
  }'

# 3. Semantic Search でエージェントが発見
# (Preview API — 正確な API 形式は GA 時に確定)
aws glue search-tables \
  --search-text "sales department product specifications" \
  --filters '[{"Key": "business_context.sensitivity", "Value": "INTERNAL"}]'
```

### 7.2 Skill Asset の作成

```bash
# 4. Skill Asset を作成し、Glue テーブルに関連付け
aws glue create-asset \
  --database-name fsxn_metadata \
  --asset-name "fsxn-s3ap-query-guide" \
  --asset-type SKILL \
  --uri "s3://my-skills-bucket/ontap-query-patterns.md" \
  --description "FSx ONTAP S3 AP 経由のデータアクセスパターンとベストプラクティス"
```

---

## 8. コスト見積もり

### 8.1 AWS Context (Coming soon — 価格未公開)

| コンポーネント | 予測 |
|-------------|------|
| Knowledge Graph 維持 | Glue/Neptune 相当の低コスト（推測） |
| Agentic Search クエリ | リクエスト単位課金（推測） |
| Iceberg メタデータ格納 | S3 Tables 料金 |
| Lake Formation 統合 | 既存 LF 料金内 |

### 8.2 Glue Data Catalog Business Context (Preview — 追加コスト小)

| コンポーネント | コスト |
|-------------|-------|
| Glue Crawler 実行 | DPU-hours ($0.44/DPU-hour) — 小規模なら < $1/月 |
| Glue Data Catalog ストレージ | 最初の 100万オブジェクトまで無料 |
| Semantic Search API | Preview 期間は無料（推測） |
| S3 Annotations (GA) | PutObjectAnnotation: $0.001/1000 リクエスト |

### 8.3 Neptune (Pattern 2 — カスタム Graph 構築時)

| コンポーネント | コスト |
|-------------|-------|
| Neptune Serverless | $0.1/NCU-hour (最小 2.5 NCU = $6/日) |
| ストレージ | $0.10/GB-month |
| I/O | $0.20/百万 I/O |

**判定**: Pattern 2 (Neptune) はコスト高のため、AWS Context GA まで Pattern 1 / 3 で先行する方が費用対効果が良い。

---

## 9. FSx ONTAP 固有の考慮事項

### 9.1 ACL メタデータの取得

| 方式 | 利点 | 制約 |
|------|------|------|
| ONTAP REST API (security descriptors) | 正確な NTFS ACL 取得 | Volume 単位の API 呼び出し、大量ファイルでは遅い |
| S3 AP HeadObject | x-amz-meta-* にACLは含まれない | FSx S3 AP は ACL をオブジェクトメタデータとして公開しない |
| FPolicy イベント | リアルタイムで操作ユーザー + パスを取得 | ACL 全体の取得には不十分 |
| AD LDAP クエリ | グループメンバーシップ解決 | 別途 LDAP 接続が必要 |

**推奨**: ONTAP REST API による定期スキャン (1回/日) + FPolicy による差分更新の組み合わせ。

### 9.2 マルチプロトコル環境での Graph 整合性

| プロトコル | ファイルパス形式 | ACL 形式 | Graph への影響 |
|-----------|--------------|---------|-------------|
| SMB | `\\svm\share\folder\file.pdf` | NTFS ACL (SID) | AD Group ベースの関係 |
| NFS | `/vol/folder/file.pdf` | UNIX uid:gid + mode | UID/GID → AD マッピング要 |
| S3 AP | `s3://alias/folder/file.pdf` | IAM + ONTAP dual-layer | IAM ARN + ONTAP identity の結合 |

**Graph 設計**: File ノードに `smb_path`, `nfs_path`, `s3ap_key` の3つのプロパティを持たせ、同一ファイルを複数パスから参照可能にする。

### 9.3 Snapshot / FlexClone と Graph の整合性

- Snapshot 内のファイルは Graph に含めない（読み取り専用の時点スナップショット）
- FlexClone ボリュームは別の Graph サブツリーとして管理
- SnapMirror 先は DR 用であり、通常は Graph に含めない

---

## 10. ロードマップ

| フェーズ | 時期 | アクション | 依存 |
|---------|------|----------|------|
| Phase 0 (即時) | 2026-06 | S3 Annotations × FSx S3 AP 互換性検証を完了 | s3-annotations-fsxn-compatibility.md |
| Phase 1 (短期) | 2026-Q3 | Glue Crawler で S3 AP ファイル一覧をカタログ化 | Glue Business Context Preview |
| Phase 2 (短期) | 2026-Q3 | Skill Assets 作成（S3 AP クエリガイド、ACL ルール） | Skill Assets Preview |
| Phase 3 (中期) | AWS Context Preview 時 | FSx ONTAP メタデータの Graph 投入 PoC | AWS Context Preview 開始 |
| Phase 4 (中期) | AWS Context GA 時 | Identity-aware search と Permission-Aware RAG 統合 | AWS Context GA |
| Phase 5 (長期) | GA + 安定後 | S3 Vectors metadata filter を Graph クエリに移行 | Graph の ACL 解決が十分な精度に |

---

## 11. 判定・次のアクション

### 判定: APPROVE WITH COMMENTS (将来統合候補として追跡)

AWS Context は **Coming soon** のため即時実装はできないが、FSx for ONTAP の Permission-Aware RAG に対して非常に高い親和性を持つ。Identity-aware な Knowledge Graph は、現在手動で行っている ACL → metadata filter 変換を自動化できる可能性がある。

### ブロッカー

1. AWS Context の GA 時期が未定
2. FSx ONTAP / S3 AP が AWS Context のデータソースとしてネイティブ対応するかは不明
3. Identity-aware search が NTFS ACL / AD Group を解決できる深さが不明

### 即時アクション

1. **S3 Annotations × FSx S3 AP 互換性検証を先行完了**（別調査ドキュメント）
2. **Glue Crawler で S3 AP ファイル一覧のカタログ化を PoC** — AWS Context 前段として有用
3. **Graph モデル設計書を維持更新** — AWS Context GA 時に迅速に対応できるよう

### 監視事項

- AWS Context の Preview / GA リリースノート
- Glue Data Catalog Business Context の GA
- Skill Assets の GA
- AWS Context のデータソース一覧（FSx / S3 AP 対応有無）
- Identity-aware search の権限解決粒度（AD Group レベルか、個人レベルか）

---

## 12. 関連ドキュメント

- [S3 Annotations × FSx S3 AP 互換性調査](./s3-annotations-fsxn-compatibility.md)
- [AgentCore Web Search 統合設計](./agentcore-web-search-fsxn-integration.md)
- [DAIS 2026 Agent Bricks 業種別ユースケース](./dais2026-agent-bricks-industry-cases.md)
- [UC29 Self-Service KB Curation](../../genai-kb-selfservice-curation/README.md)
- [UC30 Quick Agentic Workspace](../../genai-quick-agentic-workspace/README.md)
- [Permission-Aware RAG 設計原則](../../docs/comparison-alternatives.md)
