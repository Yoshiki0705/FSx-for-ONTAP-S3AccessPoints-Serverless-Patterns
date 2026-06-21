# DAIS 2026 Agent Bricks 業界事例 — FSx for ONTAP S3 AP パターンへの適用分析

🌐 **Language / 言語**: 日本語 + English (bilingual)

> **Evidence Tier**: Public（Databricks 公式ブログ / DAIS 2026 セッション）
>
> **作成日**: 2026-06-18
>
> **目的**: DAIS 2026 で発表された Agent Bricks 業界事例を、本リポジトリの FSx for ONTAP S3 Access Points サーバーレスパターンへ適用するための分析ドキュメント

---

## 概要 / Overview

DAIS 2026（Data + AI Summit 2026, San Francisco, June 15–18）で発表された 2 つの業界事例が、FSx for ONTAP S3 Access Points 上の非構造化データに対する AI 活用パターンとして参考になる。

Two industry cases presented at DAIS 2026 serve as reference patterns for AI processing of unstructured data stored on FSx for ONTAP via S3 Access Points.

| # | 企業 | 業界 | パターン概要 |
|---|------|------|------------|
| 1 | 7-Eleven | Retail & Consumer Goods | メンテナンス技術者向け GenAI アシスタント |
| 2 | AstraZeneca | Healthcare & Life Sciences | マルチエージェントシステム（10x スケール） |

---

## 1. 7-Eleven: メンテナンス技術者向け GenAI アシスタント

### 1.1 事例概要 / Case Summary


| 項目 | 内容 |
|------|------|
| **課題** | 13,000+ 店舗、数千の設備マニュアル（PDF/スプレッドシート）が共有ドライブに散在。技術者は現場でスマートフォンのみで作業。高離職率と研修機会の不足がナレッジギャップを拡大 |
| **解決策** | Mosaic AI + Agent Bricks + Databricks Hybrid Search による GenAI エージェンティックシステム。Microsoft Teams 経由で技術者に提供 |
| **成果** | 検索時間 −60%、初回修理成功率 +25%、レイテンシ −40%以上 |
| **発表** | DAIS 2026 セッション「AI Agents for the Frontline: 7-Eleven's GenAI Maintenance Assistant」 |
| **登壇者** | Sumedh Datar, Staff Engineer - Manager, 7-Eleven |

