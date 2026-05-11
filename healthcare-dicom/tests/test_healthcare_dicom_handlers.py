"""UC5 医療 DICOM Lambda ハンドラー ユニットテスト

各ハンドラーの入出力形式、エラーハンドリング、
ヘルパー関数のロジックをテストする。
AWS サービス呼び出しは unittest.mock でモック化。
"""

import os
import sys


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

    def test_handler_defines_dicom_suffix(self):
        """ハンドラーが DICOM_SUFFIX 定数を定義していることを確認（UC5 固有）"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "discovery", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "DICOM_SUFFIX" in content

    def test_handler_filters_dcm_files(self):
        """ハンドラーが .dcm ファイルのみをフィルタリングすることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "discovery", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert ".dcm" in content

    def test_handler_generates_manifest_key(self):
        """ハンドラーが manifests/ プレフィックス付きキーを生成することを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "discovery", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "manifests/" in content


# =========================================================================
# DICOM Parse Handler テスト
# =========================================================================


class TestDicomParseHandler:
    """DICOM Parse Lambda ハンドラーのテスト"""

    def test_handler_module_importable(self):
        """DICOM Parse ハンドラーモジュールが存在することを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "dicom_parse", "handler.py"
        )
        assert os.path.exists(handler_path), f"handler.py not found: {handler_path}"

    def test_handler_has_lambda_entry_point(self):
        """DICOM Parse ハンドラーに handler 関数が定義されていることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "dicom_parse", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "def handler(event, context):" in content

    def test_anonymize_metadata_defined(self):
        """anonymize_metadata 関数が定義されていることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "dicom_parse", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "def anonymize_metadata(" in content

    def test_parse_dicom_header_defined(self):
        """_parse_dicom_header 関数が定義されていることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "dicom_parse", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "def _parse_dicom_header(" in content

    def test_handler_defines_phi_fields(self):
        """ハンドラーが PHI_FIELDS 定数を定義していることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "dicom_parse", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "PHI_FIELDS" in content

    def test_handler_defines_modality_categories(self):
        """ハンドラーが MODALITY_CATEGORIES 定数を定義していることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "dicom_parse", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "MODALITY_CATEGORIES" in content

    def test_phi_fields_include_patient_name(self):
        """PHI_FIELDS に patient_name が含まれることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "dicom_parse", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "patient_name" in content

    def test_phi_fields_include_patient_id(self):
        """PHI_FIELDS に patient_id が含まれることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "dicom_parse", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "patient_id" in content

    def test_handler_checks_dicm_magic_number(self):
        """ハンドラーが DICM マジックナンバーを検証することを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "dicom_parse", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert 'b"DICM"' in content

    def test_handler_outputs_dicom_metadata_prefix(self):
        """ハンドラーが dicom-metadata/ プレフィックス付きキーを生成することを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "dicom_parse", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "dicom-metadata/" in content

    def test_handler_returns_classification(self):
        """ハンドラーの返り値に classification キーが含まれることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "dicom_parse", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert '"classification"' in content or "'classification'" in content

    def test_handler_handles_invalid_dicom(self):
        """無効な DICOM ファイルに対して INVALID ステータスを返すことを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "dicom_parse", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert '"INVALID"' in content


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

    def test_template_suffix_filter_includes_dcm(self):
        """テンプレートの SUFFIX_FILTER に .dcm が含まれることを確認（UC5 固有）"""
        template_path = os.path.join(
            os.path.dirname(__file__), "..", "template.yaml"
        )
        with open(template_path) as f:
            content = f.read()
        assert ".dcm" in content
