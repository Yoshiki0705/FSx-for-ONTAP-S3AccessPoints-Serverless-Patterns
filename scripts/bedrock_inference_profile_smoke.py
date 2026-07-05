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
import sys
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.bedrock_helper import converse_text, is_inference_profile_id  # noqa: E402


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Live Bedrock inference-profile smoke test")
    parser.add_argument("--model-id", default="apac.amazon.nova-lite-v1:0", help="model or inference-profile ID")
    parser.add_argument("--region", default="ap-northeast-1", help="AWS region")
    parser.add_argument("--prompt", default="Reply with a single short sentence confirming you are reachable.")
    parser.add_argument("--max-tokens", type=int, default=128)
    args = parser.parse_args(argv)

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
