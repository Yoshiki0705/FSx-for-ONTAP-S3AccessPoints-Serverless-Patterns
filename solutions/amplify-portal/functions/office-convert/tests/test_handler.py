"""Tests for the Office-to-PDF preview converter.

This was the one portal function with no tests. What it does is not complicated,
but three of its behaviours are load-bearing and none of them were pinned:

* **The extension allowlist is the gate.** Everything after it hands a file to
  LibreOffice, so a widened `SUPPORTED_EXTENSIONS` widens what gets executed on.
* **A cache hit must not convert.** The cache is what keeps a preview click from
  starting a 60-second subprocess, and a broken hit path degrades silently — the
  preview still appears, just slowly and at cost.
* **A failed cache upload must not fail the request.** The user has a PDF at that
  point; refusing to hand it over because it could not be stored would trade a
  working preview for a bookkeeping problem.

`usedforsecurity=False` on the cache-key hash is also pinned here. It reads as
cosmetic and is not: on a FIPS-enabled build an unqualified `md5()` raises, and the
failure would appear as every preview breaking at once.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

MODULE_PATH = Path(__file__).resolve().parent.parent / "handler.py"

BASE_ENV = {
    "AWS_REGION": "ap-northeast-1",
    "S3_AP_ALIAS": "ap-alias",
    "CACHE_PREFIX": ".cache/previews/",
    "PRESIGN_EXPIRY": "300",
}

NOT_FOUND = ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject")


def load_module(env: dict[str, str], s3: MagicMock):
    """Import handler.py fresh with a stubbed S3 client.

    The module reads its configuration and builds its boto3 client at import time,
    so both have to be in place before the import rather than patched afterwards.
    """
    s3.exceptions.ClientError = ClientError  # must be a real class for `except`
    with patch.dict(os.environ, env, clear=False), patch("boto3.client", return_value=s3):
        spec = importlib.util.spec_from_file_location("office_convert_under_test", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules["office_convert_under_test"] = module
        spec.loader.exec_module(module)
    return module


@pytest.fixture
def s3() -> MagicMock:
    client = MagicMock()
    client.generate_presigned_url.return_value = "https://example.com/signed"
    return client


@pytest.fixture
def cache_miss(s3: MagicMock) -> MagicMock:
    s3.head_object.side_effect = NOT_FOUND
    s3.get_object.return_value = {"Body": MagicMock(read=MagicMock(return_value=b"payload"))}
    return s3


def converting(work_dir: Path, *, produce_pdf: bool = True, returncode: int = 0):
    """A `subprocess.run` stand-in that behaves like the real conversion.

    LibreOffice writes its output beside the input, so the double it replaces has
    to do the same: asserting on the command alone would let a test pass while the
    handler looked for the PDF in the wrong place.
    """

    def run(command, **_kwargs):
        if produce_pdf and returncode == 0:
            source = Path(command[-1])
            source.with_suffix(".pdf").write_bytes(b"%PDF-1.4 fake")
        return MagicMock(returncode=returncode, stderr="boom" if returncode else "")

    return run


class TestInputGate:
    def test_missing_key_is_rejected(self, s3: MagicMock) -> None:
        module = load_module(BASE_ENV, s3)
        assert module.handler({}, None)["error"]
        s3.head_object.assert_not_called()

    def test_missing_alias_is_rejected(self, s3: MagicMock) -> None:
        module = load_module({**BASE_ENV, "S3_AP_ALIAS": ""}, s3)
        assert module.handler({"key": "a.docx"}, None)["error"]
        s3.head_object.assert_not_called()

    @pytest.mark.parametrize("key", ["report.pdf", "notes.txt", "archive.zip", "script.sh", "noext"])
    def test_unsupported_extensions_never_reach_libreoffice(self, s3: MagicMock, key: str) -> None:
        module = load_module(BASE_ENV, s3)
        result = module.handler({"key": key}, None)
        assert result["url"] is None
        assert "Unsupported file type" in result["error"]
        s3.head_object.assert_not_called()
        s3.get_object.assert_not_called()

    def test_double_extension_is_judged_on_the_last_suffix(self, s3: MagicMock) -> None:
        """`payload.docx.exe` must be rejected; the allowlist reads the real suffix."""
        module = load_module(BASE_ENV, s3)
        assert module.handler({"key": "payload.docx.exe"}, None)["url"] is None

    @pytest.mark.parametrize("ext", [".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt", ".odt", ".ods", ".odp"])
    def test_supported_extensions_are_accepted_in_any_case(self, s3: MagicMock, ext: str) -> None:
        module = load_module(BASE_ENV, s3)
        s3.head_object.return_value = {}
        assert module.handler({"key": f"file{ext.upper()}"}, None)["error"] is None


class TestCache:
    def test_a_hit_returns_a_url_without_converting(self, s3: MagicMock) -> None:
        module = load_module(BASE_ENV, s3)
        s3.head_object.return_value = {}
        with patch("subprocess.run") as run:
            result = module.handler({"key": "deck.pptx"}, None)
        run.assert_not_called()
        assert result == {"url": "https://example.com/signed", "cacheHit": True, "error": None}

    def test_the_key_is_stable_and_distinct_per_source(self, s3: MagicMock) -> None:
        module = load_module(BASE_ENV, s3)
        s3.head_object.return_value = {}
        module.handler({"key": "a.docx"}, None)
        module.handler({"key": "a.docx"}, None)
        module.handler({"key": "b.docx"}, None)
        keys = [call.kwargs["Key"] for call in s3.head_object.call_args_list]
        assert keys[0] == keys[1] != keys[2]
        assert all(k.startswith(".cache/previews/") and k.endswith(".pdf") for k in keys)

    def test_the_hash_is_declared_not_for_security(self, s3: MagicMock) -> None:
        """Pins `usedforsecurity=False`: without it every preview fails on FIPS builds."""
        module = load_module(BASE_ENV, s3)
        s3.head_object.return_value = {}
        module.handler({"key": "a.docx"}, None)
        expected = hashlib.md5(b"a.docx", usedforsecurity=False).hexdigest()
        assert s3.head_object.call_args.kwargs["Key"] == f".cache/previews/{expected}.pdf"

    def test_a_miss_converts_uploads_and_reports_the_miss(self, cache_miss: MagicMock, tmp_path: Path) -> None:
        module = load_module(BASE_ENV, cache_miss)
        with (
            patch("tempfile.mkdtemp", return_value=str(tmp_path)),
            patch("subprocess.run", side_effect=converting(tmp_path)),
        ):
            result = module.handler({"key": "sheet.xlsx"}, None)
        assert result["cacheHit"] is False
        assert result["url"] == "https://example.com/signed"
        assert cache_miss.put_object.call_args.kwargs["ContentType"] == "application/pdf"

    def test_a_failed_upload_still_returns_the_preview(self, cache_miss: MagicMock, tmp_path: Path) -> None:
        cache_miss.put_object.side_effect = RuntimeError("no write permission")
        module = load_module(BASE_ENV, cache_miss)
        with (
            patch("tempfile.mkdtemp", return_value=str(tmp_path)),
            patch("subprocess.run", side_effect=converting(tmp_path)),
        ):
            result = module.handler({"key": "sheet.xlsx"}, None)
        assert result["url"] == "https://example.com/signed"
        assert result["error"] is None


class TestConversionFailures:
    def test_download_failure_is_reported(self, s3: MagicMock) -> None:
        s3.head_object.side_effect = NOT_FOUND
        s3.get_object.side_effect = RuntimeError("gone")
        module = load_module(BASE_ENV, s3)
        result = module.handler({"key": "a.docx"}, None)
        assert result["url"] is None
        assert "Failed to download" in result["error"]

    def test_a_nonzero_exit_is_reported(self, cache_miss: MagicMock, tmp_path: Path) -> None:
        module = load_module(BASE_ENV, cache_miss)
        with (
            patch("tempfile.mkdtemp", return_value=str(tmp_path)),
            patch("subprocess.run", side_effect=converting(tmp_path, returncode=1)),
        ):
            result = module.handler({"key": "a.docx"}, None)
        assert result["url"] is None
        assert "Conversion failed" in result["error"]

    def test_a_timeout_is_reported_rather_than_raised(self, cache_miss: MagicMock, tmp_path: Path) -> None:
        module = load_module(BASE_ENV, cache_miss)
        with (
            patch("tempfile.mkdtemp", return_value=str(tmp_path)),
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired("libreoffice", 60)),
        ):
            result = module.handler({"key": "a.docx"}, None)
        assert result["url"] is None
        assert "timed out" in result["error"]

    def test_a_silent_conversion_is_caught(self, cache_miss: MagicMock, tmp_path: Path) -> None:
        """Exit 0 with no PDF written. LibreOffice does this, and it must not 500."""
        module = load_module(BASE_ENV, cache_miss)
        with (
            patch("tempfile.mkdtemp", return_value=str(tmp_path)),
            patch("subprocess.run", side_effect=converting(tmp_path, produce_pdf=False)),
        ):
            result = module.handler({"key": "a.docx"}, None)
        assert result["url"] is None
        assert "PDF output not found" in result["error"]

    def test_libreoffice_is_invoked_headless_with_an_output_directory(
        self, cache_miss: MagicMock, tmp_path: Path
    ) -> None:
        module = load_module(BASE_ENV, cache_miss)
        with (
            patch("tempfile.mkdtemp", return_value=str(tmp_path)),
            patch("subprocess.run", side_effect=converting(tmp_path)) as run,
        ):
            module.handler({"key": "a.docx"}, None)
        command = run.call_args.args[0]
        assert command[0] == "libreoffice"
        assert "--headless" in command
        assert command[command.index("--outdir") + 1] == str(tmp_path)
        assert command[-1].endswith(".docx")