**Sources:**
- [DAIS 2026 Session](https://www.databricks.com/dataaisummit/session/ai-agents-frontline-7-elevens-genai-maintenance-assistant)
- [Databricks Community Announcement (2026-01-29)](https://community.databricks.com/t5/announcements/with-databricks-agent-bricks-7-eleven-cuts-search-time-by-60-and/td-p/145689)
- [Databricks Blog](https://www.databricks.com/blog/how-7-eleven-transformed-maintenance-technician-knowledge-access-databricks-agent-bricks)

### 1.2 エージェント機能 / Agent Capabilities

1. **ドキュメント検索・回答**: 関連するメンテナンス文書を検索し、簡潔な回答を生成
2. **画像キャプチャ＆トラブルシューティング**: 設備画像を撮影し、視覚モデルで故障診断
3. **部品情報アクセス**: 設備ブランド別のパーツ情報を検索
4. **インターネット検索**: ガードレール付きの安全なウェブ検索で追加ソリューションを取得

### 1.3 FSx for ONTAP S3 AP 適用アーキテクチャ / Architecture with FSx for ONTAP S3 AP

```
┌─────────────────────────────────────────────────────────────────────┐
│                     7-Eleven Maintenance AI                         │
│                   FSx for ONTAP S3 AP Pattern                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────┐    ┌──────────────┐    ┌────────────────────────┐     │
│  │Technician│───▶│ Teams/Chat   │───▶│  API Gateway + Lambda  │     │
│  │(Mobile)  │    │ Interface    │    │  (Orchestrator)        │     │
│  └──────────┘    └──────────────┘    └──────────┬─────────────┘     │
│                                                  │                  │
│                                    ┌─────────────┼─────────────┐    │
│                                    ▼             ▼             ▼    │
│                         ┌──────────────┐ ┌────────────┐ ┌───────┐   │
│                         │  RAG Agent   │ │Vision Agent│ │Parts  │   │
│                         │(Doc Search)  │ │(Image AI)  │ │Agent  │   │
│                         └──────┬───────┘ └─────┬──────┘ └───┬───┘   │
│                                │               │            │       │
│                    ┌───────────▼───────────────▼────────────▼──┐    │
│                    │        Amazon Bedrock (Nova / Claude)     │    │
│                    │        + Rekognition (Vision)             │    │
│                    └───────────────────┬───────────────────────┘    │
│                                        │                            │
│                    ┌───────────────────▼───────────────────────┐    │
│                    │     Vector Store (OpenSearch Serverless)  │    │
│                    │     - Maintenance manuals (chunked)       │    │
│                    │     - Parts catalogs                      │    │
│                    │     - Troubleshooting guides              │    │
│                    └───────────────────┬───────────────────────┘    │
│                                        │ Ingestion                  │
│                    ┌───────────────────▼───────────────────────┐    │
│                    │       FSx for ONTAP S3 Access Point       │    │
│                    │  ┌─────────────────────────────────────┐  │    │
│                    │  │  SVM: maintenance-docs              │  │    │
│                    │  │  Volume: /manuals (PDF/XLSX/Images) │  │    │
│                    │  │  Volume: /parts-catalogs            │  │    │
│                    │  │  Volume: /troubleshooting-guides    │  │    │
│                    │  │  Protocol: NFS + SMB (dual)         │  │    │
│                    │  └─────────────────────────────────────┘  │    │
│                    └───────────────────────────────────────────┘    │
│                                                                     │
│  NFS/SMB ← バックオフィス（マニュアル更新チーム）                         │
│  S3 AP   ← AI パイプライン（インデックス構築・検索）                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.4 FSx for ONTAP の価値提案 / Value Proposition

| 観点 | FSx for ONTAP S3 AP による付加価値 |
|------|----------------------------------|
| **マルチプロトコルアクセス** | マニュアル更新チームは従来通り NFS/SMB で編集。AI パイプラインは S3 AP で同一データを読み取り。二重コピー不要 |
| **バージョン管理** | ONTAP Snapshot で「いつ時点のマニュアルからインデックスを構築したか」を追跡可能 |
| **大規模ファイル管理** | 13,000+ 店舗 × 数千マニュアル = 数十万ファイル。ONTAP のスケーラビリティで対応 |
| **FlexClone 検証** | 本番マニュアルデータを FlexClone し、RAG 精度評価を本番影響なしで実施 |
| **階層化ストレージ** | 古いマニュアルは Capacity Pool に自動階層化。アクセス時に透過的に取得 |
| **データ保護** | SnapMirror で DR リージョンへレプリケーション。災害時もナレッジアクセス継続 |

### 1.5 既存 UC パターンとの対応 / Mapping to Existing Patterns

| 既存パターン | ディレクトリ | 関連性 |
|-------------|------------|--------|
| **UC22** Transportation Maintenance | `transportation-maintenance/` | ⭐ 最も近い。設備点検画像＋保守レポート分析。7-Eleven の HVAC/オーブン保守は同一パターン |
| **UC11** Retail Catalog | `retail-catalog/` | 業界（小売）が一致。商品カタログ → 設備パーツカタログへの応用 |
| **UC3** Manufacturing Analytics | `manufacturing-analytics/` | 製造設備の分析。店舗設備（HVAC等）への応用 |
| **GenAI RAG Enterprise Files** | `genai-rag-enterprise-files/` | RAG パターンの基盤。ドキュメント検索 + 回答生成 |

**推奨パターン**: UC22 をベースに、マルチモーダル（画像 + テキスト）RAG を拡張。

---

## 2. AstraZeneca: マルチエージェントシステム（10x スケール）

### 2.1 事例概要 / Case Summary


| 項目 | 内容 |
|------|------|
| **課題** | 治療領域横断でコマーシャルチームが医薬品データにアクセスする必要。構造化 + 非構造化データ（臨床文書等）が混在 |
| **解決策** | Supervisor Agent + 治療領域別サブエージェント。構造化データは Genie Spaces（NL-to-SQL）、非構造化文書は Knowledge Assistant。Unity Catalog + Entra ID で権限境界を実施 |
| **成果** | 5 エージェント PoC → 20+ エージェント本番。50+ エージェントに向けた設計。MCP による外部ツール統合 |
| **発表** | DAIS 2026 セッション「AstraZeneca's Multi-Agent System: Lessons Scaling Agents by 10x With Agent Bricks」 |
| **登壇者** | Brian Burke (Senior Director, Platform Engineering, AstraZeneca), Homayoon Moradi (Staff AI Engineer, Databricks) |

**Sources:**
- [DAIS 2026 Session](https://www.databricks.com/dataaisummit/session/astrazenecas-multi-agent-system-lessons-scaling-agents-10x-agent-bricks)
- [Agent Bricks DAIS 2026 Blog](https://www.databricks.com/blog/agent-bricks-dais-2026)

### 2.2 アーキテクチャコンポーネント / Architecture Components

セッションで言及されたキーコンポーネント:

| コンポーネント | 役割 |
|--------------|------|
| **Multi-Agent Supervisor** | オーケストレーション。リクエストを適切なサブエージェントにルーティング |
| **Genie Spaces** | 構造化データへの自然言語クエリ（NL-to-SQL） |
| **Knowledge Assistant** | 非構造化ドキュメントの検索・回答生成 |
| **Unity Catalog** | 行/列レベルのセキュリティ。Entra ID 連携で権限境界を実施 |
| **MCP** | 外部ツール統合のためのプロトコル |
| **MLflow** | エージェントのトレーシング・評価 |

### 2.3 セッションの主要教訓 / Key Lessons from the Session

1. **権限保持設計** (Permission-preserving design) — エージェントがデータにアクセスする際、ユーザー権限を保持
2. **Supervisor 分割 vs エージェント追加** — スケール時の判断基準
3. **Human-in-the-loop テスト** — エージェント品質保証
4. **データ品質の重要性** — 技術に関係なく、不良データはエージェントを壊す
5. **エージェントオーナーシップの組織課題** — 誰がエージェントを所有・運用するか

### 2.4 FSx for ONTAP S3 AP 適用アーキテクチャ / Architecture with FSx for ONTAP S3 AP

```
┌─────────────────────────────────────────────────────────────────────────┐
│              AstraZeneca-style Multi-Agent System                       │
│            FSx for ONTAP S3 AP Pattern (AWS-native)                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐    ┌────────────────────────────────────────────┐     │
│  │ Commercial   │───▶│        Supervisor Agent (Bedrock Agent)    │     │
│  │ Team User    │    │  - Route to therapeutic area sub-agents    │     │
│  │ (Cognito/    │    │  - Enforce user permission context         │     │
│  │  IdC auth)   │    └──────────┬──────────┬──────────┬───────────┘     │
│  └──────────────┘               │          │          │                 │
│                        ┌────────▼───┐ ┌────▼────┐ ┌───▼──────────┐      │
│                        │Oncology    │ │Cardio   │ │Respiratory   │      │
│                        │Sub-Agent   │ │Sub-Agent│ │Sub-Agent     │      │
│                        └─────┬──────┘ └────┬────┘ └──────┬───────┘      │
│                              │             │             │              │
│              ┌───────────────▼─────────────▼─────────────▼─────────┐    │
│              │                                                     │    │
│              │  ┌──────────────────┐  ┌─────────────────────────┐  │    │
│              │  │ Structured Data  │  │  Unstructured Documents │  │    │
│              │  │ (Athena/Redshift │  │  (RAG via OpenSearch    │  │    │
│              │  │  NL-to-SQL)      │  │   Serverless + Bedrock) │  │    │
│              │  └──────────────────┘  └────────────┬────────────┘  │    │
│              │                                     │               │    │
│              └─────────────────────────────────────┼───────────────┘    │
│                                                    │ Ingestion          │
│              ┌─────────────────────────────────────▼───────────────┐    │
│              │          FSx for ONTAP S3 Access Point              │    │
│              │  ┌───────────────────────────────────────────────┐  │    │
│              │  │  SVM: pharma-research                         │  │    │
│              │  │  Volume: /clinical-docs    (PDFs, protocols)  │  │    │
│              │  │  Volume: /regulatory-docs  (submissions)      │  │    │
│              │  │  Volume: /medical-affairs  (publications)     │  │    │
│              │  │  Volume: /commercial-data  (market access)    │  │    │
│              │  │                                               │  │    │
│              │  │  ACL: AD group per therapeutic area           │  │    │
│              │  │  Protocol: SMB + NFS (researchers/analysts)   │  │    │
│              │  └───────────────────────────────────────────────┘  │    │
│              └─────────────────────────────────────────────────────┘    │
│                                                                         │
│  SMB ← リサーチャー/レギュラトリーチーム（文書作成・編集）                      │
│  S3 AP ← AI パイプライン（インデックス構築・RAG 検索）                        │
│  ACL  → ベクトル DB メタデータ（権限フィルタとして伝播）                       │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.5 FSx for ONTAP の価値提案 / Value Proposition

| 観点 | FSx for ONTAP S3 AP による付加価値 |
|------|----------------------------------|
| **権限保持 RAG** | ONTAP の NTFS ACL / AD グループが治療領域単位のアクセス制御に直結。S3 AP 経由のインデックス構築時に ACL メタデータを抽出し、ベクトル DB に保存。検索時にユーザー権限でフィルタ |
| **大規模文書管理** | 40万+ 臨床文書を NAS ファイルシステムで管理。S3 AP でバッチ処理パイプラインがアクセス |
| **マルチプロトコル共存** | リサーチャーは SMB/NFS で日常作業。AI パイプラインは S3 AP で並行アクセス。データ移動なし |
| **Snapshot 一貫性** | 「この治験データのこのバージョンから生成された回答」を Snapshot タイムスタンプで追跡 |
| **FlexClone 分離** | 各治療領域のデータを FlexClone し、サブエージェント開発・テストを本番影響なしで実施 |
| **コンプライアンス** | GxP 環境での監査証跡。誰がいつどの文書にアクセスしたかを ONTAP 監査ログ + S3 AP CloudTrail で記録 |
| **スケーラビリティ** | 5 → 20 → 50+ エージェントへのスケール。各エージェントが S3 AP 経由で並行読み取り。共有帯域幅は ONTAP が管理 |

### 2.6 既存 UC パターンとの対応 / Mapping to Existing Patterns

| 既存パターン | ディレクトリ | 関連性 |
|-------------|------------|--------|
| **UC7** Life Sciences Research | `life-sciences-research/` | ⭐ 最も近い。臨床文書の AI 分析パターン |
| **UC5** Healthcare DICOM | `healthcare-dicom/` | 医療画像処理。DICOM + 臨床レポートの組み合わせ |
| **UC28** Chemical SDS Management | `chemical-sds-management/` | ラボドキュメント管理。創薬研究文書への応用 |
| **GenAI RAG Enterprise Files** | `genai-rag-enterprise-files/` | RAG 基盤パターン。権限付き文書検索 |
| **GenAI KB Self-Service Curation** | `genai-kb-selfservice-curation/` | ナレッジベースのセルフサービスキュレーション |

**推奨パターン**: UC7 をベースに、Multi-Agent Supervisor パターン（Step Functions による治療領域別ルーティング）を追加。

---

## 3. 統合対応マップ / Consolidated Mapping


### 3.1 業界 × パターン対応表 / Industry × Pattern Matrix

| DAIS 事例 | AWS Industries 分類 | 本リポジトリの対応 UC | 主要技術要素 |
|-----------|-------------------|---------------------|-------------|
| 7-Eleven | Retail & Consumer Goods | UC22 (Transportation Maintenance) + UC11 (Retail Catalog) | Hybrid Search, Vision Model, RAG, Mobile-first UX |
| AstraZeneca | Healthcare & Life Sciences | UC7 (Life Sciences Research) + UC5 (Healthcare DICOM) | Multi-Agent Supervisor, Permission-aware RAG, NL-to-SQL |

### 3.2 技術パターン対応表 / Technology Pattern Mapping

| DAIS 事例の技術 | 本リポジトリの AWS-native 対応 |
|----------------|------------------------------|
| Agent Bricks | Amazon Bedrock Agents + Step Functions |
| Databricks Hybrid Search | Amazon OpenSearch Serverless (Hybrid: vector + keyword) |
| Genie Spaces (NL-to-SQL) | Amazon Athena + Bedrock (SQL generation prompt) |
| Knowledge Assistant | Bedrock Knowledge Bases / Custom RAG with OpenSearch |
| Unity Catalog (permissions) | S3 AP Policy + ONTAP ACL metadata in vector store |
| Entra ID | AWS IAM Identity Center + Microsoft Entra ID federation |
| MLflow (tracing) | AWS X-Ray + CloudWatch Logs Insights |
| MCP (tool integration) | Bedrock Agent Action Groups / Lambda tool functions |
| Vision Models | Amazon Rekognition + Bedrock (multimodal) |

### 3.3 共通アーキテクチャパターン / Common Architecture Pattern

両事例に共通する設計原則を、本リポジトリのパターンにマッピング:

| 設計原則 | 7-Eleven | AstraZeneca | 本リポジトリの実装 |
|---------|----------|-------------|-----------------|
| 非構造化データの AI アクセス | 共有ドライブ上の PDF/XLS | NAS 上の臨床文書 | FSx ONTAP S3 AP (`S3ApHelper`) |
| 権限保持 | — (言及なし) | Unity Catalog + Entra ID | ONTAP ACL → vector metadata filter |
| マルチモーダル | 画像 + テキスト | テキスト中心 | Rekognition + Bedrock multimodal |
| エージェント分割 | 機能別 (検索/画像/部品/Web) | 治療領域別 | Step Functions parallel branches |
| 評価・品質保証 | 3-step prompt framework | Human-in-the-loop | `shared/human_review.py` |
| スケーラビリティ | 13,000 店舗 | 50+ エージェント | EventBridge + Lambda concurrency |

---

## 4. 実装提案 / Implementation Proposals

### 4.1 提案 A: Retail Maintenance AI（7-Eleven パターン）


**対応 UC**: UC22 (`transportation-maintenance/`) の拡張として実装可能

**追加要素**:

```yaml
# template.yaml への追加パラメータ案
Parameters:
  EnableMultimodalVision:
    Type: String
    Default: "true"
    AllowedValues: ["true", "false"]
    Description: Enable image-based troubleshooting (Rekognition + Bedrock multimodal)
  
  EnablePartsLookup:
    Type: String
    Default: "true"
    AllowedValues: ["true", "false"]
    Description: Enable structured parts catalog search
  
  ChatIntegration:
    Type: String
    Default: "API"
    AllowedValues: ["API", "TEAMS", "SLACK"]
    Description: Chat platform integration target
```

**Step Functions ワークフロー**:

```
Start → ClassifyQuery
  ├── DocumentSearch → RAG retrieval → GenerateAnswer
  ├── ImageAnalysis → Rekognition + Bedrock → TroubleshootingGuide
  ├── PartsLookup → Athena query → PartsResult
  └── WebSearch (guarded) → Bedrock summarize → SafeAnswer
→ MergeResults → FormatResponse → End
```

### 4.2 提案 B: Pharma Multi-Agent System（AstraZeneca パターン）

**対応 UC**: UC7 (`life-sciences-research/`) の拡張として実装可能

**追加要素**:

```yaml
# template.yaml への追加パラメータ案
Parameters:
  TherapeuticAreas:
    Type: CommaDelimitedList
    Default: "oncology,cardiology,respiratory"
    Description: Comma-separated list of therapeutic area sub-agents

  EnablePermissionAwareRAG:
    Type: String
    Default: "true"
    AllowedValues: ["true", "false"]
    Description: Enable ACL-based retrieval filtering

  SupervisorModel:
    Type: String
    Default: "amazon.nova-pro-v1:0"
    Description: Foundation model for supervisor agent routing
```

**Step Functions ワークフロー**:

```
Start → AuthenticateUser → ExtractPermissions
  → SupervisorClassify (determine therapeutic area)
    ├── OncologyAgent → [StructuredQuery | DocumentRAG] → OncologyResult
    ├── CardioAgent → [StructuredQuery | DocumentRAG] → CardioResult
    └── RespiratoryAgent → [StructuredQuery | DocumentRAG] → RespiratoryResult
  → MergeResults → ApplyPermissionFilter → GenerateResponse
  → AuditLog → End
```

**権限フロー**:

```
User (Entra ID / Cognito) 
  → Extract AD groups + therapeutic area membership
  → Pass as metadata filter to OpenSearch query
  → Post-retrieval: re-verify chunk ACL vs user principal
  → Only authorized chunks reach Bedrock prompt
```

---

## 5. 本リポジトリへの取り込み方針 / Integration Plan


### 5.1 短期（既存パターンの拡張）

| アクション | 対象 | 内容 |
|-----------|------|------|
| UC22 README 更新 | `transportation-maintenance/README.md` | 7-Eleven 事例を「業界参考事例」セクションに追加（public evidence tier） |
| UC7 README 更新 | `life-sciences-research/README.md` | AstraZeneca 事例を「業界参考事例」セクションに追加 |
| パターン選択ガイド更新 | `docs/pattern-selection-guide.md` | マルチモーダル保守 AI、マルチエージェント製薬 AI を選択肢に追加 |
| 業界カバレッジマップ更新 | `docs/industry-coverage-map.md` | DAIS 2026 事例参照を注記として追加 |

### 5.2 中期（新パターン候補）

| 候補パターン | 概要 | 前提条件 |
|-------------|------|---------|
| `retail-maintenance-ai/` | マルチモーダル設備保守アシスタント（UC22 の小売特化版） | UC22 の拡張でカバーできない場合のみ独立パターン化 |
| `pharma-multi-agent/` | 権限保持マルチエージェント（UC7 の製薬特化版） | Bedrock Agents の Multi-Agent Supervisor GA 後に検討 |

### 5.3 注意事項 / Caveats

> **Distinction Discipline（区別の規律）**:
>
> - 7-Eleven と AstraZeneca の事例は **Databricks プラットフォーム上で構築** されたものである
> - 本ドキュメントは、同等の課題を **AWS-native サービス + FSx for ONTAP S3 AP** で解決するアーキテクチャパターンを提案するものである
> - Databricks Agent Bricks と AWS Bedrock Agents は異なるプラットフォームであり、本ドキュメントは「同一課題に対する別アプローチ」として位置づける
> - 「Databricks の代替」や「競合ツールとの比較」という位置づけではなく、「顧客課題起点で、AWS-native 実装パターンを提示する」という right-tool-for-the-job フレーミングを維持する

---

## 6. 参考リンク / References

| # | タイトル | URL | 種別 |
|---|---------|-----|------|
| 1 | AI Agents for the Frontline: 7-Eleven's GenAI Maintenance Assistant (DAIS 2026 Session) | [Link](https://www.databricks.com/dataaisummit/session/ai-agents-frontline-7-elevens-genai-maintenance-assistant) | Session |
| 2 | How 7-Eleven Transformed Maintenance Technician Knowledge Access (Blog) | [Link](https://www.databricks.com/blog/how-7-eleven-transformed-maintenance-technician-knowledge-access-databricks-agent-bricks) | Blog |
| 3 | Databricks Community: 7-Eleven Cuts Search Time by 60% | [Link](https://community.databricks.com/t5/announcements/with-databricks-agent-bricks-7-eleven-cuts-search-time-by-60-and/td-p/145689) | Community |
| 4 | AstraZeneca's Multi-Agent System (DAIS 2026 Session) | [Link](https://www.databricks.com/dataaisummit/session/astrazenecas-multi-agent-system-lessons-scaling-agents-10x-agent-bricks) | Session |
| 5 | Agent Bricks: Data + AI Summit 2026 (Blog) | [Link](https://www.databricks.com/blog/agent-bricks-dais-2026) | Blog |

---

## 更新履歴 / Changelog

| 日付 | 変更内容 |
|------|---------|
| 2026-06-18 | 初版作成 — DAIS 2026 事例分析、FSx for ONTAP S3 AP パターンへの適用提案 |
