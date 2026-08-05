# Feature Requests: Lambda Self-Managed Code Storage / AWS HealthOmics with FSx for ONTAP S3 Access Points

> 🌐 Language: [日本語](./lambda-healthomics-s3ap-gaps.md) | **English**

**Submitter**: Yoshiki Fujiwara (AWS Community Builder)
**Date**: 2026-08-02
**Project**: [FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)
**Context**: Assessment of whether two July 2026 releases (Lambda self-managed code storage / AWS HealthOmics in Tokyo) can be integrated into this project's workflows
**Status**: **✅ Submitted to AWS Support on 2026-08-02** (two cases, split by service: Lambda (FR-5 + FR-7) and HealthOmics (FR-6)). Case numbers are not recorded in this repository (tracked in `.private/`).
**Related**: [FR-1 to FR-4 (previously submitted)](./fsxn-s3ap-improvements.md) / [measured object size limits](../s3ap-object-size-limits-verification.en.md) (filed as a separate case)

---

## Executive Summary

**Conclusion: neither release can currently use Amazon FSx for NetApp ONTAP S3 Access Points (FSx for ONTAP S3 AP) as a direct data source or code source.** The nature of the blocker differs between the two.

| Release | Direct FSx for ONTAP S3 AP use | Nature of blocker | Integration via standard S3 |
|---------|:---:|---|:---:|
| Lambda self-managed code storage | ❌ | **Structural** — S3 versioning is required; FSx for ONTAP S3 AP does not support Object Versioning | ✅ Possible |
| AWS HealthOmics (Tokyo) | ❌ | **By design** — inputs must be Amazon S3 URIs, and each run stages them to a scratch volume (i.e. a copy) | ✅ Possible |

Both can be integrated into this project by routing through a standard S3 bucket, but that relay step undermines the central value of the FSx for ONTAP S3 AP integration: keeping one copy of data in one place. This is the same shape of problem as our previously submitted FR-1 to FR-4, so this document organizes them as **FR-5 / FR-6 / FR-7**.

> **Note**: HealthOmics availability in Tokyo is itself a step forward for this project. Our existing UC7 (`genomics-pipeline`) README explicitly lists real variant calling pipelines (BWA/GATK and similar) as *out of scope*. With HealthOmics now available in our primary Region (ap-northeast-1), a new pattern can fill that gap.

---

## What the Releases Contain

### Release 1: AWS Lambda self-managed code storage (July 2026)

