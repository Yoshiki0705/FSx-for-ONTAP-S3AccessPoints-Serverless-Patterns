# Design: OutputWriter Multipart / Streaming API for Large Objects

**Status**: Draft (B-thread proposal, 2026-05-11)
**Target Phase**: Phase 8 (B-P8-3 candidate)
**Scope**: `shared/output_writer.py` extension
**Prerequisites**:
- Phase 7 OutputDestination unification complete
- `shared/output_writer.py` with `put_bytes` / `put_text` / `put_json` / `get_*` (commit `2441db5`)
- Existing `shared.s3ap_helper.S3ApHelper.multipart_upload()` implementation (reusable)

## 1. Problem Statement

`OutputWriter.put_bytes()` and its wrappers (`put_text`, `put_json`) call
`s3.put_object` unconditionally. This works for AI artifact sizes typical
today (metadata JSONs, Bedrock reports — all well under 1 MB). But:

1. **FSxN S3AP PutObject hard limit is 5 GB**. Objects ≥ 5 GB must use
   multipart upload. This is AWS-enforced; FR-1/FR-2/FR-3 do not address it
   (accepted as fundamental per
   [`docs/aws-feature-requests/fsxn-s3ap-improvements.md`](aws-feature-requests/fsxn-s3ap-improvements.md)).
2. **Future use cases WILL generate large artifacts**. Near-term candidates:
   - UC4 media-vfx: 4K video frames / compositing outputs
   - UC7 genomics-pipeline: sharded VCF / BAM → summary tar
   - UC15 defense-satellite: COG tile assemblages (multi-band)
   - UC17 smart-city-geospatial: multi-resolution raster rebuilds
3. **Current behavior**: Silent failure with a confusing
   `EntityTooLarge` ClientError at runtime, caught by
   `S3ApHelperError` wrapping but producing a misleading error message.
4. **Workaround exists but is not ergonomic**: `shared/s3ap_helper.py`
   already has `multipart_upload(key, data_iterator, content_type, part_size)`,
   but handlers would have to:
   - Instantiate `S3ApHelper` directly (bypassing `OutputWriter`)
   - Implement data-to-iterator conversion manually
   - Branch on destination (STANDARD_S3 uses different boto3 API)
   - Re-invent prefix resolution logic already in `OutputWriter._resolve_target`

## 2. Design Goals

1. **Zero-surprise for small writes**: ≤ 5 GB (or configurable threshold)
   continues to go through `put_object` exactly like today
2. **Transparent promotion to multipart**: When size warrants, `OutputWriter`
   switches to multipart under the hood; caller API stays simple
3. **Symmetric API extension**: New `put_stream` / `put_large_*` methods
   mirror the existing `put_*` shape (destination-agnostic, prefix-resolving)
4. **Backward compatibility**: Existing `put_bytes` / `put_text` / `put_json`
   callers unchanged; no behavior change for any current UC
5. **Error symmetry**: STANDARD_S3 and FSXN_S3AP failures wrap to the same
   exception types as small writes (`S3ApHelperError` for S3AP,
   `ClientError` for standard S3)
6. **Testability**: Multipart behavior mockable without actual AWS;
   no more than ~10 new tests added to `shared/tests/test_output_writer.py`

## 3. API Design

### 3.1 New methods on `OutputWriter`

