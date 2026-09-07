#!/usr/bin/env python3
"""Keep the "read before going to production" section in every pattern README.

## Why this is a script and not 376 hand edits

`docs/i18n-manifest.toml` declares `solutions/*/*/README.md` as an eight-locale group,
and `check_i18n_parity.py` compares heading structure across those locales against a
ratchet. So this section cannot be added to the Japanese README alone — every edit to it
is an edit to eight files, forever. Hand-editing that once is tedious; hand-editing it
the second time is where a locale gets missed. The repository already works this way for
the deploy note (`ensure_deploy_note_all_langs.py`, `sync_deploy_section_all_langs.py`).

Idempotent. The section is delimited by HTML comment markers, so a re-run replaces the
block rather than appending a second one, and a local edit inside the markers is
overwritten on purpose — the mapping below is the source.

## Where the mapping comes from, and where it does not

The Adoption Playbook owns the division of labour: it indexes the industries and names
which module to read first. That table is at
`docs/ja/reference/industry-resource-map.md`, section "業種から入ったときの読む順序",
and `PLAYBOOK_ROWS` below is a transcription of its module pairs — not a second opinion
about them. **Constraints are deliberately not copied here.** A link to a module hub is
the whole contribution; the moment a constraint is restated on this side, there are two
copies and the one that stops being updated outlives the one that was corrected.

Fifteen solutions are named in that table directly. The rest are matched to the nearest
row by workload shape, which the table itself instructs ("読むモジュールを決めているのは
業種ではなく、ワークロードの形です ... 自分の業種が表に無くても、形が近い行を読む価値が
あります"). `INFERRED` records which assignments are that inference rather than the
Playbook's own, so a disagreement can be settled by moving one line.

## Why module hubs rather than notes, and what still gates them

Notes get renamed. A module hub does not. `check_repo_name_redirects.py` covers the
*repository name* in these links; it deliberately drops everything after `owner/repo`, so
the 24 hub paths themselves need `--verify-hubs`, which the weekly workflow runs. Without
it the generator would be claiming coverage the name check does not provide.

## Usage

    python3 scripts/sync_playbook_reading_section.py                # write
    python3 scripts/sync_playbook_reading_section.py --check         # exit 1 if out of date
    python3 scripts/sync_playbook_reading_section.py --dry-run       # show what would change
    python3 scripts/sync_playbook_reading_section.py --verify-hubs   # resolve the hub URLs
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_repo_name_redirects import fetch  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

PLAYBOOK = "https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook"

BEGIN = "<!-- playbook-reading:start -->"
END = "<!-- playbook-reading:end -->"

# The Playbook's `domains/` and `playbooks/` trees exist in ja and en only; the other six
# locales carry just README, navigation and evidence-policy. So a non-Japanese README
# points at the English hub. Verified 2026-09-07: all 24 ja/en hub URLs return 200, and --verify-hubs re-checks them.
HUB_LOCALE = {"md": "ja"}  # everything else falls back to "en"

# Suffix of each README variant, in the order the group is declared in the manifest.
LOCALES = ("md", "en.md", "ko.md", "zh-CN.md", "zh-TW.md", "fr.md", "de.md", "es.md")

# Module labels, taken from the H1 of each module's own README on the Playbook side
# rather than invented here, so the link text matches the page it opens.
MODULE_LABELS: dict[str, dict[str, str]] = {
    "domains/performance": {
        "md": "性能",
        "en.md": "Performance",
        "ko.md": "성능",
        "zh-CN.md": "性能",
        "zh-TW.md": "效能",
        "fr.md": "Performance",
        "de.md": "Performance",
        "es.md": "Rendimiento",
    },
    "domains/data-utilization": {
        "md": "データ活用",
        "en.md": "Data Utilization",
        "ko.md": "데이터 활용",
        "zh-CN.md": "数据利用",
        "zh-TW.md": "資料活用",
        "fr.md": "Exploitation des données",
        "de.md": "Datennutzung",
        "es.md": "Aprovechamiento de datos",
    },
    "domains/block-storage": {
        "md": "ブロックストレージ",
        "en.md": "Block Storage",
        "ko.md": "블록 스토리지",
        "zh-CN.md": "块存储",
        "zh-TW.md": "區塊儲存",
        "fr.md": "Stockage bloc",
        "de.md": "Blockspeicher",
        "es.md": "Almacenamiento en bloque",
    },
    "domains/data-protection": {
        "md": "データ保護",
        "en.md": "Data Protection",
        "ko.md": "데이터 보호",
        "zh-CN.md": "数据保护",
        "zh-TW.md": "資料保護",
        "fr.md": "Protection des données",
        "de.md": "Datensicherung",
        "es.md": "Protección de datos",
    },
    "domains/multiprotocol-identity": {
        "md": "マルチプロトコル・ID",
        "en.md": "Multiprotocol & Identity",
        "ko.md": "멀티프로토콜 및 ID",
        "zh-CN.md": "多协议与身份",
        "zh-TW.md": "多協定與身分",
        "fr.md": "Multiprotocole et identité",
        "de.md": "Multiprotokoll und Identität",
        "es.md": "Multiprotocolo e identidad",
    },
    "domains/security-governance": {
        "md": "セキュリティ・ガバナンス",
        "en.md": "Security & Governance",
        "ko.md": "보안 및 거버넌스",
        "zh-CN.md": "安全与治理",
        "zh-TW.md": "安全與治理",
        "fr.md": "Sécurité et gouvernance",
        "de.md": "Sicherheit und Governance",
        "es.md": "Seguridad y gobernanza",
    },
    "domains/cost": {
        "md": "コスト",
        "en.md": "Cost",
        "ko.md": "비용",
        "zh-CN.md": "成本",
        "zh-TW.md": "成本",
        "fr.md": "Coût",
        "de.md": "Kosten",
        "es.md": "Coste",
    },
    "playbooks/01-assess": {
        "md": "評価",
        "en.md": "Assess",
        "ko.md": "평가",
        "zh-CN.md": "评估",
        "zh-TW.md": "評估",
        "fr.md": "Évaluer",
        "de.md": "Bewerten",
        "es.md": "Evaluar",
    },
    "playbooks/02-design": {
        "md": "設計",
        "en.md": "Design",
        "ko.md": "설계",
        "zh-CN.md": "设计",
        "zh-TW.md": "設計",
        "fr.md": "Concevoir",
        "de.md": "Entwerfen",
        "es.md": "Diseñar",
    },
    "playbooks/03-migrate": {
        "md": "移行",
        "en.md": "Migrate",
        "ko.md": "마이그레이션",
        "zh-CN.md": "迁移",
        "zh-TW.md": "遷移",
        "fr.md": "Migrer",
        "de.md": "Migrieren",
        "es.md": "Migrar",
    },
    "playbooks/04-build": {
        "md": "構築",
        "en.md": "Build",
        "ko.md": "구축",
        "zh-CN.md": "构建",
        "zh-TW.md": "建置",
        "fr.md": "Construire",
        "de.md": "Aufbauen",
        "es.md": "Construir",
    },
    "playbooks/05-operate": {
        "md": "運用",
        "en.md": "Operate",
        "ko.md": "운영",
        "zh-CN.md": "运维",
        "zh-TW.md": "運維",
        "fr.md": "Exploiter",
        "de.md": "Betreiben",
        "es.md": "Operar",
    },
}

# Every pattern reads the Build module as well: the items that cannot be changed after
# the fact are not industry-specific, which is what the Playbook's table says under
# "どの業種でも共通して先に通すもの".
UNIVERSAL = "playbooks/04-build"

# Transcribed from the Playbook's reading-order table: row label -> (first, second).
PLAYBOOK_ROWS: dict[str, tuple[str, str]] = {
    "energy": ("playbooks/03-migrate", "playbooks/02-design"),
    "semiconductor-eda": ("domains/performance", "domains/data-utilization"),
    "automotive-adas": ("domains/data-utilization", "domains/performance"),
    "manufacturing": ("playbooks/01-assess", "domains/data-utilization"),
    "financial": ("domains/block-storage", "domains/data-protection"),
    "insurance": ("playbooks/03-migrate", "domains/multiprotocol-identity"),
    "healthcare": ("domains/data-protection", "domains/security-governance"),
    "telecom": ("playbooks/05-operate", "domains/performance"),
    "defense-public": ("domains/security-governance", "domains/data-protection"),
    "media": ("playbooks/02-design", "domains/performance"),
    "education": ("domains/multiprotocol-identity", "domains/cost"),
    "logistics": ("playbooks/03-migrate", "playbooks/05-operate"),
    "retail": ("domains/data-utilization", "domains/cost"),
    "ai-ml": ("domains/data-utilization", "domains/security-governance"),
    "saas-multitenant": ("domains/block-storage", "domains/cost"),
    "cyber-resilience": ("domains/data-protection", "domains/security-governance"),
    "observability": ("domains/performance", "domains/security-governance"),
    "lakehouse": ("domains/data-utilization", "domains/performance"),
}

# Solution directory (relative to solutions/) -> row in PLAYBOOK_ROWS.
ASSIGNMENT: dict[str, str] = {
    # Named in the Playbook's own industry index.
    "industry/energy-seismic": "energy",
    "industry/semiconductor-eda": "semiconductor-eda",
    "industry/autonomous-driving": "automotive-adas",
    "industry/manufacturing-analytics": "manufacturing",
    "industry/financial-idp": "financial",
    "industry/insurance-claims": "insurance",
    "industry/healthcare-dicom": "healthcare",
    "industry/telecom-network-analytics": "telecom",
    "industry/defense-satellite": "defense-public",
    "industry/government-archives": "defense-public",
    "industry/media-vfx": "media",
    "industry/education-research": "education",
    "industry/logistics-ocr": "logistics",
    "industry/retail-catalog": "retail",
    "amplify-portal": "ai-ml",
    # Matched to the nearest row by workload shape.
    "industry/genomics-pipeline": "semiconductor-eda",
    "industry/smart-city-geospatial": "automotive-adas",
    "industry/agri-food-traceability": "manufacturing",
    "industry/legal-compliance": "defense-public",
    "industry/hr-document-screening": "defense-public",
    "industry/chemical-sds-management": "defense-public",
    "industry/sustainability-esg-reporting": "defense-public",
    "industry/adtech-creative-management": "media",
    "industry/construction-bim": "media",
    "industry/utilities-asset-inspection": "telecom",
    "industry/transportation-maintenance": "telecom",
    "industry/real-estate-portfolio": "retail",
    "industry/travel-document-processing": "retail",
    "industry/nonprofit-grant-management": "retail",
    "flexcache/automotive-cae": "semiconductor-eda",
    "flexcache/gaming-build-pipeline": "semiconductor-eda",
    "flexcache/life-sciences-research": "semiconductor-eda",
    "flexcache/dynamic-render-workflow": "media",
    "flexcache/anycast-dr": "cyber-resilience",
    "flexcache/snapmirror-cross-region-dr": "cyber-resilience",
    "flexcache/cross-region-s3ap": "lakehouse",
    "flexcache/same-region-s3ap": "lakehouse",
    "flexcache/devops-cicd": "saas-multitenant",
    "flexcache/rag-enterprise-files": "ai-ml",
    "genai/kb-selfservice-curation": "ai-ml",
    "genai/quick-agentic-workspace": "ai-ml",
    "edge/media-ivs-vod-publishing": "media",
    "edge/content-delivery": "retail",
    "event-driven/fpolicy": "observability",
    "event-driven/prototype": "observability",
    "ha/lifekeeper-monitoring": "telecom",
    "sap/erp-adjacent": "financial",
}

# Solution directories deliberately without a section, and why. Recorded as data rather
# than left absent, because `ASSIGNMENT` is the input to the writer: a directory missing
# from it is indistinguishable from one nobody got round to, and `--check` walks
# `ASSIGNMENT` so it cannot report the difference. `check_coverage()` reads this.
EXCLUDED: dict[str, str] = {
    "nextcloud-test": "S3 AP verification environment, not a pattern anyone deploys.",
    "storage-browser-demo": "Storage Browser demo, not a pattern anyone deploys.",
}

# Assignments that are this repository's inference rather than the Playbook's own table.
# Kept as data so the distinction survives; the Playbook is still the source for the
# module pairs themselves.
INFERRED = frozenset(ASSIGNMENT) - {
    "industry/energy-seismic",
    "industry/semiconductor-eda",
    "industry/autonomous-driving",
    "industry/manufacturing-analytics",
    "industry/financial-idp",
    "industry/insurance-claims",
    "industry/healthcare-dicom",
    "industry/telecom-network-analytics",
    "industry/defense-satellite",
    "industry/government-archives",
    "industry/media-vfx",
    "industry/education-research",
    "industry/logistics-ocr",
    "industry/retail-catalog",
    "amplify-portal",
}

HEADING = {
    "md": "本番に出す前に読むもの",
    "en.md": "Read before going to production",
    "ko.md": "프로덕션 적용 전에 읽을 것",
    "zh-CN.md": "上生产前需要阅读的内容",
    "zh-TW.md": "上線前需要閱讀的內容",
    "fr.md": "À lire avant la mise en production",
    "de.md": "Vor dem Produktivbetrieb lesen",
    "es.md": "Lectura previa al paso a producción",
}

LEAD = {
    "md": (
        "デプロイしたあとに当たる制約を、どう設計判断に翻訳するかは "
        f"[FSx for ONTAP Adoption Playbook]({PLAYBOOK}) 側にあります。"
        "同じ内容を 2 か所に置くと、更新が止まった側が更新された側より長く残るためです。"
    ),
    "en.md": (
        "How the constraints that surface after deploying translate into design decisions is covered in the "
        f"[FSx for ONTAP Adoption Playbook]({PLAYBOOK}). The same content in "
        "two places means the copy that stops being updated outlives the one that was "
        "corrected."
    ),
    "ko.md": (
        "배포 후에 부딪히는 제약을 설계 판단으로 어떻게 옮기는지는 "
        f"[FSx for ONTAP Adoption Playbook]({PLAYBOOK})에 정리되어 있습니다. "
        "같은 내용을 두 곳에 두면 갱신이 멈춘 쪽이 더 오래 남기 때문입니다."
    ),
    "zh-CN.md": (
        "部署后才会遇到的约束如何转化为设计决策，记录在 "
        f"[FSx for ONTAP Adoption Playbook]({PLAYBOOK})。"
        "同一内容放在两处时，停止更新的那份会比已修正的那份存留更久。"
    ),
    "zh-TW.md": (
        "部署後才會遇到的限制如何轉化為設計決策，記錄在 "
        f"[FSx for ONTAP Adoption Playbook]({PLAYBOOK})。"
        "同一內容放在兩處時，停止更新的那份會比已修正的那份留存更久。"
    ),
    "fr.md": (
        "La façon de traduire en décisions de conception les contraintes qui apparaissent après le déploiement est documentée dans le "
        f"[FSx for ONTAP Adoption Playbook]({PLAYBOOK}). Un même contenu présent "
        "à deux endroits laisse survivre la copie qui a cessé d'être mise à jour."
    ),
    "de.md": (
        "Wie sich die nach der Bereitstellung auftretenden Einschränkungen in Entwurfsentscheidungen übersetzen, steht im "
        f"[FSx for ONTAP Adoption Playbook]({PLAYBOOK}) beschrieben. "
        "Liegt derselbe Inhalt an zwei Stellen, überlebt die nicht mehr gepflegte Kopie "
        "die korrigierte."
    ),
    "es.md": (
        "Cómo se traducen en decisiones de diseño las restricciones que aparecen después del despliegue está documentado en el "
        f"[FSx for ONTAP Adoption Playbook]({PLAYBOOK}). El mismo contenido en "
        "dos lugares hace que la copia que deja de actualizarse sobreviva a la corregida."
    ),
}

ROLE_FIRST = {
    "md": "最初に読む",
    "en.md": "read first",
    "ko.md": "먼저 읽기",
    "zh-CN.md": "先读",
    "zh-TW.md": "先讀",
    "fr.md": "à lire en premier",
    "de.md": "zuerst lesen",
    "es.md": "leer primero",
}
ROLE_SECOND = {
    "md": "次に読む",
    "en.md": "read next",
    "ko.md": "다음에 읽기",
    "zh-CN.md": "接着读",
    "zh-TW.md": "接著讀",
    "fr.md": "à lire ensuite",
    "de.md": "danach lesen",
    "es.md": "leer a continuación",
}
# Describes when to read it, not what it says. An earlier draft read "the items that
# cannot be changed afterwards", which `check_evidence_claims.py` correctly flagged: that
# is an assertion about product behaviour, and asserting it here is the first half of the
# duplication #88 exists to prevent. The claim belongs to the Playbook page behind the
# link; this side supplies reading order.
ROLE_UNIVERSAL = {
    "md": "本番前に通す（全パターン共通）",
    "en.md": "run through before production (every pattern)",
    "ko.md": "프로덕션 전에 확인 (모든 패턴 공통)",
    "zh-CN.md": "上生产前通读（所有模式通用）",
    "zh-TW.md": "上線前通讀（所有模式通用）",
    "fr.md": "à parcourir avant la production (tous les patterns)",
    "de.md": "vor dem Produktivbetrieb durchgehen (alle Patterns)",
    "es.md": "revisar antes de producción (todos los patrones)",
}


def render(locale: str, row: str) -> str:
    """Build the section body for one locale.

    Args:
        locale: README suffix, e.g. `md` or `zh-CN.md`.
        row: Key into `PLAYBOOK_ROWS`.

    Returns:
        The section text, markers included, ending in a newline.
    """
    hub_lang = HUB_LOCALE.get(locale, "en")
    first, second = PLAYBOOK_ROWS[row]

    def item(module: str, role: dict[str, str]) -> str:
        label = MODULE_LABELS[module][locale]
        return f"- [{label}]({PLAYBOOK}/tree/main/docs/{hub_lang}/{module}) — {role[locale]}"

    lines = [
        BEGIN,
        f"## {HEADING[locale]}",
        "",
        LEAD[locale],
        "",
        item(first, ROLE_FIRST),
        item(second, ROLE_SECOND),
        item(UNIVERSAL, ROLE_UNIVERSAL),
        END,
    ]
    return "\n".join(lines) + "\n"


def readme_for(solution: str, locale: str, root: Path = ROOT) -> Path:
    """Resolve a README path, accounting for the portal's inverted naming.

    `solutions/amplify-portal` keeps English in `README.md` and Japanese in
    `README.ja.md`, the opposite of every other pattern directory, so the locale-to-file
    mapping is flipped for it rather than assuming Japanese is always `README.md`.

    Args:
        solution: Path under `solutions/`, e.g. `industry/media-vfx`.
        locale: README suffix, e.g. `md` or `zh-CN.md`.
        root: Repository root, overridable for tests.

    Returns:
        The path the section belongs in. Not guaranteed to exist.
    """
    base = root / "solutions" / solution
    if solution == "amplify-portal":
        if locale == "md":
            return base / "README.ja.md"
        if locale == "en.md":
            return base / "README.md"
    if locale == "md":
        return base / "README.md"
    return base / f"README.{locale}"


class MarkerError(RuntimeError):
    """A file's markers are in a state this cannot safely rewrite."""


