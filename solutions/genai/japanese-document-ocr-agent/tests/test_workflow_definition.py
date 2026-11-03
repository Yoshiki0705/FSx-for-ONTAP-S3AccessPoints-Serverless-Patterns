"""Structural tests for the state machine definition and its agreement with the template.

cfn-lint checks the template but does not look inside the ASL file that DefinitionUri points at.
These tests check what a typo there would break only at run time: a transition to a state that
does not exist, a Task with no Retry or Catch, a `${...}` placeholder the template never fills,
or an error name that no handler raises.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from helpers import PATTERN_DIR

ASL_PATH = PATTERN_DIR / "statemachine" / "workflow.asl.json"
TEMPLATE_PATH = PATTERN_DIR / "template.yaml"
STATE_LIMIT_BYTES = 256 * 1024


class _CfnLoader(yaml.SafeLoader):
    """SafeLoader that accepts CloudFormation short-form tags (!Ref, !Sub, ...) as plain data."""


def _tag(loader: _CfnLoader, suffix: str, node: yaml.Node) -> Any:
    if isinstance(node, yaml.ScalarNode):
        return {suffix: loader.construct_scalar(node)}
    if isinstance(node, yaml.SequenceNode):
        return {suffix: loader.construct_sequence(node)}
    return {suffix: loader.construct_mapping(node)}


_CfnLoader.add_multi_constructor("!", _tag)


def load_template() -> dict[str, Any]:
    return yaml.load(TEMPLATE_PATH.read_text(encoding="utf-8"), Loader=_CfnLoader)  # noqa: S506 — SafeLoader subclass


def load_asl(path: Path = ASL_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def walk_states(definition: dict[str, Any], prefix: str = "") -> dict[str, dict[str, Any]]:
    """Flatten the top-level states and the states inside every Map's ItemProcessor."""
    found: dict[str, dict[str, Any]] = {}
    for name, state in definition["States"].items():
        found[f"{prefix}{name}"] = state
        if state.get("Type") == "Map":
            found.update(walk_states(state["ItemProcessor"], prefix=f"{name}/"))
    return found


def transitions(state: dict[str, Any]) -> list[str]:
    out = []
    if "Next" in state:
        out.append(state["Next"])
    out += [c["Next"] for c in state.get("Choices", [])]
    if "Default" in state:
        out.append(state["Default"])
    out += [c["Next"] for c in state.get("Catch", [])]
    return out


def scopes(definition: dict[str, Any]) -> list[dict[str, Any]]:
    """The definition and each nested ItemProcessor: a transition must stay inside its scope."""
    found = [definition]
    for state in definition["States"].values():
        if state.get("Type") == "Map":
            found += scopes(state["ItemProcessor"])
    return found


def check_definition(asl: dict[str, Any]) -> list[str]:
    """Return every structural problem in the definition (empty when it is sound)."""
    problems: list[str] = []
    for scope in scopes(asl):
        names = set(scope["States"])
        if scope["StartAt"] not in names:
            problems.append(f"StartAt {scope['StartAt']!r} does not exist")
        for name, state in scope["States"].items():
            for target in transitions(state):
                if target not in names:
                    problems.append(f"{name} -> {target!r} does not exist in its scope")
            if state["Type"] in {"Task", "Map"} and not state.get("Catch"):
                problems.append(f"{name}: Task/Map without Catch")
            if state["Type"] == "Task" and not state.get("Retry"):
                problems.append(f"{name}: Task without Retry")
            if state["Type"] in {"Succeed", "Fail"} or state.get("End"):
                continue
            if state["Type"] != "Choice" and "Next" not in state:
                problems.append(f"{name}: no Next and not an end state")
        reachable: set[str] = set()
        queue = [scope["StartAt"]]
        while queue:
            current = queue.pop()
            if current in reachable or current not in names:
                continue
            reachable.add(current)
            queue += transitions(scope["States"][current])
        for unreachable in sorted(names - reachable):
            problems.append(f"{unreachable}: unreachable")
    return problems


