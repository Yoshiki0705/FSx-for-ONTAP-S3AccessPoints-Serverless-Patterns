"""Tests for the boundary and the guards on every write in functions/list-files.

The boundary first. `GROUP_PATH_PREFIXES` is the multi-tenancy line, and it was
applied to the folder-watch inbox and nowhere else. The endpoints require a session
but the key arrived unchecked, so where per-team prefixes were configured a caller
could rename, trash or restore an object under another team's prefix by naming it,
and mint a presigned PUT into it. Those are the tests that matter most here: a
browser cannot reach another tenant's files through the UI, and none of these
actions is reached through the UI alone.

Then the guards that make the new actions safe to expose at all — refusing to
overwrite silently, refusing folders where a partial copy would leave two half
directories, and confining permanent deletion to the trash so that destroying
something takes two deliberate steps instead of one careless one.

Every case drives `handler` with a payload, the way AppSync does, rather than
calling the private helpers: the guard is only worth anything if it is on the path
a request actually takes.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
from urllib.parse import urlsplit

import pytest

MODULE_PATH = Path(__file__).resolve().parent.parent / "index.py"

ALIAS = "team-ap-s3alias"
# Two tenants sharing one Access Point, which is the arrangement the prefix
# boundary exists for.
PREFIXES = {"team-a": ["team-a/"], "team-b": ["team-b/"]}


def load_module(env: dict[str, str]) -> Any:
    """Import index.py fresh, since its constants are read at import time."""
    with patch.dict(os.environ, env, clear=False):
        spec = importlib.util.spec_from_file_location("list_files_guardrails", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules["list_files_guardrails"] = module
        spec.loader.exec_module(module)
    return module


@pytest.fixture
def portal() -> Any:
    """The handler with a tenant boundary configured and S3 stubbed out.

    `head_object` raises by default, so the destination of a copy is treated as
    absent unless a test says otherwise. That is the ordinary case, and making it
    the default keeps the overwrite tests to the one line that matters.
    """
    module = load_module(
        {
            "S3_AP_ALIAS": ALIAS,
            "GROUP_PATH_PREFIXES": json.dumps(PREFIXES),
            "GROUP_AP_MAPPING": "{}",
        }
    )
    module.s3 = MagicMock()
    module.s3.head_object.side_effect = Exception("NoSuchKey")
    return module


def call(module: Any, action: str, groups: list[str] | None = None, **params: Any) -> dict:
    """Invoke the handler the way the AppSync resolver does.

    Through `handler` rather than the private helpers on purpose: a guard is only
    worth something if it sits on the path a request actually takes, and the
    boundary this file is mostly about was missing from exactly that path.

    Args:
        module: The freshly imported handler module.
        action: The dispatch action name.
        groups: Cognito groups for the caller. Defaults to a single tenant.
        **params: The rest of the payload.

    Returns:
        The handler's response payload.
    """
    return module.handler({"action": action, "groups": groups if groups is not None else ["team-a"], **params}, None)


class TestTenantBoundary:
    """A key outside the caller's prefixes is refused, on every action that takes one."""

    @pytest.mark.parametrize(
        ("action", "params"),
        [
            ("trashFile", {"key": "team-b/secret.txt"}),
            ("renameFile", {"sourceKey": "team-b/a.txt", "destinationKey": "team-b/b.txt"}),
            ("restoreFromTrash", {"trashKey": ".trash/team-b/a.txt"}),
            ("createUploadLink", {"destinationPrefix": "team-b/", "fileName": "x.txt"}),
            ("copyFile", {"sourceKey": "team-b/a.txt", "destinationKey": "team-b/b.txt"}),
            ("moveFile", {"sourceKey": "team-b/a.txt", "destinationKey": "team-b/b.txt"}),
            ("createFolder", {"key": "team-b/new/"}),
            ("deleteFileForever", {"key": ".trash/team-b/a.txt", "acknowledgeIrreversible": True}),
        ],
    )
    def test_another_tenants_key_is_refused(self, portal: Any, action: str, params: dict) -> None:
        result = call(portal, action, **params)

        assert result.get("success") is not True
        assert "outside the prefixes" in result["error"]
        # Nothing was attempted. A guard that refuses after the write is not a guard.
        assert portal.s3.copy_object.call_count == 0
        assert portal.s3.delete_object.call_count == 0
        assert portal.s3.put_object.call_count == 0
        assert portal.s3.generate_presigned_url.call_count == 0

    def test_the_callers_own_prefix_is_allowed(self, portal: Any) -> None:
        result = call(portal, "copyFile", sourceKey="team-a/a.txt", destinationKey="team-a/b.txt")

        assert result["success"] is True
        portal.s3.copy_object.assert_called_once()

    def test_a_move_may_not_leave_the_prefix(self, portal: Any) -> None:
        """Both ends are checked, not just the source."""
        result = call(portal, "moveFile", sourceKey="team-a/a.txt", destinationKey="team-b/a.txt")

        assert result["success"] is False
        assert "destinationKey" in result["error"]
        assert portal.s3.copy_object.call_count == 0

    def test_storage_admin_is_not_restricted(self, portal: Any) -> None:
        result = call(
            portal, "copyFile", groups=["storage-admin"], sourceKey="team-b/a.txt", destinationKey="team-b/b.txt"
        )

        assert result["success"] is True

    def test_no_configured_prefixes_means_no_restriction(self) -> None:
        """The boundary is opt-in; a deployment without it must keep working."""
        module = load_module({"S3_AP_ALIAS": ALIAS, "GROUP_PATH_PREFIXES": "{}", "GROUP_AP_MAPPING": "{}"})
        module.s3 = MagicMock()
        module.s3.head_object.side_effect = Exception("NoSuchKey")

        result = call(module, "copyFile", sourceKey="anywhere/a.txt", destinationKey="anywhere/b.txt")

        assert result["success"] is True

    def test_a_listing_outside_the_boundary_returns_nothing(self, portal: Any) -> None:
        result = call(portal, "listFiles", prefix="team-b/")

        assert result["files"] == []
        assert result["scope"] == "denied"
        assert portal.s3.list_objects_v2.call_count == 0

    def test_the_root_listing_still_works(self, portal: Any) -> None:
        """Otherwise a restricted user cannot navigate to their own folder."""
        portal.s3.list_objects_v2.return_value = {"CommonPrefixes": [{"Prefix": "team-a/"}], "Contents": []}

        result = call(portal, "listFiles", prefix="")

        assert result["scope"] != "denied"
        portal.s3.list_objects_v2.assert_called_once()

    def test_the_restore_target_is_what_is_checked(self, portal: Any) -> None:
        """`.trash/` prefixes every key, so checking the trash key matches nothing."""
        result = call(portal, "restoreFromTrash", trashKey=".trash/team-a/a.txt")

        assert result["success"] is True
        portal.s3.copy_object.assert_called_once()
        assert portal.s3.copy_object.call_args.kwargs["Key"] == "team-a/a.txt"


