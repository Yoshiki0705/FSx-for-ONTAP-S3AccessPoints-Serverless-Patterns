"""Tests for the regulated-folder guard on the AI endpoints.

Two ways this fails, and a case for each. It fails open when a regulated key is not
recognised -- a leading slash, mixed case, or the folder appearing below the root. It fails
closed on the wrong file when a substring match catches a name that merely starts with the
same letters, which would refuse `phishing-report.pdf` for holding `phi`.

The last test pins the pattern to the browser copy in `src/utils/regulatedPath.ts`. The two
are separate definitions of one boundary, so an edit to either has to be an edit to both.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from shared.portal_regulated_path import (
    REGULATED_ROOTS,
    is_regulated_path,
    regulated_path_denial_reason,
)


class TestIsRegulatedPath:
    @pytest.mark.parametrize(
        "key",
        [
            "phi/patient-1.txt",
            "dicom/study/image.dcm",
            "pii/export.csv",
            "team/hipaa/audit.pdf",
            "a/b/protected-health/record.json",
            "team/phi-export/notes.txt",
        ],
    )
    def test_regulated(self, key):
        assert is_regulated_path(key) is True

    @pytest.mark.parametrize(
        "key",
        [
            "PHI/patient-1.txt",
            "Team/DICOM/image.dcm",
            "/phi/patient-1.txt",
        ],
    )
    def test_regulated_regardless_of_case_or_leading_slash(self, key):
        """A caller controls the shape of the key, so neither may decide the answer."""
        assert is_regulated_path(key) is True

    @pytest.mark.parametrize(
        "key",
        [
            "reports/phishing-report.pdf",
            "public/philosophy.txt",
            "team/piixel-art.png",
            "contracts/2026/invoice.pdf",
            "",
        ],
    )
    def test_not_regulated(self, key):
        """The segment has to end at a separator, or every `phi` prefix would refuse."""
        assert is_regulated_path(key) is False

    def test_none_is_not_regulated(self):
        """A missing key is refused by the endpoint's own required-argument check."""
        assert is_regulated_path(None) is False


class TestRegulatedPathDenialReason:
    def test_permitted_key_returns_none(self):
        assert regulated_path_denial_reason("contracts/invoice.pdf") is None

    def test_reason_names_the_key_and_the_convention(self):
        reason = regulated_path_denial_reason("phi/patient-1.txt")
        assert reason is not None
        assert "phi/patient-1.txt" in reason
        assert "regulated folder" in reason


def test_pattern_matches_the_browser_copy():
    """One boundary, two languages. An edit to either has to be an edit to both."""
    ts = Path(__file__).resolve().parents[2] / "solutions" / "amplify-portal" / "src" / "utils" / "regulatedPath.ts"
    source = ts.read_text(encoding="utf-8")

    segment = re.search(r"REGULATED_SEGMENT\s*=\s*/(.+?)/;", source)
    assert segment, "REGULATED_SEGMENT not found in regulatedPath.ts"
    # The TS literal escapes the leading slash; the Python pattern does not need to.
    assert segment.group(1).replace("\\/", "/") == r"/(dicom|phi|pii|hipaa|protected-health)[/-]"

    roots = re.search(r"REGULATED_ROOTS\s*=\s*\[(.*?)\]", source, re.S)
    assert roots, "REGULATED_ROOTS not found in regulatedPath.ts"
    assert tuple(re.findall(r'"([^"]+)"', roots.group(1))) == REGULATED_ROOTS


# Every portal endpoint that sends file contents to a managed AI service, and where its
# source lives. The browser hides these paths, so an endpoint missing from this list is not
# visibly broken -- it is only reachable by calling AppSync directly, which is exactly the
# case the guard exists for. Listing them here means the seventh endpoint added later fails
# a test instead of shipping open.
AI_ENDPOINTS = (
    "ask-about-file/index.py",
    "textract/index.py",
    "comprehend-analysis/index.py",
    "detect-labels/index.py",
    "agent-chat/handler.py",
)


@pytest.mark.parametrize("relative", AI_ENDPOINTS)
def test_every_ai_endpoint_consults_the_guard(relative):
    """An endpoint that reads file contents has to ask, not just the browser."""
    functions = Path(__file__).resolve().parents[2] / "solutions" / "amplify-portal" / "functions"
    source = (functions / relative).read_text(encoding="utf-8")

    assert "shared.portal_regulated_path" in source, f"{relative} does not import the guard"
    assert "regulated_path_denial_reason(" in source or "is_regulated_path" in source, (
        f"{relative} imports the guard but never calls it"
    )
