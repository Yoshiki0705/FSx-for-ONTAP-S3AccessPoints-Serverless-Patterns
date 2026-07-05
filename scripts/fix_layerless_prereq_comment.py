#!/usr/bin/env python3
"""Make the `sam build` prerequisite comment accurate for the 3 flexcache
patterns that have NO SharedLayer (their handlers don't import shared/):
automotive-cae, gaming-build-pipeline, life-sciences-research.

For these, drop the "and shared layer" wording (nothing to package into a
layer). Other patterns keep the shared-layer wording because they do declare
a SharedLayer. Applies to both the Deployment and local-testing code blocks.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = [
    "flexcache/automotive-cae",
    "flexcache/gaming-build-pipeline",
    "flexcache/life-sciences-research",
]

REPLACEMENTS = {
    "README.md": (
        "# 前提: AWS SAM CLI が必要です。sam build がコードと共有レイヤーを自動でパッケージングします。",
        "# 前提: AWS SAM CLI が必要です。sam build がコードを自動でパッケージングします。",
    ),
    "README.en.md": (
        "# Prerequisite: AWS SAM CLI required. 'sam build' packages the code and shared layer automatically.",
        "# Prerequisite: AWS SAM CLI required. 'sam build' packages the function code automatically.",
    ),
    "README.ko.md": (
        "# 전제 조건: AWS SAM CLI 필요. 'sam build'가 코드와 공유 레이어를 자동으로 패키징합니다.",
        "# 전제 조건: AWS SAM CLI 필요. 'sam build'가 함수 코드를 자동으로 패키징합니다.",
    ),
    "README.zh-CN.md": (
        "# 前提条件：需要 AWS SAM CLI。'sam build' 会自动打包代码和共享层。",
        "# 前提条件：需要 AWS SAM CLI。'sam build' 会自动打包函数代码。",
    ),
}


def main() -> int:
    changed = 0
    for pat in PATTERNS:
        d = ROOT / "solutions" / pat
        for fname, (old, new) in REPLACEMENTS.items():
            p = d / fname
            if not p.exists():
                continue
            text = p.read_text()
            if old in text:
                p.write_text(text.replace(old, new))
                changed += 1
                print(f"updated {p.relative_to(ROOT)}")
    print(f"\n{changed} file(s) updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
