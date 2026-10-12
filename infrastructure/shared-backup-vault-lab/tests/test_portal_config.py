"""07_portal_config.sh: --print, --check, --deploy and --ui, offline.

AWS is the aws stub. The external commands are fakes: ``sandbox.sh``, ``node``, ``npm``,
``npx``, ``make`` and the repository's ``portal_preflight.py`` record their arguments and the
environment values the tests assert on (never a secret: the password is reduced to a digest).
Nothing here starts a browser or reaches a network.
"""

from __future__ import annotations

import json
import re
import stat
from pathlib import Path
from typing import Any

import lab_scenarios as sc
import lab_scenarios_portal as pt
import pytest
import test_expected_calls as expected
from lab_testlib import LAB_SRC, Lab, Result, substitute_with_echo

SCRIPT = "07_portal_config.sh"
PRIMARY = sc.PRIMARY
SECOND = sc.SECOND
STATIC_KEYS = {
    "AWS_ACCESS_KEY_ID": "dummy-key-id",
    "AWS_SECRET_ACCESS_KEY": "dummy-secret",
    "AWS_SESSION_TOKEN": "dummy-token",
}


def sandbox_calls(lab: Lab) -> list[dict[str, Any]]:
    return pt.calls_of_name(lab.external_records(), "sandbox.sh")


def run_deploy(
    lab: Lab,
    scenario: dict[str, Any] | None = None,
    *,
    outputs: bool = False,
    node_modules: bool = True,
    config: bool = True,
    stage: str = "regions-only",
    identifier: str | None = pt.SANDBOX_ID,
    apply: bool = True,
    env: dict[str, str | None] | None = None,
    extra: tuple[str, ...] = (),
) -> Result:
    """Run ``--deploy`` against the fake portal."""
    lab.use_external_stubs()
    lab.make_portal(outputs=outputs, node_modules=node_modules, config=config)
    lab.write_scenario(scenario if scenario is not None else pt.deploy())
    args = ["--deploy", "--stage", stage]
    if identifier:
        args += ["--identifier", identifier]
    if apply:
        args.append("--apply")
    return lab.run(SCRIPT, *args, *extra, env={"LAB_SECOND_REGION": SECOND, **(env or {})})


def run_ui(
    lab: Lab,
    *,
    expect: str = "arn-present",
    apply: bool = True,
    provision: bool = False,
    portal: dict[str, bool] | None = None,
    env: dict[str, str | None] | None = None,
    creds: bool = True,
    scenario: dict[str, Any] | None = None,
    extra: tuple[str, ...] = (),
) -> Result:
    """Run ``--ui`` against the fake portal (credentials from the environment by default)."""
    lab.use_external_stubs()
    lab.make_portal(**(portal or {}))
    lab.write_scenario(scenario if scenario is not None else pt.base())
    args = ["--ui", "--expect", expect, *extra]
    if provision:
        args.append("--provision-user")
    if apply:
        args.append("--apply")
    full_env: dict[str, str | None] = {"STUB_MAKE_PASSWORD": pt.PASSWORD}
    if creds:
        full_env.update({"PORTAL_USER": pt.USERNAME, "PORTAL_PASSWORD": pt.PASSWORD})
    full_env.update(env or {})
    return lab.run(SCRIPT, *args, env=full_env)


# --------------------------------------------------------------------------
# Arguments
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--print", "--check"],
        ["--check", "--apply"],
        ["--print", "--apply"],
        ["--check", "--expect", "bogus"],
        ["--print", "--expect", "revoked"],
        ["--ui"],
        ["--deploy", "--stage", "everything"],
        ["--deploy", "--provision-user"],
        ["--deploy", "--function-name", "x"],
        ["--deploy", "--identifier", "bad name!"],
        ["--check", "--function-name", "bad name!"],
        ["--frobnicate"],
    ],
)
def test_07_usage_errors_exit_2_and_call_nothing(lab: Lab, args: list[str]) -> None:
    lab.use_external_stubs()
    result = lab.run(SCRIPT, *args, allow_stub_failure=True)
    assert result.rc == 2, result.err
    assert result.calls == []
    assert lab.external_calls() == []


def test_07_help_exits_0(lab: Lab) -> None:
    result = lab.run(SCRIPT, "--help")
    assert result.rc == 0 and "--print" in result.out


def test_07_deploy_has_no_replacement_check_option(lab: Lab) -> None:
    text = (LAB_SRC / "scripts" / SCRIPT).read_text(encoding="utf-8")
    assert "skip-replacement-check" not in text
    result = lab.run(SCRIPT, "--deploy", "--skip-replacement-check", allow_stub_failure=True)
    assert result.rc == 2


# --------------------------------------------------------------------------
# --print
# --------------------------------------------------------------------------


def test_07_print_writes_the_env_file_and_prints_the_same_lines(lab: Lab) -> None:
    result = expected.run_07_print(lab)
    assert result.rc == 0, result.err
    written = (lab.root / "portal.local.env").read_text(encoding="utf-8")
    assert result.out == written
    lines = {line.split("=", 1)[0]: line.split("=", 1)[1] for line in written.splitlines() if "=" in line}
    assert lines["AMPLIFY_PORTAL_BACKUP_REGIONS"] == SECOND
    assert lines["AMPLIFY_PORTAL_BACKUP_VAULT_ARNS"] == f"{sc.lag_arn(PRIMARY)},{sc.lag_arn(SECOND)}"
    assert lines["AMPLIFY_PORTAL_RESTORE_ROLE_ARN"] == sc.RECIPIENT_ROLE_ARN
    assert lines["AMPLIFY_PORTAL_RESTORE_SVM_IDS"] == sc.RECIPIENT_RESTORE_SVM
    assert lines["AMPLIFY_PORTAL_RESTORE_FILE_SYSTEM_IDS"] == sc.EXISTING_RECIPIENT_FS
    assert "\u2705" not in result.out and "digest=" not in result.out, "stdout carries the lines only"
    assert not (lab.cwd / "portal.local.env").exists()


def test_07_print_takes_the_arn_from_the_response_and_never_builds_it(lab: Lab) -> None:
    odd = "arn:aws-us-gov:backup:ap-northeast-1:111122223333:backup-vault:shared-vault-lab-lag"
    scenario = pt.print_scenario(second=False)
    scenario[f"backup list-backup-vaults --by-shared --region={PRIMARY}"] = {
        "body": {"BackupVaultList": [{"BackupVaultName": sc.LAG_VAULT, "BackupVaultArn": odd}]}
    }
    lab.write_scenario(scenario)
    result = lab.run(SCRIPT, "--print")
    assert result.rc == 0, result.err
    assert f"AMPLIFY_PORTAL_BACKUP_VAULT_ARNS={odd}" in result.out


