# S3 Access Point / ONTAP API の罠

> このファイルはリポジトリに含まれる（GitHub から読める）。ローカルの Kiro では
> `.kiro/steering/pitfalls-s3ap-ontap.md` が読み込み条件だけを持ち、
> 該当する作業をしているときにこの内容へ誘導する。`.kiro/` は公開しないため、
> 知識の本体は常にこちら側に置く。

| Pitfall | Solution |
|---------|----------|
| Internet-origin S3AP from VPC Lambda | Use VPC-external Lambda or NAT Gateway |
| S3 Gateway VPC Endpoint + Internet-origin S3AP | Does NOT work — use NAT or VPC-external |
| ONTAP REST API auth on SVM IP | Use filesystem management IP, not SVM IP |
| FlexClone `nas.security_style` | Cannot specify — inherited from parent volume |
| Modifying enabled FPolicy policy | Disable → modify → re-enable sequence |
| `mount -o vers=4` negotiates NFSv4.2 | Always use explicit `vers=4.1` |
| IVS Auto-Record to FSx for ONTAP S3 AP → `Recording Start Failure` | IVS does not support S3 AP as recording destination (confirmed by AWS service team). Use IVS → standard S3 bucket → FSx for ONTAP path |
| Volume name `quick-test-data` → BadRequest | Volume names allow only alphanumeric + underscore. Use `quick_test_data` (no hyphens) |
| `aws fsx create-and-attach-s3-access-point` positional args fail | Use `--cli-input-json file://create-ap.json`. Positional `--ontap-configuration` parsing is fragile |
| Delete volume while S3 AP attached → BadRequest | Delete S3 AP first (`detach-and-delete-s3-access-point`), wait for deletion, then delete volume |
| `DeleteVolume` names an "object store NAS bucket" after the S3 AP is gone | Attach creates an ONTAP-side `amazon-fsx-<volume-id>` bucket outliving the access point (a `FAILED` attach too). **Wait and retry — it clears asynchronously**: refused 2026-08-17, deleted in 60-90 s on 2026-08-18, no CLI needed. `GET /protocols/s3/buckets` never lists it, so an empty list is not "already gone". Interval measured once |
| Presigned URL `SignatureDoesNotMatch` from Lambda | boto3 defaults to SigV2 for presign, and ONTAP S3 only supports v2 presigned URLs from 9.16.1. Use `Config(signature_version="s3v4")` explicitly (v4 supported from ONTAP 9.11.1; NetApp recommends v4) |
| Presigned PUT answers `301 PermanentRedirect` | v4 signing alone is not enough: under the default `addressing_style` botocore presigns `<alias>.s3.amazonaws.com` even with a region set, and the redirect cannot be followed because the signature covers `host`. Two shapes work (measured 2026-08-15): path-style with an explicit regional `endpoint_url`, or `Config(signature_version="s3v4", s3={"addressing_style": "virtual"})`. Only leaving both to the default fails, and `make drift` rejects that combination in any handler that presigns |
| Rename, move, copy, trash and restore stop at 5 GiB | All five are one `CopyObject`, whose single-operation ceiling is 5 GB. `UploadPartCopy` is the documented way past it and answers `NoSuchKey` here, so there is no route past the limit through the S3 AP at all — check the size and refuse with the reason rather than surfacing an S3 error mid-operation |
| Presigned URL `HEAD` returns 403 but `GET` works | Some S3 AP configurations don't support HEAD on presigned URLs. Use GET for verification |
| ONTAP REST の `fields=` に存在しないフィールドを混ぜる → 一覧が空になる | ONTAP はリクエスト全体を 400 で拒否し（例: `The value "last_transfer_size" is invalid for field "fields"`）、ハンドラ側は空リスト + error で返す。モック ONTAP は `fields` を無視してレコードを返すため、レスポンス整形のアサートだけでは検出できない。**送信 URL の `fields` 自体をテストで固定する**（`MockHttp.calls` を検査） |
| `/cluster/nodes` と `/cluster/licensing/licenses` が 0 件 | エラーではない。FSx for ONTAP ではクラスター管理を AWS が担うため 0 件で返ることがある（ONTAP 9.17.1P7D1 で実測）。UI 側に「エラーではない」旨の注記を出す |
| ONTAP 管理が `6691623 "User is not authorized."` | **誤パスワードとロックアウトが同一メッセージ**。「権限不足」と誤診しやすい。`lockout-duration=0` で**待っても戻らない**ので**同じ資格情報で再試行しない**。復旧はパスワードリセット + Secrets Manager 更新 → [実測](../ja/portal-identity-verification-results.md) |

## S3 Access Point Critical Knowledge

### IAM ARN Format (Most Common Error)

