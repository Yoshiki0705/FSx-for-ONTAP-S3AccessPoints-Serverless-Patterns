"""Tests for scripts/check_public_ipv4.py.

The check exists so that no real address has to be written into the repository to
be detected. So the synthetic public addresses below are assembled at runtime:
written as literals, this file would itself be a finding.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_public_ipv4.py"


def _load_module() -> ModuleType:
    """Import the checker by path, since scripts/ is not a package."""
    spec = importlib.util.spec_from_file_location("check_public_ipv4", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mod = _load_module()

# Globally routable, synthetic, and never a literal in this file.
PUBLIC = ".".join(["52", "68", "14", "203"])
PUBLIC_DASHED = PUBLIC.replace(".", "-")


class TestClassification:
    """is_public must reject every range a document is meant to use."""

    @pytest.mark.parametrize(
        "value",
        [
            "10.0.1.23",  # RFC 1918
            "172.16.5.4",  # RFC 1918
            "192.168.0.1",  # RFC 1918
            "127.0.0.1",  # loopback
            "169.254.169.254",  # link-local, instance metadata
            "100.64.0.1",  # shared address space
            "0.0.0.0",  # unspecified
            "192.0.2.10",  # RFC 5737 TEST-NET-1
            "198.51.100.10",  # RFC 5737 TEST-NET-2
            "203.0.113.10",  # RFC 5737 TEST-NET-3
            "1.1.1.1",  # well-known resolver
            "8.8.8.8",  # well-known resolver
            "999.1.1.1",  # not an address
        ],
    )
    def test_non_public_accepted(self, value: str) -> None:
        assert not mod.is_public(value)

    def test_public_rejected(self) -> None:
        assert mod.is_public(PUBLIC)


class TestScanText:
    """scan_text must fire on real-looking content and stay quiet on the rest."""

    def test_dotted_address_found(self) -> None:
        assert mod.scan_text(f"ssh ec2-user@{PUBLIC}\n") == [(1, PUBLIC)]

    def test_ec2_public_dns_found(self) -> None:
        line = f"host ec2-{PUBLIC_DASHED}.ap-northeast-1.compute.amazonaws.com\n"
        assert mod.scan_text(line) == [(1, PUBLIC)]

    def test_version_number_ignored(self) -> None:
        version = ".".join(["2", "8", "5", "201"])
        assert mod.scan_text(f"Install-PackageProvider -MinimumVersion {version}\n") == []

    def test_five_part_run_ignored(self) -> None:
        assert mod.scan_text(f"oid {PUBLIC}.7\n") == []

    def test_exemption_marker(self) -> None:
        assert mod.scan_text(f"{PUBLIC} <!-- {mod.EXEMPTION_MARKER}: example -->\n") == []

    def test_mask_drops_value(self) -> None:
        assert PUBLIC not in mod.mask(PUBLIC)


class TestRepositoryScan:
    """The full scan must reach tracked files and never echo the value."""

    def _repo(self, tmp_path: Path, content: str) -> Path:
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)  # noqa: S603, S607
        (tmp_path / "notes.md").write_text(content, encoding="utf-8")
        subprocess.run(["git", "-C", str(tmp_path), "add", "notes.md"], check=True)  # noqa: S603, S607
        return tmp_path

    def test_leak_fails_and_is_masked(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        root = self._repo(tmp_path, f"endpoint: {PUBLIC}\n")
        assert mod.main(["--root", str(root)]) == 1
        out = capsys.readouterr().out
        assert "notes.md:1" in out
        assert PUBLIC not in out

    def test_clean_tree_passes(self, tmp_path: Path) -> None:
        root = self._repo(tmp_path, "endpoint: 203.0.113.10\n")
        assert mod.main(["--root", str(root)]) == 0

    def test_this_repository_is_clean(self) -> None:
        assert mod.scan_repository(REPO_ROOT) == []
