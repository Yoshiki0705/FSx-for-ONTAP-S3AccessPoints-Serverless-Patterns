# Design: Pattern C → Pattern B Hybrid for UC6/7/8/13

**Status**: Draft (B-thread proposal, 2026-05-11)
**Target Phase**: Phase 8 (B-P8-2 candidate)
**Scope**: UC6 semiconductor-eda, UC7 genomics-pipeline, UC8 energy-seismic, UC13 education-research
**Prerequisites**:
- Phase 7 OutputDestination unification complete (13/17 UCs on Pattern B)
- `shared/output_writer.py` with symmetric `put_*` / `get_*` helpers (commit `2441db5`)

## 1. Context

### 1.1 Current State: Pattern C (Standard S3 Only)

Four UCs are currently classified as Pattern C in
[`docs/output-destination-patterns.md`](output-destination-patterns.md):

| UC | Directory | Why Pattern C |
|----|-----------|---------------|
| UC6 | `semiconductor-eda/` | Uses Athena for DRC aggregation; Athena results must go to standard S3 |
| UC7 | `genomics-pipeline/` | Uses Athena for variant QC summary; same constraint |
| UC8 | `energy-seismic/` | Uses Athena for well-cross-time anomaly correlation; same constraint |
| UC13 | `education-research/` | **No Athena.** Currently Pattern C due to original spec assumption, but actually migratable to full Pattern B |

The Pattern C classification was pragmatic: Athena's
`StartQueryExecution.ResultConfiguration.OutputLocation` requires a
standard S3 bucket — FSxN S3 Access Points are not supported as query
result destinations per AWS spec
([FR-2](aws-feature-requests/fsxn-s3ap-improvements.md) requests this).

However, the AI/ML artifacts each UC produces (Bedrock-generated
reports, metadata JSONs, Rekognition outputs) are **not constrained by
Athena's limitations**. These artifacts can go to FSxN S3AP just like
UC1-5 / UC9-12 / UC14-17.

### 1.2 Why Now?

Phase 7 verified the production viability of `OutputDestination=FSXN_S3AP`
for 5 UCs (UC11/14/15/16/17). The migration pattern is mature:

1. Handler migration: `s3_client.put_object(Bucket=OUTPUT_BUCKET, ...)`
   → `OutputWriter.from_env().put_json()` (or `put_text`)
2. Template migration: add `OutputDestination` / `OutputS3APAlias` /
   `OutputS3APPrefix` / `OutputS3APName` params, `UseStandardS3` /
   `UseFsxnS3AP` conditions, conditional IAM policies, conditional
   Lambda env vars
3. Test migration: mock `OutputWriter` alongside boto3 in tests

The incremental cost of extending this to UC6/7/8/13 is small, and
the business value ("no data movement" for AI artifacts) is real for
these industries (EDA, genomics, energy, academia) where source data
retention policies are tightly regulated.

## 2. Problem Statement

How to support `OutputDestination=FSXN_S3AP` in UC6/7/8/13 while keeping
Athena query execution fully functional, given that Athena cannot write
to FSxN S3AP?

### 2.1 Constraints

- **C-1 Athena OutputLocation**: Must be a standard S3 bucket, always.
  Cannot be S3AP (enforced by AWS). Not a CloudFormation workaround.
- **C-2 Athena ResultBucket lifetime**: Queries produce `.csv` + `.metadata`
  artifacts; these are consumed by downstream Lambdas via
  `athena:GetQueryResults` (not S3 read), so the physical S3 location is
  transparent to the workflow. The bucket *must exist* but its contents
  have a short lifecycle.
- **C-3 Glue Data Catalog**: Tables point at `s3://<bucket>/metadata/`
  Parquet/JSON files that downstream Athena queries SELECT from.
  This is the "source of truth" for Athena and cannot be S3AP.
