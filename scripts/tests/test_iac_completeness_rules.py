"""Tests for the two drift rules that catch a name the infrastructure never creates.

Both rules exist because of a defect that shipped, and both defects had the same
shape: something in the code named a resource, nothing in the templates created
it, and the result was not an error but an absence.

  - Five AppSync endpoints were guarded on the `storage-admin` Cognito group while
    `defineAuth` declared no groups. A long-lived sandbox had the group, created by
    hand; a fresh deploy did not, and the administrative sections simply were not
    there.
  - Two handlers read environment variables no template set. One was a leftover
    read used nowhere. The other was a second copy of the S3 Object Lock reader,
    reachable through the API, under a role with no S3 permissions — it could only
    fail, and it failed as though a setting were missing.

A rule that has never failed is not yet a rule, so each is tested against the
defect it was written for as well as against the corrected tree.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
ROOT = SCRIPTS.parent


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def drift() -> ModuleType:
    return _load("check_portal_drift")


@pytest.fixture
def portal(drift: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., Path]:
    """A miniature portal tree the rules can be pointed at.

    Built rather than copied so a test states exactly the arrangement it is about,
    and so a fix in the real tree cannot silently satisfy a test meant to fail.
    """

    def build(
        *,
        declared_groups: list[str],
        referenced_groups: list[str],
        reads: str = "",
        env: str = "",
        preamble: str = "",
    ) -> Path:
        (tmp_path / "amplify" / "auth").mkdir(parents=True)
        (tmp_path / "amplify" / "data").mkdir(parents=True)
        (tmp_path / "functions" / "list-files").mkdir(parents=True)

        groups = ", ".join(f'"{g}"' for g in declared_groups)
        (tmp_path / "amplify" / "auth" / "resource.ts").write_text(
            "export const auth = defineAuth({\n" + (f"  groups: [{groups}],\n" if declared_groups else "") + "});\n",
            encoding="utf-8",
        )
        rules = "\n".join(f'    .authorization((allow) => [allow.groups(["{g}"])])' for g in referenced_groups)
        (tmp_path / "amplify" / "data" / "resource.ts").write_text(
            f"const schema = a.schema({{\n{rules}\n}});\n", encoding="utf-8"
        )
        # The rule only considers a function the backend refers to, so the marker
        # has to be present for the read to be examined at all.
        (tmp_path / "amplify" / "backend.ts").write_text(
            'const code = functionCode("functions/list-files");\n'
            + preamble
            + "const fn = new lambda.Function(stack, 'X', {\n"
            "  environment: {\n" + env + "  },\n});\n",
            encoding="utf-8",
        )
        (tmp_path / "functions" / "list-files" / "index.py").write_text("import os\n" + reads, encoding="utf-8")
        monkeypatch.setattr(drift, "PORTAL", tmp_path)
        return tmp_path

    return build


class TestCognitoGroups:
    def test_the_defect_that_shipped_is_a_finding(self, drift: ModuleType, portal: Callable[..., Path]) -> None:
        portal(declared_groups=[], referenced_groups=["storage-admin"])
        findings = drift.check_cognito_groups()
        assert len(findings) == 1
        assert "storage-admin" in findings[0].detail
        # The message has to say what to do; the symptom on its own reads as an
        # unbuilt feature rather than a missing declaration.
        assert "defineAuth" in findings[0].detail

    def test_the_corrected_arrangement_is_quiet(self, drift: ModuleType, portal: Callable[..., Path]) -> None:
        portal(declared_groups=["storage-admin"], referenced_groups=["storage-admin"])
        assert drift.check_cognito_groups() == []

    def test_a_declared_group_no_rule_uses_is_allowed(self, drift: ModuleType, portal: Callable[..., Path]) -> None:
        """Declaring the group first is how one is introduced."""
        portal(declared_groups=["storage-admin", "auditor"], referenced_groups=["storage-admin"])
        assert drift.check_cognito_groups() == []

    def test_every_referenced_group_is_reported(self, drift: ModuleType, portal: Callable[..., Path]) -> None:
        portal(declared_groups=["storage-admin"], referenced_groups=["storage-admin", "auditor"])
        findings = drift.check_cognito_groups()
        assert len(findings) == 1
        assert "auditor" in findings[0].detail

    def test_the_real_tree_agrees(self, drift: ModuleType) -> None:
        """The rule holds for the repository as committed."""
        assert drift.check_cognito_groups() == []


class TestOrphanEnvReads:
    def test_an_empty_fallback_nothing_sets_is_a_finding(self, drift: ModuleType, portal: Callable[..., Path]) -> None:
        portal(
            declared_groups=["storage-admin"],
            referenced_groups=[],
            reads='OUT = os.environ.get("OUTPUT_BUCKET", "")\n',
        )
        findings = drift.check_orphan_env_reads()
        assert len(findings) == 1
        assert "OUTPUT_BUCKET" in findings[0].detail

    def test_a_variable_the_template_sets_is_quiet(self, drift: ModuleType, portal: Callable[..., Path]) -> None:
        portal(
            declared_groups=["storage-admin"],
            referenced_groups=[],
            reads='OUT = os.environ.get("OUTPUT_BUCKET", "")\n',
            env="      OUTPUT_BUCKET: someBucket.bucketName,\n",
        )
        assert drift.check_orphan_env_reads() == []

    def test_a_shorthand_property_counts_as_set(
        self, drift: ModuleType, portal: Callable[..., Path]
    ) -> None:
        """`{ NAME }` sets the variable as much as `{ NAME: value }` does.

        Reading only the colon form reported `AI_METADATA_TABLE_NAME` as provided by
        nothing while `backend.ts` passed it, which points the reader at a missing
        setting when the setting is there.
        """
        portal(
            declared_groups=["storage-admin"],
            referenced_groups=[],
            reads='OUT = os.environ.get("OUTPUT_BUCKET", "")\n',
            env="      OUTPUT_BUCKET,\n",
            preamble='const OUTPUT_BUCKET = process.env.OUTPUT_BUCKET || "";\n',
        )
        assert drift.check_orphan_env_reads() == []

    def test_a_bare_uppercase_line_the_file_never_declares_is_not_set(
        self, drift: ModuleType, portal: Callable[..., Path]
    ) -> None:
        """An array element looks like a shorthand property and is not one.

        Accepting it would suppress the finding rather than raise a false one, so the
        shorthand form counts only for names the file declares as a constant.
        """
        portal(
            declared_groups=["storage-admin"],
            referenced_groups=[],
            reads='OUT = os.environ.get("OUTPUT_BUCKET", "")\n',
            env="      SOMETHING_ELSE: 1,\n",
            preamble="const ARRAY = [\n      OUTPUT_BUCKET,\n];\n",
        )
        findings = drift.check_orphan_env_reads()
        assert len(findings) == 1
        assert "OUTPUT_BUCKET" in findings[0].detail

    @pytest.mark.parametrize(
        "read",
        [
            'MAX = int(os.environ.get("MAX_ZIP_FILES", "500"))',
            'MAX = int(os.environ.get("MAX_ZIP_BYTES", str(500 * 1024 * 1024)))',
            'TTL = int(os.environ.get("PRESIGN_EXPIRES_SECONDS", "3600"))',
        ],
    )
    def test_a_tunable_with_a_working_default_is_quiet(
        self, drift: ModuleType, portal: Callable[..., Path], read: str
    ) -> None:
        """A real default is a decision, not an omission.

        The second case is why the fallback is not detected by matching a quoted
        literal: `str(500 * 1024 * 1024)` is a 500 MB limit, and a pattern that
        only recognises `"..."` reported the ZIP export as switched off.
        """
        portal(declared_groups=["storage-admin"], referenced_groups=[], reads=read + "\n")
        assert drift.check_orphan_env_reads() == []

    def test_a_function_the_backend_never_mentions_is_skipped(
        self, drift: ModuleType, portal: Callable[..., Path], tmp_path: Path
    ) -> None:
        """`office-convert` and `secure-viewer` are checked in but not deployed."""
        portal(
            declared_groups=["storage-admin"],
            referenced_groups=[],
        )
        undeployed = tmp_path / "functions" / "office-convert"
        undeployed.mkdir(parents=True)
        (undeployed / "handler.py").write_text(
            'import os\nTOKENS = os.environ.get("SHARE_TOKENS_TABLE", "")\n', encoding="utf-8"
        )
        assert drift.check_orphan_env_reads() == []

    def test_a_runtime_supplied_variable_is_quiet(self, drift: ModuleType, portal: Callable[..., Path]) -> None:
        portal(
            declared_groups=["storage-admin"],
            referenced_groups=[],
            reads='REGION = os.environ.get("AWS_REGION", "")\n',
        )
        assert drift.check_orphan_env_reads() == []

    def test_the_real_tree_agrees(self, drift: ModuleType) -> None:
        assert drift.check_orphan_env_reads() == []