```yaml
# ✅ Correct
Resource: !Sub "arn:aws:s3:${AWS::Region}:${AWS::AccountId}:accesspoint/${S3AccessPointName}"
Resource: !Sub "arn:aws:s3:${AWS::Region}:${AWS::AccountId}:accesspoint/${S3AccessPointName}/object/*"

# ❌ Wrong (bucket-style ARN does not work for S3 AP)
Resource: !Sub "arn:aws:s3:::${S3AccessPointAlias}"
```

Source: AWS [Troubleshooting access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/troubleshooting-access-points-for-fsxn.html).

### Dual-Layer Authorization

**Both layers must Allow — but *within* Layer 1 the policies are combined, not ANDed.** Measurements
and policy examples: [authorization model](../s3ap-authorization-model.md).

- **A missing AP policy is not a cause of `AccessDenied`** — same-account identity-based alone allows.
- **A narrow `Allow` does not narrow access.** Narrow with an explicit `Deny` +
  `Condition StringNotEquals aws:PrincipalArn` (not `NotPrincipal`: needs account ARN + session ARN,
  no wildcards).
- **Layer 2 returns `AccessDenied` too** — volume root `uidgid`/mode bits flipped `PutObject` with no
  AP policy attached. A Layer 2 denial has a **bare** `Access Denied` body; Layer 1's explicit deny
  appends `with an explicit deny in a resource-based policy`. Same results on UNIX and NTFS volumes.
- **A SLAG on a UNIX volume denies every protocol** until a unix→win name mapping exists. Not
  S3-specific; NFS stops too. A permissive ACE does not help, and a reachable DC is not enough.
- **Read-only needs a Layer 2 identity without write permission.** `FileSystemIdentity` has no update
  API; recreating the AP changes the alias. Decide before creating it.

### Supported Operations

PutObject, GetObject, ListObjectsV2, HeadObject, DeleteObject, MultipartUpload.
**Measured size limits** (2026-08-02, ap-northeast-1 — see [size limit verification](../s3ap-object-size-limits-verification.md)):
- Single `PutObject` and `UploadPart` per part: **5 GiB = 5,368,709,120 bytes**. Rejected on
  Content-Length (immediate, ~2.7s) with 400 `EntityTooLarge` + `MaxSizeAllowed`.
- Whole object (upload): **50 GiB = 53,687,091,200 bytes**. 50 GiB succeeds; 50 GiB + 1 fails.
- ⚠️ The whole-object limit is checked **only at `CompleteMultipartUpload`, after the entire payload is transferred** (~10 min for 50 GiB). `UploadPart` has no cumulative check, and the Complete error omits `MaxSizeAllowed`. **Validate object size client-side before uploading.**
- `CompleteMultipartUpload` took ~557s for 50 GiB — set a long `read_timeout`. Docs say "GB"; both
  limits are **binary** (GiB).
`UploadPartCopy` is documented as Supported but **fails with `NoSuchKey`** in practice (`CopyObject` works) — server-side assembly of large objects is not possible.
NOT supported: GetBucketNotificationConfiguration.
Presigned URLs: listed as "Not supported" by AWS but observed working (client-side SigV4 → plain
GetObject). A vendor-confirmed doc correction is **not yet published**, so avoid production reliance
until it is. Details: [compatibility notes](../s3ap-compatibility-notes.md).

### AI サービスは S3 参照で AP を読めない（2026-08-12 実測）

Rekognition と Textract に「S3 上のオブジェクト」として AP を渡すと失敗する。

```python
# ❌ InvalidS3ObjectException: Unable to get object metadata from S3
rekognition.detect_labels(Image={"S3Object": {"Bucket": ap_alias, "Name": key}})
textract.detect_document_text(Document={"S3Object": {"Bucket": ap_alias, "Name": key}})

# ✅ AP から bytes を取得して inline で渡す
image_bytes = s3ap.get_object_bytes(key=key)      # shared/s3ap_helper.py
rekognition.detect_labels(Image={"Bytes": image_bytes})
textract.detect_document_text(Document={"Bytes": doc_bytes})
```

**AP ポリシーの不足ではない。** `rekognition.amazonaws.com` / `textract.amazonaws.com` /
`bedrock.amazonaws.com` を AP ポリシーの Principal に許可しても同じエラーになることを確認した
（確認後ポリシーは削除した）。

**inline に切り替えられない API がある。** 同期 API は `Bytes` を受け付けるが、以下は S3 参照
しか取らないため、**通常の S3 バケットに置く必要がある**（AWS 公式リファレンスで確認済み。
`DocumentLocation` と `Video` はいずれもメンバが S3 オブジェクトのみ）:

