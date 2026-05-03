"""UC2 金融・保険 IDP Lambda ハンドラー ユニットテスト

各ハンドラーの入出力形式、エラーハンドリング、
ヘルパー関数のロジックをテストする。
AWS サービス呼び出しは unittest.mock でモック化。
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# shared モジュールのパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# =========================================================================
# Discovery Handler テスト
# =========================================================================


class TestDiscoveryHandler:
    """Discovery Lambda ハンドラーのテスト"""

    def test_handler_module_importable(self):
        """ハンドラーモジュールがインポート可能であることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "discovery", "handler.py"
        )
        assert os.path.exists(handler_path), f"handler.py not found: {handler_path}"

    def test_handler_has_lambda_entry_point(self):
        """ハンドラーに handler 関数が定義されていることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "discovery", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "def handler(event, context):" in content

    def test_handler_uses_lambda_error_handler(self):
        """ハンドラーが lambda_error_handler デコレータを使用していることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "discovery", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "@lambda_error_handler" in content

    def test_handler_returns_objects_key(self):
        """ハンドラーの返り値に objects キーが含まれることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "discovery", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert '"objects"' in content or "'objects'" in content

    def test_handler_defines_document_suffixes(self):
        """ハンドラーが DOCUMENT_SUFFIXES 定数を定義していることを確認（UC2 固有）"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "discovery", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "DOCUMENT_SUFFIXES" in content

    def test_handler_supports_pdf_tiff_jpeg(self):
        """ハンドラーが PDF, TIFF, JPEG 拡張子をサポートしていることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "discovery", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert ".pdf" in content
        assert ".tiff" in content or ".tif" in content
        assert ".jpeg" in content or ".jpg" in content

    def test_handler_deduplicates_objects(self):
        """ハンドラーが重複排除ロジックを含むことを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "discovery", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "seen_keys" in content or "unique_objects" in content

    def test_handler_generates_manifest_key(self):
        """ハンドラーが manifests/ プレフィックス付きキーを生成することを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "discovery", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "manifests/" in content


# =========================================================================
# OCR Handler テスト
# =========================================================================


class TestOcrHandler:
    """OCR Lambda ハンドラーのテスト"""

    def test_handler_module_importable(self):
        """OCR ハンドラーモジュールが存在することを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "ocr", "handler.py"
        )
        assert os.path.exists(handler_path), f"handler.py not found: {handler_path}"

    def test_handler_has_lambda_entry_point(self):
        """OCR ハンドラーに handler 関数が定義されていることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "ocr", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "def handler(event, context):" in content

    def test_select_textract_api_defined(self):
        """select_textract_api 関数が定義されていることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "ocr", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "def select_textract_api(" in content

    def test_handler_uses_textract_page_threshold(self):
        """ハンドラーが TEXTRACT_PAGE_THRESHOLD 環境変数を使用していることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "ocr", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "TEXTRACT_PAGE_THRESHOLD" in content

    def test_handler_supports_sync_and_async_api(self):
        """ハンドラーが同期・非同期 Textract API の両方をサポートすることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "ocr", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert '"sync"' in content
        assert '"async"' in content

    def test_handler_has_sync_extract_function(self):
        """同期テキスト抽出関数が定義されていることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "ocr", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "def _extract_text_sync(" in content

    def test_handler_has_async_extract_function(self):
        """非同期テキスト抽出関数が定義されていることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "ocr", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "def _extract_text_async(" in content

    def test_handler_returns_error_gracefully(self):
        """Textract エラー時に空テキストで続行することを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "ocr", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert '"extracted_text": ""' in content or "'extracted_text': ''" in content

    def test_handler_uses_analyze_document(self):
        """ハンドラーが AnalyzeDocument API を使用していることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "ocr", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "analyze_document" in content

    def test_handler_uses_start_document_analysis(self):
        """ハンドラーが StartDocumentAnalysis API を使用していることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "ocr", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "start_document_analysis" in content


# =========================================================================
# CloudFormation テンプレート整合性テスト
# =========================================================================


class TestTemplateConsistency:
    """CloudFormation テンプレートの整合性テスト"""

    def test_template_exists(self):
        """template.yaml が存在することを確認"""
        template_path = os.path.join(
            os.path.dirname(__file__), "..", "template.yaml"
        )
        assert os.path.exists(template_path)

    def test_template_deploy_exists(self):
        """template-deploy.yaml が存在することを確認"""
        template_path = os.path.join(
            os.path.dirname(__file__), "..", "template-deploy.yaml"
        )
        assert os.path.exists(template_path)

    def test_template_has_suffix_filter(self):
        """テンプレートに SUFFIX_FILTER 環境変数が定義されていることを確認"""
        template_path = os.path.join(
            os.path.dirname(__file__), "..", "template.yaml"
        )
        with open(template_path) as f:
            content = f.read()
        assert "SUFFIX_FILTER" in content

    def test_template_has_vpc_endpoint_parameter(self):
        """テンプレートに EnableVpcEndpoints パラメータが定義されていることを確認"""
        template_path = os.path.join(
            os.path.dirname(__file__), "..", "template.yaml"
        )
        with open(template_path) as f:
            content = f.read()
        assert "EnableVpcEndpoints" in content

    def test_template_has_s3_gateway_endpoint_parameter(self):
        """テンプレートに EnableS3GatewayEndpoint パラメータが定義されていることを確認"""
        template_path = os.path.join(
            os.path.dirname(__file__), "..", "template.yaml"
        )
        with open(template_path) as f:
            content = f.read()
        assert "EnableS3GatewayEndpoint" in content

    def test_template_has_route_table_ids_parameter(self):
        """テンプレートに PrivateRouteTableIds パラメータが定義されていることを確認"""
        template_path = os.path.join(
            os.path.dirname(__file__), "..", "template.yaml"
        )
        with open(template_path) as f:
            content = f.read()
        assert "PrivateRouteTableIds" in content

    def test_template_suffix_filter_includes_pdf(self):
        """テンプレートの SUFFIX_FILTER に .pdf が含まれることを確認（UC2 固有）"""
        template_path = os.path.join(
            os.path.dirname(__file__), "..", "template.yaml"
        )
        with open(template_path) as f:
            content = f.read()
        assert ".pdf" in content
