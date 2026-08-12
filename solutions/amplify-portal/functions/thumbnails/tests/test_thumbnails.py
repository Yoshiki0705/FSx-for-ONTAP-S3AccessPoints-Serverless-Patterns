"""Tests for the batched thumbnail path.

Pillow is real here. The stubs stop at S3, because the parts worth testing are the
decode and what the function refuses to decode -- a mocked renderer would assert that
the code calls itself.

Three groups, in the order they matter.

The boundary. This endpoint takes object keys from the client, so without the same
prefix check the listing applies it would read any key a caller named. The rest of the
portal's guard is tested in functions/list-files; here the question is only whether
this endpoint is behind it.

The cache. A thumbnail keyed on the object alone would keep serving the old picture
after the file changed, so the ETag is in the key, and these tests hold the key fixed
and vary the ETag to prove it.

The refusals. One awkward file in a page of a hundred must not fail the page or the
feature is less reliable than no feature.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

MODULE_PATH = Path(__file__).resolve().parent.parent / "handler.py"

ALIAS = "team-ap-s3alias"
CACHE = "thumbnail-cache-bucket"
# Two tenants on one access point, the arrangement the prefix boundary exists for.
PREFIXES = {"team-a": ["team-a/"], "team-b": ["team-b/"]}


def load_module(env: dict[str, str] | None = None) -> Any:
    """Import handler.py fresh, since its configuration is read at import time."""
    base = {
        "S3_AP_ALIAS": ALIAS,
        "THUMBNAIL_CACHE_BUCKET": CACHE,
        "GROUP_PATH_PREFIXES": json.dumps(PREFIXES),
        "GROUP_AP_MAPPING": "{}",
        "AWS_REGION": "ap-northeast-1",
    }
    base.update(env or {})
    with patch.dict(os.environ, base, clear=False):
        spec = importlib.util.spec_from_file_location("thumbnails_under_test", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules["thumbnails_under_test"] = module
        spec.loader.exec_module(module)
    return module


def an_image(width: int = 800, height: int = 600, fmt: str = "PNG", **save: Any) -> bytes:
    """Bytes of a real image, so the decode under test is a real decode."""
    image = Image.new("RGB", (width, height), (120, 30, 200))
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, **save)
    return buffer.getvalue()


def wire(
    module: Any, *, source: bytes | None = None, cached: bool = False, size: int | None = None, etag: str = "abc123"
) -> tuple[MagicMock, MagicMock]:
    """Stub S3 at both ends: the access point it reads and the bucket it caches in.

    Returns the cache client and the access-point helper so a test can assert on the
    calls each of them received.
    """
    body = source if source is not None else an_image()
    helper = MagicMock()
    helper.head_object.return_value = {
        "ContentLength": size if size is not None else len(body),
        "ETag": f'"{etag}"',
    }
    # A fresh stream per call. One shared BytesIO is exhausted after the first read,
    # which made every key after the first look like "not a readable image" -- and the
    # budget test then passed for the wrong reason.
    helper.get_object.side_effect = lambda key: {"Body": io.BytesIO(body)}
    module.S3ApHelper = MagicMock(return_value=helper)

    cache = MagicMock()
    if cached:
        cache.head_object.return_value = {"ContentLength": 1234}
    else:
        cache.head_object.side_effect = Exception("NoSuchKey")
    cache.generate_presigned_url.return_value = "https://example.com/signed"
    module._s3 = cache
    return cache, helper


def call(module: Any, keys: list[str], groups: list[str] | None = None) -> dict:
    return module.handler({"action": "getThumbnails", "keys": keys, "groups": groups or []}, None)


class TestTheBoundary:
    """The endpoint takes keys from the client, so it has to be behind the same line."""

    def test_a_key_outside_the_callers_prefixes_is_refused(self):
        module = load_module()
        cache, helper = wire(module)

        result = call(module, ["team-b/secret.png"], groups=["team-a"])

        assert result["thumbnails"] == {}
        assert "outside the prefixes" in result["skipped"]["team-b/secret.png"]
        # Refused before any read: naming another tenant's key must not even reach
        # HeadObject, or the refusal still discloses whether the object exists.
        helper.head_object.assert_not_called()

    def test_a_key_inside_the_callers_prefixes_is_served(self):
        module = load_module()
        wire(module, cached=True)

        result = call(module, ["team-a/photo.png"], groups=["team-a"])

        assert result["thumbnails"]["team-a/photo.png"] == "https://example.com/signed"

    def test_a_traversal_segment_is_refused(self):
        module = load_module()
        wire(module)

        result = call(module, ["team-a/../team-b/x.png"], groups=["team-a"])

        assert "'..'" in result["skipped"]["team-a/../team-b/x.png"]

    def test_the_access_point_follows_the_callers_groups(self):
        """A thumbnail must come from the same place the row did.

        The key is inside team-b's prefix on purpose: with a key outside it the
        request is refused before any read, and this assertion would pass without
        the alias having been used for anything.
        """
        module = load_module({"GROUP_AP_MAPPING": json.dumps({"team-b": "other-ap-s3alias"})})
        wire(module, cached=True)

        result = call(module, ["team-b/x.png"], groups=["team-b"])

        assert result["thumbnails"], "the key must be served, or this asserts nothing"
        module.S3ApHelper.assert_called_once_with("other-ap-s3alias")


class TestTheCache:
    def test_a_hit_is_served_without_generating(self):
        module = load_module()
        cache, helper = wire(module, cached=True)

        result = call(module, ["team-a/photo.png"], groups=["team-a"])

        assert result["thumbnails"]
        cache.put_object.assert_not_called()
        helper.get_object.assert_not_called()

    def test_a_miss_generates_and_stores_a_jpeg(self):
        module = load_module()
        cache, _ = wire(module)

        result = call(module, ["team-a/photo.png"], groups=["team-a"])

        assert result["thumbnails"]["team-a/photo.png"] == "https://example.com/signed"
        written = cache.put_object.call_args.kwargs
        assert written["Bucket"] == CACHE
        assert written["ContentType"] == "image/jpeg"
        assert written["Key"].startswith("thumbnails/v1/")
        assert written["Key"].endswith(".jpg")

    def test_the_stored_image_is_a_smaller_jpeg(self):
        module = load_module({"THUMBNAIL_EDGE_PX": "96"})
        cache, _ = wire(module, source=an_image(800, 600))

        call(module, ["team-a/photo.png"], groups=["team-a"])

        stored = Image.open(io.BytesIO(cache.put_object.call_args.kwargs["Body"]))
        assert stored.format == "JPEG"
        assert max(stored.size) == 96
        # Aspect preserved: 800x600 to 96x72, not squashed to a square.
        assert stored.size == (96, 72)

    def test_a_changed_etag_is_a_different_cache_entry(self):
        """Otherwise an edited file keeps showing the picture it used to be."""
        module = load_module()
        cache_one, _ = wire(module, etag="first")
        call(module, ["team-a/photo.png"], groups=["team-a"])
        first = cache_one.put_object.call_args.kwargs["Key"]

        module_two = load_module()
        cache_two, _ = wire(module_two, etag="second")
        call(module_two, ["team-a/photo.png"], groups=["team-a"])
        second = cache_two.put_object.call_args.kwargs["Key"]

        assert first != second

    def test_the_same_key_under_a_different_access_point_is_a_different_entry(self):
        module = load_module({"GROUP_AP_MAPPING": json.dumps({"team-b": "other-ap-s3alias"})})
        cache, _ = wire(module)
        call(module, ["team-b/x.png"], groups=["team-b"])
        other = cache.put_object.call_args.kwargs["Key"]

        # Same key, no group, so the default alias. An unrestricted caller reaches it.
        plain = load_module()
        cache_plain, _ = wire(plain)
        call(plain, ["team-b/x.png"], groups=[])
        default = cache_plain.put_object.call_args.kwargs["Key"]

        assert other != default

    def test_an_object_without_an_etag_is_skipped(self):
        module = load_module()
        _, helper = wire(module)
        helper.head_object.return_value = {"ContentLength": 10, "ETag": ""}

        result = call(module, ["team-a/photo.png"], groups=["team-a"])

        assert "ETag" in result["skipped"]["team-a/photo.png"]


class TestWhatIsNotCarriedOver:
    def test_the_thumbnail_carries_no_exif_from_the_original(self):
        """A phone records where a photo was taken. The list shows the thumbnail to
        everyone who can see the row, so the metadata must not travel with it."""
        exif = Image.Exif()
        exif[0x010F] = "SecretCamera"  # Make
        module = load_module()
        cache, _ = wire(module, source=an_image(fmt="JPEG", exif=exif))

        call(module, ["team-a/photo.jpg"], groups=["team-a"])

        stored = Image.open(io.BytesIO(cache.put_object.call_args.kwargs["Body"]))
        assert "SecretCamera" not in str(dict(stored.getexif()))

    def test_an_exif_rotation_is_applied_to_the_pixels(self):
        """Orientation 6 means the sensor was sideways. Without applying it the
        thumbnail of a portrait photo appears on its side."""
        exif = Image.Exif()
        exif[0x0112] = 6  # rotate 90
        module = load_module({"THUMBNAIL_EDGE_PX": "100"})
        cache, _ = wire(module, source=an_image(800, 400, fmt="JPEG", exif=exif))

        call(module, ["team-a/photo.jpg"], groups=["team-a"])

        stored = Image.open(io.BytesIO(cache.put_object.call_args.kwargs["Body"]))
        # Landscape in, portrait out, because the rotation was honoured.
        assert stored.size[1] > stored.size[0]

    def test_transparency_becomes_opaque_rather_than_failing(self):
        """JPEG has no alpha channel; saving an RGBA image without converting raises."""
        image = Image.new("RGBA", (300, 300), (255, 0, 0, 128))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        module = load_module()
        cache, _ = wire(module, source=buffer.getvalue())

        result = call(module, ["team-a/logo.png"], groups=["team-a"])

        assert result["thumbnails"]
        assert Image.open(io.BytesIO(cache.put_object.call_args.kwargs["Body"])).mode == "RGB"

    def test_a_palette_image_is_converted(self):
        image = Image.new("P", (200, 200))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        module = load_module()
        cache, _ = wire(module, source=buffer.getvalue())

        assert call(module, ["team-a/icon.png"], groups=["team-a"])["thumbnails"]


class TestRefusals:
    """One awkward file must not fail the page."""

    def test_an_unsupported_type_is_skipped_without_a_download(self):
        module = load_module()
        _, helper = wire(module)

        result = call(module, ["team-a/report.pdf"], groups=["team-a"])

        assert result["skipped"]["team-a/report.pdf"] == "unsupported type"
        helper.head_object.assert_not_called()

    def test_a_source_over_the_limit_is_skipped_without_a_download(self):
        module = load_module({"THUMBNAIL_MAX_SOURCE_BYTES": "1000"})
        _, helper = wire(module, size=2000)

        result = call(module, ["team-a/huge.png"], groups=["team-a"])

        assert "larger than" in result["skipped"]["team-a/huge.png"]
        helper.get_object.assert_not_called()

    def test_bytes_that_are_not_an_image_are_skipped(self):
        module = load_module()
        wire(module, source=b"this is not a picture")

        result = call(module, ["team-a/lying.png"], groups=["team-a"])

        assert result["skipped"]["team-a/lying.png"] == "not a readable image"

    def test_an_unreadable_source_is_skipped(self):
        module = load_module()
        _, helper = wire(module)
        helper.head_object.side_effect = Exception("AccessDenied")

        result = call(module, ["team-a/photo.png"], groups=["team-a"])

        assert result["skipped"]["team-a/photo.png"] == "not readable"

    def test_a_failed_cache_write_is_skipped_not_raised(self):
        module = load_module()
        cache, _ = wire(module)
        cache.put_object.side_effect = Exception("AccessDenied")

        result = call(module, ["team-a/photo.png"], groups=["team-a"])

        assert result["skipped"]["team-a/photo.png"] == "cache write failed"

    def test_one_bad_key_does_not_stop_the_others(self):
        module = load_module()
        cache, helper = wire(module, cached=True)

        result = call(module, ["team-a/a.png", "team-a/b.pdf", "team-a/c.png"], groups=["team-a"])

        assert set(result["thumbnails"]) == {"team-a/a.png", "team-a/c.png"}
        assert set(result["skipped"]) == {"team-a/b.pdf"}


class TestBatchLimits:
    def test_a_page_is_one_call(self):
        module = load_module()
        wire(module, cached=True)
        keys = [f"team-a/{index}.png" for index in range(module.MAX_KEYS_PER_CALL)]

        result = call(module, keys, groups=["team-a"])

        assert len(result["thumbnails"]) == module.MAX_KEYS_PER_CALL

    def test_more_keys_than_a_page_is_refused(self):
        module = load_module()
        wire(module, cached=True)
        keys = [f"team-a/{index}.png" for index in range(module.MAX_KEYS_PER_CALL + 1)]

        assert "limit" in call(module, keys, groups=["team-a"])["error"]

    def test_generation_past_the_budget_comes_back_pending(self):
        """A timeout would lose the work already done, so the rest is deferred."""
        module = load_module()
        cache, _ = wire(module)
        keys = [f"team-a/{index}.png" for index in range(module.GENERATE_BUDGET + 3)]

        result = call(module, keys, groups=["team-a"])

        assert len(result["thumbnails"]) == module.GENERATE_BUDGET
        assert len(result["pending"]) == 3
        assert cache.put_object.call_count == module.GENERATE_BUDGET

    def test_cache_hits_are_not_charged_against_the_generation_budget(self):
        module = load_module()
        wire(module, cached=True)
        keys = [f"team-a/{index}.png" for index in range(module.GENERATE_BUDGET + 5)]

        result = call(module, keys, groups=["team-a"])

        assert result["pending"] == []
        assert len(result["thumbnails"]) == len(keys)


class TestRequestShape:
    def test_an_unknown_action_is_reported(self):
        module = load_module()
        assert "Unknown action" in module.handler({"action": "nope"}, None)["error"]

    @pytest.mark.parametrize("keys", [None, [], {}, ""])
    def test_missing_keys_is_reported_as_missing(self, keys):
        module = load_module()
        wire(module)
        result = module.handler({"action": "getThumbnails", "keys": keys, "groups": []}, None)
        assert result["error"] == "keys is required"

    @pytest.mark.parametrize("keys", ["team-a/x.png", 5, {"a": 1}])
    def test_keys_that_are_present_but_not_a_list_are_reported_as_such(self, keys):
        """A single key as a bare string is the likely mistake, and "required" would
        be a misleading thing to tell someone who did supply one."""
        module = load_module()
        wire(module)
        result = module.handler({"action": "getThumbnails", "keys": keys, "groups": []}, None)
        assert result["error"] == "keys must be a list"

    def test_a_non_string_key_is_ignored_rather_than_crashing(self):
        module = load_module()
        wire(module, cached=True)

        result = call(module, [123, "team-a/ok.png"], groups=["team-a"])  # type: ignore[list-item]

        assert set(result["thumbnails"]) == {"team-a/ok.png"}

    def test_an_unconfigured_cache_bucket_is_reported(self):
        module = load_module({"THUMBNAIL_CACHE_BUCKET": ""})
        assert "THUMBNAIL_CACHE_BUCKET" in call(module, ["team-a/x.png"], groups=["team-a"])["error"]

    def test_an_unconfigured_access_point_is_reported(self):
        module = load_module({"S3_AP_ALIAS": ""})
        assert "S3_AP_ALIAS" in call(module, ["team-a/x.png"], groups=["team-a"])["error"]

    def test_the_url_lifetime_is_capped(self):
        module = load_module({"THUMBNAIL_URL_TTL": "99999"})
        assert module.URL_TTL_SECONDS == 3600

    def test_the_response_states_the_url_lifetime(self):
        """The caller needs it to know when to ask again."""
        module = load_module({"THUMBNAIL_URL_TTL": "600"})
        wire(module, cached=True)

        assert call(module, ["team-a/x.png"], groups=["team-a"])["expiresIn"] == 600
