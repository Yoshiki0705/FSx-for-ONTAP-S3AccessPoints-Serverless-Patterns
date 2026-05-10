"""Resilience tests for UC15 — verifying production fixes from AWS deployment."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_rekognition_invalid_format_returns_empty(object_detection_handler):
    """InvalidImageFormatException は空リストで継続し、例外を上げない。"""
    mock_rek = MagicMock()

    class _InvalidImageFormatException(Exception):
        pass

    class _ImageTooLargeException(Exception):
        pass

    mock_rek.exceptions.InvalidImageFormatException = _InvalidImageFormatException
    mock_rek.exceptions.ImageTooLargeException = _ImageTooLargeException
    mock_rek.detect_labels.side_effect = _InvalidImageFormatException(
        "Request has invalid image format"
    )

    with patch.object(object_detection_handler, "boto3") as mock_boto3:
        mock_boto3.client.return_value = mock_rek
        result = object_detection_handler._detect_with_rekognition(
            b"malformed bytes", min_confidence=70.0, max_labels=100
        )

    assert result == []


def test_rekognition_image_too_large_returns_empty(object_detection_handler):
    """ImageTooLargeException もフォールバック。"""
    mock_rek = MagicMock()

    class _InvalidImageFormatException(Exception):
        pass

    class _ImageTooLargeException(Exception):
        pass

    mock_rek.exceptions.InvalidImageFormatException = _InvalidImageFormatException
    mock_rek.exceptions.ImageTooLargeException = _ImageTooLargeException
    mock_rek.detect_labels.side_effect = _ImageTooLargeException("Image is too large")

    with patch.object(object_detection_handler, "boto3") as mock_boto3:
        mock_boto3.client.return_value = mock_rek
        result = object_detection_handler._detect_with_rekognition(
            b"large image bytes", min_confidence=70.0, max_labels=100
        )

    assert result == []


def test_change_detection_float_to_decimal_conversion(change_detection_handler):
    """DynamoDB への保存時に float を Decimal に再帰変換する。"""
    from decimal import Decimal

    # 内部ヘルパーがハンドラ内で定義されているため、handler 実行経由で検証
    # （float の直接送信が PutItem で失敗しないことを確認）
    mock_table = MagicMock()
    mock_table.query.return_value = {"Items": []}
    mock_resource = MagicMock()
    mock_resource.Table.return_value = mock_table

    import os

    os.environ["CHANGE_HISTORY_TABLE"] = "test-table"
    os.environ["OUTPUT_BUCKET"] = "test-bucket"
    os.environ["CHANGE_AREA_THRESHOLD_KM2"] = "0.5"

    with patch.object(change_detection_handler, "boto3") as mock_boto3:
        mock_boto3.resource.return_value = mock_resource
        event = {
            "tile_key": "tiles/test.tif",
            "detections": [
                {
                    "label": "Vehicle",
                    "confidence": 95.5,  # float
                    "bbox": {"Width": 0.1, "Height": 0.15},  # floats
                }
            ],
            "image_metadata": {"bounds": [139.0, 35.0, 140.0, 36.0]},
        }
        # Dummy context
        ctx = MagicMock()
        ctx.aws_request_id = "test-id"
        change_detection_handler.handler(event, ctx)

    # put_item が呼ばれたときの引数を検査
    mock_table.put_item.assert_called_once()
    args, kwargs = mock_table.put_item.call_args
    item = kwargs.get("Item") or args[0]

    # detected_objects は再帰的に Decimal に変換されているはず
    detected = item["detected_objects"]
    assert len(detected) == 1
    assert isinstance(detected[0]["confidence"], Decimal)
    assert isinstance(detected[0]["bbox"]["Width"], Decimal)

    # diff_area_km2 も Decimal
    assert isinstance(
        item["change_from_previous"]["diff_area_km2"], Decimal
    )
