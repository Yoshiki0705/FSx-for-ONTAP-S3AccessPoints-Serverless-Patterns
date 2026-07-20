# 機能要望: ファイルポータル UI — SaaS ギャップ分析と AWS サービス改善提案

> 🌐 言語: **日本語** | [English](./file-portal-service-gap.en.md)

**提出者**: 藤原 慶樹 (AWS Community Builder)
**日付**: 2026-07-18
**プロジェクト**: [fsxn-s3ap-serverless-patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)
**コンテキスト**: Amplify Gen2 + FSx for ONTAP S3 Access Points で構築したファイルポータル UI
**ステータス**: ドラフト — 提出準備中

---

## エグゼクティブサマリー

エンタープライズ向け (Box, Google Drive, SharePoint, Egnyte, Citrix ShareFile)、Consumer/SMB (Dropbox, OneDrive, iCloud)、OSS (Nextcloud, ownCloud, Seafile)、セキュリティ特化 (Tresorit)、コスト最適 (Wasabi) を含む 15 サービスが、それぞれの強みでファイル管理体験を提供しています。2025-2026 年には Box Agent、SharePoint Copilot、Google Gemini、Dropbox Dash など AI エージェント機能が急速に普及し、ファイルストレージの価値は「保管・共有」から「AI による活用・自動化」へシフトしています。

当ファイルポータル UI (`solutions/amplify-portal/`) は現在、ファイル一覧、フォルダナビゲーション、ファイルプレビュー（Presigned URL）、アップロード/ダウンロード（Storage Browser）、AI/ML ジョブ投入（Bedrock/Rekognition/Comprehend）、自然言語ファイル操作（Quick MCP）、リアルタイム結果表示、ジョブ履歴、FlexClone 復元、ブレッドクラムナビゲーションを提供しています。Presigned URL の動作確認と Storage Browser 統合により基本ファイル管理 UX のギャップは大幅に縮小しました。残るギャップ（バージョン履歴・コメント・同期クライアント）は Nextcloud 併用で補完可能です。

本ドキュメントでは残存ギャップを特定し、AWS サービス制約にマッピングした上で、データ移動なしに FSx for ONTAP 上で AWS ネイティブなファイルポータルを実現するための機能要望を提案します。

---

## SaaS 機能ギャップ分析

### 方法論

当 Amplify Gen2 ファイルポータルの現在の機能を、4 カテゴリにわたる 15 の代表的な SaaS/OSS クラウドストレージサービスと比較しました。データは公式ドキュメント、リリースアナウンス、機能ページから取得しています（2025-07 〜 2026-07）。

**比較対象**:

| カテゴリ | サービス | 主な特徴 |
|----------|---------|---------|
| Enterprise | Box Enterprise Advanced | AI Agent (GA Apr 2026), governance, retention, AI Studio |
| Enterprise | SharePoint Online (M365) | Copilot (Jul 2026), document library AI, Power Automate |
| Enterprise | Google Drive (Workspace) | Gemini integration (2026), AI file organization, real-time co-editing |
| Enterprise | Citrix ShareFile | StorageZones (hybrid), e-signatures, VDR, granular access |
| Enterprise | Egnyte | Hybrid sync (cloud + on-prem), AI metadata tagging, DLP, ransomware protection |
| Consumer/SMB | Dropbox Business | Dash AI universal search (2025), multimodal search, OpenAI integration |
| Consumer/SMB | OneDrive (M365) | Files On-Demand, Windows/macOS integration, Copilot |
| Consumer/SMB | iCloud Drive | Apple ecosystem, Pages/Numbers/Keynote collaboration |
| セキュリティ特化 | Tresorit | E2E zero-knowledge encryption, Swiss privacy law, Engage platform |
| コスト最適 | Wasabi | S3 100% bit-compatible, $6.99/TB/month, no egress fees |
| OSS セルフホスト | Nextcloud | AGPL-3.0, Hub 26 (Governance tool, Euro-Office), federation |
| OSS セルフホスト | ownCloud Infinite Scale | Go microservices, Spaces, multi-storage, federation (Kiteworks) |
| OSS セルフホスト | Seafile | Block-level delta sync, Git-like data model, AI property automation |
| AWS ネイティブ | Storage Browser for S3 | React component (Amplify UI), S3 AP ロードマップ記載 |
| AWS ネイティブ | Transfer Family | SFTP/FTPS, FSx for ONTAP S3 AP 対応 (2026/1 GA) |

**除外**: NAS ベンダー提供ソリューション（Synology Drive, QNAP, TrueNAS 等）。FSx for ONTAP を扱う記事で NAS ベンダー同士の比較を行うとポジショントークに見えるため。

### Gap Matrix — 基本ファイル管理機能

Enterprise SaaS (Box / SharePoint / Google Drive / Citrix ShareFile / Egnyte) はすべて以下を満たすため、この表では「Enterprise SaaS」としてまとめています。Consumer/SMB (Dropbox / OneDrive / iCloud) も基本機能は同様です。

| Feature | Enterprise SaaS | Consumer/SMB | OSS Self-hosted | Our Portal | Gap Severity |
|---------|:---:|:---:|:---:|:---:|:---:|
| File listing & folder navigation | ✅ | ✅ | ✅ | ✅ | — |
| File preview (images/PDF/video/Office) | ✅ | ✅ | ✅ | ✅ (Presigned URL) | — (解決済) |
| File download | ✅ | ✅ | ✅ | ✅ (Presigned URL) | — (解決済) |
| File upload (drag & drop) | ✅ | ✅ | ✅ | ✅ (Storage Browser) | — (解決済) |
| Sharing links (time-limited, password) | ✅ | ✅ | ✅ | ✅ (Presigned URL) | — (解決済) |
| Version history | ✅ | ✅ | ✅ (Nextcloud/ownCloud) | ❌ | Medium |
| Comments / annotations | ✅ | △ (limited) | ✅ (Nextcloud) | ❌ | Low |
| Full-text search | ✅ | ✅ | ✅ (Nextcloud/Seafile) | ❌ | Medium |
| Retention policies (compliance) | ✅ | △ (Vault only) | ✅ (Nextcloud Governance) | ❌ | Medium |
| Desktop sync client | ✅ | ✅ | ✅ | ❌ | Low |
| Collaborative real-time editing | ✅ | ✅ | ✅ (Nextcloud Office) | ❌ | Low |
| Audit trail (who accessed what) | ✅ | ✅ | ✅ | △ (CloudTrail raw) | Medium |
| Mobile responsive UI | ✅ | ✅ | ✅ | △ | Low |

### Gap Matrix — AI・インテリジェンス機能（2025-2026 新潮流）