def textract_document_arguments(paths: list[Path] | None = None) -> list[tuple[str, int, str]]:
    """List how each handler passes the document to a Textract call.

    Returns (file, line, shape) for every call that sets `Document=` or `DocumentLocation=`.
    shape is "Bytes" for inline bytes, "staging" for an S3Object whose bucket comes from the
    STAGING_BUCKET variable (or a name bound from it), and "S3Object(not staging)" otherwise.
    """
    import ast

    findings: list[tuple[str, int, str]] = []
    for path in paths or sorted((PATTERN_DIR / "functions").glob("*/handler.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
            for keyword in call.keywords:
                if keyword.arg not in {"Document", "DocumentLocation"} or not isinstance(keyword.value, ast.Dict):
                    continue
                keys = [k.value for k in keyword.value.keys if isinstance(k, ast.Constant)]
                if keys == ["Bytes"]:
                    findings.append((path.name, call.lineno, "Bytes"))
                elif keys == ["S3Object"]:
                    inner = keyword.value.values[0]
                    source = ast.unparse(inner)
                    ok = "staging" in source.lower() or "STAGING_BUCKET" in source
                    findings.append((path.name, call.lineno, "staging" if ok else "S3Object(not staging)"))
                else:
                    findings.append((path.name, call.lineno, f"unexpected keys {keys}"))
    return findings


@pytest.fixture(scope="module")
def asl() -> dict[str, Any]:
    return load_asl()


@pytest.fixture(scope="module")
def template() -> dict[str, Any]:
    return load_template()


class TestDefinitionIsSound:
    def test_no_structural_problems(self, asl):
        assert check_definition(asl) == []

    def test_the_check_itself_catches_a_dangling_transition(self, asl):
        """A check that cannot fail proves nothing: break the definition and require a finding."""
        broken = json.loads(json.dumps(asl))
        broken["States"]["Discover"]["Next"] = "NoSuchState"
        assert any("NoSuchState" in p for p in check_definition(broken))

    def test_the_check_itself_catches_a_task_without_retry_or_catch(self, asl):
        broken = json.loads(json.dumps(asl))
        del broken["States"]["Report"]["Retry"]
        del broken["States"]["ReportError"]["Catch"]
        problems = check_definition(broken)
        assert any("Report: Task without Retry" in p for p in problems)
        assert any("ReportError: Task/Map without Catch" in p for p in problems)

    def test_the_check_itself_catches_an_unreachable_state(self, asl):
        broken = json.loads(json.dumps(asl))
        broken["States"]["Orphan"] = {"Type": "Succeed"}
        assert any("Orphan: unreachable" in p for p in check_definition(broken))

    def test_the_check_itself_catches_a_transition_that_leaves_the_map(self, asl):
        broken = json.loads(json.dumps(asl))
        broken["States"]["ProcessDocuments"]["ItemProcessor"]["States"]["OcrSync"]["Next"] = "Report"
        assert any("OcrSync -> 'Report'" in p for p in check_definition(broken))


class TestShape:
    def test_standard_workflow_json_path_mode(self, asl):
        assert "QueryLanguage" not in asl  # JSONPath is the default
        assert "TimeoutSeconds" not in asl or asl["TimeoutSeconds"] > 0

    def test_map_uses_item_processor_item_selector_and_a_path_for_concurrency(self, asl):
        map_state = asl["States"]["ProcessDocuments"]
        assert "ItemProcessor" in map_state and "Iterator" not in map_state
        assert "ItemSelector" in map_state and "Parameters" not in map_state
        assert map_state["MaxConcurrencyPath"] == "$.discovery.map_concurrency"
        assert map_state["ItemProcessor"]["ProcessorConfig"]["Mode"] == "INLINE"

    def test_the_agent_input_reaches_discovery_unchanged_with_the_execution_name(self, asl):
        params = asl["States"]["Discover"]["Parameters"]
        assert params == {"request.$": "$", "execution_name.$": "$$.Execution.Name"}

    def test_report_is_given_only_what_it_needs_not_the_object_list(self, asl):
        params = asl["States"]["Report"]["Parameters"]
        assert "objects" not in json.dumps(params)
        assert params["processed.$"] == "$.processed"

    def test_failure_paths_end_in_fail_states_that_read_error_and_cause_from_the_report(self, asl):
        for name in ("AllDocumentsFailed", "ExecutionFailed"):
            state = asl["States"][name]
            assert state["Type"] == "Fail"
            assert state["ErrorPath"] == "$.error_type"
            assert state["CausePath"] == "$.cause"

    def test_a_failed_report_status_is_routed_to_the_fail_state(self, asl):
        router = asl["States"]["StatusRouter"]
        assert router["Choices"][0]["Variable"] == "$.status"
        assert router["Choices"][0]["StringEquals"] == "failed"
        assert router["Choices"][0]["Next"] == "AllDocumentsFailed"
        assert router["Default"] == "Done"

    def test_every_workflow_error_reaches_a_fail_state_not_a_silent_success(self, asl):
        """Discover, the Map and Report all Catch into ReportError, which ends in a Fail state."""
        for name in ("Discover", "ProcessDocuments", "Report"):
            assert asl["States"][name]["Catch"][0]["Next"] == "ReportError"
        assert asl["States"]["ReportError"]["Next"] == "ExecutionFailed"

    def test_the_async_loop_waits_checks_and_collects(self, asl):
        inner = asl["States"]["ProcessDocuments"]["ItemProcessor"]["States"]
        assert inner["AsyncStart"]["Next"] == "StartOutcome"
        assert inner["StartOutcome"]["Choices"][0]["Next"] == "AsyncWait"
        assert inner["StartOutcome"]["Default"] == "StartRejected"
        assert inner["AsyncWait"]["SecondsPath"] == "$.job.wait_seconds"
        assert inner["AsyncWait"]["Next"] == "AsyncCheck"
        assert inner["AsyncChoice"]["Choices"][0]["Next"] == "AsyncWait"
        assert inner["AsyncChoice"]["Default"] == "AsyncCollect"

    def test_a_failed_status_check_still_cleans_up_through_collect(self, asl):
        """Catch -> AsyncCollect with check_error, so the staged copy is deleted on that path too."""
        inner = asl["States"]["ProcessDocuments"]["ItemProcessor"]["States"]
        catch = inner["AsyncCheck"]["Catch"][0]
        assert catch["Next"] == "AsyncCollect"
        assert catch["ResultPath"] == "$.check_error"

    def test_a_catch_keeps_only_the_error_type_not_the_long_cause(self, asl):
        inner = asl["States"]["ProcessDocuments"]["ItemProcessor"]["States"]
        record = inner["RecordFailure"]["Parameters"]
        assert record["ocr"]["error.$"] == "$.failure.Error"
        assert "Cause" not in json.dumps(record)

    def test_field_extraction_failure_does_not_discard_the_ocr_result(self, asl):
        inner = asl["States"]["ProcessDocuments"]["ItemProcessor"]["States"]
        assert inner["ExtractFields"]["Catch"][0]["Next"] == "FieldsFailed"
        assert inner["FieldsFailed"]["Next"] == "Summarize"

    def test_extraction_runs_only_when_enabled_and_ocr_completed(self, asl):
        choice = asl["States"]["ProcessDocuments"]["ItemProcessor"]["States"]["AfterOcr"]["Choices"][0]
        variables = {c["Variable"] for c in choice["And"]}
        assert variables == {"$.extract_fields", "$.ocr.status"}

    def test_extract_fields_defaults_to_not_requested_so_summarize_never_reads_a_missing_path(self, asl):
        selector = asl["States"]["ProcessDocuments"]["ItemSelector"]
        assert selector["fields_result"] == {"status": "not_requested"}

    def test_summarize_keeps_the_record_shape_the_state_budget_is_measured_against(self, asl):
        """tests/test_state_budget.py builds the Map's output in exactly this shape."""
        inner = asl["States"]["ProcessDocuments"]["ItemProcessor"]["States"]
        assert set(inner["Summarize"]["Parameters"]) == {"doc_id.$", "key.$", "route.$", "ocr.$", "fields.$"}


class TestRetryPolicy:
    TEXTRACT_TASKS = ("OcrSync", "AsyncStart", "AsyncCheck", "AsyncCollect")

    def test_throttling_is_retried_with_backoff_and_jitter(self, asl):
        inner = asl["States"]["ProcessDocuments"]["ItemProcessor"]["States"]
        for name in self.TEXTRACT_TASKS:
            retry = next(r for r in inner[name]["Retry"] if r["ErrorEquals"] == ["TextractThrottled"])
            assert retry["MaxAttempts"] >= 5
            assert retry["BackoffRate"] >= 2
            assert retry["MaxDelaySeconds"] <= 60
            assert retry["JitterStrategy"] == "FULL"

    def test_a_rejected_document_is_not_retried(self, asl):
        """TextractRejected must appear in no Retry: retrying it cannot change the answer."""
        assert "TextractRejected" not in json.dumps(asl)

    def test_bedrock_throttling_is_retried(self, asl):
        inner = asl["States"]["ProcessDocuments"]["ItemProcessor"]["States"]
        assert inner["ExtractFields"]["Retry"][0]["ErrorEquals"] == ["BedrockThrottled"]

    def test_invalid_input_is_not_retried_by_discover(self, asl):
        retried = {e for r in asl["States"]["Discover"]["Retry"] for e in r["ErrorEquals"]}
        assert "InvalidInput" not in retried
        assert "InvalidConfiguration" not in retried
        assert "States.ALL" not in retried

    def test_error_names_in_retry_blocks_are_classes_the_handlers_can_raise(self, asl):
        from shared import exceptions

        raisable = {n for n in dir(exceptions) if isinstance(getattr(exceptions, n), type)}
        aws_or_states = re.compile(r"^(Lambda\.|States\.)")
        for state in walk_states(asl).values():
            for retry in state.get("Retry", []):
                for name in retry["ErrorEquals"]:
                    assert aws_or_states.match(name) or name in raisable, name


class TestTemplateAgreement:
    def test_every_placeholder_in_the_asl_is_filled_by_the_template(self, asl, template):
        used = set(re.findall(r"\$\{(\w+)\}", ASL_PATH.read_text(encoding="utf-8")))
        filled = set(template["Resources"]["OcrStateMachine"]["Properties"]["DefinitionSubstitutions"])
        assert used == filled

    def test_each_substituted_function_is_one_the_state_machine_may_invoke(self, template):
        props = template["Resources"]["OcrStateMachine"]["Properties"]
        invokable = {
            p["LambdaInvokePolicy"]["FunctionName"]["Ref"] for p in props["Policies"] if "LambdaInvokePolicy" in p
        }
        arns = {v["GetAtt"].split(".")[0] for v in props["DefinitionSubstitutions"].values()}
        assert arns == invokable

    def test_every_function_has_a_codeuri_that_exists_with_a_handler(self, template):
        functions = {n: r for n, r in template["Resources"].items() if r["Type"] == "AWS::Serverless::Function"}
        assert len(functions) == 7
        for name, resource in functions.items():
            props = resource["Properties"]
            assert props["Handler"] == "handler.handler", name
            assert (PATTERN_DIR / props["CodeUri"] / "handler.py").is_file(), name
            assert props.get("Timeout", template["Globals"]["Function"]["Timeout"]) > 0, name

    def test_lambdas_run_python_313_on_arm64(self, template):
        glob = template["Globals"]["Function"]
        assert glob["Runtime"] == "python3.13"
        assert glob["Architectures"] == ["arm64"]

    def test_the_state_machine_is_standard(self, template):
        assert "Type" not in template["Resources"]["OcrStateMachine"]["Properties"]

    def test_each_function_has_a_log_group_with_retention(self, template):
        resources = template["Resources"]
        for name, resource in resources.items():
            if resource["Type"] != "AWS::Serverless::Function":
                continue
            group = resources[name.replace("Function", "LogGroup")]
            assert group["Type"] == "AWS::Logs::LogGroup"
            assert group["Properties"]["RetentionInDays"] == {"Ref": "LogRetentionInDays"}
            assert resource["DependsOn"] == name.replace("Function", "LogGroup")

    def test_every_parameter_is_used(self, template):
        text = TEMPLATE_PATH.read_text(encoding="utf-8")
        for name in template["Parameters"]:
            assert len(re.findall(rf"\b{name}\b", text)) > 1, f"parameter {name} is never used"

    def test_the_environment_variables_the_handlers_read_are_all_provided(self, template):
        provided = set(template["Globals"]["Function"]["Environment"]["Variables"])
        provided |= {"SNS_TOPIC_ARN", "AWS_REGION", "AWS_DEFAULT_REGION"}
        read: set[str] = set()
        for handler in (PATTERN_DIR / "functions").glob("*/handler.py"):
            read |= set(re.findall(r'os\.environ(?:\.get)?\(\s*"([A-Z0-9_]+)"', handler.read_text(encoding="utf-8")))
            read |= set(re.findall(r'os\.environ\["([A-Z0-9_]+)"\]', handler.read_text(encoding="utf-8")))
        # Read only when set (BEDROCK_TEMPERATURE) or provided by the Lambda runtime / shared modules.
        optional = {"BEDROCK_TEMPERATURE", "POLL_SECONDS", "OUTPUT_S3AP_ALIAS", "OUTPUT_S3AP_PREFIX"}
        assert read - provided - optional == set()

    def test_report_may_read_the_fields_json_it_reports_on(self, template):
        """report/handler.py re-reads each document's fields.json: the state carries only counts."""
        policies = template["Resources"]["ReportFunction"]["Properties"]["Policies"]
        actions = {a for p in policies if "Statement" in p for s in p["Statement"] for a in s["Action"]}
        assert {"s3:GetObject", "s3:PutObject"} <= actions

    def test_the_shared_layer_does_not_outlive_the_stack(self, template):
        """SAM keeps a deleted stack's layer versions by default; a deploy and cleanup left one behind."""
        assert template["Resources"]["SharedLayer"]["Properties"]["RetentionPolicy"] == "Delete"


class TestSecurityPosture:
    def test_buckets_are_encrypted_with_kms_and_block_public_access(self, template):
        for name in ("StagingBucket", "ResultsBucket"):
            props = template["Resources"][name]["Properties"]
            rule = props["BucketEncryption"]["ServerSideEncryptionConfiguration"][0]
            assert rule["ServerSideEncryptionByDefault"]["SSEAlgorithm"] == "aws:kms"
            assert set(props["PublicAccessBlockConfiguration"].values()) == {True}

    def test_staging_expires_in_one_day_and_is_deleted_with_the_stack(self, template):
        bucket = template["Resources"]["StagingBucket"]
        assert bucket["DeletionPolicy"] == "Delete"
        rule = bucket["Properties"]["LifecycleConfiguration"]["Rules"][0]
        assert rule["ExpirationInDays"] == 1

    def test_results_are_retained_with_the_stack(self, template):
        assert template["Resources"]["ResultsBucket"]["DeletionPolicy"] == "Retain"

    def test_both_buckets_refuse_plain_http(self, template):
        for name in ("StagingBucketPolicy", "ResultsBucketPolicy"):
            statement = template["Resources"][name]["Properties"]["PolicyDocument"]["Statement"][0]
            assert statement["Effect"] == "Deny"
            assert statement["Condition"] == {"Bool": {"aws:SecureTransport": "false"}}

    def test_the_state_machine_role_can_deliver_logs_when_logging_is_configured(self, template):
        """Found on a live deploy: with Policies given explicitly SAM adds no log-delivery permissions,
        and CreateStateMachine fails with "not authorized to access the Log Destination"."""
        props = template["Resources"]["OcrStateMachine"]["Properties"]
        assert props["Logging"]["Level"] == "ERROR"
        assert props["Logging"]["IncludeExecutionData"] is False  # the log never holds document text
        granted = {
            action
            for policy in props["Policies"]
            if "Statement" in policy
            for statement in policy["Statement"]
            for action in statement["Action"]
        }
        # The actions Step Functions documents for logging to CloudWatch Logs.
        needed = {
            "logs:CreateLogDelivery",
            "logs:GetLogDelivery",
            "logs:UpdateLogDelivery",
            "logs:DeleteLogDelivery",
            "logs:ListLogDeliveries",
            "logs:PutResourcePolicy",
            "logs:DescribeResourcePolicies",
            "logs:DescribeLogGroups",
        }
        assert needed <= granted, sorted(needed - granted)

    def test_sns_topic_is_encrypted(self, template):
        assert template["Resources"]["NotificationTopic"]["Properties"]["KmsMasterKeyId"]

    def test_gateway_role_grants_only_what_the_five_exposed_tools_need(self, template):
        policy = template["Resources"]["GatewayServiceRole"]["Properties"]["Policies"][0]["PolicyDocument"]
        actions = sorted(a for s in policy["Statement"] for a in s["Action"])
        assert actions == [
            "states:DescribeExecution",
            "states:DescribeStateMachine",
            "states:GetExecutionHistory",
            "states:ListExecutions",
            "states:StartExecution",
        ]

    def test_gateway_trust_is_limited_to_the_account(self, template):
        trust = template["Resources"]["GatewayServiceRole"]["Properties"]["AssumeRolePolicyDocument"]["Statement"][0]
        assert trust["Principal"] == {"Service": "bedrock-agentcore.amazonaws.com"}
        assert "aws:SourceAccount" in trust["Condition"]["StringEquals"]

    def test_connector_pins_exactly_the_three_pinnable_operations_and_exposes_five_tools(self, template):
        configs = template["Resources"]["OcrConnectorTarget"]["Properties"]["TargetConfiguration"]["Mcp"]["Connector"][
            "Configurations"
        ]
        by_name = {c["Name"]: c for c in configs}
        assert set(by_name) == {
            "StartExecution",
            "ListExecutions",
            "DescribeStateMachine",
            "DescribeExecution",
            "GetExecutionHistory",
        }
        for name in ("StartExecution", "ListExecutions", "DescribeStateMachine"):
            assert by_name[name]["ParameterValues"] == {"stateMachineArn": {"Ref": "OcrStateMachine"}}
        for name in ("DescribeExecution", "GetExecutionHistory"):
            assert "ParameterValues" not in by_name[name]

    def test_task_token_operations_are_not_exposed(self, template):
        text = json.dumps(template["Resources"]["OcrConnectorTarget"])
        for name in ("SendTaskSuccess", "SendTaskFailure", "SendTaskHeartbeat", "StopExecution", "StartSyncExecution"):
            assert name not in text

    def test_gateway_authorizer_is_a_parameter_limited_to_none_and_iam(self, template):
        assert template["Resources"]["AgentCoreGateway"]["Properties"]["AuthorizerType"] == {
            "Ref": "GatewayAuthorizerType"
        }
        assert template["Parameters"]["GatewayAuthorizerType"]["AllowedValues"] == ["NONE", "AWS_IAM"]

    def test_bedrock_is_granted_only_when_field_extraction_is_on(self, template):
        statements = template["Resources"]["ExtractFieldsFunction"]["Properties"]["Policies"][0]["Statement"]
        bedrock = [s for s in statements if "If" in s]
        assert len(bedrock) == 1 and bedrock[0]["If"][0] == "FieldExtractionEnabled"
        assert "bedrock:InvokeModel" in json.dumps(bedrock[0])
        # and no other function can call Bedrock
        for name, resource in template["Resources"].items():
            if resource["Type"] == "AWS::Serverless::Function" and name != "ExtractFieldsFunction":
                assert "bedrock" not in json.dumps(resource).lower(), name

    def test_forms_and_queries_are_never_requested(self):
        for handler in (PATTERN_DIR / "functions").glob("*/handler.py"):
            text = handler.read_text(encoding="utf-8")
            assert '"FORMS"' not in text and '"QUERIES"' not in text, handler

    def test_textract_is_never_pointed_at_the_access_point(self):
        """S3 Access Points cannot be read by Textract by reference (docs/agent/pitfalls-s3ap-ontap.md).

        Synchronous calls must pass `{"Bytes": ...}`; asynchronous calls may name only the staging bucket.
        Checked on the syntax tree: a regex over the source missed a deliberately broken handler.
        """
        findings = textract_document_arguments()
        assert findings, "no Textract call found: the check would pass vacuously"
        for path, line, shape in findings:
            if shape == "Bytes":
                continue
            assert shape == "staging", f"{path}:{line} passes {shape} to Textract"

    def test_the_access_point_check_itself_catches_a_broken_handler(self, tmp_path):
        broken = tmp_path / "handler.py"
        broken.write_text(
            "import os\n"
            "def f(c, key):\n"
            '    return c.detect_document_text(Document={"S3Object": {"Bucket": os.environ["S3_ACCESS_POINT_ALIAS"], "Name": key}})\n'
        )
        shapes = [s for _, _, s in textract_document_arguments([broken])]
        assert shapes == ["S3Object(not staging)"]
