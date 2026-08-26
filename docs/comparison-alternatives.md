# 代替アーキテクチャ比較 — S3 AP vs EFS vs NFS マウント vs DataSync

## 概要

「なぜ FSx for ONTAP S3 Access Points + Lambda なのか？」という質問に対する
技術的な比較資料です。

## 比較マトリクス

| 観点 | FSx for ONTAP S3 AP + Lambda | EFS + Lambda | EC2 NFS マウント | DataSync → S3 + Lambda |
|------|:---:|:---:|:---:|:---:|
| **データ移動** | なし（in-place 読み取り） | なし（直接マウント） | なし（直接マウント） | あり（コピー） |
| **サーバーレス** | ✅ 完全サーバーレス | ✅ Lambda + EFS | ❌ EC2 必要 | ✅ Lambda (S3 側) |
| **NTFS ACL 保持** | ✅ ONTAP REST API で取得 | ❌ POSIX のみ | ✅ NFS/SMB 経由 | ❌ S3 にコピー時に喪失 |
| **スケーラビリティ** | ✅ Lambda 並列 | ✅ Lambda 並列 | ⚠️ EC2 スケール必要 | ✅ Lambda 並列 |
| **レイテンシ (読み取り)** | 数十 ms (S3 API) | 約 1 ms | サブ ms (SSD) / 数十 ms (Capacity Pool) | N/A (非同期) |
| **レイテンシ (書き込み)** | 数十 ms (S3 API) | 約 2.7 ms (Regional) / 約 1.6 ms (One Zone) | サブ ms (SSD) | N/A (非同期) |
| **スループット** | FSx 帯域共有 | EFS バースト/プロビジョンド | FSx 帯域共有 | DataSync 帯域 |
| **コスト (処理側)** | Lambda 従量課金 | Lambda + EFS 従量 | EC2 常時稼働 | Lambda 従量課金 |
| **コスト (ストレージ)** | FSx for ONTAP (既存) | EFS 追加 | FSx for ONTAP (既存) | S3 追加 |
| **VPC 依存** | NetworkOrigin による | ✅ VPC 必須 | ✅ VPC 必須 | ❌ 不要 (S3 側) |
| **イベント駆動** | EventBridge Scheduler ポーリング（FPolicy は AP 経由の操作を検知しない。実測 2026-08-26 / ONTAP 9.18.1P3D1） | S3 Event (コピー後) | inotify/FPolicy | S3 Event Notifications |
| **マルチプロトコル** | NFS + SMB + S3 | NFS のみ | NFS or SMB | S3 のみ (コピー後) |
| **データ鮮度** | リアルタイム | リアルタイム | リアルタイム | 同期遅延あり |
| **運用複雑性** | 中 | 低 | 高 | 中 |

## 選択ガイド

### FSx for ONTAP S3 AP + Lambda を選ぶべき場合

- ✅ 既に FSx for ONTAP を使用している
- ✅ NTFS ACL / AD 統合が必要
- ✅ データを移動したくない（規制要件、データ主権）
- ✅ NFS/SMB ユーザーと AI 処理結果を同じボリュームで共有したい
- ✅ サーバーレスでスケーラブルな処理が必要
- ✅ FlexCache によるマルチリージョン/マルチサイト対応が必要

### EFS + Lambda を選ぶべき場合

- ✅ POSIX 権限で十分（NTFS ACL 不要）
- ✅ **読み取り**が約 1 ms で足りる（書き込みは Regional で約 2.7 ms。小さい書き込みが多い場合はこの値で評価してください）
- ✅ シンプルな構成を優先
- ✅ FSx for ONTAP を使用していない
- ⚠️ 書き込みレイテンシを詰めたい場合は One Zone（約 1.6 ms）が選択肢ですが、AZ 冗長性とのトレードオフです

### EC2 NFS マウントを選ぶべき場合

- ✅ 長時間実行のバッチ処理（Lambda 15 分制限を超える）
- ✅ 大量のメモリ/GPU が必要
- ✅ 既存の EC2 ベースパイプラインがある
- ✅ ファイルシステムの全機能（ロック、シンボリックリンク等）が必要

### DataSync → S3 + Lambda を選ぶべき場合

- ✅ S3 Event Notifications によるイベント駆動が必須
- ✅ S3 の全機能（バージョニング、ライフサイクル、Presigned URL）が必要
- ✅ データのコピーが許容される
- ✅ FSx for ONTAP を使用していない

## レイテンシの詳細 — どの区間の何を指すか

