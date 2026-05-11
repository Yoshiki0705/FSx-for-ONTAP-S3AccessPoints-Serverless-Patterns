#!/usr/bin/env python3
"""Detect the UC9-class bug: conditional resources referenced in DefinitionString.

If a Lambda resource has a Condition, but its Arn is referenced from
`DefinitionString: !Sub` without DefinitionSubstitutions + !If, the stack
will fail to create when the condition is false (Sub cannot resolve a
conditional resource ref).

This script parses each template-deploy.yaml, identifies conditional Lambda
resources, then checks whether their ARN is referenced in DefinitionString.
It flags cases where DefinitionSubstitutions is NOT used (so references are
NOT conditionally wrapped).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

# Custom YAML loader that ignores CloudFormation intrinsic functions.
class CfnLoader(yaml.SafeLoader):
    pass


def _cfn_constructor(loader, tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return {"!" + tag_suffix: loader.construct_scalar(node)}
    if isinstance(node, yaml.SequenceNode):
        return {"!" + tag_suffix: loader.construct_sequence(node)}
    if isinstance(node, yaml.MappingNode):
        return {"!" + tag_suffix: loader.construct_mapping(node)}
    return None


CfnLoader.add_multi_constructor("!", _cfn_constructor)


def extract_definition_string(data) -> str:
    """Walk the YAML dict, collect every DefinitionString body as a single string."""
    chunks = []

    def recurse(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "DefinitionString":
                    # v may be {"!Sub": "..."} or {"!Sub": ["...", {...}]}
                    chunks.append(str(v))
                recurse(v)
        elif isinstance(obj, list):
            for item in obj:
                recurse(item)

    recurse(data)
    return "\n".join(chunks)


def find_conditional_lambdas(data) -> dict[str, str]:
    """Return {LogicalId: ConditionName} for Lambda resources with a Condition."""
    result = {}
    resources = data.get("Resources", {})
    for logical_id, spec in resources.items():
        if not isinstance(spec, dict):
            continue
        if spec.get("Type") not in ("AWS::Lambda::Function", "AWS::Serverless::Function"):
            continue
        cond = spec.get("Condition")
        if cond:
            result[logical_id] = cond
    return result


def has_definition_substitutions(data) -> bool:
    """Check whether any AWS::StepFunctions::StateMachine uses DefinitionSubstitutions."""
    resources = data.get("Resources", {})
    for spec in resources.values():
        if not isinstance(spec, dict):
            continue
        if spec.get("Type") != "AWS::StepFunctions::StateMachine":
            continue
        props = spec.get("Properties", {})
        if "DefinitionSubstitutions" in props:
            return True
    return False


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    templates = sorted(repo.glob("*/template-deploy.yaml"))
    # Exclude prototype
    templates = [t for t in templates if "event-driven-prototype" not in str(t)]

    issues = 0
    for tpl in templates:
        with open(tpl, "r", encoding="utf-8") as f:
            data = yaml.load(f, Loader=CfnLoader)

        cond_lambdas = find_conditional_lambdas(data)
        if not cond_lambdas:
            continue

        def_string = extract_definition_string(data)
        referenced = []
        for logical_id in cond_lambdas:
            if logical_id in def_string:
                referenced.append(logical_id)

        if referenced and not has_definition_substitutions(data):
            issues += 1
            rel = tpl.relative_to(repo)
            print(f"=== POTENTIAL UC9-CLASS BUG: {rel} ===")
            print(f"  DefinitionSubstitutions NOT used, but these conditional Lambdas are referenced in DefinitionString:")
            for lid in referenced:
                cond = cond_lambdas[lid]
                print(f"    - {lid} (Condition: {cond})")

    print()
    print(f"Scanned {len(templates)} templates, found {issues} potential UC9-class issue(s)")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
