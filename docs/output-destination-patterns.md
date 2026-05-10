# Output Destination Patterns Across UCs

This document catalogs the three distinct output-writing patterns used across
the 17 UCs in this project. Understanding which pattern each UC uses is
essential for:

- Deploying demos with the right parameters
- Predicting where AI/ML outputs appear in storage
- Reasoning about IAM permissions
- Answering the recurring "why is my output in a separate S3 bucket?" question

## Quick Reference

| Pattern | UCs | Output destination |
|---------|-----|-------------------|
| **A. Native S3AP output** (original design) | UC1, UC2, UC3, UC4, UC5, UC15, UC16, UC17 | FSxN S3 Access Point (same volume as input) |
| **B. Selectable via `OutputDestination`** | UC9, UC10, UC11, UC12, UC14 | Standard S3 (default) OR FSxN S3AP |
| **C. Standard S3 only** (partial) | UC6, UC7, UC8, UC13 | Standard S3 (Athena results require this per AWS spec) |

Pattern A and B both deliver the "no data movement" promise for the AI/ML
outputs; they differ only in whether the choice is a fixed parameter
(`S3AccessPointOutputAlias`) or a runtime switch (`OutputDestination`).

## Pattern A: Native S3AP Output (UC1-UC5, UC15-UC17)

### As of 2026-05-11: UC1-UC5 also accept Pattern B parameters

Starting 2026-05-11, UC1-UC5 templates were extended to **also** accept the
Pattern B parameter set (`OutputDestination`, `OutputS3APAlias`,
`OutputS3APPrefix`, `S3AccessPointName`, `OutputS3APName`), providing a
unified deployment API across all UCs that support FSxN S3AP output.

**Backward compatibility**:
- `S3AccessPointOutputAlias` (legacy) remains usable and takes effect when
  `OutputS3APAlias` is empty
- Default `OutputDestination=FSXN_S3AP` preserves the existing behavior for
  users who don't specify the new parameter
- No handler code changes — the `S3_ACCESS_POINT_OUTPUT` env var continues
  to be read and is now resolved via a fallback chain:
  `OutputS3APAlias` → `S3AccessPointOutputAlias` → `S3AccessPointAlias`

**Recommended deployment** (new):
```bash
aws cloudformation deploy \
  --template-file legal-compliance/template-deploy.yaml \
  --stack-name fsxn-legal-compliance-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    OutputS3APAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    OutputDestination=FSXN_S3AP \
    ... (other params)
```

**Legacy deployment** (still works):
```bash
aws cloudformation deploy \
  --template-file legal-compliance/template-deploy.yaml \
  --stack-name fsxn-legal-compliance-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (other params)
```

### Original design (Pattern A)

**CloudFormation parameter** (legacy, still supported):
```yaml
S3AccessPointOutputAlias:
  Type: String
  Description: FSx ONTAP S3 Access Point Alias (出力書き込み用、入力と同じ AP でも可)
```

**Lambda handler pattern**:
```python
from shared.s3ap_helper import S3ApHelper

s3ap_output = S3ApHelper(os.environ["S3_ACCESS_POINT_OUTPUT"])
s3ap_output.put_object(
    key="summaries/2026/05/contract_001.json",
    body=json.dumps(output),
    content_type="application/json",
)
```

**Deployment example**:
```bash
aws cloudformation deploy \
  --template-file legal-compliance/template-deploy.yaml \
  --stack-name fsxn-legal-compliance-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (other params)
```

**Characteristics**:
- No `AWS::S3::Bucket` resource in the template — zero standard S3 footprint
- Input and output can be the same S3AP (colocation) or different APs on the
  same FSx volume (e.g., different AP policies for producer vs. consumer)
- Original design pattern — simpler templates, no `Condition`-based branching
- Downside: users cannot easily switch to standard S3 for debugging or
  integration with S3-lifecycle-aware consumers

## Pattern B: Selectable via `OutputDestination` (UC9-12, UC14)

**CloudFormation parameters** (new as of 2026-05-10):
```yaml
OutputDestination:
  Type: String
  Default: "STANDARD_S3"
  AllowedValues: ["STANDARD_S3", "FSXN_S3AP"]
OutputS3APAlias:
  Type: String
  Default: ""  # falls back to S3AccessPointAlias
OutputS3APPrefix:
  Type: String
  Default: "ai-outputs/"
S3AccessPointName:
  Type: String
  Default: ""  # bare name, not alias, for IAM ARN form
OutputS3APName:
  Type: String
  Default: ""
```

**Lambda handler pattern**:
```python
from shared.output_writer import OutputWriter

output_writer = OutputWriter.from_env()
# Resolves to Standard S3 or FSxN S3AP based on OUTPUT_DESTINATION env var
output_writer.put_json(
    key="tags/2026/05/sku001.json",
    data={"status": "SUCCESS", "labels": [...]},
)
```

