#!/usr/bin/env python3
"""Generate English variants of the file-portal architecture diagrams.

The Japanese .drawio files under docs/diagrams/ are the single source of truth.
This script derives `<name>-en.drawio` from each by substituting the Japanese
label strings, so an edit to a JA diagram propagates to its EN counterpart by
re-running this script rather than by hand-editing two files.

Run this AFTER scripts/apply-official-aws-icons.py, since that script rewrites
labels to the official AWS service names (most of which are already English).

Usage (from repo root):
    python3 scripts/generate-en-diagrams.py
    bash scripts/export-diagrams.sh

The script fails if any CJK text survives translation, which catches labels
added to a JA diagram without a corresponding entry in TRANSLATIONS below.
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "docs" / "diagrams"

SOURCES = [
    "file-portal-overview.drawio",
    "file-portal-architecture.drawio",
    "nextcloud-only-architecture.drawio",
    "amplify-nextcloud-combined-architecture.drawio",
]

# Values are stored exactly as they appear inside the drawio `value="..."`
# attribute, so HTML is pre-escaped (&lt;b&gt;) and newlines are `&#xa;`.
TRANSLATIONS: dict[str, str] = {
    # ---- notes box -------------------------------------------------------
    # `※` is a Japanese-specific marker; the English variant uses *1 / *2, which is
    # the equivalent footnote convention.
    "&lt;b&gt;補足&lt;/b&gt;&lt;br&gt;"
    "&lt;b&gt;※1 S3 Access Point の Internet origin はパブリック公開ではない&lt;/b&gt;&lt;br&gt;"
    "Block Public Access が常時有効（無効化不可）。全リクエストに IAM 認証・認可が必要&lt;br&gt;"
    "&lt;b&gt;※2 マルチプロトコルでの同時アクセス&lt;/b&gt;&lt;br&gt;"
    "同一データに NFS / SMB / S3 API でアクセス可能。データ移行は不要": (
        "&lt;b&gt;Notes&lt;/b&gt;&lt;br&gt;"
        "&lt;b&gt;*1 Internet origin does not mean public access&lt;/b&gt;&lt;br&gt;"
        "Block Public Access is always enabled and cannot be disabled; every request "
        "requires IAM authentication and authorization&lt;br&gt;"
        "&lt;b&gt;*2 Concurrent multi-protocol access&lt;/b&gt;&lt;br&gt;"
        "The same data stays reachable over NFS / SMB / S3 API at once, with no data "
        "migration"
    ),
    # ---- diagram titles --------------------------------------------------
    "FSx for ONTAP S3 Access Points — ファイルポータル全体構成": (
        "FSx for ONTAP S3 Access Points — File Portal Architecture Overview"
    ),
    "FSx for ONTAP S3 Access Points — Amplify Gen2 による AI 処理ポータル構成": (
        "FSx for ONTAP S3 Access Points — AI Processing Portal with Amplify Gen2"
    ),
    "FSx for ONTAP S3 Access Points — Nextcloud によるファイル共有 UI 構成": (
        "FSx for ONTAP S3 Access Points — File Sharing UI with Nextcloud"
    ),
    "FSx for ONTAP S3 Access Points — Amplify Gen2 と Nextcloud の併用構成": (
        "FSx for ONTAP S3 Access Points — Amplify Gen2 and Nextcloud Side by Side"
    ),
    # ---- node labels -----------------------------------------------------
    "AWS Lambda + AI サービス&#xa;"
    "(Amazon Bedrock / Amazon Textract / Amazon Athena ほか)": (
        "AWS Lambda + AI services&#xa;"
        "(Amazon Bedrock / Amazon Textract / Amazon Athena, and others)"
    ),
    "Amazon EC2&#xa;(Nextcloud / ファイル共有 UI)": (
        "Amazon EC2&#xa;(Nextcloud / file sharing UI)"
    ),
    "AWS Amplify&#xa;(Gen2 / AI 処理ダッシュボード)": (
        "AWS Amplify&#xa;(Gen2 / AI processing dashboard)"
    ),
    "AWS Lambda&#xa;(VPC 外 / ARM64)": "AWS Lambda&#xa;(outside VPC / ARM64)",
    "Web ブラウザ&#xa;(ファイル管理 + 同期)": "Web browser&#xa;(file management + sync)",
    "Web ブラウザ&#xa;(AI ポータル)": "Web browser&#xa;(AI portal)",
    "Web ブラウザ&#xa;(ファイル管理)": "Web browser&#xa;(file management)",
    "SMB クライアント&#xa;(Windows)": "SMB client&#xa;(Windows)",
    "AI 処理・分析 (Amplify Gen2)": "AI Processing & Analytics (Amplify Gen2)",
    "ファイル管理・同期 (Nextcloud)": "File Management & Sync (Nextcloud)",
    "利用者（Web ブラウザ）": "Users (web browser)",
    "CloudTrail 監査ログ": "CloudTrail audit logs",
    "SMB クライアント": "SMB client",
    "NFS クライアント": "NFS client",
    "Web ブラウザ": "Web browser",
}

# Ordered longest-first so nested fragments are never translated prematurely.
ORDERED = sorted(TRANSLATIONS.items(), key=lambda kv: len(kv[0]), reverse=True)

# English labels are wider than their Japanese equivalents, which can push a
# centred label into a neighbour. Per-file, per-cell geometry nudges applied only
# to the EN variant. Keys: source filename -> cell id -> {x, y, width, height}.
# Coordinates are post-scale (see LAYOUT_SCALE in apply-official-aws-icons.py).
GEOMETRY_OVERRIDES: dict[str, dict[str, dict[str, int]]] = {}

# CJK ideographs, hiragana, katakana, and the full-width punctuation we use.
CJK_RE = re.compile(r"[\u3000-\u303F\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\uFF00-\uFFEF]")


def translate(xml: str) -> str:
    for ja, en in ORDERED:
        xml = xml.replace(ja, en)
    return xml


def apply_geometry_overrides(xml: str, overrides: dict[str, dict[str, int]]) -> str:
    for cell_id, attrs in overrides.items():
        pat = re.compile(
            r'(<mxCell id="' + re.escape(cell_id) + r'".*?<mxGeometry\b)([^/]*?)(/>)',
            re.S,
        )

        def repl(m: re.Match[str]) -> str:
            geo = m.group(2)
            for key, val in attrs.items():
                if re.search(rf'\b{key}="', geo):
                    geo = re.sub(rf'\b{key}="[^"]*"', f'{key}="{val}"', geo)
                else:
                    geo = f' {key}="{val}"' + geo
            return m.group(1) + geo + m.group(3)

        xml = pat.sub(repl, xml, count=1)
    return xml


def main() -> int:
    failures: list[str] = []

    for name in SOURCES:
        src = SRC_DIR / name
        if not src.exists():
            failures.append(f"{name}: source missing")
            continue

        xml = src.read_text(encoding="utf-8")
        out_xml = translate(xml)

        # keep bare '&' valid XML inside attributes (e.g. "AI Processing & Analytics")
        out_xml = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;|#)", "&amp;", out_xml)

        out_xml = apply_geometry_overrides(out_xml, GEOMETRY_OVERRIDES.get(name, {}))

        # diagram id should differ so both can coexist in a viewer
        out_xml = out_xml.replace('<diagram id="', '<diagram id="en-', 1)

        dst = SRC_DIR / name.replace(".drawio", "-en.drawio")
        dst.write_text(out_xml, encoding="utf-8")

        try:
            ET.parse(dst)
            xml_ok = "XML OK"
        except ET.ParseError as exc:
            xml_ok = f"XML BROKEN -> {exc}"
            failures.append(f"{dst.name}: {xml_ok}")

        if CJK_RE.search(out_xml):
            bad = [v for v in re.findall(r'value="([^"]*)"', out_xml) if CJK_RE.search(v)]
            failures.append(f"{dst.name}: untranslated text remains -> {bad[:4]}")
            print(f"  {dst.name}: {xml_ok}, UNTRANSLATED {bad[:4]}")
        else:
            print(f"  {dst.name}: {xml_ok}, no CJK remaining")

    if failures:
        print("\nFAILED:", file=sys.stderr)
        for f in failures:
            print("  -", f, file=sys.stderr)
        return 1

    print("\nAll EN variants generated cleanly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
