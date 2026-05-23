# Partner/SI Delivery Checklist

🌐 **Language / 言語**: [日本語](partner-si-delivery-checklist.md) | [English](partner-si-delivery-checklist.en.md)

## 概要

本チェックリストは、パートナーおよび SI が顧客に FSx for ONTAP S3 Access Points サーバーレスパターンを提案・設計・構築する際の確認項目を整理したものです。

> 📄 **初回提案向け**: [Partner/SI 1 枚要約](partner-si-one-pager.md) — What / When / How / Where を 1 ページで把握

## How to Use This Checklist

1. 最も近いユースケースまたは FlexCache/FlexClone パターンを特定する
2. 関連する Success Metrics を確認する
3. Customer-Ready PoC Plan Template をコピーする
4. Sample Baseline を顧客固有の測定値に置き換える
5. Go / No-Go 基準と次フェーズのオーナーシップを合意する

## 顧客ワークロード分類

### Step 1: データ特性の確認

| 確認項目 | 選択肢 | 設計への影響 |
|---------|--------|------------|
| ワークロードタイプ | SAP 周辺 / ファイルサーバー / 規制対象記録 / AI 分析 / バッチ処理 | UC パターン選択 |
| データプロトコル | NFSv3 / NFSv4.1 / SMB | FPolicy 対応可否（NFSv4.2 は非対応） |
| ファイルサイズ分布 | 小 (<1MB) / 中 (1-100MB) / 大 (100MB-5GB) / 超大 (>5GB) | Lambda メモリ・処理戦略 |
| ファイル数/日 | ~100 / ~1,000 / ~10,000 / 100,000+ | Map 並列度・コスト見積もり |
| データ機密性 | 一般 / 社内機密 / 規制対象 (FISC/HIPAA/GDPR) | Deployment Profile 選択 |

### Step 2: トリガーモード選択

| 確認項目 | 選択肢 | 推奨モード |
|---------|--------|-----------|
| 検知レイテンシ要件 | 時間単位で可 | POLLING |
| | サブ分単位が必要 | EVENT_DRIVEN or HYBRID |
| イベントロス許容度 | 許容可能 | EVENT_DRIVEN (is-mandatory=false) |
| | 許容不可 | EVENT_DRIVEN + Persistent Store or HYBRID |
| 運用複雑性の許容度 | 最小限を希望 | POLLING |
| | 中程度まで可 | EVENT_DRIVEN |
| | 高くても可 | HYBRID |

詳細: [Trigger Mode Decision Guide](trigger-mode-decision-guide.md)

### Step 3: Deployment Profile 選択

| 確認項目 | PoC/Demo | Production | Compliance-sensitive |
|---------|----------|------------|---------------------|
| 目的 | 機能検証・デモ | 本番ワークロード | 規制対応 |
| イベントロス | 許容 | Near-zero | Zero |
| ONTAP バージョン | 9.14.1+ | 9.15.1+ | 9.15.1+ |
| Persistent Store | 不要 | 推奨 | 必須 |
| 冪等性保証 | 不要 | DynamoDB | DynamoDB + S3 Object Lock |
| 監査証跡 | 不要 | 推奨 | 必須 |

詳細: [Deployment Profiles](deployment-profiles.md)

### Step 4: アクセスモデル設計

| レイヤー | 確認項目 | 設計判断 |
|---------|---------|---------|
| AWS IAM | Lambda Role の権限範囲 | ListBucket + GetObject (最小限) or + PutObject |
| S3 AP Policy | リソースポリシーの設定 | Principal 制限 + Condition (OrgID, VPC) |
| VPC Endpoint Policy | VPC 制限の要否 | VPC Origin AP の場合は必須 |
| SCP | Organization レベルの制御 | 規制環境では必須 |
| ONTAP File System | AP に関連付ける identity | 専用ユーザー（root 禁止） |
| セキュリティスタイル | UNIX or NTFS | ボリュームのスタイルに合わせる |