def test_07_print_ignores_a_vault_of_another_owner(lab: Lab) -> None:
    other = f"arn:aws:backup:{PRIMARY}:999999999999:backup-vault:{sc.LAG_VAULT}"
    scenario = pt.print_scenario(second=False)
    scenario[f"backup list-backup-vaults --by-shared --region={PRIMARY}"] = {
        "body": {"BackupVaultList": [{"BackupVaultName": sc.LAG_VAULT, "BackupVaultArn": other}]}
    }
    lab.write_scenario(scenario)
    result = lab.run(SCRIPT, "--print")
    assert result.rc == 1
    assert "not visible" in result.err
    assert not (lab.root / "portal.local.env").exists()


def test_07_print_second_region_without_the_vault_only_warns(lab: Lab) -> None:
    scenario = pt.print_scenario()
    scenario[f"backup list-backup-vaults --by-shared --region={SECOND}"] = {"body": {"BackupVaultList": []}}
    lab.write_scenario(scenario)
    result = lab.run(SCRIPT, "--print", env={"LAB_SECOND_REGION": SECOND})
    assert result.rc == 0, result.err
    assert "warning" in result.err and SECOND in result.err
    assert f"AMPLIFY_PORTAL_BACKUP_VAULT_ARNS={sc.lag_arn(PRIMARY)}\n" in result.out


def test_07_print_two_matching_vaults_abort(lab: Lab) -> None:
    scenario = pt.print_scenario(second=False)
    row = {"BackupVaultName": sc.LAG_VAULT, "BackupVaultArn": sc.lag_arn(PRIMARY)}
    scenario[f"backup list-backup-vaults --by-shared --region={PRIMARY}"] = {"body": {"BackupVaultList": [row, row]}}
    lab.write_scenario(scenario)
    result = lab.run(SCRIPT, "--print")
    assert result.rc == 1 and "rows=2" in result.err
    assert not (lab.root / "portal.local.env").exists()


def test_07_print_without_the_recipient_stack_points_at_02(lab: Lab) -> None:
    scenario = pt.print_scenario(second=False)
    scenario[f"cloudformation describe-stacks --stack-name={sc.TAG}-recipient-{PRIMARY}"] = sc.no_stack()
    lab.write_scenario(scenario)
    result = lab.run(SCRIPT, "--print", allow_stub_failure=True)
    assert result.rc == 1 and "02_deploy.sh" in result.err
    assert not (lab.root / "portal.local.env").exists()


def test_07_print_writes_next_to_the_lab_not_the_working_directory(lab: Lab) -> None:
    assert expected.run_07_print(lab).rc == 0
    assert (lab.root / "portal.local.env").is_file()
    assert list(lab.cwd.iterdir()) == []


# --------------------------------------------------------------------------
# --check
# --------------------------------------------------------------------------

STATES = ("arn-missing", "arn-present", "revoked")


def run_check(lab: Lab, state: str, expect: str | None, *extra: str, scenario: dict[str, Any] | None = None) -> Result:
    lab.write_scenario(scenario if scenario is not None else pt.check(state))
    args = ["--check", *extra]
    if expect:
        args += ["--expect", expect]
    return lab.run(SCRIPT, *args, env={"LAB_SECOND_REGION": SECOND})


@pytest.mark.parametrize("state", STATES)
def test_07_check_passes_in_the_matching_state(lab: Lab, state: str) -> None:
    result = run_check(lab, state, state)
    assert result.rc == 0, result.out + result.err
    assert "\u274c" not in result.out
    items = {"arn-missing": "V3", "arn-present": "V5", "revoked": "V6"}
    assert f"\u2705 [{items[state]}]" in result.out
    assert sc.mutating(result.calls) == []


@pytest.mark.parametrize(("expect", "state"), [(e, s) for e in STATES for s in STATES if e != s])
def test_07_check_expect_mismatch_fails(lab: Lab, expect: str, state: str) -> None:
    result = run_check(lab, state, expect)
    assert result.rc == 1, result.out
    failures = [line for line in result.out.splitlines() if "\u274c" in line]
    assert failures, "a mismatch must print a failure line"
    text = "\n".join(failures)
    assert "expected" in text and "measured" in text, text
    assert expect in text or "VaultNotShared" in text or "AccessDeniedException" in text or "at least one" in text


def test_07_check_revoked_requires_vaultnotshared_code(lab: Lab) -> None:
    scenario = pt.check("revoked")
    scenario["lambda invoke"] = [pt.shared_body(False), pt.recovery_points_body(0, "AccessDeniedException")]
    result = run_check(lab, "revoked", "revoked", scenario=scenario)
    assert result.rc == 1
    assert "VaultNotShared" in result.out and "AccessDeniedException" in result.out
    assert "a plain AccessDeniedException is not enough" in result.out


def test_07_check_function_not_found_fails(lab: Lab) -> None:
    scenario = pt.check("arn-present")
    scenario["lambda list-functions"] = {"body": {"Functions": [pt.function_row("other", "something else")]}}
    result = run_check(lab, "arn-present", "arn-present", scenario=scenario)
    assert result.rc == 1
    assert "not found" in result.out
    assert [c for c in result.calls if c["subcommand"] == "invoke"] == []


def test_07_check_function_name_not_found_fails(lab: Lab) -> None:
    result = run_check(lab, "arn-present", "arn-present", "--function-name", "no-such-function")
    assert result.rc == 1 and "no-such-function" in result.out
    assert [c for c in result.calls if c["subcommand"] == "invoke"] == []


def test_07_two_matching_functions_abort(lab: Lab) -> None:
    scenario = pt.check("arn-present")
    scenario["lambda list-functions"] = {
        "body": {"Functions": [pt.function_row("first-copy"), pt.function_row("second-copy")]}
    }
    result = run_check(lab, "arn-present", "arn-present", scenario=scenario)
    assert result.rc == 1
    assert "rows=2" in result.err and "first-copy" in result.err and "--function-name" in result.err
    assert [c for c in result.calls if c["subcommand"] == "invoke"] == []
    chosen = run_check(lab, "arn-present", "arn-present", "--function-name", "second-copy", scenario=scenario)
    assert chosen.rc == 0, chosen.out + chosen.err
    invokes = [c for c in chosen.calls if c["subcommand"] == "invoke"]
    assert {c["args"]["--function-name"][0] for c in invokes} == {"second-copy"}


def test_07_check_function_error_fails(lab: Lab) -> None:
    scenario = pt.check("arn-present")
    scenario["lambda invoke"] = [
        {"body": {"errorMessage": "boom"}, "stdout": json.dumps({"StatusCode": 200, "FunctionError": "Unhandled"})},
    ]
    result = run_check(lab, "arn-present", "arn-present", scenario=scenario)
    assert result.rc == 1 and "could not be invoked" in result.out


def test_07_check_without_expect_reports_and_does_not_judge(lab: Lab) -> None:
    result = run_check(lab, "revoked", None)
    assert result.rc == 0, result.err
    assert "not judged" in result.out and "errorCode=VaultNotShared" in result.out