```python
class OutputWriter:
    # Existing (unchanged):
    def put_bytes(self, key: str, body: bytes, content_type: str = ...) -> dict: ...
    def put_text(self, key: str, text: str, content_type: str = ...) -> dict: ...
    def put_json(self, key: str, data: Any, ...) -> dict: ...
    def get_bytes(self, key: str) -> bytes: ...
    def get_text(self, key: str, encoding: str = "utf-8") -> str: ...
    def get_json(self, key: str) -> Any: ...
    def build_s3_uri(self, key: str) -> str: ...

    # NEW (Phase 8 B-P8-3):

    def put_stream(
        self,
        key: str,
        data_iterator: Iterator[bytes],
        content_type: str = "application/octet-stream",
        part_size: int = 100 * 1024 * 1024,   # 100 MB
        content_length_hint: int | None = None,
    ) -> dict:
        """ストリーミングアップロード（任意サイズ対応）

        小さいデータでも大きいデータでもストリーム iterator を受け付ける。
        内部で multipart アップロードのしきい値 (part_size × 2) を下回る場合は
        全データをバッファして put_bytes 経由で通常アップロードにフォールバック、
        しきい値以上の場合は multipart に自動プロモーション。

        Args:
            key: オブジェクトキー
            data_iterator: バイト列の Iterator（ファイルハンドル、ジェネレータ等）
            content_type: Content-Type
            part_size: multipart 時のパートサイズ（デフォルト 100 MB）
            content_length_hint: 総サイズが既知の場合のヒント。これが
                part_size × 2 未満なら multipart をスキップしてバッファアップロード。

        Returns:
            dict: put_bytes と同形式（destination, bucket_or_ap, key, etag, size）
        """

    def put_file(
        self,
        key: str,
        path: str | Path,
        content_type: str | None = None,
        part_size: int = 100 * 1024 * 1024,
    ) -> dict:
        """ローカルファイルパスからアップロード

        ファイルサイズを os.stat で取得し、content_length_hint 経由で
        put_stream に委譲する。ファイルサイズによって自動で通常 /
        multipart を選択する。

        Args:
            key: オブジェクトキー
            path: ローカルファイルパス
            content_type: Content-Type（None の場合は拡張子から推定）
            part_size: multipart 時のパートサイズ

        Returns:
            dict: put_bytes と同形式
        """

    def get_stream(
        self,
        key: str,
        chunk_size: int = 8 * 1024 * 1024,   # 8 MB
    ) -> Iterator[bytes]:
        """ストリーミングダウンロード（メモリ効率のために Iterator を返す）

        get_bytes は全データを一度にメモリに乗せるが、get_stream は
        chunk_size ごとに yield する。Lambda の memory ≫ 対象ファイルサイズの
        ケースでは get_bytes のままで問題ないが、対象が 数百 MB～GB 規模の
        場合に安全。

        Args:
            key: オブジェクトキー
            chunk_size: 1 回の read サイズ

        Yields:
            bytes: チャンク
        """
```

### 3.2 Behavior Matrix

| Method | Destination | Small (< 2 × part_size) | Large (≥ 2 × part_size) |
|--------|-------------|-------------------------|--------------------------|
| `put_bytes` (existing) | STANDARD_S3 | `put_object` | `put_object` (will fail at 5 GB) |
| `put_bytes` (existing) | FSXN_S3AP | `put_object` | `put_object` (will fail at 5 GB) |
| `put_stream` (new) | STANDARD_S3 | Buffered → `put_object` | `create_multipart_upload` + `upload_part` × N + `complete_multipart_upload` |
| `put_stream` (new) | FSXN_S3AP | Buffered → `put_object` | Delegates to `S3ApHelper.multipart_upload` (existing) |
| `put_file` (new) | either | size-based auto-select | size-based auto-select |
| `get_stream` (new) | either | `get_object` + iter_chunks | same (S3 boto3 natively streams) |

Key point: `put_stream` decides at runtime based on `content_length_hint`
or by buffering up to `part_size × 2` before deciding. This means small
data in an iterator form (rare, but possible) doesn't pay multipart overhead.

### 3.3 Does `put_bytes` need to auto-promote?

**Decision: No, keep `put_bytes` as a thin wrapper over `put_object`.**

Rationale:
- `put_bytes` signature takes `body: bytes` — caller already has the full
  byte sequence in memory. If it's > 5 GB, we have a bigger problem
  (Lambda memory limit is 10 GB, so this is rare but possible)
- Auto-promoting `put_bytes` would change its performance profile for
  callers not expecting multipart (different error semantics, additional
  AWS API calls billed)
- Instead, add a **friendly error hint** when `put_bytes` fails with
  `EntityTooLarge`: raise `OutputWriterError` suggesting `put_stream`
  or `put_file`

Implementation sketch:
```python
def put_bytes(self, key, body, content_type=...):
    if len(body) > 5 * 1024 * 1024 * 1024:  # 5 GB
        raise OutputWriterError(
            f"Body size {len(body)} exceeds 5 GB limit for put_object. "
            f"Use put_stream() or put_file() for large objects."
        )
    # ... existing put_object call
```

This is pre-check validation, not a behavior change.

### 3.4 Multipart delegation strategy for FSXN_S3AP