- **C-4 Downstream artifact destination**: Things like Bedrock-generated
  Markdown reports (UC6/UC7/UC8), compliance JSONs (UC8), classification
  outputs (UC13) can go wherever the operator chooses.
- **C-5 UC13 is special**: Despite being Pattern C in the catalog, UC13
  doesn't use Athena at all. It's purely
  `Discovery → OCR → Classification → Metadata → CitationAnalysis`.
  Pattern B migration has no Athena-specific blockers.

### 2.2 Non-goals

- Extending FSxN S3AP to support Athena query results (this is FR-2,
  an AWS-side feature request; out of scope for us)
- Eliminating the standard S3 bucket entirely for UC6/7/8 (we keep a
  minimal bucket for Athena/Glue; only AI artifacts move)
- Refactoring Athena query logic itself

## 3. Design

### 3.1 Hybrid Destination Model

Introduce a third classification beyond pure Pattern A / B / C:

> **Pattern B+C hybrid**: Athena query results and Glue-managed data
> remain on a **standard S3 metadata bucket** (always created). AI/ML
> artifacts (Bedrock reports, processing JSONs, classification outputs)
> go to a **configurable destination** — standard S3 (default) or
> FSxN S3AP (opt-in via `OutputDestination=FSXN_S3AP`).

Two physical buckets / destinations per UC:

| Path | Destination | Purpose | Controlled by |
|------|-------------|---------|---------------|
| `s3://<metadata-bucket>/metadata/` | Always standard S3 | Glue tables, Parquet inputs | Existing (unchanged) |
| `s3://<metadata-bucket>/athena-results/` | Always standard S3 | Athena query results | Existing (unchanged) |
| `s3://<ai-destination>/ai-outputs/ucN/` | STANDARD_S3 or FSXN_S3AP | Bedrock reports, processed JSONs | New `OutputDestination` |

When `OutputDestination=STANDARD_S3` (default, backward-compatible):
`<ai-destination>` resolves to the same standard S3 bucket used for
metadata/athena-results. The net layout is identical to today.

When `OutputDestination=FSXN_S3AP`: `<ai-destination>` resolves to the
FSxN S3 Access Point; the metadata bucket still exists for Athena but
carries only Glue tables and Athena temp results.

### 3.2 Two-Bucket Template Structure

Template changes per UC (UC6/7/8 only; UC13 simpler, see §3.5):

```yaml
Parameters:
  # Existing (unchanged semantics)
  OutputBucketName:
    Type: String
    Default: ""
    Description: |
      Name for the metadata/Athena bucket (always created).
      This bucket holds Glue table data and Athena query results —
      both must be standard S3 per AWS spec. AI artifacts go to
      OutputDestination (separate parameter).

  # NEW (Phase 8)
  OutputDestination:
    Type: String
    Default: "STANDARD_S3"
    AllowedValues: ["STANDARD_S3", "FSXN_S3AP"]
    Description: |
      AI/ML artifacts destination. STANDARD_S3 (default) reuses the
      metadata bucket; FSXN_S3AP writes to the FSx ONTAP volume via
      S3 Access Point. Athena results are NOT affected by this
      parameter — they always go to the standard S3 metadata bucket.
  OutputS3APAlias:
    Type: String
    Default: ""
  OutputS3APPrefix:
    Type: String
    Default: "ai-outputs/"
  OutputS3APName:
    Type: String
    Default: ""

Conditions:
  UseStandardS3: !Equals [!Ref OutputDestination, "STANDARD_S3"]
  UseFsxnS3AP:   !Equals [!Ref OutputDestination, "FSXN_S3AP"]
  UseInputApAsOutputAp:
    !Equals [!Ref OutputS3APAlias, ""]
  UseInputApNameAsOutputApName:
    !Equals [!Ref OutputS3APName, ""]

Resources:
  # Always created (renamed for clarity)
  MetadataBucket:
    Type: AWS::S3::Bucket
    # ... (same as today's OutputBucket)

  # AthenaWorkgroup, GlueDatabase, GlueTable resources
  # → all reference MetadataBucket (unchanged)
```

