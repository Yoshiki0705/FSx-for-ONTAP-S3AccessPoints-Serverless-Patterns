# ORIGIN_PULL SigV4 × S3 AP alias — Hardware Verification Checklist

🌐 **Language / 言語**: [日本語](cdn-origin-verification-checklist.md) | [English](cdn-origin-verification-checklist.en.md) | [한국어](cdn-origin-verification-checklist.ko.md) | [简体中文](cdn-origin-verification-checklist.zh-CN.md) | [繁體中文](cdn-origin-verification-checklist.zh-TW.md) | [Français](cdn-origin-verification-checklist.fr.md) | [Deutsch](cdn-origin-verification-checklist.de.md) | [Español](cdn-origin-verification-checklist.es.md)

## Purpose

A reproducible procedure to settle, on real hardware, the items marked **to-be-verified (TBV)** in the
[CDN comparison](cdn-comparison.en.md): namely **whether each CDN's SigV4 origin signing works against the
FSx for ONTAP S3 Access Point `accesspoint alias` host the same way it does against a standard S3 bucket**.

Use this to decide whether `content-edge-delivery`'s `DeliveryMode=ORIGIN_PULL` (M1/M2) is viable.
**M3 (PUBLISH_PUSH) does not depend on this verification** (it avoids origin auth).

> **Distinction**: This is a measurement in a specific test environment. Do not treat general S3 behavior or
> a CDN's track record against standard buckets as a guarantee for the S3 AP alias.

---

## 0. Prerequisites

- An FSx for ONTAP file system and an **Internet-origin** S3 Access Point (VPC-origin cannot serve CDNs)
- The S3 AP alias (e.g. `<alias>-ext-s3alias`) and target region
- A test object under the **approved prefix** (e.g. `delivery-approved/test-1mb.bin`)
  - Per the permission-aware principle, do not use ACL-controlled master data for verification
- **Least-privilege IAM credentials** for origin signing (`s3:GetObject` on the target AP only); prefer
  short-lived credentials
- A test host (curl ≥ 7.75 supports `--aws-sigv4`), AWS CLI v2

> **Security**: Never leave access keys in logs, screenshots, or commits during verification. Reference by
> key name, not value (public-repository policy).

---

## 1. Baseline verification (no CDN / most important)

Without a CDN, confirm directly **whether the S3 AP alias host accepts SigV4**. This is the crux common to
all CDNs.

### 1.1 AWS CLI (SDK signing)

```bash
aws s3api get-object \
  --bucket "<alias>-ext-s3alias" \
  --key "delivery-approved/test-1mb.bin" \
  /tmp/out.bin --region <region>
```

- Expected: HTTP 200 and successful object retrieval.
- On failure: isolate IAM / AP policy / ONTAP-side identity (UNIX UID / AD) in the dual-layer authz.

### 1.2 Raw SigV4 (approximates CDN origin signing)

CDNs typically sign origin pulls with a fixed access key via SigV4. `curl --aws-sigv4` approximates this:

```bash
curl -sS -o /tmp/out.bin -w "%{http_code}\n" \
  --aws-sigv4 "aws:amz:<region>:s3" \
  --user "$AWS_ACCESS_KEY_ID:$AWS_SECRET_ACCESS_KEY" \
  -H "x-amz-content-sha256: UNSIGNED-PAYLOAD" \
  "https://<alias>-ext-s3alias.s3.<region>.amazonaws.com/delivery-approved/test-1mb.bin"
```

- **If this returns 200**: the alias host accepts SigV4 like a standard bucket → M1/M4 are likely viable.
- **If it fails**: alias-specific addressing may be the cause → verify each CDN's origin config for host
  format, region, service name (`s3`), and path-style vs virtual-host handling.
- With temporary credentials, add `-H "x-amz-security-token: $AWS_SESSION_TOKEN"`.

### 1.3 Negative checks (reconfirm the spec)

- An unsigned GET returns **403/AccessDenied** (confirms Block Public Access enforcement).
- Presigned URLs are unavailable (cannot generate / unsupported) → viewer tokens use CDN-native mechanisms.

---

## 2. Per-CDN procedures

For each CDN, set "origin = S3 AP alias host" and confirm that a cache-miss origin fetch returns 200.

