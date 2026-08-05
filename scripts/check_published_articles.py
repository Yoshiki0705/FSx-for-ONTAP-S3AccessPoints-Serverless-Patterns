#!/usr/bin/env python3
"""Apply the portal's stale-claim rules to the articles as readers actually see them.

`check_portal_drift.py` covers files in the repository. Two published Part 2 posts
still told readers that block expiry and multi-SVM fan-out were things they had to
build themselves, for a month after both shipped, and no check could have noticed:
the article text lives on Hatena and dev.to, not in git, and the rule patterns had
only ever been written against the phrasings used in `docs/`.

This script closes the first half of that gap. The rule table is imported rather
than copied, so a rule added for the repository automatically applies here too.

    python3 scripts/check_published_articles.py                 # all articles
    python3 scripts/check_published_articles.py --require-fetch # fetch must work
    python3 scripts/check_published_articles.py --url <url>     # one page, ad hoc

Not part of the pull-request gate, on purpose. A required check that reaches out
to two third-party sites fails for reasons that have nothing to do with the change
under review, and a gate that cries wolf is one people learn to force through. It
runs on a schedule and on demand instead, where a transient failure costs nobody
anything and a persistent one still gets seen.

Exit codes: 0 clean (or fetch skipped), 1 stale claims found, 2 fetch failed
under --require-fetch.

The `drift-exempt` markers understood by check_portal_drift.py are deliberately
not honoured here. A file may quote a false claim to correct it; a published
article asserting one to its readers is a finding regardless of intent.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_portal_drift import active_contradictions, scan_text  # noqa: E402

USER_AGENT = "fsxn-s3ap-serverless-patterns-doc-check (+https://github.com/Yoshiki0705)"
TIMEOUT_SECONDS = 20
ATTEMPTS = 3

# Every published article in the file-portal series, in both languages. The set is
# listed explicitly rather than discovered: a feed or sitemap would silently stop
# covering a post that gets re-slugged, and silence is the failure mode this whole
# script exists to remove.
ARTICLES = [
    {
        "label": "Part 1 (JA, Hatena)",
        "kind": "hatena",
        "url": "https://hakobiya.hatenablog.com/entry/fsxn-file-portal-1-browser-access",
    },
    {
        "label": "Part 2 (JA, Hatena)",
        "kind": "hatena",
        "url": "https://hakobiya.hatenablog.com/entry/fsxn-file-portal-2-ransomware-worm",
    },
    {
        "label": "Part 3 (JA, Hatena)",
        "kind": "hatena",
        "url": "https://hakobiya.hatenablog.com/entry/fsxn-file-portal-3-ai-agent-mcp",
    },
    {
        "label": "Part 1 (EN, dev.to)",
        "kind": "devto",
        "url": (
            "https://dev.to/aws-builders/adding-a-file-portal-to-fsx-for-ontap"
            "-s3-access-points-choosing-between-amplify-gen2-and-887"
        ),
    },
    {
        "label": "Part 2 (EN, dev.to)",
        "kind": "devto",
        "url": (
            "https://dev.to/aws-builders/embedding-storage-operations-into-a-file-portal"
            "-from-arpai-incident-response-to-regulatory-1oih"
        ),
    },
    {
        "label": "Part 3 (EN, dev.to)",
        "kind": "devto",
        "url": (
            "https://dev.to/aws-builders/embedding-ai-agents-into-a-file-portal"
            "-from-agentcore-mcp-to-multi-agent-teams-part-3-19m1"
        ),
    },
]

# Tags after which a line break belongs, so the text keeps the shape scan_text
# needs. dev.to renders a single newline in the markdown as <br>, which is how a
# claim ends up split across two lines with the whole of it on neither.
BREAK_AFTER = {"br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}
BLANK_AFTER = {"p", "div", "table", "blockquote", "pre", "ul", "ol"}
SKIP_CONTENT = {"script", "style", "noscript", "svg"}


class _TextExtractor(HTMLParser):
    """Collect readable text, optionally only from inside one container.

    `container_class` selects the article body on a full page: a blog page also
    carries the sidebar, related posts and comments, and a false claim in someone
    else's comment is not ours to fix.
    """

    def __init__(self, container_class: str | None = None) -> None:
        super().__init__(convert_charrefs=True)
        self.container_class = container_class
        self.capturing = container_class is None
        self._depth = 0
        self._container_tag: str | None = None
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIP_CONTENT:
            self._skip_depth += 1
            return
        if not self.capturing and self.container_class is not None:
            classes = dict(attrs).get("class") or ""
            if self.container_class in classes.split():
                self.capturing = True
                self._container_tag = tag
                self._depth = 1
            return
        if self.capturing and tag == self._container_tag:
            self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_CONTENT:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if not self.capturing:
            return
        if tag == self._container_tag:
            self._depth -= 1
            if self._depth <= 0:
                self.capturing = False
                return
        if tag in BLANK_AFTER:
            self._parts.append("\n\n")
        elif tag in BREAK_AFTER:
            self._parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.capturing and tag in BREAK_AFTER:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.capturing and not self._skip_depth:
            self._parts.append(data)

    @property
    def text(self) -> str:
        joined = "".join(self._parts)
        # Collapse runs of blank lines but keep single ones: scan_text uses blank
        # lines as paragraph boundaries and single newlines as wrap points, and
        # rejoining the wrap is its job, not the extractor's — it is the half that
        # knows a Japanese line break takes no space.
        joined = re.sub(r"[ \t]+", " ", joined)
        return re.sub(r"\n{3,}", "\n\n", joined).strip()


def _fetch(url: str) -> str:
    last: Exception | None = None
    for attempt in range(1, ATTEMPTS + 1):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
                return response.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as error:
            last = error
            if attempt == ATTEMPTS:
                break
    raise RuntimeError(f"{url}: {last}")


def article_text(url: str, kind: str) -> str:
    """The readable body of one published article."""
    if kind == "devto":
        # The public API returns the rendered body on its own, so the page
        # furniture never has to be filtered back out.
        slug = url.rstrip("/").split("/")
        api = f"https://dev.to/api/articles/{slug[-2]}/{slug[-1]}"
        payload = json.loads(_fetch(api))
        body = payload.get("body_html") or ""
        if not body:
            raise RuntimeError(f"{api}: response carried no body_html")
        parser = _TextExtractor()
    elif kind == "hatena":
        body = _fetch(url)
        parser = _TextExtractor(container_class="entry-content")
    else:
        body = _fetch(url)
        parser = _TextExtractor()
    parser.feed(body)
    text = parser.text
    if not text.strip():
        raise RuntimeError(f"{url}: no article text extracted")
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        help="check a single page instead of the manifest",
    )
    parser.add_argument(
        "--kind",
        choices=["devto", "hatena", "plain"],
        default="plain",
        help="how to extract the body of --url (default: strip all tags)",
    )
    parser.add_argument(
        "--require-fetch",
        action="store_true",
        help="treat a failed fetch as an error rather than skipping it",
    )
    args = parser.parse_args()

    rules = active_contradictions()
    if not rules:
        print("PUBLISHED ARTICLES: no active claim rules; nothing to check")
        return 0

    targets = [{"label": args.url, "kind": args.kind, "url": args.url}] if args.url else ARTICLES

    findings: list[str] = []
    unreachable: list[str] = []
    checked = 0

    for article in targets:
        try:
            text = article_text(article["url"], article["kind"])
        except (RuntimeError, ValueError, json.JSONDecodeError) as error:
            unreachable.append(f"{article['label']}: {error}")
            continue
        checked += 1
        for rule, number, matched in scan_text(text, rules):
            findings.append(
                f"{article['label']} (line {number})\n"
                f"      {rule['why']}\n"
                f"      {matched[:150]}\n"
                f"      {article['url']}"
            )

    for message in unreachable:
        print(f"could not fetch — {message}")

    if findings:
        print(f"\nstale claim in a published article ({len(findings)}):")
        for finding in findings:
            print(f"  {finding}")
        print(f"\nPUBLISHED ARTICLES: {len(findings)} stale claim(s) in {checked} article(s)")
        print("Edit the post in the Hatena or dev.to editor. Patch the fetched body")
        print("rather than re-posting a local draft: dev.to re-hosts inline images, so")
        print("a full overwrite silently swaps every image back to a GitHub hotlink.")
        return 1

    if not checked:
        message = "PUBLISHED ARTICLES: SKIPPED — nothing could be fetched"
        if args.require_fetch:
            print(f"{message} (--require-fetch)")
            return 2
        print(message)
        return 0

    if unreachable and args.require_fetch:
        print(f"\nPUBLISHED ARTICLES: {len(unreachable)} article(s) unreachable (--require-fetch)")
        return 2

    print(f"PUBLISHED ARTICLES: PASS ({checked} article(s), {len(rules)} claim rule(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
