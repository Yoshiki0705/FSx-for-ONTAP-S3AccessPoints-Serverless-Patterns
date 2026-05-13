#!/usr/bin/env python3
"""StackSets Compatibility Validator — マルチアカウントデプロイ互換性チェック.

検証項目:
1. ハードコード Account ID（12 桁数字列）の検出
2. リソース名の一意性（!Sub による AccountId/StackName 含有）
3. Export 名の衝突可能性
4. VPC/Subnet/SecurityGroup のパラメータ化

Usage:
    python scripts/check_stacksets_compatibility.py
    python scripts/check_stacksets_compatibility.py --template retail-catalog/template-deploy.yaml
    python scripts/check_stacksets_compatibility.py --all
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import NamedTuple

import yaml


# CloudFormation intrinsic function tag constructors
def _cfn_tag_constructor(loader: yaml.SafeLoader, tag_suffix: str, node: yaml.Node) -> dict:
    """Handle CloudFormation intrinsic function tags."""
    if isinstance(node, yaml.ScalarNode):
        return {f"Fn::{tag_suffix}": loader.construct_scalar(node)}
    elif isinstance(node, yaml.SequenceNode):
        return {f"Fn::{tag_suffix}": loader.construct_sequence(node)}
    elif isinstance(node, yaml.MappingNode):
        return {f"Fn::{tag_suffix}": loader.construct_mapping(node)}
    return {}


def _get_cfn_loader() -> type:
    """Create a YAML loader that handles CloudFormation tags."""
    loader = type("CfnLoader", (yaml.SafeLoader,), {})

    cfn_tags = [
        "Ref", "Sub", "GetAtt", "Join", "Select", "Split",
        "If", "Equals", "And", "Or", "Not", "Condition",
        "FindInMap", "GetAZs", "ImportValue", "Base64",
        "Cidr", "Transform",
    ]

    for tag in cfn_tags:
        loader.add_constructor(
            f"!{tag}",
            lambda l, n, t=tag: _cfn_tag_constructor(l, t, n),
        )

    # Handle multi-constructor for unknown tags
    loader.add_multi_constructor(
        "!",
        lambda l, suffix, n: _cfn_tag_constructor(l, suffix, n),
    )

    return loader


class ValidationResult(NamedTuple):
    """バリデーション結果."""

    template_path: str
    rule: str
    severity: str  # "error" | "warning"
    message: str
    line_number: int | None
    fix_suggestion: str


# Patterns
ACCOUNT_ID_PATTERN = re.compile(r"\b\d{12}\b")
VPC_ID_PATTERN = re.compile(r"vpc-[0-9a-f]{8,17}")
SUBNET_ID_PATTERN = re.compile(r"subnet-[0-9a-f]{8,17}")
SG_ID_PATTERN = re.compile(r"sg-[0-9a-f]{8,17}")

# Known safe 12-digit patterns (not account IDs)
SAFE_PATTERNS = {
    "000000000000",  # Placeholder
    "123456789012",  # Example account ID in docs
    "763104351884",  # AWS Deep Learning Container ECR registry
}

# UC directories
UC_DIRS = [
    "legal-compliance",
    "financial-idp",
    "manufacturing-analytics",
    "logistics-ocr",
    "healthcare-dicom",
    "semiconductor-eda",
    "genomics-pipeline",
    "energy-seismic",
    "autonomous-driving",
    "construction-bim",
    "retail-catalog",
    "media-vfx",
    "education-research",
    "insurance-claims",
    "defense-satellite",
    "government-archives",
    "smart-city-geospatial",
]


def check_hardcoded_account_ids(
    template_content: str, path: str
) -> list[ValidationResult]:
    """12 桁数字列のハードコード Account ID を検出する."""
    results: list[ValidationResult] = []

    for line_num, line in enumerate(template_content.splitlines(), 1):
        # Skip comments
        if line.strip().startswith("#"):
            continue

        matches = ACCOUNT_ID_PATTERN.findall(line)
        for match in matches:
            if match in SAFE_PATTERNS:
                continue
            # Check if it's inside a !Sub or ${AWS::AccountId} context
            if "${AWS::AccountId}" in line:
                continue
            # Check if it's a known non-account-ID number (e.g., port numbers, sizes)
            if _is_likely_non_account_id(match, line):
                continue

            results.append(
                ValidationResult(
                    template_path=path,
                    rule="hardcoded-account-id",
                    severity="error",
                    message=f"Hardcoded 12-digit number found: {match}",
                    line_number=line_num,
                    fix_suggestion=(
                        f"Replace '{match}' with !Ref AWS::AccountId or "
                        f"!Sub '${{AWS::AccountId}}' for StackSets compatibility"
                    ),
                )
            )

    return results


def check_resource_name_uniqueness(
    template: dict, path: str
) -> list[ValidationResult]:
    """リソース名に AccountId/StackName が含まれているか検証する."""
    results: list[ValidationResult] = []
    resources = template.get("Resources", {})

    for resource_name, resource_def in resources.items():
        properties = resource_def.get("Properties", {})

        # Check common name properties
        name_fields = [
            "FunctionName",
            "RoleName",
            "QueueName",
            "TableName",
            "TopicName",
            "BucketName",
            "StateMachineName",
        ]

        for field in name_fields:
            if field not in properties:
                continue

            value = properties[field]

            # If it's a plain string (not !Sub), it might collide
            if isinstance(value, str) and not value.startswith("!"):
                # Check if it contains dynamic elements
                if (
                    "${AWS::AccountId}" not in value
                    and "${AWS::StackName}" not in value
                ):
                    results.append(
                        ValidationResult(
                            template_path=path,
                            rule="resource-name-uniqueness",
                            severity="warning",
                            message=(
                                f"Resource '{resource_name}' has static {field}: "
                                f"'{value}'. May collide in multi-account deployment."
                            ),
                            line_number=None,
                            fix_suggestion=(
                                f"Use !Sub '{value}-${{AWS::StackName}}' or "
                                f"!Sub '{value}-${{AWS::AccountId}}' for uniqueness"
                            ),
                        )
                    )

    return results


def check_export_collision(
    template: dict, path: str
) -> list[ValidationResult]:
    """Export 名の衝突可能性を検証する."""
    results: list[ValidationResult] = []
    outputs = template.get("Outputs", {})

    for output_name, output_def in outputs.items():
        export = output_def.get("Export", {})
        if not export:
            continue

        export_name = export.get("Name", "")

        # Check if export name includes stack-specific identifier
        if isinstance(export_name, str):
            if (
                "${AWS::StackName}" not in export_name
                and "${AWS::AccountId}" not in export_name
            ):
                results.append(
                    ValidationResult(
                        template_path=path,
                        rule="export-collision",
                        severity="warning",
                        message=(
                            f"Export '{export_name}' in output '{output_name}' "
                            f"may collide across accounts/stacks"
                        ),
                        line_number=None,
                        fix_suggestion=(
                            f"Use !Sub '${{AWS::StackName}}-{export_name}' "
                            f"to ensure uniqueness"
                        ),
                    )
                )

    return results


def check_vpc_parameterization(
    template_content: str, template: dict, path: str
) -> list[ValidationResult]:
    """VPC/Subnet/SecurityGroup がパラメータ化されているか検証する."""
    results: list[ValidationResult] = []

    for line_num, line in enumerate(template_content.splitlines(), 1):
        if line.strip().startswith("#"):
            continue

        for pattern, resource_type in [
            (VPC_ID_PATTERN, "VPC ID"),
            (SUBNET_ID_PATTERN, "Subnet ID"),
            (SG_ID_PATTERN, "Security Group ID"),
        ]:
            matches = pattern.findall(line)
            for match in matches:
                results.append(
                    ValidationResult(
                        template_path=path,
                        rule="vpc-parameterization",
                        severity="error",
                        message=(
                            f"Hardcoded {resource_type} found: {match}"
                        ),
                        line_number=line_num,
                        fix_suggestion=(
                            f"Replace '{match}' with a Parameter reference "
                            f"(e.g., !Ref VpcId) for StackSets compatibility"
                        ),
                    )
                )

    return results


def validate_template(template_path: str) -> list[ValidationResult]:
    """テンプレートの全検証を実行する."""
    path = Path(template_path)
    if not path.exists():
        return [
            ValidationResult(
                template_path=template_path,
                rule="file-not-found",
                severity="error",
                message=f"Template file not found: {template_path}",
                line_number=None,
                fix_suggestion="Check the file path",
            )
        ]

    content = path.read_text(encoding="utf-8")

    try:
        template = yaml.load(content, Loader=_get_cfn_loader())
    except yaml.YAMLError as e:
        return [
            ValidationResult(
                template_path=template_path,
                rule="yaml-parse-error",
                severity="error",
                message=f"YAML parse error: {e}",
                line_number=None,
                fix_suggestion="Fix YAML syntax",
            )
        ]

    if not isinstance(template, dict):
        return []

    results: list[ValidationResult] = []
    results.extend(check_hardcoded_account_ids(content, template_path))
    results.extend(check_resource_name_uniqueness(template, template_path))
    results.extend(check_export_collision(template, template_path))
    results.extend(check_vpc_parameterization(content, template, template_path))

    return results


def _is_likely_non_account_id(number: str, line: str) -> bool:
    """12 桁数字列が Account ID でない可能性が高いか判定."""
    # Common non-account-ID patterns
    # - Timestamps (e.g., 20260513103000)
    # - Large numbers in descriptions
    if "Description" in line and ":" in line:
        return True
    # Port numbers, sizes, etc. are typically much smaller
    # but 12-digit numbers in those contexts are unlikely
    return False


def find_all_templates(project_root: Path) -> list[Path]:
    """全 UC テンプレートを検索する."""
    templates: list[Path] = []
    for uc_dir in UC_DIRS:
        template_path = project_root / uc_dir / "template-deploy.yaml"
        if template_path.exists():
            templates.append(template_path)
    return templates


def main() -> int:
    """メインエントリポイント."""
    parser = argparse.ArgumentParser(
        description="StackSets Compatibility Validator"
    )
    parser.add_argument(
        "--template",
        type=str,
        help="Single template to validate",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Validate all 17 UC templates",
    )
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent

    if args.template:
        templates = [Path(args.template)]
    elif args.all:
        templates = find_all_templates(project_root)
    else:
        templates = find_all_templates(project_root)

    all_results: list[ValidationResult] = []
    for template_path in templates:
        results = validate_template(str(template_path))
        all_results.extend(results)

    # Print results
    errors = [r for r in all_results if r.severity == "error"]
    warnings = [r for r in all_results if r.severity == "warning"]

    if errors:
        print(f"\n{'='*60}")
        print(f"ERRORS ({len(errors)}):")
        print(f"{'='*60}")
        for r in errors:
            line_info = f":{r.line_number}" if r.line_number else ""
            print(f"  [{r.rule}] {r.template_path}{line_info}")
            print(f"    {r.message}")
            print(f"    Fix: {r.fix_suggestion}")
            print()

    if warnings:
        print(f"\n{'='*60}")
        print(f"WARNINGS ({len(warnings)}):")
        print(f"{'='*60}")
        for r in warnings:
            line_info = f":{r.line_number}" if r.line_number else ""
            print(f"  [{r.rule}] {r.template_path}{line_info}")
            print(f"    {r.message}")
            print(f"    Fix: {r.fix_suggestion}")
            print()

    # Summary
    print(f"\n{'='*60}")
    print(f"SUMMARY: {len(templates)} templates checked")
    print(f"  Errors:   {len(errors)}")
    print(f"  Warnings: {len(warnings)}")
    print(f"{'='*60}")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
