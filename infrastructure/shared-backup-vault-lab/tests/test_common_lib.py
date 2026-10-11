"""scripts/lib/common.sh: load-time validation, gates, waiting, identity and records.

Every test runs the library under /bin/bash (3.2 on macOS) with the aws stub first on
PATH. Nothing here proves that AWS accepts a call; it proves what the library does
with the answers it is given.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

import pytest
from lab_testlib import BASE_LAB_ENV, SENTINEL, Lab, assert_called

COMMON = Path(__file__).resolve().parents[1] / "scripts" / "lib" / "common.sh"
OWNER = SENTINEL.OWNER
RECIPIENT = SENTINEL.RECIPIENT


# --------------------------------------------------------------------------
# Running the library as a program is refused
# --------------------------------------------------------------------------


def test_common_lib_refuses_to_be_executed(lab: Lab) -> None:
    result = lab.run("lib/common.sh")
    assert result.rc == 2
    assert "library" in result.err


# --------------------------------------------------------------------------
# Load-time validation (a bad value is 2; an empty required one is 78 in 01, else 2)
# --------------------------------------------------------------------------

GOOD_VALUES = {
    "LAB_OWNER_PROFILE": "lab-owner",
    "LAB_RECIPIENT_PROFILE": "lab-recipient",
    "LAB_OWNER_ACCOUNT_ID": "111122223333",
    "LAB_RECIPIENT_ACCOUNT_ID": "444455556666",
    "LAB_PRIMARY_REGION": "ap-northeast-1",
    "LAB_SECOND_REGION": "ap-northeast-3",
    "LAB_TAG": "my-lab-2",
    "LAB_STANDARD_VAULT_NAME": "my-standard_vault",
    "LAB_LAG_VAULT_NAME": "my-lag-vault",
    "LAB_SHARE_NAME": "my-share_1",
    "LAB_OWNER_SUBNET_ID": "subnet-0123456789abcdef0",
    "LAB_OWNER_SECURITY_GROUP_ID": "sg-0123456789abcdef0",
    "LAB_OWNER_THROUGHPUT_MBPS": "256",
    "LAB_OWNER_STORAGE_GIB": "2048",
    "LAB_SVM_NAME": "svm_lab_2",
    "LAB_VOLUME_NAME": "vol_lab_2",
    "LAB_VOLUME_SIZE_MB": "2048",
    "LAB_SOURCE_BACKUP_RETENTION_DAYS": "3",
    "LAB_ALLOW_EXTERNAL_PRINCIPALS": "false",
    "LAB_RECIPIENT_EXISTING_FS_ID": "fs-0123456789abcdef0",
    "LAB_RECIPIENT_SUBNET_ID": "subnet-0123456789abcdef1",
    "LAB_RECIPIENT_SECURITY_GROUP_ID": "sg-0123456789abcdef1",
    "LAB_RECIPIENT_THROUGHPUT_MBPS": "256",
    "LAB_SECOND_RECIPIENT_EXISTING_FS_ID": "fs-0123456789abcdef2",
    "LAB_SECOND_RECIPIENT_SUBNET_ID": "subnet-0123456789abcdef2",
    "LAB_SECOND_RECIPIENT_SECURITY_GROUP_ID": "sg-0123456789abcdef2",
    "LAB_RESTORE_SVM_NAME": "svm_restore_2",
    "LAB_RESTORE_VOLUME_NAME": "vol_restored_2",
    "LAB_RESTORE_JUNCTION_PATH": "/vol_restored_2",
    "LAB_RECIPIENT_SVM_LIMIT": "6",
    "LAB_PORTAL_DIR": "/some/where/portal",
    "LAB_PORTAL_FUNCTION_NAME": "portal-recovery-points",
    "LAB_PORTAL_RESTORE_FUNCTION_NAME": "portal-restore",
    "LAB_PORTAL_SANDBOX_ID": "sandbox-1",
    "LAB_MIN_SSO_MINUTES": "45",
    "LAB_UI_EXPECT": "arn-present",
    "LAB_CAPTURE_DIR": "/some/where/captures",
    "LAB_ENV_FILE": "",
    "PORTAL_URL": "http://localhost:5173",
}

BAD_VALUES = {
    "LAB_OWNER_PROFILE": "-leading-dash",
    "LAB_RECIPIENT_PROFILE": "has space",
    "LAB_OWNER_ACCOUNT_ID": "12345",
    "LAB_RECIPIENT_ACCOUNT_ID": "44445555666x",
    "LAB_PRIMARY_REGION": "Tokyo",
    "LAB_SECOND_REGION": "ap-northeast",
    "LAB_TAG": "A",
    "LAB_STANDARD_VAULT_NAME": "x",
    "LAB_LAG_VAULT_NAME": "has space",
    "LAB_SHARE_NAME": "has space",
    "LAB_OWNER_SUBNET_ID": "subnet-xyz",
    "LAB_OWNER_SECURITY_GROUP_ID": "sg-xyz",
    "LAB_OWNER_THROUGHPUT_MBPS": "fast",
    "LAB_OWNER_STORAGE_GIB": "1k",
    "LAB_SVM_NAME": "bad-name",
    "LAB_VOLUME_NAME": "bad name",
    "LAB_VOLUME_SIZE_MB": "big",
    "LAB_SOURCE_BACKUP_RETENTION_DAYS": "0",
    "LAB_ALLOW_EXTERNAL_PRINCIPALS": "yes",
    "LAB_RECIPIENT_EXISTING_FS_ID": "fs-xyz",
    "LAB_RECIPIENT_SUBNET_ID": "subnet-xyz",
    "LAB_RECIPIENT_SECURITY_GROUP_ID": "sg-xyz",
    "LAB_RECIPIENT_THROUGHPUT_MBPS": "fast",
    "LAB_SECOND_RECIPIENT_EXISTING_FS_ID": "fs-xyz",
    "LAB_SECOND_RECIPIENT_SUBNET_ID": "subnet-xyz",
    "LAB_SECOND_RECIPIENT_SECURITY_GROUP_ID": "sg-xyz",
    "LAB_RESTORE_SVM_NAME": "bad-name",
    "LAB_RESTORE_VOLUME_NAME": "bad name",
    "LAB_RESTORE_JUNCTION_PATH": "no-leading-slash",
    "LAB_RECIPIENT_SVM_LIMIT": "many",
    "LAB_PORTAL_DIR": "bad\tpath",
    "LAB_PORTAL_FUNCTION_NAME": "bad name",
    "LAB_PORTAL_RESTORE_FUNCTION_NAME": "bad name",
    "LAB_PORTAL_SANDBOX_ID": "bad id",
    "LAB_MIN_SSO_MINUTES": "soon",
    "LAB_UI_EXPECT": "sometimes",
    "LAB_CAPTURE_DIR": "bad\tpath",
    "LAB_ENV_FILE": "bad\tpath",
    "PORTAL_URL": "not a url",
}


def _validated_names() -> set[str]:
    """Names the library validates, read from common.sh itself."""
    text = COMMON.read_text(encoding="utf-8")
    return set(re.findall(r"^_lab_validate (\w+) ", text, re.M))


def test_every_validated_variable_has_a_good_and_a_bad_case() -> None:
    """Adding a _lab_validate line without a test case fails here."""
    names = _validated_names()
    assert names == set(BAD_VALUES), sorted(names ^ set(BAD_VALUES))
    assert names == set(GOOD_VALUES), sorted(names ^ set(GOOD_VALUES))


def test_all_good_values_together_load(lab: Lab) -> None:
    good = {k: v for k, v in GOOD_VALUES.items() if v != ""}
    result = lab.bash("echo loaded", env=good)
    assert result.rc == 0, result.err
    assert "loaded" in result.out


@pytest.mark.parametrize("name", sorted(BAD_VALUES))
def test_common_lib_rejects_malformed_lab_vars(lab: Lab, name: str) -> None:
    result = lab.bash("echo not-reached", env={name: BAD_VALUES[name]})
    assert result.rc == 2, result.err
    assert name in result.err
    assert "not-reached" not in result.out


def test_second_region_must_differ_from_primary(lab: Lab) -> None:
    result = lab.bash("echo x", env={"LAB_SECOND_REGION": "ap-northeast-1"})
    assert result.rc == 2
    assert "must differ" in result.err


def test_accounts_must_differ(lab: Lab) -> None:
    result = lab.bash("echo x", env={"LAB_RECIPIENT_ACCOUNT_ID": OWNER})
    assert result.rc == 2


@pytest.mark.parametrize(
    "missing",
    [
        "LAB_OWNER_PROFILE",
        "LAB_RECIPIENT_PROFILE",
        "LAB_OWNER_ACCOUNT_ID",
        "LAB_RECIPIENT_ACCOUNT_ID",
        "LAB_PRIMARY_REGION",
        "LAB_OWNER_SUBNET_ID",
        "LAB_RECIPIENT_SUBNET_ID",
    ],
)
def test_required_variable_empty_is_78_in_preflight_and_2_elsewhere(lab: Lab, missing: str) -> None:
    preflight = lab.bash("echo x", name="01_driver.sh", env={missing: None})
    assert preflight.rc == 78
    assert missing in preflight.err
    other = lab.bash("echo x", name="04_driver.sh", env={missing: None})
    assert other.rc == 2
    assert "01_preflight.sh" in other.err


def test_recipient_subnet_is_not_required_when_an_existing_file_system_is_given(lab: Lab) -> None:
    env = {"LAB_RECIPIENT_SUBNET_ID": None, "LAB_RECIPIENT_EXISTING_FS_ID": "fs-0123456789abcdef0"}
    assert lab.bash("echo ok", env=env).rc == 0


# --------------------------------------------------------------------------
# Env file, derived names, roots
# --------------------------------------------------------------------------


def test_env_file_values_reach_child_processes(lab: Lab) -> None:
    """KEY=value lines without `export` must still be exported to children."""
    (lab.root / "lab.local.env").write_text("LAB_TAG=from-file\nLAB_SVM_NAME=svm_from_file\n", encoding="utf-8")
    result = lab.bash("/bin/bash -c 'echo $LAB_TAG $LAB_SVM_NAME'")
    assert result.out.splitlines()[0] == "from-file svm_from_file"


def test_the_env_file_wins_over_the_shell_environment(lab: Lab) -> None:
    (lab.root / "lab.local.env").write_text("LAB_TAG=from-file\n", encoding="utf-8")
    result = lab.bash("echo $LAB_TAG", env={"LAB_TAG": "from-shell"})
    assert result.out.splitlines()[0] == "from-file"


def test_lab_env_file_can_be_relocated_and_must_exist(lab: Lab) -> None:
    elsewhere = lab.tmp / "elsewhere.env"
    elsewhere.write_text("LAB_TAG=relocated\n", encoding="utf-8")
    ok = lab.bash("echo $LAB_TAG", env={"LAB_ENV_FILE": str(elsewhere)})
    assert ok.out.splitlines()[0] == "relocated"
    missing = lab.bash("echo x", env={"LAB_ENV_FILE": str(lab.tmp / "nope.env")})
    assert missing.rc == 2


def test_derived_names_are_exported(lab: Lab) -> None:
    result = lab.bash(
        "/bin/bash -c 'echo $LAB_STANDARD_VAULT_NAME $LAB_LAG_VAULT_NAME $LAB_SHARE_NAME'",
        env={"LAB_TAG": "tagx"},
    )
    assert result.out.splitlines()[0] == "tagx-standard tagx-lag tagx-lag-share"


def test_default_names_follow_lab_tag(lab: Lab) -> None:
    default = lab.bash("echo $LAB_STANDARD_VAULT_NAME $LAB_LAG_VAULT_NAME $LAB_SHARE_NAME")
    assert default.out.splitlines()[0] == "shared-vault-lab-standard shared-vault-lab-lag shared-vault-lab-lag-share"
    explicit = lab.bash("echo $LAB_LAG_VAULT_NAME", env={"LAB_TAG": "t2x", "LAB_LAG_VAULT_NAME": "keep-this"})
    assert explicit.out.splitlines()[0] == "keep-this"


def test_roots_are_resolved_from_the_library_location(lab: Lab) -> None:
    result = lab.bash("echo $LAB_ROOT; echo $LAB_REPO_ROOT; grep -c '^portal-demo-user:' $LAB_REPO_ROOT/Makefile")
    root, repo, count = result.out.splitlines()[:3]
    assert Path(root).resolve() == lab.root.resolve()
    assert Path(repo).resolve() == lab.repo.resolve()
    assert count == "1"


# --------------------------------------------------------------------------
# now(): the pinned clock warns once
# --------------------------------------------------------------------------


def test_now_uses_utc_iso_format(lab: Lab) -> None:
    result = lab.bash("now")
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", result.out.splitlines()[0])
    assert "pinned" not in result.err


def test_a_pinned_clock_warns_exactly_once(lab: Lab) -> None:
    result = lab.bash('a=$(now); b=$(now); echo "$a $b"', env={"LAB_NOW": "2026-10-11T00:00:00Z"})
    assert result.out.splitlines()[0] == "2026-10-11T00:00:00Z 2026-10-11T00:00:00Z"
    assert result.err.count("clock is pinned") == 1


def test_a_malformed_pinned_clock_is_refused(lab: Lab) -> None:
    result = lab.bash("echo x", env={"LAB_NOW": "yesterday"})
    assert result.rc == 2


def test_lab_now_is_read_only_inside_now() -> None:
    """The test-only variable must not leak into other code paths."""
    code = "\n".join(
        line for line in COMMON.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("#")
    )
    start = code.index("now() {")
    end = code.index("\n}\n", start)
    name = re.compile(r"(?<![A-Za-z_])LAB_NOW(?![A-Za-z_])")
    assert name.search(code[start:end])
    assert not name.search(code[:start] + code[end:])


# --------------------------------------------------------------------------
# require_one
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("document", "rows"),
    [("[]", 0), ("null", 0), ('""', 0), ('["a","b"]', 2), ("[null]", 0), ('[null,"a","b"]', 2)],
)
def test_require_one_aborts_unless_exactly_one(lab: Lab, document: str, rows: int) -> None:
    result = lab.bash(f"require_one thing '{document}'; echo not-reached")
    assert result.rc == 1
    assert f"thing: expected exactly one value (rows={rows})" in result.err
    assert "not-reached" not in result.out


@pytest.mark.parametrize(
    ("document", "value"),
    [('["only"]', "only"), ('"scalar"', "scalar"), ("[7]", "7"), ('[null,"x"]', "x"), ('[{"a":1}]', '{"a":1}')],
)
def test_require_one_prints_the_single_value(lab: Lab, document: str, value: str) -> None:
    result = lab.bash(f"v=$(require_one thing '{document}'); echo \"$v\"")
    assert result.rc == 0, result.err
    assert result.out.splitlines()[0] == value


def test_require_one_rejects_invalid_json(lab: Lab) -> None:
    result = lab.bash("require_one thing 'not json'")
    assert result.rc == 1
    assert "not valid JSON" in result.err


# --------------------------------------------------------------------------
# wait_until (verbatim contract; sleep is the stub)
# --------------------------------------------------------------------------


def test_wait_until_poll_failure_x3(lab: Lab) -> None:
    result = lab.bash(
        """
        poll() { return 255; }
        rc=0; wait_until polling 3600 30 poll || rc=$?
        echo "rc=$rc"
        """
    )
    assert "rc=1" in result.out
    assert "polling: poll failed 3x" in result.err
    assert lab.sleeps() == ["30", "30"]


def test_wait_until_times_out_without_real_sleep(lab: Lab) -> None:
    started = time.monotonic()
    result = lab.bash(
        """
        notyet() { return 1; }
        rc=0; wait_until slow 3600 30 notyet || rc=$?
        echo "rc=$rc"
        """
    )
    assert "rc=1" in result.out
    assert "slow: timeout after 3600s slept" in result.err
    assert time.monotonic() - started < 5
    sleeps = lab.sleeps()
    assert len(sleeps) == 3600 // 30
    assert set(sleeps) == {"30"}


def test_wait_until_resets_failure_count_on_not_yet(lab: Lab) -> None:
    """255, 255, 1, 255, 255, 0 must finish with 0: the 'not yet' resets the count."""
    state = lab.tmp / "poll-state"
    state.write_text("0", encoding="utf-8")
    result = lab.bash(
        f"""
        poll() {{
          local n; n=$(( $(cat "{state}") )); echo $((n + 1)) > "{state}"
          case $n in 0|1|3|4) return 255 ;; 2) return 1 ;; *) return 0 ;; esac
        }}
        rc=0; wait_until resetting 3600 30 poll || rc=$?
        echo "rc=$rc"
        """
    )
    assert "rc=0" in result.out
    assert len(lab.sleeps()) == 5


def test_wait_until_returns_zero_at_once_when_done(lab: Lab) -> None:
    result = lab.bash("done_now() { return 0; }; wait_until quick 60 5 done_now; echo rc=$?")
    assert "rc=0" in result.out
    assert lab.sleeps() == []


# --------------------------------------------------------------------------
# Gates
# --------------------------------------------------------------------------

TOKEN = "copy-7d-shared-vault-lab-lag@ap-northeast-1"
COMMAND = f"./scripts/04_backup_and_copy.sh --retention-days 7 --apply --confirm {TOKEN}"


def _gate_script(setup: str) -> str:
    return f"""
    {setup}
    echo '=== IMPACT ==='
    irreversible_gate '{TOKEN}' '{COMMAND}'
    echo CHANGED
    """


def test_irreversible_gate_plan_mode_exits_10_and_shows_the_command(lab: Lab) -> None:
    result = lab.bash(_gate_script(":"))
    assert result.rc == 10
    assert "PLAN ONLY" in result.out
    assert COMMAND in result.out
    assert "CHANGED" not in result.out


def test_irreversible_gate_apply_without_token_refuses_and_prints_the_expected_token(lab: Lab) -> None:
    result = lab.bash(_gate_script("lab_apply_on"))
    assert result.rc == 1
    assert f"--confirm {TOKEN}" in result.err
    assert "CHANGED" not in result.out


def test_irreversible_gate_wrong_token_refuses(lab: Lab) -> None:
    result = lab.bash(_gate_script("lab_apply_on; lab_confirm_set copy-7d-shared-vault-lab-lag@ap-northeast-3"))
    assert result.rc == 1
    assert "CHANGED" not in result.out


def test_irreversible_gate_correct_token_proceeds(lab: Lab) -> None:
    result = lab.bash(_gate_script(f"lab_apply_on; lab_confirm_set '{TOKEN}'"))
    assert result.rc == 0, result.err
    assert "CHANGED" in result.out


def test_environment_variables_are_not_a_confirmation(lab: Lab) -> None:
    """Exported gate state and a LAB_CONFIRM variable must never act as --apply/--confirm."""
    env = {"_LAB_APPLY": "1", "_LAB_CONFIRM": TOKEN, "LAB_APPLY": "1", "LAB_CONFIRM": TOKEN}
    result = lab.bash(_gate_script(":"), env=env)
    assert result.rc == 10
    assert "CHANGED" not in result.out
    with_apply = lab.bash(_gate_script("lab_apply_on"), env=env)
    assert with_apply.rc == 1


def test_plan_gate_exits_10_without_apply_and_continues_with_it(lab: Lab) -> None:
    plan = lab.bash("plan_gate './scripts/02_deploy.sh --apply'; echo CHANGED")
    assert plan.rc == 10 and "CHANGED" not in plan.out
    applied = lab.bash("lab_apply_on; plan_gate 'x'; echo CHANGED")
    assert applied.rc == 0 and "CHANGED" in applied.out


# --------------------------------------------------------------------------
# run_external
# --------------------------------------------------------------------------


def test_run_external_runs_the_named_command_with_its_arguments(lab: Lab) -> None:
    result = lab.bash("run_external printf '%s|' 'a b' c")
    assert result.out.startswith("a b|c|")


def test_run_external_is_not_for_aws(lab: Lab) -> None:
    result = lab.bash("run_external aws sts get-caller-identity")
    assert result.rc == 2
    assert lab.calls() == []


def test_run_external_propagates_the_exit_code(lab: Lab) -> None:
    result = lab.bash("rc=0; run_external false || rc=$?; echo rc=$rc")
    assert "rc=1" in result.out


# --------------------------------------------------------------------------
# aws_owner / aws_recipient
# --------------------------------------------------------------------------


def test_aws_wrappers_pass_profile_region_and_output_explicitly(lab: Lab) -> None:
    lab.write_scenario({"sts get-caller-identity": {"body": {"Account": OWNER}}})
    lab.bash("aws_owner sts get-caller-identity >/dev/null; aws_recipient sts get-caller-identity >/dev/null")
    calls = lab.calls()
    assert_called(calls, "sts", "get-caller-identity", profile="lab-owner", region="ap-northeast-1", times=1)
    assert_called(calls, "sts", "get-caller-identity", profile="lab-recipient", region="ap-northeast-1", times=1)
    assert all("--output" in c["argv"] for c in calls)


def test_a_call_can_override_the_region_for_one_command_only(lab: Lab) -> None:
    lab.write_scenario({"sts get-caller-identity": {"body": {"Account": OWNER}}})
    lab.bash(
        "_LAB_REGION=us-east-1 aws_owner sts get-caller-identity >/dev/null; "
        "aws_owner sts get-caller-identity >/dev/null"
    )
    assert [c["region"] for c in lab.calls()] == ["us-east-1", "ap-northeast-1"]


def test_lab_region_set_changes_the_default_region(lab: Lab) -> None:
    lab.write_scenario({"sts get-caller-identity": {"body": {"Account": OWNER}}})
    lab.bash("lab_region_set ap-northeast-3; aws_owner sts get-caller-identity >/dev/null")
    assert lab.calls()[0]["region"] == "ap-northeast-3"


# --------------------------------------------------------------------------
# assert_account
# --------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["owner", "recipient"])
def test_assert_account_accepts_the_declared_account(lab: Lab, kind: str) -> None:
    account = OWNER if kind == "owner" else RECIPIENT
    lab.write_scenario({"sts get-caller-identity": {"body": {"Account": account}}})
    result = lab.bash(f"assert_account {kind}; echo ok")
    assert result.rc == 0, result.err


@pytest.mark.parametrize("kind", ["owner", "recipient"])
def test_assert_account_mismatch_blocks_everything_after_it(lab: Lab, kind: str) -> None:
    lab.write_scenario({"sts get-caller-identity": {"body": {"Account": "999999999999"}}})
    result = lab.bash(f"assert_account {kind}; echo CHANGED")
    assert result.rc == 1
    assert "999999999999" in result.err
    assert "CHANGED" not in result.out


def test_assert_account_fails_when_sts_fails(lab: Lab) -> None:
    lab.write_scenario({"sts get-caller-identity": {"rc": 254, "stderr": "expired"}})
    result = lab.bash("assert_account owner; echo CHANGED")
    assert result.rc == 1 and "CHANGED" not in result.out


# --------------------------------------------------------------------------
# portal_env and assert_ambient_account (child processes act as the recipient)
# --------------------------------------------------------------------------

AMBIENT_ENV = {
    "AWS_ACCESS_KEY_ID": "dummy-key-id",
    "AWS_SECRET_ACCESS_KEY": "dummy-secret",
    "AWS_SESSION_TOKEN": "dummy-token",
    "AWS_SECURITY_TOKEN": "dummy-token",
    "AWS_DEFAULT_PROFILE": "someone-else",
    "AWS_PROFILE": "someone-else",
    "AWS_REGION": "eu-west-1",
    "AWS_ROLE_ARN": "arn:aws:iam::111122223333:role/kept",
    "AWS_ENDPOINT_URL": "http://kept.invalid",
}


def test_portal_env_sets_the_recipient_identity_and_drops_static_credentials(lab: Lab) -> None:
    result = lab.bash(
        '( portal_env; env | grep -E "^(AWS_|AMPLIFY_PORTAL_)" | sort ); echo "outer=${AWS_ACCESS_KEY_ID-unset}"',
        env=AMBIENT_ENV,
    )
    lines = dict(line.split("=", 1) for line in result.out.splitlines() if "=" in line)
    assert lines["AWS_PROFILE"] == "lab-recipient"
    assert lines["AWS_REGION"] == "ap-northeast-1"
    assert lines["AWS_DEFAULT_REGION"] == "ap-northeast-1"
    assert lines["AMPLIFY_PORTAL_REGION"] == "ap-northeast-1"
    for gone in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_SECURITY_TOKEN"):
        assert gone not in lines
    assert "AWS_DEFAULT_PROFILE" not in lines
    # Role and endpoint variables are left alone on purpose; assert_ambient_account guards them.
    assert lines["AWS_ROLE_ARN"].endswith("role/kept")
    assert lines["AWS_ENDPOINT_URL"] == "http://kept.invalid"
    # The subshell does not leak into the caller.
    assert "outer=dummy-key-id" in result.out


def test_assert_ambient_account_passes_for_the_recipient_and_calls_without_a_profile_flag(lab: Lab) -> None:
    lab.write_scenario({"sts get-caller-identity !--profile": {"body": {"Account": RECIPIENT}}})
    result = lab.bash("( portal_env; assert_ambient_account; echo inside-ok )", env=AMBIENT_ENV)
    assert result.rc == 0, result.err
    call = lab.calls()[0]
    assert call["profile"] is None
    assert call["env"]["AWS_PROFILE"] == "lab-recipient"
    assert call["env"]["AWS_ACCESS_KEY_ID_set"] is False


def test_assert_ambient_account_aborts_when_the_ambient_account_is_not_the_recipient(lab: Lab) -> None:
    lab.write_scenario({"sts get-caller-identity !--profile": {"body": {"Account": OWNER}}})
    result = lab.bash("( portal_env; assert_ambient_account; echo CHANGED )", env=AMBIENT_ENV)
    assert result.rc == 1
    assert "CHANGED" not in result.out
    assert OWNER in result.err


# --------------------------------------------------------------------------
# require_sso_minutes (new and legacy SSO formats)
# --------------------------------------------------------------------------

NOW = "2026-10-11T00:00:00Z"


def _sso_setup(lab: Lab, profile_block: str, cache_key: str | None, expires: str | None) -> None:
    aws_dir = lab.home / ".aws"
    (aws_dir / "sso" / "cache").mkdir(parents=True)
    (aws_dir / "config").write_text(profile_block, encoding="utf-8")
    if cache_key is not None and expires is not None:
        digest = hashlib.sha1(cache_key.encode("utf-8"), usedforsecurity=False).hexdigest()
        (aws_dir / "sso" / "cache" / f"{digest}.json").write_text(json.dumps({"expiresAt": expires}), encoding="utf-8")


NEW_FORMAT = (
    "[sso-session lab]\nsso_start_url = https://example.invalid/start\nsso_region = ap-northeast-1\n"
    "[profile lab-owner]\nsso_session = lab\nsso_account_id = 111122223333\n"
)
LEGACY_FORMAT = "[profile lab-owner]\nsso_start_url = https://example.invalid/start\nsso_account_id = 111122223333\n"


@pytest.mark.parametrize(
    ("config", "key"),
    [(NEW_FORMAT, "lab"), (LEGACY_FORMAT, "https://example.invalid/start")],
    ids=["sso-session", "legacy-start-url"],
)
def test_sso_minutes_reads_both_formats(lab: Lab, config: str, key: str) -> None:
    _sso_setup(lab, config, key, "2026-10-11T00:45:00Z")
    ok = lab.bash("require_sso_minutes lab-owner 30; echo continued", env={"LAB_NOW": NOW})
    assert ok.rc == 0, ok.err
    assert "45 minutes left" in ok.out and "continued" in ok.out


@pytest.mark.parametrize(
    ("config", "key"),
    [(NEW_FORMAT, "lab"), (LEGACY_FORMAT, "https://example.invalid/start")],
    ids=["sso-session", "legacy-start-url"],
)
def test_sso_minutes_below_the_minimum_stops_before_any_change(lab: Lab, config: str, key: str) -> None:
    _sso_setup(lab, config, key, "2026-10-11T00:20:00Z")
    result = lab.bash("require_sso_minutes lab-owner 30; echo CHANGED", env={"LAB_NOW": NOW})
    assert result.rc == 1
    assert "20 minutes left" in result.out
    assert "CHANGED" not in result.out


def test_sso_minutes_skips_profiles_that_are_not_sso(lab: Lab) -> None:
    _sso_setup(lab, "[profile lab-owner]\nregion = ap-northeast-1\n", None, None)
    result = lab.bash("require_sso_minutes lab-owner 30; echo continued", env={"LAB_NOW": NOW})
    assert result.rc == 0 and "not an SSO profile" in result.out and "continued" in result.out


def test_sso_minutes_unreadable_cache_warns_and_continues(lab: Lab) -> None:
    _sso_setup(lab, NEW_FORMAT, None, None)
    result = lab.bash("require_sso_minutes lab-owner 30; echo continued", env={"LAB_NOW": NOW})
    assert result.rc == 0
    assert "could not be checked" in result.out and "continued" in result.out


# --------------------------------------------------------------------------
# check_* , summary, record_event, the EXIT trap
# --------------------------------------------------------------------------


def test_checks_are_counted_and_recorded_with_their_item_and_mode(lab: Lab) -> None:
    result = lab.bash(
        """
        check_pass V1 "vault is shared"
        check_fail E3 "unexpected"
        check_warn - "free text"
        summary || echo "summary-failed"
        """
    )
    assert "Passed: 1  Failed: 1  Warnings: 1" in result.out
    assert "summary-failed" in result.out
    events = [r for r in lab.records() if r["event"].startswith("check_")]
    assert [(r["event"], r["item"], r["mode"]) for r in events] == [
        ("check_pass", "V1", "plan"),
        ("check_fail", "E3", "plan"),
        ("check_warn", "-", "plan"),
    ]
    assert all(r["script"] == "02" and r["region"] == "ap-northeast-1" for r in events)


def test_records_carry_the_apply_mode_and_variant(lab: Lab) -> None:
    lab.bash("lab_apply_on; lab_set_variant ui; check_pass V3 ok", name="07_driver.sh")
    record = [r for r in lab.records() if r["event"] == "check_pass"][0]
    assert (record["script"], record["mode"], record["item"]) == ("07-ui", "apply", "V3")


def test_the_exit_trap_prints_the_digest_line_and_records_the_end(lab: Lab) -> None:
    result = lab.bash("lab_apply_on; check_pass V1 fine", env={"LAB_NOW": NOW})
    match = re.search(r"^digest=([0-9a-f]{12}) run=(\S+)$", result.err, re.M)
    assert match, result.err
    assert match.group(2) == NOW
    end = [r for r in lab.records() if r["event"] == "end"][0]
    assert json.loads(end["detail"]) == {"digest": match.group(1), "exit": 0}
    assert end["mode"] == "apply"


def test_the_exit_trap_keeps_the_exit_code(lab: Lab) -> None:
    result = lab.bash("exit 7")
    assert result.rc == 7
    end = [r for r in lab.records() if r["event"] == "end"][0]
    assert json.loads(end["detail"])["exit"] == 7


def test_a_plan_exit_is_recorded_as_exit_10(lab: Lab) -> None:
    result = lab.bash("plan_exit 'run it'")
    assert result.rc == 10
    end = [r for r in lab.records() if r["event"] == "end"][0]
    assert (json.loads(end["detail"])["exit"], end["mode"]) == (10, "plan")


# --------------------------------------------------------------------------
# Argument validation helpers (all exit 2)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["6", "36", "abc", "", "-7", "007x"])
def test_retention_days_outside_7_to_35_is_a_usage_error(lab: Lab, value: str) -> None:
    result = lab.bash(f"validate_retention_days '{value}'; echo not-reached")
    assert result.rc == 2 and "not-reached" not in result.out


@pytest.mark.parametrize("value", ["7", "35", "14"])
def test_retention_days_inside_the_range_passes(lab: Lab, value: str) -> None:
    assert lab.bash(f"validate_retention_days '{value}'").rc == 0


@pytest.mark.parametrize("value", ["2026-02-30", "2026-1-1", "yesterday", "", "2026-13-01"])
def test_since_must_be_a_real_date(lab: Lab, value: str) -> None:
    assert lab.bash(f"validate_since '{value}'").rc == 2


@pytest.mark.parametrize("value", ["2024-02-29", "2026-10-11"])
def test_since_accepts_real_dates(lab: Lab, value: str) -> None:
    assert lab.bash(f"validate_since '{value}'").rc == 0


def test_arn_arguments_are_validated(lab: Lab) -> None:
    share = "arn:aws:ram:ap-northeast-1:111122223333:resource-share/0123-abcd"
    assert lab.bash(f"validate_arn --share-arn '{share}' ram").rc == 0
    assert lab.bash("validate_arn --share-arn 'not-an-arn' ram").rc == 2
    assert lab.bash(f"validate_arn --share-arn '{share}' backup").rc == 2
    assert lab.bash("validate_arn --x 'arn:aws:backup:ap-northeast-1:111122223333:recovery-point:abc'").rc == 0
    assert lab.bash("validate_arn --x ''").rc == 2


def test_region_argument_must_be_a_configured_region(lab: Lab) -> None:
    only_primary = lab.bash("validate_region_arg ap-northeast-3")
    assert only_primary.rc == 2
    with_second = {"LAB_SECOND_REGION": "ap-northeast-3"}
    assert lab.bash("validate_region_arg ap-northeast-3", env=with_second).rc == 0
    assert lab.bash("validate_region_arg ap-northeast-1", env=with_second).rc == 0
    assert lab.bash("validate_region_arg us-east-1", env=with_second).rc == 2


def test_since_error_names_the_option(lab: Lab) -> None:
    result = lab.bash("validate_since 2026-02-30")
    assert "--since" in result.err


# --------------------------------------------------------------------------
# JSON built by jq, never by concatenation
# --------------------------------------------------------------------------


def test_payload_is_built_with_jq(lab: Lab) -> None:
    result = lab.bash(
        r"""
        v='he said "hi" \ and