「レイテンシ」を 1 つの数値で比較すると判断を誤ります。**読み取りと書き込みで桁が違うサービスがあり、
同じサービスでも構成（ストレージ層、AZ 構成、性能モード）で変わります。** 以下は各サービスが
公表している数値と、その数値がどの区間を指すか、そこから何を考慮すべきかです。

> 各社の公表値は**最良条件での値**です。Amazon EFS のドキュメントは
> 「Latency values shown represent best-case performance under optimal conditions.
> Actual results may vary based on network, workload, and system factors.」と明記しています。
> 実測は自分のワークロードで取ってください。

### FSx for ONTAP S3 Access Point（S3 API 経由）

| 区間 | 値 | 出典 |
|---|---|---|
| S3 API リクエスト単位（読み書き） | 数十 ms | AWS ドキュメント |

AWS は「S3 access points for FSx for ONTAP file systems deliver latency in the tens of
milliseconds range, consistent with S3 bucket access」と記載しています。**これはストレージの
レイテンシではなく S3 プロトコル経路のレイテンシです。** 同じファイルを同じファイルシステムから
NFS で読めばサブ ms なので、差はプロトコルの層にあります。

考慮すべき点:

- **オブジェクト単位の固定オーバーヘッドなので、小さいファイルを大量に処理すると支配的になります。**
  1 MB × 1,000 個は 1 GB × 1 個より遅くなります。バッチ単位を大きくするか、Lambda を並列に
  広げて隠します。
- **一覧取得はページ単位で積み上がります。** `ListObjectsV2` は 1 リクエスト最大 1,000 件なので、
  10,000 ファイルなら 10 ページ = 約 500 ms が下限です（[S3 AP Performance Considerations](./s3ap-performance-considerations.md)）。
- **部分更新がありません。** PutObject はオブジェクト全体の置き換えなので、大きいファイルの
  1 バイト変更にファイル全体の書き込みが発生します。追記型・ランダム更新型のワークロードは
  この経路に向きません。
- リアルタイム応答（対話的な UI のブロッキング処理）には数十 ms が積み上がります。定期スキャンや
  イベント駆動のバッチでは問題になりません。

### Amazon EFS（NFS 経由）

| 構成 | 読み取り | 書き込み | 出典 |
|---|---|---|---|
| Regional（Elastic / Provisioned / Bursting） | 約 1 ms | **約 2.7 ms** | AWS ドキュメント |
| One Zone（同上） | 約 1 ms | **約 1.6 ms** | 同上 |
| EFS Standard ストレージクラス | 1 ms（first byte） | 2.7 ms（first byte） | 同上 |
| EFS IA / Archive ストレージクラス | **数十 ms（first byte）** | 数十 ms | 同上 |
| Max I/O 性能モード | General Purpose より**高い** | 同左 | 同上 |

**書き込みが読み取りの約 2.7 倍というのがこのサービスの性格です。** Regional ファイルシステムは
書き込みを複数 AZ にコミットしてから応答するため、その分が書き込みレイテンシに乗ります。
One Zone は約 1.6 ms で、差は AZ 冗長性とのトレードオフです。

考慮すべき点:

- **小さい書き込みを多数出すワークロードで問題になります。** 追記の多いログ処理、SQLite などの
  ファイルベース DB、`git` のような小ファイル多数の操作は、1 操作ごとにこのレイテンシを払います。
  I/O サイズを大きくするか並列化して償却します（AWS も「overall throughput generally increases as
  the average I/O size increases, since the overhead is amortized over a larger amount of data」と
  説明しています）。
- **メタデータ操作も同じ経路です。** ディレクトリ走査やファイル作成が多い処理は、データ転送量が
  小さくてもレイテンシで律速します。
- **ストレージクラスの自動階層化がテールを作ります。** IA / Archive に落ちたファイルの first byte は
  数十 ms で、Standard の 1 ms とは 1 桁以上違います。ライフサイクルポリシーとアクセスパターンが
  合っていないと、体感が読み取り 1 ms から数十 ms に変わります。
- **Max I/O は選ばないのが現在の推奨です。** AWS は「Due to the higher per-operation latencies with
  Max I/O, we recommend using General Purpose performance mode for all file systems」と明記して
  います（One Zone と Elastic throughput では選択自体できません）。
- 上限は throughput mode でも変わります（Regional Bursting は書き込み 7,000 IOPS、Elastic は
  500,000 IOPS）。レイテンシが同じでも、詰まれば実効応答時間は伸びます。

### FSx for ONTAP（NFS / SMB 経由、EC2 マウント）

