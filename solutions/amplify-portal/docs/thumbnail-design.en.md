# Thumbnails in the file list — design and limits

🌐 **Language / 言語**: [日本語](thumbnail-design.md) | English

The design behind showing an image thumbnail in a list row: why the obvious
implementation is expensive, and what was built instead.

## Requirements

- A row shows what the picture is
- No extra Lambda invocation per file
- No extra transfer on a phone over cellular
- One awkward file does not break the page
- It runs inside the same authorization boundary as the listing

## Why the obvious implementation was not used

Putting a presigned URL in an `<img>` is the shortest path, and it costs twice.

| The obvious way | What it costs |
|---|---|
| A presigned URL per file | **100 extra Lambda invocations** on a hundred-file page |
| The original straight into `<img>` | the **whole original downloaded** to draw 48 pixels. A 20 MB photo is 20 MB |

The second matters most on a phone. If a thumbnail means fetching the original, the
thumbnail is slower than no thumbnail.

## What was built

Generation moves to the backend, and one call serves a page.

```
FileExplorer (collects the page's keys)
  └─ thumbnailQuery / getThumbnails (one call)
       └─ ThumbnailsFunction (Pillow)
            ├─ HeadObject for the ETag and size (through the S3 AP)
            ├─ cached: presign and return
            └─ missing: GetObject -> resize -> JPEG -> PUT to the cache -> presign
```

| Piece | Where |
|---|---|
| Endpoint | `thumbnailQuery` (one action, `getThumbnails`) |
| Lambda | `functions/thumbnails/handler.py`, 1024 MB / 60 s, ARM64 |
| Layers | `PillowLayer` and `SharedPythonLayer` (the authorization boundary) |
| Cache | `ThumbnailCacheBucket`, expiring after 30 days |
| Frontend | `src/hooks/useThumbnails.ts` into `FilePreview`'s `thumbnailUrl` |

### Why not an action on the listing Lambda

`fileQuery` and `fileMutation` both bind to the listing Lambda
(`ListFilesLambdaDataSource`), so an action added there would **run generation inside
it** — putting a 6 MB layer and the extra memory on the cold start of every listing,
thumbnails or not. The ZIP function is separate for the same reason.

### Why the ETag is in the cache key

Keyed on the path alone, a replaced file would **keep serving the old picture**. The
cache key is `sha256(AP alias + key + ETag + edge pixels)`, so different content is a
different entry. The alias is included because the same key under two access points is
two different objects.

### Authorization

This endpoint **takes object keys from the client**, so it has to sit behind the same
boundary the listing uses. It shares `shared.portal_path_scope` (`reject_key`,
`allowed_prefixes`) with the listing and the agent, and a key outside the caller's
prefixes is refused **before HeadObject** — refusing after the read would leak whether
the object exists.

`groups` is injected by the resolver from the verified token, never read from the
request body.

### What is not generated, and how that looks

So that one file cannot break a page, anything ineligible comes back under `skipped`
with a reason and the row keeps its existing icon.

| Condition | Behaviour |
|---|---|
| Unsupported extension | skipped without a download |
| Over 25 MB (default) | skipped without a download |
| Image extension, other content | skipped (`not a readable image`) |
| Over 40 megapixels | Pillow refuses — the guard against a small file claiming enormous dimensions |
| Past the per-call generation cap (12) | returned as `pending`; the frontend asks again a few seconds later |

`pending` exists to avoid a timeout. Trying to render a hundred cache misses in one
invocation does not fit in 60 s, and **the work already done would be lost with it**.

### EXIF is not carried into the thumbnail

The resized image is saved as a new JPEG, so no metadata comes with it: the location a
phone recorded is not republished in a picture shown to everyone who can see the row.
Rotation is the exception — it is **applied to the pixels before the metadata is
dropped**, or a portrait photo appears on its side.

## The decision to add Pillow

The repository's first third-party Python dependency.

