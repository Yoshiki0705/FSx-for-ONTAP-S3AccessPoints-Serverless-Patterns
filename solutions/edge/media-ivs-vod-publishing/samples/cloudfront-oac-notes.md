# CloudFront + OAC notes — FSx for ONTAP S3 Access Point origin

These notes describe how to front an FSx for ONTAP **S3 Access Point** with **Amazon
CloudFront** for HLS VOD delivery. An AWS tutorial documents HLS adaptive-bitrate delivery
from FSx for ONTAP via S3 Access Point + CloudFront; this pattern reuses that mechanism for
IVS-originated recordings.

## Origin model

- The CloudFront origin is the **S3 endpoint for the access point** (not a bucket-website
  endpoint, and not the S3 Gateway VPC Endpoint).
- Use **Origin Access Control (OAC)**. CloudFront signs origin requests with **SigV4** so the
  access point can authorize the request. (Legacy OAI is for buckets, not the recommended
  path here — use OAC.)
- The S3 Access Point resource policy must allow the CloudFront distribution as principal.
  See [access-point-policy-cloudfront.json](access-point-policy-cloudfront.json).

## Dual-layer authorization (important)

FSx for ONTAP S3 AP enforces **two** layers:

1. **AWS side** — IAM identity policy + S3 Access Point resource policy (the OAC/SigV4 request
   must be allowed here).
2. **ONTAP side** — the file-system identity (UNIX UID or Windows AD user) mapped for the
   access point must have file permission to the objects.

Both must allow the read, or delivery fails. Confirm the ONTAP-side identity mapping when the
AWS-side policy looks correct but CloudFront still receives 403s.

## Cache TTL guidance

| Object type | Extension | Suggested TTL | Reason |
|-------------|-----------|---------------|--------|
| Media playlist / master manifest | `.m3u8` | **Short** (e.g. seconds–minutes) | Playlist can change; VOD publish/updates must propagate |
| Media segments | `.ts`, `.m4s` | **Long** (e.g. hours–days) | Segments are immutable once written |
| Init segment | `.mp4` / init | Long | Immutable |

- Enable **Origin Shield** to collapse origin fetches and reduce load on FSx for ONTAP
  (throughput is shared with NFS/SMB/S3AP editing traffic).
- Segments are immutable — after publishing new content, invalidate only the `*.m3u8` path,
  not the segments.

## Viewer access lockdown

- **Do not** let viewers reach the S3 Access Point directly. FSx for ONTAP S3 AP enforces
  Block Public Access and requires SigV4; expose only the CloudFront distribution to viewers.
- **Presigned URLs are not supported** on FSx for ONTAP S3 AP — use CloudFront-native
  **signed URLs / signed cookies** for controlled/authenticated VOD.
- For region-bound content, apply CloudFront **geo-restriction**.

## Checklist

- [ ] CloudFront distribution created with OAC targeting the S3 AP origin.
- [ ] S3 AP resource policy allows the CloudFront distribution (SourceArn condition).
- [ ] ONTAP file-system identity for the AP can read the VOD objects.
- [ ] `.m3u8` short TTL, segments long TTL, Origin Shield enabled.
- [ ] Viewer auth via CloudFront signed URLs/cookies (no Presigned URLs).
- [ ] Geo-restriction applied where required.

## References

- [Restricting access to an Amazon S3 origin (OAC)](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html)
- [FSx for ONTAP S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html)
- [Serving private content with signed URLs and cookies](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/PrivateContent.html)
