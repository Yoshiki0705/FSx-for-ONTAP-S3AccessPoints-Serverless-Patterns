"""Tests for the S3 Access Point IAM policy check.

The check exists because a policy that names the access point only in the bucket form
(`arn:aws:s3:::<alias>/*`) is refused for list, get and put alike once a request
resolves the access point by name. The template deploys, the stack reports success, and
every object operation answers AccessDenied.

Two things are asserted here, and the second is the reason this file exists at all.

**That the rule is enforced** -- a template carrying the bucket-form-only policy has to
fail the check.

**That the scanned set follows the tree.** The check used to hold a list of 17
directories and look only for `template-deploy.yaml`. The repository has 52
`template.yaml` and 28 `template-deploy.yaml`, so 35 pattern directories were never
looked at and no SAM source was looked at either -- and the run printed "Scanned 17
templates" with a tick, because a path that did not exist was skipped in silence. A
checker whose coverage can shrink without saying so reports the absence of findings
either way, so the coverage is asserted rather than assumed.

Written against a temporary tree so a violation can be constructed, and so these
tests keep meaning something while the repository itself is clean.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "check_s3ap_iam_patterns.py"

#: A write policy naming the access point in the bucket form only. This is the shape
#: that deploys and then refuses every object operation.
BUCKET_FORM_ONLY = """\
AWSTemplateFormatVersion: '2010-09-09'
Parameters:
  S3AccessPointAlias:
    Type: String
  S3AccessPointName:
    Type: String
    Default: ''
Conditions:
  HasS3AccessPointName: !Not [!Equals [!Ref S3AccessPointName, '']]
Resources:
  DiscoveryRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Statement:
          - Effect: Allow
            Principal: {Service: lambda.amazonaws.com}
            Action: sts:AssumeRole
      Policies:
        - PolicyName: s3ap
          PolicyDocument:
            Statement:
              - Sid: S3AccessPointWrite
                Effect: Allow
                Action:
                  - s3:PutObject
                Resource:
                  - !Sub "arn:aws:s3:::${S3AccessPointAlias}/*"
"""

#: The same policy with both forms, which is what the rule asks for.
BOTH_FORMS = BUCKET_FORM_ONLY.replace(
    """                Resource:
                  - !Sub "arn:aws:s3:::${S3AccessPointAlias}/*"
""",
    """                Resource: !If
                  - HasS3AccessPointName
                  - - !Sub "arn:aws:s3:::${S3AccessPointAlias}/*"
                    - !Sub "arn:aws:s3:${AWS::Region}:${AWS::AccountId}:accesspoint/${S3AccessPointName}/object/*"
                  - - !Sub "arn:aws:s3:::${S3AccessPointAlias}/*"
