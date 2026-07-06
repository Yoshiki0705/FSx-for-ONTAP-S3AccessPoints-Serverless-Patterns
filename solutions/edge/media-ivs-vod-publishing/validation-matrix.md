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
| 2 | IVS RecordingConfiguration with **FSx for ONTAP S3 AP alias** as `bucketName` | **Experimental** (partial observation) | See [direct-recording-experiment.md](direct-recording-experiment.md): remaining unknowns are live-stream recording success, IVS SLR write path through the AP, and the FSx for ONTAP AP (dual-layer auth) case | High — recording-time write + FSx for ONTAP dual-layer auth unverified | [CreateRecordingConfiguration API](https://docs.aws.amazon.com/ivs/latest/LowLatencyAPIReference/API_CreateRecordingConfiguration.html) accepts `destinationConfiguration.s3.bucketName`; [S3 AP alias usage](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-points-alias.html) | **Observed (test env, standard S3 AP)**: config with the AP **alias** reached `ACTIVE`; the AP **ARN** was rejected (`bucketName` max length 63). Config-creation ≠ recording success; FSx for ONTAP AP + live-stream recording untested → **stays Experimental, not Supported** |
| 3 | S3 → FSx via NFS/SMB | **Supported** | Mount volume from ECS/Batch worker; copy HLS package; verify readable by editors | Low | [FSx for ONTAP multiprotocol access](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/managing-volumes.html) | Preserves file semantics for editors/MAM |
| 4 | S3 → FSx via S3 AP `PutObject` | **Supported** (with constraints) | Put objects through the AP; verify size ≤ 5 GB or use multipart; confirm objects visible via NFS/SMB | Medium — many small segments = many API calls; 5 GB single-put limit | [FSx for ONTAP S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) | Internet-origin AP needs a VPC-external worker or NAT |
| 5 | FSx for ONTAP S3 AP → CloudFront | **Supported** | Configure CloudFront OAC to S3 AP origin; verify SigV4 GET of `.m3u8`/segments | Low–Medium | [Restricting access to an S3 origin (OAC)](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html) | An AWS tutorial covers HLS delivery from FSx for ONTAP via S3 AP + CloudFront |
| 6 | FSx for ONTAP S3 AP → Lambda | **Supported** | Lambda reads/writes via S3 AP (Internet-origin → VPC-external Lambda) | Low | [FSx for ONTAP S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) | Post-processing, metadata extraction |
| 7 | FSx for ONTAP S3 AP → Athena / Glue / Bedrock | **Supported** | Point Glue crawler / Athena / Bedrock KB at S3 AP; verify catalog + query | Low–Medium | [FSx for ONTAP S3 access points service integrations](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) | Metadata catalog, search, GenAI over recordings |

## Interpretation

- The **recommended path** (rows 1, 3–7) is composed entirely of **Supported** integration
  points. This is what the README and blogs present as the recommended architecture.
- Row 2 (**direct IVS → FSx for ONTAP S3 AP recording**) is the only **Experimental** element. Even if
  it appears to work in a test environment, it must be labeled Experimental in public docs
  until AWS documents support. See the experiment plan for the exact evidence to collect.

## Open questions carried into the AWS feature request

- Is an S3 Access Point alias/ARN a supported value for
  `RecordingConfiguration.destinationConfiguration.s3.bucketName`?
- If the alias points to an FSx for ONTAP S3 AP, is behavior supported or best-effort?
- Which IAM / AP policy / ONTAP file-system identity pattern does the IVS Service-Linked Role
  require to write recordings through an S3 AP?

These are tracked in [support-request/feature-request-en.md](support-request/feature-request-en.md).