def test_07_check_warns_when_the_function_lacks_the_second_region(lab: Lab) -> None:
    scenario = pt.check("arn-present")
    scenario["lambda list-functions"] = {"body": {"Functions": [pt.function_row(regions=[])]}}
    result = run_check(lab, "arn-present", "arn-present", scenario=scenario)
    assert result.rc == 0
    assert "\u26a0 [-] BACKUP_REGIONS" in result.out


def test_07_check_compares_the_role_policy_with_the_state(lab: Lab) -> None:
    scenario = pt.check("arn-present")
    scenario["iam get-role-policy"] = pt.policy_body([])
    result = run_check(lab, "arn-present", "arn-present", scenario=scenario)
    assert result.rc == 1
    assert "expected the shared vault ARN in the role policy" in result.out


def test_07_check_payloads_are_valid_json_built_by_jq(lab: Lab) -> None:
    result = run_check(lab, "arn-present", "arn-present")
    invokes = [c for c in result.calls if c["subcommand"] == "invoke"]
    payloads = [json.loads(c["args"]["--payload"][0]) for c in invokes]
    assert payloads == [json.loads(pt.SHARED_PAYLOAD), json.loads(pt.RP_PAYLOAD)]
    assert "--cli-binary-format" in invokes[0]["argv"]
    assert invokes[0]["argv"][invokes[0]["argv"].index("--cli-binary-format") + 1] == "raw-in-base64-out"


# --------------------------------------------------------------------------
# --deploy
# --------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["deploy", "ui-env", "ui-provision"])
def test_07_portal_children_receive_recipient_identity(lab: Lab, mode: str) -> None:
    """The fake sandbox.sh, make and npx see the recipient profile and the primary Region, no static key."""
    env: dict[str, str | None] = {**STATIC_KEYS, "AWS_PROFILE": "someone-else", "AWS_REGION": "eu-west-1"}
    if mode == "deploy":
        result = run_deploy(lab, env=env)
        names = ["sandbox.sh"]
    elif mode == "ui-env":
        result = run_ui(lab, env=env)
        names = ["npx"]
    else:
        result = run_ui(lab, creds=False, provision=True, portal={"node_modules": False, "chromium": False}, env=env)
        names = ["make", "npx"]
    assert result.rc == 0, result.out + result.err
    records = lab.external_records()
    for name in names:
        found = [r for r in records if r["name"] == name]
        assert found, f"no call of {name}"
        for record in found:
            assert record["env"]["AWS_PROFILE"] == sc.RECIPIENT_PROFILE
            assert record["env"]["AWS_REGION"] == PRIMARY
            assert record["env"]["AWS_DEFAULT_REGION"] == PRIMARY
            assert record["env"]["AMPLIFY_PORTAL_REGION"] == PRIMARY
            assert record["env"]["AWS_ACCESS_KEY_ID_set"] is False
            assert record["env"]["AWS_SECRET_ACCESS_KEY_set"] is False
            assert record["env"]["AWS_SESSION_TOKEN_set"] is False
            assert record["env"]["AWS_DEFAULT_PROFILE"] is None


@pytest.mark.parametrize("mode", ["deploy", "ui", "ui-provision"])
def test_07_ambient_account_mismatch_aborts_before_sandbox(lab: Lab, mode: str) -> None:
    scenario = pt.base()
    scenario["sts get-caller-identity !--profile"] = pt.who_ambient(sc.OWNER)
    if mode == "deploy":
        result = run_deploy(lab, {**pt.deploy(), **{"sts get-caller-identity !--profile": pt.who_ambient(sc.OWNER)}})
    elif mode == "ui":
        result = run_ui(lab, scenario=scenario)
    else:
        result = run_ui(lab, creds=False, provision=True, scenario=scenario)
    assert result.rc == 1, result.out + result.err
    assert sc.OWNER in result.err
    names = {r["name"] for r in lab.external_records()}
    assert not names & {"sandbox.sh", "make"}, names
    assert not any("playwright test" in line for line in lab.external_calls())
    assert not any(c["subcommand"] == "describe-stacks" and not c["args"].get("--stack-name") for c in result.calls)


def test_07_provision_user_runs_make_in_repo_root(lab: Lab) -> None:
    result = run_ui(lab, creds=False, provision=True)
    assert result.rc == 0, result.out + result.err
    makes = pt.calls_of_name(lab.external_records(), "make")
    assert len(makes) == 1
    argv = makes[0]["argv"]
    assert argv[0] == "-C"
    assert Path(argv[1]).resolve() == lab.repo.resolve()
    assert argv[2] == "portal-demo-user"
    assert argv[3] == f"ARGS=--username {pt.USERNAME} --groups storage-admin,internal"
    assert len(argv) == 4


def test_07_provision_user_passes_the_expected_sandbox(lab: Lab) -> None:
    result = run_ui(lab, creds=False, provision=True, env={"LAB_PORTAL_SANDBOX_ID": "labsandbox"})
    assert result.rc == 0, result.out + result.err
    argv = pt.calls_of_name(lab.external_records(), "make")[0]["argv"]
    assert argv[3].endswith("--expected-sandbox labsandbox")


def test_07_provision_user_without_the_make_target_fails_clearly(lab: Lab) -> None:
    (lab.repo / "Makefile").write_text("other:\n\t@true\n", encoding="utf-8")
    result = run_ui(lab, creds=False, provision=True)
    assert result.rc == 1
    assert "portal-demo-user" in result.err and "Makefile" in result.err
    assert pt.calls_of_name(lab.external_records(), "make") == []


def test_07_deploy_creates_portal_config_when_missing(lab: Lab) -> None:
    plan = run_deploy(lab, config=False, apply=False)
    assert plan.rc == 10
    assert "cp amplify/portal-config.example.ts amplify/portal-config.ts" in plan.out
    assert not (lab.portal / "amplify" / "portal-config.ts").exists(), "a plan creates nothing"
    result = run_deploy(Lab(lab.tmp / "second"), config=False)
    assert result.rc == 0, result.out + result.err


def test_07_deploy_copies_the_example_and_never_overwrites(lab: Lab) -> None:
    result = run_deploy(lab, config=False)
    assert result.rc == 0, result.out + result.err
    config = lab.portal / "amplify" / "portal-config.ts"
    assert config.read_text(encoding="utf-8") == (lab.portal / "amplify" / "portal-config.example.ts").read_text(
        encoding="utf-8"
    )
    config.write_text("// the reader's own settings\n", encoding="utf-8")
    again = lab.run(SCRIPT, "--deploy", "--stage", "regions-only", "--identifier", pt.SANDBOX_ID, "--apply")
    assert again.rc in (0, 1)
    assert config.read_text(encoding="utf-8") == "// the reader's own settings\n"


