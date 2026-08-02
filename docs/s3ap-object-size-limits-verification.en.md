# FSx for ONTAP S3 Access Points — Measured Object Size Limits

> 🌐 Language: [日本語](./s3ap-object-size-limits-verification.md) | **English**

**Tested**: 2026-08-02
**Region**: ap-northeast-1
**Target**: Amazon FSx for NetApp ONTAP S3 Access Points (FSx for ONTAP S3 AP)
**Goal**: Establish, by measurement, the exact sizes at which uploads fail and the verbatim error messages, following the documentation change of the upload object size limit from 5 GB to 50 GB

---

## Executive Summary

**Both "5 GB" and "50 GB" in the documentation turn out to be binary units.** The measured values:

| Item | Measured (bytes) | Equals | Status |
|------|-----------------:|--------|:---:|
| Single `PutObject` limit | **5,368,709,120** | 5 GiB | ✅ Measured |
| `UploadPart` (one part) limit | **5,368,709,120** | 5 GiB | ✅ Measured |
| Whole-object limit (upload) | **53,687,091,200** | 50 GiB | ✅ Measured |
| `UploadPartCopy` | Documented as Supported but fails with `NoSuchKey` | — | ✅ Measured |

The boundaries are pinned to the byte:

| Size (bytes) | Result |
|-------------:|--------|
| 5,368,709,120 (5 GiB) | ✅ Within the single `PutObject` range |
| 5,368,709,121 (5 GiB + 1) | ❌ `PutObject` returns 400 `EntityTooLarge` |
| 53,687,091,200 (50 GiB) | ✅ Succeeds via multipart (`ContentLength=53687091200`) |
| 53,687,091,201 (50 GiB + 1) | ❌ `CompleteMultipartUpload` returns 400 `EntityTooLarge` |

### The most operationally important finding

**The whole-object limit is not checked by `UploadPart` — only by `CompleteMultipartUpload`.** In the 50 GiB + 1 test, all 11 parts (53,687,091,201 bytes total) uploaded successfully, and the rejection came only **after 590 seconds (about 10 minutes) of transferring the entire payload**.

So an object that exceeds the limit by a single byte still **consumes the full bandwidth and time before failing**. That contrasts with single `PutObject` and `UploadPart`, which reject immediately on Content-Length.

Additionally, the `CompleteMultipartUpload` error **does not include** the `ProposedSize` and `MaxSizeAllowed` fields that `PutObject` and `UploadPart` do return. A client has no way to learn the limit from the error, so discovering it requires trial and error.

> **Design implication**: Applications handling objects above 5 GiB **should validate client-side that the object does not exceed 50 GiB before starting the upload**. There is no service-side pre-flight check; an over-limit object is only detected after the transfer completes.

---

## Test Environment

| Item | Value |
|------|-------|
| Region | ap-northeast-1 |
| File system | FSx for ONTAP, Single-AZ, 128 MBps throughput capacity, 1024 GiB SSD |
| Volume | UNIX security style |
| S3 AP | ONTAP-attached, `FileSystemIdentity` = UNIX (`root`), Internet origin |
| Client | boto3 / botocore (explicit SigV4, retries = 1) |
| Run from | A local workstation outside the Region — rejection is decided on Content-Length, so bandwidth is not a factor |

> Account ID, volume IDs, and access point aliases are omitted per this repository's public-output policy.

---

## Test 1: Single `PutObject` limit

### Method

Pass a zero-filled stream with an explicit Content-Length and let S3 evaluate the limit.

```python
s3.put_object(Bucket=<ap-alias>, Key=key, Body=stream, ContentLength=5*1024**3 + 1)
```

### Result: 5 GiB + 1 byte (5,368,709,121) → rejected

```
RESULT=CLIENT_ERROR elapsed=2.7s
  HTTPStatusCode : 400
  Code           : EntityTooLarge
  Message        : Your proposed upload exceeds the maximum allowed size
  ErrorExtra     : {'ProposedSize': '5368709121', 'MaxSizeAllowed': '5368709120'}
  bytes_streamed : 12582912
```

