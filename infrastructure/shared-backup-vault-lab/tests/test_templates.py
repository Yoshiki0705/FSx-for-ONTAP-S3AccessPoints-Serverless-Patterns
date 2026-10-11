"""The three CloudFormation templates and their parameter examples.

Nothing here deploys anything. These tests read the templates (with cfn-lint's own
YAML loader, so intrinsic functions survive as dictionaries) and run the pinned
cfn-lint. Whether CloudFormation accepts and runs the templates is not yet run on
real environment.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from cfnlint.decode import cfn_yaml
from lab_testlib import LAB_SRC, Lab

CFN_DIR = LAB_SRC / "cloudformation"
PARAMS_DIR = CFN_DIR / "parameters"
COMMON = LAB_SRC / "scripts" / "lib" / "common.sh"
NAMES = ("owner-base", "owner-lag-share", "recipient-restore")
STATUS_RE = re.compile(
    r"^# Real-environment run: (not yet done|recorded( \[[VE]\d+\])+(; not recorded( \[[VE]\d+\])+)?)"
    r" \(status source: docs/verification-record\.md\)$"
)

# Resource types each template creates. The README "types created" list is compared
# with this set by a later test.
EXPECTED_TYPES = {
    "owner-base": {
        "AWS::KMS::Key",
        "AWS::KMS::Alias",
        "AWS::FSx::FileSystem",
        "AWS::FSx::StorageVirtualMachine",
        "AWS::FSx::Volume",
        "AWS::Backup::BackupVault",
        "AWS::IAM::Role",
    },
    "owner-lag-share": {"AWS::Backup::LogicallyAirGappedBackupVault", "AWS::RAM::ResourceShare"},
    "recipient-restore": {"AWS::IAM::Role", "AWS::FSx::FileSystem", "AWS::FSx::StorageVirtualMachine"},
}

# cfn-lint findings at Warning level or above that are accepted, with the reason.
TOLERATED = {
    "W3011": (
        "The LAG vault sets UpdateReplacePolicy: Retain only. An empty vault must be deletable with "
        "the stack, so no DeletionPolicy is set."
    ),
}


def load(name: str) -> dict[str, Any]:
    """Load a template with cfn-lint's YAML loader."""
    return json.loads(json.dumps(cfn_yaml.load(str(CFN_DIR / f"{name}.yaml"))))


