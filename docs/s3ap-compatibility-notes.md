# S3AP Compatibility Notes

## What FSx for ONTAP S3 Access Points Provide

FSx for ONTAP S3 Access Points provide an S3-facing access boundary for file data stored in FSx for ONTAP. Data remains on FSx for ONTAP and can continue to be accessed through NFS and SMB.

## S3 AP vs NFS/SMB: When to Use Which

| 要件 | S3 AP 推奨 | NFS/SMB 推奨 |
|------|:---:|:---:|
| サーバーレス連携 (Lambda, Step Functions) | ✅ | — |
| POSIX セマンティクス必須 (lock, rename, symlink) | — | ✅ |
| 大容量ファイルの逐次処理 | △ (5GB 上限あり) | ✅ |
| 権限ベースのファイルアクセス制御 | ✅ (dual-layer auth) | ✅ (NTFS/UNIX ACL) |
| 低レイテンシ metadata 操作 (stat, readdir) | △ (tens of ms) | ✅ (sub-ms) |
| 既存アプリケーション互換性 | — | ✅ |
| AWS サービス統合 (Athena, Bedrock, Textract) | ✅ | — |
| イベント駆動ファイル処理 | ✅ (FPolicy + S3 AP) | △ (FPolicy + NFS mount) |

> **注**: S3 AP は NFS/SMB の置き換えではなく、AWS サービス統合のための補完的アクセスパスです。同じボリュームに NFS/SMB と S3 AP の両方からアクセスできます。

## Tested Operations

| Operation | Status |
|-----------|--------|
| ListObjectsV2 | ✅ Tested |
| GetObject | ✅ Tested |
| PutObject (max 5 GB) | ✅ Tested |
| Range GET | ✅ Tested |
| HeadObject | ✅ Tested |
| DeleteObject | ✅ Tested |
| MultipartUpload | ✅ Supported (per AWS docs) |

## Not Equivalent to Full S3 Bucket Semantics

Not all bucket-level features or integration patterns apply directly:

