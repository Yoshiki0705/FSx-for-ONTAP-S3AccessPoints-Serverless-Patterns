# Feature request — Amazon IVS Auto-Record to an S3 Access Point (incl. FSx for ONTAP)

> Constructive feature request template for AWS Support / the IVS service team. Framed as a
> capability request and a set of clarifications, not a complaint. Fill in the placeholders and
> attach the evidence listed at the end. Do not include account IDs, internal IPs, support case
> numbers, or personal names.

## Request summary

Please consider supporting **S3 Access Point alias or ARN** — in particular an access point
associated with **Amazon FSx for NetApp ONTAP** — as an explicit destination for Amazon IVS
Auto-Record, in addition to a standard S3 bucket name in
`RecordingConfiguration.destinationConfiguration.s3.bucketName`.

## Business / technical motivation

- Post-live VOD, editing, QC, approval, and archive workflows commonly need **both** file
  protocols (NFS/SMB) and the S3 API on the same media.
- FSx for ONTAP exposes the same data over NFS/SMB and via an S3 Access Point, which fits media
  workflows well (single authoritative copy usable by editors and by S3-API services).
- Writing IVS recordings directly to an FSx for ONTAP volume would remove the extra copy step
  from the standard S3 bucket into FSx.
- Relevant use cases include live commerce, event streaming, education, sports/fitness, and
  internal broadcast archives.

## Requested clarifications

We would appreciate confirmation on the following:

1. Is specifying an **S3 Access Point alias** in
   `destinationConfiguration.s3.bucketName` a supported configuration for IVS Auto-Record?
2. If the alias points to an **FSx for ONTAP S3 Access Point**, is the behavior supported?
3. If not currently supported, can this be accepted as a **roadmap item / feature request**?
4. Are there plans to support an **S3 Access Point ARN** as a destination?
5. Can AWS provide the recommended policy pattern for the **IVS Service-Linked Role**
   interacting with an **S3 Access Point policy** and **FSx file-system identity** (UNIX/Windows)?
6. If direct recording is not feasible, could AWS publish an official reference architecture for
   **IVS → S3 → FSx for ONTAP** for post-live media workspaces and VOD publishing?

## Evidence to attach

- IVS Recording Configuration API/CLI currently accepts `bucketName`
  ([API reference](https://docs.aws.amazon.com/ivs/latest/LowLatencyAPIReference/API_CreateRecordingConfiguration.html)).
- IVS docs describe recording to an S3 bucket owned by the account
  ([Auto-Record to S3](https://docs.aws.amazon.com/ivs/latest/LowLatencyUserGuide/record-to-s3.html)).
- FSx for ONTAP S3 Access Points support S3 object operations such as
  `PutObject` / `GetObject` / `ListObjectsV2`
  ([FSx for ONTAP S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html)).
- FSx for ONTAP docs already include HLS video streaming via S3 Access Point + CloudFront.
- The proposed architecture is useful for post-live media workspace and VOD publishing.
- **Observed in a test environment (standard S3 AP, not FSx for ONTAP):**
  `create-recording-configuration` with the access point **alias** as `bucketName` reached
  `ACTIVE`, while the access point **ARN** was rejected with
  `ValidationException: bucketName is required to have a maximum length of 63`. This indicates IVS
  validates `bucketName` only as a ≤63-char, bucket-name-shaped string at config-creation time.
  It does **not** confirm recording-time writes through the AP, nor FSx for ONTAP S3 AP behavior
  (config-creation ≠ recording success). Explicit ARN support would require relaxing the 63-char
  `bucketName` constraint. See `direct-recording-experiment.md` for the full observation.
- (Recommended next) the end-to-end result with a live stream and an FSx for ONTAP S3 AP — Recording
  Start/End events, whether `ivs/v1/...` objects are written through the AP, and CloudTrail entries
  for the S3 APIs the IVS service-linked role invokes.
