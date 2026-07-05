#!/usr/bin/env python3
"""Check for deprecated/EOL Bedrock model IDs in the codebase.

This CI guardrail prevents deployment of templates or code referencing
models that are LEGACY or approaching End-of-Life.

Maintains a list of known deprecated model IDs. Add new entries as
AWS Health notifications arrive.
"""

import glob
import sys
from pathlib import Path

# Model IDs that are LEGACY or EOL — update this list as AWS notifies.
# Replacements are geo-prefixed cross-region INFERENCE-PROFILE IDs, not bare model IDs:
# Nova/newer Claude cannot be invoked on-demand by the bare ID in some regions, and the
# repo enforces profile IDs (see docs/bedrock-inference-profiles.md + the inference-profile
# guard). Note prefix availability is model-specific — claude-haiku-4-5 / claude-sonnet-4-5
# have jp./global. but no apac.; global. is used here for portability.
DEPRECATED_MODELS = {
    "anthropic.claude-3-haiku-20240307-v1:0": {
        "status": "LEGACY → EOL 2026-09-10",
        "replacement": "global.anthropic.claude-haiku-4-5-20251001-v1:0",
    },
    "anthropic.claude-3-5-sonnet-20240620-v1:0": {
        "status": "LEGACY → EOL 2026-07-30",
        "replacement": "global.anthropic.claude-sonnet-4-5-20250929-v1:0",
    },
    "anthropic.claude-3-sonnet-20240229-v1:0": {
        "status": "LEGACY",
        "replacement": "global.anthropic.claude-sonnet-4-5-20250929-v1:0",
    },
    "anthropic.claude-3-5-sonnet-20241022-v2:0": {
        "status": "LEGACY",
        "replacement": "global.anthropic.claude-sonnet-4-5-20250929-v1:0",
    },
}

# File patterns to scan
SCAN_PATTERNS = [
    "solutions/**/template.yaml",
    "solutions/**/template-deploy.yaml",
    "solutions/**/handler.py",
    "solutions/**/samconfig.toml.example",
    "scripts/*.py",
    "shared/**/*.py",
]

# Directories/files to skip
SKIP_PATTERNS = {"__pycache__", ".git", "node_modules", ".hypothesis", ".ruff_cache"}
# Self-reference: this script contains model IDs as data — exclude from scan
SELF_SCRIPT = "scripts/check_deprecated_models.py"


def should_skip(path: str) -> bool:
    parts = Path(path).parts
    if str(Path(path)) == SELF_SCRIPT:
        return True
    return any(skip in parts for skip in SKIP_PATTERNS)


def scan_file(filepath: str) -> list[tuple[int, str, str]]:
    """Scan a single file for deprecated model IDs. Returns (line_no, model_id, line_content)."""
    findings = []
    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            for line_no, line in enumerate(f, 1):
                for model_id in DEPRECATED_MODELS:
                    if model_id in line:
                        findings.append((line_no, model_id, line.strip()))
    except (OSError, UnicodeDecodeError):
        pass
    return findings


def main() -> int:
    print("🔍 Checking for deprecated/EOL Bedrock model IDs...")
    print(f"   Scanning for {len(DEPRECATED_MODELS)} known deprecated models\n")

    all_files: set[str] = set()
    for pattern in SCAN_PATTERNS:
        all_files.update(glob.glob(pattern, recursive=True))

    # Also scan docs for stale references (warning only)
    doc_files = set(glob.glob("docs/**/*.md", recursive=True))

    errors: list[str] = []
    warnings: list[str] = []

    for filepath in sorted(all_files):
        if should_skip(filepath):
            continue
        findings = scan_file(filepath)
        for line_no, model_id, line_content in findings:
            info = DEPRECATED_MODELS[model_id]
            errors.append(
                f"  {filepath}:{line_no} — {model_id}\n"
                f"    Status: {info['status']}\n"
                f"    Replace with: {info['replacement']}"
            )

    for filepath in sorted(doc_files):
        if should_skip(filepath):
            continue
        findings = scan_file(filepath)
        for line_no, model_id, line_content in findings:
            info = DEPRECATED_MODELS[model_id]
            warnings.append(f"  {filepath}:{line_no} — {model_id}\n    Status: {info['status']}")

    if warnings:
        print(f"⚠️  {len(warnings)} deprecated model reference(s) in docs (warning):")
        for w in warnings:
            print(w)
        print()

    if errors:
        print(f"❌ {len(errors)} deprecated model reference(s) in code/templates (BLOCKING):")
        for e in errors:
            print(e)
        print("\n💡 Run: grep -r 'OLD_MODEL_ID' --include='*.yaml' --include='*.py' | grep -v __pycache__")
        print("   Then replace with the suggested model ID.")
        return 1

    print("✅ No deprecated model IDs found in code/templates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
