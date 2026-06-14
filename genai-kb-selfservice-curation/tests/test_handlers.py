"""UC29 Self-Service KB Curation — Lambda ハンドラーのユニットテスト"""

from __future__ import annotations

import importlib.util
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch


def _load_handler(function_name: str):
    """指定した関数のハンドラーモジュールをロード（importlib 方式）"""
    handler_path = os.path.join(
        os.path.dirname(__file__), "..", "functions", function_name, "handler.py"
    )
    spec = importlib.util.spec_from_file_location(f"uc29_{function_name}_handler", handler_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


AUTO_SYNC_ENV = {
    "S3_ACCESS_POINT_ALIAS": "test-s3ap-alias",
    "KNOWLEDGE_BASE_ID": "KB123",
    "DATA_SOURCE_ID": "DS456",
    "INGESTION_PREFIX": "sales/",
    "NOTIFICATION_TOPIC_ARN": "",
}


class TestAutoSync:
    """Auto-Sync Lambda のテスト"""

    @staticmethod
    def _jobs_side_effect(active_jobs, last_started):
        """list_ingestion_jobs のモック。STATUS フィルタ時は進行中ジョブ、sortBy 時は直近ジョブ。"""
        def _fn(**kwargs):
            if "filters" in kwargs:
                return {"ingestionJobSummaries": active_jobs}
            if last_started is not None:
                return {"ingestionJobSummaries": [{"startedAt": last_started}]}
            return {"ingestionJobSummaries": []}
        return _fn

    def test_missing_config_returns_error(self):
        module = _load_handler("auto_sync")
        with patch.dict(os.environ, {"S3_ACCESS_POINT_ALIAS": "", "KNOWLEDGE_BASE_ID": "", "DATA_SOURCE_ID": ""}, clear=False):
            result = module.handler({}, None)
        assert result["status"] == "error"

    def test_no_change_skips_ingestion(self):
        module = _load_handler("auto_sync")
        old = datetime(2020, 1, 1, tzinfo=timezone.utc)
        last_job = datetime(2026, 1, 1, tzinfo=timezone.utc)
        list_resp = {
            "Contents": [
                {"Key": "sales/a.pdf", "LastModified": old},
                {"Key": "sales/b.jpg", "LastModified": last_job + timedelta(days=1)},
            ],
            "IsTruncated": False,
        }
        with patch.dict(os.environ, AUTO_SYNC_ENV, clear=False):
            with patch.object(module.bedrock_agent, "list_ingestion_jobs", side_effect=self._jobs_side_effect([], last_job)):
                with patch.object(module.s3_client, "list_objects_v2", return_value=list_resp):
                    result = module.handler({}, None)
        assert result["status"] == "no_change"
        assert result["changed_files_detected"] == 0

    def test_changed_file_triggers_ingestion(self):
        module = _load_handler("auto_sync")
        last_job = datetime(2026, 1, 1, tzinfo=timezone.utc)
        list_resp = {
            "Contents": [
                {"Key": "sales/new-spec.pdf", "LastModified": last_job + timedelta(hours=1)},
            ],
            "IsTruncated": False,
        }
        start_resp = {"ingestionJob": {"ingestionJobId": "JOB789"}}
        with patch.dict(os.environ, AUTO_SYNC_ENV, clear=False):
            with patch.object(module.bedrock_agent, "list_ingestion_jobs", side_effect=self._jobs_side_effect([], last_job)):
                with patch.object(module.s3_client, "list_objects_v2", return_value=list_resp):
                    with patch.object(module.bedrock_agent, "start_ingestion_job", return_value=start_resp) as start:
                        result = module.handler({}, None)
        assert result["status"] == "ingestion_started"
        assert result["changed_files_detected"] == 1
        assert result["ingestion_job_id"] == "JOB789"
        start.assert_called_once()

    def test_force_triggers_even_without_change(self):
        module = _load_handler("auto_sync")
        list_resp = {"Contents": [], "IsTruncated": False}
        start_resp = {"ingestionJob": {"ingestionJobId": "JOBFORCE"}}
        with patch.dict(os.environ, AUTO_SYNC_ENV, clear=False):
            with patch.object(module.bedrock_agent, "list_ingestion_jobs", side_effect=self._jobs_side_effect([], None)):
                with patch.object(module.s3_client, "list_objects_v2", return_value=list_resp):
                    with patch.object(module.bedrock_agent, "start_ingestion_job", return_value=start_resp) as start:
                        result = module.handler({"force": True}, None)
        assert result["status"] == "ingestion_started"
        assert result["forced"] is True
        start.assert_called_once()

    def test_skips_when_ingestion_in_progress(self):
        module = _load_handler("auto_sync")
        with patch.dict(os.environ, AUTO_SYNC_ENV, clear=False):
            with patch.object(
                module.bedrock_agent,
                "list_ingestion_jobs",
                side_effect=self._jobs_side_effect([{"ingestionJobId": "ACTIVE1"}], None),
            ):
                with patch.object(module.bedrock_agent, "start_ingestion_job") as start:
                    result = module.handler({"force": True}, None)
        assert result["status"] == "ingestion_in_progress"
        assert result["active_ingestion_job_id"] == "ACTIVE1"
        start.assert_not_called()


class TestIngestionStatus:
    """Ingestion Status Lambda のテスト"""

    def test_missing_ids_returns_error(self):
        module = _load_handler("ingestion_status")
        result = module.handler({"ingestion_job_id": "JOB1"}, None)
        assert result["status"] == "error"
        assert result["ingestion_status"] == "UNKNOWN"

    def test_complete_status_returned(self):
        module = _load_handler("ingestion_status")
        job_resp = {
            "ingestionJob": {
                "status": "COMPLETE",
                "statistics": {
                    "numberOfDocumentsScanned": 12,
                    "numberOfNewDocumentsIndexed": 1,
                    "numberOfDocumentsFailed": 0,
                },
            }
        }
        event = {"knowledge_base_id": "KB1", "data_source_id": "DS1", "ingestion_job_id": "JOB1"}
        with patch.object(module.bedrock_agent, "get_ingestion_job", return_value=job_resp):
            result = module.handler(event, None)
        assert result["status"] == "completed"
        assert result["ingestion_status"] == "COMPLETE"
        assert result["documents_indexed"] == 1


class TestQuery:
    """Query Lambda のテスト"""

    def test_missing_query_returns_error(self):
        module = _load_handler("query")
        with patch.dict(os.environ, {"KNOWLEDGE_BASE_ID": "KB123"}, clear=False):
            result = module.handler({"query": ""}, None)
        assert result["status"] == "error"

    def test_retrieve_and_generate_success(self):
        module = _load_handler("query")
        rag_resp = {
            "output": {"text": "新製品Xの仕様は..."},
            "citations": [
                {
                    "retrievedReferences": [
                        {"location": {"s3Location": {"uri": "s3://ap/sales/product-x-spec.pdf"}}}
                    ]
                }
            ],
        }
        env = {"KNOWLEDGE_BASE_ID": "KB123", "BEDROCK_LLM_MODEL_ID": "amazon.nova-pro-v1:0", "AWS_REGION": "ap-northeast-1"}
        with patch.dict(os.environ, env, clear=False):
            with patch.object(module.bedrock_runtime, "retrieve_and_generate", return_value=rag_resp):
                result = module.handler({"query": "新製品Xの主な仕様を教えて"}, None)
        assert result["status"] == "completed"
        assert "新製品X" in result["answer"]
        assert result["citations"][0]["source"].endswith("product-x-spec.pdf")

    def test_role_filter_builds_metadata_filter(self):
        module = _load_handler("query")
        rag_resp = {"output": {"text": "ans"}, "citations": []}
        env = {"KNOWLEDGE_BASE_ID": "KB123", "BEDROCK_LLM_MODEL_ID": "amazon.nova-pro-v1:0", "AWS_REGION": "ap-northeast-1"}
        captured = {}

        def _capture(**kwargs):
            captured.update(kwargs)
            return rag_resp

        with patch.dict(os.environ, env, clear=False):
            with patch.object(module.bedrock_runtime, "retrieve_and_generate", side_effect=_capture):
                result = module.handler({"query": "q", "role": "sales"}, None)
        assert result["status"] == "completed"
        kb_cfg = captured["retrieveAndGenerateConfiguration"]["knowledgeBaseConfiguration"]
        flt = kb_cfg["retrievalConfiguration"]["vectorSearchConfiguration"]["filter"]
        assert flt == {"equals": {"key": "role", "value": "sales"}}