`shared/s3ap_helper.py` already implements `multipart_upload(key,
data_iterator, content_type, part_size)` correctly:

- Uses bucket_param = alias (not ARN)
- Handles `create_multipart_upload` → `upload_part` loop →
  `complete_multipart_upload`
- Aborts on failure via `abort_multipart_upload`
- Wraps all errors in `S3ApHelperError`

**Plan: `OutputWriter.put_stream` delegates to `S3ApHelper.multipart_upload`
when destination is `FSXN_S3AP`.** Benefits:

- Zero duplication of multipart logic
- Any future improvements to `S3ApHelper.multipart_upload` (e.g., retry
  strategies) automatically benefit `OutputWriter`
- The delegation boundary is clean: `OutputWriter` handles destination
  routing + prefix resolution, `S3ApHelper` handles the actual
  multipart upload mechanics

`OutputWriter.put_stream` for STANDARD_S3 uses its own multipart logic
(standard S3 doesn't need the S3ApHelper wrapper — stock boto3 works
directly). Implementation mirrors the S3ApHelper version but uses
`self._s3_client` directly.

### 3.5 Stream adapter for in-memory bytes

A common case: caller has a `bytes` object larger than `part_size × 2`
and wants multipart upload. Rather than requiring the caller to wrap it
in an iterator, `put_stream` can accept `bytes` directly:

```python
def put_stream(
    self,
    key: str,
    data: Iterator[bytes] | bytes,  # union type
    ...
):
    if isinstance(data, bytes):
        data_iterator = _chunk_bytes(data, part_size)
        content_length_hint = len(data)
    else:
        data_iterator = data
        # content_length_hint stays as passed
```

Helper `_chunk_bytes` yields slices of `part_size`. For bytes smaller
than `part_size × 2`, the buffering path in `put_stream` catches it and
uses single-part `put_object`.

## 4. Implementation Plan

### 4.1 File changes

```
shared/output_writer.py
  + _MULTIPART_THRESHOLD_MULTIPLIER = 2  # promote when size > part_size × 2
  + def put_stream(self, key, data, content_type, part_size, content_length_hint) -> dict
  + def put_file(self, key, path, content_type, part_size) -> dict
  + def get_stream(self, key, chunk_size) -> Iterator[bytes]
  + def _put_multipart_standard_s3(self, key, data_iterator, content_type, part_size) -> dict
  + def _put_multipart_fsxn_s3ap(self, key, data_iterator, content_type, part_size) -> dict
  + _chunk_bytes(data: bytes, part_size: int) -> Iterator[bytes]  (module-level)
  ± put_bytes: add pre-check for 5 GB body with hint to use put_stream
  (no changes to existing get_bytes/get_text/get_json/put_text/put_json)

shared/tests/test_output_writer.py
  + TestPutStream class (8-10 tests):
    - test_put_stream_small_bytes_uses_put_object
    - test_put_stream_large_bytes_promotes_to_multipart
    - test_put_stream_iterator_standard_s3_uses_multipart
    - test_put_stream_iterator_fsxn_s3ap_delegates_to_helper
    - test_put_stream_hint_below_threshold_skips_multipart
    - test_put_stream_aborts_multipart_on_failure_standard_s3
    - test_put_stream_wraps_fsxn_errors_as_s3ap_helper_error
    - test_put_bytes_rejects_over_5gb_with_hint
    - test_put_file_picks_multipart_based_on_file_size
    - test_get_stream_yields_chunks

shared/s3ap_helper.py
  (no changes — multipart_upload already exists and is reused)

docs/output-destination-patterns.md
  ± Add a "Large object handling" section referencing this design
```

### 4.2 Implementation sketch for `put_stream`

