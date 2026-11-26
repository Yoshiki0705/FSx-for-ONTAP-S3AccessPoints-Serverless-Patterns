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
    assert choices == [{"Variable": "$.plan.dryRun", "BooleanEquals": False, "Next": "RecordApproval"}]
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


# ---------------------------------------------------------------- review follow-up: structure
def _tasks(definition):
    return [(n, s) for n, s in _states(definition) if s["Type"] == "Task"]


@pytest.mark.parametrize("definition", [ARCHIVE, RESTORE], ids=["archive", "restore"])
def test_every_task_has_a_timeout(definition):
    """A Task without TimeoutSeconds never raises States.Timeout, so its Retry on that error is dead.

    RequestApproval waits for a person and is bounded by TimeoutSecondsPath. HeartbeatSeconds is not
    set anywhere: neither ecs:runTask.sync nor the SDK and Lambda integrations send task heartbeats,
    and a heartbeat that nothing sends would time every task out.
    """
    for name, state in _tasks(definition):
        assert "TimeoutSeconds" in state or "TimeoutSecondsPath" in state, f"{name} has no timeout"
        assert "HeartbeatSeconds" not in state and "HeartbeatSecondsPath" not in state, name


@pytest.mark.parametrize("definition", [ARCHIVE, RESTORE], ids=["archive", "restore"])
def test_fargate_tasks_are_bounded_by_the_stack_parameter(definition):
    runs = [(n, s) for n, s in _tasks(definition) if s["Resource"].endswith("ecs:runTask.sync")]
    assert runs
    for name, state in runs:
        assert state["TimeoutSecondsPath"] == "$.plan.config.fargateTimeoutSeconds", name
        timeouts = [r for r in state["Retry"] if "States.Timeout" in r["ErrorEquals"]]
        assert timeouts and timeouts[0]["MaxAttempts"] == 1, name


@pytest.mark.parametrize("definition", [ARCHIVE, RESTORE], ids=["archive", "restore"])
def test_every_retry_uses_jitter(definition):
    for name, state in _states(definition):
        for r in state.get("Retry", []):
            assert r.get("JitterStrategy") == "FULL", name


def test_lambda_tasks_retry_a_timeout():
    for name, state in _tasks(ARCHIVE):
        if state["Resource"].startswith("${") and name != "RequestApproval":
            assert any("States.Timeout" in r["ErrorEquals"] for r in state["Retry"]), name


def test_delete_is_reachable_only_through_the_recorded_approval():
    edges = _graph(ARCHIVE)

    def reach_without(blocked):
        seen, todo = set(), [ARCHIVE["StartAt"]]
        while todo:
            n = todo.pop()
            if n in seen or n in blocked:
                continue
            seen.add(n)
            todo.extend(edges[n])
        return seen

    assert "DeleteFiles" not in reach_without({"RecordApproval"})
    assert "DeleteFiles" not in reach_without({"ApprovalRecordedChoice"})
    assert ARCHIVE["States"]["ApprovalRecordedChoice"]["Default"] == "SummarizeApprovalRefused"
    sel = ARCHIVE["States"]["DeleteFiles"]["ItemSelector"]
    assert "approvedBy.$" not in sel and sel["claim.$"] == "$$.Execution.Id"


def test_resume_goes_through_reconcile_and_a_new_approval_not_around_them():
    edges = _graph(ARCHIVE)
    assert ARCHIVE["States"]["ChooseSelection"]["Choices"][0]["Next"] == "ResumeReconcile"
    assert edges["ResumeDefaults"] == {"PrepareManifest"}
    assert "DeleteFiles" not in edges["ResumeReconcile"] | edges["ResumeDefaults"] | edges["PrepareManifest"]


def test_plan_separates_an_input_error_from_a_service_error():
    catches = ARCHIVE["States"]["Plan"]["Catch"]
    assert catches[0]["ErrorEquals"] == ["InvalidInput", "InvalidConfiguration"]
    assert catches[0]["Next"] == "FailInvalidInput" and catches[-1]["Next"] == "FailPlan"


def test_restore_verifies_every_restored_file_before_it_counts_as_restored_ok():
    states = RESTORE["States"]["RestoreFiles"]["ItemProcessor"]["States"]
    assert states["Finalize"]["Next"] == "VerifyChoice"
    assert states["VerifyChoice"]["Default"] == "VerifyRestored"
    assert states["VerifyRestored"]["Parameters"]["action"] == "verify"
    env = states["VerifyRestoredLarge"]["Parameters"]["Overrides"]["ContainerOverrides"][0]["Environment"]
    assert {"Name": "TASK_MODE", "Value": "verify_restore"} in env
    assert states["VerifyRestoredLarge"]["Parameters"]["TaskDefinition"] == "${RestoreTaskDefinitionArn}"