Key point: `MetadataBucket` is created unconditionally. There is no
`Condition: UseStandardS3` gate like UC15-17 have, because Athena needs
it either way.

### 3.3 Handler Migration Matrix

Per UC, classify each Lambda into one of three categories:

**Category A — AI artifact writer (migrate to OutputWriter)**:
These produce JSONs / Markdown / text outputs that conceptually belong
next to the source data. Migrate to `OutputWriter.from_env()`.

**Category B — Athena-bound writer (keep OUTPUT_BUCKET direct S3)**:
These invoke Athena queries and consume `GetQueryResults`. Their output
IS an Athena result which must stay on standard S3. No migration.

**Category C — Downstream aggregator (depends)**:
Read Category B results + produce final reports. The reports are
Category A candidates. Split read-path from write-path.

#### UC6 semiconductor-eda (4 Lambdas)

| Lambda | Today | Category | Plan |
|--------|-------|----------|------|
| discovery | S3AP manifest via `s3ap_output.put_object` | (existing special) | Keep as-is |
| metadata_extraction | `OUTPUT_BUCKET/metadata/*.json` | Category B | **Keep** — this feeds Glue table |
| drc_aggregation | Athena queries, results to `OUTPUT_BUCKET/athena-results/` | Category B | Keep |
| report_generation | `OUTPUT_BUCKET/reports/*.md` (Bedrock Markdown) | **Category A** | **Migrate to OutputWriter** |

Net result: Operators choose where the Bedrock report lands. Glue table
continues to work because `metadata_extraction` still writes to
`MetadataBucket/metadata/`. DRC query results still land at
`MetadataBucket/athena-results/` (Athena OutputLocation unchanged).

#### UC7 genomics-pipeline (5 Lambdas)

| Lambda | Today | Category | Plan |
|--------|-------|----------|------|
| discovery | S3AP manifest | (existing) | Keep |
| qc | `OUTPUT_BUCKET/qc/*.json` | Category B (Glue-fed) | Keep |
| variant_aggregation | `OUTPUT_BUCKET/variants/*.json` | Category B (Glue-fed) | Keep |
| athena_analysis | Athena queries | Category B | Keep |
| summary | `OUTPUT_BUCKET/summary/*.md` (Bedrock report) | **Category A** | **Migrate** |

Similar shape to UC6. Summary report is the only migratable artifact.

#### UC8 energy-seismic (5 Lambdas)

| Lambda | Today | Category | Plan |
|--------|-------|----------|------|
| discovery | S3AP manifest | (existing) | Keep |
| seismic_metadata | `OUTPUT_BUCKET/metadata/*.json` | Category B | Keep |
| anomaly_detection | `OUTPUT_BUCKET/anomalies/*.json` | Category B | Keep |
| athena_analysis | Athena queries | Category B | Keep |
| compliance_report | `OUTPUT_BUCKET/reports/*.md` + compliance JSON | **Category A** | **Migrate** |

Similar shape. Compliance report + summary JSON move.

#### UC13 education-research (5 Lambdas) — SPECIAL CASE

| Lambda | Today | Category | Plan |
|--------|-------|----------|------|
| discovery | S3AP manifest | (existing) | Keep |
| ocr | `OUTPUT_BUCKET/ocr-results/*.txt` | **Category A** | **Migrate** |
| classification | `OUTPUT_BUCKET/classifications/*.json` | **Category A** | **Migrate** (reads ocr via get_text) |
| metadata | `OUTPUT_BUCKET/metadata/*.json` | **Category A** | **Migrate** |
| citation_analysis | `OUTPUT_BUCKET/citations/*.json` | **Category A** | **Migrate** (reads ocr via get_text) |

**UC13 is full Pattern B**, not hybrid. No Athena, no Glue. Can collapse
to the same pattern as UC16 (chain structure with `get_text`).