def apply(text: str, section: str) -> str:
    """Insert or replace the marked section, leaving the rest of the file alone.

    Args:
        text: Current file contents.
        section: Output of `render()`, markers included.

    Returns:
        The updated contents. Applying the same section twice is a no-op.

    Raises:
        MarkerError: One marker is present without the other. Rewriting then would
            delete content, so it refuses instead.
    """
    begins = text.count(BEGIN)
    ends = text.count(END)

    if begins == 0 and ends == 0:
        return f"{text.rstrip(chr(10))}\n\n---\n\n{section}"

    # An orphaned marker used to fall through to the append path, which produced
    # BEGIN...BEGIN...END. The run after that satisfied the replace condition, took
    # everything between the FIRST begin and the FIRST end as the block, and deleted it --
    # so a Governance Note survived one run and was gone after the next. The damage landed
    # on the run `--check` tells you to make, which is the worst possible moment for it.
    if begins != ends:
        raise MarkerError(
            f"found {begins} '{BEGIN}' and {ends} '{END}'. Repair the markers by hand: "
            "rewriting a half-open block would delete everything after it."
        )

    head, _, rest = text.partition(BEGIN)
    _, _, tail = rest.partition(END)

    # More than one pair is not corruption, but it is a fixed point: rewriting the first
    # and leaving the rest means `--check` calls a file with two sections up to date.
    # sync_lang_switcher.py drops duplicates for the same reason.
    if begins > 1:
        while BEGIN in tail and END in tail:
            before, _, after = tail.partition(BEGIN)
            _, _, tail = after.partition(END)
            head_tail = before.rstrip()
            tail = (head_tail + tail) if head_tail else tail

    return head + section.rstrip("\n") + tail


