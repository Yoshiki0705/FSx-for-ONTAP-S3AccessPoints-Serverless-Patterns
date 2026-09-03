"""Tests for publishing the portal to Amplify Hosting.

Only the pure parts are exercised: the archive's shape, the app naming, and the
rewrite rule. The Amplify calls have to run against the real service, and asserting
on a mock of them would prove the mock matches the code rather than that the code
matches Amplify.

The archive tests are the ones that earn their place. A zip whose paths are nested
under `dist/` deploys successfully and then serves 404 for every route, so the
failure appears at the far end of a deployment that reported success.
"""

from __future__ import annotations

import importlib.util
import io
import sys
import zipfile
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parent.parent / "portal_deploy_hosting.py"
_spec = importlib.util.spec_from_file_location("portal_deploy_hosting", MODULE_PATH)
assert _spec and _spec.loader
hosting = importlib.util.module_from_spec(_spec)
sys.modules["portal_deploy_hosting"] = hosting
_spec.loader.exec_module(hosting)


@pytest.fixture
def dist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A minimal built bundle standing in for dist/."""
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<html></html>", encoding="utf-8")
    (root / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    monkeypatch.setattr(hosting, "DIST_DIR", root)
    return root


class TestZipDist:
    """Turning dist/ into an archive Amplify can serve."""

    def test_paths_are_relative_to_dist(self, dist: Path) -> None:
        with zipfile.ZipFile(io.BytesIO(hosting.zip_dist())) as archive:
            names = set(archive.namelist())
        assert "index.html" in names
        assert "assets/app.js" in names
        assert not any(name.startswith("dist/") for name in names)

    def test_refuses_a_missing_dist(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(hosting, "DIST_DIR", tmp_path / "absent")
        with pytest.raises(RuntimeError, match="not found"):
            hosting.zip_dist()

    def test_refuses_a_dist_without_index_html(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # An empty or partial dist/ would deploy and serve nothing, which is
        # indistinguishable from a broken build once it is live.
        root = tmp_path / "dist"
        root.mkdir()
        (root / "stray.txt").write_text("x", encoding="utf-8")
        monkeypatch.setattr(hosting, "DIST_DIR", root)
        with pytest.raises(RuntimeError, match="index.html"):
            hosting.zip_dist()

    def test_archive_is_not_empty(self, dist: Path) -> None:
        assert len(hosting.zip_dist()) > 0


class TestAppName:
    """Naming the hosting app after the sandbox it is bound to."""

    def test_derived_from_sandbox(self) -> None:
        assert hosting.app_name("demo") == "fsxn-portal-demo"

    def test_two_sandboxes_get_two_apps(self) -> None:
        # Publishing from a second sandbox must not overwrite the first app's bundle,
        # because the bundle carries a different user pool.
        assert hosting.app_name("demo") != hosting.app_name("yoshiki")


class TestSandboxIdentifier:
    """Reading the sandbox identifier out of a stack name."""

    def test_reads_identifier(self) -> None:
        name = "amplify-fsxns3apamplifyportal-demo-sandbox-753443151c-auth179371D7-ABC"
        assert hosting.sandbox_identifier(name) == "demo"

    @pytest.mark.parametrize("name", ["", "amplify-branch-main"])
    def test_non_sandbox_names_are_reported_not_guessed(self, name: str) -> None:
        assert hosting.sandbox_identifier(name) == "(not a sandbox stack)"


class TestSpaRewrite:
    """The rewrite that makes sub-routes survive a reload."""

    def test_sends_unmatched_routes_to_index_with_a_200(self) -> None:
        (rule,) = hosting.SPA_REWRITE
        assert rule["target"] == "/index.html"
        # 404-200 rather than a plain redirect: the browser has to receive the app at
        # the requested URL, otherwise client-side routing loses the route.
        assert rule["status"] == "404-200"


class TestBranchUrl:
    """Composing the URL a person opens."""

    def test_is_https_on_the_branch_subdomain(self) -> None:
        url = hosting.branch_url({"defaultDomain": "d1234abcd.amplifyapp.com"})
        assert url == f"https://{hosting.BRANCH_NAME}.d1234abcd.amplifyapp.com"

    def test_scheme_is_https_because_sign_in_requires_a_secure_context(self) -> None:
        assert hosting.branch_url({"defaultDomain": "x.amplifyapp.com"}).startswith("https://")