""",
)


def load_checker() -> Any:
    """Import the checker under a name of its own, so tests can rebind its globals."""
    spec = importlib.util.spec_from_file_location("check_s3ap_iam_under_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_s3ap_iam_under_test"] = module
    spec.loader.exec_module(module)
    return module


def write_pattern(root: Path, rel_dir: str, filename: str, body: str) -> Path:
    """Place a template at `rel_dir/filename` under `root`."""
    path = root / rel_dir / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


def test_bucket_form_only_is_reported() -> None:
    """The rule holds: a bucket-form-only write policy is a finding."""
    checker = load_checker()
    root = Path(__file__).resolve().parents[2]
    tmp = root / ".pytest-tmp-s3ap-iam"
    try:
        template = write_pattern(tmp, "solutions/industry/x", "template.yaml", BUCKET_FORM_ONLY)
        assert checker.check_template(template), "a bucket-form-only policy has to be reported"
    finally:
        for leftover in sorted(tmp.rglob("*"), reverse=True):
            leftover.unlink() if leftover.is_file() else leftover.rmdir()
        tmp.rmdir()


def test_both_forms_is_clean(tmp_path: Path) -> None:
    """The rule does not fire on the shape it asks for."""
    checker = load_checker()
    template = write_pattern(tmp_path, "solutions/industry/x", "template.yaml", BOTH_FORMS)
    assert checker.check_template(template) == []


@pytest.mark.parametrize(
    "rel_dir,filename",
    [
        ("solutions/industry/new-pattern", "template.yaml"),
        ("solutions/industry/new-pattern", "template-deploy.yaml"),
        ("solutions/flexcache/new-pattern", "template.yaml"),
        ("solutions/genai/new-pattern", "template.yaml"),
        ("operations/new-pattern", "template.yaml"),
        ("operations/new-pattern", "template-deploy.yaml"),
    ],
)
def test_discovery_covers_a_newly_added_pattern(tmp_path: Path, rel_dir: str, filename: str) -> None:
    """A pattern added anywhere under the globs is scanned without editing the checker.

    Parameterized over both template families and over `solutions/*/*` and
    `operations/*`, because the previous list covered one family in one subtree.
    """
    checker = load_checker()
    template = write_pattern(tmp_path, rel_dir, filename, BOTH_FORMS)
    assert template in checker.discover_templates(tmp_path)


def test_discovery_finds_both_families_in_one_directory(tmp_path: Path) -> None:
    """A pattern holding both templates contributes both, not whichever came first.

    The two can disagree: `check_template_consistency.py` compares parameter names and
    function logical IDs across the pair, not policy resources, so a bucket-form-only
    policy could sit in the raw variant while the SAM source is correct.
    """
    checker = load_checker()
    sam = write_pattern(tmp_path, "solutions/industry/p", "template.yaml", BOTH_FORMS)
    raw = write_pattern(tmp_path, "solutions/industry/p", "template-deploy.yaml", BUCKET_FORM_ONLY)
    found = checker.discover_templates(tmp_path)
    assert sam in found and raw in found


def test_empty_tree_fails_rather_than_passing_over_nothing(tmp_path: Path, capsys: Any) -> None:
    """Matching no template is a failure, not a clean run.

    This is the condition the hand-kept list produced: every path it named was
    absent from the family it looked for, and the run reported a tick.
    """
    checker = load_checker()
    assert checker.discover_templates(tmp_path) == []

    # main() resolves its root from the module's own location, so the empty case is
    # reached by pointing the globs at a directory that does not exist.
    checker.PATTERN_GLOBS = ("no-such-dir/*/template.yaml",)
    assert checker.main() == 1
    assert "no longer fits the tree" in capsys.readouterr().out


def test_excluded_paths_are_skipped(tmp_path: Path) -> None:
    """An entry in EXCLUDED drops out of the scanned set.

    Empty in the repository; asserted so the escape hatch is known to work before it
    is needed, rather than being reached for during an incident.
    """
    checker = load_checker()
    kept = write_pattern(tmp_path, "solutions/industry/kept", "template.yaml", BOTH_FORMS)
    dropped = write_pattern(tmp_path, "solutions/industry/dropped", "template.yaml", BOTH_FORMS)
    checker.EXCLUDED = frozenset({"solutions/industry/dropped/template.yaml"})
    found = checker.discover_templates(tmp_path)
    assert kept in found and dropped not in found


def test_repository_itself_is_covered_and_clean() -> None:
    """The real tree: every pattern template is scanned, and none is a finding.

    The count is asserted as a floor rather than an exact number, so adding a pattern
    does not fail this test -- but removing the discovery, or narrowing it back to a
    list, does.
    """
    checker = load_checker()
    root = MODULE_PATH.resolve().parents[1]
    templates = checker.discover_templates(root)
    families = {t.name for t in templates}
    assert families == {"template.yaml", "template-deploy.yaml"}, (
        f"both template families have to be scanned; got {families}"
    )
    assert len(templates) >= 80, (
        f"only {len(templates)} templates scanned; the tree held 80 when this was written, "
        "so a smaller number means the globs stopped matching part of it"
    )
    findings = {t.relative_to(root).as_posix(): checker.check_template(t) for t in templates}
    assert not {k: v for k, v in findings.items() if v}
