#!/usr/bin/env python3
"""Check all screenshot sizes."""

import os

from PIL import Image

bases = [
    "solutions/genai/kb-selfservice-curation/docs/screenshots/masked",
    "solutions/genai/quick-agentic-workspace/docs/screenshots/masked",
]

for base in bases:
    print(f"\n{base}/")
    for f in sorted(os.listdir(base)):
        if f.endswith(".png"):
            im = Image.open(os.path.join(base, f))
            print(f"  {f}: {im.size}")
