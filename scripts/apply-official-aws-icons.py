#!/usr/bin/env python3
"""Bring the file-portal architecture diagrams onto the official AWS icon set.

Replaces draw.io's bundled `mxgraph.aws4` shapes (2019 generation) with icons from
the official AWS Architecture Icons asset package, and enforces the icon-usage rules
from the official deck:

  * Service icons embedded at their native size (80x80 for Arch_*_64, which is a
    64px artwork on an 80px canvas) and resource icons at 48x48 — never rescaled.
  * Service labels carry the full official name with its `Amazon`/`AWS` prefix, and
    abbreviations are expanded (`ALB` -> `Elastic Load Balancing`).
  * Labels stay within two lines.
  * Arrows use the preset "Open Arrow" format in a single colour — no bespoke
    per-flow colours, widths, or dash patterns.

Because official icons are larger than the 50/60px shapes previously used, all
coordinates are scaled by LAYOUT_SCALE so relative spacing survives; each icon is
re-centred on its original centre point.

The icon package is NOT vendored into this repository. Point ICON_ROOT at a local
extraction of the official package (see AWS_ICON_PACKAGE_URL). Icons are embedded
as base64 into the finished diagrams, which is the permitted "use in architecture
diagrams" — the raw asset library itself is deliberately not committed.

Usage:
    python3 scripts/apply-official-aws-icons.py --icon-root /tmp/awsicons
    python3 scripts/generate-en-diagrams.py
    bash scripts/export-diagrams.sh
"""

from __future__ import annotations

import argparse
import base64
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "docs" / "diagrams"

AWS_ICON_PACKAGE_URL = "https://aws.amazon.com/architecture/icons/  (Asset Package, e.g. Icon-package_04302026)"

SOURCES = [
    "file-portal-overview.drawio",
    "file-portal-architecture.drawio",
    "nextcloud-only-architecture.drawio",
    "amplify-nextcloud-combined-architecture.drawio",
]

# Icons grew from 50/60px to their native 80/48px, so spread the layout to match.
# Horizontal needs the most room because official service names are long
# ("Amazon Rekognition" is ~130px at 13px, so a 160px pitch leaves ~30px clearance).
# Vertical labels don't compete for width, so it is compressed to avoid dead space.
SCALE_X = 1.6
SCALE_Y = 1.25

SERVICE_SIZE = 80  # Arch_*_64.svg native canvas
RESOURCE_SIZE = 48  # Res_*_48.svg native canvas

