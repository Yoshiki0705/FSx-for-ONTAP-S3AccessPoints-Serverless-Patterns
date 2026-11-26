"""Input validation for the archive and restore workflows."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from shared.archive_verify import plan as P
from shared.exceptions import InvalidConfiguration, InvalidInput


def _norm(event, ontap=False, name="exec-1"):
    return P.normalize_archive_input(event, execution_name=name, ontap_enabled=ontap)


def test_defaults_are_the_safe_ones():
    plan = _norm({"olderThanDays": 365})
    assert plan.dry_run is True
    assert plan.storage_class == "DEEP_ARCHIVE"
    assert plan.selection == "MTIME"
    assert plan.capture_attributes == "NONE"
    assert plan.run_id == "exec-1"


def test_run_id_from_input_wins_over_execution_name():
    assert _norm({"olderThanDays": 1, "runId": "r-1"}).run_id == "r-1"


@pytest.mark.parametrize("bad", ["", "a b", "a/b", "x" * 65, "a;rm -rf", "é"])
def test_run_id_is_restricted(bad):
    with pytest.raises(InvalidInput):
        P.valid_run_id(bad)


@pytest.mark.parametrize(
    "event",
    [
        {},
        {"olderThanDays": -1},
        {"olderThanDays": "30"},
        {"olderThanDays": True},
        {"olderThanDays": 1, "storageClass": "STANDARD_IA"},
        {"olderThanDays": 1, "selection": "CTIME"},
        {"olderThanDays": 1, "maxFiles": 0},
        {"olderThanDays": 1, "maxFiles": P.MAX_FILES_CEILING + 1},
        {"olderThanDays": 1, "prefix": "../etc"},
        {"olderThanDays": 1, "prefix": "a/../b"},
        {"olderThanDays": 1, "prefix": "/abs"},
        {"olderThanDays": 1, "captureAttributes": "SSH"},
    ],
)
def test_invalid_input_is_rejected(event):
    with pytest.raises(InvalidInput):
        _norm(event)


def test_atime_needs_the_ontap_function():
    with pytest.raises(InvalidConfiguration):
        _norm({"olderThanDays": 1, "selection": "ATIME"})
    assert _norm({"olderThanDays": 1, "selection": "ATIME"}, ontap=True).capture_attributes == "ONTAP_REST"


def test_capture_needs_the_ontap_function():
    with pytest.raises(InvalidConfiguration):
        _norm({"olderThanDays": 1, "captureAttributes": "ONTAP_REST"})


def test_parse_dry_run():
    assert P.parse_dry_run(None) is True
    assert P.parse_dry_run(True) is True
    assert P.parse_dry_run(False) is False
    for bad in ("false", 0, "0", "no"):
        with pytest.raises(InvalidInput):
            P.parse_dry_run(bad)


def test_is_older_than_is_strict():
    now = datetime(2026, 11, 26, tzinfo=timezone.utc)
    assert P.is_older_than(now - timedelta(days=31), 30, now)
    assert not P.is_older_than(now - timedelta(days=30), 30, now)
    assert P.is_older_than("2020-01-01T00:00:00Z", 30, now)
    assert P.is_older_than(datetime(2020, 1, 1), 30, now)  # naive means UTC


def test_etag_equal_ignores_quotes_and_rejects_empty():
    assert P.etag_equal('"abc"', "abc")
    assert not P.etag_equal('"abc"', '"abd"')
    assert not P.etag_equal("", "")
    assert not P.etag_equal(None, "abc")


def test_copy_source_encodes_the_key_only():
    assert P.copy_source("ap-ext-s3alias", "a b/ü+.txt") == "ap-ext-s3alias/a%20b/%C3%BC%2B.txt"


@given(st.text(min_size=1, max_size=40))
def test_metadata_is_ascii_for_any_key(key):
    meta = P.build_metadata(key, '"e"', "2026-01-01T00:00:00+00:00", {"uid": 1, "mode": "644", "gid": None})
    for k, v in meta.items():
        assert k.isascii() and v.isascii()
    assert "source-gid" not in meta
    assert meta["source-uid"] == "1"


def test_content_type_is_always_set():
    assert P.guess_content_type("a.pdf") == "application/pdf"
    assert P.guess_content_type("noext") == "application/octet-stream"