def test_07_deploy_regions_only_omits_vault_arns(lab: Lab) -> None:
    leaked = {
        "AMPLIFY_PORTAL_BACKUP_VAULT_ARNS": "arn:aws:backup:ap-northeast-1:111122223333:backup-vault:from-the-readers-shell",
        "AMPLIFY_PORTAL_RESTORE_ROLE_ARN": "arn:aws:iam::444455556666:role/from-the-readers-shell",
    }
    result = run_deploy(lab, env=leaked)
    assert result.rc == 0, result.out + result.err
    env = sandbox_calls(lab)[0]["env"]
    assert env["AMPLIFY_PORTAL_BACKUP_REGIONS"] == SECOND
    assert env["AMPLIFY_PORTAL_BACKUP_VAULT_ARNS"] is None
    assert env["AMPLIFY_PORTAL_RESTORE_ROLE_ARN"] is None


def test_07_deploy_full_reads_portal_local_env(lab: Lab) -> None:
    lab.make_portal(outputs=False)
    (lab.root / "portal.local.env").write_text(
        "# comment\n"
        f"AMPLIFY_PORTAL_BACKUP_REGIONS={SECOND}\n"
        f"AMPLIFY_PORTAL_BACKUP_VAULT_ARNS={sc.lag_arn(PRIMARY)},{sc.lag_arn(SECOND)}\n"
        f"AMPLIFY_PORTAL_RESTORE_ROLE_ARN={sc.RECIPIENT_ROLE_ARN}\n"
        f"AMPLIFY_PORTAL_RESTORE_SVM_IDS={sc.RECIPIENT_RESTORE_SVM}\n"
        f"AMPLIFY_PORTAL_RESTORE_FILE_SYSTEM_IDS={sc.EXISTING_RECIPIENT_FS}\n",
        encoding="utf-8",
    )
    result = run_deploy(lab, stage="full")
    assert result.rc == 0, result.out + result.err
    env = sandbox_calls(lab)[0]["env"]
    assert env["AMPLIFY_PORTAL_BACKUP_VAULT_ARNS"] == f"{sc.lag_arn(PRIMARY)},{sc.lag_arn(SECOND)}"
    assert env["AMPLIFY_PORTAL_RESTORE_ROLE_ARN"] == sc.RECIPIENT_ROLE_ARN
    assert env["AMPLIFY_PORTAL_RESTORE_SVM_IDS"] == sc.RECIPIENT_RESTORE_SVM
    assert env["AMPLIFY_PORTAL_RESTORE_FILE_SYSTEM_IDS"] == sc.EXISTING_RECIPIENT_FS


def test_07_deploy_full_without_the_env_file_asks_for_print_and_exits_10(lab: Lab) -> None:
    result = run_deploy(lab, stage="full")
    assert result.rc == 10
    assert "--print" in result.out
    assert sandbox_calls(lab) == []


def test_07_deploy_full_rejects_an_unknown_key_in_the_env_file(lab: Lab) -> None:
    lab.make_portal(outputs=False)
    (lab.root / "portal.local.env").write_text("SOMETHING_ELSE=1\n", encoding="utf-8")
    result = run_deploy(lab, stage="full")
    assert result.rc == 1 and "unexpected key" in result.err


def test_07_deploy_without_node_modules_prints_npm_ci_plan(lab: Lab) -> None:
    plan = run_deploy(lab, node_modules=False, apply=False)
    assert plan.rc == 10, plan.out + plan.err
    assert "npm ci" in plan.out
    assert not any(line.startswith(("npm ci", "sandbox.sh")) for line in lab.external_calls())
    done = run_deploy(Lab(lab.tmp / "apply"), node_modules=False)
    assert done.rc == 0, done.out + done.err


def test_07_deploy_installs_before_it_deploys(lab: Lab) -> None:
    result = run_deploy(lab, node_modules=False)
    assert result.rc == 0, result.out + result.err
    lines = lab.external_calls()
    assert lines.index("npm ci") < lines.index("sandbox.sh --once")


def test_07_deploy_identifier_is_passed_to_sandbox_sh(lab: Lab) -> None:
    result = run_deploy(lab)
    assert result.rc == 0, result.out + result.err
    calls = sandbox_calls(lab)
    assert len(calls) == 1
    assert calls[0]["argv"] == ["--once"]
    assert calls[0]["env"]["AMPLIFY_PORTAL_SANDBOX_IDENTIFIER"] == pt.SANDBOX_ID
    assert Path(calls[0]["cwd"]).resolve() == lab.portal.resolve()


def test_07_deploy_new_sandbox_requires_an_identifier(lab: Lab) -> None:
    result = run_deploy(lab, identifier=None)
    assert result.rc == 2 and "--identifier" in result.err
    assert sandbox_calls(lab) == []


def test_07_deploy_identifier_mismatch_with_outputs_is_refused(lab: Lab) -> None:
    result = run_deploy(lab, outputs=True, env={"STUB_PREFLIGHT_ID": "another-sandbox"})
    assert result.rc == 2, result.out + result.err
    assert "another-sandbox" in result.err and pt.SANDBOX_ID in result.err
    assert sandbox_calls(lab) == []


def test_07_deploy_identifier_match_with_outputs_proceeds(lab: Lab) -> None:
    result = run_deploy(lab, outputs=True, env={"STUB_PREFLIGHT_ID": pt.SANDBOX_ID})
    assert result.rc == 0, result.out + result.err
    assert len(sandbox_calls(lab)) == 1


def test_07_deploy_unidentifiable_sandbox_is_refused(lab: Lab) -> None:
    result = run_deploy(lab, outputs=True, env={"STUB_PREFLIGHT_RC": "3"})
    assert result.rc == 1 and "could not be identified" in result.err
    assert sandbox_calls(lab) == []


def stacks_after(*rows: dict[str, Any]) -> list[dict[str, Any]]:
    return [*rows, pt.stack(pt.UNRELATED)]


DEPLOY_CASES = {
    # sandbox exit code, stacks after the run, expected exit code, text that must appear
    "exit0-update-failed": (
        "0",
        stacks_after(
            pt.stack(pt.ROOT, "UPDATE_COMPLETE", pt.STAMP_NEW), pt.stack(pt.DATA, "UPDATE_FAILED", pt.STAMP_NEW)
        ),
        1,
        "UPDATE_FAILED",
    ),
    "exit0-nothing-updated": ("0", None, 1, "no amplify- stack was created or updated"),
    "exit1-stacks-complete": (
        "1",
        stacks_after(
            pt.stack(pt.ROOT, "UPDATE_COMPLETE", pt.STAMP_NEW), pt.stack(pt.DATA, "UPDATE_COMPLETE", pt.STAMP_NEW)
        ),
        0,
        "exited 1 although the stacks reached a complete state",
    ),
    "exit1-sso-expired-nothing-changed": ("1", None, 1, "no amplify- stack was created or updated"),
}


