# S3 Standard Bucket ユーザー向けガイド — FSx for ONTAP S3 Access Points との違い

🌐 **Language / 言語**: [日本語](s3-bucket-user-guide.md) | [English](s3-bucket-user-guide.en.md)

## このドキュメントの目的

Amazon S3 標準バケットを普段使用している方が、FSx for ONTAP S3 Access Points を初めて扱う際に知るべき差分を整理します。

> **重要**: このパターンライブラリは **S3 データレイクパターンの代替ではありません**。FSx ONTAP に保存されたファイルデータを、NFS/SMB アクセスパスを維持しながら S3 互換 API で処理するための **file-data integration pattern** です。

## Standard S3 Bucket vs FSx ONTAP S3 Access Point

| 機能 | Standard S3 Bucket | FSx ONTAP S3 AP |
|------|:---:|:---:|
| Object storage backend | S3 | FSx ONTAP volume |
| Versioning | ✅ Supported | ❌ Not supported |
| Object Lock (WORM) | ✅ Supported | ❌ Not supported (代替: SnapLock) |
| Lifecycle policies | ✅ Supported | ❌ Not supported (代替: Snapshot/SnapMirror) |
| S3 Event Notifications | ✅ Supported | ❌ Not supported (代替: FPolicy) |
| Presigned URLs | ✅ Supported | ❌ Not supported (docs) |
| S3 Replication | ✅ Supported | ❌ Not supported (代替: SnapMirror) |
| File protocol access (NFS/SMB) | ❌ | ✅ Alongside S3 API |
| Dual-layer authorization | IAM only | IAM + S3 AP policy + ONTAP file identity |
| Performance dependency | S3 service (auto-scaling) | FSx throughput capacity (provisioned) |
| Cost model | Storage + requests + transfer | Provisioned infrastructure + throughput |

## WORM / Immutable Storage の代替

S3 Object Lock が使えない場合、FSx for ONTAP は以下の代替機能を提供:

| S3 Object Lock 機能 | ONTAP 代替 | 特徴 |
|---|---|---|
| Compliance mode (WORM) | **SnapLock Compliance** | SEC 17a-4(f), FINRA 4511 対応。保持期間中は誰も削除不可（管理者含む） |
| Governance mode | **SnapLock Enterprise** | 内部コンプライアンス用。Privileged delete 可能 |
| Object Lock + Versioning | **Tamperproof Snapshot** | SnapLock Compliance clock で Snapshot にロック期間を設定。管理者を含む誰も保持期間内に削除不可 |

さらに、ランサムウェア対策として:

| 目的 | ONTAP 機能 | 特徴 |
|---|---|---|
| 異常検知 + 自動保護 | **Autonomous Ransomware Protection (ARP)** | AI でボリュームの異常パターン（エントロピー、拡張子変更、IOPS）を監視し、脅威検知時に自動 Snapshot 作成 |
| Snapshot 削除防止 | **Tamperproof Snapshot** | SnapLock 技術で Snapshot をロックし、ランサムウェアによる Snapshot 削除攻撃を防止 |

> **Tamperproof Snapshot と ARP は別機能です**:
> - **Tamperproof Snapshot**: Snapshot のロック保護（誰も削除不可にする仕組み）
> - **ARP**: 脅威の検知と自動対応（異常検知時に Snapshot を自動作成する仕組み）
>
> 両者を組み合わせることで「ARP が脅威検知 → Snapshot 自動作成 → Tamperproof で削除防止」の多層防御が可能。