class TestKeyShape:
    @pytest.mark.parametrize(
        ("key", "because"),
        [
            ("team-a/../team-b/a.txt", "'..' segment"),
            ("/team-a/a.txt", "empty path segment"),
            ("team-a//a.txt", "empty path segment"),
            ("team-a/a\x00.txt", "control characters"),
            ("", "is required"),
        ],
    )
    def test_a_malformed_key_is_refused(self, portal: Any, key: str, because: str) -> None:
        """A `..` segment is refused even though S3 would treat it literally.

        `a/../b` is a key, not a path, and nothing resolves it. That is the reason:
        it means one thing to the prefix comparison and another to a person reading
        it, and no legitimate request in this portal produces one.
        """
        result = call(portal, "trashFile", key=key)

        assert result["success"] is False
        assert because in result["error"]
        assert portal.s3.copy_object.call_count == 0

    def test_an_overlong_key_is_refused_before_s3_sees_it(self, portal: Any) -> None:
        result = call(portal, "trashFile", key="team-a/" + "x" * 1100)

        assert result["success"] is False
        assert "key limit" in result["error"]


class TestOverwrite:
    @pytest.mark.parametrize("action", ["copyFile", "moveFile", "renameFile"])
    def test_an_occupied_destination_is_refused(self, portal: Any, action: str) -> None:
        portal.s3.head_object.side_effect = None  # the destination is there

        result = call(portal, action, sourceKey="team-a/a.txt", destinationKey="team-a/b.txt")

        assert result["success"] is False
        assert "already exists" in result["error"]
        assert portal.s3.copy_object.call_count == 0

    @pytest.mark.parametrize("action", ["copyFile", "moveFile", "renameFile"])
    def test_overwriting_is_possible_when_asked_for(self, portal: Any, action: str) -> None:
        portal.s3.head_object.side_effect = None

        result = call(portal, action, sourceKey="team-a/a.txt", destinationKey="team-a/b.txt", overwrite=True)

        assert result["success"] is True

    def test_restoring_onto_an_existing_file_is_refused(self, portal: Any) -> None:
        """The original came back while the copy sat in the trash."""
        portal.s3.head_object.side_effect = None

        result = call(portal, "restoreFromTrash", trashKey=".trash/team-a/a.txt")

        assert result["success"] is False
        assert "already exists" in result["error"]
        assert portal.s3.copy_object.call_count == 0