@pytest.mark.parametrize("case", sorted(DEPLOY_CASES))
def test_07_deploy_ignores_sandbox_exit_code(lab: Lab, case: str) -> None:
    rc_sandbox, after, rc_expected, text = DEPLOY_CASES[case]
    before = [pt.stack(pt.ROOT), pt.stack(pt.DATA), pt.stack(pt.UNRELATED)]
    scenario = pt.deploy(before=before, after=after if after is not None else before, events=True)
    result = run_deploy(lab, scenario, env={"STUB_SANDBOX_RC": rc_sandbox})
    assert result.rc == rc_expected, result.out + result.err
    assert text in result.out
    assert len(sandbox_calls(lab)) == 1
    if rc_expected == 0:
        assert "\u26a0" in result.out, "an exit code that disagrees with the stacks is a warning"


def test_07_deploy_zero_changed_stacks_is_a_failure_even_with_a_clean_exit(lab: Lab) -> None:
    before = [pt.stack(pt.ROOT), pt.stack(pt.DATA)]
    result = run_deploy(lab, pt.deploy(before=before, after=before))
    assert result.rc == 1 and "did not take effect" in result.out


def test_07_deploy_new_stacks_count_as_changed(lab: Lab) -> None:
    result = run_deploy(
        lab,
        pt.deploy(
            before=[pt.stack(pt.UNRELATED)],
            after=[pt.stack(pt.UNRELATED), pt.stack(pt.ROOT, "CREATE_COMPLETE", created=True)],
        ),
    )
    assert result.rc == 0, result.out + result.err
    assert "CREATE_COMPLETE" in result.out


def test_07_deploy_ignores_stacks_without_the_amplify_prefix(lab: Lab) -> None:
    before = [pt.stack(pt.UNRELATED, stamp=pt.STAMP_OLD)]
    after = [pt.stack(pt.UNRELATED, stamp=pt.STAMP_NEW)]
    result = run_deploy(lab, pt.deploy(before=before, after=after))
    assert result.rc == 1 and "no amplify- stack" in result.out


def test_07_deploy_waits_while_a_changed_stack_is_in_progress(lab: Lab) -> None:
    before = [pt.stack(pt.ROOT), pt.stack(pt.DATA)]
    polls = [
        [
            pt.stack(pt.ROOT, "UPDATE_COMPLETE_CLEANUP_IN_PROGRESS", pt.STAMP_NEW),
            pt.stack(pt.DATA, "UPDATE_COMPLETE", pt.STAMP_NEW),
        ],
        [pt.stack(pt.ROOT, "UPDATE_COMPLETE", pt.STAMP_NEW), pt.stack(pt.DATA, "UPDATE_COMPLETE", pt.STAMP_NEW)],
    ]
    result = run_deploy(lab, pt.deploy(before=before, after=polls))
    assert result.rc == 0, result.out + result.err
    assert lab.sleeps(), "the poll slept between reads"


def test_07_deploy_update_failed_points_to_quality_gates_doc(lab: Lab) -> None:
    before = [pt.stack(pt.ROOT), pt.stack(pt.DATA)]
    after = [pt.stack(pt.ROOT, "UPDATE_COMPLETE", pt.STAMP_NEW), pt.stack(pt.DATA, "UPDATE_FAILED", pt.STAMP_NEW)]
    result = run_deploy(lab, pt.deploy(before=before, after=after, events=True))
    assert result.rc == 1
    assert "docs/agent/portal-cdk-quality-gates.md" in result.out
    assert "Stub reason: the update was refused" in result.out
    assert "does not determine the cause" in result.out
    assert not re.search(r"(caused by|because of|the cause is) .{0,40}(AwsCli|asset)", result.out, re.I)
    events = [c for c in result.calls if c["subcommand"] == "describe-stack-events"]
    assert [c["args"]["--stack-name"][0] for c in events] == [pt.DATA]


def test_07_deploy_failure_reasons_are_capped_at_five(lab: Lab) -> None:
    before = [pt.stack(pt.ROOT), pt.stack(pt.DATA)]
    after = [pt.stack(pt.ROOT, "UPDATE_FAILED", pt.STAMP_NEW), pt.stack(pt.DATA, "UPDATE_FAILED", pt.STAMP_NEW)]
    scenario = pt.deploy(before=before, after=after)
    scenario["cloudformation describe-stack-events"] = {
        "body": {
            "StackEvents": [
                {
                    "StackName": "s",
                    "LogicalResourceId": f"R{i}",
                    "ResourceStatus": "UPDATE_FAILED",
                    "ResourceStatusReason": f"reason {i}",
                }
                for i in range(9)
            ]
        }
    }
    result = run_deploy(lab, scenario)
    assert result.rc == 1
    assert len(re.findall(r"reason \d", result.out)) == 5


def test_07_deploy_stack_read_failure_before_the_run_starts_nothing(lab: Lab) -> None:
    scenario = pt.deploy()
    scenario["cloudformation describe-stacks !--stack-name"] = sc.err("AccessDenied", "no")
    result = run_deploy(lab, scenario)
    assert result.rc == 1
    assert sandbox_calls(lab) == []


def test_07_deploy_has_no_mutating_aws_call(lab: Lab) -> None:
    result = run_deploy(lab)
    assert result.rc == 0
    assert sc.mutating(result.calls) == []


@pytest.mark.parametrize("mode", ["deploy", "ui"])
def test_07_plan_mode_records_zero_sandbox_or_npx_calls(lab: Lab, mode: str) -> None:
    if mode == "deploy":
        result = run_deploy(lab, apply=False)
    else:
        result = run_ui(lab, apply=False)
    assert result.rc == 10, result.out + result.err
    assert "PLAN ONLY" in result.out
    assert sandbox_calls(lab) == []
    assert not any(line.startswith(("npx ", "npm ci", "make ")) for line in lab.external_calls())
    assert sc.mutating(result.calls) == []


# --------------------------------------------------------------------------
# Missing tools
# --------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["--deploy", "--ui"])
def test_07_ui_missing_node_exits_75(lab: Lab, mode: str) -> None:
    """node and npm missing is a missing tool (75), not a prerequisite that --apply installs (10)."""
    lab.make_portal()
    lab.write_scenario(pt.base())
    args = (
        [mode, "--stage", "regions-only", "--identifier", pt.SANDBOX_ID]
        if mode == "--deploy"
        else [mode, "--expect", "revoked"]
    )
    result = lab.run(SCRIPT, *args, "--apply", env={"PORTAL_USER": "u", "PORTAL_PASSWORD": "p"})
    assert result.rc == 75, result.out + result.err
    assert "node" in result.err


def test_07_ui_missing_npm_exits_75(lab: Lab) -> None:
    lab.use_external_stubs("node", "npx")
    lab.make_portal()
    result = lab.run(SCRIPT, "--ui", "--expect", "revoked", "--apply", env={"PORTAL_USER": "u", "PORTAL_PASSWORD": "p"})
    assert result.rc == 75 and "npm" in result.err


# --------------------------------------------------------------------------
# --ui
# --------------------------------------------------------------------------


def test_07_ui_without_a_deployed_portal_asks_for_deploy(lab: Lab) -> None:
    result = run_ui(lab, portal={"outputs": False})
    assert result.rc == 1 and "--deploy" in result.err
    assert lab.external_calls() == []


