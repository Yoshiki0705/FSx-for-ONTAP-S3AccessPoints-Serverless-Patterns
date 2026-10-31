"""Unit tests for the stepfunctions-agentcore-tools handlers."""

from __future__ import annotations

import json
import os
from io import BytesIO
from unittest.mock import patch

import boto3
import pytest
from helpers import load_handler
from moto import mock_aws

TEST_BUCKET = "demo-bucket"
TEST_ENV = {
    "S3_ACCESS_POINT_ALIAS": TEST_BUCKET,
    "FILE_PREFIX": "input/",
    "MAX_FILES": "100",
    "AWS_DEFAULT_REGION": "ap-northeast-1",
}


@pytest.fixture
def seeded_bucket():
    """Create a demo S3 bucket with a few objects (DemoMode uses a regular bucket)."""
    with mock_aws():
        s3 = boto3.client("s3", region_name="ap-northeast-1")
        s3.create_bucket(
            Bucket=TEST_BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
        )
        s3.put_object(Bucket=TEST_BUCKET, Key="input/order_001.idoc", Body=b"ORDERS idoc body")
        s3.put_object(Bucket=TEST_BUCKET, Key="input/extract_002.csv", Body=b"a,b,c\n1,2,3")
        yield s3


class TestDiscovery:
    @patch.dict(os.environ, TEST_ENV)
    def test_lists_and_categorizes(self, seeded_bucket):
        module = load_handler("discovery")
        result = module.handler({}, None)

        assert result["status"] == "completed"
        assert result["object_count"] == 2
        categories = {obj["category"] for obj in result["objects"]}
        assert "sap_idoc" in categories
        assert "data_extract" in categories

    @patch.dict(os.environ, {**TEST_ENV, "MAX_FILES": "1"})
    def test_respects_max_files(self, seeded_bucket):
        module = load_handler("discovery")
        result = module.handler({"max_files": 1}, None)
        assert result["object_count"] == 1
        assert result["truncated"] is True


class TestProcessing:
    @patch.dict(os.environ, TEST_ENV)
    def test_summarizes_and_evaluates_confidence(self, seeded_bucket):
        module = load_handler("processing")

        fake_body = BytesIO(json.dumps({"output": {"message": {"content": [{"text": "A" * 60}]}}}).encode())
        with patch.object(module._bedrock, "invoke_model", return_value={"body": fake_body}):
            result = module.handler({"key": "input/order_001.idoc", "category": "sap_idoc", "size": 16}, None)

        assert result["status"] == "completed"
        assert result["confidence"] >= 0.85
        assert result["human_review"]["action"] == "AUTO_APPROVE"

    @patch.dict(os.environ, TEST_ENV)
    def test_bedrock_failure_lowers_confidence(self, seeded_bucket):
        module = load_handler("processing")
        with patch.object(module._bedrock, "invoke_model", side_effect=RuntimeError("boom")):
            result = module.handler({"key": "input/extract_002.csv", "category": "data_extract", "size": 11}, None)
        # Confidence 0.0 is below the reject threshold -> REJECT, review required.
        assert result["confidence"] == 0.0
        assert result["human_review"]["requires_review"] is True


class TestReport:
    @patch.dict(os.environ, {"DATA_CLASSIFICATION": "INTERNAL"})
    def test_aggregates_results(self):
        module = load_handler("report")
        processed = [
            {"status": "completed", "category": "sap_idoc", "human_review": {"requires_review": False}},
            {"status": "completed", "category": "data_extract", "human_review": {"requires_review": True}},
            {"status": "error", "category": "sap_idoc"},
        ]
        with patch.object(module._sns, "publish") as pub:
            result = module.handler({"processed": processed}, None)

        summary = result["report"]["summary"]
        assert summary["total_files"] == 3
        assert summary["succeeded"] == 2
        assert summary["failed"] == 1
        assert summary["human_review_required"] == 1
        assert result["data_classification"].startswith("Internal")
        # No SNS topic configured in env -> publish skipped.
        pub.assert_not_called()

    @patch.dict(
        os.environ, {"DATA_CLASSIFICATION": "INTERNAL", "SNS_TOPIC_ARN": "arn:aws:sns:ap-northeast-1:123456789012:t"}
    )
    def test_error_mode(self):
        module = load_handler("report")
        with patch.object(module._sns, "publish") as pub:
            result = module.handler({"status": "ERROR", "error": {"Cause": "x"}}, None)
        assert result["status"] == "error"
        assert result["report"]["error"] == {"Cause": "x"}
        pub.assert_called_once()


def test_report_handles_empty_input():
    """NoFiles path passes an empty processed list."""
    module = load_handler("report")
    with patch.dict(os.environ, {"DATA_CLASSIFICATION": "INTERNAL"}):
        result = module.handler({"processed": []}, None)
    assert result["report"]["summary"]["total_files"] == 0
    assert result["report"]["summary"]["success_rate_pct"] == 0.0
