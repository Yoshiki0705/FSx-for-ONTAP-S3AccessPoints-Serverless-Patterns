"""Tests for the boundary on presigned URL generation.

A presigned URL is a bearer credential that outlives the request, and it executes as
the ONTAP identity of the access point it was signed against. Measurement on
2026-08-26 (ONTAP 9.18.1P3D1) showed what that costs when the two are not connected:
a URL signed against an access point pinned to UNIX `root` read a directory at mode
0700 owned by an unrelated uid, and a `PUT` signed the same way landed as uid 0. The
same key signed against a read-only access point answered 403.

So there are two things to hold, and both were absent here while the listing endpoint
had them: the caller's group must choose the access point, and the key must be inside
the caller's prefixes before anything is signed. The tests are ordered that way --
routing, then the key check, then the compatibility case that must keep working for a
deployment which configures neither.

Signing is stubbed at `S3ApHelper`. What matters is which access point the helper was
constructed with and whether it was constructed at all, not the bytes of the URL.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

MODULE_PATH = Path(__file__).resolve().parent.parent / "index.py"

DEFAULT_ALIAS = "default-ap-s3alias"
TEAM_A_ALIAS = "team-a-readonly-ap-s3alias"
TEAM_B_ALIAS = "team-b-ap-s3alias"

GROUP_AP_MAPPING = {"team-a": TEAM_A_ALIAS, "team-b": TEAM_B_ALIAS}
GROUP_PATH_PREFIXES = {"team-a": ["team-a/", "shared/"], "team-b": ["team-b/", "shared/"]}


def load_module(env: dict[str, str] | None = None) -> Any:
    """Import index.py fresh, since its configuration is read at import time."""
    base = {
        "S3_AP_ALIAS": DEFAULT_ALIAS,
        "GROUP_AP_MAPPING": json.dumps(GROUP_AP_MAPPING),
        "GROUP_PATH_PREFIXES": json.dumps(GROUP_PATH_PREFIXES),
        "URL_AUDIT_TABLE_NAME": "",
        "AWS_REGION": "ap-northeast-1",
    }
    base.update(env or {})
    with patch.dict(os.environ, base, clear=False):
        spec = importlib.util.spec_from_file_location("presigned_url_under_test", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules["presigned_url_under_test"] = module
        spec.loader.exec_module(module)
    # Replaces the helper class, so the assertions can read which access point it was
    # constructed with. Stubbing the boto3 client instead would test one layer lower
    # and say nothing about the routing decision, which is the thing that regressed.
    module.S3ApHelper = MagicMock()
    module.S3ApHelper.return_value.generate_presigned_get_url.return_value = "https://example.invalid/signed"
    return module


def call(module: Any, key: str, groups: list[str] | None = None) -> dict:
    """Invoke the handler as the resolver would, with an attributed caller.

    Args:
        module: The freshly imported handler module.
        key: The object key being requested.
        groups: The caller's Cognito groups.

    Returns:
        The handler's response.
    """
    return module.handler({"key": key, "userId": "someone", "groups": groups or []}, None)


def signed_bucket(module: Any) -> str:
    """The access point the URL was signed against."""
    return module.S3ApHelper.call_args.args[0]


def nothing_was_signed(module: Any) -> bool:
    """Whether the handler refused before any URL could exist."""
    return not module.S3ApHelper.called


class TestAccessPointRouting:
    def test_a_mapped_group_signs_against_its_own_access_point(self) -> None:
        module = load_module()
        result = call(module, "team-a/report.pdf", groups=["team-a"])
        assert result["error"] is None
        assert signed_bucket(module) == TEAM_A_ALIAS

    def test_an_unmapped_caller_signs_against_the_default(self) -> None:
        module = load_module()
        result = call(module, "shared/report.pdf", groups=["some-other-group"])
        assert result["error"] is None
        assert signed_bucket(module) == DEFAULT_ALIAS

    def test_a_mapped_group_never_signs_against_the_default(self) -> None:
        """The measured regression, stated as an assertion.

        The identity a presigned URL executes as follows from the access point. While
        this function read `S3_AP_ALIAS` alone, a caller mapped to a read-only access
        point received a URL signed against the deployment default -- which the
        documented runbook pins to UNIX `root`. The bypass produced no error, so
        nothing short of checking the bucket catches it.
        """
        module = load_module()
        call(module, "team-a/report.pdf", groups=["team-a"])
        assert signed_bucket(module) != DEFAULT_ALIAS

    def test_no_alias_configured_signs_nothing(self) -> None:
        module = load_module({"S3_AP_ALIAS": "", "GROUP_AP_MAPPING": "{}"})
        result = call(module, "shared/report.pdf")
        assert result["url"] is None
        assert "S3_AP_ALIAS" in result["error"]
        assert nothing_was_signed(module)


class TestKeyBoundary:
    def test_a_key_outside_the_callers_prefixes_is_refused_before_signing(self) -> None:
        module = load_module()
        result = call(module, "team-b/secret.pdf", groups=["team-a"])
        assert result["url"] is None
        assert "outside the prefixes" in result["error"]
        # The refusal has to come first. A URL that is signed and then withheld is
        # still a credential that existed, and the audit row would claim it was issued.
        assert nothing_was_signed(module)

    def test_a_key_inside_the_callers_prefixes_is_signed(self) -> None:
        module = load_module()
        assert call(module, "team-a/report.pdf", groups=["team-a"])["error"] is None
        assert call(module, "shared/report.pdf", groups=["team-a"])["error"] is None

    def test_a_traversal_segment_is_refused(self) -> None:
        module = load_module()
        result = call(module, "team-a/../team-b/secret.pdf", groups=["team-a"])
        assert result["url"] is None
        assert ".." in result["error"]
        assert nothing_was_signed(module)

    def test_an_empty_key_is_refused(self) -> None:
        module = load_module()
        assert call(module, "", groups=["team-a"])["url"] is None
        assert nothing_was_signed(module)

    def test_storage_admin_is_not_confined_to_prefixes(self) -> None:
        """Matches the boundary the rest of the portal applies, so admin views work."""
        module = load_module()
        result = call(module, "team-b/secret.pdf", groups=["storage-admin"])
        assert result["error"] is None


class TestBackwardCompatibility:
    def test_a_deployment_with_no_boundary_configured_keeps_working(self) -> None:
        """The boundary is opt-in. Without it nothing is filtered, as before."""
        module = load_module({"GROUP_AP_MAPPING": "{}", "GROUP_PATH_PREFIXES": "{}"})
        result = call(module, "anything/at/all.pdf", groups=[])
        assert result["error"] is None
        assert signed_bucket(module) == DEFAULT_ALIAS


class TestAuditRow:
    """The ledger write now goes through shared/portal_activity_ledger.py.

    Patched there rather than on this module, which no longer imports boto3 at all --
    the inline writer it used to hold was duplicated per handler, and the download,
    upload-link and delete paths needed the same row shape.
    """

    def test_the_access_point_is_recorded_with_the_key(self) -> None:
        """Two rows naming the same key differ only by the identity behind them."""
        module = load_module({"URL_AUDIT_TABLE_NAME": "url-audit"})
        table = MagicMock()
        with patch("shared.portal_activity_ledger.boto3.resource") as resource:
            resource.return_value.Table.return_value = table
            call(module, "team-a/report.pdf", groups=["team-a"])
        item = table.put_item.call_args.kwargs["Item"]
        assert item["file_key"] == "team-a/report.pdf"
        assert item["access_point"] == TEAM_A_ALIAS
        assert item["generated_by"] == "someone"

    def test_a_refused_key_is_not_recorded_as_issued(self) -> None:
        module = load_module({"URL_AUDIT_TABLE_NAME": "url-audit"})
        table = MagicMock()
        with patch("shared.portal_activity_ledger.boto3.resource") as resource:
            resource.return_value.Table.return_value = table
            call(module, "team-b/secret.pdf", groups=["team-a"])
        table.put_item.assert_not_called()
