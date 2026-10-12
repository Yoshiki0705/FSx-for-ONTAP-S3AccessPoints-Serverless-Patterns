"""The offline harness itself: PATH isolation, the aws stub, and repository hygiene.

These tests come first on purpose. If the stub can be bypassed, or if it accepts a
call the botocore model rejects, every later test in this directory proves less than
it appears to.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from lab_testlib import REPO_SRC, SENTINEL, STUBS, Lab, arn, assert_called, substitute_with_echo

OWNER = SENTINEL.OWNER
RECIPIENT = SENTINEL.RECIPIENT
RP_ARN = arn("backup", "ap-northeast-1", OWNER, "recovery-point:abc123")
VAULT_ARN = arn("backup", "ap-northeast-1", OWNER, "backup-vault:lab-lag")
ROLE_ARN = arn("iam", "", OWNER, "role/lab-backup-role")

GLOBALS = ["--profile", "lab-owner", "--region", "ap-northeast-1", "--output", "json"]
GOOD_COPY = [
    *GLOBALS,
    "backup",
    "start-copy-job",
    "--recovery-point-arn",
    RP_ARN,
    "--source-backup-vault-name",
    "lab-standard",
    "--destination-backup-vault-arn",
    VAULT_ARN,
    "--iam-role-arn",
    ROLE_ARN,
    "--lifecycle",
    "DeleteAfterDays=7",
]
COPY_SCENARIO = {"backup start-copy-job": {"body": {"CopyJobId": "job-1"}}}


def _without(argv: list[str], flag: str) -> list[str]:
    """Return argv without ``flag`` and the value that follows it."""
    index = argv.index(flag)
    return argv[:index] + argv[index + 2 :]


def _replace(argv: list[str], old: str, new: str) -> list[str]:
    """Return argv with one token replaced."""
    out = list(argv)
    out[out.index(old)] = new
    return out


# --------------------------------------------------------------------------
# PATH isolation
# --------------------------------------------------------------------------


def test_path_resolves_to_the_stub(lab: Lab) -> None:
    """The first test: the real aws must be unreachable from every lab run."""
    result = lab.bash("command -v aws", library=False)
    assert result.out.strip() == str(STUBS / "aws")
    found = []
    for directory in lab.path().split(os.pathsep):
        candidate = Path(directory) / "aws"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            found.append(str(candidate))
    assert found == [str(STUBS / "aws")], f"another aws is reachable on PATH: {found}"


def test_jq_is_reachable_but_nothing_else_from_its_directory(lab: Lab) -> None:
    result = lab.bash("command -v jq; ls '" + str(lab.jq_dir) + "'", library=False)
    assert result.rc == 0
    assert (lab.jq_dir / "jq").is_symlink()
    assert sorted(p.name for p in lab.jq_dir.iterdir()) == ["jq"]


def test_lab_copy_has_the_repository_layout(lab: Lab) -> None:
    assert lab.root.parent.name == "infrastructure"
    assert (lab.repo / "Makefile").read_text(encoding="utf-8").startswith("portal-demo-user:")
    assert not list(lab.root.rglob("*.local.*"))


def test_harness_environment_is_built_from_scratch(lab: Lab) -> None:
    env = lab.env({}, lab_env=False)
    assert not [k for k in env if k.startswith(("AWS_", "LAB_"))]
    assert env["HOME"] == str(lab.home)


# --------------------------------------------------------------------------
# The stub: each rule has a passing control and a failing case
# --------------------------------------------------------------------------


def test_stub_accepts_a_correct_call_and_records_it(lab: Lab) -> None:
    lab.write_scenario(COPY_SCENARIO)
    proc = lab.stub(*GOOD_COPY)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == {"CopyJobId": "job-1"}
    call = assert_called(
        lab.calls(),
        "backup",
        "start-copy-job",
        {"--source-backup-vault-name": "lab-standard", "--lifecycle": "DeleteAfterDays=7"},
        profile="lab-owner",
        region="ap-northeast-1",
        times=1,
    )
    assert call["stub_rc"] == 0


@pytest.mark.parametrize(
    ("label", "argv", "expected"),
    [
        ("unknown flag", lambda: _replace(GOOD_COPY, "--lifecycle", "--lifecycle-days"), "UNKNOWN FLAG"),
        ("missing required", lambda: _without(GOOD_COPY, "--iam-role-arn"), "MISSING REQUIRED"),
        (
            "bad enum",
            lambda: [*GLOBALS, "backup", "list-copy-jobs", "--by-state", "BOGUS"],
            "BAD ENUM",
        ),
        (
            "unknown subcommand",
            lambda: _replace(GOOD_COPY, "start-copy-job", "start-copy-jobs"),
            "UNKNOWN SUBCOMMAND",
        ),
        ("cli-input-json", lambda: [*GOOD_COPY, "--cli-input-json", "file://x.json"], "REFUSED FLAG"),
        (
            "name pattern",
            lambda: _replace(GOOD_COPY, "lab-standard", "x"),
            "PATTERN",
        ),
        (
            "arn shape (model has no pattern for this member)",
            lambda: _replace(GOOD_COPY, VAULT_ARN, "lab-lag"),
            "NOT AN ARN",
        ),
        (
            "shorthand key",
            lambda: _replace(GOOD_COPY, "DeleteAfterDays=7", "DeleteAfter=7"),
            "UNKNOWN KEY",
        ),
        ("unknown service", lambda: [*GLOBALS, "nosuchservice", "list-things"], "UNKNOWN SERVICE"),
    ],
)
def test_stub_rejects_a_broken_call(lab: Lab, label: str, argv, expected: str) -> None:
    lab.write_scenario({**COPY_SCENARIO, "backup list-copy-jobs": {"body": {}}})
    proc = lab.stub(*argv())
    assert proc.returncode == 97, f"{label}: {proc.stderr}"
    assert expected in proc.stderr
    assert proc.stderr.startswith("stub:")
    assert lab.calls()[-1]["stub_rc"] == 97


def test_a_rejected_call_fails_the_lab_run(lab: Lab) -> None:
    """run()/bash() turn a stub rejection into a test failure instead of a script error."""
    lab.write_scenario({})
    with pytest.raises(pytest.fail.Exception):
        lab.bash("aws_owner backup list-backup-vaults --bogus-flag 1 || true")


def test_stub_default_denies_an_unscripted_call(lab: Lab) -> None:
    lab.write_scenario({})
    proc = lab.stub(*GOOD_COPY)
    assert proc.returncode == 99
    assert "UNSTUBBED call: backup start-copy-job" in proc.stderr
    assert lab.calls()[-1]["stub_rc"] == 99


def test_stub_requires_json_output(lab: Lab) -> None:
    lab.write_scenario(COPY_SCENARIO)
    proc = lab.stub(*_replace(GOOD_COPY, "json", "text"))
    assert proc.returncode == 98
    assert "stub:" in proc.stderr


def test_stub_runs_the_query_with_jmespath(lab: Lab) -> None:
    lab.write_scenario({"backup list-backup-vaults": {"body": {"BackupVaultList": [{"BackupVaultName": "a"}]}}})
    proc = lab.stub(*GLOBALS, "backup", "list-backup-vaults", "--query", "BackupVaultList[].BackupVaultName")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == ["a"]
    bad = lab.stub(*GLOBALS, "backup", "list-backup-vaults", "--query", "BackupVaultList[")
    assert bad.returncode == 97


def test_stub_returns_list_responses_in_order_and_repeats_the_last(lab: Lab) -> None:
    lab.write_scenario(
        {"backup list-backup-vaults": [{"body": {"n": 1}}, {"body": {"n": 2}}, {"rc": 254, "stderr": "boom"}]}
    )
    seen = []
    for _ in range(5):
        proc = lab.stub(*GLOBALS, "backup", "list-backup-vaults")
        seen.append(json.loads(proc.stdout)["n"] if proc.returncode == 0 else proc.returncode)
    assert seen == [1, 2, 254, 254, 254]


def test_stub_picks_the_scenario_entry_with_more_constraints(lab: Lab) -> None:
    lab.write_scenario(
        {
            "sts get-caller-identity": {"body": {"Account": OWNER}},
            "sts get-caller-identity !--profile": {"body": {"Account": RECIPIENT}},
        }
    )
    with_profile = lab.stub(*GLOBALS, "sts", "get-caller-identity")
    without_profile = lab.stub("--output", "json", "sts", "get-caller-identity")
    assert json.loads(with_profile.stdout)["Account"] == OWNER
    assert json.loads(without_profile.stdout)["Account"] == RECIPIENT


def test_stub_accepts_multi_value_list_flags(lab: Lab) -> None:
    lab.write_scenario({"fsx describe-volumes": {"body": {"Volumes": []}}})
    proc = lab.stub(
        *GLOBALS,
        "fsx",
        "describe-volumes",
        "--filters",
        f"Name=file-system-id,Values={SENTINEL.FS}",
        "Name=storage-virtual-machine-id,Values=" + SENTINEL.SVM,
    )
    assert proc.returncode == 0, proc.stderr
    call = lab.calls()[-1]
    assert call["args"]["--filters"][0].startswith("Name=file-system-id")


def test_stub_validates_cloudformation_deploy_against_its_flag_table(lab: Lab) -> None:
    lab.write_scenario({"cloudformation deploy": {"body": {}}})
    good = [
        *GLOBALS,
        "cloudformation",
        "deploy",
        "--template-file",
        "t.yaml",
        "--stack-name",
        "s",
        "--capabilities",
        "CAPABILITY_IAM",
        "--parameter-overrides",
        "A=1",
        "B=2",
        "--tags",
        "Project=x",
        "--no-fail-on-empty-changeset",
    ]
    assert lab.stub(*good).returncode == 0
    assert lab.stub(*good, "--bogus", "1").returncode == 97
    assert lab.stub(*_without(good, "--stack-name")).returncode == 97
    assert lab.stub(*_replace(good, "CAPABILITY_IAM", "CAPABILITY_ANY")).returncode == 97
    assert lab.stub(*_replace(good, "A=1", "A")).returncode == 97


def test_stub_writes_the_lambda_invoke_response_to_the_output_file(lab: Lab) -> None:
    lab.write_scenario({"lambda invoke": {"body": {"statusCode": 200, "ok": True}}})
    outfile = lab.cwd / "out.json"
    proc = lab.stub(
        *GLOBALS,
        "lambda",
        "invoke",
        "--function-name",
        "fn",
        "--cli-binary-format",
        "raw-in-base64-out",
        "--payload",
        "{}",
        str(outfile),
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(outfile.read_text(encoding="utf-8")) == {"statusCode": 200, "ok": True}
    assert json.loads(proc.stdout) == {"StatusCode": 200}
    assert lab.stub(*GLOBALS, "lambda", "invoke", "--function-name", "fn").returncode == 97  # no output file


def test_expected_value_assert_rejects_name_where_id_expected(lab: Lab) -> None:
    """A member without a model pattern is caught only by the value assertion."""
    lab.write_scenario({"fsx describe-volumes": {"body": {"Volumes": []}}})
    # The script under test (wrongly) filtered by the SVM *name*; the model has no
    # pattern for filter values, so the stub accepts it.
    lab.stub(
        *GLOBALS,
        "fsx",
        "describe-volumes",
        "--filters",
        f"Name=storage-virtual-machine-id,Values={SENTINEL.NAME_SVM}",
    )
    calls = lab.calls()
    with pytest.raises(AssertionError):
        assert_called(
            calls,
            "fsx",
            "describe-volumes",
            {"--filters": f"Name=storage-virtual-machine-id,Values={SENTINEL.SVM}"},
        )
    # The same assertion passes for the correct call (control).
    lab.stub(
        *GLOBALS,
        "fsx",
        "describe-volumes",
        "--filters",
        f"Name=storage-virtual-machine-id,Values={SENTINEL.SVM}",
    )
    assert_called(
        lab.calls(),
        "fsx",
        "describe-volumes",
        {"--filters": f"Name=storage-virtual-machine-id,Values={SENTINEL.SVM}"},
    )


def test_assert_called_checks_profile_region_and_count(lab: Lab) -> None:
    lab.write_scenario(COPY_SCENARIO)
    lab.stub(*GOOD_COPY)
    calls = lab.calls()
    assert_called(calls, "backup", "start-copy-job", profile="lab-owner", region="ap-northeast-1", times=1)
    with pytest.raises(AssertionError):
        assert_called(calls, "backup", "start-copy-job", profile="lab-recipient")
    with pytest.raises(AssertionError):
        assert_called(calls, "backup", "start-copy-job", region="ap-northeast-3")
    with pytest.raises(AssertionError):
        assert_called(calls, "backup", "start-copy-job", times=2)


def test_sentinels_are_distinct_and_well_formed() -> None:
    values = [v for v in vars(SENTINEL).values()]
    assert len(values) == len(set(values))
    assert SENTINEL.FS.startswith("fs-") and SENTINEL.SVM.startswith("svm-") and SENTINEL.VOLUME.startswith("fsvol-")


# --------------------------------------------------------------------------
# Repository hygiene
# --------------------------------------------------------------------------


def test_local_files_stay_in_the_lab_root(lab: Lab) -> None:
    """Writing from another directory must not drop files in cwd, HOME or the repo root."""
    result = lab.bash('record_event probe V1 "from a temp cwd"')
    assert result.rc == 0, result.err
    assert (lab.root / "lab-run.local.jsonl").is_file()
    assert list(lab.cwd.iterdir()) == []
    assert list(lab.home.iterdir()) == []
    stray = [p.name for p in lab.repo.iterdir() if p.name not in {"Makefile", "infrastructure"}]
    assert stray == []


def _check_ignored(path: str) -> bool:
    proc = subprocess.run(["git", "-C", str(REPO_SRC), "check-ignore", "-q", path], capture_output=True, check=False)
    return proc.returncode == 0


LAB_REL = "infrastructure/shared-backup-vault-lab"


@pytest.mark.parametrize(
    "relative",
    [
        "lab.local.env",
        "portal.local.env",
        "portal-user.local.env",
        "lab-run.local.jsonl",
        "ui-result.local.json",
        "cloudformation/parameters/owner-base.local.json",
        "docs/screenshots/originals/x.png",
        "docs/screenshots/deeper/originals/y.png",
    ],
)
def test_local_files_are_gitignored(relative: str) -> None:
    assert _check_ignored(f"{LAB_REL}/{relative}"), f"{relative} would be tracked"


@pytest.mark.parametrize(
    "relative",
    [
        "cloudformation/parameters/owner-base.example.json",
        "lab.env.example",
        "scripts/01_preflight.sh",
        "scripts/lib/common.sh",
        "tests/stubs/aws",
    ],
)
def test_committed_files_are_not_gitignored(relative: str) -> None:
    assert not _check_ignored(f"{LAB_REL}/{relative}"), f"{relative} is wrongly ignored"


def test_botocore_pin_matches_installed() -> None:
    """The stub reads the botocore service model; its version must be the pinned one."""
    import botocore

    pins = [
        line.split("==", 1)[1].split("#", 1)[0].strip()
        for line in (REPO_SRC / "requirements-dev.txt").read_text(encoding="utf-8").splitlines()
        if line.startswith("botocore==")
    ]
    assert len(pins) == 1, "requirements-dev.txt must pin botocore exactly once"
    assert botocore.__version__ == pins[0]


# --------------------------------------------------------------------------
# Scripts that only print a call must not pass (synthetic scripts; the real
# scripts are covered by the same two rules when they are added)
# --------------------------------------------------------------------------

VOLUME_ARN = arn("fsx", "ap-northeast-1", OWNER, f"volume/{SENTINEL.FS}/{SENTINEL.VOLUME}")
SYNTHETIC_BACKUP = f"""#!/bin/bash
set -euo pipefail
. "$(dirname "$0")/lib/common.sh"
aws_owner backup start-backup-job --backup-vault-name lab-standard --resource-arn {VOLUME_ARN} \
  --iam-role-arn {ROLE_ARN} --idempotency-token tok-1 --lifecycle DeleteAfterDays=2 >/dev/null