- **No Docker.** `pip install --target --platform manylinux2014_aarch64
  --python-version 3.13` extracts the ARM64 wheel, so the layer build still works on a
  laptop.
- **One place for the version.** `functions/thumbnails/requirements.txt` is the source
  and the CDK reads it. `requirements-dev.txt` pins the same one and
  `scripts/tests/test_thumbnail_pins_agree.py` asserts they agree — a test decoding
  images with a different Pillow than production runs is a test of something else.
- **12.2.0**, the newest release with a cp313 manylinux2014_aarch64 wheel. A version
  without one cannot be staged without Docker.

The alternative considered was extracting only the EXIF thumbnail embedded in JPEGs,
which needs nothing but the standard library. It covers most phone and camera photos
but not PNGs or screenshots, leaving "some images have pictures" — so it was not taken.
Hand-writing an image decoder was not considered further: it parses untrusted input and
has to be maintained.

## Cost

| Item | Rough figure |
|---|---|
| Generation | Lambda at 1024 MB for a few hundred ms per image; the same ETag is never generated twice |
| Cache storage | tens of KB per thumbnail, expiring after 30 days |
| Invocations | one per page (plus a few if anything is `pending`) |

Prices change, so confirm with the Pricing API before quoting any figure.

## Limits (not addressed)

- **No SVG.** Pillow does not rasterise it. `FilePreview` keeps a separate list of what
  it can *open*, and `tests/hooks/useThumbnails.test.ts` asserts the two lists agree.
- **No RAW or EXR.** Pillow either cannot read them or needs plugins this layer does
  not carry.
- **No video thumbnails.** Frame extraction is a different dependency (ffmpeg).
- **Rotation is not visible in the row.** The thumbnail is cropped to a 32px square,
  so the aspect ratio does not show (the cached object is 108x192 — the rotation is
  applied).

## Verified against a real deployment

Deployed to the ap-northeast-1 sandbox and driven by invoking the Lambda directly.

| Check | Result |
|---|---|
| Generation | 2 of 3 JPEGs rendered; the first thumbnail is 1,168 bytes |
| Downscaling | `192x144`, aspect ratio preserved (192px edge requested) |
| **EXIF** | **0 entries** — no metadata carried over, on real data |
| Cache | a second call did not add objects to the cache, so nothing was regenerated |
| Unsupported extension | `.pdf` skipped as `unsupported type`, without a download |
| Image extension, other content | `tokyo_aerial.jpg` skipped as `not a readable image` — and that file really is **JSON text with a `.jpg` extension**, so the refusal is correct |
| Layers | `PillowLayer1220E379832F` and `SharedPythonLayer4dc7cbd5285c…`, matching the working tree's fingerprint |

The last row was luck worth keeping. The demo data contains a file whose extension is an
image and whose content is metadata JSON, so the decision to put it in `skipped` rather
than fail the page paid off immediately.

### On a handset (iPhone)

<img src="screenshots/portal-mobile-thumbnails.png" alt="A file list on an iPhone showing small pictures of the images" width="360">

Five images have pictures and `estimate.pdf` keeps its 📕. `photo_front.jpg` looks washed
out because the original is very nearly a single colour (240,240,240) — the rendering is
faithful.

### What the deployment ran into

`ampx sandbox` updates the stack with `DisableRollback=true`, and CloudFormation
**refuses to replace a LayerVersion whose content changed** under that setting, so the
first deploy stopped at `UPDATE_FAILED`. The recorded recovery was `sandbox delete` and
recreate, which destroys the Cognito users and DynamoDB tables. Putting the fingerprint
in the layer's **logical ID** turns the replacement into a create plus a delete, and
that recovered the stack without deleting anything. See
`docs/agent/portal-cdk-quality-gates.md`.

## References

- The listing's authorization boundary: `shared/portal_path_scope.py`
- The caps and why they exist: the top of `functions/thumbnails/handler.py`
- The invocation-count check: `tests/hooks/useThumbnailsBatching.test.tsx`