> **重要**: S3 API アクセスは ONTAP ファイルシステム権限をバイパスしません。AWS 側と ONTAP 側の両方で least-privilege を設計する必要があります。

詳細: [S3AP 二段階認可モデル](s3ap-authorization-model.md)

### Step 5: ネットワークモデル

| 構成 | 説明 | 適用シナリオ |
|------|------|------------|
| Single VPC (Private) | FSx + Lambda + S3AP すべて同一 VPC | 最もシンプル、PoC 向け |
| VPC Origin AP | AP を特定 VPC にバインド | セキュリティ要件が高い環境 |
| Internet Origin AP + VPC 外 Lambda | Lambda を VPC 外で実行 | S3 Gateway EP 経由不可の回避 |
| Cross-Account | RAM 共有 or Cross-Account IAM | マルチアカウント環境 |
| Shared Services | 集中監視・ログ集約 | エンタープライズ運用 |

### Step 6: 運用モデル

| 確認項目 | 選択肢 |
|---------|--------|
| 運用主体 | 顧客自社運用 / パートナー運用 / マネージドサービス |
| 監視 | CloudWatch Alarm のみ / ダッシュボード + Alarm / SLO + Runbook |
| 障害対応 | 自動復旧のみ / Runbook 手動対応 / 24/7 オンコール |
| 変更管理 | 手動デプロイ / CI/CD (StackSets) / GitOps |
| コスト管理 | 固定予算 / 従量課金監視 / Cost Anomaly Detection |

### Step 7: 成功基準の定義

| メトリクス | 測定方法 | 目標値（例） |
|-----------|---------|------------|
| 検知レイテンシ | EventBridge event timestamp - file creation time | < 30 秒 (EVENT_DRIVEN) |
| 処理スループット | Files processed / hour | > 1,000 files/hour |
| エラー率 | Failed executions / total executions | < 1% |
| コスト | Monthly AWS bill for the pipeline | < $100/month (PoC) |
| 可用性 | Pipeline uptime | > 99.5% |
| リカバリ時間 | Time to recover from Fargate task restart | < 5 min |
| 監査対応 | Event lineage completeness | 100% (Compliance profile) |

### 各ステップの成果物テンプレート

#### デリバリーフロー全体像

```
Discover → Design → Deploy → Validate → Govern → Operate → Optimize
   │          │        │         │         │        │         │
   ▼          ▼        ▼         ▼         ▼        ▼         ▼
Discovery  Architecture  CFn    PoC      Security  Runbook   Cost
  Note      Diagram    Deploy  Results   Review    Handover  Review
```

| Step | 成果物 | 形式 |
|------|--------|------|
| 1. データ特性 | Discovery Note（データ分類・プロトコル・ファイルプロファイル） | Markdown / Word |
| 2. トリガーモード | Current-state data flow + Target architecture diagram | Draw.io / Mermaid |
| 3. Deployment Profile | Security review checklist（認可モデル確認結果） | Checklist |
| 4. アクセスモデル | IAM + ONTAP permission design document | Markdown |
| 5. ネットワーク | Network architecture diagram + VPC Endpoint decision | Draw.io |
| 6. 運用モデル | Operations handover checklist | Checklist |
| 7. 成功基準 | PoC success criteria + Cost estimate | Spreadsheet |

---

## PoC 実施ガイド

### Phase 1: 環境準備（1-2 日）

1. FSx for ONTAP ファイルシステム確認（既存 or 新規作成）
2. S3 Access Point 作成 + file system identity 設定
3. テストファイル配置（NFS/SMB 経由）
4. S3 AP 経由の ListObjectsV2 / GetObject 動作確認

### Phase 2: POLLING パターン検証（1-2 日）

1. UC テンプレートのデプロイ（CloudFormation）
2. EventBridge Scheduler による定期実行確認
3. Discovery Lambda → Processing Lambda → Output 確認
4. CloudWatch メトリクス・ログ確認

### Phase 3: EVENT_DRIVEN パターン検証（2-3 日）