```python
def put_stream(self, key, data, content_type="application/octet-stream",
               part_size=100*1024*1024, content_length_hint=None):
    # Normalize data to iterator
    if isinstance(data, bytes):
        if content_length_hint is None:
            content_length_hint = len(data)
        data_iterator = _chunk_bytes(data, part_size)
    else:
        data_iterator = data

    # Decide small vs. large path
    multipart_threshold = part_size * 2
    if content_length_hint is not None and content_length_hint < multipart_threshold:
        # Fast path: buffer + put_object
        buffer = b"".join(data_iterator)
        return self.put_bytes(key, buffer, content_type=content_type)

    # Unknown size or known-large: probe-and-decide
    buffered = []
    accumulated = 0
    for chunk in data_iterator:
        buffered.append(chunk)
        accumulated += len(chunk)
        if accumulated >= multipart_threshold:
            # Large — remaining data continues via multipart
            break
    else:
        # Iterator exhausted below threshold: single PUT
        buffer = b"".join(buffered)
        return self.put_bytes(key, buffer, content_type=content_type)

    # Multipart path
    def merged_iterator():
        for chunk in buffered:
            yield chunk
        for chunk in data_iterator:
            yield chunk

    bucket_param, resolved_key = self._resolve_target(key)
    if self._destination == FSXN_S3AP:
        return self._put_multipart_fsxn_s3ap(
            resolved_key, merged_iterator(), content_type, part_size
        )
    return self._put_multipart_standard_s3(
        bucket_param, resolved_key, merged_iterator(), content_type, part_size
    )
```

### 4.3 FSXN_S3AP delegation

```python
def _put_multipart_fsxn_s3ap(self, resolved_key, data_iterator,
                              content_type, part_size):
    from shared.s3ap_helper import S3ApHelper
    helper = S3ApHelper(self._s3ap_alias, session=self._session)
    # NOTE: helper uses its own key resolution; we pre-resolved so
    # pass raw resolved_key (without adding prefix twice)
    # We need to temporarily bypass helper's internal prefix logic
    # OR: don't use _resolve_target before delegating — pass raw key
    ...
```

Complication: `_resolve_target` already prefixed `resolved_key`, but
`S3ApHelper` doesn't know about `OutputWriter`'s prefix. Resolution:

