#!/usr/bin/env python3
"""Opt-in live smoke test: invoke Bedrock through a cross-region inference profile.

This is the true end-to-end check that a geo-prefixed inference-profile ID actually
works on-demand via the shared Converse helper. It makes a REAL Bedrock call and
therefore:
  - requires AWS credentials with bedrock:InvokeModel,
  - requires model access enabled for the target model in the region(s) the profile
    spans (Bedrock console -> Model access),
  - incurs a small token cost.

It is intentionally NOT a pytest and is NOT run in CI.

Usage:
    # default: apac.amazon.nova-lite-v1:0 in ap-northeast-1
    python3 scripts/bedrock_inference_profile_smoke.py

    # pick model / region / prompt
    python3 scripts/bedrock_inference_profile_smoke.py \
        --model-id us.amazon.nova-lite-v1:0 --region us-east-1 \
        --prompt "Say hello in one short sentence."

    # negative control: prove a BARE id fails on-demand (expected ValidationException)
    python3 scripts/bedrock_inference_profile_smoke.py --model-id amazon.nova-lite-v1:0

Exit codes: 0 success, 2 invocation failed (message printed), 3 bad usage.

See docs/bedrock-inference-profiles.md.
"""

from __future__ import annotations

import argparse
import glob
import re
import sys
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shared.bedrock_helper import converse_text, is_inference_profile_id  # noqa: E402


def _discover_repo_default_models() -> list[str]:
    """Return the distinct geo-prefixed model/profile IDs the templates default to.

    This lets one invocation validate that *every* default the fleet ships actually
    resolves + invokes — catching invalid profile IDs (e.g. a geo prefix that does not
    exist for a given model) that static checks cannot detect.
    """
    pat = re.compile(r'Default:\s*"?((?:apac|us|eu|us-gov|jp|au|ca|global)\.[A-Za-z0-9.:-]+)"?')
    found: set[str] = set()
    for tpl in glob.glob(str(ROOT / "solutions" / "**" / "template*.yaml"), recursive=True):
        if ".aws-sam" in tpl:
            continue
        for m in pat.finditer(Path(tpl).read_text(encoding="utf-8", errors="ignore")):
            found.add(m.group(1))
    return sorted(found)


def _invoke_once(model_id: str, region: str, prompt: str, max_tokens: int) -> tuple[bool, str]:
    client = boto3.client("bedrock-runtime", region_name=region)
    try:
        text = converse_text(model_id=model_id, prompt=prompt, max_tokens=max_tokens, temperature=0.2, client=client)
        return True, text.replace("\n", " ")[:60]
    except Exception as e:  # noqa: BLE001 — surface the real error to the operator
        return False, f"{type(e).__name__}: {e}"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Live Bedrock inference-profile smoke test")
    parser.add_argument("--model-id", default="apac.amazon.nova-lite-v1:0", help="model or inference-profile ID")
    parser.add_argument("--region", default="ap-northeast-1", help="AWS region")
    parser.add_argument("--prompt", default="Reply with a single short sentence confirming you are reachable.")
    parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument(
        "--all-repo-defaults",
        action="store_true",
        help="Discover every geo-prefixed default in the templates and invoke each once (fleet validation).",
    )
    args = parser.parse_args(argv)

    if args.all_repo_defaults:
        models = _discover_repo_default_models()
        print(f"Discovered {len(models)} distinct geo-prefixed default(s) in templates; region={args.region}\n")
        failures = 0
        for mid in models:
            ok, detail = _invoke_once(mid, args.region, args.prompt, args.max_tokens)
            print(f"  {'✅' if ok else '❌'} {mid}\n      {detail}")
            failures += 0 if ok else 1
        print(f"\n{'✅ all defaults invoke' if failures == 0 else f'❌ {failures} default(s) failed'} in {args.region}")
        return 0 if failures == 0 else 2

    profile_like = is_inference_profile_id(args.model_id)
    print(f"model_id       : {args.model_id}")
    print(f"region         : {args.region}")
    print(f"inference-profile id? {profile_like}")
    if not profile_like:
        print("⚠️  This is a BARE model id. Nova/newer Claude will likely fail on-demand")
        print("    with a ValidationException — that is the expected negative control.")

    client = boto3.client("bedrock-runtime", region_name=args.region)
    try:
        text = converse_text(
            model_id=args.model_id,
            prompt=args.prompt,
            max_tokens=args.max_tokens,
            temperature=0.2,
            client=client,
        )
    except Exception as e:  # noqa: BLE001 — surface the real error to the operator
        print(f"\n❌ Invocation failed: {type(e).__name__}: {e}")
        return 2

    print("\n✅ Invocation succeeded. Model response:")
    print("-" * 60)
    print(text)
    print("-" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