### What this tells us

- **`MaxSizeAllowed` = 5,368,709,120 = 5 × 1024³ = 5 GiB** (not decimal 5 GB = 5,000,000,000)
- Rejection happens **right after transfer starts** (~12 MB sent, 2.7 s)
- The error code is the standard Amazon S3 `EntityTooLarge`

---

## Test 2: `UploadPart` (single multipart part) limit

### Results

| Requested size | Result | `MaxSizeAllowed` | Bytes actually sent |
|----------------|--------|------------------|---------------------|
| 5,368,709,121 (5 GiB + 1) | 400 `EntityTooLarge` | 5,368,709,120 | 10,485,760 |
| 6,442,450,944 (6 GiB) | 400 `EntityTooLarge` | 5,368,709,120 | 8,388,608 |

```
--- UploadPart 6 GiB: 6442450944 bytes ---
  RESULT=REJECTED status=400
    Code    : EntityTooLarge
    Message : Your proposed upload exceeds the maximum allowed size
    Extra   : {'ProposedSize': '6442450944', 'MaxSizeAllowed': '5368709120'}
```

### What this tells us

The part size limit is also 5 GiB, matching standard Amazon S3 multipart specifications (5 MiB to 5 GiB per part). Building a 50 GiB object therefore requires **at least 10 parts**.

---

## Test 3: `UploadPartCopy` is documented as Supported but fails in practice

[Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html) lists `UploadPartCopy` (same-Region, within the same access point) as Supported. In testing, **every `CopySource` form returned `NoSuchKey`**. `HeadObject` on the same key succeeds and `CopyObject` also succeeds, so this is not a missing-key or permissions problem.

| API | `CopySource` form | Result |
|-----|-------------------|--------|
| `UploadPartCopy` | `{Bucket: <alias>, Key: k}` | ❌ 404 `NoSuchKey` |
| `UploadPartCopy` | `{Bucket: <ap-arn>, Key: k}` | ❌ 404 `NoSuchKey` |
| `UploadPartCopy` | `"<alias>/k"` | ❌ 404 `NoSuchKey` |
| `UploadPartCopy` | `"<ap-arn>/object/k"` | ❌ 404 `NoSuchKey` |
| `CopyObject` | `{Bucket: <alias>, Key: k}` | ✅ Success |
| `CopyObject` | `"<alias>/k"` | ✅ Success |
| `HeadObject` (same key) | — | ✅ Success |

> **Practical impact**: You cannot assemble a large object server-side (replicating a small object into parts and concatenating them). Creating objects above 5 GiB requires transferring real data from a client. This directly affects the cost of validating large-object behaviour, and is worth raising with AWS Support.

---

## Test 4: whole-object limit = 50 GiB (multipart upload)

### Method

A dedicated 150 GiB test volume and a VPC-origin S3 AP were created, and a 50 GiB object was assembled from an in-Region EC2 instance (`c6in.large`) using 10 parts of the maximum 5 GiB part size. The part source was a sparse file (created with `truncate`, `blocks_on_disk=0`), so the sending side consumed no disk.

> **Why VPC origin**: in this VPC the S3 Gateway endpoint is associated with **every route table**, and Internet-origin S3 access points are not reachable through an S3 Gateway endpoint. To avoid changing shared networking in a shared account, the test access point was created with VPC origin.

### Result A: 53,687,091,200 bytes (exactly 50 GiB) → success

```
target=53687091200 (50.000000000 GiB / 53.687091200 GB)
part_size=5368709120 full_parts=10 tail=0 total_parts=10
  part  1/10 cumulative= 5368709120 ( 5.000 GiB)   53s  97 MiB/s
  part  5/10 cumulative=26843545600 (25.000 GiB)  269s  95 MiB/s
  part 10/10 cumulative=53687091200 (50.000 GiB)  538s  95 MiB/s
calling CompleteMultipartUpload ...
RESULT=SUCCESS ContentLength=53687091200 elapsed=1095s
```

### Result B: 53,687,091,201 bytes (50 GiB + 1) → fails at `CompleteMultipartUpload`