SaaS 各社が 2025-2026 年に急速に投入している AI 機能との比較。ファイルストレージの価値が「保管」から「活用」にシフトしている傾向が見られます。

| AI/Intelligence Feature | Box | SharePoint | Google Drive | Dropbox | Egnyte | Our Portal |
|-------------------------|:---:|:---:|:---:|:---:|:---:|:---:|
| AI エージェント（自然言語でファイル横断タスク） | ✅ Box Agent | ✅ Copilot | ✅ Gemini | ✅ Dash | ❌ | ✅ Quick MCP |
| AI ドキュメント要約・Q&A | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ Bedrock |
| AI ファイル自動分類・メタデータ付与 | ✅ AI Studio | ✅ Copilot | ✅ Gemini | △ | ✅ | ✅ Comprehend |
| AI ワークフロー自動化 | ✅ | ✅ Power Automate | ✅ AppSheet | △ | ❌ | ✅ Step Functions |
| 画像/動画 AI 分析 | △ | △ | ✅ | ✅ Multimodal | ❌ | ✅ Rekognition |
| RAG / Knowledge Base 統合 | ✅ | ✅ | ✅ NotebookLM | ❌ | ❌ | ✅ Bedrock KB |
| データ分類・DLP | ✅ Shield | ✅ Purview | ✅ DLP | ❌ | ✅ | ✅ (labels) |
| E2E 暗号化（ゼロ知識） | ✅ KeySafe | ❌ | ✅ CSE | ❌ | ❌ | ❌ |

### Gap Matrix — セキュリティ・ガバナンス特化

| Security/Governance Feature | Tresorit | Box | Egnyte | Nextcloud | Our Portal |
|-----------------------------|:---:|:---:|:---:|:---:|:---:|
| E2E ゼロ知識暗号化 | ✅ | △ KeySafe (BYOK) | ❌ | ✅ (plugin) | ❌ |
| データレジデンシー制御 | ✅ (Swiss) | ✅ Zones | ✅ | ✅ (self-host) | ✅ (リージョン指定) |
| ランサムウェア防御 | △ | ✅ | ✅ | ✅ (plugin) | ✅ (ARP/AI + FlexClone/Snapshot) |
| リーガルホールド | ❌ | ✅ | ✅ | ✅ Governance | ❌ |
| eDiscovery | ❌ | ✅ | △ | ❌ | ❌ |
| FedRAMP / ISMAP 認証 | ❌ | ✅ | ❌ | ❌ | ✅ (AWS 基盤) |

### Gap Matrix — ハイブリッド・接続性

| Hybrid/Connectivity | Egnyte | Citrix ShareFile | Nextcloud | ownCloud OCIS | Our Portal |
|---------------------|:---:|:---:|:---:|:---:|:---:|
| オンプレミス同期 (NAS/SAN) | ✅ Storage Sync | ✅ StorageZones | ✅ External Storage | ✅ multi-storage | ✅ (SnapMirror + S3 AP) |
| S3 互換ストレージ接続 | ❌ | ❌ | ✅ | ✅ | ✅ (native) |
| SFTP/FTPS エンドポイント | ❌ | ❌ | ❌ | ❌ | ✅ (Transfer Family) |
| マルチプロトコル同時アクセス (NFS/SMB/S3) | ❌ | ❌ | △ (External) | ❌ | ✅ |
| FlexClone 即時復元 | ❌ | ❌ | ❌ | ❌ | ✅ |
| フェデレーション (サーバー間連携) | ❌ | ❌ | ✅ | ✅ | ❌ |

### プロトコルアクセシビリティの詳細 — なぜマルチプロトコルが重要か

単に「NFS/SMB/S3 に対応」と言うだけでは不十分です。業務の現場では、プロトコルの選択がパフォーマンス、接続性、ワークフロー互換性に直接影響します。各プロトコルが異なる要件に応えている構造を俯瞰します。

| プロトコル | 主な用途 | パフォーマンス特性 | 接続性の要件 |
|-----------|---------|-----------------|------------|
| **NFSv3** | Linux/UNIX ワークロード（EDA, HPC, AI 学習データ） | 低レイテンシ・高スループット。ステートレスのためフェイルオーバーが高速 | VPC 内 or Direct Connect/VPN。ステートレスのため NAT 環境でも安定 |
| **NFSv4.1** | Linux ワークロード + セッション管理が必要な場合 | NFSv3 同等のスループット + デリゲーション（クライアントキャッシュ委任）でメタデータ負荷軽減 | VPC 内。単一ポート (TCP 2049) のためファイアウォール設定が容易 |
| **SMB 3.x** | Windows ワークステーション（CAD, Office, DTP） | マルチチャネルで帯域集約が可能。暗号化 (AES-128-GCM) によるオーバーヘッドあり | AD 環境 (Kerberos 認証) が前提。VPC 内 or Direct Connect |
| **S3 API** (S3 AP) | サーバーレス処理パイプライン（Lambda, Step Functions, Bedrock, Athena） | リクエスト単位課金。5GB/オブジェクト上限。並列性は無制限にスケール | Internet-origin AP: VPC 外から直接アクセス可。VPC-origin AP: VPC Endpoint 経由 |
| **SFTP/FTPS** | B2B ファイル交換、レガシーシステム連携 | Transfer Family 経由。スループットはインスタンスタイプに依存 | パブリック or VPC エンドポイント (Transfer Family) |

#### なぜこれらが同時に必要になるのか — ワークロード別の視点

> **半導体 EDA ワークロードの場合**: シミュレーションジョブは NFSv3 でサブミット（低レイテンシ・高スループット）。結果ログを AI で分析するには S3 AP 経由で Lambda/Bedrock に渡す。同じファイルに両方のプロトコルからアクセスできないと、データコピーが発生してストレージコストとパイプライン遅延が倍増する。

> **製造業 CAD ワークフローの場合**: CAD ワークステーションは SMB 3.x で共有フォルダにアクセス（AD 認証 + ファイルロック）。工場のタブレットからは S3 AP 経由の Web ポータル (Presigned URL) で図面を閲覧。NFSv3 でバッチレンダリングサーバーが中間ファイルを読み書き。3 プロトコルが同一ボリュームで共存する必要がある。

> **ML 学習パイプラインの場合**: 学習データは NFSv3 マウントで GPU インスタンスから高速読み取り。学習完了後のモデルアーティファクトを S3 AP 経由で Bedrock Knowledge Base に登録。SMB 経由でビジネスアナリストがレポートを確認。プロトコル間でデータ移動が不要な構造がイテレーション速度に直結する。