@pytest.mark.parametrize(
    "case",
    ["no-node-modules", "no-chromium", "no-config", "credentials-to-create"],
)
def test_07_ui_missing_prerequisites_prints_plan_and_exits_10(lab: Lab, case: str) -> None:
    portal = {
        "no-node-modules": {"node_modules": False},
        "no-chromium": {"chromium": False},
        "no-config": {"config": False},
        "credentials-to-create": {},
    }[case]
    result = run_ui(
        lab,
        apply=False,
        creds=case != "credentials-to-create",
        provision=case == "credentials-to-create",
        portal=portal,
    )
    assert result.rc == 10, result.out + result.err
    assert "Missing" in result.out and "PLAN ONLY" in result.out
    wanted = {
        "no-node-modules": "npm ci",
        "no-chromium": "npx playwright install chromium",
        "no-config": "cp amplify/portal-config.example.ts amplify/portal-config.ts",
        "credentials-to-create": "portal-demo-user",
    }[case]
    assert wanted in result.out
    assert not any(line.startswith(("npx playwright test", "npm ci", "make ")) for line in lab.external_calls())
    assert not (lab.root / "ui-result.local.json").exists()


def test_07_ui_installs_what_is_missing_with_apply(lab: Lab) -> None:
    result = run_ui(lab, portal={"node_modules": False, "chromium": False, "config": False})
    assert result.rc == 0, result.out + result.err
    lines = lab.external_calls()
    assert (
        lines.index("npm ci")
        < lines.index("npx playwright install chromium")
        < next(i for i, line in enumerate(lines) if line.startswith("npx playwright test"))
    )
    assert (lab.portal / "amplify" / "portal-config.ts").is_file()


def test_07_ui_without_credentials_and_without_provision_user_shows_both_routes(lab: Lab) -> None:
    result = run_ui(lab, creds=False)
    assert result.rc == 1
    assert "PORTAL_USER" in result.err and "--provision-user" in result.err


def test_07_ui_exports_derived_values(lab: Lab) -> None:
    capture = str(lab.tmp / "captures")
    result = run_ui(lab, expect="arn-missing", env={"LAB_SECOND_REGION": SECOND, "LAB_CAPTURE_DIR": capture})
    assert result.rc == 0, result.out + result.err
    env = pt.calls_of_name(lab.external_records(), "npx")[0]["env"]
    assert env["LAB_LAG_VAULT_NAME"] == sc.LAG_VAULT, "derived from LAB_TAG, never set in the environment"
    assert env["LAB_OWNER_ACCOUNT_ID"] == sc.OWNER
    assert env["LAB_UI_EXPECT"] == "arn-missing"
    assert env["LAB_SECOND_REGION"] == SECOND
    assert env["LAB_CAPTURE_DIR"] == capture
    assert env["PORTAL_USER"] == pt.USERNAME
    assert env["PORTAL_PASSWORD_sha256"] == pt.sha256(pt.PASSWORD)


def test_07_ui_derived_vault_name_follows_lab_tag(lab: Lab) -> None:
    result = run_ui(lab, env={"LAB_TAG": "other-lab"})
    assert result.rc == 0, result.out + result.err
    assert pt.calls_of_name(lab.external_records(), "npx")[0]["env"]["LAB_LAG_VAULT_NAME"] == "other-lab-lag"


def test_07_ui_runs_in_the_portal_dir_with_the_spec_filter(lab: Lab) -> None:
    result = run_ui(lab)
    assert result.rc == 0, result.out + result.err
    call = pt.calls_of_name(lab.external_records(), "npx")[0]
    assert call["argv"] == ["playwright", "test", "shared-vault-lab\\.spec\\.ts$", "--reporter=json"]
    assert Path(call["cwd"]).resolve() == lab.portal.resolve()
    assert (lab.root / "ui-result.local.json").is_file()


@pytest.mark.parametrize(
    ("ci", "url", "ci_expected"),
    [("true", "", None), ("true", "https://portal.example.com", "true"), (None, "", None)],
)
def test_07_ui_unsets_ci_when_portal_url_empty(lab: Lab, ci: str | None, url: str, ci_expected: str | None) -> None:
    result = run_ui(lab, env={"CI": ci, "PORTAL_URL": url})
    assert result.rc == 0, result.out + result.err
    env = pt.calls_of_name(lab.external_records(), "npx")[0]["env"]
    assert env["CI"] == ci_expected
    assert env["PORTAL_URL"] == url


@pytest.mark.parametrize(
    ("stats", "rc", "text"),
    [
        ({"expected": 1, "skipped": 1}, 1, "a skipped test is not a pass"),
        ({"expected": 0, "skipped": 0}, 1, "expected=0"),
        ({"expected": 2, "unexpected": 1}, 1, "unexpected=1"),
        ({"expected": 1, "flaky": 1}, 0, "passed only on retry"),
        ({"expected": 3}, 0, "ran 3 test(s)"),
    ],
)
def test_07_ui_judges_the_report_stats(lab: Lab, stats: dict[str, int], rc: int, text: str) -> None:
    report = pt.write_report(lab.tmp / "report.json", **stats)
    result = run_ui(lab, env={"STUB_NPX_REPORT": str(report), "STUB_NPX_RC": "1" if stats.get("unexpected") else "0"})
    assert result.rc == rc, result.out + result.err
    assert text in result.out
    if stats.get("flaky"):
        assert "\u26a0" in result.out


def test_07_ui_skipped_tests_are_failure(lab: Lab) -> None:
    report = pt.write_report(lab.tmp / "report.json", expected=1, skipped=1)
    result = run_ui(lab, expect="arn-present", env={"STUB_NPX_REPORT": str(report)})
    assert result.rc == 1
    assert "\u274c [V3]" in result.out and "\u274c [V5]" in result.out and "\u274c [E20]" in result.out


def test_07_ui_a_list_only_report_is_not_a_pass(lab: Lab) -> None:
    """`--list` reports every test as skipped; such a report must never read as success."""
    report = lab.tmp / "report.json"
    report.write_text(json.dumps({"suites": [], "stats": {"expected": 0, "skipped": 2, "unexpected": 0, "flaky": 0}}))
    result = run_ui(lab, env={"STUB_NPX_REPORT": str(report)})
    assert result.rc == 1


def test_07_ui_unreadable_report_is_failure(lab: Lab) -> None:
    report = lab.tmp / "report.json"
    report.write_text("this is not json", encoding="utf-8")
    result = run_ui(lab, env={"STUB_NPX_REPORT": str(report), "STUB_NPX_RC": "1"})
    assert result.rc == 1 and "\u274c [E25]" in result.out


def test_07_ui_npx_failure_is_failure_even_when_the_report_looks_fine(lab: Lab) -> None:
    result = run_ui(lab, env={"STUB_NPX_RC": "1"})
    assert result.rc == 1
    assert "npx exited 1" in result.out