# cell id -> (official SVG filename, native size, default label)
# Labels use the official service name; a second line may carry context.
ICONS: dict[str, tuple[str, int, str]] = {
    # people / endpoints (generic resource icons, not AWS services -> no prefix)
    "users": ("Res_Users_48_Light.svg", RESOURCE_SIZE, "利用者（Web ブラウザ）"),
    "browser": ("Res_Users_48_Light.svg", RESOURCE_SIZE, "Web ブラウザ"),
    "browser-ai": ("Res_Users_48_Light.svg", RESOURCE_SIZE, "Web ブラウザ&#xa;(AI ポータル)"),
    "browser-files": ("Res_Users_48_Light.svg", RESOURCE_SIZE, "Web ブラウザ&#xa;(ファイル管理)"),
    "nfs-client": ("Res_Server_48_Light.svg", RESOURCE_SIZE, "NFS クライアント"),
    "smb-client": ("Res_Client_48_Light.svg", RESOURCE_SIZE, "SMB クライアント"),
    # AWS services
    "quick-desktop": ("Arch_Amazon-Quick_64.svg", SERVICE_SIZE, "Amazon Quick"),
    "amplify": ("Arch_AWS-Amplify_64.svg", SERVICE_SIZE, "AWS Amplify"),
    "cognito": ("Arch_Amazon-Cognito_64.svg", SERVICE_SIZE, "Amazon Cognito"),
    "mcp-gw": (
        "Arch_Amazon-Bedrock-AgentCore_64.svg",
        SERVICE_SIZE,
        "Amazon Bedrock AgentCore",
    ),
    "appsync": ("Arch_AWS-AppSync_64.svg", SERVICE_SIZE, "AWS AppSync"),
    "lambda": ("Arch_AWS-Lambda_64.svg", SERVICE_SIZE, "AWS Lambda&#xa;(VPC 外 / ARM64)"),
    "bedrock": ("Arch_Amazon-Bedrock_64.svg", SERVICE_SIZE, "Amazon Bedrock"),
    "rekognition": ("Arch_Amazon-Rekognition_64.svg", SERVICE_SIZE, "Amazon Rekognition"),
    "athena": ("Arch_Amazon-Athena_64.svg", SERVICE_SIZE, "Amazon Athena"),
    "textract": ("Arch_Amazon-Textract_64.svg", SERVICE_SIZE, "Amazon Textract"),
    "comprehend": ("Arch_Amazon-Comprehend_64.svg", SERVICE_SIZE, "Amazon Comprehend"),
    "nextcloud": (
        "Arch_Amazon-EC2_64.svg",
        SERVICE_SIZE,
        "Amazon EC2&#xa;(Nextcloud / Docker)",
    ),
    "alb": ("Arch_Elastic-Load-Balancing_64.svg", SERVICE_SIZE, "Elastic Load Balancing"),
    "rds": ("Arch_Amazon-RDS_64.svg", SERVICE_SIZE, "Amazon RDS&#xa;(MariaDB)"),
    "eventbridge": (
        "Arch_Amazon-EventBridge_64.svg",
        SERVICE_SIZE,
        "Amazon EventBridge&#xa;Scheduler",
    ),
    "sfn": ("Arch_AWS-Step-Functions_64.svg", SERVICE_SIZE, "AWS Step Functions"),
    "s3-objectlock": (
        "Arch_Amazon-Simple-Storage-Service_64.svg",
        SERVICE_SIZE,
        "Amazon S3&#xa;(Object Lock / WORM)",
    ),
    # S3 access points have a dedicated official resource icon
    "s3ap": (
        "Res_Amazon-Simple-Storage-Service_General-Access-Points_48.svg",
        RESOURCE_SIZE,
        "Amazon S3 Access Point&#xa;(Internet origin)",
    ),
    "fsxn": (
        "Arch_Amazon-FSx-for-NetApp-ONTAP_64.svg",
        SERVICE_SIZE,
        "Amazon FSx for&#xa;NetApp ONTAP",
    ),
}

# Non-icon cells whose labels also need the official service-name prefix.
EXTRA_LABELS: dict[str, str] = {
    "ai-group": "AWS Lambda + AI サービス&#xa;(Amazon Bedrock / Amazon Textract / Amazon Athena ほか)",
}

# Cells removed because the notes box now carries the same statement. Keeping both
# duplicated the multi-protocol sentence in every diagram.
CELLS_TO_DROP = {"note1"}

# Per-file label overrides where the node carries diagram-specific context.
LABEL_OVERRIDES: dict[str, dict[str, str]] = {
    "file-portal-overview.drawio": {
        "amplify": "AWS Amplify&#xa;(Gen2 / AI 処理ダッシュボード)",
        "nextcloud": "Amazon EC2&#xa;(Nextcloud / ファイル共有 UI)",
        "s3ap": "Amazon S3 Access Point",
    },
    "nextcloud-only-architecture.drawio": {
        "browser": "Web ブラウザ&#xa;(ファイル管理 + 同期)",
        "sfn": "AWS Step Functions&#xa;(UC1-28)",
    },
    "amplify-nextcloud-combined-architecture.drawio": {
        "smb-client": "SMB クライアント&#xa;(Windows)",
    },
    "file-portal-architecture.drawio": {
        "smb-client": "SMB クライアント&#xa;(Windows)",
        "appsync": "AWS AppSync&#xa;(GraphQL API)",
    },
}

# Preset "Open Arrow" in a single colour, per the official arrow rule.
ARROW_COLOUR = "#232F3E"
ARROW_STYLE = (
    "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;"
    f"endArrow=open;endFill=0;strokeColor={ARROW_COLOUR};strokeWidth=1;"
    "fontSize=12;fontColor=" + ARROW_COLOUR + ";labelBackgroundColor=#ffffff;"
)

