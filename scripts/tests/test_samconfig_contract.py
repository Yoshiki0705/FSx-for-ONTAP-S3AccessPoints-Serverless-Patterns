"""Tests for the samconfig.toml.example contract gate.

The gate's own three rules are exercised against synthetic templates rather than the
repo, so that fixing a real pattern cannot quietly disable a rule.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from check_samconfig_contract import (  # noqa: E402
    authorization_gated_parameters,
    template_parameters,
)

TEMPLATE = """AWSTemplateFormatVersion: "2010-09-09"
Parameters:
  S3AccessPointAlias:
    Type: String
    AllowedPattern: "^[a-z0-9-]+-ext-s3alias$"

  S3AccessPointName:
    Type: String
    Default: ""

  OutputBucketName:
    Type: String
    Default: ""

  NotificationEmail:
    Type: String

Conditions:
  HasS3AccessPointName:
    !Not [!Equals [!Ref S3AccessPointName, ""]]
  HasOutputBucketName:
    !Not [!Equals [!Ref OutputBucketName, ""]]

Resources:
  Role:
    Type: AWS::IAM::Role
    Properties:
      Policies:
        - PolicyDocument:
            Statement:
              - Effect: Allow
                Resource:
                  - !Sub "arn:aws:s3:::${S3AccessPointAlias}/*"
                  - !If
                    - HasS3AccessPointName
                    - !Sub "arn:aws:s3:${AWS::Region}:${AWS::AccountId}:accesspoint/${S3AccessPointName}/object/*"
                    - !Ref AWS::NoValue
                  - !If
                    - HasOutputBucketName
                    - !Sub "arn:aws:s3:::${OutputBucketName}/*"
                    - !Ref AWS::NoValue
"""


def test_first_parameter_is_not_dropped() -> None:
    """Regression: a "\\n  " anchor skipped the first parameter of every template."""
    every, _ = template_parameters(TEMPLATE)
    assert "S3AccessPointAlias" in every, "the first declared parameter must be parsed"


def test_required_means_no_default() -> None:
    every, required = template_parameters(TEMPLATE)
    assert every == {"S3AccessPointAlias", "S3AccessPointName", "OutputBucketName", "NotificationEmail"}
    assert required == {"S3AccessPointAlias", "NotificationEmail"}


def test_only_accesspoint_gated_parameters_are_flagged() -> None:
    """Empty is a legitimate choice for most gated parameters, so the rule is narrow.

    OutputBucketName empty means "create one for me". S3AccessPointName empty removes an
    accesspoint-form ARN from the IAM policy, which cannot be noticed until runtime.
    """
    gated = authorization_gated_parameters(TEMPLATE)
    assert "S3AccessPointName" in gated
    assert "OutputBucketName" not in gated


def test_no_parameters_section_is_not_an_error() -> None:
    every, required = template_parameters("Resources:\n  T:\n    Type: AWS::SNS::Topic\n")
    assert every == set()
    assert required == set()


@pytest.mark.parametrize("pattern", ["defense-satellite", "adtech-creative-management", "utilities-asset-inspection"])
def test_repo_examples_cover_every_required_parameter(pattern: str) -> None:
    """Spot-check the real repo: these three were each broken in a different way."""
    import tomllib

    root = Path(__file__).resolve().parent.parent.parent / "solutions" / "industry" / pattern
    config = tomllib.loads((root / "samconfig.toml.example").read_text())
    supplied = {
        str(item).partition("=")[0].strip() for item in config["default"]["deploy"]["parameters"]["parameter_overrides"]
    }
    _, required = template_parameters((root / "template.yaml").read_text())
    assert not (required - supplied), f"{pattern} example omits required {sorted(required - supplied)}"
