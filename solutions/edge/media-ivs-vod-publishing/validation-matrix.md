# Validation Matrix — Amazon IVS × FSx for ONTAP S3 AP

Status legend:

- **Supported** — documented and supported by AWS official docs.
- **Candidate** — components are supported individually; the specific combination is plausible
  but should be confirmed in your environment.
- **Experimental** — no AWS documentation states this is supported; validate independently and
  label results as "observed in this test environment," not "officially supported."
- **Not supported** — documented as unsupported, or a known hard constraint.
- **Unknown** — insufficient public evidence; treat as needing validation.

| # | Integration point | Status | Required validation | Expected risk | Source reference | Notes |
|---|-------------------|--------|---------------------|---------------|------------------|-------|
| 1 | IVS Auto-Record to standard S3 bucket | **Supported** | Create RecordingConfiguration, attach to channel, stream briefly, confirm `ivs/v1/...` objects | Low | [IVS Auto-Record to S3](https://docs.aws.amazon.com/ivs/latest/LowLatencyUserGuide/record-to-s3.html) | Channel, RecordingConfiguration, and S3 must be same-region |
| 2 | IVS RecordingConfiguration with **FSx for ONTAP S3 AP alias** as `bucketName` | **Not supported (confirmed by AWS)** | None needed — settled. See [direct-recording-experiment.md](direct-recording-experiment.md) | N/A — do not use | [IVS Auto-Record to S3](https://docs.aws.amazon.com/ivs/latest/LowLatencyUserGuide/record-to-s3.html) (supported destination is a **standard S3 bucket**); [CreateRecordingConfiguration API](https://docs.aws.amazon.com/ivs/latest/LowLatencyAPIReference/API_CreateRecordingConfiguration.html) | The **AWS service team confirmed** S3 Access Points (incl. FSx for ONTAP) are **not** a supported IVS Auto-Record destination. The AP **alias** is accepted at config creation only because `bucketName` is validated as a bucket-name-shaped string (≤63 chars); recording-time writes are unsupported (observed `Recording Start Failure`, no `ivs/v1/...` objects, even with the IVS SLR granted on the AP). **Use IVS → standard S3 → FSx for ONTAP.** Feature request raised with AWS (no roadmap) |
| 3 | S3 → FSx via NFS/SMB | **Supported** | Mount volume from ECS/Batch worker; copy HLS package; verify readable by editors | Low | [FSx for ONTAP multiprotocol access](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/managing-volumes.html) | Preserves file semantics for editors/MAM |
| 4 | S3 → FSx via S3 AP `PutObject` | **Supported** (with constraints) | Put objects through the AP; verify size ≤ 5 GB or use multipart; confirm objects visible via NFS/SMB | Medium — many small segments = many API calls; 5 GB single-put limit | [FSx for ONTAP S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) | Internet-origin AP needs a VPC-external worker or NAT |
| 5 | FSx for ONTAP S3 AP → CloudFront | **Supported** | Configure CloudFront OAC to S3 AP origin; verify SigV4 GET of `.m3u8`/segments | Low–Medium | [Restricting access to an S3 origin (OAC)](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html) | An AWS tutorial covers HLS delivery from FSx for ONTAP via S3 AP + CloudFront |
| 6 | FSx for ONTAP S3 AP → Lambda | **Supported** | Lambda reads/writes via S3 AP (Internet-origin → VPC-external Lambda) | Low | [FSx for ONTAP S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) | Post-processing, metadata extraction |
| 7 | FSx for ONTAP S3 AP → Athena / Glue / Bedrock | **Supported** | Point Glue crawler / Athena / Bedrock KB at S3 AP; verify catalog + query | Low–Medium | [FSx for ONTAP S3 access points service integrations](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) | Metadata catalog, search, GenAI over recordings |

## Interpretation

- The **recommended path** (rows 1, 3–7) is composed entirely of **Supported** integration
  points. This is what the README and blogs present as the recommended architecture — and, with
  row 2 now confirmed unsupported, it is the **only** supported way to land IVS recordings on FSx for ONTAP.
- Row 2 (**direct IVS → FSx for ONTAP S3 AP recording**) is **Not supported (confirmed by the AWS
  service team)**. Do not attempt it in production; route recordings through a standard S3 bucket first.

## Resolved by AWS (was: open questions)

- **Is an S3 Access Point alias/ARN a supported value for `destinationConfiguration.s3.bucketName`?**
  No. The supported destination is a **standard Amazon S3 bucket**. The alias only passes config-time
  validation because `bucketName` is checked as a bucket-name-shaped string (≤63 chars).
- **If the alias points to an FSx for ONTAP S3 AP, is behavior supported or best-effort?** Not
  supported — recording-time writes through the access point are not supported.
- **Which IAM / AP policy / ONTAP identity does the IVS Service-Linked Role require to write through
  an S3 AP?** None makes it work today; the destination itself is unsupported.

The remaining item is a **feature request** (direct S3 Access Point recording + S3 AP ARN as a
destination) recorded with the AWS service team — **no roadmap**. Correspondence is kept privately,
outside this public repository.
