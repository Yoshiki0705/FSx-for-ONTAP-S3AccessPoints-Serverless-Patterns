"""Tests for the S3 access point inventory script.

The properties worth pinning are the ones that would let a stale or partial
inventory pass as a complete one: reading only the first page, treating a
`MISCONFIGURED` access point as usable, or reporting success for an alias that
is not there.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "discover_s3_access_points.py"
_spec = importlib.util.spec_from_file_location("discover_s3_access_points", SCRIPT)
assert _spec and _spec.loader
discover = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(discover)


def _attachment(name: str, lifecycle: str = "AVAILABLE", vpc: str | None = None) -> dict[str, Any]:
    access_point: dict[str, Any] = {"Alias": f"{name}-ext-s3alias"}
    if vpc:
        access_point["VpcConfiguration"] = {"VpcId": vpc}
    return {
        "Name": name,
        "Lifecycle": lifecycle,
        "Type": "ONTAP",
        "S3AccessPoint": access_point,
    }


class _FakePaginator:
    def __init__(self, pages: list[list[dict[str, Any]]]) -> None:
        self._pages = pages

    def paginate(self) -> list[dict[str, Any]]:
        return [{"S3AccessPointAttachments": page} for page in self._pages]


class _FakeFsx:
    def __init__(self, pages: list[list[dict[str, Any]]]) -> None:
        self._pages = pages

    def get_paginator(self, name: str) -> _FakePaginator:
        assert name == "describe_s3_access_point_attachments"
        return _FakePaginator(self._pages)


@pytest.fixture
def two_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    """An account whose attachments do not fit in one page."""
    pages = [
        [_attachment("first"), _attachment("broken", lifecycle="MISCONFIGURED")],
        [_attachment("second", vpc="vpc-0123456789abcdef0")],
    ]
    monkeypatch.setattr(discover, "_client", lambda *a, **k: _FakeFsx(pages))


def test_every_page_is_read(two_pages: None) -> None:
    # A single describe call would have returned two of the three, and the
    # missing one looks identical to an access point that does not exist.
    rows = discover.collect(["ap-northeast-1"], [], None, None)
    assert [r["name"] for r in rows] == ["first", "broken", "second"]


def test_lifecycle_filter_excludes_unusable(two_pages: None) -> None:
    rows = discover.collect(["ap-northeast-1"], [], None, discover.USABLE)
    assert [r["name"] for r in rows] == ["first", "second"]


def test_absent_vpc_configuration_is_reported_as_internet(two_pages: None) -> None:
    # The distinction decides whether a browser can reach the access point at
    # all, so it must not be blank when the API simply omits the key.
    rows = {r["name"]: r for r in discover.collect(["ap-northeast-1"], [], None, None)}
    assert rows["first"]["origin"] == "internet"
    assert rows["second"]["origin"] == "vpc-0123456789abcdef0"


def test_regions_are_queried_separately(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def fake_client(service: str, region: str, account: str | None, role_name: str | None) -> _FakeFsx:
        seen.append(region)
        return _FakeFsx([[_attachment(f"ap-{region}")]])

    monkeypatch.setattr(discover, "_client", fake_client)
    rows = discover.collect(["ap-northeast-1", "us-east-1"], [], None, None)
    assert seen == ["ap-northeast-1", "us-east-1"]
    assert len(rows) == 2


def test_require_alias_fails_when_absent(two_pages: None, capsys: pytest.CaptureFixture[str]) -> None:
    code = discover.main(["--regions", "ap-northeast-1", "--require-alias", "nowhere-ext-s3alias", "--format", "alias"])
    assert code == 1
    assert "not found" in capsys.readouterr().err


def test_require_alias_passes_when_available(two_pages: None) -> None:
    assert (
        discover.main(["--regions", "ap-northeast-1", "--require-alias", "first-ext-s3alias", "--format", "alias"]) == 0
    )


def test_require_alias_rejects_a_misconfigured_access_point(two_pages: None) -> None:
    # Present in the account, unusable for data operations. Reporting success
    # here is the failure this gate exists to prevent.
    assert (
        discover.main(["--regions", "ap-northeast-1", "--require-alias", "broken-ext-s3alias", "--format", "alias"])
        == 1
    )


def test_cross_account_requires_a_role(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        discover.main(["--regions", "ap-northeast-1", "--accounts", "111111111111"])
    assert "--role-name" in capsys.readouterr().err