```
target=53687091201 (50.000000001 GiB / 53.687091201 GB)
part_size=5368709120 full_parts=10 tail=1 total_parts=11
  part 10/11 size=5368709120 cumulative=53687091200 (50.000 GiB) 536s  96 MiB/s
  part 11/11 size=1          cumulative=53687091201 (50.000 GiB) 590s  87 MiB/s
                                    ^ the 1-byte part is accepted too

calling CompleteMultipartUpload ...
RESULT=COMPLETE_FAILED
    parts_uploaded : 11
    declared_total : 53687091201
    HTTPStatusCode : 400
    Code           : EntityTooLarge
    Message        : Your proposed upload exceeds the maximum allowed size
```

### What this tells us

1. **The limit is exactly 50 GiB = 53,687,091,200 bytes.** The documented "50 GB" is not decimal 50×10⁹ (46.57 GiB).
2. **`UploadPart` performs no cumulative size check.** All 11 parts totalling 50 GiB + 1 were accepted, including the 1-byte tail part.
3. **Rejection happens only at `CompleteMultipartUpload`**, after the full transfer (590 s). No service-side pre-flight check exists.
4. **The `CompleteMultipartUpload` error omits `MaxSizeAllowed` / `ProposedSize`**, which `PutObject` and `UploadPart` do return (Tests 1 and 2). The APIs are not consistent here.
5. **`CompleteMultipartUpload` itself takes a long time.** In the success case uploads finished at 538 s while the whole run took 1095 s, so **assembly alone took about 557 s (over 9 minutes)**. Clients need a generous `read_timeout` (1800 s was used here).
6. Throughput held steady at 95-97 MiB/s across all parts, bounded by the file system's 128 MBps throughput capacity (~122 MiB/s).

### Side observation: zero-filled data consumes almost no capacity

After roughly 29 GB had been sent, the file system's SSD `StorageUsed` had grown by only about 0.3 GiB. The volume was created with `StorageEfficiencyEnabled=False`, but zero blocks appear not to be allocated. Also, as the AWS documentation states, the **volume-level** `StorageUsed` metric does **not** reflect in-progress multipart parts (they are reflected at the parent file system level). Use file-system-level metrics or EC2 `NetworkOut` to monitor progress.

### Resources used (all deleted afterwards)

| Resource | Detail |
|----------|--------|
| FSx for ONTAP volume | 150 GiB, UNIX security style, no tiering |
| S3 AP | VPC origin, `FileSystemIdentity` = UNIX (`root`) |
| EC2 | `c6in.large`, Amazon Linux 2023, IMDSv2 required, public IP (for SSM reachability) |
| IAM | Dedicated role (`AmazonSSMManagedInstanceCore` + an inline policy scoped to the test access point only) |
| Security group | Egress only (no inbound rules) |

Actual cost was about one hour of EC2 (~$0.13) plus negligible capacity charges, since the data was zero-filled. S3 traffic went through the existing S3 Gateway endpoint, so no data transfer charges were incurred.

---

## Reproduction

The probe relies on immediate over-limit rejection, so it **writes no data to the volume**.

```python
# Single PutObject boundary (rejected on Content-Length alone)
import boto3
from botocore.config import Config

s3 = boto3.client("s3", region_name="ap-northeast-1",
                  config=Config(signature_version="s3v4",
                                retries={"max_attempts": 1, "mode": "standard"}))

class ZeroStream:
    """Fixed-length zero stream (no memory or disk cost)."""
    def __init__(self, size): self._size, self._pos, self.sent = size, 0, 0
    def __len__(self): return self._size
    def seek(self, off, whence=0): self._pos = off if whence == 0 else self._pos + off; return self._pos
    def tell(self): return self._pos
    def read(self, amt=None):
        rem = self._size - self._pos
        if rem <= 0: return b""
        n = rem if amt is None or amt < 0 else min(amt, rem)
        self._pos += n; self.sent += n
        return b"\0" * n

size = 5 * 1024**3 + 1          # 5 GiB + 1
s3.put_object(Bucket="<ap-alias>", Key="probe.bin",
              Body=ZeroStream(size), ContentLength=size)
# -> botocore.exceptions.ClientError: EntityTooLarge
#    ProposedSize=5368709121 / MaxSizeAllowed=5368709120
```

