#!/usr/bin/env python3
"""Check that the deployed Lambda layer really carries the shared/ modules.

The portal's containment actions import `shared.ontap_response`. That import
failed in every deployment for a long time, and two separate mistakes kept it
hidden:

- the first bundler copied only top-level modules, and `shared/__init__.py`
  imports its subpackages eagerly, so `import shared` failed on a missing
  subpackage rather than on the module actually wanted
- `ampx sandbox` deploys via CDK hotswap, which updates function code in place
  and skips LayerVersion content changes, so a corrected layer was never
  published and the deployment reported success

Checking the synthesized template is not enough for either of those. This reads
what is actually attached to the deployed function.

Usage
    python3 scripts/portal-probes/verify_shared_layer.py
    python3 scripts/portal-probes/verify_shared_layer.py --expect-subpackage streaming schemas routing
"""

from __future__ import annotations

import argparse
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).parent))
from _common import find_function  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--function", default="ArpResponseFun")
    parser.add_argument("--region", default="ap-northeast-1")
    parser.add_argument(
        "--expect-module",
        nargs="*",
        default=["ontap_client", "ontap_response", "routing", "observability", "exceptions"],
        help="top-level modules that shared/__init__.py imports, plus the containment path",
    )
    parser.add_argument(
        "--expect-subpackage",
        nargs="*",
        default=["streaming", "schemas"],
        help="subpackages that shared/__init__.py imports eagerly",
    )
    args = parser.parse_args()

    lam = boto3.client("lambda", region_name=args.region)
    name = find_function(args.function, args.region)
    config = lam.get_function_configuration(FunctionName=name)

    layers = config.get("Layers") or []
    if not layers:
        print(f"{name.split('-')[-1]} has no layers attached; the containment imports cannot resolve")
        return 1

    problems = 0
    for layer in layers:
        arn = layer["Arn"]
        version = arn.rsplit(":", 1)[-1]
        layer_name = arn.rsplit(":", 2)[-2]
        print(f"layer: {layer_name} version {version}")

        detail = lam.get_layer_version_by_arn(Arn=arn)
        print(f"  description: {detail.get('Description', '')}")

        with urllib.request.urlopen(detail["Content"]["Location"]) as response:  # noqa: S310
            archive = zipfile.ZipFile(io.BytesIO(response.read()))

        names = archive.namelist()
        # Python only searches /opt/python, so the archive must carry that prefix.
        if not any(n.startswith("python/") for n in names):
            print("  FAIL  no python/ prefix, so Lambda will not put this on sys.path")
            problems += 1
            continue

        py_files = [n for n in names if n.endswith(".py")]
        print(f"  {len(py_files)} .py files")

        for module in args.expect_module:
            present = any(n.endswith(f"shared/{module}.py") for n in names) or any(
                f"shared/{module}/" in n for n in names
            )
            print(f"  {'ok  ' if present else 'FAIL'} module {module}")
            problems += 0 if present else 1

        for package in args.expect_subpackage:
            # Accept either shape. Something imported as `shared.x` can be a
            # package directory or a single module, and converting between the
            # two is a refactor, not a packaging failure.
            as_package = any(f"shared/{package}/" in n for n in names)
            as_module = any(n.endswith(f"shared/{package}.py") for n in names)
            present = as_package or as_module
            shape = "package" if as_package else "module" if as_module else "missing"
            print(f"  {'ok  ' if present else 'FAIL'} subpackage {package} ({shape})")
            problems += 0 if present else 1

    if problems:
        print(
            f"\n{problems} problem(s). If the content looks stale rather than wrong, the layer was\n"
            "probably not republished: a LayerVersion is immutable, and hotswap skips content-only\n"
            "changes, so the description carries a fingerprint of the sources to force a replacement."
        )
        return 1

    print("\nSHARED LAYER: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
