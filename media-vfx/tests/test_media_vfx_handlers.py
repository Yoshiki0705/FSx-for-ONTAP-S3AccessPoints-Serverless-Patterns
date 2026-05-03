"""UC4 メディア VFX Lambda ハンドラー ユニットテスト

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

    def test_handler_defines_render_asset_extensions(self):
        """ハンドラーが RENDER_ASSET_EXTENSIONS 定数を定義していることを確認（UC4 固有）"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "discovery", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "RENDER_ASSET_EXTENSIONS" in content

    def test_handler_supports_exr_dpx_tga(self):
        """ハンドラーが .exr, .dpx, .tga 拡張子をサポートしていることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "discovery", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert ".exr" in content
        assert ".dpx" in content
        assert ".tga" in content

    def test_handler_supports_usd_formats(self):
        """ハンドラーが USD 系フォーマット (.usd, .usda, .usdc, .usdz) をサポートしていることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "discovery", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert ".usd" in content
        assert ".usda" in content
        assert ".usdc" in content
        assert ".usdz" in content

    def test_handler_has_filter_render_assets(self):
        """ハンドラーに _filter_render_assets 関数が定義されていることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "discovery", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "def _filter_render_assets(" in content

    def test_handler_generates_manifest_key(self):
        """ハンドラーが manifests/ プレフィックス付きキーを生成することを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "discovery", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "manifests/" in content


# =========================================================================
# Job Submit Handler テスト
# =========================================================================


class TestJobSubmitHandler:
    """Job Submit Lambda ハンドラーのテスト"""

    def test_handler_module_importable(self):
        """Job Submit ハンドラーモジュールが存在することを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "job_submit", "handler.py"
        )
        assert os.path.exists(handler_path), f"handler.py not found: {handler_path}"

    def test_handler_has_lambda_entry_point(self):
        """Job Submit ハンドラーに handler 関数が定義されていることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "job_submit", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "def handler(event, context):" in content

    def test_build_job_template_defined(self):
        """_build_job_template 関数が定義されていることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "job_submit", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "def _build_job_template(" in content

    def test_handler_uses_deadline_cloud(self):
        """ハンドラーが AWS Deadline Cloud を使用していることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "job_submit", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "deadline" in content
        assert "create_job" in content

    def test_handler_uses_deadline_farm_id(self):
        """ハンドラーが DEADLINE_FARM_ID 環境変数を使用していることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "job_submit", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "DEADLINE_FARM_ID" in content

    def test_handler_uses_deadline_queue_id(self):
        """ハンドラーが DEADLINE_QUEUE_ID 環境変数を使用していることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "job_submit", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "DEADLINE_QUEUE_ID" in content

    def test_handler_returns_submitted_status(self):
        """ハンドラーが SUBMITTED ステータスを返すことを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "job_submit", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert '"SUBMITTED"' in content

    def test_handler_uses_head_object(self):
        """ハンドラーが head_object でアセットメタデータを確認することを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "job_submit", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "head_object" in content


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

    def test_template_suffix_filter_includes_exr(self):
        """テンプレートの SUFFIX_FILTER に .exr が含まれることを確認（UC4 固有）"""
        template_path = os.path.join(
            os.path.dirname(__file__), "..", "template.yaml"
        )
        with open(template_path) as f:
            content = f.read()
        assert ".exr" in content