| API | 受け付ける入力 | 該当パターン |
|---|---|---|
| Textract `StartDocumentAnalysis` / `StartDocumentTextDetection`（非同期） | `DocumentLocation.S3Object` のみ | `financial-idp/ocr` |
| Rekognition Video `StartContentModeration` 等（stored video） | `Video.S3Object` のみ | `edge/media-ivs-vod-publishing/moderation` |

inline 方式は同期 API の上限（5 MB）に収まる必要がある。`S3ApHelper.get_object_bytes()` が
`head_object` で**取得前に**判定して落とす。

### NetworkOrigin (Immutable After Creation)

- `Internet`: Accessible from anywhere with valid credentials.
  - ⚠️ ここには以前「NOT via S3 Gateway VPC Endpoint」と書いていたが、2026-08-12 の実測と
    整合しない。NAT を撤去済みでパブリック IP を持たない VPC Lambda（`subnet-0123456789abcdef0`）
    から Internet-origin AP への ListObjectsV2 / PutObject が成功した。この subnet の主ルート
    テーブルには S3 ゲートウェイエンドポイントが紐づいており、他に外向き経路が無い。
    **パケット経路を直接観測したわけではない**ので断定はしないが、「ゲートウェイエンドポイント
    経由では到達できない」は少なくとも無条件には成立しない。
- `VPC`: Accessible only from bound VPC via S3 Gateway/Interface Endpoint.

### AD-Joined SVM: AD DC Reachability Required for Data Operations

On AD-joined SVMs (CIFS enabled), **every S3 AP data operation** needs the SVM to reach its AD domain
controllers — ONTAP does a `unix→win` reverse lookup per file-system operation, even on UNIX security
style volumes. **`HeadBucket` succeeds anyway**, so it is a false positive: ListObjectsV2, GetObject
and PutObject all return `AccessDenied` while HeadBucket, IAM, AP policy and network all pass. The
cause is the ONTAP layer, not any of the layers the symptom points at.

**Pre-flight check**: use `shared/ad_health_check.check_ad_dc_reachability()`. Do not hand-roll it —
a non-empty `discovered_servers` list is **not** sufficient (entries persist after the controllers
stop answering); the entry must have `server_type=ms_dc` and `state=ok`. Procedure and Step Functions
wiring: [AD-joined SVM prerequisites](../en/ad-joined-svm-s3ap-prerequisites.md). Re-joining, OU
paths, DNS restore and audit-subject behaviour: [pitfalls-ad-smb](pitfalls-ad-smb.md).

---

## 条件付き書き込み（`If-None-Match`）の 501 応答

ブラウザから S3 AP に書くとき、`PutObject` に `if-none-match: *` を付けると
`501 NotImplemented`（`A header you provided implies functionality that is not implemented`）
が返る。S3 の conditional write に相当する機能をこの Access Point が実装していない。

実測（2026-08、ONTAP 9.18.1P3D1、Cognito Identity Pool の authenticated ロール）:

| リクエスト | 結果 |
|---|---|
| `PUT` + `if-none-match: *` + `x-amz-checksum-crc32` | 501 NotImplemented |
| `PUT` + `if-none-match: *`（checksum なし） | 501 NotImplemented |
| `PUT` + `x-amz-checksum-crc32`（`if-none-match` なし） | **200 OK** |
| `GET` / `ListObjectsV2` | 200（どちらのヘッダーも送らないため影響なし） |

CRC32 チェックサムは通る。落ちるのは `if-none-match` だけ。Storage Browser は
`preventOverwrite` をこのヘッダーに変換し upload と createFolder の両方が送るので、
「一覧は見えるのに書き込みだけ全件失敗する」形になる。ヘッダーは `SignedHeaders` に入るため
署名後に除去できず、差し替えられるのはハンドラーだけ（`createStorageBrowser({ actions })`）。
上書き防止は書き込み前の `list` で代替するが原子性はない。実装は
`solutions/amplify-portal/src/lib/storageBrowserWriteHandlers.ts`。

**代替実装で踏んだ罠**: 存在確認と書き込みを並行に走らせると、小さいファイルでは PUT が先に
完了し、直後の一覧が**自分が書いたオブジェクト**を見つけて `OVERWRITE_PREVENTED` を返す。
画面は失敗、AP にはオブジェクトが存在する（1.8 MB で実際に発生）。確認は書き込み開始の
**前**に完了させる。

## 有効な S3 AP は API から引く（台帳を持たない）

手書きの一覧は無言で古くなる（削除済みや `MISCONFIGURED` の AP も設定ファイル上は正しく
見える）。インベントリ源は `fsx describe-s3-access-point-attachments` の 1 つだけ。
必ずページングを追う: 1 ページ目だけ読むと、存在する AP が「存在しない」と区別できない
形で欠ける。`make discover-s3ap`（`scripts/discover_s3_access_points.py`）と使い方は
[portal-deployment-runbook](../ja/portal-deployment-runbook.md) にある。