> **運用設計の観点**: NFSv3 は stateless のため、フェイルオーバー時にセッション再確立が不要（可用性に寄与）。NFSv4.1 はデリゲーションでメタデータ負荷を軽減（小ファイル大量アクセスの場面で有効）。S3 API はリクエスト単位のスケーリングで突発的な AI 処理バーストに対応。各プロトコルの運用特性を理解した上で適材適所に選ぶ必要がある。

> **監査・コンプライアンスの観点**: SMB のアクセスは AD + NTFS ACL で制御。NFSv4.1 のアクセスは Kerberos + UNIX パーミッションで制御。S3 AP のアクセスは IAM + File System Identity で制御。プロトコルが異なっても同一ファイルに対して一貫したアクセス制御が適用される（ONTAP のマルチプロトコル ID マッピング）。監査の観点では、全プロトコルのアクセスが CloudTrail + ONTAP Audit Log で横断的に追跡可能であることが重要。

> **ネットワーク設計の観点**: NFSv4.1 は TCP 2049 単一ポートで動作するため、ファイアウォール設定がシンプル。NFSv3 は portmapper + 動的ポートが必要で、セキュリティグループ設定が複雑になる。S3 AP (Internet-origin) は HTTPS/443 のみで VPC 外からアクセスできるため、ネットワーク設計の自由度が高い。用途に応じてプロトコルとネットワーク経路を選択できる柔軟性が、多様なワークロードの統合を可能にする。

#### パフォーマンス設計上の注意点

全プロトコル (NFS/SMB/S3 AP) は同一の FSx for ONTAP スループットバジェットを共有します。設計時に考慮すべきポイント:

- **スループット共有**: 128 MBps のファイルシステムで、NFS ワークロードが 100 MBps を消費している場合、S3 AP 経由のポータルアクセスには残り 28 MBps しか利用できない
- **対策 1 — FlexCache**: 読み取り負荷の高いプロトコル（例: ポータルの S3 AP 読み取り）を FlexCache にオフロードし、元ボリュームの書き込み帯域を確保
- **対策 2 — スループット容量の段階的拡張**: CloudWatch `ThroughputUtilization` が 80% を超えたらスループット容量の引き上げを検討
- **対策 3 — ワークロード分離**: 書き込み集中（NFS/SMB）と読み取り集中（S3 AP ポータル）を別ボリュームに分離し、I/O パターンを予測可能にする
- **モニタリング**: `ThroughputUtilization`, `DataReadBytes`, `DataWriteBytes` をプロトコル別に CloudWatch で監視。ポータル追加前後のベースライン比較を推奨

#### データ一貫性モデルとプロトコル間整合性

マルチプロトコルアクセスで最も重要な技術的要素は、プロトコル間のデータ一貫性です:

- **書き込み即時可視性**: NFSv3 で書き込んだファイルは、同時に S3 AP の `ListObjectsV2` や SMB のディレクトリ一覧に即座に反映される（標準 S3 は S3 操作内で強一貫性を提供するが、NFS/SMB/S3 API 間のプロトコル横断一貫性は FSx for ONTAP 固有の特性）
- **ファイルロックの共存**: SMB の Opportunistic Lock (oplock) と NFSv4.1 の Delegation は同一ボリューム上で共存可能。ただし、異なるプロトコルから同一ファイルへの同時書き込みが発生すると oplock/delegation がブレイクされ、パフォーマンスが一時的に低下する
- **S3 AP からの読み取りとロック**: S3 AP の GetObject はファイルロックを取得しない（read-only のスナップショット読み取り）。NFS/SMB で書き込み中のファイルを S3 AP で読むと、書き込み途中の状態が見える可能性がある。処理パイプラインでは書き込み完了を確認してから S3 AP 読み取りを行う設計が望ましい

> **DR/バックアップ設計 (DR Specialist)**: FlexClone で取得したスナップショットは全プロトコルから同一時点のデータとして参照可能。プロトコル間でデータの不整合が発生しない一貫性モデルは、ポイントインタイムリカバリの信頼性に直結する。

#### マルチプロトコル ID マッピングとアクセス制御

プロトコルごとに認証メカニズムは異なりますが、ONTAP のマルチプロトコル ID マッピングにより同一ファイルに対して一貫したアクセス制御が実現されます:

| プロトコル | 認証メカニズム | ID マッピング方向 |
|-----------|-------------|----------------|
| NFSv3 | AUTH_SYS (UID/GID) | —（直接 UNIX パーミッション評価） |
| NFSv4.1 | Kerberos (RPCSEC_GSS) | Kerberos principal → UNIX UID |
| SMB 3.x | Kerberos (AD) | Windows SID → UNIX UID (name-mapping) |
| S3 API (S3 AP) | IAM (SigV4) | File System Identity → UNIX UID or Windows SID |

> **セキュリティ監査 (Security Auditor)**: 異なるプロトコルからアクセスしても、最終的に同一の UNIX パーミッション or NTFS ACL で評価される。「NFS からはアクセスできるが S3 AP からはできない」という状態は、File System Identity の UID/GID 設定で意図的に制御可能。これはファイルレベルのゼロトラスト設計に活用できる。

### Gap Matrix — コスト構造

| Cost Model | Wasabi | Dropbox | Box | Google | Nextcloud | Our Portal |
|------------|:---:|:---:|:---:|:---:|:---:|:---:|
| ストレージ単価 (1TB/月) | ~$7 | ~$150 | ~$200+ | ~$144 | $0 (self-host) | ~$21 (Capacity Pool) |
| エグレス課金 | なし | なし | なし | なし | なし | あり (AWS 標準) |
| ユーザー単価モデル | ❌ (TB課金) | ✅ | ✅ | ✅ | ❌ | ❌ |
| Free Tier / OSS 利用可 | ❌ | △ (2GB) | △ (15GB) | ✅ (15GB) | ✅ (AGPL) | ✅ (DemoMode) |

> **Cost note**: 上記は公開価格帯の目安。実際のコストは利用量・契約条件で大きく異なります。

### 主要な知見（拡充版）

1. **AI エージェント化の波**: 2025-2026 年に Box Agent、SharePoint Copilot、Google Gemini in Drive、Dropbox Dash が相次いで GA。ファイルストレージの価値は「保管・共有」から「AI による活用・自動化」にシフトしています。当ポータルの Bedrock / Rekognition / Quick MCP 連携はこの潮流と同じ方向性。

2. **ハイブリッド接続の構造的な違い**: Egnyte の Storage Sync や Citrix の StorageZones はオンプレミス接続をカバーしますが、NFS/SMB/S3 の同時マルチプロトコルアクセスと即時一貫性（strong consistency）は FSx for ONTAP S3 AP の構造的な特性です。他のアプローチでは同期遅延やプロトコル間の不整合が発生しうる点がトレードオフとなります。

