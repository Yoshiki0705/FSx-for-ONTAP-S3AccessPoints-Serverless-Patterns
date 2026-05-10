# AWS Verification Evidence

This directory contains CLI-based evidence files complementing the visual
screenshots in `docs/screenshots/masked/`. These text-based artifacts are
extracted directly from the AWS environment during verification runs and
serve as machine-readable proof that:

- FSxN S3 Access Point received AI/ML pipeline outputs correctly
- The "no data movement" pattern produces visible results on the same volume
- Output format matches what handlers are designed to write

## Files

### UC11 retail-catalog (`uc11-demo/`)

- `s3ap-output-listing.txt` — `aws s3 ls` output showing 14 JSON files
  written to `ai-outputs/uc11/{tags,quality}/2026/05/10/` via the FSxN
  S3 Access Point
- `sample-tags-output.json` — one sample Rekognition tags JSON
  demonstrating successful label detection (top label `Oval` at 99.93%
  confidence) written directly to the FSx ONTAP volume

### UC14 insurance-claims (`uc14-demo/`)

- `s3ap-output-listing.txt` — `aws s3 ls` output showing JSON files in
  `ai-outputs/uc14/{assessments,estimates,reports}/2026/05/10/`
- `sample-claims-report.json` — one sample claims report showing the
  Bedrock Nova Lite output-format pre-existing issue (unrelated to
  Pattern B work — tracked separately)

### UC15 defense-satellite (`uc15-demo/`) — Phase 7 Theme E verification

- `s3ap-output-listing.txt` — 5 output files under `ai-outputs/uc15/`
  covering tiling metadata, object-detection results, and geo-enriched
  detections from the 2026-05-11 FSXN_S3AP verification
- `sample-tiling-metadata.json` — Tiling Lambda output (image dimensions,
  tile count) written via `OutputWriter.put_json()`
- `sample-enriched-output.json` — GeoEnrichment Lambda output (sensor
  type, coordinates, enriched detections)

### UC16 government-archives (`uc16-demo/`) — Phase 7 Theme E verification

- `s3ap-output-listing.txt` — 6 output files under `ai-outputs/uc16/`
  covering OCR text/blocks, classification, PII entities, redacted text,
  and redaction metadata from the 2026-05-11 FSXN_S3AP verification
- `sample-classification.json` — Comprehend classification output
  (`clearance_level=public` via keyword fallback since sample PDF had no
  confidential markers)
- `sample-redaction-metadata.json` — Redaction sidecar JSON
  (`redaction_count=0` because minimal test PDF produced no extractable
  text via Textract; chain-level end-to-end flow is the key proof)

**Chain-read verification**: Each downstream Lambda
(Classification/EntityExtraction/Redaction) successfully read the OCR
text via `OutputWriter.get_text()` from the same FSxN S3 Access Point
the OCR Lambda wrote to, proving the symmetric read-side of the
OutputWriter works in FSXN_S3AP mode.

### UC17 smart-city-geospatial (`uc17-demo/`) — Phase 7 Theme E verification

- `s3ap-output-listing.txt` — 4 output files under `ai-outputs/uc17/`
  covering preprocessed metadata, land-use classification, risk map, and
  Bedrock-generated Markdown report from the 2026-05-11 FSXN_S3AP
  verification
- `sample-bedrock-report.md` — Bedrock Nova Lite generated Japanese city
  planning report (自治体担当者向け所見レポート) saved as Markdown to FSx
  ONTAP, directly viewable via SMB/NFS with any text editor
- `sample-risk-map.json` — RiskMapping Lambda output (flood, earthquake,
  landslide risk scores and levels)

## Why CLI Evidence?

Browser-based screenshots require console authentication and manual
capture. CLI evidence is:

- Captured automatically during deployment verification (no human step)
- Reproducible (re-run the `aws s3 ls` command any time)
- Diffable (text format, so changes are obvious in `git diff`)
- Complementary to visual screenshots (which show the S3 Console UI)

## When to Regenerate

Whenever:

- UC11, UC14, UC15, UC16, or UC17 is re-deployed in FSXN_S3AP mode
- OutputDestination pattern is rolled out to additional UCs (UC9, UC10, etc.)
- Step Functions generates a new successful execution

Command to regenerate UC11 evidence:

```bash
aws s3 ls "s3://arn:aws:s3:ap-northeast-1:<account>:accesspoint/<ap-name>/ai-outputs/uc11/" \
  --region ap-northeast-1 --recursive --human-readable \
  > docs/verification-evidence/uc11-demo/s3ap-output-listing.txt
```

## Privacy

These CLI outputs contain:

- ✅ File paths (safe to publish — they're project-level prefixes)
- ✅ File sizes and timestamps (safe to publish)
- ✅ Rekognition label names and confidence scores (safe to publish —
  derived from public sample images)
- ✅ Bedrock-generated text (safe to publish — derived from project-owned
  GIS sample data)
- ❌ NOT included: AWS account IDs, S3 AP ARNs, execution ARNs, or any PII

If any sensitive value appears in future captures, run through
`scripts/_sensitive_strings.py` substitution before committing.
