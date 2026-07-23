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
| **レイテンシ** | 数十 ms (S3 API) | < 1 ms (NFS) | < 1 ms (NFS) | N/A (非同期) |
| **スループット** | FSx 帯域共有 | EFS バースト/プロビジョンド | FSx 帯域共有 | DataSync 帯域 |
| **コスト (処理側)** | Lambda 従量課金 | Lambda + EFS 従量 | EC2 常時稼働 | Lambda 従量課金 |
| **コスト (ストレージ)** | FSx for ONTAP (既存) | EFS 追加 | FSx for ONTAP (既存) | S3 追加 |
| **VPC 依存** | NetworkOrigin による | ✅ VPC 必須 | ✅ VPC 必須 | ❌ 不要 (S3 側) |
| **イベント駆動** | FPolicy (Phase 10) | S3 Event (コピー後) | inotify/FPolicy | S3 Event Notifications |
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
- ✅ サブミリ秒のレイテンシが必要
- ✅ シンプルな構成を優先
- ✅ FSx for ONTAP を使用していない

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
A: バッチ処理（定期スキャン）では問題になりません。リアルタイム応答が必要な場合は EFS + Lambda を検討してください。

**Q: S3 AP で書き込みもできるか？**
A: はい。PutObject（最大 5 GB）をサポートしています。AI 処理結果を同じボリュームに書き戻し、NFS/SMB ユーザーが閲覧できます。

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
