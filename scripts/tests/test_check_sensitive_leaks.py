"""Tests for the sensitive-string scanner's option handling.

Narrow on purpose. The scanning itself is exercised by running it -- it reads the
tracked tree and the OCR half needs Tesseract -- so what is pinned here is the part
that decided, silently and wrongly, that there was nothing to do.

`--text-only` is not a flag this script has. It selected neither half, so the run
printed "No leaks detected" and exited 0 having scanned nothing. It was used that way
to verify a real leak had been removed, and it reported clean because it had looked at
nothing at all. The leak was in fact removed, which is the part that makes this
failure mode dangerous: the wrong verification agreed with the right answer.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "_check_sensitive_leaks.py"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the scanner with arguments and capture its result."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )


class TestUnknownOptions:
    """An option the script does not know must never report success."""

    @pytest.mark.parametrize(
        "flag",
        [
            "--text-only",  # the one that actually shipped
            "--images-only",
            "--txt",
            "--all",
            "--quiet",
        ],
    )
    def test_refuses_rather_than_scanning_nothing(self, flag: str) -> None:
        result = run(flag)
        assert result.returncode == 2, result.stdout
        assert "unknown option" in result.stderr
        # The wording has to name what was rejected, or the next person retries the
        # same typo.
        assert flag in result.stderr

    def test_does_not_print_a_clean_verdict_when_refusing(self) -> None:
        result = run("--text-only")
        assert "No leaks detected" not in result.stdout
        assert "Total files with leaks" not in result.stdout


class TestTextMode:
    """`--text` runs the text half and says how much it looked at."""

    def test_reports_what_it_scanned(self) -> None:
        result = run("--text")
        assert result.returncode == 0, result.stdout
        # "What a checker looked at is part of its result": a count of zero files
        # would mean the scan silently covered nothing.
        assert "Scanned:" in result.stdout
        scanned = int(next(line for line in result.stdout.splitlines() if line.startswith("Scanned:")).split()[1])
        assert scanned > 100

    def test_does_not_run_the_ocr_half(self) -> None:
        # The point of the mode: the image scan takes minutes and is why the whole
        # check could not go into `make drift`.
        result = run("--text")
        assert "Image Scan" not in result.stdout
