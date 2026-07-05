#!/usr/bin/env python3
"""CI guard: Bedrock on-demand invocation must use inference profiles.

Amazon Nova and newer Claude models cannot be invoked on-demand by the bare
model ID — they require a cross-region inference profile (apac./us./eu. prefix),
and the IAM policy must allow the inference-profile ARN (not only foundation-model).
See docs/bedrock-inference-profiles.md.

This guard flags, per pattern that uses Bedrock text generation:
  (1) a BedrockModelId Default that is a BARE Nova/Claude ID (no geo prefix), and
  (2) a Bedrock IAM statement that references foundation-model but NOT
      inference-profile, or uses a wildcard Resource ('*').

Patterns still pending the fleet-wide rollout are listed in KNOWN_PENDING so the
guard passes today; each remediation batch removes its patterns from that set.
When KNOWN_PENDING is empty the guard fully enforces the rule.

Usage:
    python3 scripts/check_bedrock_inference_profile.py            # CI mode
    python3 scripts/check_bedrock_inference_profile.py --list     # print status, never fail
    python3 scripts/check_bedrock_inference_profile.py --selftest # run built-in assertions
"""

from __future__ import annotations

import glob
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Pattern directories not yet migrated to inference profiles.
# Remove entries as each remediation batch lands; target = empty set.
KNOWN_PENDING: set[str] = {
    # Tier B (body + model + IAM)
    "solutions/industry/insurance-claims",
    "solutions/industry/retail-catalog",
    "solutions/industry/smart-city-geospatial",
    # Tier A (model default + IAM)
    "solutions/flexcache/automotive-cae",
    "solutions/flexcache/gaming-build-pipeline",
    "solutions/flexcache/life-sciences-research",
    "solutions/flexcache/rag-enterprise-files",
    "solutions/ha/lifekeeper-monitoring",
    "solutions/sap/erp-adjacent",
    "solutions/industry/adtech-creative-management",
    "solutions/industry/agri-food-traceability",
    "solutions/industry/chemical-sds-management",
    "solutions/industry/construction-bim",
    "solutions/industry/energy-seismic",
    "solutions/industry/financial-idp",
    "solutions/industry/genomics-pipeline",
    "solutions/industry/hr-document-screening",
    "solutions/industry/legal-compliance",
    "solutions/industry/nonprofit-grant-management",
    "solutions/industry/real-estate-portfolio",
    "solutions/industry/semiconductor-eda",
    "solutions/industry/sustainability-esg-reporting",
    "solutions/industry/telecom-network-analytics",
    "solutions/industry/transportation-maintenance",
    "solutions/industry/travel-document-processing",
    "solutions/industry/utilities-asset-inspection",
}

_GEO_PREFIXES = ("apac.", "us.", "eu.", "us-gov.")
# Bare text-generation model families that need an inference profile on-demand.
_BARE_MODEL_RE = re.compile(r'Default:\s*["\']?(amazon\.nova|anthropic\.claude)[\w.:-]*', re.I)


def _default_values(text: str) -> list[str]:
    """Return BedrockModelId-style Default values that are bare Nova/Claude IDs."""
    bare = []
    for m in re.finditer(r'Default:\s*["\']?([A-Za-z0-9._:-]+)', text):
        val = m.group(1)
        fam = val.split(".", 1)[0]
        if val.startswith(("amazon.nova", "anthropic.claude")) and not val.startswith(_GEO_PREFIXES):
            # amazon.titan-embed-* etc. are fine; only nova/claude text families flagged
            bare.append(val)
        elif fam in {"apac", "us", "eu"}:
            continue
    return bare


def classify_template(text: str) -> set[str]:
    """Return the set of violation codes for one template's text.

    Codes:
      bare-default : model Default is a bare Nova/Claude ID (needs geo prefix)
      iam-missing  : uses bedrock:InvokeModel + foundation-model but no inference-profile
      iam-wildcard : bedrock statement uses Resource '*'
    """
    violations: set[str] = set()
    if _default_values(text):
        violations.add("bare-default")

    if "bedrock:InvokeModel" in text or "bedrock:invoke_model" in text.lower():
        has_profile = "inference-profile" in text
        has_fm = "foundation-model" in text
        has_wildcard = re.search(r"bedrock[\s\S]{0,400}?Resource:\s*['\"]\*['\"]", text) is not None
        if has_wildcard and not has_profile:
            violations.add("iam-wildcard")
        elif has_fm and not has_profile:
            violations.add("iam-missing")
    return violations


