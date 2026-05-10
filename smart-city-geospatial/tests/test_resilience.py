"""Resilience tests for UC17 — verifying production fixes from AWS deployment."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_rekognition_invalid_format_returns_empty(
    land_use_classification_handler, lambda_context, monkeypatch
):
    """InvalidImageFormatException でもワークフロー停止せず空の分布を返す。"""
    monkeypatch.setenv("OUTPUT_BUCKET", "test-bucket")
    monkeypatch.setenv("INFERENCE_TYPE", "none")

    class _InvalidImageFormatException(Exception):
        pass

    class _ImageTooLargeException(Exception):
        pass

    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {
        "Body": MagicMock(read=lambda: b"II*\x00" + b"\x00" * 100)
    }

    mock_rek = MagicMock()
    mock_rek.exceptions.InvalidImageFormatException = _InvalidImageFormatException
    mock_rek.exceptions.ImageTooLargeException = _ImageTooLargeException
    mock_rek.detect_labels.side_effect = _InvalidImageFormatException("invalid")

    def boto3_client(service):
        if service == "s3":
            return mock_s3
        if service == "rekognition":
            return mock_rek
        return MagicMock()

    mock_writer = MagicMock()

    with patch.object(land_use_classification_handler, "boto3") as mock_boto3, patch.object(
        land_use_classification_handler, "OutputWriter"
    ) as mock_output_writer_cls:
        mock_boto3.client.side_effect = boto3_client
        mock_output_writer_cls.from_env.return_value = mock_writer
        event = {"source_key": "gis/malformed.tif"}
        result = land_use_classification_handler.handler(event, lambda_context)

    assert result["inference_path"] == "rekognition"
    # empty distribution, no crash
    assert result["landuse_distribution"] == {}


def test_change_detection_float_to_decimal(
    change_detection_handler, lambda_context, monkeypatch
):
    """DynamoDB 保存時に float が Decimal 変換されていること。"""
    from decimal import Decimal

    monkeypatch.setenv("LANDUSE_HISTORY_TABLE", "test-table")
    monkeypatch.setenv("CHANGE_THRESHOLD", "0.15")

    mock_table = MagicMock()
    mock_table.query.return_value = {"Items": []}
    mock_resource = MagicMock()
    mock_resource.Table.return_value = mock_table

    with patch.object(change_detection_handler, "boto3") as mock_boto3:
        mock_boto3.resource.return_value = mock_resource
        event = {
            "source_key": "gis/area.tif",
            "landuse_distribution": {"residential": 0.5, "forest": 0.3},
        }
        change_detection_handler.handler(event, lambda_context)

    mock_table.put_item.assert_called_once()
    args, kwargs = mock_table.put_item.call_args
    item = kwargs.get("Item") or args[0]

    # All float values must be Decimal
    for v in item["landuse_distribution"].values():
        assert isinstance(v, Decimal)
    assert isinstance(item["change_magnitude"], Decimal)
