# ドキュメント索引 / Documentation Index

> AGENTS.md から分離した索引。常時ロードする必要はなく、必要なときに引く。

## 作業別のノート（`docs/agent/`）

実際に踏んだ罠と、その作業をするときだけ必要になる規約。AGENTS.md はここへの索引だけを
持ち、ローカルの Kiro は該当する作業をしているときに自動でこれらへ誘導する。

| 作業 | ノート |
|------|--------|
| CloudFormation / SAM、デプロイ失敗 | [pitfalls-cfn-sam](agent/pitfalls-cfn-sam.md) |
| S3 Access Point / ONTAP REST API、AccessDenied | [pitfalls-s3ap-ontap](agent/pitfalls-s3ap-ontap.md) |
| FlexCache / SnapMirror / SVM ピアの作成・削除 | [pitfalls-flexcache-snapmirror](agent/pitfalls-flexcache-snapmirror.md) |
| ボリューム / FlexCache の作成・削除、SMB ローカルユーザー | [pitfalls-volume-lifecycle](agent/pitfalls-volume-lifecycle.md) |
| Active Directory 連携 / SMB / ドメイン参加 | [pitfalls-ad-smb](agent/pitfalls-ad-smb.md) |
| Bedrock / AgentCore / Quick / KNFSD | [pitfalls-genai-edge](agent/pitfalls-genai-edge.md) |
| SnapLock / WORM / Snapshot ロック | [pitfalls-snaplock](agent/pitfalls-snaplock.md) |
| ポータルの CDK / cdk-nag | [portal-cdk-quality-gates](agent/portal-cdk-quality-gates.md) |
| ポータル UI の文字列 / 8 言語 | [portal-i18n](agent/portal-i18n.md) |
| コスト見積り / リソース停止 | [cost-awareness](agent/cost-awareness.md) |
| 依存追加 / Renovate | [dependency-updates](agent/dependency-updates.md) |
| 構成図の作成・再生成・エクスポート | [diagram-regeneration](agent/diagram-regeneration.md) |
| 新パターンの追加と公開判定 | [new-pattern](agent/new-pattern.md) |

## ドキュメント全体