def test_restore_concurrency_is_a_parameter_not_a_literal():
    m = RESTORE["States"]["RestoreFiles"]
    assert "MaxConcurrency" not in m and m["MaxConcurrencyPath"] == "$.req.config.mapConcurrency"


def test_concurrency_default_is_low_and_justified_in_the_template():
    p = TEMPLATE["Parameters"]["MapConcurrency"]
    assert p["Default"] == 1
    assert "76 MB/s" in p["Description"] and "128 MBps" in p["Description"]
    assert "not measured" in p["Description"]  # parallel reads were not measured


def test_two_streams_at_the_measured_rate_would_exceed_the_throughput_capacity():
    """The arithmetic behind the default: 76 MB/s per stream, 128 MBps of capacity."""
    per_stream, capacity = 76, 128
    assert per_stream <= capacity < 2 * per_stream
    assert TEMPLATE["Parameters"]["MapConcurrency"]["Default"] * per_stream <= capacity


def test_exclude_patterns_default_is_not_empty_and_covers_the_files_the_description_names():
    from shared.archive_verify.plan import SelectionFilters

    default = TEMPLATE["Parameters"]["ExcludePatterns"]["Default"]
    patterns = tuple(x.strip() for x in default.split(",") if x.strip())
    assert patterns, "the description says these files must be excluded; the default excludes nothing"
    f = SelectionFilters(exclude_patterns=patterns)
    must_be_excluded = [
        "vm/disk.vmdk", "vm/disk.vhd", "vm/disk.vhdx", "vm/disk.vdi", "vm/disk.qcow2",
        "sql/data.mdf", "sql/data.ndf", "sql/log.ldf", "mysql/t.ibd", "oracle/users01.dbf",
        "tbl/_delta_log/00000.json", "_delta_log/00000.json",
        "tbl/.hoodie/hoodie.properties", ".hoodie/hoodie.properties",
        "wh/tbl/metadata/v1.metadata.json", "metadata/v1.metadata.json",
    ]  # fmt: skip
    for key in must_be_excluded:
        assert f.key_exclusion(key) == "pattern", key
    for key in ["docs/report.pdf", "projects/a/data.csv", "photos/2020/img.jpg", "logs/app.log", "x/metadata.txt"]:
        assert f.key_exclusion(key) is None, key


def test_every_default_exclude_pattern_is_in_the_samconfig_example_note_and_description():
    default = TEMPLATE["Parameters"]["ExcludePatterns"]["Default"]
    description = TEMPLATE["Parameters"]["ExcludePatterns"]["Description"]
    assert "starting point, not a complete list" in description
    for ext in ("vmdk", "vhd", "vhdx", "vdi", "qcow2", "mdf", "ndf", "ldf", "ibd", "dbf"):
        assert f"*.{ext}" in default and ext in description
    for marker in ("_delta_log", ".hoodie", "metadata"):
        assert marker in default and marker in description
    example = (ROOT / "samconfig.toml.example").read_text()
    assert '"ExcludePatterns=",' not in example, "an empty override would remove the default"


def test_approval_validity_is_a_parameter_and_reaches_the_functions():
    p = TEMPLATE["Parameters"]["ApprovalValidityHours"]
    assert p["Default"] == 24 and p["MinValue"] >= 1
    env = TEMPLATE["Globals"]["Function"]["Environment"]["Variables"]
    assert env["APPROVAL_VALIDITY_HOURS"] == {"Ref": "ApprovalValidityHours"}


def test_the_delete_step_passes_the_execution_id_as_the_claim_the_approval_is_bound_to():
    """The approval records ``$$.Execution.Id``; the delete compares it with ``claim``. Both must be that value."""
    map_state = ARCHIVE["States"]["DeleteFiles"]
    assert map_state["ItemSelector"]["claim.$"] == "$$.Execution.Id"
    assert ARCHIVE["States"]["RecordApproval"]["Parameters"]["executionArn.$"] == "$$.Execution.Id"


def test_the_task_token_is_encrypted_with_a_key_of_the_stack_and_the_approver_needs_it():
    key = TEMPLATE["Resources"]["ApprovalTokenKey"]
    assert key["Type"] == "AWS::KMS::Key" and key["Properties"]["EnableKeyRotation"] is True
    statements = key["Properties"]["KeyPolicy"]["Statement"]
    assert len(statements) == 1 and "root" in json.dumps(statements[0]["Principal"])  # IAM decides who may use it
    env = TEMPLATE["Globals"]["Function"]["Environment"]["Variables"]
    assert env["APPROVAL_TOKEN_KEY_ID"] == {"Fn::GetAtt": ["ApprovalTokenKey.Arn"]} or "ApprovalTokenKey" in json.dumps(
        env["APPROVAL_TOKEN_KEY_ID"]
    )
    assert "ApprovalTokenKeyArn" in TEMPLATE["Outputs"]


