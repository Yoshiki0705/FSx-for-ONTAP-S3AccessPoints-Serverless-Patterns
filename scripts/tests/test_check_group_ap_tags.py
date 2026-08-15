"""Tests for the groupApMapping / access point tag consistency check.

The check exists because the mapping is hand-written and nothing reported when it
stopped matching the resources. These pin the cases where a silent pass would put
the check back where it started: a group whose access point is gone, an alias that
moved, a tag nobody put in the mapping, and a tag value claimed by two access
points.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "check_group_ap_tags.py"
_spec = importlib.util.spec_from_file_location("check_group_ap_tags", SCRIPT)
assert _spec and _spec.loader
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)

TAG = check.DEFAULT_TAG_KEY


def test_mapping_is_parsed_from_typescript() -> None:
    source = """
    export const config: PortalConfig = {
      region: "ap-northeast-1",
      groupApMapping: {
        engineering: "eng-ap-ext-s3alias",
        "finance": 'fin-ap-ext-s3alias',
      },
      bedrockKbId: "",
    };
    """
    assert check.parse_mapping(source) == {
        "engineering": "eng-ap-ext-s3alias",
        "finance": "fin-ap-ext-s3alias",
    }


def test_an_empty_mapping_is_not_a_finding() -> None:
    # The documented default: every user shares one access point.
    assert check.parse_mapping("groupApMapping: {},") == {}
    assert check.parse_mapping('region: "ap-northeast-1",') == {}


def test_agreement_produces_no_findings() -> None:
    findings = check.compare(
        {"engineering": "eng-ap-ext-s3alias"},
        {"engineering": ["eng-ap-ext-s3alias"]},
        TAG,
    )
    assert findings == []


def test_a_group_with_no_tagged_access_point_is_reported() -> None:
    findings = check.compare({"engineering": "eng-ap-ext-s3alias"}, {}, TAG)
    assert len(findings) == 1
    assert "no access point tagged" in findings[0]


def test_an_alias_that_moved_is_reported() -> None:
    # The failure this check is for: the file still names the old access point.
    findings = check.compare(
        {"engineering": "old-ap-ext-s3alias"},
        {"engineering": ["new-ap-ext-s3alias"]},
        TAG,
    )
    assert len(findings) == 1
    assert "new-ap-ext-s3alias" in findings[0]


def test_a_tag_absent_from_the_mapping_is_reported() -> None:
    findings = check.compare(
        {"engineering": "eng-ap-ext-s3alias"},
        {"engineering": ["eng-ap-ext-s3alias"], "finance": ["fin-ap-ext-s3alias"]},
        TAG,
    )
    assert len(findings) == 1
    assert "does not mention" in findings[0]


def test_two_access_points_claiming_one_group_are_reported() -> None:
    # The mapping can name one alias, so a second tagged access point is
    # unreachable through it and the operator has to choose.
    findings = check.compare(
        {"engineering": "eng-ap-ext-s3alias"},
        {"engineering": ["eng-ap-ext-s3alias", "eng2-ap-ext-s3alias"]},
        TAG,
    )
    assert len(findings) == 1
    assert "can name only one" in findings[0]


def test_pagination_is_followed(monkeypatch: pytest.MonkeyPatch) -> None:
    # Reading one page would drop a tagged access point and report the group as
    # untagged, which is the opposite of the truth.
    pages = [
        [{"S3AccessPoint": {"Alias": "a-ext-s3alias"}, "Tags": [{"Key": TAG, "Value": "one"}]}],
        [{"S3AccessPoint": {"Alias": "b-ext-s3alias"}, "Tags": [{"Key": TAG, "Value": "two"}]}],
    ]

    class _Paginator:
        def paginate(self) -> list[dict[str, Any]]:
            return [{"S3AccessPointAttachments": page} for page in pages]

    class _Fsx:
        def get_paginator(self, name: str) -> _Paginator:
            assert name == "describe_s3_access_point_attachments"
            return _Paginator()

    monkeypatch.setattr(check.boto3, "client", lambda *a, **k: _Fsx())
    assert check.tagged_access_points(["ap-northeast-1"], TAG) == {
        "one": ["a-ext-s3alias"],
        "two": ["b-ext-s3alias"],
    }


def test_a_missing_config_is_reported_rather_than_passed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # portal-config.ts is gitignored. "No config" and "config agrees" are
    # different answers, and exiting 0 here would hide the difference.
    code = check.main(["--regions", "ap-northeast-1", "--config", str(tmp_path / "absent.ts")])
    assert code == 2
    assert "nothing to compare" in capsys.readouterr().err
