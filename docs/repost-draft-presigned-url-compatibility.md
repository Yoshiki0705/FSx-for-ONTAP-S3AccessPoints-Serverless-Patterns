# re:Post Draft: FSx for ONTAP S3 Access Points — Presigned URL Behavior Clarification

> **投稿先**: https://repost.aws (Article or Question)
> **カテゴリ**: Amazon FSx for ONTAP, Amazon S3
> **タグ**: FSx for ONTAP, S3 Access Points, Presigned URLs

---

## Title

**FSx for ONTAP S3 Access Points: Presigned URLs listed as "Not supported" but observed working — clarification from AWS Support**

---

## Body

### Summary

The [FSx for ONTAP S3 Access Points compatibility table](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html) lists `Presign — Not supported`. However, testing shows that presigned URLs for `GetObject` operations work successfully. After raising this discrepancy with AWS Support, the following clarification was provided.

### Test Setup

- FSx for ONTAP file system with S3 Access Point attached (Internet-origin)
- ONTAP version: 9.17.1
- Region: ap-northeast-1
- Test file: Parquet file (~250 KB) on the ONTAP volume

### Test Procedure

```bash
# Generate presigned URL (no network request is made here)
PRESIGNED_URL=$(aws s3 presign \
  "s3://<S3_AP_ALIAS>/path/to/file.parquet" \
  --expires-in 3600)

# Use the presigned URL to download the file
curl -o output.parquet "$PRESIGNED_URL"

# Verify the downloaded file
file output.parquet
# output.parquet: Apache Parquet format data
```

### Result

- HTTP 200 returned
- Valid file content downloaded (verified by file type and size)
- No errors or access denied

### Why the table and the behaviour disagree

The signing mechanism explains it, and each step is documented.

1. **Presigning is not a server-side API operation** — [`aws s3 presign`](https://docs.aws.amazon.com/cli/latest/reference/s3/presign.html) is a client-side SigV4 signature calculation. Running it makes no network request to AWS.

2. **Using the presigned URL issues a standard `GetObject`** — per the [presigned URL reference](https://docs.aws.amazon.com/AmazonS3/latest/userguide/ShareObjectPreSignedURL.html), the signature arrives in query-string parameters instead of the `Authorization` header.

3. **Since `GetObject` is listed as Supported**, there is no place left to block a presigned URL. Not without breaking `GetObject` itself.

4. **Why the table reads `Not supported` is `open`** — no published reason was found. Presigning that involves SSE or versioning parameters may fail for its own reasons, so test that case separately.

### Important: Should You Rely on This?

**No.** The compatibility table is the contract, and it says `Not supported`. An operation returning success today is not a commitment.

> Treat the working behaviour as measured, not promised. Nothing published guarantees it across regions or after a service update.

Reasons:
- May change without deprecation notice
- May return inconsistent results across regions or over time
- May stop working after service-side updates
- May behave differently for edge cases

### Recommended Classification

| Feature | Status | Guidance |
|---------|--------|----------|
| GetObject, PutObject, ListObjectsV2 | **Supported** | Build on freely |
| Conditional writes (If-None-Match) | **Blocked** | Do not attempt (returns `NotImplemented`) |
| Presigned URLs | **Not supported (doc)** | Do not rely on; design alternatives |
| ListObjectVersions | **Not supported (doc)** | Use ListObjectsV2 instead |

### Documentation Improvement

AWS Support has escalated this feedback to the FSx for ONTAP service team for documentation clarification, specifically:
- Removing or reframing the "Presign" row (since it's not an API operation)
- Distinguishing between "Not supported + hard-blocked" (returns error) vs. "Not supported + may incidentally work" (no guarantees)

### Practical Implications

For teams building integrations (Athena, Databricks, Snowflake, etc.) against FSx for ONTAP S3 Access Points:

- **Athena**: Uses `ListObjectsV2` + `GetObject` (both supported) — no impact
- **Databricks/Snowflake**: Standard S3 connectors use `ListObjectsV2` + `GetObject` + multipart — no impact for basic read/write. Delta Lake features (vacuum, time-travel) that use `ListObjectVersions` should not be enabled
- **Presigned URL sharing**: If platforms use presigned URLs for shareable downloads, document that it works in testing but is not recommended for production reliance

### Related Resources

- [Access point compatibility — FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)
- [FSx for ONTAP S3 Access Points Serverless Patterns (GitHub)](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)

---

## 投稿前チェックリスト

- [x] AWS アカウント ID が含まれていないこと
- [x] S3 AP エイリアス（実際の値）が含まれていないこと
- [x] IP アドレスが含まれていないこと
- [x] サポートケース番号が含まれていないこと
- [x] サポート担当者名が含まれていないこと
- [x] ファイルパス（実際の値）がマスクされていること
- [x] サポートの回答を根拠にしていないこと（挙動は公開ドキュメントと実測で説明していること）
- [x] 「本番利用は非推奨」の注意書きが含まれていること