**Deployment examples**:
```bash
# STANDARD_S3 mode (default — keeps existing behavior)
aws cloudformation deploy \
  --parameter-overrides OutputDestination=STANDARD_S3 \
  ...

# FSXN_S3AP mode (writes AI outputs back to FSx ONTAP volume)
aws cloudformation deploy \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/uc11/ \
    S3AccessPointName=eda-demo-s3ap \
  ...
```

**Characteristics**:
- The `AWS::S3::Bucket` resource is created conditionally
  (`Condition: UseStandardS3`) — in FSXN_S3AP mode, the stack has zero
  standard S3 footprint
- IAM policies are dual-form: they grant `s3:PutObject` on either the
  standard bucket ARN OR the S3AP alias + ARN, driven by `!If` conditions
- Gracefully handles FSxN S3AP permission quirks by supporting both alias
  form (`arn:aws:s3:::<alias>/*`) and ARN form
  (`arn:aws:s3:<region>:<account>:accesspoint/<name>/object/*`) — the Phase 7
  learning is baked in
- AWS verified: UC11 + UC14 deployed 2026-05-10 in FSXN_S3AP mode, both
  SUCCEEDED. See [verification-results-output-destination.md](verification-results-output-destination.md).

## Pattern C: Standard S3 Only (UC6, UC7, UC8, UC13)

These UCs use Amazon Athena to query metadata written by the pipeline. AWS
explicitly states that Athena query results cannot be written to an FSxN
S3 Access Point:

> "Athena writes query results to an Amazon S3 bucket, not to the FSx for ONTAP volume."
>
> — [Query files with SQL using Amazon Athena (FSx ONTAP User Guide)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-query-data-with-athena.html)

Because the whole output pipeline in these UCs is structured around a
single `OutputBucket` (metadata + athena-results + reports prefixes), the
standard S3 bucket is kept as the only output destination. See
[FR-1 in fsxn-s3ap-improvements.md](aws-feature-requests/fsxn-s3ap-improvements.md#fr-1)
for the requested AWS enhancement.

**Future enhancement**: Split the outputs of Pattern C UCs into two:
- `athena-results/` → standard S3 (required)
- `metadata/` + `reports/` → FSxN S3AP (optional via `OutputDestination=FSXN_S3AP`)

This would require refactoring to use `OutputWriter` for non-Athena outputs
while keeping the Athena Workgroup's `ResultConfiguration.OutputLocation`
pointing to standard S3.

## How to Tell Which Pattern a UC Uses

1. Look for `OutputDestination` parameter → Pattern B
2. Look for `S3AccessPointOutputAlias` parameter → Pattern A
3. Look for `AthenaWorkgroup` resource AND only `OutputBucketName` →
   Pattern C

Or simply check the template's `Resources:` section: if
`OutputBucket: Type: AWS::S3::Bucket` has no `Condition:` and the template
has no `S3AccessPointOutputAlias` parameter, it's Pattern C.

## Rollout History

| Date | Milestone |
|------|-----------|
| Phase 1 | UC1-UC5 designed with Pattern A from day 1 |
| Phase 2 | UC6, UC7, UC8, UC9, UC10, UC11, UC12, UC13, UC14 designed with Pattern C |
| Phase 7 | UC15-UC17 designed with Pattern A (S3AP output) |
| 2026-05-10 morning | UC11 + UC14 refactored from Pattern C to Pattern B. AWS verified FSXN_S3AP mode end-to-end |
| 2026-05-10 afternoon | UC9 + UC10 + UC12 refactored from Pattern C to Pattern B. Unit tests pass, AWS deploy pending |
| **2026-05-11** | **UC1-UC5 extended to accept Pattern B parameters** (`OutputDestination`, `OutputS3APAlias`, `OutputS3APPrefix`, `S3AccessPointName`, `OutputS3APName`) while keeping `S3AccessPointOutputAlias` as optional legacy. Default `OutputDestination=FSXN_S3AP` preserves existing behavior. Handler code unchanged (still reads `S3_ACCESS_POINT_OUTPUT` env var, which now resolves via the new fallback chain). This unifies the CFN-level API across UC1-5 (Pattern A) and UC9/10/11/12/14 (Pattern B). |
| TBD | Handler code migration: Pattern A UC handlers could optionally migrate from `S3ApHelper(os.environ["S3_ACCESS_POINT_OUTPUT"]).put_object()` to `OutputWriter.from_env().put_json()` for full consistency with Pattern B handlers |
| TBD | Consider Pattern C → Pattern B (partial) refactor for UC6, UC7, UC8, UC13 |
| TBD | Extend Phase 7 UCs (UC15, UC16, UC17) to accept the unified API |

## Cross-Reference

- [aws-feature-requests/fsxn-s3ap-improvements.md](aws-feature-requests/fsxn-s3ap-improvements.md) — requested AWS enhancements including Athena result FSxN support
- [verification-results-output-destination.md](verification-results-output-destination.md) — AWS verification results for UC11/UC14 in FSXN_S3AP mode
- [../README.md#aws-仕様上の制約と回避策](../README.md#aws-仕様上の制約と回避策) — top-level project docs on AWS limitations
