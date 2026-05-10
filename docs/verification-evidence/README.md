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

## Why CLI Evidence?

Browser-based screenshots require console authentication and manual
capture. CLI evidence is:

- Captured automatically during deployment verification (no human step)
- Reproducible (re-run the `aws s3 ls` command any time)
- Diffable (text format, so changes are obvious in `git diff`)
- Complementary to visual screenshots (which show the S3 Console UI)

## When to Regenerate

Whenever:

- UC11 or UC14 is re-deployed in FSXN_S3AP mode
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
- ❌ NOT included: AWS account IDs, S3 AP ARNs, execution ARNs, or any PII

If any sensitive value appears in future captures, run through
`scripts/_sensitive_strings.py` substitution before committing.