class TestFolders:
    @pytest.mark.parametrize(
        ("action", "params"),
        [
            ("copyFile", {"sourceKey": "team-a/dir/", "destinationKey": "team-a/other/"}),
            ("moveFile", {"sourceKey": "team-a/dir/", "destinationKey": "team-a/other/"}),
            ("trashFile", {"key": "team-a/dir/"}),
        ],
    )
    def test_a_folder_is_refused_rather_than_half_handled(self, portal: Any, action: str, params: dict) -> None:
        """One object per call. A prefix would need every object under it, and a run
        that fails halfway leaves the contents split across two places."""
        result = call(portal, action, **params)

        assert result["success"] is False
        assert portal.s3.copy_object.call_count == 0

    def test_creating_a_folder_supplies_the_trailing_separator(self, portal: Any) -> None:
        """S3 has no directories: the trailing "/" is what makes it one."""
        result = call(portal, "createFolder", key="team-a/reports")

        assert result["success"] is True
        assert result["key"] == "team-a/reports/"
        assert portal.s3.put_object.call_args.kwargs["Key"] == "team-a/reports/"

    def test_creating_a_folder_that_exists_is_refused(self, portal: Any) -> None:
        portal.s3.head_object.side_effect = None

        result = call(portal, "createFolder", key="team-a/reports/")

        assert result["success"] is False
        assert "already exists" in result["error"]
        assert portal.s3.put_object.call_count == 0


class TestPermanentDeletion:
    def test_only_the_trash_may_be_purged(self, portal: Any) -> None:
        """Destroying something takes two deliberate steps: trash it, then purge it."""
        result = call(portal, "deleteFileForever", key="team-a/a.txt", acknowledgeIrreversible=True)

        assert result["success"] is False
        assert ".trash/" in result["error"]
        assert portal.s3.delete_object.call_count == 0

    def test_the_consequence_is_stated_and_must_be_acknowledged(self, portal: Any) -> None:
        result = call(portal, "deleteFileForever", key=".trash/team-a/a.txt")

        assert result["success"] is False
        # Naming the consequence is the point of the flag, not the flag itself.
        assert "cannot be undone" in result["error"]
        assert "not versioned" in result["error"]
        assert portal.s3.delete_object.call_count == 0

    def test_an_acknowledged_purge_proceeds(self, portal: Any) -> None:
        result = call(portal, "deleteFileForever", key=".trash/team-a/a.txt", acknowledgeIrreversible=True)

        assert result["success"] is True
        assert portal.s3.delete_object.call_args.kwargs["Key"] == ".trash/team-a/a.txt"

    def test_a_truthy_value_other_than_true_does_not_acknowledge(self, portal: Any) -> None:
        """`"false"` is a truthy string. The flag is identity-checked against True."""
        result = call(portal, "deleteFileForever", key=".trash/team-a/a.txt", acknowledgeIrreversible="false")

        assert result["success"] is False
        assert portal.s3.delete_object.call_count == 0


class TestMoveOrdering:
    def test_the_source_survives_a_failed_copy(self, portal: Any) -> None:
        """Delete after copy, never before: the other order loses the object."""
        portal.s3.copy_object.side_effect = Exception("AccessDenied")

        result = call(portal, "moveFile", sourceKey="team-a/a.txt", destinationKey="team-a/b.txt")

        assert result["success"] is False
        assert portal.s3.delete_object.call_count == 0

    def test_a_copy_leaves_the_source_alone(self, portal: Any) -> None:
        result = call(portal, "copyFile", sourceKey="team-a/a.txt", destinationKey="team-a/b.txt")

        assert result["success"] is True
        assert portal.s3.delete_object.call_count == 0