def check_coverage(root: Path = ROOT) -> list[str]:
    """Report solution directories on disk that the mapping says nothing about.

    `main()` iterates `ASSIGNMENT`, so on its own it can only report a README the mapping
    names and disk lacks. This is the other direction: a pattern added to the tree without
    an `ASSIGNMENT` entry silently gets no section, and every gate stays green.

    Args:
        root: Repository root, overridable for tests.

    Returns:
        One message per uncovered directory. Empty when every directory is either mapped
        or listed in `EXCLUDED`.
    """
    problems: list[str] = []
    solutions = root / "solutions"
    for readme in sorted(solutions.glob("*/*/README.md")) + sorted(solutions.glob("*/README.md")):
        rel = readme.parent.relative_to(solutions).as_posix()
        if rel in ASSIGNMENT or rel in EXCLUDED or rel == ".":
            continue
        problems.append(
            f"solutions/{rel} has a README and no ASSIGNMENT entry. Add one, or record the "
            f"exclusion in EXCLUDED with the reason."
        )
    return problems


def hub_urls() -> list[str]:
    """Every distinct hub URL the generator can emit, for both languages."""
    modules = {UNIVERSAL}
    for first, second in PLAYBOOK_ROWS.values():
        modules.update((first, second))
    return [f"{PLAYBOOK}/tree/main/docs/{lang}/{m}" for lang in ("ja", "en") for m in sorted(modules)]


