# Supported Path — IVS → S3 → FSx for ONTAP → S3 Access Point → CloudFront

> **Status: Recommended.** Every component below is documented and supported by AWS
> individually. This is the path to present to users, teams, and organizations.

## Flow

```text
Amazon IVS
  -> Auto-Record to S3 bucket
  -> EventBridge "IVS Recording State Change" (Recording End)
  -> Step Functions
  -> Lambda / ECS / Batch / DataSync
  -> FSx for ONTAP volume
  -> S3 Access Point
  -> CloudFront with OAC
  -> VOD viewers
```

## Why this composition is safe

- **IVS Auto-Record → S3 bucket** is the documented, supported recording destination.
- **S3 → FSx for ONTAP** is a standard copy/sync (S3 AP `PutObject`, or NFS/SMB via
  ECS/Batch/DataSync).
- **FSx for ONTAP S3 AP → CloudFront** has a documented tutorial for HLS delivery via S3 AP + CloudFront
  with OAC/SigV4.
- No undocumented behavior is required anywhere in the chain.

## Implementation samples in this pattern

| Sample | File | Purpose |
|--------|------|---------|
| EventBridge event | [samples/eventbridge-recording-ended.json](samples/eventbridge-recording-ended.json) | Recording End event shape to build the rule/trigger against |
| Step Functions ASL | [samples/stepfunctions-state-machine.asl.json](samples/stepfunctions-state-machine.asl.json) | Orchestration of validate → list → copy → verify → catalog → invalidate |
| Deployable handler | [functions/publish/handler.py](functions/publish/handler.py) | The actual Lambda deployed by `template.yaml` — validates Recording End, ingests to FSx for ONTAP S3 AP, validates the master manifest, runs Human Review, writes the VOD publish manifest |
| Lambda snippet | [samples/lambda-copy-handler.py](samples/lambda-copy-handler.py) | Minimal illustrative copy snippet (S3 AP PutObject vs NFS/SMB); not the deployed handler |
| AP policy | [samples/access-point-policy-cloudfront.json](samples/access-point-policy-cloudfront.json) | S3 AP resource policy allowing the CloudFront OAC principal |
| CloudFront notes | [samples/cloudfront-oac-notes.md](samples/cloudfront-oac-notes.md) | OAC + SigV4 origin, TTL guidance, viewer lockdown |

## Step Functions stages

1. **Validate IVS recording path** — confirm the event is `Recording End` and extract
   `recording_s3_bucket_name` + `recording_s3_key_prefix`.
2. **List S3 objects under the recording prefix** — enumerate the HLS package.
3. **Copy/sync HLS package to FSx for ONTAP** — Lambda (small) or ECS/Batch/DataSync (large).
4. **Validate manifest exists** — confirm the master `.m3u8` landed on FSx.
5. **(Optional) Update metadata catalog** — Glue/DynamoDB entry for the VOD asset.
6. **(Optional) Invalidate CloudFront playlist path** — refresh the short-TTL playlist.
7. **Mark job completed** — emit success (SNS / metric).

## Choosing the copy/sync compute

| Package characteristics | Recommended worker | Write method |
|-------------------------|--------------------|--------------|
| Small (few objects, < a few hundred MB) | Lambda | S3 AP `PutObject` |
| Large / many small segments | ECS or AWS Batch | NFS/SMB mount |
| Bulk / scheduled bulk transfer | AWS DataSync | DataSync task to FSx |

> Lambda cannot mount NFS/SMB to FSx for ONTAP directly; for file-protocol writes use
> ECS/Batch with the volume mounted, or DataSync.

## Delivery

- Configure CloudFront with **Origin Access Control (OAC)** to the S3 Access Point origin;
  CloudFront signs origin requests with **SigV4**.
- The S3 AP resource policy must allow the CloudFront service principal / distribution
  (see [samples/access-point-policy-cloudfront.json](samples/access-point-policy-cloudfront.json)).
- Use CloudFront-native **signed URLs / signed cookies** for controlled VOD (Presigned URLs
  are not supported by FSx for ONTAP S3 AP).
- TTL: short for `.m3u8` playlists, long for immutable `.ts` / `.m4s` segments.

## Operational notes

- Start downstream processing **only after Recording End** — manifests/segments are not
  guaranteed complete before then.
- Large packages: watch FSx provisioned throughput (shared with editing/QC); consider a
  FlexCache volume as the delivery-origin source.
- The deployable handler (`functions/publish/handler.py`) **auto-selects** the write method by
  object size: `PutObject` for small objects and **streaming multipart**
  (`S3ApHelper.streaming_download` + `multipart_upload`, low memory) above `MULTIPART_THRESHOLD_MB`
  (default 100MB). Objects above `MAX_LAMBDA_INGEST_GB` (default 20GB) are skipped — use DataSync
  or an ECS/Batch NFS/SMB worker for those.
- The `samples/` snippets are **illustrative PoC**, not production-hardened. Add idempotency
  (`shared/idempotency_checker.py`) and error handling before production use.