### 3.4 Migration Effort Estimate

Per UC, using UC15-17 Phase 7 migration as the baseline:

| Step | UC6 | UC7 | UC8 | UC13 | Total |
|------|-----|-----|-----|------|-------|
| Handler migration (Category A only) | 1 Lambda | 1 | 1 | 4 | **7 Lambdas** |
| Template changes (Params + Conditions + env vars) | ~50 LOC | ~50 | ~50 | ~100 | ~250 LOC |
| Test updates (mock OutputWriter) | 1 test file | 1 | 1 | 4 | 7 test files |
| cfn-lint | 0 errors expected | 0 | 0 | 0 | — |
| AWS deploy + Step Functions exec | verify | verify | verify | verify | 4 deployments |
| CLI evidence capture | 1 UC | 1 | 1 | 1 | 4 UCs |
| Docs (pattern catalog, per-UC demo-guide) | per UC | per UC | per UC | per UC | — |

Estimated total effort: ~2-3 days wall clock for B-thread, assuming
Phase 7 migration patterns are reused mechanically.

### 3.5 UC13 Full Pattern B Migration

Since UC13 has no Athena, it's actually closer to UC16's migration than
to UC6/7/8. Specifically:

- Rename `OutputBucket` to conditional (gate with `UseStandardS3`), same
  as UC16
- Add all 4 Pattern B params + 4 conditions
- Migrate all 4 handlers (ocr, classification, metadata,
  citation_analysis) to `OutputWriter`
- The chain structure (classification reads ocr-results via `get_text`,
  citation_analysis reads ocr-results via `get_text`) matches UC16
  exactly

UC13 graduates from "Pattern C" to pure "Pattern B" after migration,
not to the hybrid category.

### 3.6 Output Destination Patterns Doc Update

After migration:

```markdown
| Pattern | UCs | Output destination |
|---------|-----|-------------------|
| A. Native S3AP (legacy params) | UC1, UC2, UC3, UC4, UC5 | FSxN S3 AP |
| B. Selectable via OutputDestination | UC9, UC10, UC11, UC12, UC13 ✨, UC14, UC15, UC16, UC17 | STANDARD_S3 (default) or FSXN_S3AP |
| B+C hybrid (AI artifacts movable, Athena fixed) | UC6 ✨, UC7 ✨, UC8 ✨ | AI artifacts: STANDARD_S3 or FSXN_S3AP; Athena: STANDARD_S3 only |
```

After Phase 8: **16 of 17 UCs** support `OutputDestination=FSXN_S3AP`
opt-in (all except UC6 metadata/athena, UC7 qc/variant/athena,
UC8 seismic/anomaly/athena — which are tied to Athena/Glue by design).

## 4. Risks and Mitigations

### 4.1 Risk: Operator confusion on "why is some data in S3AP and some in standard S3?"

**Mitigation**:
- Clear demo-guide section per UC: "出力先について: OutputDestination で切替可能 (Pattern B+C hybrid)"
- Table in each UC doc showing which Lambda writes where:
  - `metadata_extraction` → `s3://MetadataBucket/metadata/` (Glue)
  - `drc_aggregation` → `s3://MetadataBucket/athena-results/` (Athena)
  - `report_generation` → `s3://OutputDestination/ai-outputs/uc6/reports/*.md`

### 4.2 Risk: UC6/7/8 Bedrock reports lose linkage to the Athena query that produced them

**Mitigation**:
- Report Lambda's input already includes `athena_results: dict`
  (passed via Step Functions state). No change needed — the Bedrock
  prompt continues to reference Athena results by value, not by
  location
- Report output includes `"athena_query_id": "..."` metadata for
  traceability back to the query execution

### 4.3 Risk: Handler refactoring introduces bugs in long-verified UC6/7/8 code

**Mitigation**:
- Migration is mechanical (`s3_client.put_object(Bucket=output_bucket, ...)` →
  `OutputWriter.from_env().put_json(...)`)