def walk(node: Any):
    """Yield every (key, value) pair in a nested structure."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield key, value
            yield from walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk(item)


@pytest.fixture(params=NAMES)
def template(request: pytest.FixtureRequest) -> tuple[str, dict[str, Any]]:
    return request.param, load(request.param)


# --------------------------------------------------------------------------
# Content rules
# --------------------------------------------------------------------------


def test_each_template_starts_with_the_status_line(template: tuple[str, dict[str, Any]]) -> None:
    name, _ = template
    first = (CFN_DIR / f"{name}.yaml").read_text(encoding="utf-8").splitlines()[0]
    assert STATUS_RE.match(first), first


def test_the_lab_templates_are_exactly_the_three_expected() -> None:
    assert sorted(p.stem for p in CFN_DIR.glob("*.yaml")) == sorted(NAMES)
    assert sorted(p.stem.replace(".example", "") for p in PARAMS_DIR.glob("*.example.json")) == sorted(NAMES)


def test_resource_types_are_the_documented_set(template: tuple[str, dict[str, Any]]) -> None:
    name, body = template
    assert {r["Type"] for r in body["Resources"].values()} == EXPECTED_TYPES[name]


def test_no_template_configures_snaplock_or_a_vault_lock(template: tuple[str, dict[str, Any]]) -> None:
    _, body = template
    keys = {key for key, _ in walk(body)}
    assert "SnaplockConfiguration" not in keys
    assert "LockConfiguration" not in keys


def test_the_key_and_alias_are_retained() -> None:
    body = load("owner-base")
    for logical in ("FsKey", "FsKeyAlias"):
        assert body["Resources"][logical]["DeletionPolicy"] == "Retain"
        assert body["Resources"][logical]["UpdateReplacePolicy"] == "Retain"
    assert body["Resources"]["FsKey"]["Properties"]["EnableKeyRotation"] is True


def test_the_file_system_uses_the_customer_managed_key_and_no_automatic_backup() -> None:
    props = load("owner-base")["Resources"]["FileSystem"]["Properties"]
    assert props["KmsKeyId"] == {"Fn::GetAtt": ["FsKey", "Arn"]}
    assert props["OntapConfiguration"]["AutomaticBackupRetentionDays"] == 0
    assert props["OntapConfiguration"]["DeploymentType"] == "SINGLE_AZ_1"
    assert "PreferredSubnetId" not in props["OntapConfiguration"]
    assert "FsxAdminPassword" not in props["OntapConfiguration"]


def test_the_recipient_file_system_has_no_key_and_is_conditional() -> None:
    body = load("recipient-restore")
    fs = body["Resources"]["NewFileSystem"]
    assert fs["Condition"] == "CreateFileSystem"
    assert "KmsKeyId" not in fs["Properties"]
    assert body["Conditions"]["CreateFileSystem"] == {"Fn::Equals": [{"Ref": "ExistingFileSystemId"}, ""]}


def test_the_standard_vault_is_an_unlocked_backup_vault() -> None:
    vault = load("owner-base")["Resources"]["StandardVault"]
    assert vault["Type"] == "AWS::Backup::BackupVault"
    assert "LockConfiguration" not in vault["Properties"]


def test_the_lag_vault_min_and_max_retention_are_the_same_parameter() -> None:
    props = load("owner-lag-share")["Resources"]["LagVault"]["Properties"]
    assert props["MinRetentionDays"] == props["MaxRetentionDays"] == {"Ref": "RetentionDays"}
    assert load("owner-lag-share")["Resources"]["LagVault"]["UpdateReplacePolicy"] == "Retain"


def test_the_lag_vault_has_no_encryption_key_so_an_aws_owned_key_is_used() -> None:
    assert "EncryptionKeyArn" not in load("owner-lag-share")["Resources"]["LagVault"]["Properties"]


def test_retention_parameters_have_a_range_and_no_default() -> None:
    params = load("owner-lag-share")["Parameters"]
    for name in ("RetentionDays", "AcknowledgeRetentionDays"):
        assert params[name]["Type"] == "Number"
        assert (params[name]["MinValue"], params[name]["MaxValue"]) == (7, 35)
        assert "Default" not in params[name]


def test_the_template_range_matches_the_script_range(lab: Lab) -> None:
    """validate_retention_days accepts exactly the range the template allows."""
    params = load("owner-lag-share")["Parameters"]["RetentionDays"]
    low, high = params["MinValue"], params["MaxValue"]
    for value, ok in ((low, True), (low - 1, False), (high, True), (high + 1, False)):
        result = lab.bash(f"validate_retention_days {value}")
        assert (result.rc == 0) is ok, (value, result.err)


def test_a_rule_asks_for_the_retention_twice() -> None:
    rules = load("owner-lag-share")["Rules"]
    assertions = [a for rule in rules.values() for a in rule["Assertions"]]
    assert any(
        a["Assert"] == {"Fn::Equals": [{"Ref": "RetentionDays"}, {"Ref": "AcknowledgeRetentionDays"}]}
        for a in assertions
    )


def test_the_share_is_conditional_on_the_switch() -> None:
    body = load("owner-lag-share")
    assert body["Resources"]["VaultShare"]["Condition"] == "ShareOn"
    assert body["Conditions"]["ShareOn"] == {"Fn::Equals": [{"Ref": "ShareEnabled"}, "true"]}
    assert body["Parameters"]["ShareEnabled"]["Default"] == "true"


def test_the_share_lists_the_vault_arn_and_the_recipient() -> None:
    props = load("owner-lag-share")["Resources"]["VaultShare"]["Properties"]
    assert props["ResourceArns"] == [{"Fn::GetAtt": ["LagVault", "BackupVaultArn"]}]
    assert props["Principals"] == [{"Ref": "RecipientAccountId"}]
    assert "PermissionArns" not in props


def test_no_iam_role_has_a_fixed_name(template: tuple[str, dict[str, Any]]) -> None:
    """A RoleName would need CAPABILITY_NAMED_IAM and break a second deployment."""
    _, body = template
    for logical, resource in body["Resources"].items():
        if resource["Type"] == "AWS::IAM::Role":
            assert "RoleName" not in resource["Properties"], logical


def test_taggable_resources_carry_the_project_and_cleanup_tags(template: tuple[str, dict[str, Any]]) -> None:
    _, body = template
    for logical, resource in body["Resources"].items():
        if resource["Type"] == "AWS::KMS::Alias":
            continue
        props = resource["Properties"]
        tags = props.get("Tags")
        if tags is not None:
            as_map = {t["Key"]: t["Value"] for t in tags}
        else:
            as_map = props.get("BackupVaultTags", {})
        assert set(as_map) >= {"Project", "Cleanup"}, logical
        assert as_map["Project"] == {"Ref": "LabTag"}, logical


def test_lag_vault_tags_are_a_string_map_not_a_list() -> None:
    """A list of Key/Value pairs on BackupVaultTags is rejected by cfn-lint (E3002)."""
    tags = load("owner-lag-share")["Resources"]["LagVault"]["Properties"]["BackupVaultTags"]
    assert isinstance(tags, dict)
    assert tags["Cleanup"] == "delete-when-done"


def test_the_backup_role_may_use_only_the_lab_key() -> None:
    role = load("owner-base")["Resources"]["BackupRole"]["Properties"]
    assert role["AssumeRolePolicyDocument"]["Statement"][0]["Principal"] == {"Service": "backup.amazonaws.com"}
    statements = role["Policies"][0]["PolicyDocument"]["Statement"]
    assert all(s["Resource"] == {"Fn::GetAtt": ["FsKey", "Arn"]} for s in statements)
    grant = next(s for s in statements if s["Action"] == "kms:CreateGrant")
    assert grant["Condition"] == {"Bool": {"kms:GrantIsForAWSResource": "true"}}
    assert all(s["Action"] != "kms:*" and s["Resource"] != "*" for s in statements)


def test_the_output_names_the_scripts_read_exist() -> None:
    assert set(load("owner-base")["Outputs"]) == {
        "KeyArn",
        "FileSystemId",
        "SvmId",
        "VolumeId",
        "VolumeArn",
        "StandardVaultName",
        "BackupRoleArn",
    }
    assert set(load("owner-lag-share")["Outputs"]) == {"LagVaultArn", "LagVaultName", "ResourceShareArn"}
    assert set(load("recipient-restore")["Outputs"]) == {"RestoreRoleArn", "FileSystemId", "RestoreSvmId"}


def test_the_volume_arn_output_is_the_resource_arn_attribute() -> None:
    assert load("owner-base")["Outputs"]["VolumeArn"]["Value"] == {"Fn::GetAtt": ["Volume", "ResourceARN"]}


def test_templates_and_examples_contain_no_non_ascii_text() -> None:
    for path in [*CFN_DIR.glob("*.yaml"), *PARAMS_DIR.glob("*.json")]:
        text = path.read_text(encoding="utf-8")
        assert all(ord(ch) < 128 for ch in text), path.name


def test_template_name_patterns_agree_with_the_script_validation() -> None:
    """The scripts and the templates must reject the same malformed names."""
    common = COMMON.read_text(encoding="utf-8")

    def script_pattern(variable: str) -> str:
        found = re.search(rf"^_lab_validate {variable} '([^']+)'", common, re.M)
        assert found, variable
        return found.group(1)

    base = load("owner-base")["Parameters"]
    lag = load("owner-lag-share")["Parameters"]
    recipient = load("recipient-restore")["Parameters"]
    assert base["LabTag"]["AllowedPattern"] == script_pattern("LAB_TAG")
    assert base["SvmName"]["AllowedPattern"] == script_pattern("LAB_SVM_NAME")
    assert base["VolumeName"]["AllowedPattern"] == script_pattern("LAB_VOLUME_NAME")
    assert recipient["RestoreSvmName"]["AllowedPattern"] == script_pattern("LAB_RESTORE_SVM_NAME")
    assert lag["ShareName"]["AllowedPattern"] == script_pattern("LAB_SHARE_NAME")
    common_vault = re.search(r"^_lab_re_vault='([^']+)'", common, re.M)
    assert common_vault
    assert base["StandardVaultName"]["AllowedPattern"] == common_vault.group(1)
    assert lag["LagVaultName"]["AllowedPattern"] == common_vault.group(1)
    assert lag["RecipientAccountId"]["AllowedPattern"] == "^[0-9]{12}$"


# --------------------------------------------------------------------------
# LAG vault ARN: GetAtt, never Ref
# --------------------------------------------------------------------------


def refs_in_arn_positions(body: dict[str, Any], logical_id: str) -> list[str]:
    """Find places where ``Ref: logical_id`` is used where an ARN is required.

    For ``AWS::Backup::LogicallyAirGappedBackupVault`` a Ref returns the vault NAME.
    Checked positions: any resource property whose name contains ``Arn``
    (``ResourceArns``, ``PermissionArns``, ...) and any output whose name ends in
    ``Arn``.

    Args:
        body: Parsed template.
        logical_id: Logical id of the resource.

    Returns:
        Human-readable locations of the misuse (empty when none).
    """
    bad: list[str] = []
    target = {"Ref": logical_id}

    def contains_target(node: Any) -> bool:
        if node == target:
            return True
        if isinstance(node, dict):
            return any(contains_target(value) for value in node.values())
        if isinstance(node, list):
            return any(contains_target(item) for item in node)
        return False

    for logical, resource in body.get("Resources", {}).items():
        for key, value in walk(resource.get("Properties", {})):
            if "Arn" in key and contains_target(value):
                bad.append(f"Resources.{logical}.{key}")
    for name, output in body.get("Outputs", {}).items():
        if name.endswith("Arn") and contains_target(output.get("Value")):
            bad.append(f"Outputs.{name}")
    return bad


def test_the_lag_vault_arn_comes_from_getatt_never_ref() -> None:
    body = load("owner-lag-share")
    assert body["Outputs"]["LagVaultArn"]["Value"] == {"Fn::GetAtt": ["LagVault", "BackupVaultArn"]}
    assert refs_in_arn_positions(body, "LagVault") == []


def test_ref_in_an_arn_position_is_detected() -> None:
    """Negative control: the check reports a Ref used where an ARN is needed."""
    broken = load("owner-lag-share")
    broken["Resources"]["VaultShare"]["Properties"]["ResourceArns"] = [{"Ref": "LagVault"}]
    broken["Outputs"]["LagVaultArn"]["Value"] = {"Ref": "LagVault"}
    found = refs_in_arn_positions(broken, "LagVault")
    assert "Resources.VaultShare.ResourceArns" in found
    assert "Outputs.LagVaultArn" in found


# --------------------------------------------------------------------------
# Parameter examples (the direct-deploy form)
# --------------------------------------------------------------------------


def cli_cloudformation_form_accepts(data: Any) -> bool:
    """The AWS CLI's `deploy --parameter-overrides file://` test for the CloudFormation form.

    Mirrors CloudFormationLikeParameterOverrideParser.can_parse in AWS CLI 2.36.5
    (read from the installed source): every element has ParameterKey and
    ParameterValue and at most two keys.
    """
    return isinstance(data, list) and all(
        isinstance(p, dict) and "ParameterKey" in p and "ParameterValue" in p and len(p) <= 2 for p in data
    )


@pytest.mark.parametrize("name", NAMES)
def test_example_parameters_have_the_cloudformation_form(name: str) -> None:
    data = json.loads((PARAMS_DIR / f"{name}.example.json").read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert cli_cloudformation_form_accepts(data)
    for item in data:
        assert set(item) == {"ParameterKey", "ParameterValue"}
        assert isinstance(item["ParameterKey"], str) and isinstance(item["ParameterValue"], str)


@pytest.mark.parametrize("name", NAMES)
def test_example_parameters_match_the_template(name: str) -> None:
    declared = load(name)["Parameters"]
    data = json.loads((PARAMS_DIR / f"{name}.example.json").read_text(encoding="utf-8"))
    given = [item["ParameterKey"] for item in data]
    assert len(given) == len(set(given)), "a key is listed twice"
    assert set(given) <= set(declared), sorted(set(given) - set(declared))
    required = {k for k, v in declared.items() if "Default" not in v}
    assert required <= set(given), sorted(required - set(given))


@pytest.mark.parametrize("name", NAMES)
def test_example_parameter_values_satisfy_the_template_constraints(name: str) -> None:
    declared = load(name)["Parameters"]
    for item in json.loads((PARAMS_DIR / f"{name}.example.json").read_text(encoding="utf-8")):
        spec, value = declared[item["ParameterKey"]], item["ParameterValue"]
        if "AllowedPattern" in spec:
            assert re.fullmatch(spec["AllowedPattern"], value), item
        if "AllowedValues" in spec:
            assert value in [str(v) for v in spec["AllowedValues"]], item
        if spec["Type"] == "Number":
            number = float(value)
            assert spec.get("MinValue", number) <= number <= spec.get("MaxValue", number), item


def test_the_cli_form_check_has_a_negative_control() -> None:
    assert not cli_cloudformation_form_accepts({"Parameters": {"A": "b"}})
    assert not cli_cloudformation_form_accepts([{"ParameterKey": "A"}])
    assert not cli_cloudformation_form_accepts([{"ParameterKey": "A", "ParameterValue": "b", "Extra": "c"}])
    assert cli_cloudformation_form_accepts([{"ParameterKey": "A", "ParameterValue": "b"}])


def test_example_values_are_placeholders_not_real_identifiers() -> None:
    text = "".join(p.read_text(encoding="utf-8") for p in PARAMS_DIR.glob("*.json"))
    assert re.findall(r"\b\d{12}\b", text) == ["444455556666"]
    assert "@" not in text and "/Users/" not in text


# --------------------------------------------------------------------------
# cfn-lint at Warning level
# --------------------------------------------------------------------------


def lint_findings(paths: list[Path]) -> list[dict[str, Any]]:
    """Run the pinned cfn-lint with its default exit-code settings and return findings.

    Args:
        paths: Templates to lint.

    Returns:
        Parsed JSON findings (all levels).
    """
    executable = Path(sys.executable).parent / "cfn-lint"
    command = str(executable) if executable.exists() else shutil.which("cfn-lint")
    assert command, "cfn-lint is a pinned dev dependency and must be installed"
    proc = subprocess.run([command, "--format", "json", *map(str, paths)], capture_output=True, text=True, check=False)
    assert proc.returncode in (0, 2, 4, 6, 8, 10, 12, 14), proc.stderr
    return json.loads(proc.stdout or "[]")


def untolerated(findings: list[dict[str, Any]]) -> list[str]:
    """Error and Warning findings that are not listed in TOLERATED.

    Args:
        findings: Output of :func:`lint_findings`.

    Returns:
        ``"<rule> <message>"`` entries.
    """
    return [
        f"{f['Rule']['Id']} {f['Message']}"
        for f in findings
        if f["Level"] in ("Error", "Warning") and f["Rule"]["Id"] not in TOLERATED
    ]


def test_cfn_lint_reports_no_error_or_warning_beyond_the_tolerated_set() -> None:
    """`make lint-cfn` ignores warnings; a conditional resource used unconditionally is one."""
    findings = lint_findings([CFN_DIR / f"{name}.yaml" for name in NAMES])
    assert untolerated(findings) == []
    assert all(reason for reason in TOLERATED.values())


def test_the_tolerated_warning_is_still_emitted() -> None:
    """A TOLERATED entry that no longer fires is stale and must be removed."""
    findings = lint_findings([CFN_DIR / f"{name}.yaml" for name in NAMES])
    assert {f["Rule"]["Id"] for f in findings if f["Level"] == "Warning"} == set(TOLERATED)


CONDITIONAL_REF = """\
AWSTemplateFormatVersion: "2010-09-09"
Parameters:
  Make:
    Type: String
    Default: "yes"
    AllowedValues: ["yes", "no"]