| 区間 | 値 | 出典 |
|---|---|---|
| SSD ストレージ上のファイル操作 | **サブ ms（一貫して）** | AWS ドキュメント |
| Capacity Pool ストレージ上のファイル操作 | **数十 ms** | 同上 |

AWS は Single-AZ / Multi-AZ の**どちらもサブ ms** と記載しています（"FSx for ONTAP Multi-AZ and
Single-AZ file systems provide consistent sub-millisecond file operation latencies with SSD
storage and tens of milliseconds of latency with capacity pool storage"）。EFS のように書き込み側の
公表値が別建てにはなっていません。

考慮すべき点:

- **テールを作るのは AZ 構成ではなく階層化です。** FabricPool で Capacity Pool に落ちたブロックの
  読み取りは数十 ms です。コールドデータを含む全体スキャンは、SSD 上の数値では見積れません。
- **NVMe 読み取りキャッシュは構成に依存します。** 対象は Multi-AZ 1 / Multi-AZ 2、2022-11-28 以降に
  作成しスループット 2 GBps 以上の Single-AZ 1、ペアあたり 6 GBps 以上の Single-AZ 2 です。
- **第 2 世代では NVMe キャッシュがスループットを下げることがあります。** AWS は高スループット /
  大 I/O のワークロードでは無効化を推奨しています。レイテンシとスループットのどちらを取るかの選択です。
- 実測は `qos statistics workload latency show`（fsxadmin）で Network / Data / Disk の内訳が取れます。
  「遅い」がどの層かを切り分けられるので、体感の劣化を報告する前にこれを見ます。

### DataSync → S3

**per-operation レイテンシの問題ではなく、鮮度（RPO）の問題です。** 読み取り自体は S3 の
レイテンシですが、支配的なのは「元データの変更がコピー先に現れるまでの時間」＝タスクの実行間隔と
1 回の転送時間です。

考慮すべき点:

- スケジュール間隔より短い鮮度は得られません。処理側から見ると、直前の変更は見えない前提で
  設計する必要があります。
- 差分検出のためのスキャン時間はファイル数に比例します。ファイル数が多いソースでは、転送量が
  小さくてもタスク時間が縮まりません。

### まとめ — レイテンシで選ぶときの見方

| 問い | 見るべき数値 |
|---|---|
| 対話的な UI がブロックするか | 読み取りレイテンシ × 1 操作あたりの往復回数 |
| 小さい書き込みが多いか | **書き込み**レイテンシ（EFS Regional は読み取りの約 2.7 倍） |
| コールドデータを含むか | 階層化後のレイテンシ（EFS IA / FSx Capacity Pool はどちらも数十 ms） |
| ファイル数が多いか | 一覧・メタデータ操作の回数（S3 AP はページ単位、NFS は操作単位） |
| 鮮度が要件か | コピー方式なら同期間隔。in-place アクセスなら常にリアルタイム |

