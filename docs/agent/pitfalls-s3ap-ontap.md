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
| Presigned URL `SignatureDoesNotMatch` from Lambda | boto3 defaults to SigV2 for presign, and ONTAP S3 only supports v2 presigned URLs from 9.16.1. Use `Config(signature_version="s3v4")` explicitly (v4 supported from ONTAP 9.11.1; NetApp recommends v4) |
| Presigned URL `PermanentRedirect` from Lambda | Global endpoint `s3.amazonaws.com` redirects. Use `endpoint_url=f"https://s3.{region}.amazonaws.com"` |
| Presigned URL `HEAD` returns 403 but `GET` works | Some S3 AP configurations don't support HEAD on presigned URLs. Use GET for verification |
| ONTAP REST の `fields=` に存在しないフィールドを混ぜる → 一覧が空になる | ONTAP はリクエスト全体を 400 で拒否し（例: `The value "last_transfer_size" is invalid for field "fields"`）、ハンドラ側は空リスト + error で返す。モック ONTAP は `fields` を無視してレコードを返すため、レスポンス整形のアサートだけでは検出できない。**送信 URL の `fields` 自体をテストで固定する**（`MockHttp.calls` を検査） |
| `/cluster/nodes` と `/cluster/licensing/licenses` が 0 件 | エラーではない。FSx for ONTAP ではクラスター管理を AWS が担うため 0 件で返ることがある（ONTAP 9.17.1P7D1 で実測）。UI 側に「エラーではない」旨の注記を出す |

## S3 Access Point Critical Knowledge

### IAM ARN Format (Most Common Error)

```yaml
# ✅ Correct
Resource: !Sub "arn:aws:s3:${AWS::Region}:${AWS::AccountId}:accesspoint/${S3AccessPointName}"
Resource: !Sub "arn:aws:s3:${AWS::Region}:${AWS::AccountId}:accesspoint/${S3AccessPointName}/object/*"

# ❌ Wrong (bucket-style ARN does not work for S3 AP)
Resource: !Sub "arn:aws:s3:::${S3AccessPointAlias}"
```

### Dual-Layer Authorization

Both must Allow:
1. **AWS-side**: IAM identity policy + S3 AP resource policy
2. **ONTAP-side**: File system identity (UNIX UID or Windows AD user)

### Supported Operations

PutObject, GetObject, ListObjectsV2, HeadObject, DeleteObject, MultipartUpload.
**Measured size limits** (2026-08-02, ap-northeast-1 — see [size limit verification](../s3ap-object-size-limits-verification.md)):
- Single `PutObject`: **5 GiB = 5,368,709,120 bytes**. Rejected on Content-Length (immediate, ~2.7s) with 400 `EntityTooLarge` + `MaxSizeAllowed`.
- `UploadPart` per part: **5 GiB** (same value, same fast rejection).
- Whole object (upload): **50 GiB = 53,687,091,200 bytes**. 50 GiB succeeds; 50 GiB + 1 fails.
- ⚠️ The whole-object limit is checked **only at `CompleteMultipartUpload`, after the entire payload is transferred** (~10 min for 50 GiB). `UploadPart` has no cumulative check, and the Complete error omits `MaxSizeAllowed`. **Validate object size client-side before uploading.**
- `CompleteMultipartUpload` took ~557s to assemble a 50 GiB object — set a long `read_timeout`.
- Docs say "5 GB"/"50 GB" but both are **binary** (GiB).
`UploadPartCopy` is documented as Supported but **fails with `NoSuchKey`** in practice (`CopyObject` works) — server-side assembly of large objects is not possible.
NOT supported: GetBucketNotificationConfiguration.
Presigned URLs: Listed as "Not supported" in the AWS compatibility table, but observed working (client-side SigV4 calculation → standard GetObject). AWS Support has since confirmed ONTAP-layer support (v4 from ONTAP 9.11.1, v2 from 9.16.1) and submitted a doc correction — **not yet published**, so continue to avoid production reliance until it is. See docs/s3ap-compatibility-notes.md for details.

### NetworkOrigin (Immutable After Creation)

- `Internet`: Accessible from anywhere with valid credentials. NOT via S3 Gateway VPC Endpoint.
- `VPC`: Accessible only from bound VPC via S3 Gateway/Interface Endpoint.

### AD-Joined SVM: AD DC Reachability Required for Data Operations

On AD-joined SVMs (CIFS enabled), **every S3 AP data operation** (ListObjectsV2, GetObject, PutObject) requires the SVM to successfully contact its AD domain controllers. ONTAP's multiprotocol identity pipeline performs a `unix→win` reverse lookup for every file system operation when CIFS is enabled — even on UNIX security style volumes accessed via S3 AP.

**Diagnostic pattern**:
| Test | AD DC Reachable | AD DC Unreachable |
|------|:---:|:---:|
| HeadBucket | ✅ | ✅ (false positive) |
| ListObjectsV2 | ✅ | ❌ AccessDenied |
| GetObject | ✅ | ❌ AccessDenied |
| PutObject | ✅ | ❌ AccessDenied |

**Pre-flight check** (recommended for Step Functions workflows on AD-joined SVMs):
```python
# 1. Check if SVM has CIFS enabled (= AD-joined)
cifs = ontap_request("GET", f"/protocols/cifs/services?svm.name={svm}&fields=ad_domain.fqdn")
if cifs["records"]:
    # 2. Verify DC discovery
    domains = ontap_request("GET", f"/protocols/cifs/domains?svm.name={svm}&fields=discovered_servers")
    if not domains["records"] or domains["records"][0].get("discovered_servers") == []:
        raise RuntimeError("AD DC unreachable — S3 AP data operations will fail with AccessDenied")
```

**Why this is confusing**: HeadBucket succeeds because it only validates at the S3 metadata layer. All IAM, AP policy, and network checks also pass. This leads developers to investigate the wrong layers. The root cause is at the ONTAP file-system layer (reverse name-mapping requires AD DC LDAP/Kerberos connectivity).

**When this happens**:
- AD (Managed AD or self-managed) is deleted, stopped, or network-unreachable
- SVM DNS IPs point to old/dead AD DC addresses after AD recreation
- Security Group or NACL blocks AD ports (53/88/389/445/636) from SVM ENIs to DC IPs

> **Note**: This pattern was verified in `fsxn-observability-integrations` (restore-verification workflow). The patterns in this repo work without AD because they typically target pure UNIX SVMs (no CIFS enabled).
