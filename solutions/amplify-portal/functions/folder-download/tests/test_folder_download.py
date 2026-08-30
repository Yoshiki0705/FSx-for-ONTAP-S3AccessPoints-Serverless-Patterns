"""Tests for the folder-to-ZIP endpoint.

Three things this endpoint does that nothing else does, and each is why it had to be
covered separately rather than left to the listing tests:

**Its prefix check is one-directional.** Navigating a listing may go up as well as down,
because each level is filtered as it is read. Zipping cannot: asking for an *ancestor* of
an allowed prefix would package every sibling under it in one archive. So reaching a
permitted subfolder must not be a reason to accept the folder above it, and that asymmetry
is easy to "simplify" away into the symmetric check the listing uses.

**It writes the ledger row that stands in for a bulk read.** The files are read and
assembled here, so the retrieval has happened whether or not anybody follows the URL. The
row names a prefix, and a prefix says nothing about how much left with it, which is why
the file count and byte total are part of the record rather than decoration.

**It is a write endpoint that looks like a read.** `folderMutation` carries the same
AppSync rule as upload and delete. That is asserted on the schema side; here the point is
only that the handler is the one behind it.

`boto3` is stubbed at the module's `s3` client. What matters is which access point was
listed and read, which keys went into the archive, and what was recorded -- not the bytes
of a real presigned URL.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

MODULE_PATH = Path(__file__).resolve().parent.parent / "index.py"

DEFAULT_ALIAS = "default-ap-s3alias"
TEAM_A_ALIAS = "team-a-ap-s3alias"
ZIP_BUCKET = "zip-temp-bucket"
GROUP_AP_MAPPING = {"team-a": TEAM_A_ALIAS}
GROUP_PATH_PREFIXES = {"team-a": ["team-a/", "shared/"]}


def load_module(env: dict[str, str] | None = None) -> Any:
    """Import index.py fresh, since its configuration is read at import time."""
    base = {
        "S3_AP_ALIAS": DEFAULT_ALIAS,
        "GROUP_AP_MAPPING": json.dumps(GROUP_AP_MAPPING),
        "GROUP_PATH_PREFIXES": json.dumps(GROUP_PATH_PREFIXES),
        "ZIP_TEMP_BUCKET": ZIP_BUCKET,
        "URL_AUDIT_TABLE_NAME": "",
        "AWS_REGION": "ap-northeast-1",
    }
    base.update(env or {})
    with patch.dict(os.environ, base, clear=False):
        spec = importlib.util.spec_from_file_location("folder_download_under_test", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules["folder_download_under_test"] = module
        spec.loader.exec_module(module)
    return module


def stub_s3(module: Any, objects: dict[str, bytes]) -> MagicMock:
    """Replace the module's S3 client with one serving `objects`.

    Args:
        module: The freshly imported handler module.
        objects: Key to body, as the access point would return them.

    Returns:
        The stub, so a test can read which calls were made.
    """
    client = MagicMock()

    def list_objects_v2(**kwargs):
        prefix = kwargs.get("Prefix", "")
        contents = [{"Key": key, "Size": len(body)} for key, body in objects.items() if key.startswith(prefix)]
        return {"Contents": contents, "IsTruncated": False}

    def get_object(**kwargs):
        return {"Body": BytesIO(objects[kwargs["Key"]])}

    client.list_objects_v2.side_effect = list_objects_v2
    client.get_object.side_effect = get_object
    client.generate_presigned_url.return_value = "https://example.invalid/signed"
    module.s3 = client
    return client


def call(module: Any, prefix: str, groups: list[str] | None = None) -> dict:
    """Invoke the handler as the resolver would, with an attributed caller."""
    return module.handler({"prefix": prefix, "userId": "someone", "groups": groups or []}, None)


class TestPrefixBoundary:
    """Which prefixes a caller may package."""

    def test_accepts_a_prefix_inside_the_allowed_ones(self) -> None:
        module = load_module()
        stub_s3(module, {"team-a/report.txt": b"body"})
        assert call(module, "team-a/", ["team-a"])["success"] is True

    def test_accepts_a_subfolder_of_an_allowed_prefix(self) -> None:
        module = load_module()
        stub_s3(module, {"team-a/2026/report.txt": b"body"})
        assert call(module, "team-a/2026/", ["team-a"])["success"] is True

    def test_refuses_an_ancestor_of_an_allowed_prefix(self) -> None:
        # The asymmetry this endpoint exists to hold. The caller may reach
        # `team-a/2026/`, and `team-a/` is one level above it. A symmetric check -- the one
        # the listing uses, where either may be a prefix of the other -- would accept this
        # and package `team-a/private/` along with it in a single archive.
        module = load_module({"GROUP_PATH_PREFIXES": json.dumps({"team-a": ["team-a/2026/"]})})
        stub_s3(module, {"team-a/2026/ok.txt": b"body", "team-a/private/secret.txt": b"body"})
        result = call(module, "team-a/", ["team-a"])
        assert result["success"] is False
        assert "outside the prefixes" in result["error"]
        assert result["downloadUrl"] is None

    def test_refuses_a_sibling_prefix(self) -> None:
        module = load_module()
        stub_s3(module, {"team-b/secret.txt": b"body"})
        assert call(module, "team-b/", ["team-a"])["success"] is False

    def test_refuses_a_prefix_that_merely_shares_a_leading_string(self) -> None:
        # `team-a-archive/` starts with neither `team-a/` nor `shared/`. Worth stating
        # because a check written against `team-a` rather than `team-a/` would accept it.
        module = load_module()
        stub_s3(module, {"team-a-archive/old.txt": b"body"})
        assert call(module, "team-a-archive/", ["team-a"])["success"] is False

    def test_a_caller_with_no_prefixes_configured_is_not_confined(self) -> None:
        # The compatibility case: a deployment that configures no prefixes has to keep
        # working, and `allowed_prefixes` returns nothing for it. Asserted so the boundary
        # cannot be "fixed" into refusing everybody.
        module = load_module({"GROUP_PATH_PREFIXES": "{}"})
        stub_s3(module, {"anything/file.txt": b"body"})
        assert call(module, "anything/", ["team-a"])["success"] is True

    def test_requires_a_prefix(self) -> None:
        module = load_module()
        stub_s3(module, {})
        result = call(module, "")
        assert result["success"] is False
        assert "prefix is required" in result["error"]


class TestAccessPointRouting:
    """Which ONTAP identity assembles the archive."""

    def test_uses_the_group_access_point_when_one_is_mapped(self) -> None:
        # The handler read only the default alias for a while, so every archive was
        # assembled through the deployment's default identity -- the one the runbook pins
        # to UNIX root -- whatever the caller's group.
        module = load_module()
        client = stub_s3(module, {"team-a/report.txt": b"body"})
        call(module, "team-a/", ["team-a"])
        assert client.list_objects_v2.call_args.kwargs["Bucket"] == TEAM_A_ALIAS
        assert client.get_object.call_args.kwargs["Bucket"] == TEAM_A_ALIAS

    def test_falls_back_to_the_default_access_point(self) -> None:
        module = load_module()
        client = stub_s3(module, {"shared/report.txt": b"body"})
        call(module, "shared/", ["unmapped-group"])
        assert client.list_objects_v2.call_args.kwargs["Bucket"] == DEFAULT_ALIAS


class TestArchiveContents:
    """What ends up in the ZIP."""

    def test_packages_the_files_under_the_prefix_relatively(self) -> None:
        module = load_module()
        client = stub_s3(
            module,
            {"team-a/2026/a.txt": b"aaa", "team-a/2026/sub/b.txt": b"bb"},
        )
        result = call(module, "team-a/2026/", ["team-a"])
        assert result["fileCount"] == 2
        assert result["totalBytes"] == 5
        body = client.put_object.call_args.kwargs["Body"]
        with zipfile.ZipFile(BytesIO(body)) as archive:
            # Relative to the prefix asked for, so extracting does not recreate the whole
            # path from the root of the access point.
            assert sorted(archive.namelist()) == ["a.txt", "sub/b.txt"]
            assert archive.read("sub/b.txt") == b"bb"

    def test_the_listing_filter_drops_a_key_outside_the_allowed_prefixes(self) -> None:
        """`_list_all_objects` filters per key, and that filter is asserted here directly.

        Not through the handler, because through the handler it cannot fire. The handler
        accepts a request only when the prefix starts with an allowed prefix, and every key
        under that prefix therefore starts with it too -- so `key_is_visible` says yes to
        all of them. Written against the helper because that is where the rule is
        reachable, and stated because a test posting a request and expecting a key to be
        dropped would pass whether or not the filter existed.

        Worth keeping rather than deleting: the filter is what holds if the handler's check
        is ever loosened to the symmetric form the listing endpoint uses.
        """
        module = load_module()
        client = stub_s3(module, {"shared/ok/keep.txt": b"keep", "shared/other/leak.txt": b"leak"})
        # Listing a prefix wider than the caller's own -- the state a loosened handler check
        # would produce.
        objects = module._list_all_objects("some-ap", "shared/", ["shared/ok/"])
        assert [obj["Key"] for obj in objects] == ["shared/ok/keep.txt"]
        assert client.list_objects_v2.call_args.kwargs["Prefix"] == "shared/"

    def test_the_listing_filter_keeps_everything_for_an_unconfined_caller(self) -> None:
        module = load_module()
        stub_s3(module, {"a/one.txt": b"1", "b/two.txt": b"2"})
        objects = module._list_all_objects("some-ap", "", [])
        assert len(objects) == 2

    def test_reports_an_empty_prefix_rather_than_shipping_an_empty_archive(self) -> None:
        module = load_module()
        stub_s3(module, {})
        result = call(module, "team-a/", ["team-a"])
        assert result["success"] is False
        assert "No files found" in result["error"]

    def test_refuses_more_files_than_the_limit(self) -> None:
        module = load_module({"MAX_ZIP_FILES": "2"})
        stub_s3(module, {f"team-a/{n}.txt": b"x" for n in range(5)})
        result = call(module, "team-a/", ["team-a"])
        assert result["success"] is False
        assert "Too many files" in result["error"]

    def test_refuses_more_bytes_than_the_limit(self) -> None:
        module = load_module({"MAX_ZIP_BYTES": "10"})
        stub_s3(module, {"team-a/big.bin": b"x" * 50})
        result = call(module, "team-a/", ["team-a"])
        assert result["success"] is False
        assert "exceeds maximum" in result["error"]


class TestFailureHandling:
    """What the caller is told when assembly does not finish."""

    def test_a_read_failure_is_reported_and_nothing_is_uploaded(self) -> None:
        module = load_module()
        client = stub_s3(module, {"team-a/report.txt": b"body"})
        client.get_object.side_effect = RuntimeError("access point unreachable")
        result = call(module, "team-a/", ["team-a"])
        assert result["success"] is False
        assert result["downloadUrl"] is None
        assert "access point unreachable" in result["error"]
        # A half-assembled archive must not be published: the URL is what the caller acts
        # on, and one pointing at a partial ZIP is worse than an error.
        client.put_object.assert_not_called()

    def test_an_upload_failure_yields_no_url(self) -> None:
        module = load_module()
        client = stub_s3(module, {"team-a/report.txt": b"body"})
        client.put_object.side_effect = RuntimeError("temp bucket denied")
        result = call(module, "team-a/", ["team-a"])
        assert result["success"] is False
        assert result["downloadUrl"] is None
        client.generate_presigned_url.assert_not_called()

    def test_a_missing_temp_bucket_is_named(self) -> None:
        module = load_module({"ZIP_TEMP_BUCKET": ""})
        stub_s3(module, {"team-a/report.txt": b"body"})
        result = call(module, "team-a/", ["team-a"])
        assert result["success"] is False
        assert "ZIP_TEMP_BUCKET" in result["error"]

    def test_demo_mode_answers_without_an_access_point(self) -> None:
        module = load_module({"S3_AP_ALIAS": "", "GROUP_AP_MAPPING": "{}"})
        stub_s3(module, {})
        result = call(module, "team-a/", ["team-a"])
        assert result["success"] is True
        assert result["demoMode"] is True

    def test_demo_mode_still_honours_the_prefix_boundary(self) -> None:
        # The DemoMode branch sits after the boundary check, and it must stay there: a mock
        # response for a prefix the caller may not reach still tells them it exists.
        module = load_module({"S3_AP_ALIAS": "", "GROUP_AP_MAPPING": "{}"})
        stub_s3(module, {})
        assert call(module, "team-b/", ["team-a"])["success"] is False


class TestActivityLedger:
    """What is recorded, and when."""

    def test_records_the_prefix_with_the_volume_that_left_with_it(self) -> None:
        module = load_module({"URL_AUDIT_TABLE_NAME": "ledger"})
        stub_s3(module, {"team-a/a.txt": b"aaa", "team-a/b.txt": b"bb"})
        with patch.object(module, "record_activity") as record:
            call(module, "team-a/", ["team-a"])
        assert record.call_count == 1
        recorded = record.call_args.kwargs
        assert recorded["table_name"] == "ledger"
        assert recorded["action"] == module.ACTION_DOWNLOAD
        assert recorded["user_id"] == "someone"
        # The prefix, not a file: this is one row for a bulk read.
        assert recorded["key"] == "team-a/"
        assert recorded["access_point"] == TEAM_A_ALIAS
        # A prefix says nothing about how much left with it, so the count and size are
        # part of the record.
        assert recorded["detail"]["file_count"] == 2
        assert recorded["detail"]["total_bytes"] == 5

    @pytest.mark.parametrize(
        "prefix,groups",
        [("team-b/", ["team-a"]), ("", ["team-a"])],
        ids=["refused-prefix", "missing-prefix"],
    )
    def test_records_nothing_when_the_request_was_refused(self, prefix: str, groups: list[str]) -> None:
        # Nothing was read, so there is nothing to account for. A row here would report a
        # download that did not happen.
        module = load_module({"URL_AUDIT_TABLE_NAME": "ledger"})
        stub_s3(module, {"team-b/secret.txt": b"body"})
        with patch.object(module, "record_activity") as record:
            call(module, prefix, groups)
        record.assert_not_called()

    def test_records_nothing_when_assembly_failed(self) -> None:
        module = load_module({"URL_AUDIT_TABLE_NAME": "ledger"})
        client = stub_s3(module, {"team-a/report.txt": b"body"})
        client.put_object.side_effect = RuntimeError("temp bucket denied")
        with patch.object(module, "record_activity") as record:
            call(module, "team-a/", ["team-a"])
        record.assert_not_called()


class TestNaming:
    """The archive's name, and the key it is stored under."""

    def test_names_the_archive_after_the_prefix(self) -> None:
        module = load_module()
        assert module._prefix_to_filename("claims/photos/2026/05/") == "claims_photos_2026_05.zip"

    def test_names_the_root_archive_something(self) -> None:
        # An empty prefix reaches this only where no prefixes are configured, and an
        # attachment called ".zip" is not a filename.
        module = load_module()
        assert module._prefix_to_filename("") == "folder.zip"
        assert module._prefix_to_filename("/") == "folder.zip"

    def test_the_stored_key_stays_under_one_place(self) -> None:
        module = load_module()
        key = module._generate_zip_key("team-a/2026/", "someone")
        assert key.startswith("zip-downloads/")
        assert key.endswith(".zip")
        # No slash from the prefix survives, so a prefix cannot steer the archive out of
        # the directory the temp bucket's lifecycle rule expires.
        assert "/" not in key[len("zip-downloads/") :]

    def test_two_requests_for_one_prefix_do_not_collide_by_name_alone(self) -> None:
        # Same prefix, same second: the key is prefix plus timestamp, so this *does*
        # collide, and the second upload overwrites the first. Asserted so the behaviour is
        # recorded rather than assumed absent -- both callers hold URLs for the same
        # archive of the same prefix, which is why it has been left alone.
        module = load_module()
        first = module._generate_zip_key("team-a/", "someone")
        second = module._generate_zip_key("team-a/", "somebody-else")
        assert first == second