# With colour coding gone the legend's colour rows carry no meaning; keep only the
# access-point clarification, which is genuinely load-bearing information.
# Pre-escaped for direct insertion into an XML attribute. Labels elsewhere already
# carry `&#xa;` entities, so escaping is applied per-value here rather than globally.
#
# Formatting follows Japanese figure-annotation convention: `※` is the standard
# marker for 注記/補足 and is numbered (※1, ※2) when there is more than one. Each
# item is a bold headline in 体言止め followed by its detail on the next line, so the
# box can be scanned rather than read as a paragraph.
NOTE_TEXT = (
    "&lt;b&gt;補足&lt;/b&gt;&lt;br&gt;"
    "&lt;b&gt;※1 S3 Access Point の Internet origin はパブリック公開ではない&lt;/b&gt;&lt;br&gt;"
    "Block Public Access が常時有効（無効化不可）。全リクエストに IAM 認証・認可が必要&lt;br&gt;"
    "&lt;b&gt;※2 マルチプロトコルでの同時アクセス&lt;/b&gt;&lt;br&gt;"
    "同一データに NFS / SMB / S3 API でアクセス可能。データ移行は不要"
)
NOTE_STYLE = (
    "rounded=1;whiteSpace=wrap;html=1;dashed=1;dashPattern=8 4;"
    "strokeColor=#232F3E;fillColor=#FFFFFF;align=left;verticalAlign=top;"
    "spacingLeft=10;spacingTop=4;fontSize=11;fontColor=#232F3E;"
)

CELL_RE = re.compile(r"<mxCell\b[^>]*?(?:/>|>.*?</mxCell>)", re.S)
GEO_RE = re.compile(r"<mxGeometry\b[^>]*?/>|<mxGeometry\b[^>]*?>.*?</mxGeometry>", re.S)


def find_icon(icon_root: Path, filename: str) -> Path:
    hits = list(icon_root.rglob(filename))
    if not hits:
        raise FileNotFoundError(f"{filename} not found under {icon_root}")
    return hits[0]


def data_uri(path: Path) -> str:
    raw = path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:image/svg+xml,{b64}"


def attr(text: str, name: str) -> str | None:
    m = re.search(rf'\b{name}="([^"]*)"', text)
    return m.group(1) if m else None


def set_attr(text: str, name: str, value: str) -> str:
    if re.search(rf'\b{name}="', text):
        return re.sub(rf'\b{name}="[^"]*"', f'{name}="{value}"', text, count=1)
    return text


def scale_geometry(geo: str, is_icon: bool, native: int) -> str:
    """Scale positions; icons get native size re-centred on their old centre."""
    x, y = attr(geo, "x"), attr(geo, "y")
    w, h = attr(geo, "width"), attr(geo, "height")
    if x is None or y is None:
        return geo  # relative (edge) geometry
    fx, fy = float(x), float(y)
    fw = float(w) if w else 0.0
    fh = float(h) if h else 0.0

    if is_icon:
        cx, cy = (fx + fw / 2) * SCALE_X, (fy + fh / 2) * SCALE_Y
        geo = set_attr(geo, "x", f"{cx - native / 2:.0f}")
        geo = set_attr(geo, "y", f"{cy - native / 2:.0f}")
        geo = set_attr(geo, "width", str(native))
        geo = set_attr(geo, "height", str(native))
        return geo

    geo = set_attr(geo, "x", f"{fx * SCALE_X:.0f}")
    geo = set_attr(geo, "y", f"{fy * SCALE_Y:.0f}")
    if w:
        geo = set_attr(geo, "width", f"{fw * SCALE_X:.0f}")
    if h:
        geo = set_attr(geo, "height", f"{fh * SCALE_Y:.0f}")
    return geo