class TestCopyCeiling:
    """Objects a single CopyObject cannot carry are refused before it is attempted.

    Rename, move, copy, trash and restore are all one `copy_object`, which stops at
    5 GiB. The documented way past it is multipart copy, and on FSx for ONTAP S3
    Access Points that call is listed as supported and answers `NoSuchKey` when
    measured -- so there is no route past the limit here at all.

    Refused with the size and the reason rather than left to S3, whose error arrives
    partway through an operation the reader believed had started.
    """

    OVER = 6 * 1024 * 1024 * 1024
    UNDER = 4 * 1024 * 1024 * 1024

    @staticmethod
    def _sized(portal: Any, size: int, key: str = "team-a/big.bin") -> None:
        """Make exactly `key` exist with `size`, and every other head miss.

        Only that one key: restore refuses a destination that already exists, and it
        checks that before the size, so a stub that answered for both keys tested the
        wrong guard.
        """

        def head(Bucket: str, Key: str) -> dict:  # noqa: N803  (boto3 kwarg names)
            if Key == key:
                return {"ContentLength": size}
            raise Exception("NoSuchKey")

        portal.s3.head_object.side_effect = head

    @pytest.mark.parametrize(
        ("action", "params"),
        [
            ("copyFile", {"sourceKey": "team-a/big.bin", "destinationKey": "team-a/copy.bin"}),
            ("moveFile", {"sourceKey": "team-a/big.bin", "destinationKey": "team-a/moved.bin"}),
            ("renameFile", {"sourceKey": "team-a/big.bin", "destinationKey": "team-a/other.bin"}),
            ("trashFile", {"key": "team-a/big.bin"}),
            ("restoreFromTrash", {"trashKey": ".trash/team-a/big.bin"}),
        ],
    )
    def test_an_oversize_object_is_refused_without_copying(self, portal: Any, action: str, params: dict) -> None:
        # Restore reads the size of the object in the trash; the others read the source.
        sized = params.get("trashKey", "team-a/big.bin")
        self._sized(portal, self.OVER, sized)

        result = call(portal, action, **params)

        assert result["success"] is False
        assert "5 GiB" in result["error"]
        assert "6.0 GiB" in result["error"]
        assert portal.s3.copy_object.call_count == 0

    def test_an_object_within_the_limit_is_copied(self, portal: Any) -> None:
        self._sized(portal, self.UNDER)

        result = call(portal, "copyFile", sourceKey="team-a/big.bin", destinationKey="team-a/copy.bin")

        assert result["success"] is True
        assert portal.s3.copy_object.call_count == 1

    def test_a_size_that_cannot_be_read_does_not_block_the_copy(self, portal: Any) -> None:
        """A denied or failing head is not a refusal: the copy reports the real reason.

        Otherwise the guard would turn every permission problem into a message about
        object size, which is the wrong thing to tell someone.
        """
        portal.s3.head_object.side_effect = Exception("AccessDenied")

        result = call(portal, "copyFile", sourceKey="team-a/a.txt", destinationKey="team-a/b.txt")

        assert result["success"] is True
        assert portal.s3.copy_object.call_count == 1


class TestPresignedUploadUrl:
    """The upload link is signed and addressed the way S3 will accept.

    Not a style preference. The URL this handler hands out is the whole feature, and it
    had never worked: `generate_presigned_url` signs with SigV2 unless told otherwise, and
    under the default addressing style botocore presigns the global `s3.amazonaws.com`
    even with a region set. S3 answers the PUT with 301 PermanentRedirect naming the
    regional host, which the signature cannot follow because it covers `host`.

    Asserted on the real client rather than a mock, because the defect was in how the
    client was constructed -- a mocked `generate_presigned_url` returns whatever the test
    says and proves nothing about it.
    """

    # Credentials and a region have to be present when the module is imported, because
    # that is when the client is built and `boto3.client` resolves credentials for its
    # signer there and then. Patching them around the signing call instead looked right
    # and failed with NoCredentialsError on a machine with no profile -- which is every CI
    # runner. Stand-in values are enough: what these tests assert is the URL's shape.
    ENV = {
        "S3_AP_ALIAS": ALIAS,
        "AWS_ACCESS_KEY_ID": "AKIAIOSFODNN7EXAMPLE",
        "AWS_SECRET_ACCESS_KEY": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "AWS_DEFAULT_REGION": "ap-northeast-1",
        "AWS_REGION": "ap-northeast-1",
    }

    def test_the_client_signs_with_sigv4(self) -> None:
        module = load_module(self.ENV)

        assert module.s3.meta.config.signature_version == "s3v4"

    def test_the_client_addresses_the_bucket_virtually(self) -> None:
        """Which is what puts the region in the host that gets signed."""
        module = load_module(self.ENV)

        assert module.s3.meta.config.s3["addressing_style"] == "virtual"

    def test_the_signed_url_names_a_regional_host(self) -> None:
        """The end of the chain: v4 plus virtual addressing, so no redirect is needed."""
        module = load_module(self.ENV)

        url = module.s3.generate_presigned_url("put_object", Params={"Bucket": ALIAS, "Key": "probe.txt"}, ExpiresIn=60)

        host = urlsplit(url).netloc
        assert host.startswith(f"{ALIAS}.s3.")
        assert host != f"{ALIAS}.s3.amazonaws.com", "the global host is the one S3 redirects"
        assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in url


