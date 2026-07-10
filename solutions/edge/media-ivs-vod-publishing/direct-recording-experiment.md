# Direct Path Experiment — IVS Recording directly to an FSx for ONTAP S3 Access Point

> **Status: RESOLVED — Not supported (confirmed by the AWS service team).**
> AWS Support, after confirming with the Amazon IVS service team, stated that **Amazon S3 Access
> Points — including those backed by Amazon FSx for NetApp ONTAP — are not a supported IVS
> Auto-Record recording destination**. The access point alias is accepted at configuration
> creation only because it is validated as a bucket-name-shaped string; recording-time writes
> through the access point are a separate, unsupported path. This matches the recording-time
> failure observed below. **Use the recommended path (IVS → standard Amazon S3 bucket → FSx for
> ONTAP), which is the supported destination.** The sections below are retained as the
> investigation record that led to this confirmation.

## Resolution (AWS service team confirmation)

- **Supported destination**: IVS Auto-Record supports recording to a **standard Amazon S3 bucket**.
  Destinations other than a standard S3 bucket — including S3 Access Points and FSx for ONTAP S3
  access points — are **not supported**. AWS does not separately document every unsupported
  destination; the supported-destination statement in the docs is the boundary to rely on.
- **Why config-creation still "succeeds"**: `destinationConfiguration.s3.bucketName` is validated
  only as a bucket-name-shaped string (≤63 chars), so an access point **alias** passes and the
  RecordingConfiguration reaches `ACTIVE`. That is **not** an indication of support.
- **No configuration makes it work today**: because the destination itself is unsupported, there is
  **no access point policy, service-linked role, or FileSystemIdentity configuration** that will make
  recording-time writes succeed. The live-stream write-through test is not worth pursuing further.
- **Feature request**: the use case (direct recording to an S3 Access Point, and accepting an S3
  Access Point **ARN** as a destination — which would require relaxing the 63-char `bucketName`
  limit) has been raised with the service team. There is **no roadmap or timeline** to share.
- **Recommended action**: continue building on the supported path (IVS → standard S3 → FSx for ONTAP),
  which is exactly the production architecture this pattern already uses.

> Provenance (support case reference, correspondence, dates) is kept in `.private/`, not in this
> public repository.

## Hypothesis

`RecordingConfiguration.destinationConfiguration.s3.bucketName` accepts a bucket **name**.
An S3 Access Point **alias** can substitute for a bucket name in S3 *object* operations. It is
unknown whether IVS (and its Service-Linked Role) treats an S3 AP alias as a valid destination,
because IVS may perform bucket-ownership validation, region checks, and bucket-level API calls
that an S3 AP does not serve.

## Prerequisites

- An FSx for ONTAP file system with an **S3 Access Point** created on a volume, in the **same
  region** as the IVS channel.
- The S3 AP alias (placeholder: `<FSX_S3_ACCESS_POINT_ALIAS>`).
- Permission to create IVS resources and read CloudTrail.
- A test streamer/encoder (OBS, ffmpeg, or IVS Broadcast SDK) — short test stream only.

## Step 1 — Attempt to create the Recording Configuration

```bash
aws ivs create-recording-configuration \
  --name ivs-fsx-s3ap-direct-test \
  --destination-configuration '{
    "s3": {
      "bucketName": "<FSX_S3_ACCESS_POINT_ALIAS>"
    }
  }'
```

Record the outcome:

- Does the configuration reach **`ACTIVE`**? (`aws ivs get-recording-configuration --arn <arn>`)
- If it becomes **`CREATE_FAILED`**, capture the exact failure reason from the API response and
  from CloudTrail. Common candidates: bucket does not exist / bucket ownership validation /
  region mismatch / access denied on a bucket-level API.

> IVS provisioning of a Recording Configuration performs validation against the destination.
> A failure here is itself a meaningful result: it likely means an S3 AP alias is not accepted.

## Step 2 — Attach to a channel

```bash
aws ivs create-channel \
  --name ivs-fsx-s3ap-direct-test-channel \
  --recording-configuration-arn <RECORDING_CONFIGURATION_ARN>
```

- Confirm the channel is created with the recording configuration attached.

## Step 3 — Short live test + recording lifecycle

