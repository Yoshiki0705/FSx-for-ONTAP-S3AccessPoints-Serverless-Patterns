# Screenshot Addition Workflow

Standard procedure for adding a new screenshot to `docs/screenshots/masked/`.
Follows the dual-Kiro coordination rules (A/B/C/D/E/F) agreed on 2026-05-11.

## Quick Reference

```
1. Capture screenshot           (browser or headless)
2. Save to originals/           (docs/screenshots/originals/ucN-demo/)
3. Run v7 OCR masking           (scripts/mask_uc_demos.py ucN-demo)
4. Verify zero leaks            (scripts/_check_sensitive_leaks.py, rule E)
5. Update industry mapping      (docs/screenshots/uc-industry-mapping.md if new UC, rule F)
6. Update demo-guide reference  (ucN/docs/demo-guide.md)
7. Update main README table row (README.md UI/UX section, rule B)
8. Commit with descriptive msg  (rule C for removals/replacements)
9. Notify parallel thread       ([X] SCREENSHOTS ADDED: ucN.png, ...)
```

## Detailed Steps

### 1. Capture

- **Manual (AWS Console)**: Log into AWS Management Console, navigate to
  the target service view, capture via OS screenshot tool (Cmd+Shift+4 on
  macOS)
- **Chrome DevTools MCP**: Only if browser is free (check with parallel
  thread, see Rule G below)
- Save as PNG, use descriptive filename: `ucN-<service>-<view>.png`

Example filenames:
- `uc11-product-tags.png` — UC11 product tagging UI
- `uc14-claims-report.png` — UC14 claims assessment report
- `uc6-athena-query-result.png` — UC6 Athena query results

### 2. Save to originals

```bash
mkdir -p docs/screenshots/originals/ucN-demo/
mv ~/Desktop/screenshot.png docs/screenshots/originals/ucN-demo/ucN-<name>.png
```

**Important**: `docs/screenshots/originals/` is **gitignored**. Original
screenshots with sensitive strings (account IDs, AP ARNs, etc.) are kept
locally only.

### 3. Run v7 OCR masking

```bash
# Prerequisites (one-time):
brew install tesseract tesseract-lang
pip3 install pytesseract pillow

# Run masking
python3 scripts/mask_uc_demos.py ucN-demo
```

This uses the v7 OCR-based precision masking:
- `pytesseract.image_to_data(lang="eng+jpn")` detects word-level bounding boxes
- Each word containing a sensitive substring gets a small black rectangle
- Top-right account widget is masked unconditionally (fixed AWS console position)
- 4-pass iterative re-scan catches residual leaks
- Output saved to `docs/screenshots/masked/ucN-demo/`

### 4. Verify zero leaks (Rule E — mandatory)

```bash
python3 scripts/_check_sensitive_leaks.py
```

Expected output: `Scanned: N masked images, Images with detectable sensitive substrings: 0`

If any leaks are reported:
- Inspect the affected image with `read_media_file` or manual preview
- Check that `scripts/_sensitive_strings.py` contains all relevant strings
- Re-run `mask_uc_demos.py` (the script is idempotent and will re-mask)
- Loop until 0 leaks

**Do not commit a screenshot with detectable leaks.** Even if the leak
looks minor (partial string, low-confidence OCR detection), the cost of
re-masking is minutes, the cost of a PII leak in a public repo is hours
of revert + force-push + audit trail.

### 5. Update industry mapping (Rule F)

If you're adding a screenshot for a UC that already exists in
`docs/screenshots/uc-industry-mapping.md`, skip this step.

If you're adding a new UC (e.g., a future UC18), update the mapping file
BEFORE updating any README or demo-guide. This file is the single source
of truth for UC industry labels across 8 languages.

### 6. Update demo-guide reference

Add the new screenshot to the relevant section of `ucN/docs/demo-guide.md`:

```markdown
### N. <Screen Description>

![UCN: <description>](../../docs/screenshots/masked/ucN-demo/ucN-<name>.png)

<!-- SCREENSHOT: ucN-<name>.png
     Content: <what the screenshot shows>
     Masked: <what was masked and why> -->
```

Update the Japanese version first (`demo-guide.md`), then propagate to 7
language versions in the next translation batch.

### 7. Update main README table row (Rule B)

Edit the "UI/UX スクリーンショット" section table in `README.md`:

- Locate the row for the UC (e.g., `| UC11 | 小売・カタログ | ...`)
- Update 掲載画面数 (screenshot count)
- Update 主な画面内容 (main screen content) if the new screenshot represents
  a new screen type not yet mentioned

### 8. Commit

```bash
git add docs/screenshots/masked/ucN-demo/ucN-<name>.png
git add ucN/docs/demo-guide.md
git add README.md
# Optional (if adding new UC):
git add docs/screenshots/uc-industry-mapping.md

git commit -m "docs(ucN-demo): add screenshot of <feature> (v7 OCR masked, 0 leaks)"
```

Commit message template:
```
docs(ucN-demo): add <screen description> screenshot

- File: docs/screenshots/masked/ucN-demo/ucN-<name>.png
- Content: <what the screenshot shows>
- Persona: <role that views this screen>
- Masked: OCR-based v7 precision mask, 0 leaks verified
```

### 9. Notify parallel thread

Post to the shared chat:
```
[X] SCREENSHOTS ADDED: ucN-<name>.png (0 leaks, v7 OCR)
    Affected files: docs/screenshots/masked/ucN-demo/, ucN/docs/demo-guide.md, README.md
    Next: <next action if any>
```

## Removal / Replacement Workflow (Rule C)

1. **Notify first**: `[X] I plan to remove/replace ucN-<name>.png, reason: <reason>`
2. Wait for `[Y] ACK, go ahead` or objection
3. Remove the file:
   ```bash
   git rm docs/screenshots/masked/ucN-demo/ucN-<name>.png
   ```
4. Update demo-guide.md to remove the `![...]` reference
5. Update main README table row (reduce 掲載画面数 count)
6. Commit and notify completion:
   ```
   [X] SCREENSHOT REMOVED: ucN-<name>.png
   ```

## Rules Recap (2026-05-11)

- **A**: Section-wide rewrite requires pre-approval; numeric updates (counts) don't
- **B**: New screenshot order: masked/ → demo-guide → main README
- **C**: Removal / replacement requires pre-notification
- **D**: Industry classification changes require pre-agreement (current: JP fixed)
- **E**: OCR leak check mandatory before commit (0 leaks only)
- **F**: Industry mapping updates go through `docs/screenshots/uc-industry-mapping.md`

Additional (proposed):

- **G**: Chrome DevTools MCP browser coordination — check with parallel thread before `new_page`, use `--isolated` if both threads need simultaneous access

## Related Documents

- [`docs/screenshots/MASK_GUIDE.md`](MASK_GUIDE.md) — Masking target strings and patterns (gitignored)
- [`docs/screenshots/uc-industry-mapping.md`](uc-industry-mapping.md) — UC × industry × 8 languages table
- [`scripts/mask_uc_demos.py`](../../scripts/mask_uc_demos.py) — v7 OCR mask script
- [`README.md`](../../README.md) — Main README with UI/UX screenshot table