1. FPolicy Server (Fargate or EC2) デプロイ
2. ONTAP FPolicy 設定（external-engine, policy, scope）
3. NFS/SMB ファイル作成 → SQS → EventBridge 到達確認
4. IP Updater Lambda の動作確認（Fargate の場合）

### Phase 4: 結果評価・次ステップ決定（1 日）

1. レイテンシ・スループット・コストの測定結果整理
2. Deployment Profile の選択（PoC → Production への移行計画）
3. 追加要件の洗い出し（Persistent Store, 冪等性, 監査等）

---

## よくある質問（パートナー向け）

### Q: 既存の NFS/SMB アクセスに影響はありますか？

A: ありません。S3 Access Point をアタッチしても、NFS/SMB 経由の既存アクセスは一切変更されません。AP ポリシーの制限は AP 経由のリクエストにのみ適用されます。

### Q: SAP 環境で使えますか？

A: SAP 周辺ファイル（IDoc エクスポート、帳票出力、BW データ抽出等）の自動処理に適しています。SAP HANA データボリューム自体への S3 AP アタッチは推奨しません（パフォーマンス影響の可能性）。SAP 周辺の共有ファイルストレージに対して使用してください。

### Q: 本番環境で使うには何が必要ですか？

A: [Deployment Profiles](deployment-profiles.md) の Production profile を参照してください。主な追加要件: EC2 static IP or NLB、DynamoDB 冪等性、Full alarm profile、定期ポーリングによる reconciliation。

### Q: イベントロスゼロを保証できますか？

A: ONTAP 9.14.1+ の Persistent Store + is-mandatory=true (ONTAP 9.15.1+) の組み合わせで、テスト済みシナリオ（5-event / 20-event disconnect）ではゼロイベントロスを確認しています。ただし、Persistent Store ボリュームの容量超過時の動作は追加設計が必要です。

### Q: コスト見積もりの目安は？

A: POLLING モード（1 時間間隔、1,000 ファイル/日）で月額 $6-21。EVENT_DRIVEN モードで月額 $32-60（Fargate 24/7 含む）。処理 Lambda のコストはワークロード依存。

---

---

## PoC Proposal Example
<!-- 旧見出し: PoC 提案書への転記例 -->

UC1 (Legal Compliance) を例にした PoC 提案書テンプレート:

```markdown
### PoC Objective
Automate document discovery and audit report generation for legal file shares stored on FSx for ONTAP.

### Success Criteria
- Process 10,000+ files within the agreed batch window (1 hour)
- Generate a standardized audit report after each scheduled run
- Route files requiring manual review to the Human Review queue (target: < 10%)
- Keep processing cost within the agreed PoC budget (< $100/month)
- Achieve > 50% reduction in manual audit preparation effort

### Measurement Method
- Step Functions execution history (file count, duration, success/failure)
- CloudWatch Metrics (FilesProcessed, Duration, ErrorRate)
- Generated report metadata in S3 output bucket
- Human Review queue records in DynamoDB

### PoC Duration
2-4 weeks (Level 1 Sandbox → Level 2 Scheduled)

### Next Phase Criteria
See [Production Readiness Exit Criteria](production-readiness.md#exit-criteria各レベル完了条件)
```

> 上記は UC1 の例です。各 UC の Success Metrics を参照し、顧客の業務要件に合わせてカスタマイズしてください。

### Industry Expansion Guide
<!-- 旧見出し: 横展開ガイド -->

このテンプレートは全 UC に横展開可能です。業界別の例:

