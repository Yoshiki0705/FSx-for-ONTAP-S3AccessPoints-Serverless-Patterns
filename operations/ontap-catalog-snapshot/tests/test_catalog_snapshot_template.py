"""Template checks for operations/ontap-catalog-snapshot (OPS7), and its registration points.

The first group reads the template as CloudFormation would: the lockout protections (no retry,
one run at a time, no wildcard resource on the secret) must be there, not only described.
The last tests make sure OPS7 is registered where the hand-written lists are, because those lists
silently skip anything that is not in them.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

PATTERN = Path(__file__).parent.parent
ROOT = PATTERN.parent.parent
TEMPLATE = PATTERN / "template.yaml"


class _Loader(yaml.SafeLoader):
    pass


def _tag(loader: yaml.Loader, suffix: str, node: yaml.Node) -> Any:
    if isinstance(node, yaml.ScalarNode):
        value: Any = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node, deep=True)
    else:
        value = loader.construct_mapping(node, deep=True)
    return {("Ref" if suffix == "Ref" else f"Fn::{suffix}"): value}


_Loader.add_multi_constructor("!", _tag)


@pytest.fixture(scope="module")
def tpl() -> dict[str, Any]:
    return yaml.load(TEMPLATE.read_text(), Loader=_Loader)  # noqa: S506 (safe subclass)


def function(tpl: dict[str, Any]) -> dict[str, Any]:
    return tpl["Resources"]["SnapshotFunction"]["Properties"]


def test_the_function_is_never_retried_and_never_run_twice_at_once(tpl: dict[str, Any]) -> None:
    props = function(tpl)
    assert props["EventInvokeConfig"]["MaximumRetryAttempts"] == 0
    assert props["ReservedConcurrentExecutions"] == 1
    rule = tpl["Resources"]["ScheduleRule"]["Properties"]
    assert rule["Targets"][0]["RetryPolicy"]["MaximumRetryAttempts"] == 0


def test_the_function_runs_in_the_vpc_on_arm64(tpl: dict[str, Any]) -> None:
    props = function(tpl)
    assert props["Architectures"] == ["arm64"]
    assert props["Runtime"] == "python3.13"
    assert set(props["VpcConfig"]) == {"SubnetIds", "SecurityGroupIds"}


def test_the_secret_policy_names_exactly_one_secret(tpl: dict[str, Any]) -> None:
    statements = [s for p in function(tpl)["Policies"] if isinstance(p, dict) for s in p["Statement"] if isinstance(s, dict)]
    secret = next(s for s in statements if s.get("Sid") == "ReadTheOneSecret")
    assert secret["Resource"] == {"Ref": "OntapSecretArn"}
    assert set(secret["Action"]) == {"secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"}


def test_no_statement_uses_a_wildcard_action_or_resource(tpl: dict[str, Any]) -> None:
    for p in function(tpl)["Policies"]:
        if not isinstance(p, dict):
            continue
        for s in p["Statement"]:
            if not isinstance(s, dict) or "Effect" not in s:
                continue
            actions = s["Action"] if isinstance(s["Action"], list) else [s["Action"]]
            assert not any(a == "*" or a.endswith(":*") for a in actions), s
            assert s["Resource"] != "*", s


def test_listing_is_limited_to_the_output_prefix(tpl: dict[str, Any]) -> None:
    statements = [s for p in function(tpl)["Policies"] if isinstance(p, dict) for s in p["Statement"] if isinstance(s, dict)]
    listing = next(s for s in statements if s.get("Sid") == "ListOutputPrefix")
    assert listing["Action"] == "s3:ListBucket"
    assert "s3:prefix" in listing["Condition"]["StringLike"], "ListBucket must be limited to the output prefix"


def test_the_schedule_is_switched_by_an_explicit_state_not_by_an_empty_string(tpl: dict[str, Any]) -> None:
    """sam deploy ignores an empty parameter value, which once created a schedule nobody asked for."""
    state = tpl["Parameters"]["ScheduleState"]
    assert state["AllowedValues"] == ["ENABLED", "DISABLED"]
    assert tpl["Conditions"]["HasSchedule"] == {"Fn::Equals": [{"Ref": "ScheduleState"}, "ENABLED"]}
    assert tpl["Parameters"]["ScheduleExpression"].get("MinLength") == 1, "an empty expression must not be accepted"
    assert tpl["Resources"]["ScheduleRule"]["Condition"] == "HasSchedule"
    assert tpl["Resources"]["SchedulePermission"]["Condition"] == "HasSchedule"


def test_the_output_bucket_keeps_history_and_survives_stack_deletion(tpl: dict[str, Any]) -> None:
    bucket = tpl["Resources"]["OutputBucket"]
    assert bucket["DeletionPolicy"] == "Retain" and bucket["UpdateReplacePolicy"] == "Retain"
    props = bucket["Properties"]
    assert props["VersioningConfiguration"]["Status"] == "Enabled"
    assert props["PublicAccessBlockConfiguration"] == dict.fromkeys(
        ("BlockPublicAcls", "BlockPublicPolicy", "IgnorePublicAcls", "RestrictPublicBuckets"), True
    )
    assert props["BucketEncryption"]["ServerSideEncryptionConfiguration"][0]["ServerSideEncryptionByDefault"]["SSEAlgorithm"] == "aws:kms"


def test_every_environment_variable_the_handler_reads_is_set_by_the_template(tpl: dict[str, Any]) -> None:
    source = (PATTERN / "functions" / "snapshot" / "handler.py").read_text()
    read = set(re.findall(r'os\.environ(?:\.get)?\(?\[?"([A-Z_]+)"', source)) - {"LOG_LEVEL"}
    set_by_template = set(function(tpl)["Environment"]["Variables"])
    assert read <= set_by_template, f"read but never set: {sorted(read - set_by_template)}"


def test_the_handler_directory_holds_only_the_handler() -> None:
    names = {p.name for p in (TEMPLATE.parent / "functions" / "snapshot").iterdir() if p.name != "__pycache__"}
    assert names == {"handler.py"}


def test_the_template_has_no_cfn_lint_findings_at_all() -> None:
    """CI runs cfn-lint with no tolerance, while `make lint` accepts exit codes up to 12 for the older templates.

    A warning here passes `make test` and still fails the pull request, so this test asks for exit code 0.
    """
    import shutil
    import subprocess
    import sys

    exe = shutil.which("cfn-lint") or str(Path(sys.executable).parent / "cfn-lint")
    if not Path(exe).exists():
        pytest.skip("cfn-lint is not installed")
    done = subprocess.run([exe, str(TEMPLATE)], capture_output=True, text=True, cwd=ROOT)  # noqa: S603
    assert done.returncode == 0, done.stdout + done.stderr


def test_ops7_is_registered_in_the_hand_written_lists() -> None:
    """The lint list, the test target and the per-pattern test list are written by hand."""
    makefile = (ROOT / "Makefile").read_text()
    assert "operations/ontap-catalog-snapshot/template.yaml" in makefile, "lint-cfn-ops must list the OPS7 template"
    assert "test-ops7:" in makefile and "operations/ontap-catalog-snapshot/tests/" in makefile
    dirs = (ROOT / "pattern-test-dirs.txt").read_text().splitlines()
    assert "operations/ontap-catalog-snapshot" in dirs
    ops_readme = (ROOT / "operations" / "README.md").read_text()
    assert "OPS7" in ops_readme and "ontap-catalog-snapshot/" in ops_readme


def test_the_readme_states_the_credential_exception_and_the_limits() -> None:
    """The user-facing limits are part of the pattern: they must be in the README, not only in review notes."""
    text = (PATTERN / "README.md").read_text()
    for needle in ("fsxadmin", "D28", "次の週", "ロック", "EventBridge", "unavailable", "6691623"):
        assert needle in text, f"README.md must mention {needle!r}"
    head = text[: text.index("\n## ", text.index("\n## ") + 1)]
    assert "D28" in head, "the D28 exception must appear near the top, not in a footnote"


# --- Security group: the template can create the one the function needs -------------------------


def _sg_egress(tpl: dict[str, Any]) -> list[Any]:
    return tpl["Resources"]["FunctionSecurityGroup"]["Properties"]["SecurityGroupEgress"]


def test_the_security_group_is_created_by_default_and_the_function_uses_it(tpl: dict[str, Any]) -> None:
    assert tpl["Parameters"]["CreateSecurityGroup"]["Default"] == "true"
    assert tpl["Parameters"]["CreateSecurityGroup"]["AllowedValues"] == ["true", "false"]
    assert tpl["Resources"]["FunctionSecurityGroup"]["Condition"] == "CreateSg"
    ids = function(tpl)["VpcConfig"]["SecurityGroupIds"]
    assert ids["Fn::If"][0] == "CreateSg" and ids["Fn::If"][1] == [{"Ref": "FunctionSecurityGroup"}]


def test_the_created_group_opens_only_https_and_nothing_inbound(tpl: dict[str, Any]) -> None:
    props = tpl["Resources"]["FunctionSecurityGroup"]["Properties"]
    assert not props.get("SecurityGroupIngress"), "the function accepts no inbound traffic"
    rules = [r["Fn::If"][1] if isinstance(r, dict) and "Fn::If" in r else r for r in _sg_egress(tpl)]
    assert rules, "an explicit egress list is what removes the default allow-all rule"
    for r in rules:
        assert (r["IpProtocol"], r["FromPort"], r["ToPort"]) == ("tcp", 443, 443), r


def test_egress_to_the_internet_is_a_switch_that_is_off_by_default(tpl: dict[str, Any]) -> None:
    assert tpl["Parameters"]["AllowOutboundHttpsToInternet"]["Default"] == "false"
    open_rules = [
        r for r in _sg_egress(tpl) if isinstance(r, dict) and "Fn::If" in r and r["Fn::If"][1].get("CidrIp") == "0.0.0.0/0"
    ]
    assert len(open_rules) == 1 and open_rules[0]["Fn::If"][0] == "AllowInternet"


def test_the_rules_on_the_existing_groups_are_https_from_the_function_group_only(tpl: dict[str, Any]) -> None:
    for name in ("FsxIngressFromFunction", "SecretsEndpointIngressFromFunction"):
        res = tpl["Resources"][name]
        p = res["Properties"]
        assert res["Type"] == "AWS::EC2::SecurityGroupIngress"
        assert (p["IpProtocol"], p["FromPort"], p["ToPort"]) == ("tcp", 443, 443)
        assert p["SourceSecurityGroupId"] == {"Ref": "FunctionSecurityGroup"}
        assert "CidrIp" not in p


def test_a_group_that_cannot_reach_anything_is_refused_at_deploy_time(tpl: dict[str, Any]) -> None:
    """Rules fail the deployment up front, not the first invocation 15 minutes later."""
    rules = tpl["Rules"]
    text = repr(rules)
    for needle in ("VpcId", "FsxSecurityGroupId", "SecretsEndpointSecurityGroupId", "S3PrefixListId", "AllowOutboundHttpsToInternet"):
        assert needle in text, f"a Rule must cover {needle}"
    assert "VpcSecurityGroupIds" in text, "with CreateSecurityGroup=false the group ids must be given"


def test_the_discovery_script_only_reads() -> None:
    script = PATTERN / "scripts" / "discover-network.sh"
    assert script.exists(), "readers need a way to look up the values instead of guessing them"
    text = script.read_text()
    calls = re.findall(r"aws_q\s+([a-z0-9-]+)\s+([a-z0-9-]+)", text)
    assert len(calls) >= 8, "the script must look up the file system, network, endpoints and secret by tag"
    for service, verb in calls:
        assert verb.startswith(("describe-", "list-", "get-")), f"{service} {verb} is not a read"
    assert text.count("aws --region") == 1, "aws must be called only through the aws_q wrapper"
    assert "get-secret-value" not in text, "the script must never read a secret value"


# --- Cleanup: the output bucket is kept by the stack, so deleting it is a separate, guarded step ------


def test_the_bucket_cleanup_script_lists_first_and_deletes_only_with_an_explicit_flag() -> None:
    script = PATTERN / "scripts" / "delete-output-bucket.sh"
    assert script.exists(), "the stack keeps the bucket; readers need a safe way to remove it"
    text = script.read_text()
    assert "--yes" in text
    first_delete = min(text.index(w) for w in ("delete-objects", "delete-bucket"))
    assert text.index("--yes") < first_delete, "the --yes check must come before any delete call"
    assert "get-bucket-tagging" in text, "it must refuse a bucket this pattern did not create"
    assert text.index("get-bucket-tagging") < first_delete
    assert "fsxn-ontap-catalog-snapshot" in text


def test_the_readme_documents_how_to_delete_in_both_languages() -> None:
    for name, needle in (("README.md", "削除"), ("README.en.md", "Cleanup")):
        text = (PATTERN / name).read_text()
        assert f"## {needle}" in text, f"{name} needs a cleanup section"
        for must in ("delete-output-bucket.sh", "delete-stack"):
            assert must in text, f"{name} must mention {must}"