def test_restore_prepare_receives_the_run_id_so_an_overwrite_can_be_checked_against_the_ledger():
    prepare = RESTORE["States"]["RestoreFiles"]["ItemProcessor"]["States"]["Prepare"]
    assert prepare["Parameters"]["runId.$"] == "$.req.runId"


def test_minimum_size_default_is_128_kib_and_says_why():
    p = TEMPLATE["Parameters"]["MinFileSizeBytes"]
    assert p["Default"] == 131072 and "128 KB" in p["Description"] and "40 KB" in p["Description"]


def test_separate_approver_defaults_to_on():
    assert TEMPLATE["Parameters"]["RequireSeparateApprover"]["Default"] == "true"


def test_data_classification_defaults_to_the_stricter_label():
    assert TEMPLATE["Parameters"]["DataClassification"]["Default"] == "RESTRICTED"


# ---------------------------------------------------------------- observability
def test_both_state_machines_log_without_execution_data():
    for name in ("ArchiveStateMachine", "RestoreStateMachine"):
        logging = TEMPLATE["Resources"][name]["Properties"]["Logging"]
        assert logging["IncludeExecutionData"] is False, "execution data holds file keys"
        assert logging["Destinations"][0]["CloudWatchLogsLogGroup"]["LogGroupArn"]


def test_the_notification_topic_uses_a_customer_managed_key_that_events_and_alarms_can_use():
    topic = TEMPLATE["Resources"]["NotificationTopic"]["Properties"]
    assert topic["KmsMasterKeyId"] == {"Ref": "NotificationKey"}, "alias/aws/sns cannot be used by AWS services"
    stmts = TEMPLATE["Resources"]["NotificationKey"]["Properties"]["KeyPolicy"]["Statement"]
    by_service = {s["Principal"]["Service"]: s for s in stmts if "Service" in s["Principal"]}
    for service in ("events.amazonaws.com", "cloudwatch.amazonaws.com"):
        assert {"kms:GenerateDataKey*", "kms:Decrypt"} <= set(by_service[service]["Action"])
    assert "Condition" not in by_service["events.amazonaws.com"], "SNS docs: not supported for EventBridge"


def test_publishers_to_the_topic_can_use_its_key():
    for name in ("ApprovalFunction", "SummarizeFunction"):
        text = json.dumps(TEMPLATE["Resources"][name])
        assert "NotificationKey" in text, name


def test_alarms_cover_failures_approval_wait_stuck_deletes_and_mismatches():
    alarms = {n: r for n, r in TEMPLATE["Resources"].items() if r["Type"] == "AWS::CloudWatch::Alarm"}
    assert set(alarms) == {
        "ArchiveExecutionsFailedAlarm",
        "RestoreExecutionsFailedAlarm",
        "ApprovalPendingAlarm",
        "FilesStuckDeletingAlarm",
        "FilesMismatchAlarm",
        "RestoreMismatchAlarm",
    }
    for name, a in alarms.items():
        assert a["Properties"]["AlarmActions"] == [{"Ref": "NotificationTopic"}], name
    names = {a["Properties"].get("MetricName") for a in alarms.values()}
    assert {"ApprovalPendingHours", "FilesStuckDeleting", "FilesMismatch", "RestoreMismatch"} <= names


def test_alarm_dimensions_match_what_the_functions_emit():
    """EmfMetrics dimensions: FunctionName=<service>, Environment=<ENVIRONMENT>, plus UseCase."""
    env = TEMPLATE["Globals"]["Function"]["Environment"]["Variables"]["ENVIRONMENT"]
    assert env == {"Ref": "AWS::StackName"}
    dims = TEMPLATE["Resources"]["FilesMismatchAlarm"]["Properties"]["Dimensions"]
    assert {d["Name"]: d["Value"] for d in dims} == {
        "FunctionName": "archive-verify-delete",
        "Environment": {"Ref": "AWS::StackName"},
        "UseCase": "archive-verify-delete",
    }


# ---------------------------------------------------------------- permissions
def _role_holds(resource_name, action, resource_text=None):
    for stmt in _statements(TEMPLATE["Resources"][resource_name]):
        if isinstance(stmt, dict) and "Fn::If" in stmt:
            stmt = stmt["Fn::If"][1]
        if action in _actions(stmt) and (resource_text is None or resource_text in json.dumps(stmt.get("Resource"))):
            return True
    return False


def test_put_object_on_the_access_point_is_held_only_by_restore_roles():
    holders = set()
    for name, res in TEMPLATE["Resources"].items():
        for stmt in _statements(res):
            if isinstance(stmt, dict) and "Fn::If" in stmt:
                stmt = stmt["Fn::If"][1]
            if "s3:PutObject" in _actions(stmt) and "AccessPoint" in json.dumps(stmt.get("Resource")):
                holders.add(name)
    assert holders == {"FargateRestoreTaskRole", "RestoreStateMachine"}, holders