- **Option A**: `S3ApHelper.multipart_upload` doesn't apply prefix
  (it's a raw S3 API wrapper) — so passing `resolved_key` works
- **Option B**: Move prefix logic to a helper method so both
  `OutputWriter.put_stream` and the delegation call agree on the key

Verification needed during implementation: inspect
`S3ApHelper.multipart_upload` for any key-transformation logic.

Quick scan: `S3ApHelper.multipart_upload` at line 434 uses
`self.bucket_param` and passes `Key=key` verbatim. No prefix
transformation. **Option A works.**

## 5. Testing Strategy

### 5.1 Unit tests (moto / MagicMock)

- **moto**: Covers `put_object` + `create_multipart_upload` /
  `upload_part` / `complete_multipart_upload` / `abort_multipart_upload`
  for standard S3. Good enough for STANDARD_S3 multipart path
- **MagicMock**: For FSXN_S3AP delegation path, mock
  `shared.s3ap_helper.S3ApHelper.multipart_upload` and verify it was
  called with correct `(resolved_key, iterator, content_type, part_size)`
  arguments. Don't try to fully moto-simulate FSxN S3AP semantics
- **Property-based (Hypothesis)**: For `_chunk_bytes` helper, verify
  `sum(len(c) for c in _chunk_bytes(data, n)) == len(data)` for random
  byte sequences and part sizes

### 5.2 Integration tests

Skipped — follow Phase 7 pattern of unit tests + live AWS verification
at deployment time. Real multipart testing requires > 200 MB data which
is cost-prohibitive for CI.

### 5.3 Live verification (during first UC adoption)

When the first UC handler adopts `put_stream` for a real large artifact,
verify end-to-end on AWS:

1. Upload a > 200 MB file via `put_stream` in FSXN_S3AP mode
2. Confirm `aws s3api list-objects-v2` shows the object
3. `aws s3api head-object` shows correct `ETag` (multipart ETag has a
   dash: `"abc...-N"` where N is part count)
4. Download + checksum comparison to verify integrity

## 6. Non-breaking Assessment

| API | Change | Impact |
|-----|--------|--------|
| `put_bytes` | +5 GB pre-check | Only affects existing callers if they pass > 5 GB (today: none). Adds early, friendly error in place of opaque `EntityTooLarge` |
| `put_text` | none | — |
| `put_json` | none | — |
| `get_bytes` | none | — |
| `get_text` | none | — |
| `get_json` | none | — |
| `build_s3_uri` | none | — |
| OutputWriter constructor | none | — |
| `OutputWriter.from_env` | none | — |
| Existing env vars | none | — |
| Existing exceptions | none (new error reuses `OutputWriterError`) | — |

**Net: zero breaking changes for Phase 7 handlers.** Fully additive.

## 7. Use Cases That Would Adopt `put_stream`

Near-term (post-migration) candidates where `put_stream` would be
preferred over `put_bytes`:

| UC | Handler | Artifact | Current size | Future size |
|----|---------|----------|--------------|-------------|
| UC4 media-vfx | (new) final_composite | Rendered MP4 | — | 500 MB – 5 GB |
| UC7 genomics-pipeline | variant_aggregation | Aggregated VCF | ~10 MB | 2 – 20 GB |
| UC8 energy-seismic | seismic_metadata | Derived SEG-Y | ~5 MB | 5 – 50 GB |
| UC15 defense-satellite | tiling | COG assemblage | ~1 MB metadata only | Could include actual tile binaries |
| UC17 smart-city-geospatial | risk_mapping | Raster risk map | ~1 KB JSON | 100 MB – 2 GB GeoTIFF |

None of these require `put_stream` today (current implementations use
sampled / synthetic data). But Phase 8 UC4 + potential Pattern B+C
hybrid work (UC7/UC8) may adopt it.

## 8. Risks and Mitigations

### 8.1 Risk: Multipart upload state leaks (orphaned uploads)

**Mitigation**:
- Both STANDARD_S3 and FSXN_S3AP paths must `AbortMultipartUpload` on
  any exception (existing S3ApHelper already does this correctly)
- Unit test explicitly verifies abort-on-failure
- Operator remediation: `aws s3api list-multipart-uploads --bucket ...`
  + `abort-multipart-upload` can clean up any orphans. Document this
  in `docs/phase7-troubleshooting.md` when `put_stream` is first used

### 8.2 Risk: Memory blowup in probe-and-decide logic

**Mitigation**:
- `put_stream` buffers at most `part_size × 2 = 200 MB` (default) before
  deciding. Lambda memory ≥ 256 MB should accommodate this easily
- `part_size` is configurable; callers on memory-tight functions can
  reduce it
- Provide `content_length_hint` to skip probing entirely when size is
  known upfront

### 8.3 Risk: ETag format differs between single-PUT and multipart

**Mitigation**:
- Document that `dict` return value's `etag` field has format
  `"abc123"` for single-PUT and `"abc123-N"` for multipart. Downstream
  code comparing ETags across upload modes must strip the `-N` suffix
- No Phase 7 handler uses ETag for identity comparison today
  (verified via grep); low risk of regression

### 8.4 Risk: STANDARD_S3 bucket policy disallows multipart

**Mitigation**:
- Default S3 bucket policies allow multipart. Explicit DENY on
  `s3:AbortMultipartUpload` would break `put_stream`; document
  requirements in the UC deployment guide
- Phase 7 UC templates' OutputBucket doesn't restrict multipart
  (verified via template inspection)

### 8.5 Risk: FSxN S3AP part_size constraints

**Mitigation**:
- FSxN S3AP multipart follows standard S3 constraints: 5 MB minimum
  part size (except last), 5 GB maximum part size, 10,000 parts max
  per upload
- `OutputWriter` default `part_size=100 MB` is well within these
  bounds: allows 1 TB total per upload (100 MB × 10,000)
- Expose `part_size` as a parameter so callers can tune for their data
  size profile (smaller parts for more parallelism on upload, larger
  parts for fewer network round-trips)

## 9. Acceptance Criteria

1. `put_stream(bytes)` produces same ETag / size / object as
   equivalent `put_bytes(bytes)` for small data (< 200 MB)
2. `put_stream(iterator)` for > 200 MB data produces a multipart object
   (ETag format `"...-N"`)
3. `put_stream` works in both STANDARD_S3 and FSXN_S3AP modes
4. `put_file` correctly dispatches by file size
5. `get_stream` yields data that concatenates to the object's full body
6. Multipart aborts correctly on mid-upload failure (no orphan uploads)
7. `put_bytes(body)` with `len(body) > 5 GB` raises
   `OutputWriterError` with a hint to use `put_stream`
8. All existing `shared/tests/test_output_writer.py` tests continue to
   PASS (zero regression)
9. 8-10 new tests cover the new API surface
10. No changes required in any UC handler for zero-regression
    (existing `put_bytes`/`put_text`/`put_json` behavior unchanged
    within the 5 GB range)

## 10. Out of Scope

- **Parallel multipart uploads**: Could add `max_concurrency` param for
  concurrent `upload_part` calls within a single upload (speeds up
  large uploads). Defer to a follow-up design doc; requires
  threading / asyncio consideration in Lambda context
- **Resumable uploads**: If Lambda times out mid-multipart, a new
  invocation doesn't know the `upload_id`. Could persist `upload_id`
  to DynamoDB for resumability. Out of scope for first version
- **Server-side streaming from S3 → S3**: e.g., `copy_object` for
  > 5 GB transfers (`UploadPartCopy`). Useful for cross-AP scenarios
  but not needed for current UC patterns
- **Pre-signed multipart URLs**: For client-side direct upload to
  S3AP via multipart. Listed as FR-4 enhancement, separate track
- **Async / await native**: Python `asyncio` integration. boto3 is
  synchronous; async wrapper is a separate, larger change

## 11. Cross-References

- [`shared/output_writer.py`](../shared/output_writer.py) — Current implementation
- [`shared/s3ap_helper.py`](../shared/s3ap_helper.py) — Contains `multipart_upload` method to be reused (lines 434-540)
- [`shared/tests/test_output_writer.py`](../shared/tests/test_output_writer.py) — Existing 28 tests; new tests land here
- [`docs/output-destination-patterns.md`](output-destination-patterns.md) — Pattern catalog; add "Large object handling" section
- [`docs/aws-feature-requests/fsxn-s3ap-improvements.md`](aws-feature-requests/fsxn-s3ap-improvements.md) — 5 GB limit accepted as fundamental (section "Secondary / Informational Findings" #1)
- [`docs/verification-results-phase7-outputdestination.md`](verification-results-phase7-outputdestination.md) — Phase 7 Theme E verification report (same doc pattern will apply to B-P8-3 verification)
- [`docs/design-pattern-c-to-b-hybrid.md`](design-pattern-c-to-b-hybrid.md) — B-P8-2 design (potential `put_stream` adopter in UC7/UC8 AI artifacts)

## 12. Open Questions

### Q12.1 — Priority of B-P8-3 vs B-P8-2?

B-P8-2 (Pattern C hybrid) delivers customer value (FSXN_S3AP for 4
more UCs) with mechanical migration.

B-P8-3 (multipart API) is primarily infrastructure — no customer value
until a UC actually produces > 5 GB artifacts. Current test data in
Phase 7 verification is all KB-sized.

**B proposal**: **B-P8-2 first** (higher near-term value), **B-P8-3
second** (enables future UC growth without surprise failures).

However, B-P8-3 is small (~300 LOC + 10 tests) and could slot in
opportunistically before UC4 (media-vfx) migration as a prerequisite.

### Q12.2 — `put_stream` arg name bikeshedding

Candidate names considered:

- `put_stream` ✅ (chosen — clearest intent)
- `put_chunked` (implementation-leaky)
- `upload` (too broad, conflicts with AWS CLI `s3 cp` terminology)
- `put_large` (misleading — handles small iterators too)
- `put_iter` (terse but obscure)

### Q12.3 — Should we expose `content_length_hint` or always probe?

Probing (buffer until threshold then decide) is simple and works for
both known-size and unknown-size cases. But probing costs 200 MB of
Lambda memory for any call.

**Options**:
- (a) Always probe, ignore hint
- (b) Use hint when provided, probe when not (proposed)
- (c) Require hint (reject un-hinted iterators unless explicitly told to probe)

**B proposal**: **(b)** — hint is an optimization, not a requirement.

### Q12.4 — FSXN_S3AP delegation vs inline implementation

Should `OutputWriter._put_multipart_fsxn_s3ap` delegate to
`S3ApHelper.multipart_upload` (DRY) or reimplement inline (independent
evolution)?

**B proposal**: **Delegate.** DRY wins; S3ApHelper is the right place
for S3AP-specific multipart logic. `OutputWriter` stays focused on
destination routing + prefix resolution.

---

**Status: design proposal pending A-thread review and A/B priority
alignment. No implementation will proceed until Phase 8 scope is
finalized.**