- Stream for 1–2 minutes to the channel ingest endpoint.
- Observe the EventBridge `IVS Recording State Change` events:
  - `Recording Start`
  - `Recording End`
  - `Recording Start Failure` / `Recording End Failure` (capture `recording_status_reason`)

See [samples/eventbridge-recording-ended.json](samples/eventbridge-recording-ended.json) for
the expected event shape.

## Step 4 — Inspect the FSx-resident destination

Through the same S3 AP (or via NFS/SMB on the volume), check whether the recording prefix was
created:

```bash
aws s3api list-objects-v2 \
  --bucket <FSX_S3_ACCESS_POINT_ALIAS> \
  --prefix "ivs/v1/" \
  --max-keys 50
```

- Was the `ivs/v1/<account_id>/<channel_id>/...` prefix created on the FSx volume?
- Were HLS manifests (`.m3u8`), segments (`.ts`/`.m4s`), thumbnails, and the metadata/events
  JSON written?

## Step 5 — CloudTrail / API behavior review

Using CloudTrail, identify which S3 APIs IVS (or its Service-Linked Role) invoked against the
destination, and record:

- `AccessDenied` occurrences and on which API.
- Any **bucket-level** API calls (these are the most likely to fail against an S3 AP).
- Whether/how the **IVS Service-Linked Role** policy was generated or used.
- Any **region mismatch** or **bucket ownership validation** errors.
- If **multipart upload** APIs were used, cross-check against FSx for ONTAP S3 AP multipart
  support/limits.

## Step 6 — Decide the public label

| Observation | Public label to use |
|-------------|---------------------|
| Config `CREATE_FAILED`, or recording fails | **Not supported (observed)** — document the failure reason |
| Config ACTIVE + recording written successfully | **Experimental** — "Observed working in this test environment, not documented as officially supported" |
| Mixed / intermittent | **Unknown** — document what varied |

> **Rule (superseded by the Resolution above):** during the investigation, no observation was to be
> labeled **Supported** without AWS documentation. This is now settled — the AWS service team
> confirmed the destination is **Not supported**, which is the label the README uses.

## Observed results (this test environment — not official support)

> Ran in a **test AWS account**, region `ap-northeast-1`. **This tested a STANDARD S3 Access Point
> (on a regular S3 bucket), NOT an FSx for ONTAP S3 Access Point**, and only the
> RecordingConfiguration **creation/validation** step — **no live stream was run**. Treat as an
> **Experimental** signal, not as documented support.

| Test | Input (`destinationConfiguration.s3.bucketName`) | Result |
|------|--------------------------------------------------|--------|
| Alias as `bucketName` (standard S3 AP) | S3 AP **alias** (`<name>-s3alias`, ≤63 chars) | RecordingConfiguration created and reached **`state: ACTIVE`** |
| ARN as `bucketName` (standard S3 AP) | S3 AP **ARN** (`arn:aws:s3:<region>:<account-id>:accesspoint/<name>`, 78 chars) | **Rejected** — `ValidationException: ...bucketName is required to have a maximum length of 63, found 78` |
| Alias as `bucketName` (**FSx for ONTAP S3 AP**) | FSx-for-ONTAP S3 AP **alias** (`<name>-ext-s3alias`, ≤63 chars) | RecordingConfiguration created and reached **`state: ACTIVE`** (config-creation only; deleted after) |
| ARN as `bucketName` (**FSx for ONTAP S3 AP**) | FSx-for-ONTAP S3 AP **ARN** (68 chars) | **Rejected** — `ValidationException` (consistent ≤63-char `bucketName` limit) |

> **Update (advanced observation)**: a later run reused an **existing FSx for ONTAP S3 Access Point
> attachment** (not a standard S3 AP) and confirmed its **alias** is likewise accepted by IVS at
> config-creation time and reaches `ACTIVE`; the **ARN** is rejected on the 63-char limit. This was
> config-creation validation only — **no channel attach, no live stream, no writes to the FSx for
> ONTAP volume** — so recording-time behavior and dual-layer authorization remain **unverified**.

### Interpretation

- IVS validates `bucketName` as a **bucket-name-shaped string with a 63-character maximum**. An S3
  Access Point **alias** is ≤63 chars and shaped like a valid name, so it **passed config-time
  validation and reached ACTIVE**. An Access Point **ARN** (78 chars) is rejected purely on length.
