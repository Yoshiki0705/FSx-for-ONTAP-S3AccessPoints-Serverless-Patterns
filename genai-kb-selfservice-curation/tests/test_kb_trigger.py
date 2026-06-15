"""UC29 Scenario C — KB Trigger Lambda のユニットテスト"""

from __future__ import annotations

import importlib.util
import os
import pytest
from botocore.exceptions import ClientError
from unittest.mock import patch


def _load_handler():
    handler_path = os.path.join(
        os.path.dirname(__file__), "..", "functions", "kb_trigger", "handler.py"
    )
    spec = importlib.util.spec_from_file_location("uc29_kb_trigger_handler", handler_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Ctx:
    aws_request_id = "req-123"


ENV = {
    "KNOWLEDGE_BASE_ID": "KB123",
    "DATA_SOURCE_ID": "DS456",
    "FPOLICY_PATH_FILTER": "ai_knowledge",
    "NOTIFICATION_TOPIC_ARN": "",
}


def _fpolicy_event(operation: str = "create", path: str = "ai_knowledge/sales/spec.md") -> dict:
    return {
        "source": "fsxn.fpolicy",
        "detail-type": "FPolicy File Operation",
        "detail": {
            "event_id": "11111111-1111-4111-8111-111111111111",
            "operation_type": operation,
            "file_path": path,
            "volume_name": "ai_knowledge",
            "svm_name": "uc29demosvm",
            "timestamp": "2026-06-15T23:00:00Z",
            "file_size": 1024,
        },
    }


class TestKbTrigger:
    def test_missing_config_returns_error(self):
        module = _load_handler()
        with patch.dict(os.environ, {"KNOWLEDGE_BASE_ID": "", "DATA_SOURCE_ID": ""}, clear=False):
            result = module.handler(_fpolicy_event(), _Ctx())
        assert result["status"] == "error"
        assert result["reason"] == "missing_configuration"

    def test_prefix_mismatch_skips(self):
        module = _load_handler()
        with patch.dict(os.environ, ENV, clear=False):
            result = module.handler(_fpolicy_event(path="other-data/file.md"), _Ctx())
        assert result["status"] == "skipped"
        assert result["reason"] == "path_filter_mismatch"

    def test_event_triggers_ingestion(self):
        module = _load_handler()
        start_resp = {"ingestionJob": {"ingestionJobId": "JOB789"}}
        with patch.dict(os.environ, ENV, clear=False):
            with patch.object(module, "_find_active_ingestion_job", return_value=None):
                with patch.object(
                    module.bedrock_agent, "start_ingestion_job", return_value=start_resp
                ) as start:
                    result = module.handler(_fpolicy_event("create"), _Ctx())
        assert result["status"] == "ingestion_started"
        assert result["trigger"] == "fpolicy_event"
        assert result["ingestion_job_id"] == "JOB789"
        start.assert_called_once()

    def test_debounce_skips_when_in_progress(self):
        module = _load_handler()
        with patch.dict(os.environ, ENV, clear=False):
            with patch.object(module, "_find_active_ingestion_job", return_value="ACTIVE1"):
                with patch.object(module.bedrock_agent, "start_ingestion_job") as start:
                    result = module.handler(_fpolicy_event("write"), _Ctx())
        assert result["status"] == "ingestion_in_progress"
        assert result["active_ingestion_job_id"] == "ACTIVE1"
        start.assert_not_called()

    def test_delete_operation_triggers_ingestion(self):
        module = _load_handler()
        start_resp = {"ingestionJob": {"ingestionJobId": "JOBDEL"}}
        with patch.dict(os.environ, ENV, clear=False):
            with patch.object(module, "_find_active_ingestion_job", return_value=None):
                with patch.object(
                    module.bedrock_agent, "start_ingestion_job", return_value=start_resp
                ):
                    result = module.handler(
                        _fpolicy_event("delete", "ai_knowledge/sales/old.md"), _Ctx()
                    )
        assert result["status"] == "ingestion_started"
        assert result["operation"] == "delete"

    def test_start_ingestion_unexpected_error_reraises(self):
        """予期せぬ例外は再送出され、Lambda 非同期リトライ/DLQ を発火させる。"""
        module = _load_handler()
        with patch.dict(os.environ, ENV, clear=False):
            with patch.object(module, "_find_active_ingestion_job", return_value=None):
                with patch.object(
                    module.bedrock_agent,
                    "start_ingestion_job",
                    side_effect=Exception("unexpected"),
                ):
                    with pytest.raises(Exception, match="unexpected"):
                        module.handler(_fpolicy_event(), _Ctx())

    def test_start_ingestion_throttling_reraises(self):
        """ThrottlingException など ClientError（Conflict 以外）は再送出される。"""
        module = _load_handler()
        err = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "rate exceeded"}},
            "StartIngestionJob",
        )
        with patch.dict(os.environ, ENV, clear=False):
            with patch.object(module, "_find_active_ingestion_job", return_value=None):
                with patch.object(
                    module.bedrock_agent, "start_ingestion_job", side_effect=err
                ):
                    with pytest.raises(ClientError):
                        module.handler(_fpolicy_event(), _Ctx())

    def test_conflict_exception_treated_as_skip(self):
        """検知とジョブ開始の競合（ConflictException）は進行中扱いでスキップ（リトライ不要）。"""
        module = _load_handler()
        err = ClientError(
            {"Error": {"Code": "ConflictException", "Message": "ongoing ingestion job"}},
            "StartIngestionJob",
        )
        with patch.dict(os.environ, ENV, clear=False):
            with patch.object(module, "_find_active_ingestion_job", return_value=None):
                with patch.object(
                    module.bedrock_agent, "start_ingestion_job", side_effect=err
                ):
                    result = module.handler(_fpolicy_event(), _Ctx())
        assert result["status"] == "ingestion_in_progress"
        assert result["reason"] == "conflict_exception"

    def test_documented_schema_contract(self):
        """デモガイドに記載のイベント本体スキーマ（operation_type/file_path）で動作する。"""
        module = _load_handler()
        # demo-guide / fpolicy-event-schema.json と同じフィールド名
        event = {
            "source": "fsxn.fpolicy",
            "detail-type": "FPolicy File Operation",
            "detail": {
                "event_id": "33333333-3333-4333-8333-333333333333",
                "operation_type": "create",
                "file_path": "ai_knowledge/legal/contracts/nda.md",
                "volume_name": "ai_knowledge",
                "svm_name": "uc29demosvm",
                "timestamp": "2026-06-16T01:00:00Z",
                "file_size": 512,
            },
        }
        start_resp = {"ingestionJob": {"ingestionJobId": "JOBSCHEMA"}}
        with patch.dict(os.environ, ENV, clear=False):
            with patch.object(module, "_find_active_ingestion_job", return_value=None):
                with patch.object(
                    module.bedrock_agent, "start_ingestion_job", return_value=start_resp
                ):
                    result = module.handler(event, _Ctx())
        assert result["status"] == "ingestion_started"

    def test_find_active_job_returns_id(self):
        module = _load_handler()
        list_resp = {"ingestionJobSummaries": [{"ingestionJobId": "RUN1", "status": "IN_PROGRESS"}]}
        with patch.object(module.bedrock_agent, "list_ingestion_jobs", return_value=list_resp):
            job = module._find_active_ingestion_job("KB123", "DS456")
        assert job == "RUN1"

    def test_find_active_job_none_when_empty(self):
        module = _load_handler()
        with patch.object(
            module.bedrock_agent, "list_ingestion_jobs", return_value={"ingestionJobSummaries": []}
        ):
            job = module._find_active_ingestion_job("KB123", "DS456")
        assert job is None
