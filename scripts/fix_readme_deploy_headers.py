#!/usr/bin/env python3
"""Update deployment section headers that still say "CloudFormation" to "SAM",
since the documented command is now `sam build && sam deploy`.

Only touches Markdown HEADER lines (starting with #) that contain both
"CloudFormation" and a localized deploy word — leaving prose mentions of
CloudFormation untouched. Idempotent.

Usage: python3 scripts/fix_readme_deploy_headers.py <README.md> [--write]
"""
from __future__ import annotations

import sys
from pathlib import Path

DEPLOY_WORDS = ("デプロイ", "Deployment", "Deploy", "部署", "배포",
                "Bereitstellung", "Déploiement", "Despliegue")


def transform(content: str) -> tuple[str, int]:
    lines = content.split("\n")
    count = 0
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#") and "CloudFormation" in line \
                and any(w in line for w in DEPLOY_WORDS):
            new = line.replace("AWS CloudFormation", "AWS SAM").replace("CloudFormation", "SAM")
            if new != line:
                lines[i] = new
                count += 1
    return "\n".join(lines), count


def main() -> int:
    path = Path(sys.argv[1])
    write = "--write" in sys.argv
    new, count = transform(path.read_text())
    if write and count:
        path.write_text(new)
    print(f"{'WROTE' if (write and count) else 'dry'} {path} ({count})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
