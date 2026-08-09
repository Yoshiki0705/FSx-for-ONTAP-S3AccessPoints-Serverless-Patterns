# Office File Preview — Design Investigation and Options

🌐 **Language / 言語**: [日本語](office-preview-design.md) | [English](office-preview-design.en.md)

## Requirements

We want to preview `.docx`, `.xlsx`, `.pptx`, and `.pdf` in the browser from the portal's "All Files" section. Today only download via a presigned URL is available (image files already have inline preview).

## Option comparison

| Approach | Cold start | Cost | Constraints | Rating |
|-----------|:---:|------|------|:---:|
| **A. Lambda Container Image + LibreOffice** | 3-8s (first call) | ~$0.002/conversion | Image size about 833MB, x86_64 only | ⭐⭐⭐ |
| **B. Lambda Layer (Brotli compression)** | 1-2s (decompression) | ~$0.001/conversion | Fits within the 250MB limit (95MB compressed) but is **x86_64-only**, which does not coexist with this project's ARM64 uniformity (see below) | ⭐ |
| **C. Textract → text display** | 0.5s | $1.50/1000 pages | Text + tables only (layout is lost) | ⭐⭐ |
| **D. Client-side (pdf.js + docx-preview)** | 0s | $0 | PDF/DOCX only, no xlsx support | ⭐⭐ |
| **E. External SaaS (CloudConvert, etc.)** | 0s | $0.01/conversion | Data is sent outside (compliance concern) | ⭐ |

## Recommended: hybrid approach D → A

### Phase 1 (can be done immediately): client-side preview

Zero cost, no additional Lambda. Rendered directly in the browser:

| File format | Library | Size | Notes |
|------------|-----------|------|------|
| PDF | [pdf.js](https://mozilla.github.io/pdf.js/) (Mozilla) | 350KB | Industry standard, Canvas rendering |
| DOCX | [docx-preview](https://github.com/nicholasguo/docx-preview) | 80KB | XML → HTML conversion |
| XLSX | — | — | Difficult client-side |
| PPTX | — | — | Difficult client-side |

**Implementation sketch**:
```typescript
// FilePreview.tsx
if (key.endsWith(".pdf")) {
  const url = await getPresignedUrl(key);
  return <iframe src={url} style={{ width: "100%", height: "600px" }} />;
}
if (key.endsWith(".docx")) {
  const blob = await fetch(presignedUrl).then(r => r.blob());
  renderAsync(blob, previewContainer); // docx-preview
}
```

**Trade-offs**:
- PDF: just pass the presigned URL to an `<iframe>` (rendered by the browser's built-in viewer)
- DOCX: layout fidelity is 70-80% (complex styling breaks)
- XLSX/PPTX: not supported by this approach

### Phase 2 (future): Lambda Container Image + LibreOffice

If XLSX/PPTX support becomes necessary:

```dockerfile
FROM public.ecr.aws/shelf/lambda-libreoffice-base:26.2-python3.13-x86_64

# Required. LibreOffice writes a user profile on first launch, and every
# path outside /tmp is read-only in Lambda, so omitting this ends in
# "User installation could not be completed" and exit code 77.
ENV HOME=/tmp

COPY handler.py ${LAMBDA_TASK_ROOT}
CMD ["handler.handler"]
```

The implemented Dockerfile lives at [`functions/office-convert/Dockerfile`](../functions/office-convert/Dockerfile); local build and conversion behavior have been verified (it is not yet referenced from a `DockerImageFunction`).

- [shelfio/libreoffice-lambda-base-image](https://github.com/shelfio/libreoffice-lambda-base-image): LibreOffice 26.2, supports Python 3.12/3.13/3.14
- Distributed via Amazon ECR Public (`public.ecr.aws/shelf/lambda-libreoffice-base`). Tags use the version-first form `26.2-python3.13-x86_64`
- Being a Container Image, it avoids the 250MB Layer limit (up to 10GB). Image size is about 833 MB
- x86_64 only (LibreOffice does not support ARM64). Every other Lambda in this project is ARM64, so this function alone needs an explicit `architecture: lambda.Architecture.X86_64`
- `handler.py` invokes `libreoffice` assuming it resolves on PATH. The base image provides a symlink `/usr/bin/libreoffice` → `/opt/libreoffice26.2/program/soffice`, so it resolves as-is
- Cold start: 3-8 seconds (can be mitigated with Provisioned Concurrency)

**Flow**:
```
Browser → AppSync → Lambda (Container, x86_64)
                      ↓
                S3 AP GetObject (fetch the Office file)
                      ↓
                LibreOffice --convert-to pdf
                      ↓
                S3 PutObject (store the PDF in the cache bucket)
                      ↓
                Presigned URL → Browser (<iframe>)
```

## Details of the Lambda Layer size problem

| Constraint | Value |
|------|-----|
| Lambda Layer total limit (uncompressed) | 250 MB |
| Lambda Container Image limit | 10 GB |
| Lambda /tmp directory | 512 MB (expandable up to 10 GB) |

[shelfio/libreoffice-lambda-layer](https://github.com/shelfio/libreoffice-lambda-layer) fits into **95 MB** using Brotli compression, which is within the Layer limit. However:
- It decompresses into /tmp at runtime → 1-2 seconds of overhead
- It does not work on Python 3.12 ARM64 (x86_64 builds only)
- **Every Lambda in this project is ARM64** → the Layer approach is not compatible

→ Container Image (x86_64) is the realistic option.

## Decision at this point

**Implement Phase 1 (client-side PDF + DOCX).**

Reasons:
1. Zero cost, no additional infrastructure
2. PDF covers 80%+ of preview demand
3. The ARM64-only policy can be maintained
4. Container Image can wait until there is clear demand for XLSX/PPTX

## Implementation tasks (Phase 1)

- [ ] `npm install docx-preview` (DOCX rendering)
- [ ] Add PDF iframe + DOCX preview branches to `FilePreview.tsx`
- [ ] Supported formats: `.pdf` (iframe), `.docx` (docx-preview), images (existing presigned URL)
- [ ] Unsupported formats: show a download link (unchanged)
- [ ] Size limit: show "file is too large" above 10MB

## References

- [shelfio/libreoffice-lambda-layer](https://github.com/shelfio/libreoffice-lambda-layer) — 95MB Brotli-compressed Layer
- [shelfio/libreoffice-lambda-base-image](https://github.com/shelfio/libreoffice-lambda-base-image) — Container Image base
- [docx-preview](https://github.com/nicholasguo/docx-preview) — client-side DOCX rendering
- [pdf.js](https://mozilla.github.io/pdf.js/) — Mozilla PDF renderer
