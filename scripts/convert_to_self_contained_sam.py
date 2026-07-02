#!/usr/bin/env python3
"""Convert a pattern's template.yaml into a self-contained SAM template.

Handles two broken source shapes:
  A) AWS::Lambda::Function with path-style Handler `<uc>/functions/<dir>/handler.handler`
     and NO Code property (E3003).
  B) AWS::Serverless::Function with dotted Handler `functions.<dir>.handler.handler`
     and NO CodeUri (E0001).

Transforms applied:
  1. Ensure `Transform: AWS::Serverless-2016-10-31` present.
  2. Insert a SharedLayer (AWS::Serverless::LayerVersion, ContentUri ../../../,
     BuildMethod makefile) as the first resource under `Resources:`.
  3. For every function:
     - Type -> AWS::Serverless::Function
     - Handler -> handler.handler
     - insert CodeUri: functions/<dir>/
     - insert Layers: [!Ref SharedLayer]
     - TracingConfig:/Mode: X -> Tracing: X
     - Tags: [ {Key,Value}... ] -> Tags map

Usage: python3 scripts/convert_to_self_contained_sam.py <pattern-dir> [--write]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SHARED_LAYER_BLOCK = """  SharedLayer:
    Type: AWS::Serverless::LayerVersion
    Properties:
      LayerName: !Sub "${AWS::StackName}-shared"
      Description: Shared Python modules (s3ap_helper, ontap_client, observability, etc.)
      ContentUri: ../../../
      CompatibleRuntimes:
        - python3.12
        - python3.13
      CompatibleArchitectures:
        - arm64
        - x86_64
    Metadata:
      BuildMethod: makefile
      BuildArchitecture: arm64

