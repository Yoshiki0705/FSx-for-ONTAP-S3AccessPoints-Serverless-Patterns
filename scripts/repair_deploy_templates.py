#!/usr/bin/env python3
"""Repair drifted/corrupted template-deploy.yaml files (CI-breaking cfn-lint errors).

Fixes two mechanical error classes introduced by earlier bulk edits:
  1. E0000 Athena WorkGroup corruption:
       EnforceWorkGroupConfiguration:
       RecursiveDeleteOption: true true
     -> EnforceWorkGroupConfiguration: true  (+ RecursiveDeleteOption moved to
        WorkGroup Properties level, deduplicated)
  2. E7001 unused `AlarmProfileConfig` Mapping whose key `HIGH_VOLUME` violates the
     CFN Mapping key regex. The mapping has zero FindInMap references -> remove it.

Usage: python3 scripts/repair_deploy_templates.py <template-deploy.yaml> [--write]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


def fix_true_true(content: str) -> str:
    return re.sub(
        r'^(?P<ind>[ \t]+)EnforceWorkGroupConfiguration:[ \t]*\n'
        r'[ \t]+RecursiveDeleteOption:[ \t]*true[ \t]+true[ \t]*\n',
        lambda m: f"{m.group('ind')}EnforceWorkGroupConfiguration: true\n",
        content,
        flags=re.MULTILINE,
    )


def move_recursive_delete_option(content: str) -> str:
    """Move RecursiveDeleteOption out of WorkGroupConfiguration to WorkGroup level."""
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


def remove_alarm_profile_mapping(content: str) -> str:
    """Remove the unused AlarmProfileConfig mapping block (2-space indented key)."""
    return re.sub(
        r'^  AlarmProfileConfig:\n(?:    .*\n|\n)*?(?=^  [A-Za-z0-9]+:\n|^[A-Za-z])',
        '',
        content,
        flags=re.MULTILINE,
    )


def remove_empty_mappings(content: str) -> str:
    """Remove a now-empty `Mappings:` section header."""
    return re.sub(
        r'^Mappings:[ \t]*\n(?=(?:\n)*^(?:Resources|Conditions|Outputs|Globals):)',
        '',
        content,
        flags=re.MULTILINE,
    )


def repair(content: str) -> str:
    content = fix_true_true(content)
    content = move_recursive_delete_option(content)
    # Only remove if not referenced by FindInMap
    if not re.search(r'FindInMap[^\n]*AlarmProfileConfig', content):
        content = remove_alarm_profile_mapping(content)
    content = remove_empty_mappings(content)
    return content


def main() -> int:
    path = Path(sys.argv[1])
    write = "--write" in sys.argv
    new = repair(path.read_text())
    if write:
        path.write_text(new)
        print(f"WROTE {path}")
    else:
        print(new)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