def test_07_ui_items_follow_the_expected_state(lab: Lab) -> None:
    ok = {"arn-missing": ["V3"], "arn-present": ["V3", "V5"], "revoked": ["V6"]}
    for state, items in ok.items():
        local = Lab(lab.tmp / state)
        result = run_ui(local, expect=state)
        assert result.rc == 0, result.out + result.err
        for item in [*items, "E20", "E25"]:
            assert f"\u2705 [{item}]" in result.out, (state, item)


def test_07_ui_script_id_is_the_ui_variant(lab: Lab) -> None:
    result = run_ui(lab)
    assert result.rc == 0
    assert {r["script"] for r in lab.records()} == {"07-ui"}
    assert all(r["mode"] == "apply" for r in lab.records())


# -- credentials -----------------------------------------------------------------


def write_cred_file(lab: Lab, user: str, password: str, mode: int = 0o600) -> Path:
    path = lab.root / "portal-user.local.env"
    path.write_text(f"PORTAL_USER={user}\nPORTAL_PASSWORD={password}\n", encoding="utf-8")
    path.chmod(mode)
    return path


def test_07_ui_credentials_precedence(lab: Lab) -> None:
    write_cred_file(lab, "file-user@example.com", "FilePassword-1!")
    result = run_ui(lab, creds=True)
    assert result.rc == 0, result.out + result.err
    env = pt.calls_of_name(lab.external_records(), "npx")[0]["env"]
    assert env["PORTAL_USER"] == pt.USERNAME and env["PORTAL_PASSWORD_sha256"] == pt.sha256(pt.PASSWORD)
    assert "credentials: environment" in result.out

    second = Lab(lab.tmp / "file-only")
    write_cred_file(second, "file-user@example.com", "FilePassword-1!")
    result = run_ui(second, creds=False)
    assert result.rc == 0, result.out + result.err
    env = pt.calls_of_name(second.external_records(), "npx")[0]["env"]
    assert env["PORTAL_USER"] == "file-user@example.com"
    assert env["PORTAL_PASSWORD_sha256"] == pt.sha256("FilePassword-1!")
    assert "credentials: file" in result.out
    assert pt.calls_of_name(second.external_records(), "make") == []


def test_07_ui_credentials_file_wider_than_0600_warns(lab: Lab) -> None:
    write_cred_file(lab, "file-user@example.com", "FilePassword-1!", mode=0o644)
    result = run_ui(lab, creds=False)
    assert result.rc == 0, result.out + result.err
    assert "\u26a0 [-] portal-user.local.env is readable" in result.out
    assert "FilePassword-1!" not in result.out + result.err


def test_07_ui_provision_user_saves_the_password_with_mode_0600_and_reuses_it(lab: Lab) -> None:
    result = run_ui(lab, creds=False, provision=True)
    assert result.rc == 0, result.out + result.err
    path = lab.root / "portal-user.local.env"
    assert path.read_text(encoding="utf-8") == f"PORTAL_USER={pt.USERNAME}\nPORTAL_PASSWORD={pt.PASSWORD}\n"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    again = run_ui(lab, creds=False, provision=True)
    assert again.rc == 0, again.out + again.err
    assert len(pt.calls_of_name(lab.external_records(), "make")) == 1, "the saved credentials are used the second time"


def test_07_ui_provision_user_with_a_wide_umask_still_writes_0600(lab: Lab) -> None:
    path = write_cred_file(lab, "old@example.com", "OldPassword-1!", mode=0o666)
    path.unlink()
    result = run_ui(lab, creds=False, provision=True)
    assert result.rc == 0, result.out + result.err
    assert stat.S_IMODE((lab.root / "portal-user.local.env").stat().st_mode) == 0o600


def test_07_ui_existing_user_without_password_prints_recovery(lab: Lab) -> None:
    result = run_ui(lab, creds=False, provision=True, env={"STUB_MAKE_MODE": "exists"})
    assert result.rc == 1, result.out + result.err
    assert "admin-delete-user" in result.err
    assert "us-east-1_StubPool" in result.err and "ap-northeast-1" in result.err
    assert pt.USERNAME in result.err
    assert "--provision-user --apply" in result.err
    assert not re.search(r"--password|--permanent|set-user-password", result.err), (
        "no way to put a password on a command line"
    )
    assert not (lab.root / "portal-user.local.env").exists()
    assert not any(line.startswith("npx playwright test") for line in lab.external_calls())


def test_07_ui_provision_output_without_a_password_line_is_refused(lab: Lab) -> None:
    result = run_ui(lab, creds=False, provision=True, env={"STUB_MAKE_MODE": "garbled"})
    assert result.rc == 1
    assert "print format" in result.err
    assert not (lab.root / "portal-user.local.env").exists()


def test_07_ui_provision_failure_shows_the_output_without_a_password_line(lab: Lab) -> None:
    result = run_ui(lab, creds=False, provision=True, env={"STUB_MAKE_MODE": "fail"})
    assert result.rc == 1 and "exit 2" in result.err


def test_provision_output_contract(lab: Lab) -> None:
    """07 depends on two strings printed by scripts/portal_provision_demo_user.py; a change must fail here."""
    source = (LAB_SRC.parents[1] / "scripts" / "portal_provision_demo_user.py").read_text(encoding="utf-8")
    assert 'print(f"  password  {password}")' in source
    assert "already exists; password unchanged" in source
    created = "pool     p\n" + "  username  u\n" + "  password  Aa1!bB2#cC3-dD4w\n" + "Shown once\n"
    assert sc.helpers.parse_provision_output(created) == ("password", "Aa1!bB2#cC3-dD4w")
    existing = "user     u already exists; password unchanged\n"
    assert sc.helpers.parse_provision_output(existing) == ("exists", "")
    for bad in ("", "password  x\n", "  password  a\n  password  b\n", "nothing useful"):
        with pytest.raises(ValueError):
            sc.helpers.parse_provision_output(bad)
    # The fake make prints the same format.
    stub_out = (LAB_SRC / "tests" / "stubs" / "external" / "make_stub.py").read_text(encoding="utf-8")
    assert "  password  " in stub_out and "already exists; password unchanged" in stub_out


def test_provision_error_messages_never_contain_output_text() -> None:
    with pytest.raises(ValueError) as caught:
        sc.helpers.parse_provision_output("  password  a\n  password  SecretValue-1\n")
    assert "SecretValue-1" not in str(caught.value)


# -- H22 -------------------------------------------------------------------------


def files_with(lab: Lab, secret: str, skip: tuple[Path, ...] = ()) -> list[Path]:
    """Every file under the test directory whose bytes contain ``secret`` (inputs of the fakes excluded)."""
    found = []
    for path in lab.tmp.rglob("*"):
        if path.is_file() and path not in skip and secret.encode() in path.read_bytes():
            found.append(path)
    return found