- **ACTIVE at config-creation does NOT prove recording works.** IVS validates the destination when
  the configuration is created, but the actual object writes happen during a live stream (Recording
  Start/End) via the IVS service-linked role. This test did **not** run a live stream, so recording
  success is **unverified**.
- Both a **standard S3 AP** and an **FSx for ONTAP S3 AP** alias passed config-creation and reached
  ACTIVE (see the advanced observation above). However, an FSx for ONTAP S3 AP adds dual-layer
  authorization (AP policy **and** ONTAP file-system identity) and a different backing store; the
  **recording-time** behavior (actual writes through the AP during a live stream) is still **untested**
  for both.

> **Update (recording-time write-through — observed FAILURE)**: a later run went past config creation
> to an actual live stream. With a channel whose recording destination was an **FSx for ONTAP S3 AP
> alias**, the stream session recorded a **`Recording Start Failure`** (IVS Recording State Change) at
> stream start, and **no `ivs/v1/...` objects were written** to the access point. This happened **even
> with an access point policy granting the IVS RecordToS3 service-linked role** write access
> (`s3:PutObject`/`GetObject`/`ListBucket`/`AbortMultipartUpload`/`ListMultipartUploadParts`). The
> event `code` was empty, so no detailed public reason surfaced.
>
> Note on the AP policy: `s3:GetBucketLocation` and `s3:ListBucketMultipartUploads` are **rejected by
> the FSx for ONTAP S3 AP policy** ("MalformedPolicy: invalid action") — use only the supported subset.

### Public label decision

Config-creation acceptance is a validation artifact (bucket-name-shaped string ≤63 chars), the
**recording-time write-through was observed to FAIL** (`Recording Start Failure`, no objects
written) for an FSx for ONTAP S3 AP alias, and the **AWS service team has now confirmed the
destination is not supported**. The README labels this **Not supported (confirmed by AWS)**. Use the
recommended path (IVS → standard S3 bucket → FSx for ONTAP) for real work. **Do not mark Supported.**

### Observed status summary

| Stage | FSx for ONTAP S3 AP alias | Notes |
|-------|---------------------------|-------|
| Config creation (alias) | **ACTIVE** | Also ACTIVE for a standard S3 AP alias |
| Config creation (ARN) | **Rejected** | `bucketName` max length 63 |
| Recording-time write-through | **Recording Start Failure** | No `ivs/v1/...` objects written; SLR granted on AP; empty reason code |

### Resolved by AWS

- **Is recording-time Auto-Record to an S3 Access Point (incl. FSx for ONTAP) supported?** **No** —
  confirmed by the AWS service team. No AP policy / service-linked-role / FileSystemIdentity /
  network-origin configuration makes it work today.
- **Feature request raised**: direct recording to an S3 Access Point, and accepting an S3 Access
  Point **ARN** as a destination (relaxing the 63-char `bucketName` limit). **No roadmap/timeline**
  is available.

### Remaining follow-up (non-blocking)

- AWS asked for the exact `recording_status_reason` value from the observed `Recording Start Failure`
  event, plus what diagnostic detail would have helped identify the destination issue faster, to
  evaluate improving the reason code. In this test the event `code` was **empty**. This feedback is
  tracked privately (`.private/`) and does not change the supported/not-supported outcome.

> **Support status**: Resolved. The AWS service team confirmed S3 Access Points (including FSx for
> ONTAP) are **not** a supported IVS Auto-Record destination; the supported destination is a **standard
> Amazon S3 bucket**. The feature request is recorded with the team (no roadmap). Correspondence is kept
> in `.private/`, outside this repository.

## Cleanup

```bash
# Detach + delete channel and recording configuration to avoid ongoing charges
aws ivs delete-channel --arn <CHANNEL_ARN>
aws ivs delete-recording-configuration --arn <RECORDING_CONFIGURATION_ARN>
```

## Evidence to attach to the AWS feature request

- The `create-recording-configuration` result (ACTIVE or the exact failure reason).
- EventBridge recording events (Start / End / Failure) captured.
- CloudTrail entries showing the S3 APIs IVS invoked and any AccessDenied / bucket-level calls.
- Whether the `ivs/v1/...` prefix and HLS artifacts appeared on the FSx volume.
