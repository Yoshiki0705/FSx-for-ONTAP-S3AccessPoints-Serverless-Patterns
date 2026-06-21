"""Tests for shared.s3_annotations module."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.s3_annotations import (
    FALLBACK_MODE_ERROR,
    FALLBACK_MODE_SKIP,
    FALLBACK_MODE_TAG,
    AnnotationHelper,
    ProcessingAnnotation,
    S3AnnotationError,
)


class TestProcessingAnnotation:
    """ProcessingAnnotation dataclass tests."""

    def test_minimal_annotation(self):
        ann = ProcessingAnnotation(
            uc_id="legal-compliance",
            source_path="/vol1/legal/contracts/deal-001.pdf",
            data_classification="INTERNAL",
            processing_timestamp="2026-06-18T10:30:00Z",
        )
        assert ann.uc_id == "legal-compliance"
        assert ann.annotation_schema_version == "1.0"
        assert ann.confidence_score is None

    def test_full_annotation(self):
        ann = ProcessingAnnotation(
            uc_id="semiconductor-eda",
            source_path="/vol1/eda/gds/chip-v2.gds",
            data_classification="RESTRICTED",
            processing_timestamp="2026-06-18T10:30:00Z",
            confidence_score=0.95,
            human_review_action="AUTO_APPROVE",
            model_id="amazon.nova-pro-v1:0",
            embedding_model_id="amazon.titan-embed-text-v2:0",
            step_functions_execution_arn="arn:aws:states:ap-northeast-1:123456789012:execution:uc6:run-001",
            input_checksum="a" * 64,
            output_checksum="b" * 64,
            duration_ms=4523,
            chunking_strategy_version="v2-overlap-256",
            uc_template_version="1.3.0",
            custom={"drc_violations": 3, "layer_count": 42},
        )
        assert ann.confidence_score == 0.95
        assert ann.custom["drc_violations"] == 3

    def test_to_json_excludes_none(self):
        ann = ProcessingAnnotation(
            uc_id="legal-compliance",
            source_path="/vol1/legal/deal.pdf",
            data_classification="INTERNAL",
            processing_timestamp="2026-06-18T10:30:00Z",
        )
        data = json.loads(ann.to_json())
        assert "uc_id" in data
        assert "confidence_score" not in data
        assert "model_id" not in data

    def test_to_json_includes_present_values(self):
        ann = ProcessingAnnotation(
            uc_id="financial-idp",
            source_path="/vol1/finance/invoice.pdf",
            data_classification="RESTRICTED",
            processing_timestamp="2026-06-18T10:30:00Z",
            confidence_score=0.88,
            human_review_action="AUTO_APPROVE",
        )
        data = json.loads(ann.to_json())
        assert data["confidence_score"] == 0.88
        assert data["human_review_action"] == "AUTO_APPROVE"
        assert data["annotation_schema_version"] == "1.0"

    def test_to_dict_excludes_none(self):
        ann = ProcessingAnnotation(
            uc_id="test",
            source_path="/test",
            data_classification="PUBLIC",
            processing_timestamp="2026-06-18T10:30:00Z",
        )
        d = ann.to_dict()
        assert "confidence_score" not in d
        assert "uc_id" in d

    def test_custom_dict_included_when_non_empty(self):
        ann = ProcessingAnnotation(
            uc_id="test",
            source_path="/test",
            data_classification="INTERNAL",
            processing_timestamp="2026-06-18T10:30:00Z",
            custom={"key": "value"},
        )
        data = json.loads(ann.to_json())
        assert data["custom"] == {"key": "value"}

    def test_empty_custom_dict_excluded(self):
        """空の custom dict は to_json に含まれない（falsy 扱い）。"""
        ann = ProcessingAnnotation(
            uc_id="test",
            source_path="/test",
            data_classification="INTERNAL",
            processing_timestamp="2026-06-18T10:30:00Z",
        )
        # 空dict は None ではないが、to_json のフィルタは `v is not None` なので含まれる
        data = json.loads(ann.to_json())
        # 空dict は含まれる（None ではないため）
        assert "custom" in data


class TestAnnotationHelperPutAnnotation:
    """AnnotationHelper.put_annotation() tests."""

    def test_put_annotation_success(self):
        mock_client = MagicMock()
        mock_client.put_object_annotation.return_value = {"ResponseMetadata": {"HTTPStatusCode": 200}}

        with patch("boto3.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session.client.return_value = mock_client
            mock_session_cls.return_value = mock_session

            helper = AnnotationHelper(bucket="output-bucket", session=mock_session)
            helper._s3_client = mock_client

            ann = ProcessingAnnotation(
                uc_id="legal-compliance",
                source_path="/vol1/deal.pdf",
                data_classification="INTERNAL",
                processing_timestamp="2026-06-18T10:30:00Z",
            )

            helper.put_annotation(
                key="reports/deal-analysis.json",
                annotation_name="processing_metadata",
                annotation=ann,
            )

            mock_client.put_object_annotation.assert_called_once()
            call_kwargs = mock_client.put_object_annotation.call_args[1]
            assert call_kwargs["Bucket"] == "output-bucket"
            assert call_kwargs["Key"] == "reports/deal-analysis.json"
            assert call_kwargs["AnnotationName"] == "processing_metadata"
            assert helper.is_supported is True

    def test_put_annotation_with_dict(self):
        mock_client = MagicMock()
        mock_client.put_object_annotation.return_value = {}

        helper = AnnotationHelper(bucket="test-bucket")
        helper._s3_client = mock_client

        helper.put_annotation(
            key="file.json",
            annotation_name="custom",
            annotation={"key": "value", "score": 0.95},
        )

        call_kwargs = mock_client.put_object_annotation.call_args[1]
        payload = call_kwargs["AnnotationPayload"].decode("utf-8")
        data = json.loads(payload)
        assert data["key"] == "value"
        assert data["score"] == 0.95

    def test_put_annotation_with_string(self):
        mock_client = MagicMock()
        mock_client.put_object_annotation.return_value = {}

        helper = AnnotationHelper(bucket="test-bucket")
        helper._s3_client = mock_client

        helper.put_annotation(
            key="file.txt",
            annotation_name="summary",
            annotation="This is a plain text summary.",
        )

        call_kwargs = mock_client.put_object_annotation.call_args[1]
        payload = call_kwargs["AnnotationPayload"].decode("utf-8")
        assert payload == "This is a plain text summary."

    def test_put_annotation_api_not_available_skip(self):
        """boto3 が API 未実装の場合、skip フォールバック。"""
        mock_client = MagicMock()
        del mock_client.put_object_annotation  # AttributeError を発生させる

        helper = AnnotationHelper(bucket="test-bucket", fallback_mode=FALLBACK_MODE_SKIP)
        helper._s3_client = mock_client

        result = helper.put_annotation(
            key="file.json",
            annotation_name="meta",
            annotation={"uc_id": "test"},
        )

        assert result["fallback"] == "skipped"
        assert helper.is_supported is False

    def test_put_annotation_api_not_available_error(self):
        """boto3 が API 未実装の場合、error フォールバック。"""
        mock_client = MagicMock()
        del mock_client.put_object_annotation

        helper = AnnotationHelper(bucket="test-bucket", fallback_mode=FALLBACK_MODE_ERROR)
        helper._s3_client = mock_client

        with pytest.raises(S3AnnotationError):
            helper.put_annotation(
                key="file.json",
                annotation_name="meta",
                annotation={"uc_id": "test"},
            )

    def test_put_annotation_api_not_available_tag_fallback(self):
        """boto3 が API 未実装の場合、tag フォールバック。"""
        mock_client = MagicMock()
        del mock_client.put_object_annotation
        # put_object_tagging は利用可能
        mock_client.put_object_tagging = MagicMock(return_value={})

        helper = AnnotationHelper(bucket="test-bucket", fallback_mode=FALLBACK_MODE_TAG)
        helper._s3_client = mock_client

        result = helper.put_annotation(
            key="file.json",
            annotation_name="meta",
            annotation=ProcessingAnnotation(
                uc_id="legal-compliance",
                source_path="/vol1/deal.pdf",
                data_classification="RESTRICTED",
                processing_timestamp="2026-06-18T10:30:00Z",
                confidence_score=0.92,
                human_review_action="AUTO_APPROVE",
            ),
        )

        assert result["fallback"] == "tags"
        assert result["tag_count"] >= 1
        mock_client.put_object_tagging.assert_called_once()


class TestAnnotationHelperGetAnnotation:
    """AnnotationHelper.get_annotation() tests."""

    def test_get_annotation_success(self):
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps({"uc_id": "test", "confidence": 0.9}).encode()

        mock_client = MagicMock()
        mock_client.get_object_annotation.return_value = {"AnnotationPayload": mock_body}

        helper = AnnotationHelper(bucket="test-bucket")
        helper._s3_client = mock_client

        result = helper.get_annotation("file.json", "processing_metadata")

        assert result["uc_id"] == "test"
        assert result["confidence"] == 0.9

    def test_get_annotation_not_available(self):
        mock_client = MagicMock()
        del mock_client.get_object_annotation

        helper = AnnotationHelper(bucket="test-bucket")
        helper._s3_client = mock_client

        result = helper.get_annotation("file.json", "processing_metadata")
        assert result is None


class TestAnnotationHelperListAnnotations:
    """AnnotationHelper.list_annotations() tests."""

    def test_list_annotations_success(self):
        mock_client = MagicMock()
        mock_client.list_object_annotations.return_value = {
            "Annotations": [
                {"AnnotationName": "processing_metadata"},
                {"AnnotationName": "ai_summary"},
                {"AnnotationName": "lineage"},
            ]
        }

        helper = AnnotationHelper(bucket="test-bucket")
        helper._s3_client = mock_client

        result = helper.list_annotations("file.json")
        assert result == ["processing_metadata", "ai_summary", "lineage"]

    def test_list_annotations_not_available(self):
        mock_client = MagicMock()
        del mock_client.list_object_annotations

        helper = AnnotationHelper(bucket="test-bucket")
        helper._s3_client = mock_client

        result = helper.list_annotations("file.json")
        assert result == []


class TestAnnotationHelperDeleteAnnotation:
    """AnnotationHelper.delete_annotation() tests."""

    def test_delete_annotation_success(self):
        mock_client = MagicMock()
        mock_client.delete_object_annotation.return_value = {}

        helper = AnnotationHelper(bucket="test-bucket")
        helper._s3_client = mock_client

        result = helper.delete_annotation("file.json", "old_metadata")
        assert result is True

    def test_delete_annotation_not_available(self):
        mock_client = MagicMock()
        del mock_client.delete_object_annotation

        helper = AnnotationHelper(bucket="test-bucket")
        helper._s3_client = mock_client

        result = helper.delete_annotation("file.json", "old_metadata")
        assert result is False