- Phase 7 migration (UC15/16/17) had 0 behavior-changing bugs — the
  pattern is well-understood
- Each UC gets unit tests updated + Step Functions SUCCEEDED end-to-end
  verification before commit

### 4.4 Risk: Cost regression if users don't understand the hybrid

**Mitigation**:
- Default remains `OutputDestination=STANDARD_S3`, which is identical
  to today's behavior (reuses metadata bucket for AI artifacts). No
  migration required for existing deployments
- FSXN_S3AP mode reduces AI artifact storage to $0 (on FSx ONTAP
  volume) but keeps metadata bucket cost constant (Glue/Athena
  requirements). Net effect: strictly ≤ current cost

### 4.5 Risk: UC13 chain structure bugs (OCR output read by classification + citation_analysis)

**Mitigation**:
- UC16 already verified this pattern in production (Phase 7 Theme E)
- UC13's chain is simpler than UC16 (no PII/Textract complexity)
- Reuse UC16 test patterns for mocking `OutputWriter` across chain stages

## 5. Implementation Phases

Proposed sub-phasing within Phase 8 B-P8-2:

### Phase 8.2a — UC13 full Pattern B migration (lowest risk)

Since UC13 has no Athena, it's a clean Pattern B migration identical
to UC16. Gate commits:

1. Migrate OCR / Classification / Metadata / CitationAnalysis handlers
   to `OutputWriter` (1 commit per Lambda, 4 commits total)
2. Update template-deploy.yaml (Pattern B params + conditions + env vars)
3. Update tests (mock OutputWriter, chain reads via get_text)
4. cfn-lint + unit tests PASS → AWS deploy + verify → CLI evidence
5. Update pattern catalog classification: UC13 moves to Pattern B column

### Phase 8.2b — UC6 hybrid migration (lowest Athena complexity)

UC6 has 1 migratable Lambda (report_generation). Validate the hybrid
pattern end-to-end on this UC first before applying to UC7/UC8.

1. Migrate `report_generation` handler to OutputWriter
2. Update template (hybrid params + conditions, keep MetadataBucket
   unconditional, gate only AI artifact IAM policies)
3. Test updates
4. Deploy in STANDARD_S3 mode → verify behavior unchanged
5. Deploy in FSXN_S3AP mode → verify Bedrock report lands on S3AP,
   Athena continues to write to MetadataBucket
6. CLI evidence

### Phase 8.2c — UC7 + UC8 parallel migration

Same shape as UC6. Can be done in parallel since templates and handlers
are UC-isolated.

### Phase 8.2d — Documentation + article

- Update `docs/output-destination-patterns.md` with new classifications
- Update `README.md` per-UC output table
- Phase 8 article section: "Pattern B+C hybrid: When Athena says no,
  we say 'some data can still move'"
- Update coordination docs if the hybrid pattern introduces new
  cross-thread considerations

## 6. Acceptance Criteria

### Per-UC

1. Unit tests: existing tests PASS after handler migration; new tests
   mock `OutputWriter.from_env()` correctly
2. cfn-lint: 0 real errors on updated template
3. AWS deploy: CloudFormation deploys cleanly in both STANDARD_S3
   (backward compat) and FSXN_S3AP modes
4. Step Functions: SUCCEEDED execution in both modes
5. Outputs visible:
   - STANDARD_S3 mode: all artifacts under `s3://MetadataBucket/`
     (unchanged from today)
   - FSXN_S3AP mode: AI artifacts under `s3://<s3ap>/ai-outputs/ucN/`;
     Athena artifacts under `s3://MetadataBucket/athena-results/`
6. CLI evidence captured in `docs/verification-evidence/ucN-demo/`

### Project-wide

