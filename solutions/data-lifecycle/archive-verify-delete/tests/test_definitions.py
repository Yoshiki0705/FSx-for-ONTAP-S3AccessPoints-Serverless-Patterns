"""Static properties of the state machines and the template.

These do not need AWS. They hold the structure that the delete gate depends on: every Task
retries and catches, nothing reaches the delete state without the approval and dry-run checks,
only one role can delete, and no immutability feature appears in the template.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = json.loads((ROOT / "statemachine" / "archive.asl.json").read_text())
RESTORE = json.loads((ROOT / "statemachine" / "restore.asl.json").read_text())


class _Loader(yaml.SafeLoader):
    pass


def _tag(loader, suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return {suffix: loader.construct_scalar(node)}
    if isinstance(node, yaml.SequenceNode):
        return {suffix: loader.construct_sequence(node, deep=True)}
    return {suffix: loader.construct_mapping(node, deep=True)}


_Loader.add_multi_constructor("!", _tag)
TEMPLATE = yaml.load((ROOT / "template.yaml").read_text(), Loader=_Loader)


def _states(definition):
    """Yield (path, name, state) for every state, descending into Map processors."""
    for name, state in definition["States"].items():
        yield name, state
        if state.get("Type") == "Map":
            yield from _states(state["ItemProcessor"])


def _graph(definition):
    edges = {}
    for name, state in definition["States"].items():
        nxt = set()
        if "Next" in state:
            nxt.add(state["Next"])
        for c in state.get("Choices", []):
            nxt.add(c["Next"])
        if "Default" in state:
            nxt.add(state["Default"])
        for c in state.get("Catch", []):
            nxt.add(c["Next"])
        edges[name] = nxt
    return edges


@pytest.mark.parametrize("definition", [ARCHIVE, RESTORE], ids=["archive", "restore"])
def test_every_task_retries_and_catches(definition):
    tasks = [(n, s) for n, s in _states(definition) if s["Type"] == "Task"]
    assert tasks
    for name, state in tasks:
        assert state.get("Retry"), f"{name} has no Retry"
        assert state.get("Catch"), f"{name} has no Catch"


@pytest.mark.parametrize("definition", [ARCHIVE, RESTORE], ids=["archive", "restore"])
def test_transitions_point_at_states_that_exist(definition):
    def check(d):
        names = set(d["States"])
        assert d["StartAt"] in names
        for name, nxts in _graph(d).items():
            assert nxts <= names, f"{name} -> {nxts - names}"
        for state in d["States"].values():
            if state.get("Type") == "Map":
                check(state["ItemProcessor"])

    check(definition)


@pytest.mark.parametrize("definition", [ARCHIVE, RESTORE], ids=["archive", "restore"])
def test_all_states_are_reachable(definition):
    def check(d):
        edges, seen, todo = _graph(d), set(), [d["StartAt"]]
        while todo:
            n = todo.pop()
            if n not in seen:
                seen.add(n)
                todo.extend(edges[n])
        assert seen == set(d["States"]), set(d["States"]) - seen
        for state in d["States"].values():
            if state.get("Type") == "Map":
                check(state["ItemProcessor"])

    check(definition)


def test_delete_is_reachable_only_through_approval_and_the_dry_run_check():
    edges = _graph(ARCHIVE)

    def reach_without(blocked: set[str]) -> set[str]:
        seen, todo = set(), [ARCHIVE["StartAt"]]
        while todo:
            n = todo.pop()
            if n in seen or n in blocked:
                continue
            seen.add(n)
            todo.extend(edges[n])
        return seen

    assert "DeleteFiles" in reach_without(set())
    assert "DeleteFiles" not in reach_without({"RequestApproval"})
    assert "DeleteFiles" not in reach_without({"ApprovalCheck"})
    assert "DeleteFiles" not in reach_without({"DryRunChoice"})


def test_dry_run_choice_requires_the_boolean_false():
    choices = ARCHIVE["States"]["DryRunChoice"]["Choices"]
    assert choices == [{"Variable": "$.plan.dryRun", "BooleanEquals": False, "Next": "DeleteFiles"}]
    assert ARCHIVE["States"]["DryRunChoice"]["Default"] == "SummarizeDryRun"


def test_approval_needs_a_named_approver():
    cond = ARCHIVE["States"]["ApprovalCheck"]["Choices"][0]["And"]
    variables = {(c["Variable"], tuple(k for k in c if k not in ("Variable", "Next"))) for c in cond}
    assert ("$.approval.approved", ("BooleanEquals",)) in variables
    assert ("$.approval.approver", ("IsString",)) in variables
    assert ARCHIVE["States"]["ApprovalCheck"]["Default"] == "SummarizeRejected"


def test_approval_waits_with_a_token_and_a_timeout():
    s = ARCHIVE["States"]["RequestApproval"]
    assert s["Resource"].endswith("lambda:invoke.waitForTaskToken")
    assert s["Parameters"]["Payload"]["taskToken.$"] == "$$.Task.Token"
    assert "TimeoutSecondsPath" in s
    assert "ErrorEquals" in s["Catch"][0]


def test_the_task_token_is_not_part_of_any_notification_input():
    text = json.dumps(ARCHIVE["States"]["PrepareManifest"]) + json.dumps(ARCHIVE["States"]["SummarizeCompleted"])
    assert "Task.Token" not in text


def test_copy_carries_the_ledger_etag_as_a_precondition():
    for name in ("CopyArchive", "CopySecond"):
        params = ARCHIVE["States"]["ProcessFiles"]["ItemProcessor"]["States"][name]["Parameters"]
        assert "CopySourceIfMatch.$" in params
        assert params["ChecksumAlgorithm"] == "SHA256"
        assert params["MetadataDirective"] == "REPLACE" and "ContentType.$" in params


def test_verify_requests_checksums_from_the_bucket():
    states = ARCHIVE["States"]["ProcessFiles"]["ItemProcessor"]["States"]
    for name in ("HeadArchived", "HeadSecond"):
        assert states[name]["Parameters"]["ChecksumMode"] == "ENABLED"


def test_restore_never_overwrites_an_existing_file():
    processor = RESTORE["States"]["RestoreFiles"]["ItemProcessor"]
    edges = _graph(processor)

    def reach(blocked):
        seen, todo = set(), [processor["StartAt"]]
        while todo:
            n = todo.pop()
            if n in seen or n in blocked:
                continue
            seen.add(n)
            todo.extend(edges[n])
        return seen

    assert {"RestoreCopy", "RestoreLarge"} <= reach(set())
    # With the existence check removed from the graph, no copy is reachable.
    assert not {"RestoreCopy", "RestoreLarge"} & reach({"ExistsChoice"})
    assert processor["States"]["ExistsChoice"]["Choices"][0]["Next"] == "ItemExists"


def test_restore_copy_has_no_if_match():
    params = RESTORE["States"]["RestoreFiles"]["ItemProcessor"]["States"]["RestoreCopy"]["Parameters"]
    assert not any(k.startswith("CopySourceIfMatch") for k in params)


def test_asl_placeholders_are_all_substituted_by_the_template():
    for name, definition, resource in (
        ("archive", ARCHIVE, "ArchiveStateMachine"),
        ("restore", RESTORE, "RestoreStateMachine"),
    ):
        used = set(re.findall(r"\$\{(\w+)\}", json.dumps(definition)))
        provided = set(TEMPLATE["Resources"][resource]["Properties"]["DefinitionSubstitutions"])
        assert used <= provided, f"{name}: {used - provided}"
        assert provided <= used, f"{name} substitutes unused names: {provided - used}"


def _statements(resource):
    props = resource["Properties"]
    for pol in props.get("Policies", []):
        if isinstance(pol, dict) and "Statement" in pol:
            yield from pol["Statement"]
        elif isinstance(pol, dict) and "PolicyDocument" in pol:
            yield from pol["PolicyDocument"]["Statement"]


def _actions(stmt):
    if isinstance(stmt, dict) and "Fn::If" in stmt:
        stmt = stmt["Fn::If"][1]
    if not isinstance(stmt, dict):
        return []
    a = stmt.get("Action", [])
    return [a] if isinstance(a, str) else a


def test_only_the_delete_function_can_delete_from_the_access_point():
    holders = []
    for name, res in TEMPLATE["Resources"].items():
        for stmt in _statements(res):
            if any(a in ("s3:DeleteObject", "s3:DeleteObjects", "s3:*") for a in _actions(stmt)):
                holders.append(name)
    assert holders == ["DeleteFunction"]


def test_no_role_may_delete_ledger_items_or_the_bucket_objects():
    for name, res in TEMPLATE["Resources"].items():
        for stmt in _statements(res):
            for a in _actions(stmt):
                assert a not in ("dynamodb:DeleteItem", "dynamodb:*", "s3:DeleteBucket", "s3:PutBucketPolicy"), name


FORBIDDEN_KEY = re.compile(r"ObjectLock|Snaplock|SnapLock|VaultLock|LegalHold|Retention(?!InDays)", re.I)
FORBIDDEN_ACTION = re.compile(
    r"PutObjectRetention|PutObjectLegalHold|PutBucketObjectLockConfiguration|VaultLock|PutBackupVaultLock", re.I
)


def _walk(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield k, v
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def test_template_uses_no_immutability_feature():
    for key, value in _walk(TEMPLATE["Resources"]):
        assert not FORBIDDEN_KEY.search(str(key)), key
        if key == "Action":
            for a in [value] if isinstance(value, str) else value:
                assert not FORBIDDEN_ACTION.search(str(a)), a
    for res in TEMPLATE["Resources"].values():
        assert res["Type"] not in ("AWS::Backup::BackupVault", "AWS::Glacier::Vault")


def test_archive_bucket_is_private_encrypted_and_retained():
    bucket = TEMPLATE["Resources"]["ArchiveBucket"]
    assert bucket["DeletionPolicy"] == "Retain"
    block = bucket["Properties"]["PublicAccessBlockConfiguration"]
    assert all(
        block[k] is True for k in ("BlockPublicAcls", "BlockPublicPolicy", "IgnorePublicAcls", "RestrictPublicBuckets")
    )
    assert bucket["Properties"]["NotificationConfiguration"]["EventBridgeConfiguration"]["EventBridgeEnabled"] is True
    assert "ServerSideEncryptionConfiguration" in bucket["Properties"]["BucketEncryption"]


def test_functions_are_arm64_python313_and_tagged():
    g = TEMPLATE["Globals"]["Function"]
    assert g["Runtime"] == "python3.13" and g["Architectures"] == ["arm64"]
    assert g["Tags"]["UseCase"] == "archive-verify-delete" and "Phase" in g["Tags"]
    for res in TEMPLATE["Resources"].values():
        if res["Type"] == "AWS::ECS::TaskDefinition":
            assert res["Properties"]["RuntimePlatform"]["CpuArchitecture"] == "ARM64"


def test_state_machines_use_definition_uri():
    for name in ("ArchiveStateMachine", "RestoreStateMachine"):
        props = TEMPLATE["Resources"][name]["Properties"]
        assert "DefinitionUri" in props and "Definition" not in props and "DefinitionString" not in props


def test_access_point_policies_name_both_arn_forms():
    for name in ("SelectFunction", "RecordFunction", "DeleteFunction"):
        text = json.dumps(TEMPLATE["Resources"][name])
        assert "AccessPointArn" in text and "AccessPointAlias" in text, name


@pytest.mark.parametrize("machine", ["ArchiveStateMachine", "RestoreStateMachine"], ids=["archive", "restore"])
def test_state_machine_role_can_invoke_every_function_its_definition_calls(machine):
    """A function substituted into the definition needs a LambdaInvokePolicy on the same machine.

    The first deployed run failed with AccessDenied on the ONTAP REST function: it was
    substituted into the definition but had no invoke permission, and the template tests
    only compared the substitution names with the placeholders.
    """
    props = TEMPLATE["Resources"][machine]["Properties"]
    called = set()
    for value in props["DefinitionSubstitutions"].values():
        called.update(re.findall(r"(\w+Function)\.Arn", json.dumps(value)))
    granted = set(re.findall(r'"LambdaInvokePolicy".*?"Ref": "(\w+Function)"', json.dumps(props["Policies"])))
    assert called, machine
    assert called <= granted, f"{machine}: no invoke permission for {sorted(called - granted)}"


def test_template_passes_the_tls_verification_choice_to_the_ontap_function():
    env = TEMPLATE["Resources"]["OntapRestFunction"]["Properties"]["Environment"]["Variables"]
    assert env["ONTAP_VERIFY_SSL"] == {"Ref": "OntapVerifySsl"}
    param = TEMPLATE["Parameters"]["OntapVerifySsl"]
    assert param["AllowedValues"] == ["true", "false"]


def test_restore_request_tells_an_in_progress_restore_from_other_s3_errors():
    """The Step Functions SDK integration reports RestoreAlreadyInProgress as ``S3.S3Exception``.

    Observed on a live request (HTTP 409, "Object restore is already in progress"). A catch on
    ``S3.RestoreAlreadyInProgressException`` never matches, so a second restore request for the same
    object failed the file. The definition must route that cause to the wait loop and send every other
    S3 error to the failure state.
    """
    states = RESTORE["States"]["RestoreFiles"]["ItemProcessor"]["States"]
    catches = states["RequestRestore"]["Catch"]
    sdk = next(c for c in catches if "S3.S3Exception" in c["ErrorEquals"])
    assert sdk["ResultPath"] == "$.error"
    choice = states[sdk["Next"]]
    assert choice["Type"] == "Choice"
    matched = choice["Choices"][0]
    assert matched["Variable"] == "$.error.Cause"
    assert matched["StringMatches"] == "*restore is already in progress*"
    assert matched["Next"] == "WaitRestore"
    assert choice["Default"] == "ItemFailed"
