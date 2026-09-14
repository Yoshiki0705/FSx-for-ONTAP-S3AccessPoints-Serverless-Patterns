# Beyond the four features — what each addition requires

> 🌐 **Language / 言語**: [日本語](../ja/portal-parity-next-steps.md) | English

## TL;DR

- [The same four features on three foundations](portal-parity-four-features.md) built exactly
  four: sign in, list, read, upload. This document records **what each further addition newly
  requires**, stage by stage, so a reader can go as far as their own requirements need and stop.
- There are six stages. **Stages 1 to 3 need no VPC attachment.** From stage 4 the Amazon FSx for
  NetApp ONTAP management LIF has to be reachable, and **that is where the decision to put a
  Lambda in a VPC arrives**. It is not a matter of difficulty but of which network can be reached.
- **The first thing to settle is not how many stages but the scope of writes and whether an audit
  trail is required.** Staying read-only through stage 3 and allowing writes from stage 1 differ
  enormously in what it costs to change your mind.
- Cost steps up discontinuously at stage 4, because a VPC endpoint or a NAT gateway becomes
  necessary and bills regardless of traffic. See [cost per stage](#cost-per-stage).
- At every stage, **decide early to confine writes to a prefix**. Narrowing it later means moving
  objects that have already been written.

## Scope

**Covered**: the stages beyond the four features, what each newly requires (permissions,
networking, resources, operational work), the direction cost moves, and which stages can be
skipped.

**Not covered**: implementation code for each stage (linked to the relevant pattern in this
repository instead). Performance or capacity estimates. Which foundation is better.

**Audience**: anyone with the four features working who wants to reach their own requirements, and
wants to know up front where a VPC becomes necessary and where cost jumps.

## The stages

| Stage | Addition | VPC attachment | Newly required |
|---|---|---|---|
| 1 | Paging, search, sorting | No | Nothing beyond S3's `ContinuationToken` |
| 2 | Download and shareable links | No | Presigned URLs, and a policy on their lifetime |
| 3 | Large-file upload | No | Multipart upload, or a presigned-URL path straight from the browser |
| 4 | ONTAP information (volumes, snapshots, capacity) | **Yes** | Reaching the management LIF, credential storage, an in-VPC Lambda |
| 5 | ONTAP operations (snapshot, FlexClone, locking) | **Yes** | Everything in stage 4, plus approval for irreversible operations and an audit trail |
| 6 | AI processing (classification, summarization, extraction) | Depends | Inference calls, confidence thresholds, human review, data classification labels |

Stage 4 is the boundary. **Everything up to stage 3 is satisfied by the S3 Access Point alone**;
from stage 4 the ONTAP management plane has to be reachable. What can actually reach that plane is
in [FSx for ONTAP management interfaces](fsx-ontap-management-interfaces.md).

## Stage 1. Paging, search, sorting

The four-feature listing returns objects under a prefix with a cap. Real use exceeds the cap.

**Newly required**: state to carry S3's `ListObjectsV2` `ContinuationToken` back and forth. Search
is a choice between fetching then filtering, and slicing prefixes more finely: the first costs
transfer, the second adds a dependency on a naming convention.

**Not required**: further permissions, further resources, a VPC attachment.

**Decide first**: whether sorting happens **server-side**. S3 lists keys in lexicographic order,
so sorting by size or modification time crosses page boundaries. Unless fetching everything is
acceptable, sorting has to be declared as "within this page only".

## Stage 2. Download and shareable links

Taking the object out as a file rather than rendering it in the page.

**Newly required**: presigned URL issuance. The URL is valid under the permissions of the
credentials that signed it, so **the issuer's permission becomes the URL's permission**. Decide
the lifetime (minutes or hours) and whether issuance is recorded.

**Decide first**: if it does not matter who holds the URL, this is **a path outside
authentication**. If sharing outside the organisation is allowed, settle expiry and revocation
before building it.

This repository records the signature-version and endpoint details for presigned URLs in
[S3 Access Point and ONTAP API pitfalls](../agent/pitfalls-s3ap-ontap.md).

## Stage 3. Large-file upload

The four-feature upload sends the body as JSON, which runs into the API Gateway and Lambda payload
limits.

**Newly required**: one of the following.

- **Multipart upload** managed server-side (`CreateMultipartUpload`, `UploadPart`,
  `CompleteMultipartUpload`). Per-part progress and cleanup of abandoned uploads come with it
- **A presigned URL that the browser posts to directly.** The payload never traverses the server,
  so the limit does not apply — but the prefix restriction can only be enforced at issuance

**Decide first**: where the write is validated. On a path that does not traverse the server, **the
filename and prefix checks have to happen when the URL is issued**, because there is nowhere else.

## Stage 4. ONTAP information

The character of the work changes here. Volume listings, snapshots, capacity and ARP state are not
visible through the S3 Access Point; they come from the ONTAP REST API.

**Newly required**:

| Item | Detail |
|---|---|
| Networking | The management LIF is private, so **the Lambda goes in the VPC** (or reaches it over a transit gateway peering) |
| Credentials | An ONTAP management user in AWS Secrets Manager, with a rotation cadence |
| Reachability | A VPC endpoint or NAT gateway for the in-VPC Lambda to reach other AWS services |
| Separation | An in-VPC function reaches an Internet-origin access point only through an egress path (NAT gateway or endpoint). This repository splits the work instead: an in-VPC function for ONTAP, a VPC-less one for the access point |

That last point shapes the design. The portal in this repository does the same, and `AGENTS.md`
states outright that a single Lambda never reaches both the management LIF and an Internet-origin
S3 access point. Reaching stage 4 increases **not the number of functions but the number of places
they live**.

**This is where cost steps up discontinuously** (see [cost per stage](#cost-per-stage)).

**Decide first**: whether to stop at information or go on to stage 5. Display alone is satisfied by
a read-only ONTAP user, which makes the permission design far lighter.

## Stage 5. ONTAP operations

Snapshot creation, FlexClone, volume locking — operations that change state.

**Newly required**: everything in stage 4, plus

- **Approval for irreversible operations.** Snapshot locking and SnapLock retention are one-way:
  the retention mode is fixed when the volume is created, and a locked snapshot's expiry can be
  extended but not brought forward. There has to be a path that records who requested and who
  approved, before the operation
- **An audit trail.** State-changing operations recorded in a form that cannot be altered later
- **Handling for operations that fail.** ONTAP jobs are asynchronous, and a success response does
  not always mean the work finished

**On irreversibility**: this repository has measured and recorded that, for SnapLock and
tamperproof snapshots, **an API can return success while the resource does not change**, and that
**an audit-log volume blocks deletion of its parent resources for months**
([SnapLock pitfalls](../agent/pitfalls-snaplock.md)). Worth reading at the point stage 5 is being
considered, not after.

**Decide first**: who may perform these operations. Roles and approval have to exist before the
implementation, because they cannot be added to tokens that have already been issued.

## Stage 6. AI processing

Running classification, summarization or extraction over the files.

**Newly required**:

| Item | Detail |
|---|---|
| Inference calls | Permission to call Amazon Bedrock or similar, and a region choice |
| Confidence handling | A threshold design that **does not adopt output as-is** |
| Human review | A path that routes sub-threshold output to a person |
| Data classification | Labels on the output, inheriting the sensitivity of the input |

**AI output is an assistive signal, not a final decision.** A design that feeds classification or
extraction straight into a business decision does not hold up in a regulated industry. This
repository handles confidence-based branching in `shared/human_review.py` and output labelling in
`shared/data_classification.py`.

**Decide first**: who notices when it is wrong. A threshold means nothing if sub-threshold output
reaches no one.

## Cost per stage

Prices are point-in-time and vary by region and configuration. **Check current rates before
quoting any figure.** What follows is the direction of the increment and whether it depends on
traffic.

| Stage | Nature of the increment | Traffic-dependent |
|---|---|---|
| 1-3 | More S3 requests and transfer | **Yes** (nothing accrues when unused) |
| 4 | **A VPC endpoint or NAT gateway becomes a standing charge** | **No** (it accrues from the moment it exists) |
| 5 | As stage 4, plus FlexClone and snapshot capacity | Partly |
| 6 | Per-token inference charges | **Yes** |

**Stage 4 is the step.** Stages 1 to 3 charge for what is used; from stage 4 onward something
charges for merely existing. If stage 4 was built to try something out, deciding when to remove it
is part of the work.

Rough figures for this repository's expensive resources, and the patterns for reducing them, are in
[cost awareness](../agent/cost-awareness.md).

## Which stages can be skipped

| Stage | Skippable | Condition |
|---|---|---|
| 1 (paging) | Yes | Only when the target prefix is known to hold few objects |
| 2 (download) | Yes | When in-page display suffices (text, small images) |
| 3 (large files) | Yes | When the files handled are reliably below the API payload limit |
| 4 (ONTAP information) | **No** | It is the prerequisite for stage 5; without a path to the management plane there is no state to read |
| 5 (ONTAP operations) | Yes | Unnecessary if reading and writing files is the whole requirement |
| 6 (AI) | Yes | Unnecessary if classification and summarization are not requirements |

**Stage 4 is the one that is hard to add later**, because it concerns network placement and
function separation, which means rewriting the stage 1-3 implementation. If stage 5 or later is a
possibility, **split functions into "touches the S3 access point" and "touches ONTAP" from the
start** and adding stage 4 later becomes wiring rather than restructuring.

## What each foundation is like to extend

All six stages are reachable on any of the three. What differs is the nature of the work.

| | Adding a stage |
|---|---|
| AWS Blocks | Add a block and check what it grants. **For an externally referenced resource, add the permission explicitly** ([T1](portal-parity-four-features.md#t1-the-arn-form-that-filebucketfromexisting-generates)) |
| Nx Plugin for AWS | Add a project with a generator and write the wiring in `ApplicationStack`. **Lambdas grow per procedure**, so the set needing VPC configuration grows too |
| Amplify Gen 2 | Add functions and resources to the backend definition. **An in-VPC Lambda is written through an escape hatch** |

In each case the question is not whether it can be added but where it is written. For choosing
among them, see [Choosing a
foundation](scaffolding-and-backend-toolkit-choices.md#choosing).

## Related documents

- [The same four features on three foundations](portal-parity-four-features.md) — where this
  document starts
- [Choosing a foundation for a full-stack AWS
  app](scaffolding-and-backend-toolkit-choices.md) — selecting the foundation
- [FSx for ONTAP management interfaces](fsx-ontap-management-interfaces.md) — the reachability that
  stage 4 onward depends on
- [Cost awareness](../agent/cost-awareness.md) — rough figures for expensive resources, and how to
  reduce them