Summarized from [AWS Lambda announces self-managed code storage](https://aws.amazon.com/about-aws/whats-new/2026/07/lambda-self-managed-code-storage/) and [Self-managed S3 code storage (Lambda Developer Guide)](https://docs.aws.amazon.com/lambda/latest/dg/configuration-self-managed-storage.html):

| Item | Detail |
|------|--------|
| Capability | Setting `S3ObjectStorageMode: REFERENCE` makes Lambda read the .zip **directly from your own S3 bucket without copying it** |
| Benefit | Code does not count against the Lambda-managed storage quota; faster function activation after create/update |
| Related change | Default Lambda-managed code storage quota raised from 75 GB to **300 GB** per account per Region |
| Scope | Both **functions and layers** created from .zip archives. Container image functions are out of scope |
| Prerequisites | ① S3 **versioning must be enabled** (Lambda tracks which version of the source object to use) ② `S3ObjectVersion` must be specified ③ a bucket policy granting `lambda.amazonaws.com` the `s3:GetObject` and `s3:GetObjectVersion` actions |
| Ongoing dependency | Lambda **periodically accesses** the source object to reoptimize code. Losing access moves the function to `Inactive` |
| Unchanged | The 250 MB (unzipped) .zip deployment package limit |
| Availability | All commercial Regions |

*Content was rephrased for compliance with licensing restrictions; see the linked pages for the authoritative wording.*

### Release 2: AWS HealthOmics in Tokyo and Ohio (2026-07-20)

Summarized from [AWS HealthOmics is now available in two additional AWS Regions](https://aws.amazon.com/about-aws/whats-new/2026/07/healthomics-tokyo-ohio/):

| Item | Detail |
|------|--------|
| New Regions | **Asia Pacific (Tokyo)**, US East (Ohio) |
| Feature | Private workflows |
| Workflow languages | Nextflow / WDL / CWL |
| Built-in features | Git integration for versioned workflow development; third-party container registry support via Amazon ECR |
| Compliance | HIPAA eligible service |
| Full Region list | US East (N. Virginia, Ohio), US West (Oregon), Europe (Frankfurt, Ireland, London), Israel (Tel Aviv), Asia Pacific (Seoul, Singapore, Tokyo) |

*Content was rephrased for compliance with licensing restrictions.*

> **Region alignment note**: This project's primary deployment target is ap-northeast-1. FSx for ONTAP S3 AP is available in Tokyo ([supported Regions](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)), and HealthOmics now is too, so **the prerequisite of co-locating both services in one Region is satisfied**. The remaining barrier is the data path, not the Region.

---

## Integration Assessment

| Criterion | Lambda self-managed code storage | AWS HealthOmics |
|-----------|:---:|:---:|
| FSx for ONTAP S3 AP as a direct source | ❌ Not possible | ❌ Not possible |
| Integration via a standard S3 bucket | ✅ Possible | ✅ Possible |
| CloudFormation (`AWS::Lambda::Function`) support | ✅ `Code.S3ObjectStorageMode` exists | — |
| AWS SAM (`AWS::Serverless::Function`) support | ⚠️ **Unverified** — no such property found in the SAM resource reference | — |
| Recommended for adoption in this project | △ Conditional (pending FR-7) | ○ Viable as a new pattern |

---

## FR-5: Allow Lambda Self-Managed Code Storage to Reference FSx for ONTAP S3 Access Points

### Current State

Lambda self-managed code storage requires S3 versioning. [Self-managed S3 code storage](https://docs.aws.amazon.com/lambda/latest/dg/configuration-self-managed-storage.html) lists enabling bucket versioning as the second setup step, explaining that Lambda needs it to track which version of the source object to use. An `S3ObjectVersion` value must also be supplied.

Meanwhile, [Access point compatibility (FSx for ONTAP User Guide)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html) documents the following as unsupported:

| Element | FSx for ONTAP S3 AP status |
|---------|---------------------------|
| Object Versioning | Listed as unsupported in the Limitations section |
| `ListObjectVersions` | Not supported |
| `GetBucketPolicy` / `PutBucketPolicy` | Not supported |

*Content was rephrased for compliance with licensing restrictions.*

Consequently, **none of the three prerequisites can be met** when using an FSx for ONTAP S3 AP as a code source:

1. Versioning cannot be enabled
2. There is no `S3ObjectVersion` to retrieve
3. There is no path to apply a bucket policy granting the `lambda.amazonaws.com` service principal (an access point policy exists, but it is undefined how an AWS service principal would pass the ONTAP-side file system identity check in the two-layer authorization model)

There is also a design consideration: because Lambda periodically re-reads the source object and moves the function to `Inactive` if access is lost, a file-system-backed code source would couple file system availability (volume capacity, AD reachability, and so on) to function state.

### Impact on Our Patterns

In this repository, **37 templates** define an `AWS::Serverless::LayerVersion` ("SharedLayer") to distribute the shared Python modules under `shared/`. Most use the repository root as `ContentUri`, so every `sam deploy` publishes a new layer version, and in `COPY` mode each one consumes Lambda-managed storage quota.

| Item | Count | Impact |
|------|------:|--------|
| Templates with a SharedLayer | 37 | Layer versions accumulate, consuming quota on every deploy and redeploy |
| Lambda functions (all patterns) | 100+ | All .zip packages, so all are candidates for `REFERENCE` mode |

The default quota increase to 300 GB relieves immediate pressure, but for a Partner/SI workflow that validates all patterns across multiple Regions and accounts, quota management remains an operational item.

**Value specific to the FSx for ONTAP context**: In the EDA, gaming, and DevOps patterns this project targets (`semiconductor-eda`, `gaming-build-pipeline`, `devops-cicd`), build servers commonly write artifacts to FSx for ONTAP over NFS or SMB. If the deployment package already exists on the file system, re-uploading it to a standard S3 bucket is a redundant copy. Referencing the FSx for ONTAP S3 AP directly would let "the file system is the single source of truth for build artifacts" carry through to Lambda deployment.

### Requested Behavior

Allow the `S3Bucket` value in the `Code` property of `AWS::Lambda::Function` and in `create-function` / `update-function-code` / `publish-layer-version` to be an FSx for ONTAP S3 AP alias or ARN. We would welcome any of these approaches:

- **Option A**: Support Object Versioning on FSx for ONTAP S3 AP (for example by projecting ONTAP Snapshots as object versions) so that `S3ObjectVersion` becomes available. This is the same direction as our previously submitted FR-4.
- **Option B**: Provide an alternative change-detection mode in Lambda that uses ETag or last-modified time instead of `S3ObjectVersion`, for sources that do not support versioning.
- **Option C**: Retrieve the source object using an IAM principal equivalent to a function execution role rather than the service principal, so the existing two-layer authorization model (access point policy plus file system identity, described in [Accessing your data via Amazon S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)) can be used as-is.

Whichever approach is taken, it needs to respect that two-layer authorization model.

### Workaround in this Project

Provision a standard S3 bucket (versioning enabled) for deployment artifacts and set `S3ObjectStorageMode: REFERENCE`. Build artifacts on the file system are relayed via S3 AP `GetObject` → standard S3 `PutObject` (one additional copy step). Not currently applied to this repository's SAM-based packaging because FR-7 is unresolved.

---

## FR-6: Accept FSx for ONTAP S3 Access Points as HealthOmics Run Input and Output

### Current State

HealthOmics workflow runs assume Amazon S3 URIs for both input and output.

Per [HealthOmics run inputs](https://docs.aws.amazon.com/omics/latest/dev/workflows-run-inputs.html), when a workflow definition specifies input files, HealthOmics **stages** them to a scratch volume dedicated to the run, and those files are read-only. Input parameters are interpreted as a single object key, as a prefix when the value ends with a forward slash, or (for Nextflow) as a glob pattern.

Per [Start a run in HealthOmics](https://docs.aws.amazon.com/omics/latest/dev/starting-a-run.html), the output location is a required setting and takes an Amazon S3 location in `s3://bucket/prefix/object` form. The service role is documented as requiring permissions for Amazon S3 and KMS.

*Content was rephrased for compliance with licensing restrictions.*

In addition, [Using access points with AWS services (FSx for ONTAP User Guide)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-access-points-with-aws-services.html) lists Athena, Lambda, AWS Glue, Amazon Bedrock Knowledge Bases, Amazon EMR Serverless, CloudFront, and AWS Transfer Family as integration examples — **AWS HealthOmics is not among them**.

We therefore assess FSx for ONTAP S3 AP as unsupported for HealthOmics input and output today. Two technical considerations stand out:

1. **Staging (copying) is built into the design** — inputs are copied to a scratch volume, so even if an S3 AP URI were accepted, part of the "no data movement" value would not be realized. That said, a run-scoped temporary volume is materially different from a permanent second copy.
2. **Encryption model difference** — HealthOmics assumes Amazon S3 and KMS permissions, whereas SSE-FSX is the only server-side encryption mode on FSx for ONTAP S3 AP ([Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)). This creates a difference in service role permission design.

### AWS Support Confirmation (August 2026)

This section was originally an assessment based on public documentation. AWS Support has since answered three questions about current behaviour.

| Question | AWS Support answer |
|----------|--------------------|
| Is the restriction specific to FSx for ONTAP S3 access points? | It applies to **S3 access points in general**. `StartRun`'s `outputUri` contract requires `s3://USER-OWNED-BUCKET/` form and treats the first path segment as a bucket name. Access point ARNs and virtual-hosted-style URLs are rejected with a validation error at run submission, **identically for standard S3 access points and FSx for ONTAP ones**. There is no access-point-specific handling of any kind |
| Does SSE-FSX conflict with the service role's KMS requirements? | The requirement that the run's service role and the caller hold permissions such as `kms:GenerateDataKey` and `kms:Decrypt` is documented for SSE-KMS output buckets. However, because access points are not a supported destination, **HealthOmics has not been qualified against SSE-FSX, so whether it would present an additional obstacle is unconfirmed** |
| How are output objects near the 50 GiB limit handled? | HealthOmics writes large run outputs using **multipart upload**, so a single-`PutObject` limit is not the governing mechanism. No threshold can be stated for access point writes because that path is untested. Our copy-back step runs in our own Lambda, so the applicable limits are those of the S3 and FSx APIs it calls |

Two things follow from this.

1. The **encryption model difference noted under "Current State" is unconfirmed rather than a verified blocker**. This document does not present it as one.
2. The restriction is **not specific to FSx for ONTAP**. We state this explicitly so readers do not over-generalise the scope.

On the object size limit mentioned under "Requested Behavior": because HealthOmics uses multipart upload, that concern is on a different axis from the single-PUT limit.

AWS Support confirmed that the documentation request — noting HealthOmics support status in the FSx for ONTAP user guide — is tracked independently of whether the feature is implemented.

### Impact on Our Patterns

| Pattern | Impact |
|---------|--------|
| UC7 `genomics-pipeline` | FASTQ/BAM/VCF live on FSx for ONTAP. Quality checks and variant statistics are implemented in Lambda, but the README explicitly puts **full variant calling with BWA/GATK and similar out of scope**. HealthOmics fills that gap, but inputs must be copied to standard S3 first |
| `solutions/flexcache/life-sciences-research` | Its strength is per-researcher dataset branching via FlexClone. Feeding a cloned volume straight into HealthOmics would make "clone → analyze" a single step; today it is clone → S3 copy → analyze |
| UC5 `healthcare-dicom` | In combined imaging + genomics scenarios with HealthOmics (also HIPAA eligible), the two data paths diverge |

A single FASTQ sample can be tens of GB. The relay copy costs transfer time and temporary storage, and — the concern customers raise more often — **each additional copy of regulated data is another location to access-control, apply retention to, and audit**. In life sciences, keeping a single authoritative copy is tied directly to audit requirements, so this copy step matters beyond technical inefficiency.

> **Governance note**: This section describes storage architecture considerations. It is not a legal or compliance assessment of conformance with any specific regulation (HIPAA, GxP, or others). Interpretation of applicable requirements rests with each organization's legal and compliance functions.

### Requested Behavior

- **Input**: Accept an FSx for ONTAP S3 AP alias, ARN, or virtual-hosted-style URI in `StartRun` input parameters (including S3 URI values inside the `--parameters` JSON). Retaining the existing staging behavior — reading from the access point into the scratch volume — is fine. Both the prefix form and the sample sheet pattern should work.
- **Output**: Allow `--output-uri` to target an FSx for ONTAP S3 AP, so analysis results become directly visible to NFS and SMB users. We expect SSE-FSX to be accepted automatically as the encryption mode, and object size limits to be honored.
- **Documentation**: If implemented, please add HealthOmics to the integrated services list in [Using access points with AWS services](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-access-points-with-aws-services.html).

Output alone would deliver substantial value, so we propose prioritizing **output over input**. Because HealthOmics stages inputs read-only by design, the benefit of reading directly from the file system is comparatively smaller on the input side.

### Workaround in this Project

A Step Functions workflow (not yet implemented; backlogged as a new pattern candidate):

1. Discovery Lambda: detect FASTQ/BAM via S3 AP `ListObjectsV2`
2. Stage Lambda: S3 AP `GetObject` → standard S3 `PutObject` (multipart)
3. `omics:StartRun` → wait for completion
4. Writeback Lambda: HealthOmics output (standard S3) → S3 AP `PutObject` back to FSx for ONTAP

Steps 2 and 4 are what FR-6 would remove.

---

## FR-7: Expose `S3ObjectStorageMode` Through AWS SAM

### Current State

`S3ObjectStorageMode` is documented on the [`Code` property of `AWS::Lambda::Function`](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-lambda-function-code.html) with allowed values `COPY | REFERENCE`. By contrast, `AWS::Serverless::Function` and `AWS::Serverless::LayerVersion` expose only `CodeUri` / `ContentUri` (a local path or an S3 URI), and we could not find an equivalent property in the SAM resource reference.

> **Verification status update (August 2026)**: This item was originally an inference from public documentation alone. AWS Support has since reproduced it hands-on and confirmed that SAM discards the property without warning. See "AWS Support Confirmation" below.

### AWS Support Confirmation (August 2026)

AWS Support reproduced this in a test environment and confirmed the following. This upgrades the item from our original inference ("we could not find the property documented") to **behaviour verified hands-on**.

| Checked | Result |
|---------|--------|
| Specifying `S3ObjectStorageMode: REFERENCE` under `CodeUri` on `AWS::Serverless::Function` | `sam validate` and `sam deploy` both **succeed without error** |
| Mode of the function actually created | The property is **silently dropped** during the SAM transform; the function is created in the default `COPY` mode |
| Properties accepted by SAM's `S3Location` type | Only `Bucket` / `Key` / `Version`; anything else is discarded during transformation (not specific to `S3ObjectStorageMode`) |
| Methods listed in the Lambda Developer Guide | Console / AWS CLI / CloudFormation. **AWS SAM is not listed** |
| `update-function-code` drift | Confirmed. `S3ObjectStorageMode` must be specified on every call or it reverts to `COPY` |

> ⚠️ **What this means in practice**: A successful `sam deploy` does not mean `REFERENCE` mode was applied, so **the deployment result gives no signal that it was skipped**. Any workflow that depends on `REFERENCE` mode needs a post-deploy step that confirms the mode actually in effect.

The Inactive-state coupling was also confirmed: Lambda periodically re-reads the source object and transitions the function to Inactive if access is lost. However, AWS Support explicitly stated they **could not confirm that this is the specific reason FSx for ONTAP S3 access points are unsupported**, so this document does not present it as the cause.

On the AWS side, a feature request has been raised with the Lambda service team, a bug report with the SAM team (to add `S3ObjectStorageMode` to `AWS::Serverless::Function` and `AWS::Serverless::LayerVersion`), and feedback that SAM should raise a validation error for unrecognised properties rather than discarding them silently. However, these are **internal tickets and are not publicly accessible**. AWS Support advised that opening an issue ourselves on [aws/serverless-application-model](https://github.com/aws/serverless-application-model) is the appropriate channel for public tracking, and encouraged it on the grounds that community-filed issues with clear reproduction steps help the SAM team prioritise.

**Supported workaround (confirmed with AWS Support)**: For functions that require `REFERENCE` mode, define them as a native `AWS::Lambda::Function` with `Code.S3ObjectStorageMode: REFERENCE` rather than `AWS::Serverless::Function`, so no SAM transform is involved. Mixing `AWS::Serverless::` and native `AWS::` resources in the same SAM template was also confirmed to be **a valid and supported pattern**. This is the recommended path until SAM adds native support.

### Impact on Our Patterns

Every pattern in this repository is packaged with SAM (`AWS::Serverless::Function` plus a local `CodeUri`), with `sam build` / `sam deploy` managing artifact upload. If `S3ObjectStorageMode` cannot be set through SAM, adopting `REFERENCE` mode requires either:

- Rewriting all templates to `AWS::Lambda::Function` (losing SAM's concision and the `Policies` shorthand), or
- Running `update-function-code` after `sam deploy` (which risks drifting from CloudFormation state, since `S3ObjectStorageMode` must be specified on every call)

Both are repository-wide packaging convention changes affecting 37 templates, so we have deferred adoption pending FR-7.

### Requested Behavior

Support `S3ObjectStorageMode` (or an equivalent SAM-side property) on `AWS::Serverless::Function` and `AWS::Serverless::LayerVersion`, so `REFERENCE` mode can be selected against the artifact bucket that `sam deploy` manages. We would also like `sam deploy` to either enable versioning on its managed artifact bucket automatically, or return a clear error when `REFERENCE` mode is requested against a non-versioned bucket.

### Workaround in this Project

Remaining on `COPY` mode. No pattern here currently needs `REFERENCE` mode, so there is no reason to change the repository-wide packaging convention. If that changes, we will apply the **supported workaround** above (a native `AWS::Lambda::Function`) to the specific functions that need it, rather than rewriting every template.

---

## Secondary / Informational Findings

Items identified during this assessment that are **not** requests to AWS:

1. **The object size limit changed from 5 GB to 50 GB (now corrected)** — the current [Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html) page gives a maximum object size of **50 GB** for uploads, with larger downloads possible.

   **When it changed**: Wayback Machine snapshots show **5 GB as of 2026-03-08** and **50 GB as of 2026-06-25**. No corresponding What's New announcement was found, so it appears to have landed as a documentation-only update (the FSx for ONTAP user guide's `doc-history.html` now redirects to `what-is-fsx-ontap.html`, so there is no official change log to follow). The same revision also added the Object Annotations rows and `GetBucketCors`.

   **An important distinction**: 50 GB is the **object size ceiling**, not the single-`PutObject` limit. A single PUT is still bounded by the Amazon S3 API-wide **5 GB** limit ([Uploading objects](https://docs.aws.amazon.com/AmazonS3/latest/userguide/upload-objects.html)). Objects between 5 GB and 50 GB therefore require Multipart Upload. Statements in this repository of the form "PutObject max 5 GB" were still correct for a single PUT; what was wrong were the statements implying objects above 5 GB cannot be handled at all.

   Corrected in this session along that distinction: `AGENTS.md`, `README.md` and all 8 language variants, `docs/s3ap-compatibility-notes.{md,en.md}`, `docs/s3ap-performance-considerations.{md,en.md}`, `docs/design-considerations{,-en}.md`, `docs/{ja,en}/deployment-guide.md`, `docs/guides/s3ap-fsxn-specification.md`, `docs/cdn-comparison.*.md` (7 languages), `docs/comparison-alternatives.md`, `docs/partner-si-one-pager.{md,en.md}`, `docs/file-portal-amplify-gen2.{md,en.md}`, `docs/{ja,en}/storage-browser-demo-guide.md`, `docs/*/portal-quick-reference.md` and `portal-user-guide.md` (8 languages), `docs/nextcloud-external-storage-s3ap.{md,en.md}`, `docs/aws-feature-requests/file-portal-service-gap.{md,en.md}`, `docs/aws-feature-requests/fsxn-s3ap-improvements.md` (added as a dated correction note, since that document is a record of what was submitted), `docs/design-output-writer-multipart.md`, industry pattern READMEs and demo guides, and `drafts/blog/article-file-portal-draft.{md,en.md}`.

   > **Design impact note**: The multipart promotion threshold in `design-output-writer-multipart.md` is based on the 5 GB single-`put_object` boundary, and **that design decision needs no change**. What changed is the ceiling reachable via multipart (5 GB → 50 GB), which makes `put_stream` more useful than when it was designed.
   >
   > **Inconsistency between AWS documents**: The [AWS Transfer Family user guide](https://docs.aws.amazon.com/transfer/latest/userguide/fsx-s3-access-points.html) still states that upload file sizes are limited to 5 GB. That may be a Transfer Family-specific constraint, so we did not change Transfer-Family-scoped statements. It is worth raising as a clarification question in the AWS Support cases.
2. **The English version of `native-s3ap-notifications-evidence.md` is missing** — that file links to `native-s3ap-notifications-evidence.en.md` at the top, but the file does not exist. This is an open JA/EN parity item.
3. **HealthOmics in Tokyo fills a gap in UC7** — the "not a good fit" case that UC7's README calls out (real-time variant calling) becomes addressable with the FR-6 workaround architecture. Worth raising as a new pattern.
4. **The 300 GB Lambda-managed storage default is an effective interim mitigation** — even with 37 layer-bearing templates, quota exhaustion is much less of a concern for normal single-Region operation. `REFERENCE` mode is an optimization, not a necessity.

---

## Priority Ranking (From Customer Perspective)

| Rank | FR | Why this ordering |
|:---:|-----|-------------------|
| 1 | **FR-6 (HealthOmics output)** | In life sciences, single-copy data location ties directly to audit requirements. Output alone lets NFS/SMB users see results in place, which is high value |
| 2 | **FR-7 (SAM support)** | Comparatively small implementation cost on the AWS side, and it removes the practical barrier to adopting `REFERENCE` mode. Also a prerequisite for FR-5 |
| 3 | **FR-6 (HealthOmics input)** | Smaller direct-read benefit than output because of the staging design, but it cuts transfer time for large FASTQ files |
| 4 | **FR-5 (Lambda code source)** | Contains a structural blocker (Object Versioning) and depends on our previously submitted FR-4. The workaround is also cheaper than the others |

Merged with the previously submitted FR-1 to FR-4, our ordering is **FR-2 (event notifications) > FR-6 > FR-1 > FR-7 > FR-3 > FR-4 ≈ FR-5**. The dependency between FR-4 (versioning) and FR-5 is worth noting as additional support for FR-4's business case.

---

## Business Case Summary

- **What the Region alignment unlocks**: With FSx for ONTAP S3 AP and HealthOmics both available in ap-northeast-1, Japanese life sciences customers can for the first time keep genomics data on an in-Region file system and run analysis in-Region. For research institutions and pharmaceutical companies with strict data residency requirements, that alignment is a precondition for adoption. The fact that only the data path remains as a barrier is what makes FR-6 a high-return investment.
- **Accumulated cost of copy steps**: As noted in our earlier FRs, a PoC typically ends up needing two or three standard S3 buckets. Adding HealthOmics adds more, for input staging and output collection. The growth in bucket count shows up less as cost and more as governance load: more resources to access-control, apply retention to, and audit.
- **Scale changes the calculus for existing patterns**: 37 templates means a packaging convention change cannot be contained per pattern. If FR-7 is resolved, the change happens once; if not, the choice is binary between a repo-wide rewrite and not adopting the feature.

> **Cost note**: The figures in this section are a static count of templates in the repository (37 templates define a SharedLayer). They are not measurements from a specific customer environment or a production-scale estimate.

---

## AWS Support Submission Text

The following is intended to be pasted directly into an AWS Support case (Technical Support → the relevant service → Category: General guidance / Feature request). Cases are **split by service** (FR-5 and FR-7 under Lambda, FR-6 under HealthOmics). Each body states explicitly where a change on the FSx for ONTAP S3 AP side is needed and asks for the request to be shared with the Amazon FSx service team.

See the [Japanese version](./lambda-healthomics-s3ap-gaps.md#aws-support-提出用テキスト) for the two full case bodies (they are written in English there and are identical; they are kept in one place to avoid drift between the two language versions).

### Pre-Submission Checklist

- [ ] Open cases **split by service** (Lambda / HealthOmics)
- [ ] State the Region explicitly as ap-northeast-1
- [ ] Category: Technical Support → General guidance (feature request)
- [ ] State explicitly that this is **not** a quota increase request (Lambda case)
- [ ] Include reference documentation URLs in the body
- [ ] Ask for the request to be shared with the Amazon FSx service team
- [ ] Do not commit case numbers or support engineer names to this repository (track in `.private/`)
- [ ] After submission, update the **Status** line in this document

---

## References

All references are AWS-authored documentation or AWS-authored announcements, accessed 2026-08-02:

1. [AWS Lambda announces self-managed code storage — What's New](https://aws.amazon.com/about-aws/whats-new/2026/07/lambda-self-managed-code-storage/)
2. [Self-managed S3 code storage — AWS Lambda Developer Guide](https://docs.aws.amazon.com/lambda/latest/dg/configuration-self-managed-storage.html)
3. [AWS::Lambda::Function Code — CloudFormation Template Reference](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-lambda-function-code.html)
4. [AWS HealthOmics is now available in two additional AWS Regions — What's New](https://aws.amazon.com/about-aws/whats-new/2026/07/healthomics-tokyo-ohio/)
5. [HealthOmics run inputs — AWS HealthOmics Developer Guide](https://docs.aws.amazon.com/omics/latest/dev/workflows-run-inputs.html)
6. [Start a run in HealthOmics — AWS HealthOmics Developer Guide](https://docs.aws.amazon.com/omics/latest/dev/starting-a-run.html)
7. [Access point compatibility — FSx for ONTAP User Guide](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)
8. [Accessing your data via Amazon S3 access points — FSx for ONTAP User Guide](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
9. [Using access points with AWS services — FSx for ONTAP User Guide](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-access-points-with-aws-services.html)

---

## Appendix: Workaround Architectures

### FR-6 Workaround (HealthOmics Companion Pattern)

```
┌──────────────────────────────┐
│ FSx for ONTAP volume         │
│  FASTQ / BAM / VCF           │
│  (sequencer writes via       │
│   NFS/SMB)                   │
└──────────┬───────────────────┘
           │ S3 AP: ListObjectsV2 / GetObject  ✅ supported
           ▼
┌──────────────────────────────┐
│ Stage Lambda                 │
│  S3 AP → standard S3 copy    │  ◀── step FR-6 would remove
└──────────┬───────────────────┘
           ▼
┌──────────────────────────────┐
│ Standard S3 bucket (input)   │
└──────────┬───────────────────┘
           │ omics:StartRun --parameters
           ▼
┌──────────────────────────────┐
│ AWS HealthOmics              │
│  Nextflow / WDL / CWL        │
│  (now runnable in Tokyo)     │
└──────────┬───────────────────┘
           │ --output-uri (standard S3 required)
           ▼
┌──────────────────────────────┐
│ Standard S3 bucket (output)  │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│ Writeback Lambda             │
│  standard S3 → S3 AP         │  ◀── step FR-6 would remove
└──────────┬───────────────────┘
           ▼
    NFS/SMB users see results
    next to the source data
```

If only the output side of FR-6 is delivered, the Writeback Lambda (the lower copy) becomes unnecessary. If the input side is delivered as well, the Stage Lambda goes away too, leaving a workflow that simply calls `StartRun`.

### FR-5 Workaround (Lambda Code Storage)

```
┌──────────────────────────────┐
│ FSx for ONTAP volume         │
│  build artifact .zip         │
│  (build server writes via    │
│   NFS/SMB)                   │
└──────────┬───────────────────┘
           │ S3 AP: GetObject  ✅ supported
           ▼
┌──────────────────────────────┐
│ Standard S3 bucket           │
│  versioning enabled          │  ◀── relay FR-5 would remove
│  (required)                  │
└──────────┬───────────────────┘
           │ S3ObjectStorageMode: REFERENCE
           │ + S3ObjectVersion
           ▼
┌──────────────────────────────┐
│ Lambda function / layer      │
└──────────────────────────────┘
```
