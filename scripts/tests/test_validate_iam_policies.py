"""Tests for scripts/validate-iam-policies.py intrinsic resolution.

Access Analyzer only accepts fully resolved IAM JSON. Any CloudFormation
intrinsic left in the document is reported as INVALID_POLICY_ELEMENT, and
Fn::If additionally hides Effect inside a branch, which produces a spurious
MISSING_EFFECT for the enclosing statement. These tests pin that behaviour so
the validator cannot regress into reporting false positives, and they run
without AWS credentials.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "validate-iam-policies.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("validate_iam_policies", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mod():
    return _load_module()


def _resolved(mod, doc):
    return json.loads(mod.resolve_intrinsics(doc))


def _walk_keys(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield key
            yield from _walk_keys(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_keys(item)


class TestFnIf:
    def test_fn_if_resolves_to_true_branch(self, mod):
        doc = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Fn::If": [
                        "SomeCondition",
                        {"Effect": "Allow", "Action": "s3:GetObject", "Resource": "*"},
                        {"Effect": "Deny", "Action": "s3:*", "Resource": "*"},
                    ]
                }
            ],
        }
        out = _resolved(mod, doc)
        statement = out["Statement"][0]
        # Effect must survive at statement level, otherwise Access Analyzer
        # reports MISSING_EFFECT.
        assert statement["Effect"] == "Allow"
        assert "Fn::If" not in statement

    def test_no_intrinsic_keys_survive(self, mod):
        doc = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": {"Fn::If": ["C", "s3:GetObject", "s3:PutObject"]},
                    "Resource": [
                        {"Fn::Sub": "arn:${AWS::Partition}:s3:::bucket/*"},
                        {"Fn::GetAtt": ["Bucket", "Arn"]},
                        {"Fn::Join": ["", ["a", "b"]]},
                        {"Fn::ImportValue": "OtherStackExport"},
                        {"Fn::Select": [0, ["a", "b"]]},
                        {"Fn::FindInMap": ["M", "K", "V"]},
                    ],
                }
            ],
        }
        out = _resolved(mod, doc)
        leftover = [k for k in _walk_keys(out) if k.startswith("Fn::") or k == "Ref"]
        assert leftover == [], f"unresolved intrinsics leaked: {leftover}"

    def test_malformed_fn_if_is_dropped(self, mod):
        doc = {"Statement": [{"Fn::If": ["OnlyTwoElements", {"Effect": "Allow"}]}]}
        out = _resolved(mod, doc)
        assert out["Statement"] == []


class TestNoValue:
    def test_ref_no_value_key_is_removed(self, mod):
        doc = {
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": "s3:GetObject",
                    "Resource": "*",
                    "Condition": {"Ref": "AWS::NoValue"},
                }
            ]
        }
        out = _resolved(mod, doc)
        assert "Condition" not in out["Statement"][0]
        assert out["Statement"][0]["Effect"] == "Allow"

    def test_fn_if_resolving_to_no_value_is_removed(self, mod):
        doc = {
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": "s3:GetObject",
                    "Resource": "*",
                    "Condition": {"Fn::If": ["C", {"Ref": "AWS::NoValue"}, {"x": "y"}]},
                }
            ]
        }
        out = _resolved(mod, doc)
        assert "Condition" not in out["Statement"][0]


class TestPseudoParameters:
    @pytest.mark.parametrize(
        ("pseudo", "expected"),
        [
            ("AWS::AccountId", "123456789012"),
            ("AWS::Region", "ap-northeast-1"),
            ("AWS::Partition", "aws"),
            ("AWS::StackName", "test-stack"),
            ("AWS::URLSuffix", "amazonaws.com"),
        ],
    )
    def test_pseudo_parameters_resolve(self, mod, pseudo, expected):
        out = _resolved(mod, {"Resource": {"Ref": pseudo}})
        assert out["Resource"] == expected

    def test_output_is_valid_json(self, mod):
        doc = {"Statement": [{"Effect": "Allow", "Action": "s3:*", "Resource": {"Ref": "MyBucket"}}]}
        # json.loads in _resolved would already raise; assert the shape too.
        out = _resolved(mod, doc)
        assert out["Statement"][0]["Resource"] == mod.ARN_PLACEHOLDER


class TestPositionAwareRefs:
    """A Ref to a template parameter has to be shaped for where it sits.

    Substituting a generic "ref-Name" string everywhere produced 51 false
    MISSING_ARN_FIELD and 2 false INVALID_REGION findings from Access Analyzer
    across templates that were correct — the parameter simply carries the ARN or
    Region at deploy time.
    """

    def test_ref_under_resource_becomes_an_arn(self, mod):
        out = _resolved(mod, {"Resource": {"Ref": "FsxAdminSecretArn"}})
        assert out["Resource"].startswith("arn:aws:")

    def test_ref_under_not_resource_becomes_an_arn(self, mod):
        out = _resolved(mod, {"NotResource": {"Ref": "SomeArnParam"}})
        assert out["NotResource"].startswith("arn:aws:")

    def test_ref_in_a_resource_list_becomes_an_arn(self, mod):
        out = _resolved(mod, {"Resource": [{"Ref": "ArnA"}, {"Ref": "ArnB"}]})
        assert all(r.startswith("arn:aws:") for r in out["Resource"])

    def test_ref_under_principal_becomes_an_arn(self, mod):
        out = _resolved(mod, {"Principal": {"AWS": {"Ref": "RoleArnParam"}}})
        assert out["Principal"]["AWS"].startswith("arn:aws:")

    @pytest.mark.parametrize("condition_key", ["aws:RequestedRegion", "ec2:Region"])
    def test_ref_in_a_region_condition_becomes_a_region(self, mod, condition_key):
        out = _resolved(
            mod,
            {"Condition": {"StringEquals": {condition_key: {"Ref": "CrossRegion"}}}},
        )
        value = out["Condition"]["StringEquals"][condition_key]
        assert value == mod.REGION_PLACEHOLDER
        assert not value.startswith("ref-")

    def test_ref_elsewhere_keeps_the_generic_placeholder(self, mod):
        """Positions with no ARN or Region requirement are left recognisable."""
        out = _resolved(mod, {"Condition": {"StringEquals": {"s3:prefix": {"Ref": "Prefix"}}}})
        assert out["Condition"]["StringEquals"]["s3:prefix"] == "ref-Prefix"

    def test_sub_in_a_region_condition_becomes_a_region(self, mod):
        out = _resolved(
            mod,
            {"Condition": {"StringEquals": {"aws:RequestedRegion": {"Fn::Sub": "${Region}"}}}},
        )
        assert out["Condition"]["StringEquals"]["aws:RequestedRegion"] == mod.REGION_PLACEHOLDER