run_external touch "$LAB_ROOT/external-ran"
"""
BACKUP_EXPECTATION = {
    "--backup-vault-name": "lab-standard",
    "--resource-arn": VOLUME_ARN,
    "--lifecycle": "DeleteAfterDays=2",
}


def _run_synthetic(lab: Lab, text: str):
    lab.write_scenario({"backup start-backup-job": {"body": {"BackupJobId": "job-1"}}})
    lab.install_script("90_synthetic.sh", text)
    return lab.run("90_synthetic.sh")


def test_a_real_call_satisfies_the_expectation(lab: Lab) -> None:
    """Control for the two rejection tests below."""
    result = _run_synthetic(lab, SYNTHETIC_BACKUP)
    assert result.rc == 0, result.err
    assert_called(result.calls, "backup", "start-backup-job", BACKUP_EXPECTATION, profile="lab-owner", times=1)
    assert (lab.root / "external-ran").exists()


def test_echo_only_script_is_rejected(lab: Lab) -> None:
    """A script that prints the aws command instead of running it records no call."""
    echo_only = "#!/bin/bash\necho aws backup start-backup-job --backup-vault-name lab-standard\n"
    result = _run_synthetic(lab, echo_only)
    assert result.rc == 0
    assert result.calls == []
    with pytest.raises(AssertionError):
        assert_called(result.calls, "backup", "start-backup-job", BACKUP_EXPECTATION)


def test_echo_substitution_fails_for_aws_and_external_calls(lab: Lab) -> None:
    """Replacing the real call with echo (aws and non-aws) must make the expectation fail."""
    aws_substituted = substitute_with_echo(SYNTHETIC_BACKUP, "aws_owner backup start-backup-job")
    result = _run_synthetic(lab, aws_substituted)
    assert result.rc == 0
    with pytest.raises(AssertionError):
        assert_called(result.calls, "backup", "start-backup-job", BACKUP_EXPECTATION)
    external_substituted = substitute_with_echo(SYNTHETIC_BACKUP, "run_external touch")
    lab.call_log.unlink(missing_ok=True)
    (lab.root / "external-ran").unlink(missing_ok=True)
    result = _run_synthetic(lab, external_substituted)
    assert result.rc == 0
    assert not (lab.root / "external-ran").exists(), "the external command still ran"
    # The aws call is still real in this variant, so only the external expectation is lost.
    assert_called(result.calls, "backup", "start-backup-job", BACKUP_EXPECTATION, times=1)


def test_substitution_requires_the_call_to_be_a_literal() -> None:
    """A call built in a variable cannot be substituted, so it cannot be tested: refuse it."""
    with pytest.raises(AssertionError, match="not found as a literal"):
        substitute_with_echo('svc=backup; aws_owner "$svc" start-backup-job', "aws_owner backup start-backup-job")
