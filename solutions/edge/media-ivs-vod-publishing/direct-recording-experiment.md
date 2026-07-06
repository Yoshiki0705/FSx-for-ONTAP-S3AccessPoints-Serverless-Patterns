# Direct Path Experiment — IVS Recording directly to an FSx for ONTAP S3 Access Point

> **Status: Experimental / Not documented as supported.**
> This plan tests whether an Amazon IVS Recording Configuration can point directly at an
> FSx for ONTAP S3 Access Point alias. AWS documentation does **not** state this is supported.
> **Do not describe this as "Supported" in public docs based on a test result alone.** If it
> appears to work, describe it as *"Observed working in this test environment, not documented
> as officially supported."*

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

> **Rule:** regardless of a successful observation, unless AWS documentation explicitly states
> support, the README must say **Experimental**, never **Supported**.

## Observed results (this test environment — not official support)

> Ran in a **test AWS account**, region `ap-northeast-1`. **This tested a STANDARD S3 Access Point
> (on a regular S3 bucket), NOT an FSx for ONTAP S3 Access Point**, and only the
> RecordingConfiguration **creation/validation** step — **no live stream was run**. Treat as an
> **Experimental** signal, not as documented support.

| Test | Input (`destinationConfiguration.s3.bucketName`) | Result |
|------|--------------------------------------------------|--------|
| Alias as `bucketName` | S3 AP **alias** (`<name>-s3alias`, ≤63 chars) | RecordingConfiguration created and reached **`state: ACTIVE`** |
| ARN as `bucketName` | S3 AP **ARN** (`arn:aws:s3:<region>:<account-id>:accesspoint/<name>`, 78 chars) | **Rejected** — `ValidationException: ...bucketName is required to have a maximum length of 63, found 78` |

### Interpretation

- IVS validates `bucketName` as a **bucket-name-shaped string with a 63-character maximum**. An S3
  Access Point **alias** is ≤63 chars and shaped like a valid name, so it **passed config-time
  validation and reached ACTIVE**. An Access Point **ARN** (78 chars) is rejected purely on length.
- **ACTIVE at config-creation does NOT prove recording works.** IVS validates the destination when
  the configuration is created, but the actual object writes happen during a live stream (Recording
  Start/End) via the IVS service-linked role. This test did **not** run a live stream, so recording
  success is **unverified**.
- This used a **standard S3 AP**. An **FSx for ONTAP S3 AP** adds dual-layer authorization (AP policy
  **and** ONTAP file-system identity) and a different backing store; behavior there is **untested**.

### Public label decision

Config-creation acceptance is a **positive but partial** signal. Per the rule above, this stays
**Experimental** in the README until all of: (a) actual recording via a live stream is verified
end-to-end, (b) the FSx for ONTAP S3 AP case is validated, and (c) AWS documents support. **Do not
mark Supported.**

### Still to verify (requires a live stream + an FSx for ONTAP S3 AP)

- Attach the RecordingConfiguration to a channel, stream briefly, and confirm Recording Start/End and
  that `ivs/v1/...` objects are actually written **through the access point**.
- Whether the IVS service-linked role can write through an S3 AP that has **no resource policy**
  granting it, and what AP policy is required.
- The same sequence against an **FSx for ONTAP S3 AP** (AP policy + ONTAP UNIX/Windows identity).

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
