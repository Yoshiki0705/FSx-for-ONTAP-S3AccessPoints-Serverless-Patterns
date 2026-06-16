"""UC30 Amazon Quick Agentic Workspace — Lambda ハンドラーのユニットテスト"""

from __future__ import annotations

import importlib.util
import json
import os
from unittest.mock import patch


def _load_handler(function_name: str):
    handler_path = os.path.join(
        os.path.dirname(__file__), "..", "functions", function_name, "handler.py"
    )
    spec = importlib.util.spec_from_file_location(f"uc30_{function_name}_handler", handler_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestQuickAction:
    """Quick Flows アクション API のテスト"""

    def test_unknown_action_returns_400(self):
        module = _load_handler("quick_action")
        resp = module.handler({"action": "nope"}, None)
        assert resp["statusCode"] == 400

    def test_create_action_item(self):
        module = _load_handler("quick_action")
        with patch.dict(os.environ, {"NOTIFICATION_TOPIC_ARN": ""}, clear=False):
            resp = module.handler(
                {"action": "create_action_item", "params": {"title": "PoC日程調整", "assignee": "sales"}},
                None,
            )
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["status"] == "completed"
        assert body["item"]["title"] == "PoC日程調整"
        assert body["item"]["status"] == "open"

    def test_generate_brief_invokes_bedrock(self):
        module = _load_handler("quick_action")
        converse_resp = {
            "output": {"message": {"content": [{"text": "ブリーフ要約テキスト"}]}}
        }
        event = {
            "action": "generate_brief",
            "params": {"title": "案件サマリ", "context": "製品Xの提案状況..."},
        }
        with patch.object(module.bedrock_runtime, "converse", return_value=converse_resp):
            resp = module.handler(event, None)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert "ブリーフ" in body["brief"]

    def test_api_gateway_body_parsed(self):
        module = _load_handler("quick_action")
        event = {"body": json.dumps({"action": "create_action_item", "params": {"title": "T"}})}
        with patch.dict(os.environ, {"NOTIFICATION_TOPIC_ARN": ""}, clear=False):
            resp = module.handler(event, None)
        assert resp["statusCode"] == 200

    def test_request_approval_pending_for_high_risk(self):
        module = _load_handler("quick_action")
        event = {
            "action": "request_approval",
            "params": {"operation": "approve_payment", "requested_by": "finance", "summary": "支払承認"},
        }
        with patch.dict(os.environ, {"NOTIFICATION_TOPIC_ARN": ""}, clear=False):
            resp = module.handler(event, None)
        assert resp["statusCode"] == 202
        body = json.loads(resp["body"])
        assert body["status"] == "pending_approval"
        assert body["approval"]["high_risk"] is True
        assert body["approval"]["status"] == "pending_approval"
        # 非強制スタブであることを明示
        assert body["approval"]["enforced"] is False
        # 監査の requested_by は本文ではなく呼び出し元（直接呼び出しは direct-invoke）
        assert body["approval"]["requested_by"] == "direct-invoke"

    def test_requested_by_not_spoofable_from_body(self):
        """本文の requested_by は監査値に採用されない（SigV4 呼び出し元を使用）。"""
        module = _load_handler("quick_action")
        event = {
            "action": "request_approval",
            "requestContext": {"identity": {"userArn": "arn:aws:iam::111122223333:role/QuickConn"}},
            "params": {"operation": "send_email", "requested_by": "ceo@example.com"},
        }
        with patch.dict(os.environ, {"NOTIFICATION_TOPIC_ARN": ""}, clear=False):
            resp = module.handler(event, None)
        body = json.loads(resp["body"])
        assert body["approval"]["requested_by"] == "arn:aws:iam::111122223333:role/QuickConn"

    def test_request_approval_low_risk(self):
        module = _load_handler("quick_action")
        event = {"action": "request_approval", "params": {"operation": "noop_op"}}
        with patch.dict(os.environ, {"NOTIFICATION_TOPIC_ARN": ""}, clear=False):
            resp = module.handler(event, None)
        body = json.loads(resp["body"])
        assert body["approval"]["high_risk"] is False

    def test_request_approval_missing_operation(self):
        module = _load_handler("quick_action")
        resp = module.handler({"action": "request_approval", "params": {}}, None)
        body = json.loads(resp["body"])
        assert body["status"] == "error"

    def test_generate_brief_missing_context(self):
        module = _load_handler("quick_action")
        resp = module.handler({"action": "generate_brief", "params": {"title": "T"}}, None)
        body = json.loads(resp["body"])
        assert body["status"] == "error"

    def test_internal_error_not_leaked(self):
        """例外時に内部詳細（str(e)）を返さない。"""
        module = _load_handler("quick_action")
        with patch.object(module, "_generate_brief", side_effect=Exception("secret ARN detail")):
            resp = module.handler({"action": "generate_brief", "params": {"context": "x"}}, None)
        assert resp["statusCode"] == 500
        body = json.loads(resp["body"])
        assert body["error"] == "internal error"
        assert "secret ARN detail" not in resp["body"]


class TestAthenaQuery:
    """Athena Query Lambda のテスト"""

    def test_missing_db_returns_error(self):
        module = _load_handler("athena_query")
        with patch.dict(os.environ, {"ATHENA_DATABASE": ""}, clear=False):
            result = module.handler({"sql": "SELECT 1"}, None)
        assert result["status"] == "error"

    def test_raw_sql_rejected_by_default(self):
        """既定（ALLOW_RAW_SQL 未設定）では任意 SQL を拒否する。"""
        module = _load_handler("athena_query")
        env = {"ATHENA_DATABASE": "quick_workspace_db", "ATHENA_WORKGROUP": "wg", "ATHENA_OUTPUT_LOCATION": "s3://b/r/"}
        with patch.dict(os.environ, env, clear=False):
            with patch.dict(os.environ, {"ALLOW_RAW_SQL": "false"}, clear=False):
                result = module.handler({"sql": "SELECT * FROM finance_secret"}, None)
        assert result["status"] == "error"
        assert "raw sql is disabled" in result["error"]
        assert "sales_pipeline_total" in result["allowed_queries"]

    def test_raw_sql_allowed_when_enabled(self):
        """ALLOW_RAW_SQL=true の管理用途では任意 SQL を実行する。"""
        module = _load_handler("athena_query")
        env = {
            "ATHENA_DATABASE": "quick_workspace_db",
            "ATHENA_WORKGROUP": "wg",
            "ATHENA_OUTPUT_LOCATION": "s3://b/r/",
            "ALLOW_RAW_SQL": "true",
        }
        rows = {"ResultSet": {"Rows": [{"Data": [{"VarCharValue": "c"}]}]}}
        with patch.dict(os.environ, env, clear=False):
            with patch.object(module.athena_client, "start_query_execution", return_value={"QueryExecutionId": "q1"}):
                with patch.object(
                    module.athena_client, "get_query_execution",
                    return_value={"QueryExecution": {"Status": {"State": "SUCCEEDED"}}},
                ):
                    with patch.object(module.athena_client, "get_query_results", return_value=rows):
                        result = module.handler({"sql": "SELECT 1 AS c"}, None)
        assert result["status"] == "completed"

    def test_internal_error_not_leaked(self):
        module = _load_handler("athena_query")
        env = {"ATHENA_DATABASE": "quick_workspace_db", "ATHENA_WORKGROUP": "wg", "ATHENA_OUTPUT_LOCATION": "s3://b/r/"}
        with patch.dict(os.environ, env, clear=False):
            with patch.object(
                module.athena_client, "start_query_execution", side_effect=Exception("arn:secret")
            ):
                result = module.handler({"query_name": "sales_pipeline_total"}, None)
        assert result["status"] == "error"
        assert result["error"] == "internal error"
        module = _load_handler("athena_query")
        env = {"ATHENA_DATABASE": "quick_workspace_db", "ATHENA_WORKGROUP": "wg", "ATHENA_OUTPUT_LOCATION": "s3://b/r/"}
        rows = {
            "ResultSet": {
                "Rows": [
                    {"Data": [{"VarCharValue": "stage"}, {"VarCharValue": "total_jpy"}]},
                    {"Data": [{"VarCharValue": "Negotiation"}, {"VarCharValue": "1200000"}]},
                ]
            }
        }
        with patch.dict(os.environ, env, clear=False):
            with patch.object(module.athena_client, "start_query_execution", return_value={"QueryExecutionId": "q1"}):
                with patch.object(
                    module.athena_client,
                    "get_query_execution",
                    return_value={"QueryExecution": {"Status": {"State": "SUCCEEDED"}}},
                ):
                    with patch.object(module.athena_client, "get_query_results", return_value=rows):
                        result = module.handler({"query_name": "sales_pipeline_total"}, None)
        assert result["status"] == "completed"
        assert result["columns"] == ["stage", "total_jpy"]
        assert result["row_count"] == 1


class TestDataPrep:
    """Data Prep Lambda のテスト"""

    def test_missing_alias_returns_error(self):
        module = _load_handler("data_prep")
        with patch.dict(os.environ, {"S3_ACCESS_POINT_ALIAS": ""}, clear=False):
            result = module.handler({}, None)
        assert result["status"] == "error"

    def test_manifest_classifies_by_service_and_role(self):
        module = _load_handler("data_prep")
        list_resp = {
            "Contents": [
                {"Key": "quick-workspace/index/sales/spec.md"},
                {"Key": "quick-workspace/analytics/finance/budget.csv"},
                {"Key": "quick-workspace/flows/legal/approval.json"},
                {"Key": "quick-workspace/index/"},  # フォルダーマーカーは無視
            ],
            "IsTruncated": False,
        }
        with patch.dict(os.environ, {"S3_ACCESS_POINT_ALIAS": "alias"}, clear=False):
            with patch.object(module.s3_client, "list_objects_v2", return_value=list_resp):
                result = module.handler({"prefix": "quick-workspace/"}, None)
        assert result["status"] == "completed"
        assert result["total_objects"] == 3
        assert result["by_service"]["index"] == 1
        assert result["by_service"]["analytics"] == 1
        assert result["by_service"]["flows"] == 1
        assert result["by_role"]["sales"] == 1

    def test_prefix_clamped_to_workspace(self):
        """WORKSPACE_PREFIX 外の prefix 要求はクランプされる（スコープ逸脱防止）。"""
        module = _load_handler("data_prep")
        captured = {}

        def _capture(**kwargs):
            captured.update(kwargs)
            return {"Contents": [], "IsTruncated": False}

        env = {"S3_ACCESS_POINT_ALIAS": "alias", "WORKSPACE_PREFIX": "quick-workspace/"}
        with patch.dict(os.environ, env, clear=False):
            with patch.object(module.s3_client, "list_objects_v2", side_effect=_capture):
                result = module.handler({"prefix": ""}, None)
        assert result["status"] == "completed"
        # 空 prefix は WORKSPACE_PREFIX にクランプされる
        assert captured["Prefix"] == "quick-workspace/"
