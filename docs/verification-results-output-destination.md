# Verification Results: OutputDestination=FSXN_S3AP Mode

**Date**: 2026-05-10
**Region**: ap-northeast-1
**Verified UCs**: UC11 (retail-catalog), UC14 (insurance-claims)

## Objective

Verify that the new `OutputDestination=FSXN_S3AP` CloudFormation parameter
enables AI/ML pipeline outputs to be written directly to the FSx for NetApp ONTAP
volume via S3 Access Points (the "no data movement" pattern), instead of to a
separate standard S3 bucket.

## Deployment

Both stacks were deployed with:

```
OutputDestination=FSXN_S3AP
OutputS3APPrefix=ai-outputs/uc{11,14}/
S3AccessPointAlias=eda-demo-s3ap-...-ext-s3alias
S3AccessPointName=eda-demo-s3ap  # For IAM ARN-form fallback (Phase 7 learning)
# No OutputS3APAlias/OutputS3APName → fallback to input AP
```

## Results

### ✅ UC11 retail-catalog (fsxn-retail-catalog-demo)

| Metric | Value |
|--------|-------|
| CloudFormation stack status | CREATE_COMPLETE |
| `OutputBucket` resource created? | **No** (condition `UseStandardS3` correctly evaluated to false) |
| Step Functions execution status | **SUCCEEDED** (2 executions, ~3 min each) |
| Rekognition labels | 7 images processed, up to 11 labels per image (top: `Oval` 99.93%) |
| Output S3 URI | `s3://eda-demo-s3ap-...-ext-s3alias/ai-outputs/uc11/tags/2026/05/10/*.json` |
| Output S3 URI | `s3://eda-demo-s3ap-...-ext-s3alias/ai-outputs/uc11/quality/2026/05/10/*.json` |
| Files written (SMB/NFS visible) | 14 JSONs (7 tags + 7 quality) |
| Total output size | ~8 KB |

**Sample output** (`ai-outputs/uc11/tags/2026/05/10/sample_product.json`):
```json
{
    "file_key": "products/2026/05/sample_product.jpg",
    "status": "SUCCESS",
    "labels": [
        {"name": "Oval", "confidence": 99.93},
        {"name": "Food", "confidence": 60.67},
        ...
    ]
}
```

### ✅ UC14 insurance-claims (fsxn-insurance-claims-demo)

| Metric | Value |
|--------|-------|
| CloudFormation stack status | CREATE_COMPLETE |
| `OutputBucket` resource created? | **No** |
| Step Functions execution status | **SUCCEEDED** (2 executions) |
| Rekognition damage detection | 7 images processed (MANUAL_REVIEW path for non-vehicle images) |
| Textract OCR (cross-region us-east-1) | 7 PDFs processed |
| Bedrock claims report generation | Parsing successful; model output format issue (pre-existing, unrelated) |
| Output S3 URI | `s3://.../ai-outputs/uc14/assessments/**` |
| Output S3 URI | `s3://.../ai-outputs/uc14/estimates/**` |
| Output S3 URI | `s3://.../ai-outputs/uc14/reports/**` |
| Files written | 18 files (7 assessments + 7 estimates + 2 reports JSON + 2 reports TXT) |

## Key Findings

### 1. SMB/NFS User Visibility

Outputs are visible from NFS/SMB mount of `/eda_demo` volume under `ai-outputs/`
prefix — alongside the source data. This is the core "no data movement" promise
made concrete.

### 2. No Separate S3 Bucket

With `OutputDestination=FSXN_S3AP`, the `AWS::S3::Bucket` resource is skipped
via CloudFormation `Condition: UseStandardS3`. Reduced architectural footprint:

- No S3 bucket creation / deletion overhead
- No cross-service permission chain
- No data duplication across buckets

### 3. IAM Policy Dual-Form

Phase 7 learning applied: IAM policies must include both AP alias form
(`arn:aws:s3:::<alias>/*`) and AP ARN form
(`arn:aws:s3:<region>:<account>:accesspoint/<name>/object/*`) for reliable
access. The `HasS3AccessPointName` condition conditionally adds the ARN form
when `S3AccessPointName` parameter is provided.

### 4. SSE-FSX Compliance

`OutputWriter.put_*()` does not pass `ServerSideEncryption` parameter — FSxN S3AP
requires SSE-FSX (automatic, server-side managed by FSx). The helper's unit
tests explicitly validate this compliance.

### 5. 5 GB Object Size Limit

Not reached during this verification (all test outputs were under 1 KB). For
pipelines that generate larger outputs (e.g., 4K video frames, large GeoTIFFs),
the 5 GB limit applies — use `shared.s3ap_helper.multipart_upload()` for
streaming writes of larger files.

## Pre-existing Issues (Unrelated to This Change)

- **UC14 Bedrock report**: `Malformed input request: #: required key [messages]
  not found` — Nova Lite expects Messages API format, UC14 uses the legacy
  textGenerationConfig shape. Tracked in parallel thread's work.

## Screenshots Recommended (Manual Capture)

To visualize the "no data movement" pattern:

- **S3 Console → Access Points → `eda-demo-s3ap` → Objects tab → `ai-outputs/uc11/`**:
  Shows AI output JSON files appearing alongside `products/`, `claims/`, etc.
  prefixes on the same FSx ONTAP volume.
- **S3 Console → Access Points → `eda-demo-s3ap` → Objects tab → `ai-outputs/uc14/`**:
  Shows `assessments/`, `estimates/`, `reports/` subdirectories.

File names to use (when captured):
- `uc11-s3ap-output.png` — UC11 output browsing via S3AP
- `uc14-s3ap-output.png` — UC14 output browsing via S3AP

Both should be saved under `docs/screenshots/masked/` with account ID and SVM ID
masked.

## Cost

- Deploy + verify + cleanup: ~45 minutes
- Lambda invocations: ~20 × $0.0000002 = negligible
- Rekognition: 7 images × 2 calls × $0.001 = ~$0.014
- Textract: 7 docs × ~10 pages × $0.0015 = ~$0.10
- Bedrock Nova Lite: ~14 invocations × ~500 tokens = ~$0.01
- **Total realized cost**: ~$0.13

## Next Steps

1. Screenshot the S3 Console → Access Points → Objects tab (manual)
2. Delete demo stacks (leaves FSx ONTAP intact)
3. Apply the same pattern to UC1-UC10, UC12, UC13, UC15-UC17
4. Submit FR document to AWS Support via parallel thread's contact channel
