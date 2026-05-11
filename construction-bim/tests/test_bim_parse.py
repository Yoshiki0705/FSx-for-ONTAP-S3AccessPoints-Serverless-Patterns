"""Unit Tests for UC10: BIM パース・OCR・安全チェック Lambda

IFC パース、バージョン差分、Cross-Region Textract 呼び出し、安全チェックロジックをテストする。

Requirements: 13.1, 13.2
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# shared モジュールと UC10 関数のパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from functions.bim_parse.handler import (
    IfcParseError,
    parse_ifc_metadata,
    compute_version_diff,
)
from functions.safety_check.handler import (
    determine_overall_compliance,
    _keyword_based_check,
    DEFAULT_SAFETY_RULES,
)


# ---------------------------------------------------------------------------
# IFC パーステスト
# ---------------------------------------------------------------------------


class TestParseIfcMetadata:
    """IFC メタデータパースのテスト"""

    def _build_valid_ifc(self) -> str:
        """有効な IFC ファイルコンテンツを生成する"""
        return (
            "ISO-10303-21;\n"
            "HEADER;\n"
            "FILE_DESCRIPTION(('ViewDefinition [CoordinationView]'),'2;1');\n"
            "FILE_NAME('building_A.ifc','2026-01-15T10:00:00',('Author'),('Org'),'','','');\n"
            "FILE_SCHEMA(('IFC4'));\n"
            "ENDSEC;\n"
            "DATA;\n"
            "#1=IFCPROJECT('guid1',#2,$,'Building A',$,$,$,(#3),#4);\n"
            "#5=IFCSITE('guid5',#6,$,'Site',$,$,$,$,.ELEMENT.,$,$,$,$,$);\n"
            "#10=IFCBUILDING('guid10',#11,$,'Building A',$,$,$,$,.ELEMENT.,$,$,$);\n"
            "#15=IFCGEOMETRICREPRESENTATIONCONTEXT('EPSG:4326',$,3,$,$,$);\n"
            "#20=IFCBUILDINGSTOREY('guid20',#21,$,'Floor 1',$,$,$,$,.ELEMENT.,0.0);\n"
            "#21=IFCBUILDINGSTOREY('guid21',#22,$,'Floor 2',$,$,$,$,.ELEMENT.,3000.0);\n"
            "#22=IFCBUILDINGSTOREY('guid22',#23,$,'Floor 3',$,$,$,$,.ELEMENT.,6000.0);\n"
            "#30=IFCWALL('guid30',#31,$,'Wall 1',$,$,$,$,$);\n"
            "#31=IFCWALL('guid31',#32,$,'Wall 2',$,$,$,$,$);\n"
            "ENDSEC;\n"
            "END-ISO-10303-21;\n"
        )

    def test_valid_ifc4_file(self):
        """有効な IFC4 ファイルを正しくパースする"""
        content = self._build_valid_ifc()
        metadata = parse_ifc_metadata(content)

        assert metadata["project_name"] == "Building A"
        assert metadata["ifc_schema_version"] == "IFC4"
        assert metadata["floor_count"] == 3
        assert metadata["coordinate_system"] == "EPSG:4326"
        # 9 entities: IFCPROJECT, IFCSITE, IFCBUILDING, IFCGEOMETRICREPRESENTATIONCONTEXT,
        # 3x IFCBUILDINGSTOREY, 2x IFCWALL
        assert metadata["building_elements_count"] == 9

    def test_ifc2x3_schema(self):
        """IFC2X3 スキーマバージョンを正しく抽出する"""
        content = (
            "ISO-10303-21;\n"
            "HEADER;\n"
            "FILE_SCHEMA(('IFC2X3'));\n"
            "ENDSEC;\n"
            "DATA;\n"
            "#1=IFCPROJECT('guid',#2,$,'Old Project',$,$,$,(#3),#4);\n"
            "ENDSEC;\n"
            "END-ISO-10303-21;\n"
        )
        metadata = parse_ifc_metadata(content)
        assert metadata["ifc_schema_version"] == "IFC2X3"

    def test_no_storeys(self):
        """IFCBUILDINGSTOREY がない場合に floor_count=0 を返す"""
        content = (
            "ISO-10303-21;\n"
            "HEADER;\n"
            "FILE_SCHEMA(('IFC4'));\n"
            "ENDSEC;\n"
            "DATA;\n"
            "#1=IFCPROJECT('guid',#2,$,'No Floors',$,$,$,(#3),#4);\n"
            "#2=IFCSITE('guid2',#3,$,'Site',$,$,$,$,.ELEMENT.,$,$,$,$,$);\n"
            "ENDSEC;\n"
            "END-ISO-10303-21;\n"
        )
        metadata = parse_ifc_metadata(content)
        assert metadata["floor_count"] == 0
        assert metadata["building_elements_count"] == 2

    def test_invalid_file_raises_error(self):
        """無効なファイルで IfcParseError を発生させる"""
        content = "This is not an IFC file at all."
        with pytest.raises(IfcParseError):
            parse_ifc_metadata(content)

    def test_bytes_input(self):
        """バイト列入力を正しく処理する"""
        content = self._build_valid_ifc().encode("utf-8")
        metadata = parse_ifc_metadata(content)
        assert metadata["project_name"] == "Building A"

    def test_unknown_coordinate_system(self):
        """座標系情報がない場合に 'unknown' を返す"""
        content = (
            "ISO-10303-21;\n"
            "HEADER;\n"
            "FILE_SCHEMA(('IFC4'));\n"
            "ENDSEC;\n"
            "DATA;\n"
            "#1=IFCPROJECT('guid',#2,$,'Test',$,$,$,(#3),#4);\n"
            "ENDSEC;\n"
            "END-ISO-10303-21;\n"
        )
        metadata = parse_ifc_metadata(content)
        assert metadata["coordinate_system"] == "unknown"


# ---------------------------------------------------------------------------
# バージョン差分テスト
# ---------------------------------------------------------------------------


class TestComputeVersionDiff:
    """バージョン差分計算のテスト"""

    def test_first_version_all_additions(self):
        """初回バージョン（previous=None）は全て追加"""
        current = {
            "project_name": "Building A",
            "building_elements_count": 100,
            "floor_count": 5,
            "coordinate_system": "EPSG:4326",
            "ifc_schema_version": "IFC4",
        }
        diff = compute_version_diff(current, None)
        assert diff["elements_added"] == 100
        assert diff["elements_deleted"] == 0
        assert diff["elements_modified"] == 0

    def test_elements_added(self):
        """要素が追加された場合"""
        current = {"building_elements_count": 150, "project_name": "A", "floor_count": 5, "coordinate_system": "X"}
        previous = {"building_elements_count": 100, "project_name": "A", "floor_count": 5, "coordinate_system": "X"}
        diff = compute_version_diff(current, previous)
        assert diff["elements_added"] == 50
        assert diff["elements_deleted"] == 0

    def test_elements_deleted(self):
        """要素が削除された場合"""
        current = {"building_elements_count": 80, "project_name": "A", "floor_count": 5, "coordinate_system": "X"}
        previous = {"building_elements_count": 100, "project_name": "A", "floor_count": 5, "coordinate_system": "X"}
        diff = compute_version_diff(current, previous)
        assert diff["elements_added"] == 0
        assert diff["elements_deleted"] == 20

    def test_metadata_modifications(self):
        """メタデータフィールドが変更された場合"""
        current = {"building_elements_count": 100, "project_name": "B", "floor_count": 6, "coordinate_system": "Y"}
        previous = {"building_elements_count": 100, "project_name": "A", "floor_count": 5, "coordinate_system": "X"}
        diff = compute_version_diff(current, previous)
        assert diff["elements_added"] == 0
        assert diff["elements_deleted"] == 0
        assert diff["elements_modified"] == 3  # project_name, floor_count, coordinate_system

    def test_no_changes(self):
        """変更がない場合"""
        metadata = {"building_elements_count": 100, "project_name": "A", "floor_count": 5, "coordinate_system": "X"}
        diff = compute_version_diff(metadata, metadata)
        assert diff["elements_added"] == 0
        assert diff["elements_deleted"] == 0
        assert diff["elements_modified"] == 0


# ---------------------------------------------------------------------------
# 安全チェックロジックテスト
# ---------------------------------------------------------------------------


class TestSafetyCheckLogic:
    """安全コンプライアンスチェックロジックのテスト"""

    def test_all_pass(self):
        """全ルール PASS の場合に overall=PASS"""
        results = [
            {"rule_id": "R1", "rule_name": "Rule 1", "status": "PASS"},
            {"rule_id": "R2", "rule_name": "Rule 2", "status": "PASS"},
        ]
        assert determine_overall_compliance(results) == "PASS"

    def test_one_fail(self):
        """1 つでも FAIL があれば overall=FAIL"""
        results = [
            {"rule_id": "R1", "rule_name": "Rule 1", "status": "PASS"},
            {"rule_id": "R2", "rule_name": "Rule 2", "status": "FAIL"},
        ]
        assert determine_overall_compliance(results) == "FAIL"

    def test_all_fail(self):
        """全ルール FAIL の場合に overall=FAIL"""
        results = [
            {"rule_id": "R1", "rule_name": "Rule 1", "status": "FAIL"},
            {"rule_id": "R2", "rule_name": "Rule 2", "status": "FAIL"},
        ]
        assert determine_overall_compliance(results) == "FAIL"

    def test_empty_results(self):
        """空の結果リストの場合に overall=PASS"""
        assert determine_overall_compliance([]) == "PASS"

    def test_keyword_based_check_pass(self):
        """キーワードが見つかる場合に PASS"""
        text = "This building has fire escape routes and emergency exits."
        results = _keyword_based_check(text, {}, DEFAULT_SAFETY_RULES)

        fire_rule = next(r for r in results if r["rule_id"] == "FIRE_ESCAPE_001")
        assert fire_rule["status"] == "PASS"

    def test_keyword_based_check_fail(self):
        """キーワードが見つからない場合に FAIL"""
        text = "This is a simple document with no relevant content."
        results = _keyword_based_check(text, {}, DEFAULT_SAFETY_RULES)

        # 全ルールが FAIL になるはず
        for result in results:
            assert result["status"] == "FAIL"

    def test_keyword_based_check_partial(self):
        """一部のキーワードのみ見つかる場合"""
        text = "The structural load analysis shows adequate foundation support."
        results = _keyword_based_check(text, {}, DEFAULT_SAFETY_RULES)

        structural_rule = next(r for r in results if r["rule_id"] == "STRUCTURAL_LOAD_001")
        assert structural_rule["status"] == "PASS"


# ---------------------------------------------------------------------------
# OCR ハンドラテスト
# ---------------------------------------------------------------------------


class TestOcrHandler:
    """OCR Lambda ハンドラのテスト"""

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
        "CROSS_REGION": "us-east-1",
    })
    @patch("functions.ocr.handler.OutputWriter")
    @patch("functions.ocr.handler.boto3.client")
    @patch("functions.ocr.handler.CrossRegionClient")
    @patch("functions.ocr.handler.S3ApHelper")
    def test_ocr_success(self, mock_s3ap_class, mock_cr_class, mock_boto3_client, mock_output_writer_cls):
        """正常な PDF で SUCCESS を返す"""
        from functions.ocr.handler import handler

        # S3ApHelper モック
        mock_s3ap = MagicMock()
        mock_s3ap_class.return_value = mock_s3ap
        mock_body = MagicMock()
        mock_body.read.return_value = b"%PDF-1.4 test content"
        mock_s3ap.get_object.return_value = {"Body": mock_body}

        # CrossRegionClient モック
        mock_cr = MagicMock()
        mock_cr_class.return_value = mock_cr
        mock_cr.analyze_document.return_value = {
            "Blocks": [
                {"BlockType": "LINE", "Text": "Floor Plan - Level 1", "Id": "b1"},
                {"BlockType": "LINE", "Text": "Emergency Exit", "Id": "b2"},
            ]
        }

        # S3 クライアントモック
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3

        # OutputWriter モック
        mock_writer = MagicMock()
        mock_writer.target_description = "Standard S3 bucket 'test-output-bucket'"
        mock_writer.build_s3_uri.return_value = "s3://test-output-bucket/out.json"
        mock_output_writer_cls.from_env.return_value = mock_writer

        context = MagicMock()
        context.aws_request_id = "test-request-id"

        event = {"Key": "drawings/floor_plan.pdf", "Size": 5242880}
        result = handler(event, context)

        assert result["status"] == "SUCCESS"
        assert result["file_key"] == "drawings/floor_plan.pdf"
        assert "Floor Plan" in result["extracted_text"]
        assert "Emergency Exit" in result["extracted_text"]

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
        "CROSS_REGION": "us-east-1",
    })
    @patch("functions.ocr.handler.CrossRegionClient")
    @patch("functions.ocr.handler.S3ApHelper")
    def test_ocr_file_read_error(self, mock_s3ap_class, mock_cr_class):
        """ファイル読み取りエラー時に ERROR を返す"""
        from functions.ocr.handler import handler

        mock_s3ap = MagicMock()
        mock_s3ap_class.return_value = mock_s3ap
        mock_s3ap.get_object.side_effect = Exception("Access denied")

        context = MagicMock()
        context.aws_request_id = "test-request-id"

        event = {"Key": "drawings/missing.pdf", "Size": 0}
        result = handler(event, context)

        assert result["status"] == "ERROR"
        assert "Access denied" in result["error"]


# ---------------------------------------------------------------------------
# BIM パースハンドラテスト
# ---------------------------------------------------------------------------


class TestBimParseHandler:
    """BIM パース Lambda ハンドラのテスト"""

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
        "PREVIOUS_METADATA_PREFIX": "metadata/history/",
    })
    @patch("functions.bim_parse.handler.OutputWriter")
    @patch("functions.bim_parse.handler.boto3.client")
    @patch("functions.bim_parse.handler.S3ApHelper")
    def test_handler_success(self, mock_s3ap_class, mock_boto3_client, mock_output_writer_cls):
        """正常な IFC ファイルで SUCCESS を返す"""
        from functions.bim_parse.handler import handler

        ifc_content = (
            "ISO-10303-21;\n"
            "HEADER;\n"
            "FILE_SCHEMA(('IFC4'));\n"
            "ENDSEC;\n"
            "DATA;\n"
            "#1=IFCPROJECT('guid',#2,$,'Test Building',$,$,$,(#3),#4);\n"
            "#2=IFCBUILDINGSTOREY('guid2',#3,$,'Floor 1',$,$,$,$,.ELEMENT.,0.0);\n"
            "ENDSEC;\n"
            "END-ISO-10303-21;\n"
        ).encode("utf-8")

        # S3ApHelper モック
        mock_s3ap = MagicMock()
        mock_s3ap_class.return_value = mock_s3ap
        mock_body = MagicMock()
        mock_body.read.return_value = ifc_content
        mock_s3ap.get_object.return_value = {"Body": mock_body}

        # S3 クライアントモック（前バージョンなし）
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3
        mock_s3.list_objects_v2.return_value = {"Contents": []}

        # OutputWriter モック
        mock_writer = MagicMock()
        mock_writer.target_description = "Standard S3 bucket 'test-output-bucket'"
        mock_writer.build_s3_uri.return_value = "s3://test-output-bucket/out.json"
        mock_output_writer_cls.from_env.return_value = mock_writer

        context = MagicMock()
        context.aws_request_id = "test-request-id"

        event = {"Key": "models/building_A_v3.ifc", "Size": 1024}
        result = handler(event, context)

        assert result["status"] == "SUCCESS"
        assert result["file_key"] == "models/building_A_v3.ifc"
        assert result["metadata"]["project_name"] == "Test Building"
        assert result["metadata"]["ifc_schema_version"] == "IFC4"
        assert result["metadata"]["floor_count"] == 1

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
    })
    @patch("functions.bim_parse.handler.boto3.client")
    @patch("functions.bim_parse.handler.S3ApHelper")
    def test_handler_invalid_file(self, mock_s3ap_class, mock_boto3_client):
        """無効な IFC ファイルで INVALID を返す"""
        from functions.bim_parse.handler import handler

        mock_s3ap = MagicMock()
        mock_s3ap_class.return_value = mock_s3ap
        mock_body = MagicMock()
        mock_body.read.return_value = b"Not an IFC file"
        mock_s3ap.get_object.return_value = {"Body": mock_body}

        context = MagicMock()
        context.aws_request_id = "test-request-id"

        event = {"Key": "models/corrupted.ifc", "Size": 100}
        result = handler(event, context)

        assert result["status"] == "INVALID"
        assert "error" in result