> **出典**: [How SnapLock works — FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/how-snaplock-works.html), [Snapshot locking — NetApp ONTAP](https://docs.netapp.com/us-en/ontap/snaplock/snapshot-lock-concept.html), [ARP — FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/ARP.html)

**推奨設計**:
- 規制対応 WORM が必要な監査成果物 → SnapLock Compliance volume に出力、または標準 S3 バケット（Object Lock 有効）にコピー
- Snapshot の改ざん防止 → Tamperproof Snapshot を有効化
- ランサムウェア検知・自動対応 → ARP を volume レベルで有効化（追加コスト無し）
- point-in-time recovery → ONTAP Snapshot（S3 Versioning の代替）

> **注意**: SnapLock は ONTAP ネイティブの WORM オプションですが、S3 Object Lock API のドロップイン代替ではありません。規制要件に基づいて SnapLock と標準 S3 Object Lock のどちらが適切かを検証してください。

## Versioning の代替

S3 Versioning と ONTAP Snapshot は異なるリカバリモデルです:

| 特性 | S3 Versioning | ONTAP Snapshot |
|------|---|---|
| 保護粒度 | 個別オブジェクト単位 | ファイルシステム全体の point-in-time |
| 保持コスト | 全バージョン分のストレージ | 差分ブロックのみ（容量効率的） |
| リストア | 特定バージョンを指定して取得 | Snapshot からの個別ファイル復元 or volume restore |
| 削除保護 | Delete Marker + バージョン残存 | Snapshot 内に保持（volume 上のファイルが削除されても） |

## Event Notification の代替

| S3 機能 | ONTAP 代替 | 説明 |
|---|---|---|
| S3 Event Notifications | **FPolicy** (event-driven pipeline) | ファイル作成/書込/名前変更を TCP 経由で通知 |
| EventBridge S3 events | **EventBridge Scheduler** (polling) | 定期的に ListObjectsV2 で新規ファイルを検出 |

本パターンライブラリは主に EventBridge Scheduler を使用しますが、リアルタイムイベント処理が必要な場合は Phase 10-12 の FPolicy パイプラインを参照してください。

## Performance の違い

| 特性 | Standard S3 | FSx ONTAP S3 AP |
|---|---|---|
| スケーリング | リクエスト率に応じて自動 | FSx throughput capacity に依存（provisioned） |
| レイテンシ | 数ms（同一リージョン） | tens of ms（S3 AP data plane 経由） |
| 並列性能 | プレフィックス並列で 5,500+ req/s/prefix | FSx throughput capacity がボトルネック |
| Throughput 変更時 | 影響なし | S3 AP が ServiceUnavailable になる可能性あり |

> S3 標準バケットとは異なり、FSx ONTAP S3 AP の可用性は FSx ファイルシステムの運用変更（throughput capacity 変更など）の影響を受ける可能性があります。

## Security の違い

S3 標準バケットでは Bucket Policy で許可すれば OK ですが、FSx ONTAP S3 AP では:

> **FSx ONTAP S3 AP リクエストは AWS 認可（IAM + S3 AP policy）とファイルシステム認可（ONTAP file identity）の両方を通過する必要があります。IAM Allow だけでは不十分です。**

推奨チェック:
- IAM Access Analyzer で S3 AP policy を検証してからデプロイ
- file system identity の権限を NFS/SMB クライアントから事前確認
- Access Denied シナリオのテスト（意図しないファイルへのアクセスがブロックされるか）

## NetworkOrigin の注意

| S3 標準バケット | FSx ONTAP S3 AP |
|---|---|
| VPC Endpoint は routing choice | NetworkOrigin は **作成時に決定、変更不可** |
| Gateway/Interface EP を後から追加・変更可能 | Internet-origin ↔ VPC-origin 変更不可 |

## 保持・ライフサイクルの代替設計

S3 Lifecycle policies が使えないため:

- **短期保持** (中間成果物): ONTAP volume quota + 定期削除スクリプト
- **長期保持** (監査成果物): SnapLock Compliance volume、または標準 S3 バケット（Object Lock）へコピー
- **階層化**: ONTAP auto-tiering (SSD → Capacity Pool) が S3 Intelligent-Tiering の代替
- **期限切れ削除**: Lambda による定期クリーンアップ + data classification ラベルで判断

## データ戦略の判断基準

| 戦略 | 使用する場合 |
|---|---|
| FSx ONTAP に残す + S3 AP で処理 | ファイルセマンティクス、NFS/SMB 互換性、移行コスト回避 |
| 分析結果を標準 S3 にコピー | データレイクガバナンス、Lifecycle、Object Lock、Lake Formation が必要 |
| 全面 S3 移行 | Object-native アプリケーションモダナイゼーション |

## Observability の違い

S3 標準バケットの監査（CloudTrail data events, S3 Server Access Logs, Storage Lens）に加え、FSx ONTAP では:

```
AWS API plane:  CloudTrail, CloudWatch, Step Functions execution history
Application:    Lambda logs, EMF metrics, lineage records
File-system:    FSx CloudWatch metrics, ONTAP REST API, FPolicy audit logs
```

> 両方のプレーン（AWS + ファイルシステム）を観測してください。

---

## FAQ

| 質問 | 回答 |
|------|------|
| これは普通の S3 バケットですか？ | **いいえ**。FSx ONTAP volume への S3 API アクセスパスです |
| Lifecycle は使えますか？ | **いいえ**。Snapshot/SnapMirror/auto-tiering を使用 |
| Versioning は使えますか？ | **いいえ**。ONTAP Snapshot が代替 |
| Object Lock は使えますか？ | **いいえ**。SnapLock (Compliance/Enterprise) が代替 |
| Presigned URL は使えますか？ | **ドキュメント上 Not supported** |
| NFS/SMB からもアクセスできますか？ | **はい**。同じデータに並行アクセス可能 |
| データレイクとして使うべきですか？ | **通常 No**。Integration boundary として使い、分析出力は標準 S3 へ |
| S3 Event Notifications は使えますか？ | **いいえ**。FPolicy または EventBridge Scheduler を使用 |

---

> **Governance Caveat**: 本ドキュメントは技術ガイダンスであり、法的・コンプライアンス・規制上の助言ではありません。