"""


def ensure_transform(content: str) -> str:
    if "Transform: AWS::Serverless-2016-10-31" in content:
        return content
    return re.sub(
        r'(^AWSTemplateFormatVersion:.*\n)',
        r'\1Transform: AWS::Serverless-2016-10-31\n',
        content,
        count=1,
        flags=re.MULTILINE,
    )


def insert_shared_layer(content: str) -> str:
    if "SharedLayer:" in content:
        return content
    # Insert right after the first `Resources:` line (allow trailing comment lines skipped)
    return re.sub(
        r'(^Resources:\s*\n)',
        r'\1' + SHARED_LAYER_BLOCK,
        content,
        count=1,
        flags=re.MULTILINE,
    )


def convert_types(content: str) -> str:
    return content.replace("Type: AWS::Lambda::Function", "Type: AWS::Serverless::Function")


def convert_handlers(content: str) -> str:
    """Convert path/dotted handler to handler.handler + CodeUri + Layers."""
    # Path style: [<uc>/]functions/<dir>/handler.handler  (UC prefix optional)
    path_re = re.compile(
        r'^(?P<ind>\s+)Handler:\s+(?:[A-Za-z0-9_-]+/)?functions/(?P<dir>[A-Za-z0-9_]+)/handler\.handler\s*$',
        re.MULTILINE,
    )
    # Dotted style: functions.<dir>.handler.handler
    dotted_re = re.compile(
        r'^(?P<ind>\s+)Handler:\s+functions\.(?P<dir>[A-Za-z0-9_]+)\.handler\.handler\s*$',
        re.MULTILINE,
    )

    def repl(m: re.Match) -> str:
        ind = m.group("ind")
        d = m.group("dir")
        return (
            f"{ind}Handler: handler.handler\n"
            f"{ind}CodeUri: functions/{d}/\n"
            f"{ind}Layers:\n"
            f"{ind}  - !Ref SharedLayer"
        )

    content = path_re.sub(repl, content)
    content = dotted_re.sub(repl, content)
    return content


def convert_tracing(content: str) -> str:
    # TracingConfig:\n<ind>  Mode: X  -> Tracing: X
    return re.sub(
        r'^(?P<ind>\s+)TracingConfig:\s*\n\s+Mode:\s+(?P<val>.+)$',
        lambda m: f"{m.group('ind')}Tracing: {m.group('val').strip()}",
        content,
        flags=re.MULTILINE,
    )


def convert_tags(content: str) -> str:
    """Convert Tags list -> map ONLY inside AWS::Serverless::Function blocks.

    Other resource types (EC2 SG, S3, etc.) require list-format Tags, so we must
    scope the conversion to function resources only.
    """
    lines = content.split("\n")
    out: list[str] = []
    n = len(lines)
    i = 0

    def top_level_resource_start(idx: int) -> bool:
        return bool(re.match(r"^  [A-Za-z0-9]+:\s*$", lines[idx]))

    current_is_function = False
    while i < n:
        line = lines[i]
        if top_level_resource_start(i):
            current_is_function = False
            j = i + 1
            while j < n and (lines[j].startswith("    ") or lines[j].strip() == ""):
                if lines[j].strip() == "Type: AWS::Serverless::Function":
                    current_is_function = True
                    break
                if re.match(r"^    Type:", lines[j]):
                    break
                j += 1
        m = re.match(r"^(\s+)Tags:\s*$", line)
        if m and current_is_function and i + 1 < n and re.match(r"^\s+-\s+Key:", lines[i + 1]):
            ind = m.group(1)
            out.append(f"{ind}Tags:")
            i += 1
            while i + 1 < n:
                km = re.match(r"^\s+-\s+Key:\s+(.+?)\s*$", lines[i])
                vm = re.match(r"^\s+Value:\s+(.+?)\s*$", lines[i + 1])
                if km and vm:
                    out.append(f"{ind}  {km.group(1)}: {vm.group(1)}")
                    i += 2
                else:
                    break
            continue
        out.append(line)
        i += 1

    return "\n".join(out)


def strip_local_testing_header(content: str) -> str:
    return re.sub(
        r'^# ⚠️ NOTE: This file is for SAM local testing only\.\n'
        r'# The authoritative deployment template is template-deploy\.yaml\.\n'
        r'# Edit template-deploy\.yaml for production changes\.\n#\n',
        '',
        content,
    )


def fix_athena_workgroup(content: str) -> str:
    """Move RecursiveDeleteOption out of WorkGroupConfiguration (it is a direct
    property of AWS::Athena::WorkGroup, not of WorkGroupConfiguration)."""
    return re.sub(
        r'^(?P<ind>[ \t]+)WorkGroupConfiguration:[ \t]*\n'
        r'[ \t]+RecursiveDeleteOption:[ \t]*(?P<val>true|false)[ \t]*\n',
        lambda m: (
            f"{m.group('ind')}RecursiveDeleteOption: {m.group('val')}\n"
            f"{m.group('ind')}WorkGroupConfiguration:\n"
        ),
        content,
        flags=re.MULTILINE,
    )


def convert_deploy_code_blocks(content: str, uc: str) -> str:
    """Convert template-deploy.yaml style Code blocks to CodeUri + Layers."""
    code_re = re.compile(
        r'^(?P<ind>[ \t]+)Handler:[ \t]+handler\.handler[ \t]*\n'
        r'[ \t]+Code:[ \t]*\n'
        r'[ \t]+S3Bucket:[ \t]+!Ref DeployBucket[ \t]*\n'
        r'[ \t]+S3Key:[ \t]+lambda/' + re.escape(uc) + r'-(?P<funcpart>[A-Za-z0-9_-]+)\.zip[ \t]*\n',
        re.MULTILINE,
    )

    def repl(m: re.Match) -> str:
        ind = m.group("ind")
        d = m.group("funcpart").replace("-", "_")
        return (
            f"{ind}Handler: handler.handler\n"
            f"{ind}CodeUri: functions/{d}/\n"
            f"{ind}Layers:\n"
            f"{ind}  - !Ref SharedLayer\n"
        )

    return code_re.sub(repl, content)


def remove_deploy_bucket_param(content: str) -> str:
    return re.sub(
        r'^  DeployBucket:\n(?:    .*\n)+?(?=  [A-Za-z0-9]+:\n|\n)',
        '',
        content,
        count=1,
        flags=re.MULTILINE,
    )


def convert(path: Path, uc: str | None = None, from_deploy: bool = False) -> str:
    content = path.read_text()
    content = strip_local_testing_header(content)
    content = ensure_transform(content)
    if from_deploy:
        content = remove_deploy_bucket_param(content)
    content = convert_types(content)
    content = convert_handlers(content)
    if from_deploy and uc:
        content = convert_deploy_code_blocks(content, uc)
    content = convert_tracing(content)
    content = convert_tags(content)
    content = fix_athena_workgroup(content)
    content = insert_shared_layer(content)
    return content


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    pattern_dir = Path(sys.argv[1])
    write = "--write" in sys.argv
    from_deploy = "--from-deploy" in sys.argv
    uc = pattern_dir.name
    src = pattern_dir / ("template-deploy.yaml" if from_deploy else "template.yaml")
    if not src.exists():
        print(f"ERROR: {src} not found")
        return 1
    new_content = convert(src, uc=uc, from_deploy=from_deploy)
    tpl = pattern_dir / "template.yaml"
    if write:
        tpl.write_text(new_content)
        print(f"WROTE {tpl} (from {src.name})")
    else:
        print(new_content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