**出典**:
[Amazon EFS performance specifications](https://docs.aws.amazon.com/efs/latest/ug/performance.html)（レイテンシ表、ストレージクラス、性能モード） /
[Amazon FSx for NetApp ONTAP performance](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/performance.html)（SSD / Capacity Pool、NVMe キャッシュの条件） /
[When to Choose EFS](https://aws.amazon.com/efs/when-to-choose-efs/)（I/O サイズによる償却） /
[S3 AP Performance Considerations](./s3ap-performance-considerations.md)（一覧のページネーション実測）

## コスト比較（月額概算、100 files/日、1 MB 平均）

| アーキテクチャ | 処理コスト | ストレージコスト | 合計 |
|--------------|-----------|----------------|------|
| FSx for ONTAP S3 AP + Lambda | ~$15 | $0 (既存 FSx) | **~$15** |
| EFS + Lambda | ~$15 | ~$30 (100 GB EFS) | **~$45** |
| EC2 NFS マウント | ~$50 (t3.medium 常時) | $0 (既存 FSx) | **~$50** |
| DataSync → S3 + Lambda | ~$15 + DataSync $5 | ~$2.3 (100 GB S3) | **~$22** |

> **注記**: 上記は概算であり、実際のコストはワークロード特性により異なります。FSx for ONTAP の既存環境を前提としています。

## NFS Read Cache 比較 — FlexCache vs KNFSD File Cache vs Amazon File Cache

読取り集中ワークロード（EDA、VFX レンダリング、シミュレーション、HPC）で FSx for ONTAP をソースとして NFS キャッシュレイヤーを検討する場合の比較です。

### 比較マトリクス

| 観点 | FlexCache (ONTAP native) | KNFSD File Cache (OSS) | Amazon File Cache |
|------|:---:|:---:|:---:|
| **管理モデル** | FSx for ONTAP フルマネージド | EC2 セルフマネージド (Terraform) | フルマネージド |
| **ソースフィラー** | ONTAP ボリュームのみ | **任意の NFS フィラー（複数同時）** | NFS / S3 |
| **プロトコル** | NFS / SMB / S3 AP | NFS v3 / v4.1 / v4.2 | NFS (Lustre 互換) |
| **書込み** | Write-back（遅延書戻し） | Write-through / Write-around | Read-only |
| **キャッシュ層** | ONTAP volume (SSD + Capacity Pool) | L1: RAM + L2: NVMe (FS-Cache) | SSD |
| **スケーリング** | FSx throughput capacity | **EC2 Auto Scaling（接続数ベース）** | 手動（容量変更） |
| **マルチソース** | 不可（単一 Origin volume） | **可能（複数 NFS サーバー同時）** | 可能（複数リンク） |
| **Observability** | ONTAP CLI/REST + CloudWatch (基本) | **70+ CloudWatch metrics + OTel** | CloudWatch (基本) |
| **データ保護** | SnapMirror, Snapshot 統合 | なし（プロトコルレベル） | なし |
| **Fanout アーキテクチャ** | 不可 | **Tier 1 (WAN) + Tier 2 (LAN) 構成** | 不可 |
| **コスト (キャッシュ層)** | FSx 容量消費 | **EC2 のみ（$5.82/hr で 100 Gbps）** | File Cache 容量課金 |
| **Spot 活用** | N/A | **クライアント側 Spot 対応（キャッシュ常駐）** | N/A |
| **ライセンス** | FSx for ONTAP 含む | Apache 2.0 (OSS) | AWS マネージド |
| **成熟度** | GA (本番利用可) | **Preview** | GA |

### NFS キャッシュ選択ガイド

#### FlexCache を選ぶべき場合

- ✅ ONTAP ボリュームのみがソース
- ✅ Write-back（書込みキャッシュ）が必要
- ✅ SnapMirror / Snapshot との統合が必要
- ✅ フルマネージドで運用負荷を最小化したい
- ✅ SMB / S3 AP を含むマルチプロトコルキャッシュが必要

#### KNFSD File Cache を選ぶべき場合

- ✅ **大規模バーストコンピュート**（数百〜数千コア）で読取り集中
- ✅ **複数の NFS ソース**を統合キャッシュしたい（オンプレ + FSx for ONTAP + OpenZFS）
- ✅ **Spot インスタンス**でコンピュートを実行（キャッシュが warm 状態を維持）
- ✅ キャッシュ層を**独立にスケール**したい（コンピュートと分離）
- ✅ **詳細な Observability**（70+ metrics、OTel エクスポート）が必要
- ✅ WAN/高レイテンシ環境で Fanout アーキテクチャが有効
- ✅ コスト最適化（ONTAP キャパシティを消費しない）

> **FSID Backend**: 単一ノードなら SQLite on FSx for ONTAP ($0)、マルチノードなら RDS/Aurora が必要。
> 詳細は [FSID Backend 選択ガイド](../infrastructure/knfsd-file-cache/docs/fsid-backend-options.md) を参照。

#### Amazon File Cache を選ぶべき場合

- ✅ Lustre 互換クライアントがある
- ✅ フルマネージドで NFS キャッシュが必要（S3 ソースも含む）
- ✅ HPC ワークロードで Lustre の並列 I/O が有効

### KNFSD + S3 AP 相補アーキテクチャ

読取り集中のコンピュートワークロードと、サーバーレス AI/ML 処理を同一データソースに対して実行する場合、KNFSD File Cache と S3 AP を組み合わせることで各アクセスパスを最適化できます:

```
┌─────────────────────────────────────────────────────────────────┐
│  FSx for ONTAP Volume (ソースデータ)                              │
│                                                                 │
│  ┌────────────────┐                       ┌──────────────────┐  │
│  │ KNFSD File     │  NFS re-export        │ Compute Fleet    │  │
│  │ Cache (EC2     │◄─────────────────────►│ (EDA/VFX/HPC)   │  │
│  │ Auto Scaling)  │  local VPC speed      │ Spot 活用可能     │  │
│  └───────┬────────┘                       └──────────────────┘  │
│          │ NFS mount (source)                                    │
│          ▼                                                       │
│  ┌────────────────┐                       ┌──────────────────┐  │
│  │ FSx for ONTAP  │  S3 AP               │ Lambda / Step    │  │
│  │ File System    │◄─────────────────────►│ Functions        │  │
│  │                │  serverless access     │ (AI/ML 後処理)   │  │
│  └────────────────┘                       └──────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**典型的なワークフロー**:
1. 大規模コンピュートフリートが KNFSD 経由で入力データを高速読取り（EDA DRC/LVS、VFX レンダリング等）
2. 処理結果を FSx for ONTAP に書戻し（KNFSD write-through）
3. S3 AP 経由で Lambda が結果ファイルの品質検証・メタデータ抽出・AI 分析を実行
4. NFS/SMB ユーザーが同じボリューム上で最終成果物を閲覧

> **参考**: KNFSD File Cache の詳細は [AWS Solutions Guidance](https://docs.aws.amazon.com/solutions/knfsd-file-cache-on-aws/) および [GitHub リポジトリ](https://github.com/awslabs/knfsd-file-cache) を参照。FSx for ONTAP 向けの deployment example が含まれています。

> **注意**: KNFSD File Cache は 2026 年 7 月時点で **Preview** です。本番ワークロードへの適用は GA を待つことを推奨します。

---

## FAQ

**Q: S3 AP のレイテンシ（数十 ms）は問題にならないか？**
A: バッチ処理（定期スキャン）では問題になりません。1 操作あたり数十 ms が積み上がる対話的な処理には向きません。その場合の代替は NFS 経路ですが、**「NFS なら速い」と一括りにはできません**。詳細は [レイテンシの詳細](#レイテンシの詳細--どの区間の何を指すか) を参照してください。要点は、EFS の書き込みは Regional で約 2.7 ms（読み取りの約 2.7 倍）、FSx for ONTAP は SSD 上ならサブ ms だが Capacity Pool に落ちたデータは数十 ms、という点です。

**Q: 書き込みが多いワークロードではどれを選ぶべきか？**
A: 書き込みレイテンシで比べます。FSx for ONTAP の NFS/SMB（SSD 上）がサブ ms、EFS One Zone が約 1.6 ms、EFS Regional が約 2.7 ms、S3 AP が数十 ms（かつ部分更新不可なので更新はオブジェクト全体の書き換え）です。小さい追記が多い処理ほどこの差が実行時間に直結します。逆にバッチで大きく書くなら、レイテンシよりスループット上限とコストで選ぶ方が妥当です。

**Q: S3 AP で書き込みもできるか？**
A: はい。PutObject をサポートしています（オブジェクト上限 50 GB、単一 PutObject は 5 GB まで。5 GB 超は Multipart Upload）。AI 処理結果を同じボリュームに書き戻し、NFS/SMB ユーザーが閲覧できます。

**Q: FlexCache と EFS の違いは？**
A: FlexCache は ONTAP ボリュームのキャッシュであり、Origin のデータ変更が自動的に反映されます。EFS は独立したファイルシステムです。

**Q: KNFSD File Cache と FlexCache はどう使い分ける？**
A: 単一 ONTAP ソースで書込みキャッシュも必要なら FlexCache。複数ソースの統合や大規模バースト読取りには KNFSD。書込みが少なく読取り集中なら KNFSD のコスト効率が高い場合があります。

**Q: KNFSD File Cache を S3 AP と組み合わせるメリットは？**
A: 同一データに対して「高速 NFS 読取り（コンピュート向け）」と「サーバーレス処理（AI/ML 向け）」の両方を最適化できます。各アクセスパスが独立してスケールし、FSx のスループットを効率的に活用できます。

---

> **Governance Caveat**: 本比較は技術的な観点からの参考情報です。最終的なアーキテクチャ選択は、利用者の要件、既存環境、規制要件を総合的に評価して決定してください。

## 関連ドキュメント

- [KNFSD + S3 AP Dual-Path Architecture (EDA/HPC/VFX)](./knfsd-s3ap-dual-path-architecture.md) — 読取り集中ワークロードの深掘りアーキテクチャガイド
- [S3 AP Performance Considerations](./s3ap-performance-considerations.md) — スループット設計・最適化ガイド
- [ONTAP Integration Notes](./ontap-integration-notes.md) — NAS 共存・FlexCache 組み合わせガイド
- [ファイルポータル UI の選択肢 (Amplify Gen2 / Nextcloud / カスタムビルド)](./file-portal-amplify-gen2.md) — Web UI フロントエンドの比較・選択ガイド