| Document | Purpose |
|----------|---------|
| **[Portal User Guide (EN)](en/portal-user-guide.md)** / [(JA)](ja/portal-user-guide.md) | For someone who signs in and uses the portal: sign-in, browsing, previewing, downloading, and **using it on a phone**. Also in ko / zh-CN / zh-TW / fr / de / es |
| **[Phone walkthrough (EN)](en/portal-mobile-guide.md)** / [(JA)](ja/portal-mobile-guide.md) | The same portal on a phone, one screenshot per step: sign-in, the drawer, row actions, bulk selection, upload, AI, snapshots, language and theme |
| [Demo Mode Guide](demo-mode-guide.md) | Run without FSx for ONTAP |
| [Customization Guide](customization-guide.md) | Adapt patterns to your workload |
| [Portal Implementation Guide](../solutions/amplify-portal/docs/IMPLEMENTATION.md) | Portal architecture, config, component structure, modification log |
| [Admin Demo Guide (EN)](en/admin-resource-management-demo.md) | 26 admin + user demo scenarios |
| [管理者向けリソース管理 デモガイド (JA)](ja/admin-resource-management-demo.md) | 同 26 シナリオの日本語版 |
| [Portal Verification Results (EN)](../solutions/amplify-portal/docs/verification-results.en.md) | What is Live E2E vs live-read vs tests-only vs DemoMode, per feature |
| ポータル検証結果 (JA) — `solutions/amplify-portal/docs/verification-results.md`（gitignore、ローカルのみ） | 機能ごとの検証区分（実機 E2E / 読み取り / テストのみ / DemoMode）。公開しているのは EN 版 |
| [Portal Getting Started](../solutions/amplify-portal/docs/GETTING-STARTED.md) | First deploy of the portal |
| [ONTAP Connection Guide](../solutions/amplify-portal/docs/ONTAP-CONNECTION-GUIDE.md) | VPC, secret and management LIF wiring — start with `make ontap-preflight` when a panel has no data |
| [Handover & Support Guide](../solutions/amplify-portal/docs/portal-handover-guide.md) | After the deploy: the three things to send a user, where every value is managed, and a reverse index from what the user said to what to check |
| [Portal Tabs Guide](../solutions/amplify-portal/docs/portal-tabs-guide.md) | What each sidebar section does |
| [Thumbnail Design (JA)](../solutions/amplify-portal/docs/thumbnail-design.md) / [(EN)](../solutions/amplify-portal/docs/thumbnail-design.en.md) | Why file-list thumbnails are generated in the backend, and what is not generated |
| [Admin Capability Map (JA)](../solutions/amplify-portal/docs/admin-capability-map.md) / [(EN)](../solutions/amplify-portal/docs/admin-capability-map.en.md) | ONTAP System Manager feature coverage |
| [Resource Management Demo Guide (JA)](../solutions/amplify-portal/docs/resource-management-demo-guide.md) / [(EN)](../solutions/amplify-portal/docs/resource-management-demo-guide.en.md) | Panel-by-panel walkthrough |
| [AI Agent Demo Guide (JA)](../solutions/amplify-portal/docs/ai-agent-demo-guide.md) / [(EN)](../solutions/amplify-portal/docs/ai-agent-demo-guide.en.md) | Agent chat, directory and teams |
| [Amplify Gen2 CDK Patterns](../solutions/amplify-portal/docs/amplify-gen2-cdk-patterns.md) | Cross-stack data sources, VPC Lambda deploy cost, escape hatches |
| [Portal Cleanup Guide](../solutions/amplify-portal/docs/cleanup-guide.md) | Tearing the sandbox and its resources down |
| [AppSync Auth Troubleshooting](../solutions/amplify-portal/docs/TROUBLESHOOTING-APPSYNC-AUTH.md) | When Cognito group authorization fails |
| [Cost Calculator](cost-calculator.md) | Estimate monthly costs |
| [Comparison Alternatives](comparison-alternatives.md) | S3 AP vs EFS vs NFS vs DataSync + NFS Read Cache (FlexCache/KNFSD/File Cache) |
| [PoC Go/No-Go Template](poc-go-nogo-template.md) | PoC success criteria |
| [Incident Response Playbook](incident-response-playbook.md) | Security incident handling |
| [S3AP Compatibility Notes](s3ap-compatibility-notes.md) | Known constraints + workarounds |
| [S3AP Performance](s3ap-performance-considerations.md) | Throughput design guidance |
| [Local Testing](local-testing-quick-start.md) | sam local + pytest setup |
| [Partner/SI Checklist](partner-si-delivery-checklist.md) | Customer delivery workflow |
| [Pattern Selection Guide](pattern-selection-guide.md) | Customer situation → recommended UC |
| [ONTAP Integration Notes](ontap-integration-notes.md) | NAS coexistence, identity, data protection, OT |
| [SMB ACL Migration via Backup Operators](smb-acl-migration-backup-operators.md) | Windows file server → FSx for ONTAP with ACLs the copy account cannot read (`SeBackupPrivilege`/`SeRestorePrivilege`, robocopy `/B`, DataSync) |
| [SaaS → FSx for ONTAP 移行と連携 (JA)](ja/saas-to-fsx-ontap-migration.md) | Box / Dropbox / OneDrive / Google Drive / Wasabi 等からの移行。DataSync が扱える群と扱えない群の判定、コラボレーション SaaS のテナント単位 管理者 API、権限・ネイティブ形式・付随データの写像、Nextcloud の `urn:oid` 罠、Bedrock KB による非移行の連携 |
| [SaaS → FSx for ONTAP migration and integration (EN)](en/saas-to-fsx-ontap-migration.md) | English version: the group test for DataSync coverage, tenant-wide admin APIs, the three mappings, and the no-migration path |
| [SnapLock Audit Log Retention FR (JA)](aws-feature-requests/snaplock-audit-log-retention.md) | SL-1〜SL-3: 監査ログ保持期間の指定手段、無言で失敗する `DeleteVolume`、`AuditLogVolume` の表示と実態の不一致 |
| [SnapLock Audit Log Retention FR (EN)](aws-feature-requests/snaplock-audit-log-retention.en.md) | English version of SL-1 to SL-3 |
| [S3 Bucket User Guide](s3-bucket-user-guide.md) | Standard S3 vs FSx for ONTAP S3 AP differences |
| [Bedrock Inference Profiles](bedrock-inference-profiles.md) | Nova/Claude on-demand requirement, IAM (foundation-model + inference-profile), data residency, CI enforcement |
| [AD-Joined SVM S3 AP Prerequisites](en/ad-joined-svm-s3ap-prerequisites.md) | AD DC reachability, Internet-origin AP + VPC-external Lambda, same-account policy |
| [File Portal UI Options](file-portal-amplify-gen2.md) | Amplify Gen2 / Nextcloud / Custom Build comparison, selection guide, implementation roadmap |
| [SaaS Gap Analysis (JA)](aws-feature-requests/file-portal-service-gap.md) | 15 SaaS 比較, AI エージェント動向, プロトコルアクセシビリティ, ペルソナレビュー |
| [SaaS Gap Analysis (EN)](aws-feature-requests/file-portal-service-gap.en.md) | English version of gap matrix + feature requests |
| [Lambda / HealthOmics S3 AP Gaps (JA)](aws-feature-requests/lambda-healthomics-s3ap-gaps.md) | FR-5/6/7: Lambda セルフマネージドコードストレージ・AWS HealthOmics と FSx for ONTAP S3 AP の統合ギャップ、AWS Support 提出用テキスト |
| [Lambda / HealthOmics S3 AP Gaps (EN)](aws-feature-requests/lambda-healthomics-s3ap-gaps.en.md) | English version: integration assessment, requested behavior, workaround architectures |
| [Nextcloud External Storage Setup](nextcloud-external-storage-s3ap.md) | Nextcloud + FSx for ONTAP S3 AP step-by-step configuration |
| [Workshop EDA Integration Guide](workshop-eda-integration.md) | AWS Workshop modules mapped to UC patterns (EDA scenarios, Athena, Glue, AgentCore, Quick) |
| [Quick Desktop MCP Setup](quick-desktop-mcp-setup.md) | AgentCore MCP Gateway + Quick Desktop E2E setup (Import method, IaC, lessons learned) |
| [AgentCore MCP Demo Guide](demo-agentcore-mcp-quick-desktop.md) | E2E demo with screenshots: list_files, read_file, search_files results |
| [AgentCore MCP Remaining Issues](agentcore-mcp-remaining-issues.md) | Known issues tracker: Web UI bug, Desktop persistence, CUSTOM_JWT 403 |
| [AgentCore MCP Tools Reference](agentcore-mcp-tools.md) | Lambda tool definitions (list/read/search), input/output schemas, IAM policy |
| [KNFSD + S3 AP Dual-Path Architecture](knfsd-s3ap-dual-path-architecture.md) | KNFSD File Cache + S3 AP complementary access for EDA/VFX/HPC/Genomics/Finance/Weather/Energy |
| [Tamperproof Snapshot Design](tamperproof-snapshot-design.md) | 3-layer design (volume enable / policy retention / individual lock), irreversibility rules, operation patterns |
| [PoC → Production Guide (EN)](en/portal-poc-to-production.md) | DemoMode → production FSx for ONTAP connectivity migration checklist |
| [PoC → 本番移行ガイド (JA)](ja/portal-poc-to-production.md) | DemoMode から本番接続への移行手順（ネットワーク/認証/シークレット/監査/コスト） |
| [Scaling Guide (EN)](en/portal-scaling-guide.md) | Capacity planning, throughput sharing, QoS, component scaling, growth estimation |
| [スケーリングガイド (JA)](ja/portal-scaling-guide.md) | キャパシティプランニング、スループット共有、QoS、スケーリング特性 |
| [Accessibility Statement](en/portal-accessibility.md) | ARIA, keyboard navigation, screen reader compatibility, WCAG 2.1 AA note |
| [構成図インデックス (JA)](architecture-diagrams.md) | 全 13 図のライト / ダーク両テーマ一覧、命名規則、再生成手順 |
| [Architecture Diagram Index (EN)](architecture-diagrams.en.md) | All 13 figures in light / dark, naming convention, regeneration steps |
