# access-point-policy-cloudfront.json — usage notes

Sample **S3 Access Point resource policy** allowing an Amazon CloudFront distribution (via OAC)
to `GetObject` from an FSx for ONTAP S3 Access Point origin.

The JSON is kept free of comment keys so it can be pasted directly (IAM/S3 AP policy grammar
rejects unknown top-level keys such as `_comment`).

## Before applying

- Replace placeholders: region (`ap-northeast-1`), account ID (`123456789012`), access point
  name (`fsxn-vod-ap`), and the CloudFront distribution ID (`EDFDVBD6EXAMPLE`).
- Use the **S3-Access-Point-style ARN** (`arn:aws:s3:<region>:<account>:accesspoint/<name>`),
  not a bucket-style ARN.
- **Dual-layer authorization**: this AWS-side policy is necessary but not sufficient. The
  **ONTAP file-system identity** (UNIX UID or Windows AD user) mapped for the access point must
  also have file permission to the objects. Both layers must allow the read.

See [cloudfront-oac-notes.md](cloudfront-oac-notes.md) for OAC/SigV4 origin setup, TTL guidance,
and viewer lockdown.