7. `docs/output-destination-patterns.md` updated with hybrid pattern
8. Pattern B UC count: 9 → **13** (UC9-17 + UC13) after phase 8.2a
9. Hybrid UC count: 0 → **3** (UC6/UC7/UC8) after phase 8.2b/c
10. Pure Pattern C UC count: 4 → **0** after all sub-phases complete
11. Phase 8 article section documents the hybrid design + trade-offs

## 7. Open Questions (A/B thread coordination)

### Q7.1 — Ownership

Is B-thread the natural owner for B-P8-2, given the Phase 7
OutputDestination unification was B-led? Or should this be split?

B proposal: **B-thread drives UC6/7/8/13 migration** (pattern reuse,
`OutputWriter` expertise). A-thread owns parallel Phase 8 themes
(A/B/C/D/E/F/G per A's Phase 8 spec draft).

### Q7.2 — Timing

Should B-P8-2 be sequenced after Theme Q (UC4/UC9) is complete, or can
it proceed in parallel?

B proposal: **Parallel is fine.** UC6/7/8/13 are B-exclusive file
scopes (no overlap with A's Theme Q UC4/UC9 or Theme A-G scope). No
coordination friction expected.

### Q7.3 — AWS cost budget for verification

UC6/7/8 verification involves Athena queries (each ~$0.005 per scan)
and Glue table updates. Estimated verification cost: ~$0.50-$1.00 per
UC for deploy + execute + cleanup.

B proposal: **Acceptable.** Phase 7 Theme E came in at ~$0.05 total;
even a 10-20x Athena overhead keeps Phase 8 B-P8-2 under $5.

### Q7.4 — FR-2 dependency

Pattern C → Pattern B hybrid is a workaround; the proper fix is AWS
supporting S3AP as Athena OutputLocation (FR-2). Should we:

- (a) Implement the hybrid and keep FR-2 as "nice to have"
- (b) Hold off on hybrid pending FR-2 delivery
- (c) Implement hybrid AND keep pushing FR-2 (belt + suspenders)

B proposal: **(c).** FR-2 timeline is AWS-controlled (could be months
or years); delivering hybrid now unblocks customers. When FR-2 lands,
we can further simplify UC6/7/8 to pure Pattern B. The hybrid is a
transitional state, not a permanent one.

## 8. Cross-References

- [`docs/output-destination-patterns.md`](output-destination-patterns.md) — Current Pattern A/B/C catalog
- [`docs/verification-results-phase7-outputdestination.md`](verification-results-phase7-outputdestination.md) — Phase 7 Theme E verification (blueprint for this design)
- [`docs/aws-feature-requests/fsxn-s3ap-improvements.md`](aws-feature-requests/fsxn-s3ap-improvements.md) — FR-2 (Athena OutputLocation support on S3AP)
- [`docs/phase7-summary.md`](phase7-summary.md) — Phase 7 completion summary, lists B-P8-2 as a candidate
- [`shared/output_writer.py`](../shared/output_writer.py) — OutputWriter implementation
- [`retail-catalog/template-deploy.yaml`](../retail-catalog/template-deploy.yaml) — UC11 reference template (Pattern B full migration, non-hybrid)
- [`semiconductor-eda/template-deploy.yaml`](../semiconductor-eda/template-deploy.yaml) — UC6 current template (Pattern C, starting point for hybrid)

## 9. Next Actions (if B-P8-2 is approved)

1. A-thread reviews this design doc → approve / request changes / defer
2. B-thread drafts `.kiro/specs/fsxn-s3ap-serverless-patterns-phase8/`
   B-P8-2 task breakdown (if absent from A's current draft)
3. B-thread starts Phase 8.2a (UC13 migration) when Phase 7 Theme Q + R
   are complete (or in parallel if no conflicts)
4. A-thread publishes Phase 8 article section after all 4 UCs are
   migrated + verified

---

**This is a design proposal, not an implementation commitment. Phase 8
scope will be finalized in the Phase 8 spec after A-thread and B-thread
agree on priorities.**