class TestListingIsFilteredNotOnlyBounded:
    """What a listing shows, as opposed to which prefix it accepts.

    The request-time check refuses a prefix outside the boundary, and that was the
    whole of it. It cannot run at the root: with `prefix == ""` there is nothing to
    compare against, so every top-level name came back unfiltered. A caller confined
    to `team-a/` saw `team-b/` in the listing and was refused on opening it, which
    reads as a cosmetic glitch rather than as the boundary not applying.

    Per-identity access points do not close it either. Measured 2026-08-26 on ONTAP
    9.18.1P3D1: an identity denied a directory's contents still saw the directory's
    name, because listing the parent needs only traversal on the parent.
    """

    @staticmethod
    def _listing(module: Any, folders: list[str], keys: list[str]) -> None:
        module.s3.list_objects_v2.return_value = {
            "CommonPrefixes": [{"Prefix": p} for p in folders],
            "Contents": [
                {"Key": k, "Size": 1, "LastModified": datetime(2026, 8, 26, tzinfo=timezone.utc)} for k in keys
            ],
            "IsTruncated": False,
        }

    def test_the_root_listing_hides_another_tenants_folder(self, portal: Any) -> None:
        self._listing(portal, ["team-a/", "team-b/"], [])

        result = call(portal, "listFiles", prefix="")

        shown = [f["key"] for f in result["files"]]
        assert "team-a/" in shown
        assert "team-b/" not in shown

    def test_the_root_listing_hides_a_file_outside_the_boundary(self, portal: Any) -> None:
        self._listing(portal, [], ["team-a/mine.txt", "loose_at_root.txt", "team-b/theirs.txt"])

        result = call(portal, "listFiles", prefix="")

        shown = [f["key"] for f in result["files"]]
        assert shown == ["team-a/mine.txt"]

    def test_an_ancestor_of_an_allowed_prefix_stays_navigable(self) -> None:
        """Otherwise a caller scoped to a subfolder could never reach it."""
        module = load_module(
            {
                "S3_AP_ALIAS": ALIAS,
                "GROUP_PATH_PREFIXES": json.dumps({"team-a": ["team-a/reports/"]}),
                "GROUP_AP_MAPPING": "{}",
            }
        )
        module.s3 = MagicMock()
        self._listing(module, ["team-a/", "team-b/"], [])

        shown = [f["key"] for f in call(module, "listFiles", prefix="")["files"]]

        assert shown == ["team-a/"]

    def test_an_unrestricted_caller_still_sees_everything(self, portal: Any) -> None:
        """The boundary is opt-in, so a single-tenant deployment must be unaffected."""
        module = load_module({"S3_AP_ALIAS": ALIAS, "GROUP_PATH_PREFIXES": "{}", "GROUP_AP_MAPPING": "{}"})
        module.s3 = MagicMock()
        self._listing(module, ["team-a/", "team-b/"], ["loose_at_root.txt"])

        shown = [f["key"] for f in call(module, "listFiles", prefix="", groups=[])["files"]]

        assert shown == ["team-a/", "team-b/", "loose_at_root.txt"]

    def test_storage_admin_sees_every_folder(self, portal: Any) -> None:
        self._listing(portal, ["team-a/", "team-b/"], [])

        shown = [f["key"] for f in call(portal, "listFiles", prefix="", groups=["storage-admin"])["files"]]

        assert shown == ["team-a/", "team-b/"]

    def test_a_page_emptied_by_filtering_still_reports_more_to_come(self, portal: Any) -> None:
        """The filter runs after S3 counted the page, so an empty page is not the end.

        Collapsing this to "no more results" would hide a scoped caller's own files
        behind a page belonging entirely to another tenant.
        """
        portal.s3.list_objects_v2.return_value = {
            "CommonPrefixes": [{"Prefix": "team-b/"}],
            "Contents": [],
            "IsTruncated": True,
            "NextContinuationToken": "carry-on",
        }

        result = call(portal, "listFiles", prefix="")

        assert result["files"] == []
        assert result["isTruncated"] is True
        assert result["nextContinuationToken"] == "carry-on"