def test_the_archive_task_role_cannot_write_to_the_access_point_or_the_ledger_beyond_updates():
    assert not _role_holds("FargateTaskRole", "s3:PutObject", "AccessPoint")
    assert _role_holds("FargateTaskRole", "dynamodb:UpdateItem")
    assert not _role_holds("FargateTaskRole", "dynamodb:PutItem")


def test_only_the_approval_function_among_the_workers_can_update_ledger_items_to_approved():
    """IAM cannot restrict the value written, so the number of principals that may update is the lever.

    Updating is allowed to the functions whose job is a state transition. What this checks is that no
    function that only reads or only creates items (select, record, restore select helpers aside) gains it.
    """
    for name in ("RecordFunction", "OntapRestFunction", "WatchdogFunction"):
        assert not _role_holds(name, "dynamodb:UpdateItem"), name
    assert _role_holds("ApprovalFunction", "dynamodb:UpdateItem")
    assert not _role_holds("SummarizeFunction", "dynamodb:UpdateItem")


def test_the_restore_state_machine_passes_only_the_restore_task_role():
    text = json.dumps(TEMPLATE["Resources"]["RestoreStateMachine"]["Properties"]["Policies"])
    assert "FargateRestoreTaskRole" in text and "FargateTaskRole" not in text.replace("FargateRestoreTaskRole", "")
    text = json.dumps(TEMPLATE["Resources"]["ArchiveStateMachine"]["Properties"]["Policies"])
    assert "FargateRestoreTaskRole" not in text


def test_the_outputs_name_every_role_the_access_point_policy_needs():
    outs = set(TEMPLATE["Outputs"])
    assert {
        "SelectRoleArn",
        "RecordRoleArn",
        "DeleteRoleArn",
        "RestoreFunctionRoleArn",
        "ArchiveStateMachineRoleArn",
        "RestoreStateMachineRoleArn",
        "FargateTaskRoleArn",
        "FargateRestoreTaskRoleArn",
    } <= outs


def test_every_principal_that_reads_a_404_from_the_access_point_holds_list_bucket():
    """Live finding: HeadObject on a deleted key returned 403 for a role with GetObject but no ListBucket.

    S3 answers a missing key with 404 only when the caller may list the bucket. The delete function
    (idempotent retry), the restore function (prepare, verify) and the select function (candidates) read
    404 as "not there", so each needs s3:ListBucket on the Access Point, in IAM and in its policy.
    """
    for name in ("DeleteFunction", "RestoreFunction", "SelectFunction"):
        assert _role_holds(name, "s3:ListBucket", "AccessPointArn"), name


def test_the_topic_policy_lets_cloudwatch_alarms_publish_as_well_as_eventbridge():
    """Live finding: an alarm action failed with "CloudWatch Alarms is not authorized to perform SNS:Publish".

    The key policy allowed cloudwatch.amazonaws.com, but the topic policy (which replaces the default one)
    had only the EventBridge statement. The alarms are named <stack>-..., so the statement can be scoped.
    """
    stmts = TEMPLATE["Resources"]["NotificationTopicPolicy"]["Properties"]["PolicyDocument"]["Statement"]
    by_service = {s["Principal"]["Service"]: s for s in stmts}
    assert set(by_service) == {"events.amazonaws.com", "cloudwatch.amazonaws.com"}
    cw = by_service["cloudwatch.amazonaws.com"]
    assert cw["Action"] == "sns:Publish" and cw["Condition"]["StringEquals"]["aws:SourceAccount"]
    assert "alarm:" in json.dumps(cw["Condition"]["ArnLike"]["aws:SourceArn"])


def test_the_ledger_has_deletion_protection_which_is_reversible():
    props = TEMPLATE["Resources"]["LedgerTable"]["Properties"]
    assert props["DeletionProtectionEnabled"] is True
    assert TEMPLATE["Resources"]["LedgerTable"]["DeletionPolicy"] == "Retain"


def test_state_machine_roles_hold_the_ecs_sync_event_rule_permission_without_fargate():
    """Live finding (deploy with FargateImageUri empty): Step Functions refused to create the restore state
    machine, "role is not authorized to create managed-rule". Both definitions contain ecs:runTask.sync
    states whatever the parameters, and the managed rule is checked when the state machine is created.
    The statement must not sit behind the UseFargate condition.
    """
    for name in ("ArchiveStateMachine", "RestoreStateMachine"):
        found = [
            s
            for s in _statements(TEMPLATE["Resources"][name])
            if isinstance(s, dict)
            and "Fn::If" not in s
            and "events:PutRule" in _actions(s)
            and "StepFunctionsGetEventsForECSTaskRule" in json.dumps(s.get("Resource"))
        ]
        assert found, name