| 業界 | 参照 UC | PoC Objective の例 | Typical Stakeholder |
|------|---------|-------------------|-------------------|
| Legal / Compliance | UC1 | ファイルサーバー監査・コンプライアンスレポート自動化 | Legal Ops, Compliance, Audit |
| Public Sector | UC16 | 公文書アーカイブの自動分類・FOIA 対応迅速化 | Digital Transformation Office, Records Management |
| Healthcare | UC5 | DICOM 画像の自動分類・匿名化 | Medical IT, Research, Privacy Office |
| Enterprise Integration | SAP/ERP Adjacent | IDoc/HULFT/EDI ランディングゾーンの自動処理 | Application Owner, Integration Team, ERP Ops |
| Financial Services | UC2, UC14 | 請求書 OCR・保険査定レポート自動化 | Operations, Risk, Compliance |
| Manufacturing | UC3 | IoT ログ・品質検査画像の異常検知 | Plant IT, Quality Engineering, Data Platform |

各 UC の Success Metrics は [UC 別 Success Metrics 一覧](#uc-別-success-metrics-一覧) から参照できます。

---

---

## FlexCache / FlexClone Pattern Mapping

### By Industry

| Industry | Pattern | Customer Question | Recommended First Question |
|----------|---------|-------------------|---------------------------|
| Cross-industry DR / distributed read | FC1 FlexCache Anycast/DR | "Do you need faster distributed read access without a full independent copy?" | "What is your current read latency from remote sites, and what target would justify a caching layer?" |
| Media / VFX | FC2 Dynamic FlexCache Render | "Do you need per-job isolated cache for render workflows?" | "How many concurrent render jobs share the same source data, and what is the job lifecycle?" |
| Enterprise Knowledge / GenAI | FC3 GenAI RAG | "Do you need permission-aware RAG over enterprise files?" | "Which file shares contain the knowledge base, and do access permissions need to be preserved in RAG results?" |
| Automotive / Manufacturing | FC4 Automotive CAE | "Do you need automated solver output analysis?" | "What is the typical solver output size and how quickly must results be available for post-processing?" |
| Life Sciences / Research | FC5 Life Sciences Research | "Do you need research data classification with controlled collaboration?" | "How do you currently share research datasets between teams while maintaining data governance?" |
| Gaming / Build Pipeline | FC6 Gaming Build Pipeline | "Do you need build asset QC and pipeline acceleration?" | "What is your current build pipeline duration and which asset validation steps are bottlenecks?" |

### By Business Outcome

| Outcome | Pattern |
|---------|---------|
| Faster distributed read access | FC1 |
| Per-job isolated cache lifecycle | FC2 |
| Permission-aware enterprise RAG preprocessing | FC3 |
| Engineering workflow acceleration | FC4 |
| Research data classification and controlled collaboration | FC5 |
| Build asset quality control and pipeline acceleration | FC6 |

### FC1 PoC Success Criteria Example

FC1 FlexCache Anycast/DR パターンの PoC 成功基準例:

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Route decision latency | < 500 ms | Step Functions execution duration |
| Cache health detection time | < 30 s | HealthCheck Lambda interval × detection count |
| Read-path recovery time | < 60 s | Time from origin failure to successful cache read |
| False positive failovers (24h test) | 0 | DynamoDB routing table change audit |
| Audit event completeness | 100% | DynamoDB Streams / CloudWatch Logs record count |

> 上記は参考値です。顧客の SLA 要件に合わせて調整してください。詳細は [flexcache-anycast-dr/docs/](../flexcache-anycast-dr/docs/) を参照。

> FlexCache/FlexClone patterns are optional extensions for customers who need distributed read access, dataset branching, cache lifecycle automation, or workload-specific acceleration. Not all customers need these patterns.

---

## Customer-Ready PoC Plan Template

### Sample Baseline

初期検証の参考として、リポジトリには以下の小規模サンプルラン結果が含まれています:

- **UC1 Legal Compliance**: 10 files, 404 ms total (discovery + sequential read)
- **UC16 Government Archives**: 10 documents, 389 ms total

> これらは小規模サンプルランの結果であり、本番性能見積もりではありません。顧客 PoC では、これらの sample baseline を、顧客自身のデータセット、ファイルサイズ、並列度、FSx throughput 構成で取得した測定値に置き換えてください。

```markdown
### Selected Use Case
- UC:
- Business context:
- Stakeholders:
  - Business sponsor: (予算承認・Go/No-Go 判断の最終責任者)
  - Technical owner:
  - Measurement owner: (PoC 成功基準の測定・レポート責任者)
  - Security reviewer:
  - Operations owner:
  - Partner/SI delivery lead:

### Architecture Option
- Trigger mode:
- Deployment profile:
- Output destination:
- FlexCache/FlexClone extension (if applicable):

### Success Metrics
- Outcome:
- Metrics:
- Measurement method:

### Governance Considerations
- Data classification:
- Human review:
- Audit evidence:
- Approval owner:

### Customer-Specific Baseline
- Sample data set:
- Number of files:
- Average file size:
- FSx throughput configuration:
- Concurrency:
- Measured processing time:
- Measured cost:
- Notes / constraints:

### Estimated Effort and Cost Assumptions
- PoC duration:
- Required roles:
- AWS cost assumptions:
- Partner/SI effort:

### Next-Phase Criteria
- Go criteria:
- No-Go criteria:
- Open risks:
- Business sponsor approval:
```

> 上記テンプレートを顧客の業務要件に合わせてカスタマイズし、PoC 合意資料として使用してください。

---

## UC 別 Success Metrics 一覧

各 UC の Success Metrics（Outcome / Metrics / Measurement Method）へのリンク:

| UC | 業界 | Success Metrics |
|----|------|----------------|
| UC1 | 法務・コンプライアンス | [legal-compliance/README.md](../legal-compliance/README.md#success-metrics) |
| UC2 | 金融・保険 (IDP) | [financial-idp/README.md](../financial-idp/README.md#success-metrics) |
| UC3 | 製造業 | [manufacturing-analytics/README.md](../manufacturing-analytics/README.md#success-metrics) |
| UC4 | メディア (VFX) | [media-vfx/README.md](../media-vfx/README.md#success-metrics) |
| UC5 | 医療 (DICOM) | [healthcare-dicom/README.md](../healthcare-dicom/README.md#success-metrics) |
| UC6 | 半導体 / EDA | [semiconductor-eda/README.md](../semiconductor-eda/README.md#success-metrics) |
| UC7 | ゲノミクス | [genomics-pipeline/README.md](../genomics-pipeline/README.md#success-metrics) |
| UC8 | エネルギー | [energy-seismic/README.md](../energy-seismic/README.md#success-metrics) |
| UC9 | 自動運転 / ADAS | [autonomous-driving/README.md](../autonomous-driving/README.md#success-metrics) |
| UC10 | 建設 / BIM | [construction-bim/README.md](../construction-bim/README.md#success-metrics) |
| UC11 | 小売 / EC | [retail-catalog/README.md](../retail-catalog/README.md#success-metrics) |
| UC12 | 物流 | [logistics-ocr/README.md](../logistics-ocr/README.md#success-metrics) |
| UC13 | 教育 / 研究 | [education-research/README.md](../education-research/README.md#success-metrics) |
| UC14 | 保険 | [insurance-claims/README.md](../insurance-claims/README.md#success-metrics) |
| UC15 | 防衛・宇宙 | [defense-satellite/README.md](../defense-satellite/README.md#success-metrics) |
| UC16 | 政府 (FOIA) | [government-archives/README.md](../government-archives/README.md#success-metrics) |
| UC17 | スマートシティ | [smart-city-geospatial/README.md](../smart-city-geospatial/README.md#success-metrics) |

## 参考リンク

- [Trigger Mode Decision Guide](trigger-mode-decision-guide.md)
- [Deployment Profiles](deployment-profiles.md)
- [S3AP 二段階認可モデル](s3ap-authorization-model.md)
- [Enterprise Workload Examples](enterprise-workload-examples.md)
- [S3AP Performance Considerations](s3ap-performance-considerations.md)
- [FSx for ONTAP — SAP HANA 構成ガイド](https://docs.aws.amazon.com/sap/latest/sap-hana/sap-hana-amazon-fsx.html)