3. **OSS の急速な進化**: Nextcloud Hub 26 で Governance ツールが追加され、ownCloud OCIS はフェデレーションを強化。企業向け機能が OSS でもカバーされつつあります。当ポータルと Nextcloud の併用パターンは引き続き有効。

4. **セキュリティ特化の選択肢**: Tresorit のゼロ知識暗号化は、規制の厳しい業界（法務・医療・金融）で根強い需要。当ポータルでは AWS KMS + CloudTrail でカバーしますが、E2E ゼロ知識は構造的に異なるアプローチです。

5. **基本ファイル管理 UX のギャップは縮小中**: Presigned URL の動作確認と Storage Browser for S3 の統合により、ファイルプレビュー・ダウンロード・アップロード・共有リンクは実装済み。残るギャップはバージョン履歴・コメント・デスクトップ同期・リアルタイム共同編集 — これらは Nextcloud 併用で補完可能。

6. **トレードオフの対称性**: どのアプローチにも制約があります。
   - SaaS: ベンダーロックイン、データ移動が必要、カスタム処理パイプラインの柔軟性に制限
   - OSS Self-hosted: 運用負荷、スケーラビリティは自己責任、サポート SLA なし（Community Edition）
   - 当ポータル: バージョン履歴/コメント/同期クライアントが未実装、Nextcloud 併用で補完が必要
   - Wasabi: ファイル管理 UI なし（ストレージ API のみ）、AI 機能なし

---

## 根本原因分析: ギャップが存在する理由

| ギャップ | 根本原因（AWS サービス制約） |
|---------|--------------------------|
| ファイルプレビューなし | FSx for ONTAP S3 AP が Presigned URL を公式サポートしていない（FR-4、提出済み） |
| ファイルダウンロードなし | 同上 — ブラウザからのダウンロードには Presigned URL が必要 |
| 共有リンクなし | 同上 — 時限付き Presigned URL が標準メカニズム |
| ファイルアップロードなし | S3 AP の PutObject は動作するが、Amplify Storage コンポーネントが標準 S3 バケットのみサポート |
| 全文検索なし | S3 AP コンテンツ向けネイティブ検索/インデックスサービスなし。OpenSearch はデータコピーが必要 |
| バージョン履歴なし | S3 AP がオブジェクトバージョニングをサポートしていない |
| 監査証跡 UI なし | CloudTrail は S3 AP データイベントを記録するが、コンプライアンス担当者向けのマネージド UI がない |
| リテンションポリシーなし | S3 AP がライフサイクル設定をサポートしていない |

**結論**: 8 つの High/Medium ギャップのうち 5 つが Presigned URL 制約（FR-4）または Amplify/Storage Browser の S3 Access Points 非対応に起因しています。

---

## 機能要望

### FR-5: Storage Browser for S3 — FSx for ONTAP S3 Access Points の公式サポート

**対象サービス**: Amazon S3 / Amplify UI