- Native S3 bucket notifications (GetBucketNotificationConfiguration not supported)
- Bucket lifecycle policies
- Bucket versioning
- Object Lock (on the S3AP itself)
- Presigned URLs (**Listed as "Not supported"** — but observed working; see [Presigned URL Support](#presigned-url-support) for AWS Support clarification)

### WORM / Immutable Storage の代替

S3 Object Lock / Versioning が使えないため、FSx for ONTAP 固有の代替機能を使用:

| S3 機能 | ONTAP 代替 | 特徴 |
|---|---|---|
| Object Lock Compliance | **SnapLock Compliance** volume | SEC 17a-4(f), FINRA 4511 対応 WORM。保持期間中は誰も削除不可 |
| Object Lock Governance | **SnapLock Enterprise** volume | 内部コンプライアンス用 WORM。Privileged delete 可能 |
| Versioning (point-in-time) | **ONTAP Snapshot** | ファイルシステム全体の point-in-time 保護。差分ブロックのみ保存 |
| Replication | **SnapMirror** | クロスリージョン/クロスアカウントレプリケーション |
| ランサムウェア対策 | **Autonomous Ransomware Protection (ARP)** | AI ドリブン改ざん検知 + Tamperproof Snapshot 自動作成 |

> **推奨**: 規制対応 WORM が必要な監査成果物は SnapLock Compliance volume に保存するか、標準 S3 バケット（Object Lock 有効）にコピーしてください。
>
> **出典**: [SnapLock](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/how-snaplock-works.html), [ARP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/ARP.html)

## Recommended Trigger Patterns

| Pattern | Description |
|---------|-------------|
| POLLING (default) | EventBridge Scheduler + Discovery Lambda |
| EVENT_DRIVEN | FPolicy-based, near-real-time; not native S3 bucket notifications |
| HYBRID | Both polling and event-driven with deduplication |

---

## Presigned URL Support

> ⚠️ **Production Warning**: AWS Support explicitly states that operations marked "Not supported" should NOT be relied upon for production workloads, even when they return success today. Design alternatives for any workflow that requires presigned URL access to FSx ONTAP S3 Access Points.

### Status: Listed as "Not supported" — but observed working

AWS ドキュメントの互換性テーブルでは `Presign — Not supported` と記載されていますが、AWS サポートからの回答により、実態が明確になりました。

**AWS サポートの見解（要約）**:

1. **Presigning はサーバー側の API 操作ではない** — クライアント側の SigV4 署名計算であり、ネットワークリクエストは発生しない
2. **Presigned URL を curl 等で使用すると、実際には通常の GetObject リクエストが実行される** — 署名が Authorization ヘッダーではなくクエリパラメータに含まれるだけ
3. **GetObject が Supported である以上、Presigned URL による GetObject は構造的にブロックできない** — GetObject 自体を壊さずに Presigned URL だけを無効化することは不可能
4. **ドキュメントの意図**: 「Presigned URL ワークフローを公式にテストしていない」または「未サポート機能（SSE パラメータ、バージョニングパラメータ等）を含む Presigning シナリオは失敗する可能性がある」ことを示唆していた可能性が高い

**テスト結果（別プロジェクトで確認済み）**:

| Operation | Presigned URL | Observed Result | Notes |
|-----------|--------------|-----------------|-------|
| GetObject | ✅ 動作確認 | HTTP 200, 正常なデータ返却 | SigV4 クエリ文字列認証 |
| PutObject | 未検証 | — | GetObject と同じ原理で動作する可能性あり |
| HeadObject | 未検証 | — | 同上 |

### ⚠️ 本番利用に関する注意

AWS サポートの明確な指針:

> **"Not supported" と記載された操作が今日成功しても、本番ワークロードで依存すべきではない。**

理由:
- 非推奨通知なしに動作が変更される可能性がある
- リージョン間または時間経過で結果が不一致になる可能性がある
- サービス側の更新後に動作しなくなる可能性がある
- エッジケースで異なる動作をする可能性がある

### 推奨分類

| Feature | Status | Guidance |
|---------|--------|----------|
| GetObject, PutObject, ListObjectsV2 | **Supported** | 自由に構築可能 |
| Conditional writes (If-None-Match) | **Blocked** | 使用不可（NotImplemented を返す） |
| Presigned URLs | **Not supported (doc)** | 依存しない。代替手段を設計すること |
| ListObjectVersions | **Not supported (doc)** | ListObjectsV2 を使用すること |

### Presigned URL 代替手段

Presigned URL に依存せずに時間制限付きファイルアクセスを実現する方法:

| 代替手段 | 概要 | ユースケース |
|---------|------|-------------|
| API Gateway + Lambda proxy | IAM/JWT 認証付きの Lambda 経由ダウンロード | Web アプリ、モバイル |
| CloudFront signed URLs | Lambda@Edge で制御されたオリジン | 大規模配信 |
| 一時 STS 認証情報 | スコープされた IAM (時間制限、プレフィックス制限) | バッチ処理、パートナー連携 |
| アプリケーション層ブローカー | 監査ログ + アクセス取消機能付き | 規制産業 |

### ドキュメント改善の見通し

AWS サポートは FSx for ONTAP サービスチームにドキュメント改善をエスカレーション済み:
1. "Presign" 行の削除または再構成（API ではないため）
2. "Not supported + hard-blocked"（エラーを返す）と "Not supported + may incidentally work"（保証なし）の区別を明確化

> **Content was rephrased for compliance with licensing restrictions. Source: AWS Support correspondence (May 2026).**

### AWS Documentation Reference

- [Access point compatibility — FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)
  - 互換性テーブルに `Presign — Not supported` と記載（ドキュメント改善エスカレーション中）
- [re:Post: FSx for ONTAP S3 Access Points — Presigned URL behavior clarification](https://repost.aws/questions/QUtD1NGAd6RWGIxGlBRX4xpw)

---

## Troubleshooting Pointers

### Common Issues and Resolutions

| Symptom | Likely Cause | Resolution | Related UC |
|---------|-------------|------------|-----------|
| `AccessDenied` on ListObjectsV2 | IAM policy の Resource ARN 形式が間違い | `arn:aws:s3:{region}:{account}:accesspoint/{name}` 形式を使用（エイリアスではない） | All |
| `AccessDenied` on GetObject | S3 AP リソースポリシー未設定 | `s3control put-access-point-policy` でリソースポリシーを追加 | All |
| `Connection timed out` from VPC Lambda | Internet Origin AP に S3 Gateway VPC Endpoint 経由でアクセス | VPC 外 Lambda に変更、または NAT Gateway 経由にする | All |
| `Connection timed out` from VPC Lambda (VPC Origin AP) | Lambda が AP のバインド VPC 外にある | Lambda を AP バインド VPC 内に配置し、S3 Gateway EP を確認 | All |
| Empty ListObjectsV2 response | Prefix が間違い、またはボリュームの junction path 不一致 | ONTAP REST API でボリュームの junction path を確認し、Prefix を修正 | All |
| `ServiceUnavailable` on GetObject | FSx データプレーンへの到達不可 | FSx の管理 IP / データ LIF のサブネットとルーティングを確認 | All |
| `MalformedPolicy` on put-access-point-policy | 無効なアクション（GetBucketLocation 等）を含む | ListBucket + GetObject + PutObject のみ使用可能 | All |
| Slow response at high concurrency | FSx Throughput Capacity の飽和 | FSx Throughput Capacity を増加（256/512 MBps）、または並列度を下げる | UC with batch processing |
| Cross-region Textract/Comprehend failure | サービスが ap-northeast-1 で未提供 | `TextractRegion` / `ComprehendMedicalRegion` パラメータで us-east-1 等を指定 | UC2, UC5 |
| Lambda timeout (> 15 min) | 大ファイル処理 or 高並列による FSx キューイング | Range GET で部分読み取り、または Map State の並列度を制限 | UC4, UC5, UC8 |

### Diagnostic Steps

1. **IAM 確認**: `aws sts get-caller-identity` で呼び出し元を確認
2. **ARN 確認**: IAM ポリシーの Resource が `arn:aws:s3:{region}:{account}:accesspoint/{name}` 形式か確認
3. **ネットワーク確認**: Lambda の VPC 設定と S3 AP の NetworkOrigin (Internet/VPC) の組み合わせを確認
4. **S3 AP ポリシー確認**: `aws s3control get-access-point-policy` でリソースポリシーを確認
5. **ONTAP 側確認**: ファイルシステム identity の権限（UNIX UID or Windows AD ユーザー）を確認

---

## Cross-References from Use Cases

各 UC から本ドキュメントへの参照ポイント:

| UC / Pattern | Relevant Compatibility Note |
|-------------|---------------------------|
| UC1-UC28 (All) | Trigger patterns — POLLING がデフォルト、S3 Event Notification は非対応 |
| UC2, UC14 (Financial) | Cross-region invocation — Textract が ap-northeast-1 で未提供 |
| UC5, UC7 (Healthcare/Genomics) | Range GET — DICOM/genomics ヘッダーの部分読み取りに有効 |
| UC3, UC11 (Real-time) | EVENT_DRIVEN — FPolicy ベース、ネイティブ S3 通知ではない |
| UC4 (Media/VFX) | PutObject — 処理結果の書き戻し（max 5 GB） |
| FC1 (FlexCache Anycast/DR) | FlexCache × S3AP 統合 — AWS リリース待ち |
| FC2-FC6 (FlexClone patterns) | FlexClone ボリュームへの S3AP アタッチ — junction path 設定が必要 |

---

## Related Documentation

- [S3AP Authorization Model](s3ap-authorization-model.md)
- [Trigger Mode Decision Guide](trigger-mode-decision-guide.md)
- [S3AP Benchmark Results](s3ap-benchmark-results.md)
- [S3AP Performance Considerations](s3ap-performance-considerations.md)
- [Deployment Profiles](deployment-profiles.md)
- [Partner/SI Delivery Checklist](partner-si-delivery-checklist.md)
- [Production Readiness](production-readiness.md)
