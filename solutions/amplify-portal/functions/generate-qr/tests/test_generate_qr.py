"""Tests for the boundary on the QR-encoded share link.

A presigned URL is a bearer credential that outlives the request, and it executes as
the ONTAP identity of the access point it was signed against. The QR code adds one
thing: the URL leaves the browser as an image meant to be scanned by another device,
so the credential is expected to travel.

`shared/tests/test_portal_path_scope.py` covers `scope_for_caller` itself. What is
asserted here is that this handler calls it before signing anything, that it signs
against the caller's own access point rather than the default, and that the external
share-link refusal comes first -- whether a caller may mint a link at all does not
depend on which key they asked for, and answering in that order keeps the denial from
confirming the key exists.

`S3ApHelper` is stubbed. What matters is which access point it was constructed with and
whether it was constructed at all, not the bytes of the URL.
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
TEAM_A_ALIAS = "team-a-ap-s3alias"
GROUP_AP_MAPPING = {"team-a": TEAM_A_ALIAS}
GROUP_PATH_PREFIXES = {"team-a": ["team-a/"], "team-b": ["team-b/"]}
SIGNED_URL = "https://example.invalid/signed"

INSIDE = "team-a/thermal-spec.pdf"
OUTSIDE = "team-b/thermal-spec.pdf"


def load_module(env: dict[str, str] | None = None) -> Any:
    """Import index.py fresh, since its configuration is read at import time.

    Args:
        env: Environment overrides applied on top of the defaults below.

    Returns:
        The imported module, with `S3ApHelper` already stubbed.
    """
    base = {
        "S3_AP_ALIAS": DEFAULT_ALIAS,
        "GROUP_AP_MAPPING": json.dumps(GROUP_AP_MAPPING),
        "GROUP_PATH_PREFIXES": json.dumps(GROUP_PATH_PREFIXES),
        "MAX_QR_EXPIRY_SECONDS": "300",
        # Every role may share, so the boundary tests are not passing for the wrong
        # reason. The refusal itself is covered separately below.
        "EXTERNAL_SHARE_LINKS_BY_ROLE": json.dumps(
            {"viewer": True, "contributor": True, "storage-admin": True, "auditor": True}
        ),
        "AWS_REGION": "ap-northeast-1",
    }
    base.update(env or {})
    with patch.dict(os.environ, base, clear=False):
        spec = importlib.util.spec_from_file_location("generate_qr_under_test", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules["generate_qr_under_test"] = module
        spec.loader.exec_module(module)

    module.S3ApHelper = MagicMock()
    module.S3ApHelper.return_value.generate_presigned_get_url.return_value = SIGNED_URL
    return module


def call(module: Any, key: str, groups: list[str] | None = None, expires_in: int = 300) -> dict:
    """Invoke the handler as the resolver would, with an attributed caller.

    Args:
        module: The freshly imported handler module.
        key: The object key to share.
        groups: The caller's Cognito groups.
        expires_in: Requested lifetime in seconds.

    Returns:
        The handler's response.
    """
    return module.handler({"key": key, "expiresIn": expires_in, "groups": groups or []}, None)


def signed_alias(module: Any) -> str:
    """The access point the URL was signed against.

    Args:
        module: The freshly imported handler module.

    Returns:
        The alias `S3ApHelper` was constructed with.
    """
    return module.S3ApHelper.call_args.args[0]


def nothing_was_signed(module: Any) -> bool:
    """Whether the handler refused before any URL could exist.

    Args:
        module: The freshly imported handler module.

    Returns:
        True when `S3ApHelper` was never constructed.
    """
    return not module.S3ApHelper.called


class TestTheKeyBoundary:
    def test_a_key_outside_the_boundary_is_refused(self) -> None:
        module = load_module()
        result = call(module, OUTSIDE, groups=["team-a"])
        assert "outside the prefixes" in result["error"]

    def test_nothing_is_signed_when_the_key_is_refused(self) -> None:
        # A URL that exists has already been handed out as far as this test can tell:
        # it is a credential, not a response the handler can take back.
        module = load_module()
        result = call(module, OUTSIDE, groups=["team-a"])
        assert nothing_was_signed(module)
        assert result["presignedUrl"] == ""
        assert result["qrCodeBase64"] == ""

    def test_a_key_inside_the_boundary_is_signed(self) -> None:
        module = load_module()
        result = call(module, INSIDE, groups=["team-a"])
        assert result["error"] is None
        assert result["presignedUrl"] == SIGNED_URL

    def test_a_traversal_segment_is_refused(self) -> None:
        module = load_module()
        result = call(module, "team-a/../team-b/secret.pdf", groups=["team-a"])
        assert "'..' segment" in result["error"]
        assert nothing_was_signed(module)

    def test_an_unconfined_caller_may_share_anything(self) -> None:
        module = load_module(env={"GROUP_PATH_PREFIXES": "{}"})
        result = call(module, OUTSIDE, groups=["team-a"])
        assert result["error"] is None


class TestAccessPointRouting:
    def test_a_mapped_group_signs_against_its_own_access_point(self) -> None:
        # Measured 2026-08-26: a URL signed against an access point pinned to UNIX
        # `root` read a directory at mode 0700 owned by an unrelated uid. Checking the
        # key and then signing as the default identity hands out that reach.
        module = load_module()
        call(module, INSIDE, groups=["team-a"])
        assert signed_alias(module) == TEAM_A_ALIAS

    def test_an_unmapped_caller_signs_against_the_default(self) -> None:
        module = load_module()
        call(module, "anything/file.pdf", groups=["team-c"])
        assert signed_alias(module) == DEFAULT_ALIAS

    def test_an_unconfigured_access_point_is_reported_rather_than_signed(self) -> None:
        module = load_module(env={"S3_AP_ALIAS": "", "GROUP_AP_MAPPING": "{}"})
        result = call(module, "any/file.pdf", groups=["team-c"])
        assert result["error"] == "S3_AP_ALIAS is not configured"
        assert nothing_was_signed(module)


class TestExpiry:
    def test_a_longer_request_is_capped(self) -> None:
        module = load_module(env={"MAX_QR_EXPIRY_SECONDS": "300"})
        result = call(module, INSIDE, groups=["team-a"], expires_in=86400)
        assert result["expiresIn"] == 300
        assert module.S3ApHelper.return_value.generate_presigned_get_url.call_args.args[1] == 300

    def test_a_shorter_request_is_honoured(self) -> None:
        module = load_module()
        result = call(module, INSIDE, groups=["team-a"], expires_in=60)
        assert result["expiresIn"] == 60


class TestRefusalOrder:
    def test_an_external_caller_is_refused_before_the_key_is_considered(self) -> None:
        # Absent means denied, so an unset variable does not hand out bearer URLs.
        module = load_module(env={"EXTERNAL_SHARE_LINKS_BY_ROLE": "{}"})
        result = call(module, INSIDE, groups=["viewer", "external"])
        assert result["error"]
        assert nothing_was_signed(module)

    def test_that_refusal_does_not_depend_on_the_key_being_valid(self) -> None:
        # Which is the point of the order: the denial is the same whether or not the
        # key exists or is inside the boundary, so it confirms nothing about it.
        module = load_module(env={"EXTERNAL_SHARE_LINKS_BY_ROLE": "{}"})
        outside = call(module, OUTSIDE, groups=["viewer", "external"])
        inside = call(module, INSIDE, groups=["viewer", "external"])
        assert outside["error"] == inside["error"]


class TestQrRendering:
    def test_the_url_still_comes_back_without_the_segno_layer(self) -> None:
        # The image is a convenience; the client can render the code itself. Losing the
        # layer should not turn a working share into an error.
        module = load_module()
        with patch.object(module, "generate_qr_png", return_value=b""):
            result = call(module, INSIDE, groups=["team-a"])
        assert result["presignedUrl"] == SIGNED_URL
        assert result["qrCodeBase64"] == ""
        assert result["error"] is None

    def test_the_image_is_base64_of_what_the_renderer_returned(self) -> None:
        module = load_module()
        with patch.object(module, "generate_qr_png", return_value=b"PNGBYTES"):
            result = call(module, INSIDE, groups=["team-a"])
        assert result["qrCodeBase64"] == "UE5HQllURVM="

    def test_the_code_encodes_the_signed_url(self) -> None:
        # Encoding anything else -- the key, an unsigned URL -- would produce a QR code
        # that cannot open the file, and nothing else here would notice.
        module = load_module()
        with patch.object(module, "generate_qr_png", return_value=b"x") as renderer:
            call(module, INSIDE, groups=["team-a"])
        assert renderer.call_args.args[0] == SIGNED_URL
