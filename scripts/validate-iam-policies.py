#!/usr/bin/env python3
"""Validate IAM policies extracted from CloudFormation templates using IAM Access Analyzer.

Inspired by CDK Conference Japan 2026 session:
"型も通る、synthも通る、それでも危ない — AIのCDKの権限とコストを機械で検証する"

This script:
1. Reads CloudFormation template(s) (YAML/JSON)
2. Extracts all inline IAM policies from Lambda roles
3. Calls IAM Access Analyzer ValidatePolicy API
4. Reports findings (ERROR, SECURITY_WARNING, WARNING, SUGGESTION)

Usage:
    # Validate a single template
    python scripts/validate-iam-policies.py solutions/industry/legal-compliance/template.yaml

    # Validate all templates
    find solutions/ -name "template.yaml" | xargs python scripts/validate-iam-policies.py

    # CI mode (exit code = number of ERROR/SECURITY_WARNING findings)
    python scripts/validate-iam-policies.py --ci solutions/industry/*/template.yaml

Prerequisites:
    - AWS credentials configured (IAM Access Analyzer is a free API, no charge)
    - pip install boto3 pyyaml

Exit codes:
    0: No errors or security warnings
    N: Number of ERROR + SECURITY_WARNING findings (non-zero = CI failure)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import boto3
import yaml


def extract_iam_policies(template_path: Path) -> list[dict]:
    """Extract inline IAM policies from a CloudFormation template.

    Looks for:
    - AWS::IAM::Role with Policies property (inline policy documents)
    - AWS::IAM::Policy with PolicyDocument
    - AWS::Lambda::Function execution roles with inline policies

    Handles CloudFormation intrinsic functions (!Sub, !Ref, etc.) by
    registering custom YAML constructors.
    """

    # Register CloudFormation intrinsic function handlers for safe_load
    class CfnLoader(yaml.SafeLoader):
        pass

    def _construct_cfn_tag(loader, tag_suffix, node):
        if isinstance(node, yaml.ScalarNode):
            return {f"Fn::{tag_suffix}" if tag_suffix != "Ref" else "Ref": loader.construct_scalar(node)}
        if isinstance(node, yaml.SequenceNode):
            return {f"Fn::{tag_suffix}": loader.construct_sequence(node)}
        if isinstance(node, yaml.MappingNode):
            return {f"Fn::{tag_suffix}": loader.construct_mapping(node)}
        return {}

    cfn_tags = [
        "Sub",
        "Ref",
        "GetAtt",
        "Join",
        "Select",
        "Split",
        "If",
        "Equals",
        "Not",
        "And",
        "Or",
        "FindInMap",
        "Base64",
        "Cidr",
        "ImportValue",
        "GetAZs",
        "Transform",
    ]
    for tag in cfn_tags:
        CfnLoader.add_constructor(f"!{tag}", lambda loader, node, t=tag: _construct_cfn_tag(loader, t, node))
    # Handle !Condition
    CfnLoader.add_constructor("!Condition", lambda loader, node: {"Condition": loader.construct_scalar(node)})

    with open(template_path) as f:
        if template_path.suffix == ".json":
            template = json.load(f)
        else:
            template = yaml.load(f, Loader=CfnLoader)

    if not template or "Resources" not in template:
        return []

    policies = []
    resources = template["Resources"]

    for logical_id, resource in resources.items():
        resource_type = resource.get("Type", "")
        properties = resource.get("Properties", {})

        # AWS::IAM::Role — inline policies
        if resource_type == "AWS::IAM::Role":
            for policy in properties.get("Policies", []):
                doc = policy.get("PolicyDocument")
                if doc:
                    policies.append(
                        {
                            "logical_id": logical_id,
                            "policy_name": policy.get("PolicyName", "unnamed"),
                            "document": doc,
                            "source": str(template_path),
                        }
                    )

        # AWS::IAM::Policy — standalone policy
        elif resource_type == "AWS::IAM::Policy":
            doc = properties.get("PolicyDocument")
            if doc:
                policies.append(
                    {
                        "logical_id": logical_id,
                        "policy_name": properties.get("PolicyName", logical_id),
                        "document": doc,
                        "source": str(template_path),
                    }
                )

    return policies


# Sentinel for values that must be removed entirely, rather than replaced with a
# placeholder: Ref AWS::NoValue, and Fn::If branches that resolve to it.
_OMIT = object()

ARN_PLACEHOLDER = "arn:aws:*:*:123456789012:*"


def resolve_intrinsics(doc: dict) -> str:
    """Best-effort resolution of CloudFormation intrinsics for validation.

    Access Analyzer only accepts fully resolved IAM JSON, so every intrinsic has
    to be replaced with a placeholder before the document is submitted. Any
    intrinsic left in place is reported as INVALID_POLICY_ELEMENT, and because
    Fn::If nests Effect inside a branch it also produces a spurious
    MISSING_EFFECT for the enclosing statement.

    Fn::If is resolved to its true branch, so the policy is validated as it
    exists when the condition holds. The false branch is not validated; that is
    a deliberate limitation of a single-pass check.
    """

    def resolve(obj):
        if isinstance(obj, dict):
            if "Fn::If" in obj:
                branches = obj["Fn::If"]
                # [condition_name, value_if_true, value_if_false]
                if isinstance(branches, list) and len(branches) == 3:
                    return resolve(branches[1])
                return _OMIT
            if "Ref" in obj:
                ref = obj["Ref"]
                if ref == "AWS::NoValue":
                    return _OMIT
                if ref == "AWS::AccountId":
                    return "123456789012"
                if ref == "AWS::Region":
                    return "ap-northeast-1"
                if ref == "AWS::Partition":
                    return "aws"
                if ref == "AWS::StackName":
                    return "test-stack"
                if ref == "AWS::URLSuffix":
                    return "amazonaws.com"
                return f"ref-{ref}"
            for fn in (
                "Fn::Sub",
                "Fn::GetAtt",
                "Fn::Join",
                "Fn::Select",
                "Fn::FindInMap",
                "Fn::ImportValue",
                "Fn::Split",
                "Fn::Transform",
                "Fn::Base64",
                "Fn::Cidr",
            ):
                if fn in obj:
                    # Fn::Split returns a list; everything else a scalar ARN-ish string.
                    return [ARN_PLACEHOLDER] if fn == "Fn::Split" else ARN_PLACEHOLDER
            out = {}
            for key, value in obj.items():
                resolved_value = resolve(value)
                if resolved_value is not _OMIT:
                    out[key] = resolved_value
            return out
        if isinstance(obj, list):
            return [item for item in (resolve(i) for i in obj) if item is not _OMIT]
        return obj

    resolved = resolve(doc)
    if resolved is _OMIT:
        resolved = {}
    return json.dumps(resolved)


def validate_policy(client, policy_json: str) -> list[dict]:
    """Call IAM Access Analyzer ValidatePolicy and return findings."""
    try:
        response = client.validate_policy(
            policyDocument=policy_json,
            policyType="IDENTITY_POLICY",
        )
        return response.get("findings", [])
    except Exception as e:
        return [{"findingType": "ERROR", "issueCode": "API_ERROR", "findingDetails": str(e)}]


def main():
    parser = argparse.ArgumentParser(description="Validate IAM policies from CloudFormation templates")
    parser.add_argument("templates", nargs="+", help="CloudFormation template file(s)")
    parser.add_argument("--ci", action="store_true", help="CI mode: exit with non-zero if errors found")
    parser.add_argument("--region", default="us-east-1", help="AWS region for Access Analyzer API")
    args = parser.parse_args()

    client = boto3.client("accessanalyzer", region_name=args.region)

    total_errors = 0
    total_warnings = 0
    total_suggestions = 0

    for template_path in args.templates:
        path = Path(template_path)
        if not path.exists():
            print(f"  SKIP {template_path} (not found)")
            continue

        policies = extract_iam_policies(path)
        if not policies:
            print(f"  SKIP {template_path} (no IAM policies found)")
            continue

        print(f"\n{'=' * 60}")
        print(f"  Template: {template_path}")
        print(f"  Policies found: {len(policies)}")
        print(f"{'=' * 60}")

        for policy in policies:
            policy_json = resolve_intrinsics(policy["document"])
            findings = validate_policy(client, policy_json)

            errors = [f for f in findings if f.get("findingType") in ("ERROR", "SECURITY_WARNING")]
            warnings = [f for f in findings if f.get("findingType") == "WARNING"]
            suggestions = [f for f in findings if f.get("findingType") == "SUGGESTION"]

            status = "✅" if not errors else "❌"
            print(f"\n  {status} {policy['logical_id']}/{policy['policy_name']}")

            if errors:
                for f in errors:
                    print(f"     ❌ [{f.get('findingType')}] {f.get('issueCode', '')}: {f.get('findingDetails', '')}")
                total_errors += len(errors)

            if warnings:
                for f in warnings:
                    print(f"     ⚠️  [{f.get('findingType')}] {f.get('issueCode', '')}: {f.get('findingDetails', '')}")
                total_warnings += len(warnings)

            if suggestions:
                total_suggestions += len(suggestions)
                # Only show in non-CI mode to reduce noise
                if not args.ci:
                    for f in suggestions:
                        print(
                            f"     💡 [{f.get('findingType')}] {f.get('issueCode', '')}: {f.get('findingDetails', '')}"
                        )

    # Summary
    print(f"\n{'=' * 60}")
    print(
        f"  SUMMARY: {total_errors} errors/security warnings, "
        f"{total_warnings} warnings, {total_suggestions} suggestions"
    )
    print(f"{'=' * 60}")

    if args.ci and total_errors > 0:
        print(f"\n  ❌ CI FAILED: {total_errors} error(s) found")
        sys.exit(total_errors)

    sys.exit(0)


if __name__ == "__main__":
    main()
