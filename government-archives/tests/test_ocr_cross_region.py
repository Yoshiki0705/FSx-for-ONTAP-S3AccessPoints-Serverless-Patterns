"""Cross-region Textract integration tests for UC16 OCR."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_invoke_textract_cross_region_success(ocr_handler):
    """Cross-region Textract が成功した場合は (text, blocks, 'cross_region') を返す。"""
    mock_client = MagicMock()
    mock_client.analyze_document.return_value = {
        "Blocks": [
            {"BlockType": "LINE", "Text": "Hello from us-east-1"},
            {"BlockType": "LINE", "Text": "Cross-region works"},
        ]
    }

    with patch.object(
        ocr_handler, "CrossRegionClient", return_value=mock_client
    ):
        text, blocks, mode = ocr_handler._invoke_textract(
            document_bytes=b"pdf bytes",
            use_cross_region=True,
            cross_region_target="us-east-1",
        )

    assert mode == "cross_region"
    assert "Hello from us-east-1" in text
    assert len(blocks) == 2


def test_invoke_textract_cross_region_fallback_to_same_region(ocr_handler):
    """Cross-region が失敗したら同一リージョンにフォールバックする。"""
    from shared.exceptions import CrossRegionClientError

    cross_region_mock = MagicMock()
    cross_region_mock.analyze_document.side_effect = CrossRegionClientError(
        "Cross-region failed",
        target_region="us-east-1",
        service_name="textract",
    )

    same_region_textract = MagicMock()
    same_region_textract.analyze_document.return_value = {
        "Blocks": [{"BlockType": "LINE", "Text": "Same region fallback"}]
    }

    with patch.object(
        ocr_handler, "CrossRegionClient", return_value=cross_region_mock
    ), patch.object(ocr_handler, "boto3") as mock_boto3:
        mock_boto3.client.return_value = same_region_textract
        text, blocks, mode = ocr_handler._invoke_textract(
            document_bytes=b"pdf bytes",
            use_cross_region=True,
            cross_region_target="us-east-1",
        )

    assert mode == "same_region"
    assert "Same region fallback" in text


def test_invoke_textract_both_unavailable(ocr_handler):
    """Cross-region も same-region も失敗したら 'unavailable' を返す。"""
    from shared.exceptions import CrossRegionClientError

    cross_region_mock = MagicMock()
    cross_region_mock.analyze_document.side_effect = CrossRegionClientError(
        "Failed", target_region="us-east-1", service_name="textract"
    )

    with patch.object(
        ocr_handler, "CrossRegionClient", return_value=cross_region_mock
    ), patch.object(ocr_handler, "boto3") as mock_boto3:
        mock_boto3.client.side_effect = Exception("EndpointConnectionError")
        text, blocks, mode = ocr_handler._invoke_textract(
            document_bytes=b"pdf bytes",
            use_cross_region=True,
            cross_region_target="us-east-1",
        )

    assert mode == "unavailable"
    assert text == ""
    assert blocks == []


def test_invoke_textract_use_cross_region_false(ocr_handler):
    """USE_CROSS_REGION=false の場合は同一リージョンを直接使う。"""
    same_region_textract = MagicMock()
    same_region_textract.analyze_document.return_value = {
        "Blocks": [{"BlockType": "LINE", "Text": "Direct same-region"}]
    }

    with patch.object(ocr_handler, "boto3") as mock_boto3:
        mock_boto3.client.return_value = same_region_textract
        text, blocks, mode = ocr_handler._invoke_textract(
            document_bytes=b"pdf bytes",
            use_cross_region=False,
            cross_region_target="us-east-1",
        )

    assert mode == "same_region"
    assert "Direct same-region" in text


def test_handler_reports_invoke_mode(
    ocr_handler, lambda_context, monkeypatch
):
    """Handler output に invoke_mode が含まれる。"""
    monkeypatch.setenv("OUTPUT_BUCKET", "test-bucket")
    monkeypatch.setenv("USE_CROSS_REGION", "false")  # simpler test path

    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {
        "Body": MagicMock(read=lambda: b"%PDF-1.4" + b"\x00" * 500)
    }
    mock_textract = MagicMock()
    mock_textract.analyze_document.return_value = {
        "Blocks": [{"BlockType": "LINE", "Text": "test"}]
    }

    def boto3_client(service):
        if service == "s3":
            return mock_s3
        if service == "textract":
            return mock_textract
        return MagicMock()

    mock_writer = MagicMock()

    with patch.object(ocr_handler, "boto3") as mock_boto3, patch.object(
        ocr_handler, "OutputWriter"
    ) as mock_output_writer_cls:
        mock_boto3.client.side_effect = boto3_client
        mock_output_writer_cls.from_env.return_value = mock_writer
        event = {"Key": "archives/doc.pdf", "Size": 500}
        result = ocr_handler.handler(event, lambda_context)

    assert "invoke_mode" in result
    assert result["invoke_mode"] == "same_region"