def verify_hubs() -> tuple[list[str], list[str]]:
    """Resolve every hub URL the generated sections point at.

    Returns:
        A pair of `(broken, unreachable)`. `broken` is a 404 -- the module was renamed or
        removed, and 376 READMEs now point at nothing. `unreachable` reached no verdict.
    """
    broken: list[str] = []
    unreachable: list[str] = []
    for url in hub_urls():
        if not url.startswith("https://github.com/"):
            raise ValueError(f"refusing a non-GitHub https URL: {url}")
        request = urllib.request.Request(url, headers={"User-Agent": "playbook-hub-check"})
        # Retry lives in the sibling check so the backoff policy has one definition. GitHub
        # answers a burst of serial requests with 504, and these 24 run right after that
        # check's 29.
        _final, status, error = fetch(request)
        if status == 404:
            broken.append(f"{url}: 404 -- the module hub is gone; 376 READMEs link to it")
        elif error is not None:
            unreachable.append(f"{url}: {error}")
    return broken, unreachable


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 if any file is out of date")
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    parser.add_argument("--verify-hubs", action="store_true", help="resolve the hub URLs (needs the network)")
    args = parser.parse_args()

    if args.verify_hubs:
        broken, unreachable = verify_hubs()
        for label, rows in (("broken", broken), ("not checked", unreachable)):
            for row_text in rows:
                print(f"  {label}: {row_text}", file=sys.stderr)
        if broken:
            print(f"{len(broken)} hub URL(s) 404. 376 READMEs point at them.", file=sys.stderr)
            return 1
        if unreachable:
            return 2
        print(f"playbook-hubs: {len(hub_urls())} hub URL(s) resolve")
        return 0

    coverage = check_coverage()
    if coverage:
        print(f"{len(coverage)} solution directory(ies) outside the mapping:", file=sys.stderr)
        for line in coverage:
            print(f"  {line}", file=sys.stderr)
        return 1

    written: list[str] = []
    stale: list[str] = []
    missing: list[str] = []
    damaged: list[str] = []

    # Every path is resolved and every file read before anything is written, so a mapping
    # typo or a damaged marker pair fails before the first of several hundred writes rather
    # than after some of them.
    targets: list[tuple[Path, str, str]] = []
    for solution, row in sorted(ASSIGNMENT.items()):
        for locale in LOCALES:
            path = readme_for(solution, locale)
            if not path.exists():
                missing.append(path.relative_to(ROOT).as_posix())
                continue
            current = path.read_text(encoding="utf-8")
            try:
                updated = apply(current, render(locale, row))
            except MarkerError as exc:
                damaged.append(f"{path.relative_to(ROOT).as_posix()}: {exc}")
                continue
            targets.append((path, current, updated))

    if missing or damaged:
        for label, rows in (("do not exist", missing), ("have damaged markers", damaged)):
            if not rows:
                continue
            print(f"{len(rows)} README(s) {label}:", file=sys.stderr)
            for row_text in rows:
                print(f"  {row_text}", file=sys.stderr)
        return 1

    for path, current, updated in targets:
        if updated == current:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if args.check or args.dry_run:
            stale.append(rel)
            continue
        path.write_text(updated, encoding="utf-8")
        written.append(rel)

    if args.check:
        if stale:
            print(f"{len(stale)} README(s) out of date. Run without --check.", file=sys.stderr)
            for rel in stale[:10]:
                print(f"  {rel}", file=sys.stderr)
            return 1
        print(f"playbook-reading: {len(ASSIGNMENT) * len(LOCALES)} README(s) up to date")
        return 0

    if args.dry_run:
        print(f"would change {len(stale)} file(s)")
        return 0

    print(
        f"playbook-reading: {len(written)} file(s) written across "
        f"{len(ASSIGNMENT)} solutions ({len(INFERRED)} by inferred row)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