Conditions:
  CreateIt: !Equals [!Ref Make, "yes"]
Resources:
  Optional:
    Type: AWS::SNS::Topic
    Condition: CreateIt
Outputs:
  TopicArn:
    Value: !Ref Optional
"""


def test_cfn_lint_check_flags_an_unconditional_ref_to_a_conditional_resource(tmp_path: Path) -> None:
    """Negative control: the warning-level check must go red on the shape it exists for."""
    broken = tmp_path / "broken.yaml"
    broken.write_text(CONDITIONAL_REF, encoding="utf-8")
    assert untolerated(lint_findings([broken])), "the unconditional Ref was not reported"
    fixed = tmp_path / "fixed.yaml"
    fixed.write_text(
        CONDITIONAL_REF.replace("Value: !Ref Optional", 'Value: !If [CreateIt, !Ref Optional, "none"]'),
        encoding="utf-8",
    )
    assert untolerated(lint_findings([fixed])) == []


def test_make_lint_cfn_exit_code_ignores_warnings_which_is_why_the_check_above_exists(tmp_path: Path) -> None:
    """Documents the gap: the blocking target passes on this warning, the test above does not."""
    broken = tmp_path / "broken.yaml"
    broken.write_text(CONDITIONAL_REF, encoding="utf-8")
    command = Path(sys.executable).parent / "cfn-lint"
    exe = str(command) if command.exists() else shutil.which("cfn-lint")
    assert exe
    proc = subprocess.run(
        [exe, "--non-zero-exit-code", "error", str(broken)], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, proc.stdout
