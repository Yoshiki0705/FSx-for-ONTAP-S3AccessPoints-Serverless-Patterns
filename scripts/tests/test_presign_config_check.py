"""Tests for the presign-safe S3 client check on the portal's handlers.

The check exists because the portal's upload link had never worked. Two defaults in one
call: `generate_presigned_url` signs with SigV2 unless told otherwise, and under the
default addressing style botocore presigns the global `s3.amazonaws.com` even with a
region configured. S3 answers with 301 PermanentRedirect naming the regional host, and
the signature covers `host`, so the redirect cannot be followed.

Six other portal functions presign as well and every one was already correct, each naming
an explicit regional `endpoint_url` beside `s3v4`. Measured 2026-08-15, that shape and
`addressing_style="virtual"` both return 200 against an Access Point alias. So the rule
accepts either and rejects only the combination that does not work -- which is what the
cases below pin, because a rule that also rejected the six correct modules would have been
removed rather than obeyed.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import check_portal_drift as drift  # noqa: E402

# (module source) -> findings for a handler containing it.
Check = Callable[[str], list["drift.Finding"]]

PRESIGN = 'url = s3.generate_presigned_url("get_object", Params={"Bucket": b, "Key": k})'


@pytest.fixture
def handler(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Check:
    """Point the check at one handler module this test writes.

    Args:
        tmp_path: Directory standing in for the portal root.
        monkeypatch: Used to repoint the module's `PORTAL` at it.

    Returns:
        A callable taking the module source and returning the findings for it.
    """

    def write(source: str) -> list[drift.Finding]:
        target = tmp_path / "functions" / "probe"
        target.mkdir(parents=True, exist_ok=True)
        (target / "index.py").write_text(source, encoding="utf-8")
        monkeypatch.setattr(drift, "PORTAL", tmp_path)
        return drift.check_presign_safe_s3_clients()

    return write


def test_reports_a_bare_client_that_presigns(handler: Check) -> None:
    """The regression: the shape the upload link shipped with."""
    findings = handler(f's3 = boto3.client("s3")\n{PRESIGN}\n')

    assert findings
    assert "SigV4" in findings[0].detail


def test_reports_sigv4_without_an_endpoint_decision(handler: Check) -> None:
    """v4 alone leaves the host global, which is the half-fix that still 301s."""
    findings = handler(f's3 = boto3.client("s3", config=Config(signature_version="s3v4"))\n{PRESIGN}\n')

    assert findings
    assert "301" in findings[0].detail


def test_accepts_an_explicit_regional_endpoint(handler: Check) -> None:
    """What the six already-correct functions do."""
    findings = handler(
        "s3 = boto3.client(\n"
        '    "s3",\n'
        "    region_name=REGION,\n"
        '    endpoint_url=f"https://s3.{REGION}.amazonaws.com",\n'
        '    config=Config(signature_version="s3v4"),\n'
        ")\n"
        f"{PRESIGN}\n"
    )

    assert findings == []


def test_accepts_virtual_addressing(handler: Check) -> None:
    """What the upload link uses after the fix."""
    findings = handler(
        's3 = boto3.client("s3", config=Config(signature_version="s3v4",'
        ' s3={"addressing_style": "virtual"}))\n'
        f"{PRESIGN}\n"
    )

    assert findings == []


def test_ignores_a_client_that_never_presigns(handler: Check) -> None:
    """Most S3 clients in the portal only get, put and copy. The default is fine there."""
    findings = handler('s3 = boto3.client("s3")\ns3.copy_object(Bucket=b, Key=k)\n')

    assert findings == []


def test_says_so_when_it_can_read_nothing(handler: Check, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A reader that finds no handlers reports a clean tree, so it fails instead."""
    monkeypatch.setattr(drift, "PORTAL", tmp_path / "empty")

    findings = drift.check_presign_safe_s3_clients()

    assert findings
    assert "missing" in findings[0].detail