def assert_password_nowhere(lab: Lab, result: Result, secret: str, skip: tuple[Path, ...] = ()) -> None:
    """The password is on no command line, not in 07's output, and in no file but the credentials file."""
    assert secret not in result.out and secret not in result.err, "07 printed the password"
    for line in lab.external_calls():
        assert secret not in line, f"the password is on a command line: {line}"
    for record in lab.external_records():
        assert secret not in json.dumps(record), "a recorded call holds the password"
    for call in result.calls:
        assert secret not in json.dumps(call), "an aws call holds the password"
    holders = [p.name for p in files_with(lab, secret, skip)]
    assert holders in ([], ["portal-user.local.env"]), f"files holding the password: {holders}"


def test_07_password_never_in_argv_stdout_stderr_or_logs(lab: Lab) -> None:
    """Even when the spec output quotes the filled-in value, nothing but portal-user.local.env keeps it."""
    leak_report = lab.tmp / "leaky-report.json"
    leak_report.write_text(pt.report(extra=f" (filled in {pt.PASSWORD})"), encoding="utf-8")
    result = run_ui(
        lab,
        creds=False,
        provision=True,
        env={"STUB_NPX_REPORT": str(leak_report), "STUB_NPX_STDERR": f"locator.fill: fill('{pt.PASSWORD}')\n"},
        portal={"node_modules": False, "chromium": False},
    )
    assert result.rc == 0, result.out + result.err
    assert "<redacted>" in (lab.root / "ui-result.local.json").read_text(encoding="utf-8")
    assert "<redacted>" in result.err
    assert_password_nowhere(lab, result, pt.PASSWORD, skip=(leak_report,))
    assert [p.name for p in files_with(lab, pt.PASSWORD, skip=(leak_report,))] == ["portal-user.local.env"]
    assert stat.S_IMODE((lab.root / "portal-user.local.env").stat().st_mode) == 0o600
    assert pt.PASSWORD not in (lab.root / "lab-run.local.jsonl").read_text(encoding="utf-8")


def test_07_password_from_the_environment_is_not_stored_anywhere(lab: Lab) -> None:
    result = run_ui(lab)
    assert result.rc == 0, result.out + result.err
    assert_password_nowhere(lab, result, pt.PASSWORD)
    assert files_with(lab, pt.PASSWORD) == []


def password_on_command_line(text: str) -> list[str]:
    """Lines of the script text that could put the password into the argv of a process."""
    found = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#"):
            continue
        # A leading `VAR=...` assignment names its target on the left; a variable called
        # UI_PASSWORD there is the destination of a value captured from stdout, not an
        # argument. Scan only what follows the assignment for a PASSWORD reference.
        scanned = re.sub(r"^[A-Za-z_][A-Za-z0-9_]*=", "", line)
        if ("run_external" in scanned or "lab_py" in scanned) and "PASSWORD" in scanned:
            found.append(line)
        elif re.search(r"\benv\s+[\"']?[A-Z_]*PASSWORD=", line) or "--password" in line:
            found.append(line)
    return found


def test_07_script_never_passes_the_password_as_an_argument() -> None:
    assert password_on_command_line((LAB_SRC / "scripts" / SCRIPT).read_text(encoding="utf-8")) == []


def test_password_checks_detect_the_env_prefix_and_a_leaking_argument(lab: Lab) -> None:
    """Negative controls: `env VAR=value npx ...` and a password argument must both be caught."""
    text = (LAB_SRC / "scripts" / SCRIPT).read_text(encoding="utf-8")
    needle = "run_external npx playwright test 'shared-vault-lab\\.spec\\.ts$' --reporter=json"
    assert needle in text
    env_prefix = text.replace(
        needle, 'run_external env "PORTAL_PASSWORD=$UI_PASSWORD" ' + needle.removeprefix("run_external ")
    )
    assert password_on_command_line(env_prefix), "the static check misses an env prefix"
    # A leaking argument reaches the fake npx, so the dynamic check sees it as well.
    leaking = text.replace(needle, needle + ' "--token=$UI_PASSWORD"')
    assert password_on_command_line(leaking)
    lab.install_script(SCRIPT, leaking)
    result = run_ui(lab)
    with pytest.raises(AssertionError):
        assert_password_nowhere(lab, result, pt.PASSWORD)


# --------------------------------------------------------------------------
# Every external command goes through run_external; echo substitutes fail
# --------------------------------------------------------------------------

EXTERNAL_ROWS = [
    (row.run, row.literal)
    for row in expected.EXPECTED_CALLS[SCRIPT]
    if row.kind == "external" and row.run in ("deploy", "deploy-fresh", "deploy-existing", "ui", "ui-provision")
]


def test_07_calls_no_external_command_except_through_run_external() -> None:
    text = (LAB_SRC / "scripts" / SCRIPT).read_text(encoding="utf-8")
    code = [line.strip() for line in text.splitlines() if not line.strip().startswith("#")]
    for line in code:
        assert not re.match(
            r"^(?:\(?\s*)?(?:cd [^&]*&& )?(?:sandbox\.sh|\./scripts/sandbox\.sh|npx|npm|make|node)\b", line
        ), line
    assert text.count("run_external ") >= 6


@pytest.mark.parametrize(("run", "literal"), EXTERNAL_ROWS)
def test_echo_substitution_fails_for_external_calls(lab: Lab, run: str, literal: str) -> None:
    """Replace one real external call (sandbox.sh, npx, npm, make, node) with echo: the run must fail."""
    text = (LAB_SRC / "scripts" / SCRIPT).read_text(encoding="utf-8")
    lab.install_script(SCRIPT, substitute_with_echo(text, literal))
    with pytest.raises(AssertionError):
        expected.check_run(SCRIPT, run, lab, allow_stub_failure=True)


@pytest.mark.parametrize("run", ["deploy", "ui", "ui-provision"])
def test_echo_only_07_is_rejected_in_each_mode(lab: Lab, run: str) -> None:
    """A script that only prints the commands it would run records no external call."""
    lines = ["#!/bin/bash"]
    for row in expected.EXPECTED_CALLS[SCRIPT]:
        if row.run == run and row.kind == "external":
            lines.append(f"echo {row.flags['needle']}")
    lab.install_script(SCRIPT, "\n".join(lines) + "\n")
    with pytest.raises(AssertionError):
        expected.check_run(SCRIPT, run, lab, allow_stub_failure=True)


def test_07_header_and_modes_are_documented() -> None:
    text = (LAB_SRC / "scripts" / SCRIPT).read_text(encoding="utf-8")
    for mode in ("--print", "--check", "--deploy", "--ui"):
        assert re.search(rf"^#   07_portal_config\.sh {re.escape(mode)}", text, re.M), mode
    status_re = re.compile(
        r"^# Real-environment run: (not yet done|recorded (\[[VE]\d+\])+(; not recorded (\[[VE]\d+\])+)?)"
        r" \(status source: docs/verification-record\.md\)$"
    )
    assert status_re.match(text.splitlines()[1]), text.splitlines()[1]