---

## Summary

| Constraint | Measured value | Checked when | Error when exceeded |
|------------|----------------|--------------|---------------------|
| Single `PutObject` | **5 GiB** (5,368,709,120) | On Content-Length (immediate) | 400 `EntityTooLarge` + `MaxSizeAllowed` |
| `UploadPart` per part | **5 GiB** (5,368,709,120) | On Content-Length (immediate) | 400 `EntityTooLarge` + `MaxSizeAllowed` |
| Whole object (upload) | **50 GiB** (53,687,091,200) | At `CompleteMultipartUpload` (after full transfer) | 400 `EntityTooLarge` (no `MaxSizeAllowed`) |
| Download | No limit (per AWS documentation) | — | — |
| `UploadPartCopy` | Unusable in practice | — | 404 `NoSuchKey` |

### Recommendations for application developers

- **Validate size before uploading.** Anything above 50 GiB fails only after the transfer completes, so a client-side check is the only early detection.
- Multipart Upload is required above 5 GiB; the per-part limit is also 5 GiB.
- `CompleteMultipartUpload` can take over 9 minutes for a 50 GiB object. Set a generous `read_timeout`.
- Do not rely on server-side assembly of large objects (`UploadPartCopy`).

---

## What we filed with AWS Support (submitted 2026-08-02)

These findings were submitted to AWS Support together with clarification questions
and feature/documentation improvement requests (Service: FSx for NetApp ONTAP,
Category: Feature Request). Case numbers are not recorded in this repository
(tracked in `.private/`).

### Questions

| # | Question |
|---|----------|
| Q1 | Confirm the object limit is exactly 50 GiB (53,687,091,200) and that "5 GB"/"50 GB" in the docs are binary units |
| Q2 | Is `UploadPartCopy` returning `NoSuchKey` a defect, or is a specific `CopySource` form required for FSx-attached access points? |
| Q3 | Is ~557 s for `CompleteMultipartUpload` on a 50 GiB object expected? Does it scale with object size or part count? Recommended client timeout guidance? |
| Q4 | Is the 5 GB figure still in the AWS Transfer Family docs a Transfer Family-specific limit, or a stale value? |
| Q5 | Was the 5 GB → 50 GB change announced anywhere? No What's New entry found, and `doc-history` now redirects |

### Feature and documentation improvement requests

| # | Request |
|---|---------|
| FR-A | **Enforce the object size limit earlier in the multipart flow.** Today a one-byte overage still costs the full transfer (50 GiB and ~10 minutes in our test). Either reject at `UploadPart` once cumulative part size would exceed the limit, or accept an expected total size at `CreateMultipartUpload` for up-front validation |
| FR-B | **Include `ProposedSize` / `MaxSizeAllowed` in the `CompleteMultipartUpload` `EntityTooLarge` response.** `PutObject` and `UploadPart` return them, so the APIs are inconsistent; today the limit is only discoverable by trial and error at 50 GiB per attempt |
| FR-C | **Documentation improvements**: (1) state limits in binary units or exact bytes, (2) document that the check happens at `CompleteMultipartUpload`, (3) document expected `CompleteMultipartUpload` duration and timeout requirements for large objects, (4) publish a change log for limit changes of this kind |

---

## Related Documents

- [S3AP Compatibility Notes](s3ap-compatibility-notes.en.md) — API compatibility and constraints
- [S3AP Performance Considerations](s3ap-performance-considerations.en.md) — size-based processing strategy
- [Lambda / HealthOmics S3 AP Gaps](aws-feature-requests/lambda-healthomics-s3ap-gaps.en.md) — when the limit changed, and open questions for AWS
- [Access point compatibility (AWS)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)
- [Uploading objects (Amazon S3 User Guide)](https://docs.aws.amazon.com/AmazonS3/latest/userguide/upload-objects.html)