### 2.1 Amazon CloudFront (M1 / OAC) — reference
- Deploy the `content-edge-delivery` template with `EnableCloudFront=true` (OAC + `SigningProtocol: sigv4`).
- Verify: `curl -I https://<distribution-domain>/delivery-approved/test-1mb.bin` → 200.
- Expected to succeed per the AWS official tutorial (**proven**).

### 2.2 Fastly (M1 / native SigV4)
- Configure the alias host as an S3-compatible private origin; enable SigV4 (region, service `s3`).
- Verify: GET the target key via the Fastly service → 200. Check that the alias virtual-host form is signed
  correctly by Fastly's SigV4 implementation.

### 2.3 Cloudflare (M2 / Workers signing)
- Implement SigV4 in a Worker and fetch the alias host with a signed request (when using the S3 AP directly,
  not R2). Verify GET via the Worker → 200; check signed headers / payload hash handling.

### 2.4 Akamai (M1 / Cloud Access Manager)
- Configure AWS signing in Cloud Access Manager and set the alias host via Origin Characteristics.
- Verify GET via the Akamai property → 200; confirm signing applies on the AP alias host.

### 2.5 Bunny.net (M1 / S3 origin pull)
- Set the Pull Zone origin to the alias host using the AWS S3 origin type. Verify GET via the Pull Zone → 200.

### 2.6 Google Cloud CDN / Media CDN (M1 / private S3 origin)
- Configure the alias host with private S3-compatible origin SigV4 auth. Verify GET via Media CDN → 200;
  also check the cross-cloud egress path.

---

## 3. Pass/fail criteria

| Result | Condition |
|--------|-----------|
| **PASS** | Baseline 1.2 is 200 AND a cache-miss GET via the CDN is 200; viewer tokens work via CDN-native mechanism |
| **CONDITIONAL** | CDN GET is 200 but requires extra config (e.g. path-style) or constraints (specific headers) |
| **FAIL** | SigV4 to the alias host does not work on the CDN; a workaround is needed (M2 signing / M4 proxy / switch to M3) |
| **BLOCKED** | Prerequisites (Internet-origin, IAM, test object) are not in place; cannot verify |

---

## 4. Security / governance checks during verification

- [ ] Test objects only under `delivery-approved/` (no ACL-controlled master)
- [ ] Origin-signing IAM limited to `s3:GetObject` on the target AP
- [ ] No long-lived keys left at edge/config (prefer short-lived; revoke after verification)
- [ ] No access keys, real alias values, or account IDs in logs/screenshots/commits
- [ ] Viewer tokens use CDN-native mechanisms (no S3 presigned URLs)
- [ ] Clean up temporary resources (distributions, pull zones, etc.) created for verification

---

## 5. Result recording table (evidence)

| CDN | Mechanism | Config done | 1.2 baseline | CDN GET | Viewer token | Result | Evidence (HTTP status/headers/timestamp) | Date | Role |
|-----|-----------|:---:|:---:|:---:|:---:|:---:|---|---|---|
| CloudFront | M1/OAC |  |  |  |  |  |  |  | Storage |
| Fastly | M1 |  |  |  |  |  |  |  | Storage |
| Cloudflare | M2 |  |  |  |  |  |  |  | Storage |
| Akamai | M1 |  |  |  |  |  |  |  | Storage/Partner |
| Bunny.net | M1 |  |  |  |  |  |  |  | Storage |
| Google Media CDN | M1 |  |  |  |  |  |  |  | Storage |

> Recording note: placeholder alias values, account IDs, IPs (`<alias>-ext-s3alias`, `123456789012`). Treat
> results as measurements in a specific test environment, not as general guarantees.

---

## 6. Feed results back

- Reflect confirmed results into the [CDN comparison](cdn-comparison.en.md) section 3 "S3 AP-specific TBV"
  column and 4.1 "to be verified" (TBV → measured result).
- For CDNs that FAIL, recommend `DeliveryMode=PUBLISH_PUSH` (M3) as the path in `content-edge-delivery`.

## Related docs

- [CDN/Edge delivery comparison](cdn-comparison.en.md)
- [content-edge-delivery UC](../solutions/edge/content-delivery/README.en.md)
- [S3AP compatibility notes](s3ap-compatibility-notes.md)
