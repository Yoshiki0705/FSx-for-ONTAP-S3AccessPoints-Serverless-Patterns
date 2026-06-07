"""UC19 Processing Lambdas — Unit Tests

Visual Analyzer および Text Compliance Lambda のテスト:
- Rekognition (DetectLabels, DetectModerationLabels, DetectText) モック
- Textract (DetectDocumentText) モック
- Bedrock (InvokeModel) モック
- ラベル抽出、モデレーション検出、テキスト検出、タグ生成
- コンプライアンスルールチェック
- テキスト抽出、ブランド検証、ルールベースフォールバック

Requirements: 13.4
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# shared モジュールのパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Visual Analyzer handler
_va_path = os.path.join(os.path.dirname(__file__), "..", "functions", "visual_analyzer", "handler.py")
_va_spec = importlib.util.spec_from_file_location("visual_analyzer_handler", _va_path)
_va_module = importlib.util.module_from_spec(_va_spec)
_va_spec.loader.exec_module(_va_module)

detect_labels = _va_module.detect_labels
detect_moderation_labels = _va_module.detect_moderation_labels
detect_text = _va_module.detect_text
generate_tags = _va_module.generate_tags
check_compliance = _va_module.check_compliance
get_confidence_threshold = _va_module.get_confidence_threshold
get_max_tags = _va_module.get_max_tags

# Text Compliance handler
_tc_path = os.path.join(os.path.dirname(__file__), "..", "functions", "text_compliance", "handler.py")
_tc_spec = importlib.util.spec_from_file_location("text_compliance_handler", _tc_path)
_tc_module = importlib.util.module_from_spec(_tc_spec)
_tc_spec.loader.exec_module(_tc_module)

extract_text_with_textract = _tc_module.extract_text_with_textract
validate_brand_terminology_with_bedrock = _tc_module.validate_brand_terminology_with_bedrock
_rule_based_brand_check = _tc_module._rule_based_brand_check
check_compliance_rules = _tc_module.check_compliance_rules


# ============================================================
# Visual Analyzer: detect_labels() テスト
# ============================================================


class TestDetectLabels:
    """Rekognition DetectLabels のテスト"""

    def test_labels_extracted(self):
        """ラベルが正しく抽出される"""
        mock_client = MagicMock()
        mock_client.detect_labels.return_value = {
            "Labels": [
                {
                    "Name": "Car",
                    "Confidence": 95.5,
                    "Categories": [{"Name": "Vehicle"}],
                },
                {
                    "Name": "Road",
                    "Confidence": 88.2,
                    "Categories": [{"Name": "Outdoor"}],
                },
            ]
        }

        result = detect_labels(mock_client, b"fake_image", 80.0, 50)

        assert len(result) == 2
        assert result[0]["name"] == "Car"
        assert result[0]["confidence"] == 95.5
        assert result[0]["categories"] == ["Vehicle"]
        assert result[1]["name"] == "Road"

    def test_labels_limited_to_max_tags(self):
        """max_tags に制限される"""
        mock_client = MagicMock()
        mock_client.detect_labels.return_value = {
            "Labels": [{"Name": f"Label{i}", "Confidence": 90.0, "Categories": []} for i in range(10)]
        }

        result = detect_labels(mock_client, b"fake_image", 80.0, 5)
        assert len(result) == 5

    def test_empty_labels(self):
        """ラベルが検出されない場合は空リスト"""
        mock_client = MagicMock()
        mock_client.detect_labels.return_value = {"Labels": []}

        result = detect_labels(mock_client, b"fake_image", 80.0, 50)
        assert result == []


# ============================================================
# Visual Analyzer: detect_moderation_labels() テスト
# ============================================================


class TestDetectModerationLabels:
    """Rekognition DetectModerationLabels のテスト"""

    def test_moderation_labels_extracted(self):
        """モデレーションラベルが正しく抽出される"""
        mock_client = MagicMock()
        mock_client.detect_moderation_labels.return_value = {
            "ModerationLabels": [
                {
                    "Name": "Explicit Nudity",
                    "Confidence": 92.3,
                    "ParentName": "Nudity",
                },
            ]
        }

        result = detect_moderation_labels(mock_client, b"fake_image", 80.0)

        assert len(result) == 1
        assert result[0]["name"] == "Explicit Nudity"
        assert result[0]["confidence"] == 92.3
        assert result[0]["parent_name"] == "Nudity"

    def test_no_moderation_labels(self):
        """モデレーションラベルがない場合は空リスト"""
        mock_client = MagicMock()
        mock_client.detect_moderation_labels.return_value = {"ModerationLabels": []}

        result = detect_moderation_labels(mock_client, b"fake_image", 80.0)
        assert result == []


# ============================================================
# Visual Analyzer: detect_text() テスト
# ============================================================


class TestDetectText:
    """Rekognition DetectText のテスト"""

    def test_text_detections(self):
        """テキストが正しく検出される"""
        mock_client = MagicMock()
        mock_client.detect_text.return_value = {
            "TextDetections": [
                {"DetectedText": "SALE", "Confidence": 99.1, "Type": "LINE"},
                {"DetectedText": "50% OFF", "Confidence": 95.0, "Type": "LINE"},
                {"DetectedText": "SALE", "Confidence": 99.1, "Type": "WORD"},
            ]
        }

        result = detect_text(mock_client, b"fake_image")

        assert len(result) == 3
        assert result[0]["text"] == "SALE"
        assert result[0]["type"] == "LINE"
        assert result[1]["text"] == "50% OFF"

    def test_no_text_detections(self):
        """テキストが検出されない場合は空リスト"""
        mock_client = MagicMock()
        mock_client.detect_text.return_value = {"TextDetections": []}

        result = detect_text(mock_client, b"fake_image")
        assert result == []


# ============================================================
# Visual Analyzer: generate_tags() テスト
# ============================================================


class TestGenerateTags:
    """タグ生成のテスト"""

    def test_tags_from_labels(self):
        """ラベルからタグが生成される"""
        labels = [
            {"name": "Car", "confidence": 95.0, "categories": []},
            {"name": "Road", "confidence": 88.0, "categories": []},
            {"name": "Sky", "confidence": 85.0, "categories": []},
        ]
        tags = generate_tags(labels, 50)
        assert tags == ["Car", "Road", "Sky"]

    def test_tags_max_limit(self):
        """タグ数が max_tags に制限される"""
        labels = [{"name": f"Label{i}", "confidence": 90.0, "categories": []} for i in range(100)]
        tags = generate_tags(labels, 50)
        assert len(tags) == 50

    def test_tags_deduplication(self):
        """重複するラベル名は除外される"""
        labels = [
            {"name": "Car", "confidence": 95.0, "categories": []},
            {"name": "Car", "confidence": 90.0, "categories": []},
            {"name": "Road", "confidence": 88.0, "categories": []},
        ]
        tags = generate_tags(labels, 50)
        assert tags == ["Car", "Road"]

    def test_empty_labels(self):
        """空ラベルリストからは空タグリスト"""
        tags = generate_tags([], 50)
        assert tags == []

    def test_whitespace_names_ignored(self):
        """空白のみの名前は除外される"""
        labels = [
            {"name": "  ", "confidence": 95.0, "categories": []},
            {"name": "Car", "confidence": 90.0, "categories": []},
        ]
        tags = generate_tags(labels, 50)
        assert tags == ["Car"]


# ============================================================
# Visual Analyzer: check_compliance() テスト
# ============================================================


class TestCheckCompliance:
    """コンプライアンスルールチェックのテスト"""

    def test_compliant_asset(self):
        """全ルール通過時は compliant"""
        result = check_compliance(
            moderation_labels=[],
            text_detections=[{"text": "広告 ©2026", "confidence": 99.0, "type": "LINE"}],
            file_size=1_000_000,
            compliance_rules={
                "prohibited_moderation_categories": ["Violence"],
                "required_disclaimer_keywords": ["広告"],
                "size_constraints": {"max_bytes": 5_000_000_000},
            },
        )
        assert result["status"] == "compliant"
        assert result["violations"] == []

    def test_prohibited_moderation_category_violation(self):
        """禁止モデレーションカテゴリ検出で non-compliant"""
        result = check_compliance(
            moderation_labels=[
                {"name": "Violence", "confidence": 95.0, "parent_name": ""},
            ],
            text_detections=[],
            file_size=1_000_000,
            compliance_rules={
                "prohibited_moderation_categories": ["Violence"],
            },
        )
        assert result["status"] == "non-compliant"
        assert any(v["type"] == "prohibited_moderation_category" for v in result["violations"])

    def test_missing_disclaimer_keyword(self):
        """必須免責事項キーワード不足で non-compliant"""
        result = check_compliance(
            moderation_labels=[],
            text_detections=[{"text": "SALE 50%OFF", "confidence": 99.0, "type": "LINE"}],
            file_size=1_000_000,
            compliance_rules={
                "required_disclaimer_keywords": ["©", "広告"],
            },
        )
        assert result["status"] == "non-compliant"
        assert any(v["type"] == "missing_disclaimer_keyword" for v in result["violations"])

    def test_file_size_exceeded(self):
        """ファイルサイズ超過で non-compliant"""
        result = check_compliance(
            moderation_labels=[],
            text_detections=[],
            file_size=10_000_000_000,
            compliance_rules={
                "size_constraints": {"max_bytes": 5_000_000_000},
            },
        )
        assert result["status"] == "non-compliant"
        assert any(v["type"] == "file_size_exceeded" for v in result["violations"])

    def test_empty_rules(self):
        """ルールが空の場合は compliant"""
        result = check_compliance(
            moderation_labels=[{"name": "Violence", "confidence": 95.0, "parent_name": ""}],
            text_detections=[],
            file_size=1_000_000,
            compliance_rules={},
        )
        assert result["status"] == "compliant"


# ============================================================
# Visual Analyzer: get_confidence_threshold / get_max_tags テスト
# ============================================================


class TestEnvironmentConfig:
    """環境変数設定のテスト"""

    @patch.dict(os.environ, {"MODERATION_CONFIDENCE_THRESHOLD": "90"})
    def test_confidence_threshold_from_env(self):
        assert get_confidence_threshold() == 90.0

    @patch.dict(os.environ, {"MODERATION_CONFIDENCE_THRESHOLD": "invalid"})
    def test_confidence_threshold_invalid_fallback(self):
        assert get_confidence_threshold() == 80.0

    @patch.dict(os.environ, {"MAX_TAGS_PER_ASSET": "30"})
    def test_max_tags_from_env(self):
        assert get_max_tags() == 30

    @patch.dict(os.environ, {"MAX_TAGS_PER_ASSET": "invalid"})
    def test_max_tags_invalid_fallback(self):
        assert get_max_tags() == 50


# ============================================================
# Text Compliance: extract_text_with_textract() テスト
# ============================================================


class TestExtractTextWithTextract:
    """Textract DetectDocumentText のテスト"""

    def test_text_blocks_extracted(self):
        """テキストブロックが正しく抽出される"""
        mock_client = MagicMock()
        mock_client.detect_document_text.return_value = {
            "Blocks": [
                {"BlockType": "LINE", "Text": "Summer Sale", "Confidence": 99.5},
                {"BlockType": "WORD", "Text": "Summer", "Confidence": 99.2},
                {"BlockType": "WORD", "Text": "Sale", "Confidence": 99.8},
                {"BlockType": "PAGE", "Text": "", "Confidence": 100.0},
            ]
        }

        result = extract_text_with_textract(mock_client, b"fake_image")

        assert len(result) == 3  # LINE + 2 WORDs (PAGE excluded)
        assert result[0]["text"] == "Summer Sale"
        assert result[0]["block_type"] == "LINE"
        assert result[0]["confidence"] == 99.5

    def test_empty_document(self):
        """テキストがない場合は空リスト"""
        mock_client = MagicMock()
        mock_client.detect_document_text.return_value = {"Blocks": []}

        result = extract_text_with_textract(mock_client, b"fake_image")
        assert result == []


# ============================================================
# Text Compliance: _rule_based_brand_check() テスト
# ============================================================


class TestRuleBasedBrandCheck:
    """ルールベースブランドチェック（Bedrock フォールバック）のテスト"""

    def test_compliant_text(self):
        """ガイドライン準拠テキストは compliant"""
        result = _rule_based_brand_check(
            extracted_text="ExampleBrand™ 公式",
            brand_guidelines={
                "required_terms": ["ExampleBrand™", "公式"],
                "prohibited_terms": ["安い", "最安値"],
            },
        )
        assert result["compliance_result"] == "compliant"
        assert result["violations"] == []
        assert "ExampleBrand™" in result["matched_terms"]

    def test_prohibited_term_found(self):
        """禁止用語検出で non-compliant"""
        result = _rule_based_brand_check(
            extracted_text="最安値のExampleBrand™ 公式",
            brand_guidelines={
                "required_terms": ["ExampleBrand™"],
                "prohibited_terms": ["最安値"],
            },
        )
        assert result["compliance_result"] == "non-compliant"
        assert any(v["type"] == "prohibited_term_found" for v in result["violations"])

    def test_missing_required_term(self):
        """必須用語不足で non-compliant"""
        result = _rule_based_brand_check(
            extracted_text="Sale now on",
            brand_guidelines={
                "required_terms": ["ExampleBrand™", "公式"],
                "prohibited_terms": [],
            },
        )
        assert result["compliance_result"] == "non-compliant"
        missing = [v for v in result["violations"] if v["type"] == "required_term_missing"]
        assert len(missing) == 2

    def test_empty_guidelines(self):
        """空ガイドラインの場合は compliant"""
        result = _rule_based_brand_check(
            extracted_text="anything",
            brand_guidelines={},
        )
        assert result["compliance_result"] == "compliant"


# ============================================================
# Text Compliance: validate_brand_terminology_with_bedrock() テスト
# ============================================================


class TestValidateBrandTerminologyWithBedrock:
    """Bedrock ブランド検証のテスト"""

    def test_bedrock_compliant_response(self):
        """Bedrock がコンプライアント判定を返す場合"""
        mock_client = MagicMock()
        bedrock_response = {
            "compliance_result": "compliant",
            "matched_prohibited_terms": [],
            "matched_required_terms": ["ExampleBrand™"],
            "missing_required_terms": [],
            "reasoning": "All terms correctly used",
        }
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps(
            {
                "content": [{"type": "text", "text": json.dumps(bedrock_response)}],
            }
        ).encode()
        mock_client.invoke_model.return_value = {"body": mock_body}

        result = validate_brand_terminology_with_bedrock(
            bedrock_client=mock_client,
            extracted_text="ExampleBrand™ 公式",
            brand_guidelines={"required_terms": ["ExampleBrand™"]},
            model_id="anthropic.claude-haiku-4-5-20251001-v1:0",
        )

        assert result["compliance_result"] == "compliant"

    def test_bedrock_non_compliant_response(self):
        """Bedrock がノンコンプライアント判定を返す場合"""
        mock_client = MagicMock()
        bedrock_response = {
            "compliance_result": "non-compliant",
            "matched_prohibited_terms": ["最安値"],
            "matched_required_terms": [],
            "missing_required_terms": ["公式"],
            "reasoning": "Prohibited term found",
        }
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps(
            {
                "content": [{"type": "text", "text": json.dumps(bedrock_response)}],
            }
        ).encode()
        mock_client.invoke_model.return_value = {"body": mock_body}

        result = validate_brand_terminology_with_bedrock(
            bedrock_client=mock_client,
            extracted_text="最安値セール",
            brand_guidelines={"prohibited_terms": ["最安値"], "required_terms": ["公式"]},
            model_id="anthropic.claude-haiku-4-5-20251001-v1:0",
        )

        assert result["compliance_result"] == "non-compliant"
        assert any(v["type"] == "prohibited_term_found" for v in result["violations"])

    def test_empty_text_returns_compliant(self):
        """抽出テキストが空の場合は compliant"""
        mock_client = MagicMock()

        result = validate_brand_terminology_with_bedrock(
            bedrock_client=mock_client,
            extracted_text="   ",
            brand_guidelines={"required_terms": ["Brand"]},
            model_id="anthropic.claude-haiku-4-5-20251001-v1:0",
        )

        assert result["compliance_result"] == "compliant"
        mock_client.invoke_model.assert_not_called()

    def test_no_guidelines_returns_compliant(self):
        """ガイドラインが空の場合は compliant"""
        mock_client = MagicMock()

        result = validate_brand_terminology_with_bedrock(
            bedrock_client=mock_client,
            extracted_text="Some text",
            brand_guidelines={},
            model_id="anthropic.claude-haiku-4-5-20251001-v1:0",
        )

        assert result["compliance_result"] == "compliant"
        mock_client.invoke_model.assert_not_called()


# ============================================================
# Text Compliance: check_compliance_rules() テスト
# ============================================================


class TestCheckComplianceRules:
    """コンプライアンスルール追加チェックのテスト"""

    def test_disclaimer_keyword_check_pass(self):
        """免責事項キーワードが存在する場合はバイオレーションなし"""
        text_blocks = [
            {"text": "広告 PR ©2026 ExampleBrand", "confidence": 99.0, "block_type": "LINE"},
        ]
        result = check_compliance_rules(
            text_blocks=text_blocks,
            file_size=1_000_000,
            compliance_rules={"required_disclaimer_keywords": ["広告", "©"]},
        )
        assert result["violations"] == []

    def test_disclaimer_keyword_check_fail(self):
        """免責事項キーワードが不足する場合はバイオレーション"""
        text_blocks = [
            {"text": "Sale 50% OFF", "confidence": 99.0, "block_type": "LINE"},
        ]
        result = check_compliance_rules(
            text_blocks=text_blocks,
            file_size=1_000_000,
            compliance_rules={"required_disclaimer_keywords": ["広告", "©"]},
        )
        assert len(result["violations"]) == 2

    def test_size_constraint_pass(self):
        """サイズ制約内はバイオレーションなし"""
        result = check_compliance_rules(
            text_blocks=[],
            file_size=1_000_000,
            compliance_rules={"size_constraints": {"max_bytes": 5_000_000_000}},
        )
        assert result["violations"] == []

    def test_size_constraint_fail(self):
        """サイズ超過でバイオレーション"""
        result = check_compliance_rules(
            text_blocks=[],
            file_size=10_000_000_000,
            compliance_rules={"size_constraints": {"max_bytes": 5_000_000_000}},
        )
        assert any(v["type"] == "file_size_exceeded" for v in result["violations"])
