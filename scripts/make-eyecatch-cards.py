#!/usr/bin/env python3
"""Build 1200x630 social cards for the file-portal blog series.

Why this exists
---------------
Hatena Blog picks the first in-article image as the eyecatch when none is set,
and the resulting og:image is what X / Slack / Facebook render. Two figures in
this series are portrait (measured 1321x2003 and 1657x2335), so auto-selection
produces a badly cropped card. These cards are built at the 1.91:1 ratio the
social platforms actually crop to, so the framing is decided here rather than by
the platform.

Cards use the light-theme diagrams on white, matching the published figures (see
scripts/make-dark-diagrams.py for why light is the primary theme).

Accessibility note
------------------
Text burned into an image has no text alternative once a platform renders it as
a social card. Every HEADLINE below is therefore also present as plain text in
the corresponding article's opening lines, so the same statement is reachable
without seeing the image.

Usage:
    python3 scripts/make-eyecatch-cards.py
    python3 scripts/make-eyecatch-cards.py --check
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parent.parent
FIG_DIR = REPO_ROOT / "docs" / "images" / "png"
OUT_DIR = REPO_ROOT / "docs" / "images" / "eyecatch"

WIDTH, HEIGHT = 1200, 630  # the ratio social platforms crop to (1.91:1)

# Palette matches the published light-theme figures.
INK = "#232F3E"  # AWS squid ink: headline and rules
MUTED = "#5A6672"  # subline
ACCENT = "#ED7100"  # AWS orange: series bar and part badge
CANVAS = "#FFFFFF"

FONT_DIR = Path("/System/Library/Fonts")
FONT_BOLD = FONT_DIR / "ヒラギノ角ゴシック W7.ttc"
FONT_MED = FONT_DIR / "ヒラギノ角ゴシック W6.ttc"
FONT_REG = FONT_DIR / "ヒラギノ角ゴシック W3.ttc"

SERIES = {
    "ja": "FSx for ONTAP S3 Access Points ファイルポータル",
    "en": "FSx for ONTAP S3 Access Points — File Portal",
}
FOOTER = "github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns"

PAD = 56
TEXT_W = 620  # left text column width
FIG_X = PAD + TEXT_W + 40  # figure column start
# Sized so the longest authored line stays inside TEXT_W (measured: 596px for
# Japanese at 36px, 592px for English at 34px). Raising these forces a wrap,
# which orphans a trailing character or word.
HEAD_SIZE = {"ja": 36, "en": 34}
HEAD_LEADING = {"ja": 54, "en": 50}


@dataclass(frozen=True)
class Card:
    slug: str
    part: str
    headline: str  # must also appear verbatim in the article lead text
    subline: str
    figure: str
    lang: str = "ja"

    @property
    def headline_text(self) -> str:
        """The headline as a single sentence, for the lead-text cross-check.

        Japanese lines join with no separator; English needs the word space that
        the authored line break stood in for.
        """
        joiner = "" if self.lang == "ja" else " "
        return joiner.join(self.headline.split("\n"))


# `headline` carries explicit newlines: automatic wrapping of mixed
# Japanese/Latin text breaks in awkward places (measured: "AI か / ら使う"), and
# since the copy is authored here the break points are decided here too.
CARDS = [
    Card(
        slug="file-portal-part1",
        part="前編",
        headline="既存マウントを止めずに、\nNAS をブラウザと AI から使う",
        subline="Amplify Gen2 と Nextcloud の使い分け",
        figure="architecture-overview@2x.png",
    ),
    Card(
        slug="file-portal-part2",
        part="中編",
        headline="検知から封じ込めまでを\n画面で回す",
        subline="ARP/AI・SnapLock・監査ログ",
        # The incident-lifecycle figure is 3.2:1 and renders too small in the
        # right-hand column; the admin-operation path is portrait, fills the
        # column, and is the route containment is actually driven through.
        figure="part2-admin-operations@2x.png",
    ),
    Card(
        slug="file-portal-part3",
        part="後編",
        headline="AI エージェントに NAS を触らせ、\n人が承認する",
        subline="Amazon Bedrock AgentCore と MCP",
        figure="part3-ai-agent-overview@2x.png",
    ),
    Card(
        slug="file-portal-part1-en",
        part="Part 1 of 3",
        headline="Reach the NAS from a browser\nand from AI, without stopping\nexisting mounts",
        subline="Choosing between Amplify Gen2 and Nextcloud",
        figure="architecture-overview-en@2x.png",
        lang="en",
    ),
    Card(
        slug="file-portal-part2-en",
        part="Part 2 of 3",
        headline="Run detection through\ncontainment from the screen",
        subline="ARP/AI, SnapLock, audit logs",
        figure="part2-admin-operations-en@2x.png",
        lang="en",
    ),
    Card(
        slug="file-portal-part3-en",
        part="Part 3 of 3",
        headline="Let an AI agent work the NAS,\nwith a human approving",
        subline="Amazon Bedrock AgentCore and MCP",
        figure="part3-ai-agent-overview-en@2x.png",
        lang="en",
    ),
]


def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    if not path.is_file():
        raise FileNotFoundError(f"font not found: {path}")
    return ImageFont.truetype(str(path), size)


def text_width(draw: ImageDraw.ImageDraw, s: str, f: ImageFont.FreeTypeFont) -> int:
    return int(draw.textbbox((0, 0), s, font=f)[2])


def wrap(draw: ImageDraw.ImageDraw, s: str, f: ImageFont.FreeTypeFont, limit: int) -> list[str]:
    """Wrap without relying on spaces, since Japanese has none.

    Breaking before a small set of characters that must not start a line keeps
    the result readable (kinsoku shori, simplified).
    """
    forbidden_start = "、。）」』】・ー"
    lines: list[str] = []
    current = ""
    for ch in s:
        candidate = current + ch
        if text_width(draw, candidate, f) <= limit or not current:
            current = candidate
            continue
        if ch in forbidden_start:
            current = candidate  # let it overhang slightly rather than orphan it
            continue
        lines.append(current)
        current = ch
    if current:
        lines.append(current)
    return lines


def build(card: Card) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), CANVAS)
    draw = ImageDraw.Draw(img)

    f_series = font(FONT_MED, 24)
    f_head = font(FONT_BOLD, HEAD_SIZE[card.lang])
    f_sub = font(FONT_REG, 26)
    f_badge = font(FONT_BOLD, 24)
    f_foot = font(FONT_REG, 18)

    # --- series label with an accent bar ---
    y = PAD
    draw.rectangle([PAD, y + 4, PAD + 6, y + 28], fill=ACCENT)
    draw.text((PAD + 18, y), SERIES[card.lang], font=f_series, fill=MUTED)

    # --- part badge, right-aligned on the same baseline ---
    badge = f"{card.part}・全 3 回" if card.lang == "ja" else card.part
    bw = text_width(draw, badge, f_badge)
    bx = WIDTH - PAD - bw - 24
    draw.rounded_rectangle([bx - 14, y - 2, bx + bw + 14, y + 32], radius=16, fill=ACCENT)
    draw.text((bx, y + 2), badge, font=f_badge, fill=CANVAS)

    # --- headline (the sentence mirrored in the article lead) ---
    # Each authored line must fit on one row; an automatic wrap here would orphan
    # a trailing character, so it is treated as a copy error rather than fixed up.
    y = 168
    for authored in card.headline.split("\n"):
        measured = text_width(draw, authored, f_head)
        if measured > TEXT_W:
            raise ValueError(
                f"{card.slug}: headline line is {measured}px, over the {TEXT_W}px column: "
                f"{authored!r}. Shorten the copy or lower HEAD_SIZE."
            )
        draw.text((PAD, y), authored, font=f_head, fill=INK)
        y += HEAD_LEADING[card.lang]

    # --- subline ---
    y += 14
    for line in wrap(draw, card.subline, f_sub, TEXT_W):
        draw.text((PAD, y), line, font=f_sub, fill=MUTED)
        y += 38

    # --- figure, fitted into the right column ---
    fig_path = FIG_DIR / card.figure
    if not fig_path.is_file():
        raise FileNotFoundError(f"figure not found: {fig_path}")
    box_w = WIDTH - FIG_X - PAD
    box_h = HEIGHT - 150 - 110
    with Image.open(fig_path) as fig:
        fig = fig.convert("RGB")
        fig.thumbnail((box_w, box_h), Image.LANCZOS)
        fx = FIG_X + (box_w - fig.width) // 2
        fy = 150 + (box_h - fig.height) // 2
        img.paste(fig, (fx, fy))

    # --- footer rule and repository line ---
    draw.line([PAD, HEIGHT - 76, WIDTH - PAD, HEIGHT - 76], fill="#D5DBE0", width=2)
    draw.text((PAD, HEIGHT - 58), FOOTER, font=f_foot, fill=MUTED)

    return img


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="report without writing")
    args = ap.parse_args()

    if not args.check:
        OUT_DIR.mkdir(parents=True, exist_ok=True)

    stale = 0
    for card in CARDS:
        img = build(card)
        dest = OUT_DIR / f"{card.slug}-card.png"
        if args.check:
            missing = not dest.is_file()
            if missing:
                stale += 1
            print(f"  {dest.name}: {'MISSING' if missing else 'present'} ({img.width}x{img.height})")
            continue
        img.save(dest, optimize=True)
        size_kb = dest.stat().st_size / 1024
        print(f"  {dest.name}: {img.width}x{img.height}  {size_kb:.0f} KB")
        print(f"      headline (must appear in article lead): {card.headline_text}")

    return 1 if stale else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