def _pattern_dir(template_path: Path) -> str:
    return str(template_path.parent.relative_to(ROOT))


def scan() -> dict[str, set[str]]:
    """Return {pattern_dir: violation_codes} for every Bedrock-using pattern."""
    results: dict[str, set[str]] = {}
    for tpl in sorted(glob.glob(str(ROOT / "solutions" / "**" / "template.yaml"), recursive=True)):
        if ".aws-sam" in tpl or "/test-data/" in tpl:
            continue
        text = Path(tpl).read_text(encoding="utf-8", errors="ignore")
        # also fold in template-deploy.yaml if present
        deploy = Path(tpl).parent / "template-deploy.yaml"
        if deploy.exists():
            text += "\n" + deploy.read_text(encoding="utf-8", errors="ignore")
        v = classify_template(text)
        if v:
            results[_pattern_dir(Path(tpl))] = v
    return results


def selftest() -> int:
    ok_profile = """
      BedrockModelId:
        Default: "apac.amazon.nova-lite-v1:0"
      Resource:
        - !Sub "arn:aws:bedrock:*::foundation-model/*"
        - !Sub "arn:aws:bedrock:${AWS::Region}:${AWS::AccountId}:inference-profile/*"
      Action: bedrock:InvokeModel
    """
    bad_bare = 'BedrockModelId:\n    Default: "amazon.nova-lite-v1:0"\n'
    bad_iam = "Action: bedrock:InvokeModel\nResource:\n  - foundation-model/x\n"
    bad_wild = "Action: bedrock:InvokeModel\nResource: '*'\n"
    embed_ok = 'Default: "amazon.titan-embed-text-v2:0"\n'
    assert classify_template(ok_profile) == set(), classify_template(ok_profile)
    assert "bare-default" in classify_template(bad_bare)
    assert "iam-missing" in classify_template(bad_iam)
    assert "iam-wildcard" in classify_template(bad_wild)
    assert classify_template(embed_ok) == set()
    print("✅ selftest passed")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()

    results = scan()
    list_mode = "--list" in argv

    compliant = sorted(
        _pattern_dir(Path(t))
        for t in glob.glob(str(ROOT / "solutions" / "**" / "template.yaml"), recursive=True)
        if ".aws-sam" not in t and _pattern_dir(Path(t)) not in results
    )

    print("🔍 Bedrock inference-profile guard\n")
    print(f"   Compliant patterns (Bedrock-agnostic or migrated): {len(compliant)}")
    print(f"   Patterns with violations: {len(results)}")
    print(f"   KNOWN_PENDING allowlist size: {len(KNOWN_PENDING)}\n")

    unexpected = {d: v for d, v in results.items() if d not in KNOWN_PENDING}
    stale_allowlist = sorted(KNOWN_PENDING - set(results))

    if list_mode:
        for d in sorted(results):
            tag = "PENDING" if d in KNOWN_PENDING else "‼️ UNLISTED"
            print(f"  [{tag}] {d}: {sorted(results[d])}")
        return 0

    exit_code = 0
    if unexpected:
        print(f"❌ {len(unexpected)} pattern(s) violate the inference-profile rule and are NOT in KNOWN_PENDING:")
        for d, v in sorted(unexpected.items()):
            print(f"  {d}: {sorted(v)}")
        print("\n💡 Fix per docs/bedrock-inference-profiles.md (geo-prefixed default + inference-profile IAM),")
        print("   or, if intentionally deferred, add the pattern to KNOWN_PENDING with justification.")
        exit_code = 1

    if stale_allowlist:
        print(f"\n❌ {len(stale_allowlist)} KNOWN_PENDING entr(y/ies) are already compliant — remove them:")
        for d in stale_allowlist:
            print(f"  {d}")
        exit_code = 1

    if exit_code == 0:
        print("✅ No unexpected violations. (Remaining KNOWN_PENDING entries shrink as batches land.)")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
