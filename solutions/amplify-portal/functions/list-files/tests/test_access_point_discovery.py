"""Tests for the listAccessPoints action.

The portal used to offer the alias compiled into the frontend, which says nothing
about whether that access point still exists. These pin the properties that make
asking the API an improvement rather than a new way to fail: the group mapping
still decides visibility, pagination is followed, and a missing read permission
degrades to "state unknown" instead of an empty portal.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

MODULE_PATH = Path(__file__).resolve().parent.parent / "index.py"

DEFAULT_ALIAS = "default-ap-ext-s3alias"
TEAM_ALIAS = "team-ap-ext-s3alias"


def load_module(env: dict[str, str]) -> ModuleType:
    """Import index.py fresh, since its constants are read at import time."""
    with patch.dict(os.environ, env, clear=False):
        spec = importlib.util.spec_from_file_location("list_files_ap_discovery", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules["list_files_ap_discovery"] = module
        spec.loader.exec_module(module)
    return module


@pytest.fixture
def module() -> ModuleType:
    return load_module(
        {
            "S3_AP_ALIAS": DEFAULT_ALIAS,
            "GROUP_AP_MAPPING": f'{{"engineering": "{TEAM_ALIAS}"}}',
        }
    )


def _attachment(alias: str, name: str, lifecycle: str = "AVAILABLE", vpc: str | None = None) -> dict:
    access_point: dict = {"Alias": alias}
    if vpc:
        access_point["VpcConfiguration"] = {"VpcId": vpc}
    return {"Name": name, "Lifecycle": lifecycle, "S3AccessPoint": access_point}


def _fsx(pages: list[list[dict]]) -> MagicMock:
    client = MagicMock()
    client.get_paginator.return_value.paginate.return_value = [{"S3AccessPointAttachments": page} for page in pages]
    return client


def test_default_alias_is_annotated_from_the_api(module: ModuleType) -> None:
    with patch.object(module.boto3, "client", return_value=_fsx([[_attachment(DEFAULT_ALIAS, "portal")]])):
        result = module.handler({"action": "listAccessPoints", "groups": []}, None)

    assert result["discoveryError"] == ""
    assert result["accessPoints"] == [
        {
            "alias": DEFAULT_ALIAS,
            "isDefault": True,
            "name": "portal",
            "lifecycle": "AVAILABLE",
            "origin": "internet",
            "volumeId": "",
        }
    ]


def test_a_group_alias_comes_before_the_default(module: ModuleType) -> None:
    pages = [[_attachment(DEFAULT_ALIAS, "portal"), _attachment(TEAM_ALIAS, "team")]]
    with patch.object(module.boto3, "client", return_value=_fsx(pages)):
        result = module.handler({"action": "listAccessPoints", "groups": ["engineering"]}, None)

    assert [ap["alias"] for ap in result["accessPoints"]] == [TEAM_ALIAS, DEFAULT_ALIAS]


def test_other_teams_access_points_are_not_offered(module: ModuleType) -> None:
    # The whole point of asking the API is knowing whether the caller's alias
    # works, not advertising every access point in the account.
    pages = [[_attachment(DEFAULT_ALIAS, "portal"), _attachment("someone-else-ext-s3alias", "other")]]
    with patch.object(module.boto3, "client", return_value=_fsx(pages)):
        result = module.handler({"action": "listAccessPoints", "groups": []}, None)

    assert [ap["alias"] for ap in result["accessPoints"]] == [DEFAULT_ALIAS]


def test_an_alias_on_a_later_page_is_still_found(module: ModuleType) -> None:
    # Reading only the first page would report a configured alias as absent, and
    # absent looks the same as deleted.
    pages = [[_attachment("filler-ext-s3alias", "filler")], [_attachment(DEFAULT_ALIAS, "portal")]]
    with patch.object(module.boto3, "client", return_value=_fsx(pages)):
        result = module.handler({"action": "listAccessPoints", "groups": []}, None)

    assert result["accessPoints"][0]["lifecycle"] == "AVAILABLE"


def test_a_misconfigured_access_point_is_reported_as_such(module: ModuleType) -> None:
    pages = [[_attachment(DEFAULT_ALIAS, "portal", lifecycle="MISCONFIGURED")]]
    with patch.object(module.boto3, "client", return_value=_fsx(pages)):
        result = module.handler({"action": "listAccessPoints", "groups": []}, None)

    assert result["accessPoints"][0]["lifecycle"] == "MISCONFIGURED"


def test_vpc_origin_is_named_and_internet_origin_is_not_blank(module: ModuleType) -> None:
    pages = [[_attachment(DEFAULT_ALIAS, "portal", vpc="vpc-0123456789abcdef0")]]
    with patch.object(module.boto3, "client", return_value=_fsx(pages)):
        result = module.handler({"action": "listAccessPoints", "groups": []}, None)

    assert result["accessPoints"][0]["origin"] == "vpc-0123456789abcdef0"


def test_a_denied_describe_leaves_the_alias_usable(module: ModuleType) -> None:
    # A missing read permission must not empty the portal: the alias is still
    # offered, with its state declared unknown.
    denied = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "no"}}, "DescribeS3AccessPointAttachments"
    )
    client = MagicMock()
    client.get_paginator.return_value.paginate.side_effect = denied
    with patch.object(module.boto3, "client", return_value=client):
        result = module.handler({"action": "listAccessPoints", "groups": []}, None)

    assert result["accessPoints"] == [
        {
            "alias": DEFAULT_ALIAS,
            "isDefault": True,
            "name": "",
            "lifecycle": "UNKNOWN",
            "origin": "",
            "volumeId": "",
        }
    ]
    assert "AccessDenied" in result["discoveryError"]


def test_no_configured_alias_returns_nothing_without_calling_the_api() -> None:
    module = load_module({"S3_AP_ALIAS": "", "GROUP_AP_MAPPING": "{}"})
    with patch.object(module.boto3, "client") as client:
        result = module.handler({"action": "listAccessPoints", "groups": []}, None)

    assert result == {"accessPoints": [], "discoveryError": ""}
    client.assert_not_called()