newline'
        json_build action startRestore note "$v" 'acknowledgeIrreversible:json' true 'count:json' 3
        """
    )
    document = json.loads(result.out.splitlines()[0])
    assert document["action"] == "startRestore"
    assert document["note"] == 'he said "hi" \\ and\nnewline'
    assert document["acknowledgeIrreversible"] is True
    assert document["count"] == 3


def test_json_build_with_no_pairs_is_an_empty_object(lab: Lab) -> None:
    assert lab.bash("json_build").out.strip().splitlines()[0] == "{}"


def test_scripts_in_the_lab_never_concatenate_json(lab: Lab) -> None:
    """No script may glue a --payload together by hand."""
    offenders = []
    for path in sorted((lab.scripts).rglob("*.sh")):
        text = path.read_text(encoding="utf-8")
        if re.search(r"--payload\s+[\"']?\{", text) or re.search(r"--payload\s+\"?\$\{?[A-Za-z_]+\}?\"?\s*\"?\{", text):
            offenders.append(path.name)
    assert offenders == []


# --------------------------------------------------------------------------
# Tags
# --------------------------------------------------------------------------


def test_tags_have_lab_tag_reads_list_tags_output(lab: Lab) -> None:
    tagged = json.dumps({"Tags": [{"Key": "Project", "Value": "shared-vault-lab"}, {"Key": "x", "Value": "y"}]})
    other = json.dumps({"Tags": [{"Key": "Project", "Value": "someone-elses"}]})
    none = json.dumps({"Tags": []})
    script = "if tags_have_lab_tag '{doc}'; then echo yes; else echo no; fi"
    assert lab.bash(script.format(doc=tagged)).out.splitlines()[0] == "yes"
    assert lab.bash(script.format(doc=other)).out.splitlines()[0] == "no"
    assert lab.bash(script.format(doc=none)).out.splitlines()[0] == "no"


# --------------------------------------------------------------------------
# Library hygiene
# --------------------------------------------------------------------------


def test_common_lib_is_bash_3_2_compatible() -> None:
    """No constructs that bash 3.2 (macOS /bin/bash) does not have."""
    text = COMMON.read_text(encoding="utf-8")
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    assert "mapfile" not in code and "readarray" not in code
    assert "declare -A" not in code
    assert not re.search(r"\$\{[A-Za-z_]+(,,|\^\^)\}", code)


def test_the_status_line_is_the_second_line_and_in_english() -> None:
    lines = COMMON.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "#!/bin/bash"
    assert lines[1] == "# Real-environment run: not yet done (status source: docs/verification-record.md)"
