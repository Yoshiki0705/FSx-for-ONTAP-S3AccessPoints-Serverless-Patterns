#!/usr/bin/env python3
"""Replace broken `aws cloudformation deploy --template-file .../template.yaml`
command blocks in README files with the working `sam build && sam deploy` flow.

Preserves the pattern-specific --stack-name, --parameter-overrides, and --region.
Drops the --template-file line and converts capabilities to CAPABILITY_NAMED_IAM
plus --resolve-s3 (SAM packages/uploads the code + shared Layer automatically).

Usage: python3 scripts/fix_readme_deploy_commands.py <README.md> [--write]
"""
from __future__ import annotations

import sys
from pathlib import Path


def transform(content: str) -> tuple[str, int]:
    lines = content.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)
    count = 0
    while i < n:
        line = lines[i]
        if line.strip().rstrip("\\").strip() == "aws cloudformation deploy":
            # Capture the command block until a line containing '--region'
            block: list[str] = []
            j = i
            while j < n:
                block.append(lines[j])
                if "--region" in lines[j] and "cloudformation" not in lines[j]:
                    break
                j += 1
            # Build replacement, preserving stack-name / parameter-overrides / region
            new_block = ["sam build", "", "sam deploy \\"]
            for bl in block[1:]:  # skip the 'aws cloudformation deploy' line
                stripped = bl.strip()
                if stripped.startswith("--template-file"):
                    continue  # drop
                if stripped.startswith("--capabilities"):
                    new_block.append("  --capabilities CAPABILITY_NAMED_IAM \\")
                    new_block.append("  --resolve-s3 \\")
                    continue
                new_block.append(bl)
            out.extend(new_block)
            count += 1
            i = j + 1
            continue
        out.append(line)
        i += 1
    return "\n".join(out), count


def main() -> int:
    path = Path(sys.argv[1])
    write = "--write" in sys.argv
    new, count = transform(path.read_text())
    if write:
        path.write_text(new)
        print(f"WROTE {path} ({count} block(s))")
    else:
        print(f"[dry-run] {path}: {count} block(s) would change")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