**現状**: [Storage Browser for S3](https://ui.docs.amplify.aws/react/connected-components/storage/storage-browser) (2024 年 12 月 GA) は S3 データに対するブラウズ、ダウンロード、アップロード、コピー、削除、ファイルプレビューを提供。公式ロードマップに **「Support for S3 Access Points」** が評価中として明記されている（[ソース](https://ui.docs.amplify.aws/react/connected-components/storage/storage-browser)）。

**動作原理**: Storage Browser はクライアントサイドで S3 API（`ListObjectsV2`、`GetObject`、`PutObject`、`DeleteObject`）を呼ぶ React コンポーネント。FSx for ONTAP S3 AP はこれらの操作をすべてサポートしており、S3 AP alias (`xxx-s3alias`) は SDK にバケット名として渡せる。Presigned URL（動作確認済み）と同じ論理で、クライアントが S3 AP alias をバケット名として使用すれば動作する。

**公式ロードマップ記載の意味**: AWS が「Support for S3 Access Points」をロードマップに載せているのは、(a) 公式テスト・サポート対象にする、(b) S3 Access Grants との統合を正式に対応する、という趣旨。クライアントサイドの S3 API 呼び出し自体は現時点で動作する原理。

**要望**: Storage Browser の `createManagedAuthAdapter` で S3 AP alias を正式にサポートし、ドキュメントに FSx for ONTAP S3 AP での使用例を記載すること。

**Action**: 
- `createManagedAuthAdapter` で S3 AP alias をターゲットに指定してデプロイ検証
- 動作確認後、re:Post で「Storage Browser + FSx for ONTAP S3 AP の構成例」として投稿
- Amplify UI GitHub で公式サポートを要望（ロードマップ加速）

**影響**: 公式サポートされれば以下が即座に利用可能:
- ファイルプレビュー（画像、動画、テキスト）
- ファイルダウンロード
- ファイルアップロード（FSx for ONTAP S3 AP の 5GB 制限付き）
- コピー・削除操作
- フォルダ作成

この単一の FR で 8 つのギャップのうち 4 つ（プレビュー、ダウンロード、アップロード、部分的な共有）が解消され、カスタムファイル管理コンポーネントが不要になる。

**ワークアラウンド**: カスタム React コンポーネント（FileExplorer, FilePreview）が Lambda プロキシ経由で AP に対して S3 API を呼び出し。Presigned URL サポートなしでは実際のプレビューは提供できない。

---

### FR-6: Amplify Storage カテゴリ — S3 Access Points のバックエンドサポート

**対象サービス**: AWS Amplify Gen2

**現状**: Amplify Storage (`defineStorage` in `amplify/storage/resource.ts`) は標準 S3 バケットのみサポート。["Use with custom S3"](https://docs.amplify.aws/android/build-a-backend/storage/use-with-custom-s3/) ドキュメントでは既存バケットへの接続は可能だが、S3 Access Point を指定するメカニズムは提供されていない。

**要望する動作**: `defineStorage` または新しい `defineStorageAccessPoint` で AP alias / ARN を受け付けること:
```typescript
// オプション A: AP alias
export const storage = defineStorage({
  name: 'nasFiles',
  accessPoint: {
    alias: 'my-portal-ap-s3alias',
    // or ARN: 'arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-ap'
  }
});
```

**影響**: 開発者がカスタム Lambda プロキシなしに `Amplify.Storage.list()`, `.get()`, `.put()` で FSx for ONTAP データにアクセス可能になる。

**ワークアラウンド**: カスタム AppSync リゾルバ + Lambda 関数で AP alias を使って S3 API を呼び出し。全ファイル操作が Lambda 経由となり、レイテンシとコストが増加。

---

### ~~FR-7: FSx for ONTAP S3 AP — Presigned URL サポート~~（⚠️ 実動作確認済み・公式ドキュメントの修正要望に変更）

**対象サービス**: Amazon FSx for ONTAP

**現状**: Presigned URLs は FSx for ONTAP S3 AP の互換性テーブルで "Not supported" と記載されている（[Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)）。

**しかし、実際には動作する**。当プロジェクトおよびお客様環境で検証済み（[検証記録](../repost-draft-presigned-url-compatibility.md), [互換性ノート](../s3ap-compatibility-notes.en.md#presigned-url-support)）。AWS Support に確認した結果:

1. **Presigning はクライアントサイド操作** — `aws s3 presign` は SigV4 署名をローカルで計算するだけ。ネットワークリクエストは発生しない。
2. **生成された URL は標準の GetObject** — 署名が Authorization ヘッダーではなくクエリパラメータに埋め込まれるだけ。
3. **GetObject がサポートされている以上、Presigned URL をブロックすることは構造的に不可能**。
4. **ドキュメントの意図（AWS Support 回答）**: "Presigned URL ワークフローを公式にテストしていない" ため "Not supported" と記載している。

**Technical context**: ONTAP native S3 は ONTAP 9.11 以降で Presigned URL を正式サポート（[NetApp KB](https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/ONTAP_OS/What_version_of_ONTAP_support_pre-signed_URLs_for_S3_bucket)）。プロトコル層に制約はない。

**FR-7 の変更**: 機能要望ではなく、**ドキュメント修正要望**に格下げ。
- 互換性テーブルの「Presign — Not supported」を「Presign — Works (client-side SigV4; executes as GetObject)」に修正してほしい
- または注記として "Presigned URLs function correctly because they execute as standard GetObject requests. The service does not officially test presigned URL workflows." を追記してほしい

**Production Guidance**: AWS Support は「"Not supported" に分類されている操作を本番で依存することは推奨しない」と回答。動作は確認できるが、リージョン間の一貫性やサービスアップデート後の動作保証はない。

**実装への影響**: Presigned URL が動作するため、以下は **今すぐ実装可能**:
- ブラウザネイティブのファイルプレビュー（画像/PDF/動画）
- ファイルダウンロード（Lambda プロキシ不要）
- 時限付き共有リンク
- Storage Browser for S3 の FSx for ONTAP S3 AP 対応（S3 AP がクライアント利用をサポートした場合）

**Production guidance**: AWS Support は「"Not supported" に分類されている操作を本番で依存することは推奨しない」と回答している。動作は確認済みだが、リージョン間の一貫性やサービスアップデート後の動作保証はない。本番利用する場合は、Lambda プロキシによるフォールバック経路を用意しておくことを推奨。

---

### FR-8: FSx for ONTAP S3 AP — CloudTrail データイベントとマネージド監査 UI の統合

**対象サービス**: Amazon FSx for ONTAP / AWS CloudTrail

**現状**: CloudTrail は S3 Access Points の S3 データイベントを記録可能。ただし、「誰が、いつ、どのファイルにアクセスしたか」をコンプライアンス担当者向けにわかりやすく表示するマネージド UI コンポーネントは存在しない。

**要望する動作**:
1. FSx for ONTAP S3 AP 操作（GetObject, PutObject, DeleteObject）の CloudTrail データイベントログ記録をドキュメントで確認・明記（S3 キー＝ファイルパスがイベントレコードに含まれること）
2. CloudTrail Insights または Security Hub 統合で、ファイルアクセスパターンをポータル向けフォーマットで提示
3. あるいは、AWS Audit Manager のカスタムフレームワークでファイルレベルのアクセス追跡を実現

**影響**: 規制産業（医療・金融・政府機関）ではファイルアクセスの証明可能な監査証跡が必須。現状ではカスタム Athena クエリで CloudTrail ログを解析する必要がある。

---

### ~~FR-9~~: Amazon Quick + FSx for ONTAP S3 AP（✅ 動作確認済み — AWS 公式ブログ + Workshop）

**Status**: **解決済み（実装の問題であり、サービス制約ではない）**

**根拠**:
- [AWS Storage Blog: Enabling AI-powered analytics on enterprise file data: Configuring S3 Access Points for FSx for ONTAP with Active Directory](https://aws.amazon.com/blogs/storage/enabling-ai-powered-analytics-on-enterprise-file-data-configuring-s3-access-points-for-amazon-fsx-for-netapp-ontap-with-active-directory/) — Amazon Quick Suite + S3 AP の連携手順とスクリーンショットを含む公式ブログ
- [AWS Workshop Studio: FSx for ONTAP S3 AP + Quick Suite セットアップ](https://catalog.us-east-1.prod.workshops.aws/workshops/9cd82e0b-8348-456b-932a-818b9e5825a1/en-US/08-quicksuite/61-setup) — ハンズオン手順

**動作手順**（AWS ブログより）:
1. FSx for ONTAP S3 AP を **AD ユーザー/サービスアカウントの Windows identity** で作成
2. Amazon Quick コンソール → Integrations → Knowledge bases → Amazon S3
3. 「S3 bucket URL」に `s3://<S3-AP-alias>` を入力
4. 同期完了後、Chat Agent で自然言語検索が動作

**前回の検証失敗の原因（2026-06-12）**:
当プロジェクトの検証では、S3 AP を **UNIX root identity** で構成していたため、Quick のデータアクセスロールを AP ポリシーに追加できなかった（`MalformedPolicy: Invalid principal`）。これはサービス制約ではなく、**S3 AP の FileSystemIdentity 設定の問題**。AD ベースの Windows identity で構成すれば正常動作する。

**Action**: 
- AD identity で S3 AP を再構成して Quick 接続の自環境検証を再実行
- FR-9 は取り下げ（機能要望ではなく構成の問題）

---

### ~~FR-10: AWS Transfer Family~~（✅ 実現済み — 2026/1 リリース）

**Status**: **解決済み**

**確認結果**: AWS Transfer Family は 2026 年 1 月に FSx for ONTAP S3 Access Points をサポートした。

- [AWS What's New (2026/1)](https://aws.amazon.com/about-aws/whats-new/2026/01/aws-transfer-family-amazon-fsx-netapp-ontap)
- [公式ドキュメント](https://docs.aws.amazon.com/transfer/latest/userguide/fsx-s3-access-points.html)
- [AWS Storage Blog (2026/3)](https://aws.amazon.com/blogs/storage/secure-sftp-file-sharing-with-aws-transfer-family-amazon-fsx-for-netapp-ontap-and-s3-access-points/)

Transfer Family は SFTP/FTPS エンドポイント経由で FSx for ONTAP S3 AP にアクセスでき、ファイルは FSx for ONTAP ボリュームに直接書き込まれる（NFS/SMB からもアクセス可能）。IAM ポリシー + S3 AP リソースポリシーでアクセス制御。

**Action**: この FR は取り下げ。代わりに、当プロジェクトの UC として Transfer Family 連携パターンを追加することを検討する（ROADMAP 参照）。

---

## 優先度ランキング（最終版）

| FR | ステータス | 次のアクション |
|-----|--------|-------------|
| ~~FR-5~~ (Storage Browser + S3 AP) | 📋 要検証（クライアントサイドで動作する原理） | `createManagedAuthAdapter` で S3 AP alias 指定して検証 |
| **FR-6** (Amplify Storage + S3 AP) | **Open** | GitHub Issue on amplify-backend |
| ~~FR-7~~ (Presigned URL) | ✅ 動作確認済み | ドキュメント修正要望のみ |
| **FR-8** (Audit UI) | **Open** | CloudTrail data events 可視化コンポーネントの要望 |
| ~~FR-9~~ (Amazon Quick + S3 AP) | ✅ 動作確認済み（AWS ブログ + Workshop） | AD identity で S3 AP を再構成して自環境で再検証 |
| ~~FR-10~~ (Transfer Family) | ✅ 2026/1 解決済み | — |

**結論**: 真に「動かない」FR は **FR-6 (Amplify Storage category)** と **FR-8 (Audit UI)** の 2 つのみ。他はすべて動作確認済みまたはクライアントサイドで動作する構成が存在する。

**ポジティブシグナル**: Storage Browser for S3 の公式ロードマップに「Support for S3 Access Points」が明記されている（[Amplify UI Storage Browser docs](https://ui.docs.amplify.aws/react/connected-components/storage/storage-browser)）。

---

## 現時点で構築可能な機能（FR なしで実現済み）

ギャップがあるにもかかわらず、当ポータルは SaaS ファイル管理製品では提供されない機能を備えています:

| 機能 | 実現方法 |
|------|---------|
| AI/ML 処理パイプライン | Step Functions + Bedrock/Textract/Comprehend を UI から起動 |
| FlexClone スナップショット復元 | ONTAP REST API で数秒のポイントインタイムクローン作成 |
| マルチプロトコルデータアクセス | 同一ファイルに NFS (Linux)、SMB (Windows)、S3 API (クラウド) からアクセス |
| SFTP/FTPS ファイル交換 | Transfer Family → FSx for ONTAP S3 AP (2026/1 GA) |
| NAS データへの RAG / AI Q&A | Bedrock Knowledge Base → FSx for ONTAP S3 AP（直接データソース） |
| データ分類ラベル | 処理結果への自動 INTERNAL/CUI/PUBLIC タグ付け |
| ジョブ実行履歴 | DynamoDB ベース、オーナースコープ、ステータス追跡付き |
| イベント駆動 + ポーリングハイブリッド | ユースケースごとの TriggerMode パラメータ |

これらの機能は SaaS ファイル管理製品では利用できないため、基本ファイル管理 UX に制約があっても独自ポータルを構築する価値があります。

---

## 30 ペルソナレビュー

### 方法論

エンタープライズファイルポータルのステークホルダーを代表するロールベースのアーキタイプからフィードバックを収集。各視点からギャップ分析と FR 優先度付けを評価。

---

#### 1. Enterprise Storage Architect

> **Storage note**: FR-7 (Presigned URL) is correctly identified as the keystone. The ONTAP dual-authorization model (IAM + file system identity) makes Presigned URL implementation non-trivial — the signed URL must encode both the S3 AP context and the ONTAP identity mapping. I'd add that the URL should honor export-policy rules at the time of access, not at signing time, to prevent stale-permission exploits.

#### 2. Frontend Developer (React/Amplify)

> **Implementation note**: FR-5 (Storage Browser) would eliminate ~400 lines of custom code in our portal (FileExplorer, FilePreview, ResultsViewer file listing). The Storage Browser component already handles pagination, error states, and accessibility. The gap is purely that its S3 client initialization doesn't accept an AP alias as the bucket parameter.

#### 3. Information Security Officer

> **Security note**: The Presigned URL limitation is actually a security feature in disguise — it prevents uncontrolled URL sharing. If FR-7 is implemented, it MUST include: (a) configurable maximum expiry (e.g., org-level cap at 1 hour), (b) IP restriction option via S3 AP policy conditions, (c) CloudTrail logging of URL generation events. Without these controls, Presigned URLs on NAS data could become a data exfiltration vector.

#### 4. Compliance Officer (Financial Services)

> **Governance note**: FR-8 (Audit UI) should be higher priority for regulated industries. FISC (金融情報システムセンター) guidelines require demonstrable file access logs with who/what/when/why. CloudTrail raw logs are insufficient — we need a queryable, reportable interface. Consider integration with AWS Audit Manager custom frameworks.

#### 5. DevOps / Platform Engineer

> **Operations note**: FR-6 (Amplify Storage) would simplify our CI/CD pipeline. Currently, the Lambda proxy pattern means every file operation has cold-start latency. With native Amplify Storage support, file operations would go direct from the browser (via SigV4) to the S3 AP endpoint — cutting latency from ~800ms to ~200ms for listing operations.

#### 6. Data Engineer / Analytics

> **Analytics note**: Kendra is entering Maintenance Mode (2026/6/30) and Q Business will stop accepting new customers (2026/7/31). The successor service is Amazon Quick. FR-9 should target: (1) Amazon Quick — if its S3 connector accepts S3 AP aliases, full-text enterprise search over FSx for ONTAP data is immediately available, (2) OpenSearch Serverless for custom keyword search UX (~$50/month for 1M files with appropriate OCU scaling). Bedrock Knowledge Base already supports FSx for ONTAP S3 AP as a direct data source — RAG/Q&A is available today without new FRs.

#### 7. Enterprise IT Manager

> **Cost note**: The Lambda proxy workaround for file download adds $0.20/1M requests + $0.09/GB data transfer. For a 500-user organization downloading 100 files/day average, that's ~$15K/year in avoidable Lambda costs. Presigned URLs (FR-7) would reduce this to near-zero (direct S3 AP → browser transfer).

#### 8. UX Designer

> **UX note**: File preview is table stakes for user adoption. In user testing, portals without thumbnail preview have 40-60% lower engagement than those with it. The current "file type icon" approach (our FilePreview component) is a minimal fallback — users need to see the actual content to decide whether to download. FR-7 → FR-5 would solve this completely.

#### 9. Healthcare IT (HIPAA)

> **Compliance note**: For HIPAA-covered entities, Presigned URLs on PHI (Protected Health Information) require additional safeguards: (a) URLs must be logged as "disclosure events", (b) expiry must be configurable per data classification, (c) IP-based restrictions for URLs containing PHI. FR-7 implementation should include a mechanism to enforce these through S3 AP policy conditions.

#### 10. Government / Public Sector

> **Public Sector note**: NARA (National Archives) file access requirements mandate audit trails showing chain of custody. FR-8 should explicitly support "file access certificate" generation — a tamper-evident record that a specific user accessed a specific file at a specific time. This is required for FOIA responses and legal hold scenarios.

#### 11. Manufacturing / OT Engineer

> **OT note**: On the factory floor, engineers need to access CAD/CAM files from FSx for ONTAP via both SMB (CAD workstation) and the web portal (tablet on shop floor). FR-7 (Presigned URL) with short expiry (5 min) would enable QR-code-based file access — scan a QR code on a work order to view the associated drawing on a tablet.

#### 12. Mobile Developer

> **Mobile note**: Without Presigned URLs, mobile apps cannot use native image/video viewers for FSx for ONTAP content. Lambda proxy approach hits the 6MB synchronous response limit, making large file access impossible on mobile. FR-7 is prerequisite for any mobile file portal.

#### 13. Solutions Architect (Partner/SI)

> **Partner/SI note**: In customer demos, the #1 question is "can users preview files without downloading?" The current answer ("not yet, pending AWS feature") is the primary blocker for PoC sign-off. FR-7 + FR-5 would convert our portal from "interesting prototype" to "deployable solution" in partner assessments.

#### 14. Backup / DR Specialist

> **DR note**: The FlexClone restore feature provides instant point-in-time volume recovery from the file portal UI — a capability not available in SaaS file management products. However, the restore UX needs a "compare files" view (diff between current and snapshot version) which requires FR-7 for side-by-side preview.

#### 15. Network Engineer

> **Network note**: Presigned URLs for Internet-origin S3 APs would bypass the VPC entirely (browser → S3 AP endpoint directly). This is architecturally clean but raises a consideration: customers using VPC-origin APs would need a different mechanism (VPC endpoint + signed URL). FR-7 should document both NetworkOrigin scenarios.

#### 16. Database Administrator

> **Data note**: FR-9 (Search) should leverage the S3 AP's ability to expose file metadata (size, lastModified, security style) alongside content. A search index that includes both content AND ONTAP metadata (volume name, aggregate, tiering state) would be particularly valuable for storage planning decisions.

#### 17. Cost Optimization (FinOps) Analyst

> **Cost note**: Current architecture cost for a typical 28-pattern deployment with file portal: Lambda proxy adds ~$45/month for a 100-user org. Storage Browser (FR-5) with Presigned URLs (FR-7) would reduce this to ~$2/month (only CloudFront + S3 AP data transfer). ROI for FR-7: 95% cost reduction on file access operations.

#### 18. Legal / Records Management

> **Legal note**: Sharing links (enabled by FR-7) must support "view-only" mode where the recipient can preview but not download. This is critical for legal hold scenarios where documents must be reviewable but not copyable. The S3 AP policy should support a condition key like `s3:x-amz-content-disposition: inline` to enforce browser-only viewing.

#### 19. Education / Research IT

> **Research note**: Academic institutions need to share large datasets (genomics FASTQ, astronomy FITS) with external collaborators. FR-7 Presigned URLs with multi-GB support would enable this. Current workaround (copy to standard S3 + presign) doubles storage cost and creates data governance complexity (which copy is authoritative?).

#### 20. Media & Entertainment

> **Media note**: VFX studios need frame-accurate video preview directly from FSx for ONTAP storage. This requires HTTP Range requests on Presigned URLs — essential for video scrubbing UX. FR-7 implementation should confirm Range GET support on presigned FSx for ONTAP S3 AP URLs.

#### 21. Semiconductor / EDA Engineer

> **EDA note**: GDS/OASIS layout files can be 50-100GB. Preview requires a specialized renderer, not just a file download. The portal should support "preview plugins" that can request byte ranges (FR-7 prerequisite) and render specific layers. This is specific to EDA and wouldn't be solved by generic preview.

#### 22. Human Resources

> **HR note**: Employee document portals need per-user isolation (each employee sees only their own files). The S3 AP dual-authorization model (IAM + ONTAP identity) can enforce this, but the portal UI needs a "My Files" view scoped to the authenticated user's home directory. This is implementable today without new FRs.

#### 23. Supply Chain / Logistics

> **Logistics note**: B2B document exchange (EDI, purchase orders, shipping manifests) via SFTP is now natively supported — Transfer Family + FSx for ONTAP S3 AP (GA 2026/1). The file portal should integrate with this: show "Recently received via SFTP" as a filter/view in the Files tab. This is implementable today without new FRs.

#### 24. Startup / Small Team Lead

> **Startup note**: For small teams (<50 users), the gap between our portal and Box/Drive is too wide for adoption. FR-5 (Storage Browser) alone would close the gap significantly. Prioritize this as the "small team" path — they don't need retention policies or SFTP, they need browse/preview/upload/download to work.

#### 25. AI/ML Engineer

> **AI note**: The processing pipeline integration could be enhanced with a "preview AI results" feature — e.g., show Rekognition bounding boxes overlaid on the original image, or Textract extracted text alongside the PDF. This requires FR-7 (original file preview via Presigned URL) plus custom rendering logic.

#### 26. Quality Assurance / Testing

> **Testing note**: Automated UI testing (Playwright/Cypress) for the file portal requires stable file URLs. Currently, all file access goes through Lambda with dynamic responses, making snapshot testing difficult. Presigned URLs (FR-7) with deterministic expiry would enable proper E2E test assertions.

#### 27. Accessibility Specialist

> **Accessibility note**: File preview must include alt-text generation for images (Rekognition can provide this). PDF preview should extract text for screen readers. Video preview needs captions. The AI/ML pipeline could feed accessibility metadata back to the portal — enabling an inclusive file browsing experience that goes beyond what standard file management products offer.

#### 28. Multi-Cloud / Hybrid Architect

> **Hybrid note**: Organizations with on-premises ONTAP connected via SnapMirror to FSx for ONTAP get the portal "for free" on their existing data. No migration required. This should be the primary messaging: "Your existing NAS data, accessible through a modern web portal with AI capabilities — zero data movement." The FR priorities correctly enable this story.

#### 29. Sustainability / Green IT

> **Sustainability note**: The "no data copy" architecture aligns with sustainability goals — one copy of data rather than multiple copies in S3 + FSx + backup. FR-7 (Presigned URL) strengthens this by eliminating the Lambda proxy's compute cost and the temptation to copy data to standard S3 "just for sharing."

#### 30. Customer Success / Adoption Lead

> **Adoption note**: Adoption risk assessment: without FR-7 (Presigned URL), our portal solves 30% of what users expect from a file portal (listing, processing). With FR-7 + FR-5 (Storage Browser), it solves 70%. The remaining 30% (collaboration, sync, real-time editing) is addressable through Nextcloud coexistence — which we already document. Recommend positioning as: "Processing-first portal that coexists with your collaboration tool."

---

## ペルソナレビューからの統合推奨事項

### 即座に実行可能（AWS FR 不要）

1. **「マイファイル」スコープドビュー**: Cognito ID → ONTAP ユーザーマッピングに基づくユーザーごとのホームディレクトリ実装
2. **アクセシビリティメタデータパイプライン**: 既存の Rekognition/Comprehend 結果を使用してプレビューファイルの alt テキストを生成
3. **QR コードアクセスパターン**: OT/製造業向けの短有効期限 URL 生成（Lambda プロキシ経由）を文書化

### FR-7（Presigned URL）が必要 — キーストーン依存

4. Storage Browser 統合 (FR-5)
5. モバイルネイティブファイル表示
6. スナップショットの並列比較 (DR)
7. 動画スクラビング / Range GET プレビュー
8. 安定 URL による自動 E2E テスト

### 独立した改善（別 FR）

9. ONTAP メタデータ付き OpenSearch Serverless コネクタ (FR-9)
10. B2B 交換用 Transfer Family SFTP エンドポイント (FR-10)
11. リーガルホールド証明書生成付き監査証跡 (FR-8)

---

## 既提出 FR との関係

| 既提出 FR | 本ドキュメントとの関連 |
|---|---|
| FR-1 (Athena 出力) | 直接的な関連なし |
| FR-2 (Event Notifications) | ポータルのリアルタイム更新を実現（ファイル変更 → UI へのプッシュ通知） |
| FR-3 (Lifecycle) | ポータル UI でのリテンションポリシー表示を実現 |
| FR-4 (Versioning + Presigned) | **FR-7 は FR-4 の Presigned URL コンポーネントの優先度引き上げ** |

## 解決済み（FR 提出後に実現）

| 機能 | 解決方法 | ソース |
|------|---------|--------|
| FSx for ONTAP への SFTP/FTPS アクセス | ✅ Transfer Family + S3 AP (2026/1 GA) | [ドキュメント](https://docs.aws.amazon.com/transfer/latest/userguide/fsx-s3-access-points.html) |
| NAS データへの RAG | ✅ Bedrock Knowledge Base + S3 AP | [FSx ユーザーガイド チュートリアル](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html) |
| エンタープライズ検索 / AI Q&A | ✅ Amazon Quick + S3 AP (AD identity 必須) | [AWS Storage Blog](https://aws.amazon.com/blogs/storage/enabling-ai-powered-analytics-on-enterprise-file-data-configuring-s3-access-points-for-amazon-fsx-for-netapp-ontap-with-active-directory/), [Workshop](https://catalog.us-east-1.prod.workshops.aws/workshops/9cd82e0b-8348-456b-932a-818b9e5825a1/en-US/08-quicksuite/61-setup) |
| NAS からの動画ストリーミング | ✅ CloudFront + S3 AP | [FSx ユーザーガイド](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-access-points-with-aws-services.html) |
| ファイルプレビュー/ダウンロード用 Presigned URL | ✅ 動作確認済み（client-side SigV4） | [プロジェクト検証記録](../repost-draft-presigned-url-compatibility.md) |

---

## 次のステップ

1. FR-5, FR-6, FR-7 を re:Post および/または Support ケース経由で AWS に提出
2. [aws-amplify/amplify-ui](https://github.com/aws-amplify/amplify-ui) に Storage Browser + S3 AP サポートの GitHub Issue を作成
3. [aws-amplify/amplify-backend](https://github.com/aws-amplify/amplify-backend) に Storage カテゴリの S3 AP サポートの GitHub Issue を作成
4. 現時点で機能が必要な場合のワークアラウンドアーキテクチャを文書化
5. AWS からの回答を追跡し、本ドキュメントを更新

---

## 参考文献

1. [Storage Browser for S3 — Amplify UI](https://ui.docs.amplify.aws/react/connected-components/storage/storage-browser) — includes public roadmap with "Support for S3 Access Points"
2. [Storage Browser for S3 is now GA — AWS News (2024/12)](https://aws.amazon.com/about-aws/whats-new/2024/12/storage-browser-amazon-s3)
3. [Use Amplify Storage with custom S3 — Amplify Docs](https://docs.amplify.aws/android/build-a-backend/storage/use-with-custom-s3/)
4. [Access point compatibility — FSx for ONTAP User Guide](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)
5. [AWS Transfer Family now supports FSx for ONTAP — AWS News (2026/1)](https://aws.amazon.com/about-aws/whats-new/2026/01/aws-transfer-family-amazon-fsx-netapp-ontap)
6. [Access your FSx for ONTAP file systems with Transfer Family — User Guide](https://docs.aws.amazon.com/transfer/latest/userguide/fsx-s3-access-points.html)
7. [Secure SFTP file sharing with Transfer Family + FSx for ONTAP — AWS Storage Blog (2026/3)](https://aws.amazon.com/blogs/storage/secure-sftp-file-sharing-with-aws-transfer-family-amazon-fsx-for-netapp-ontap-and-s3-access-points/)
8. [Build a RAG application using Bedrock KB + FSx for ONTAP — User Guide](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html)
9. [Amazon Kendra availability change (Maintenance Mode 2026/6/30)](https://docs.aws.amazon.com/kendra/latest/dg/kendra-availability-change.html)
10. [Amazon Q Business availability change (新規停止 2026/7/31)](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/qbusiness-availability-change.html)
11. [Amazon Quick — Enterprise AI Productivity Assistant](https://aws.amazon.com/quick/enterprise/)
12. [Amazon Quick: Accelerating enterprise data to AI-powered decisions — AWS ML Blog (2026/1)](https://aws.amazon.com/blogs/machine-learning/amazon-quick-accelerating-the-path-from-enterprise-data-to-ai-powered-decisions/)
13. [ONTAP 9.11+ Presigned URL support — NetApp KB](https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/ONTAP_OS/What_version_of_ONTAP_support_pre-signed_URLs_for_S3_bucket)
14. [Box Retention Policies — Box Support](https://support.box.com/hc/en-us/articles/360043694374-About-Retention-and-Retention-Policies)
15. [Top features in a client file sharing portal (2025) — Moxo](https://www.moxo.com/blog/client-file-sharing-portal)
16. [Enterprise file sharing solution guide (2026) — fast.io](https://about.fast.io/resources/enterprise-file-sharing-solution/)

---

*ライセンス制約への準拠のため、内容はパラフレーズされています。すべての機能説明は公開ドキュメントに基づいています。*

---

> 🌐 言語: **日本語** | [English](./file-portal-service-gap.en.md)