def convert(path: Path, icon_root: Path) -> dict[str, int]:
    xml = path.read_text(encoding="utf-8")
    name = path.name
    overrides = LABEL_OVERRIDES.get(name, {})
    stats = {"icons": 0, "labels": 0, "edges": 0, "notes": 0}

    def handle(m: re.Match[str]) -> str:
        nonlocal stats
        cell = m.group(0)
        cid = attr(cell, "id") or ""
        is_edge = 'edge="1"' in cell

        # --- arrows: single-colour preset Open Arrow ---
        if is_edge:
            if attr(cell, "style") is not None:
                cell = set_attr(cell, "style", ARROW_STYLE)
                stats["edges"] += 1
            return cell

        # --- drop cells whose content the notes box now covers ---
        if cid in CELLS_TO_DROP:
            stats["dropped"] = stats.get("dropped", 0) + 1
            return ""

        # --- the old legend becomes a plain notes box ---
        if cid == "p0-legend":
            cell = set_attr(cell, "value", NOTE_TEXT)
            cell = set_attr(cell, "style", NOTE_STYLE)
            stats["notes"] += 1
            geo = GEO_RE.search(cell)
            if geo:
                new_geo = scale_geometry(geo.group(0), False, 0)
                # 5 rendered lines (heading + 2 items x headline/detail), not the
                # scaled-up legend height
                new_geo = set_attr(new_geo, "height", "112")
                cell = cell.replace(geo.group(0), new_geo, 1)
            return cell

        # --- non-icon labels that still need the official prefix ---
        if cid in EXTRA_LABELS:
            cell = set_attr(cell, "value", EXTRA_LABELS[cid])
            stats["labels"] += 1
            geo = GEO_RE.search(cell)
            if geo:
                cell = cell.replace(geo.group(0), scale_geometry(geo.group(0), False, 0), 1)
            return cell

        spec = ICONS.get(cid)
        if spec is None:
            geo = GEO_RE.search(cell)
            if geo:
                cell = cell.replace(geo.group(0), scale_geometry(geo.group(0), False, 0), 1)
            return cell

        filename, native, default_label = spec
        uri = data_uri(find_icon(icon_root, filename))

        style = (
            "sketch=0;html=1;shape=image;verticalLabelPosition=bottom;"
            "verticalAlign=top;labelPosition=center;align=center;"
            "imageAspect=1;aspect=fixed;fontSize=13;fontColor=#232F3E;"
            f"image={uri};"
        )
        cell = set_attr(cell, "style", style)
        cell = set_attr(cell, "value", overrides.get(cid, default_label))
        stats["icons"] += 1
        stats["labels"] += 1

        geo = GEO_RE.search(cell)
        if geo:
            cell = cell.replace(geo.group(0), scale_geometry(geo.group(0), True, native), 1)
        return cell

    xml = CELL_RE.sub(handle, xml)
    path.write_text(xml, encoding="utf-8")

    try:
        # Parsing the file this function just wrote, on the line above, to catch
        # the failure mode that motivated the check: drawio silently discards
        # everything after a malformed cell and still exports successfully, so a
        # broken write is invisible without re-parsing. The input is our own
        # output, not untrusted XML, so defusedxml would add a dependency for a
        # threat that is not present here.
        ET.parse(path)  # nosec B314
        status = "XML OK"
    except ET.ParseError as exc:
        status = f"XML BROKEN -> {exc}"
    stats["status"] = status  # type: ignore[assignment]
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--icon-root",
        required=True,
        help="Local extraction of the official AWS Architecture Icons asset package",
    )
    args = ap.parse_args()
    icon_root = Path(args.icon_root)
    if not icon_root.is_dir():
        print(f"ERROR: --icon-root not a directory: {icon_root}", file=sys.stderr)
        print(f"Download the asset package from {AWS_ICON_PACKAGE_URL}", file=sys.stderr)
        return 1

    failed = False
    for fname in SOURCES:
        st = convert(SRC_DIR / fname, icon_root)
        print(
            f"  {fname}\n"
            f"    icons={st['icons']} labels={st['labels']} edges={st['edges']} "
            f"notes={st['notes']} dropped={st.get('dropped', 0)}  {st['status']}"
        )
        if "BROKEN" in str(st["status"]):
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
