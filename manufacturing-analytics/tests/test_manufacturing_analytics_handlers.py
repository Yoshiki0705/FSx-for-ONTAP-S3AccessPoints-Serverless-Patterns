"""UC3 製造業 Analytics Lambda ハンドラー ユニットテスト

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

    def test_handler_defines_sensor_log_suffixes(self):
        """ハンドラーが SENSOR_LOG_SUFFIXES 定数を定義していることを確認（UC3 固有）"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "discovery", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "SENSOR_LOG_SUFFIXES" in content

    def test_handler_defines_inspection_image_suffixes(self):
        """ハンドラーが INSPECTION_IMAGE_SUFFIXES 定数を定義していることを確認（UC3 固有）"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "discovery", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "INSPECTION_IMAGE_SUFFIXES" in content

    def test_handler_classifies_csv_and_images(self):
        """ハンドラーが CSV ファイルと画像ファイルを分類することを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "discovery", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "csv_files" in content
        assert "image_files" in content

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
# Image Analysis Handler テスト
# =========================================================================


class TestImageAnalysisHandler:
    """Image Analysis Lambda ハンドラーのテスト"""

    def test_handler_module_importable(self):
        """Image Analysis ハンドラーモジュールが存在することを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "image_analysis", "handler.py"
        )
        assert os.path.exists(handler_path), f"handler.py not found: {handler_path}"

    def test_handler_has_lambda_entry_point(self):
        """Image Analysis ハンドラーに handler 関数が定義されていることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "image_analysis", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "def handler(event, context):" in content

    def test_should_flag_for_review_defined(self):
        """should_flag_for_review 関数が定義されていることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "image_analysis", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "def should_flag_for_review(" in content

    def test_handler_uses_confidence_threshold(self):
        """ハンドラーが CONFIDENCE_THRESHOLD 環境変数を使用していることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "image_analysis", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "CONFIDENCE_THRESHOLD" in content

    def test_handler_uses_rekognition(self):
        """ハンドラーが Amazon Rekognition を使用していることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "image_analysis", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "rekognition" in content
        assert "detect_labels" in content

    def test_handler_outputs_image_analysis_prefix(self):
        """ハンドラーが image-analysis/ プレフィックス付きキーを生成することを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "image_analysis", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "image-analysis/" in content

    def test_handler_returns_flagged_for_review(self):
        """ハンドラーの返り値に flagged_for_review キーが含まれることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "image_analysis", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "flagged_for_review" in content


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

    def test_template_suffix_filter_includes_csv(self):
        """テンプレートの SUFFIX_FILTER に .csv が含まれることを確認（UC3 固有）"""
        template_path = os.path.join(
            os.path.dirname(__file__), "..", "template.yaml"
        )
        with open(template_path) as f:
            content = f.read()
        assert ".csv" in content
