"""Unit Tests for UC9: 点群 QC Lambda

PCD ヘッダーパース、QC バリデーションロジック、ハンドラの正常系・異常系をテストする。

Requirements: 13.1, 13.2
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# shared モジュールと UC9 関数のパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from functions.point_cloud_qc.handler import (
    PcdParseError,
    parse_pcd_header,
    validate_point_cloud,
)


# ---------------------------------------------------------------------------
# PCD ヘッダーパーステスト
# ---------------------------------------------------------------------------


class TestParsePcdHeader:
    """PCD ヘッダーパースのテスト"""

    def test_valid_ascii_header(self):
        """有効な ASCII PCD ヘッダーを正しくパースする"""
        pcd_data = (
            "# .PCD v0.7\n"
            "VERSION 0.7\n"
            "FIELDS x y z intensity\n"
            "SIZE 4 4 4 4\n"
            "TYPE F F F F\n"
            "COUNT 1 1 1 1\n"
            "WIDTH 1000\n"
            "HEIGHT 1\n"
            "VIEWPOINT 0 0 0 1 0 0 0\n"
            "POINTS 1000\n"
            "DATA ascii\n"
        )
        header = parse_pcd_header(pcd_data)

        assert header["version"] == "0.7"
        assert header["fields"] == ["x", "y", "z", "intensity"]
        assert header["size"] == [4, 4, 4, 4]
        assert header["type"] == ["F", "F", "F", "F"]
        assert header["count"] == [1, 1, 1, 1]
        assert header["width"] == 1000
        assert header["height"] == 1
        assert header["points"] == 1000
        assert header["data_type"] == "ascii"

    def test_binary_header(self):
        """バイナリ PCD ヘッダーを正しくパースする"""
        pcd_data = (
            "# .PCD v0.7\n"
            "VERSION 0.7\n"
            "FIELDS x y z rgb\n"
            "SIZE 4 4 4 4\n"
            "TYPE F F F U\n"
            "COUNT 1 1 1 1\n"
            "WIDTH 5000\n"
            "HEIGHT 1\n"
            "VIEWPOINT 0 0 0 1 0 0 0\n"
            "POINTS 5000\n"
            "DATA binary\n"
        )
        header = parse_pcd_header(pcd_data)

        assert header["version"] == "0.7"
        assert header["fields"] == ["x", "y", "z", "rgb"]
        assert header["points"] == 5000
        assert header["data_type"] == "binary"

    def test_organized_point_cloud(self):
        """組織化された点群（HEIGHT > 1）を正しくパースする"""
        pcd_data = (
            "VERSION 0.7\n"
            "FIELDS x y z\n"
            "SIZE 4 4 4\n"
            "TYPE F F F\n"
            "COUNT 1 1 1\n"
            "WIDTH 640\n"
            "HEIGHT 480\n"
            "VIEWPOINT 0 0 0 1 0 0 0\n"
            "POINTS 307200\n"
            "DATA ascii\n"
        )
        header = parse_pcd_header(pcd_data)

        assert header["width"] == 640
        assert header["height"] == 480
        assert header["points"] == 307200

    def test_missing_fields_raises_error(self):
        """FIELDS が欠落している場合にエラーを発生させる"""
        pcd_data = (
            "VERSION 0.7\n"
            "SIZE 4 4 4\n"
            "TYPE F F F\n"
            "COUNT 1 1 1\n"
            "WIDTH 100\n"
            "HEIGHT 1\n"
            "POINTS 100\n"
            "DATA ascii\n"
        )
        with pytest.raises(PcdParseError):
            parse_pcd_header(pcd_data)

    def test_invalid_size_values(self):
        """SIZE に無効な値がある場合にエラーを発生させる"""
        pcd_data = (
            "VERSION 0.7\n"
            "FIELDS x y z\n"
            "SIZE abc def ghi\n"
            "TYPE F F F\n"
            "COUNT 1 1 1\n"
            "WIDTH 100\n"
            "HEIGHT 1\n"
            "POINTS 100\n"
            "DATA ascii\n"
        )
        with pytest.raises(PcdParseError):
            parse_pcd_header(pcd_data)

    def test_bytes_input(self):
        """バイト列入力を正しく処理する"""
        pcd_data = (
            "VERSION 0.7\n"
            "FIELDS x y z\n"
            "SIZE 4 4 4\n"
            "TYPE F F F\n"
            "COUNT 1 1 1\n"
            "WIDTH 500\n"
            "HEIGHT 1\n"
            "POINTS 500\n"
            "DATA ascii\n"
        ).encode("utf-8")

        header = parse_pcd_header(pcd_data)
        assert header["points"] == 500

    def test_points_from_width_height(self):
        """POINTS が 0 の場合、WIDTH * HEIGHT から計算する"""
        pcd_data = (
            "VERSION 0.7\n"
            "FIELDS x y z\n"
            "SIZE 4 4 4\n"
            "TYPE F F F\n"
            "COUNT 1 1 1\n"
            "WIDTH 100\n"
            "HEIGHT 10\n"
            "POINTS 0\n"
            "DATA ascii\n"
        )
        header = parse_pcd_header(pcd_data)
        assert header["points"] == 1000  # 100 * 10


# ---------------------------------------------------------------------------
# QC バリデーションテスト
# ---------------------------------------------------------------------------


class TestValidatePointCloud:
    """点群 QC バリデーションのテスト"""

    def _make_header(self, points: int = 100) -> dict:
        """テスト用ヘッダーを生成する"""
        return {
            "version": "0.7",
            "fields": ["x", "y", "z", "intensity"],
            "size": [4, 4, 4, 4],
            "type": ["F", "F", "F", "F"],
            "count": [1, 1, 1, 1],
            "width": points,
            "height": 1,
            "viewpoint": "0 0 0 1 0 0 0",
            "points": points,
            "data_type": "ascii",
            "header_end_offset": 0,
        }

    def test_valid_point_cloud_passes(self):
        """有効な点群データが PASS を返す"""
        header = self._make_header(5)
        data_lines = [
            "1.0 2.0 3.0 0.5",
            "4.0 5.0 6.0 0.6",
            "7.0 8.0 9.0 0.7",
            "10.0 11.0 12.0 0.8",
            "13.0 14.0 15.0 0.9",
        ]

        result = validate_point_cloud(header, data_lines)
        assert result["status"] == "PASS"
        assert result["point_count"] == 5
        assert result["nan_coordinates"] == 0
        assert result["header_point_count_match"] is True
        assert result["point_density"] > 0

    def test_nan_coordinates_fail(self):
        """NaN 座標がある場合に FAIL を返す"""
        header = self._make_header(3)
        data_lines = [
            "1.0 2.0 3.0 0.5",
            "nan nan nan 0.6",
            "7.0 8.0 9.0 0.7",
        ]

        result = validate_point_cloud(header, data_lines)
        assert result["status"] == "FAIL"
        assert result["nan_coordinates"] == 1
        assert "NaN" in result["failure_reasons"][0]

    def test_point_count_mismatch_fail(self):
        """ポイント数がヘッダーと不一致の場合に FAIL を返す"""
        header = self._make_header(10)  # ヘッダーは 10 ポイント
        data_lines = [
            "1.0 2.0 3.0 0.5",
            "4.0 5.0 6.0 0.6",
            "7.0 8.0 9.0 0.7",
        ]  # 実際は 3 ポイント

        result = validate_point_cloud(header, data_lines)
        assert result["status"] == "FAIL"
        assert result["header_point_count_match"] is False
        assert result["point_count"] == 3

    def test_coordinate_bounds_calculation(self):
        """座標範囲が正しく計算される"""
        header = self._make_header(3)
        data_lines = [
            "-10.0 -20.0 -5.0 0.5",
            "0.0 0.0 0.0 0.6",
            "10.0 20.0 5.0 0.7",
        ]

        result = validate_point_cloud(header, data_lines)
        bounds = result["coordinate_bounds"]
        assert bounds["x"]["min"] == -10.0
        assert bounds["x"]["max"] == 10.0
        assert bounds["y"]["min"] == -20.0
        assert bounds["y"]["max"] == 20.0
        assert bounds["z"]["min"] == -5.0
        assert bounds["z"]["max"] == 5.0

    def test_empty_data_lines(self):
        """空のデータ行の場合に FAIL を返す"""
        header = self._make_header(100)
        data_lines = []

        result = validate_point_cloud(header, data_lines)
        assert result["status"] == "FAIL"
        assert result["point_count"] == 0
        assert result["header_point_count_match"] is False

    def test_invalid_numeric_values(self):
        """数値変換に失敗する行は NaN としてカウントされる"""
        header = self._make_header(3)
        data_lines = [
            "1.0 2.0 3.0 0.5",
            "abc def ghi 0.6",
            "7.0 8.0 9.0 0.7",
        ]

        result = validate_point_cloud(header, data_lines)
        assert result["nan_coordinates"] == 1


# ---------------------------------------------------------------------------
# ハンドラテスト
# ---------------------------------------------------------------------------


class TestHandler:
    """ハンドラの正常系・異常系テスト"""

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
    })
    @patch("functions.point_cloud_qc.handler.boto3.client")
    @patch("functions.point_cloud_qc.handler.S3ApHelper")
    def test_handler_success(self, mock_s3ap_class, mock_boto3_client):
        """正常な PCD ファイルで SUCCESS を返す"""
        from functions.point_cloud_qc.handler import handler

        # PCD データ
        pcd_content = (
            "# .PCD v0.7\n"
            "VERSION 0.7\n"
            "FIELDS x y z intensity\n"
            "SIZE 4 4 4 4\n"
            "TYPE F F F F\n"
            "COUNT 1 1 1 1\n"
            "WIDTH 3\n"
            "HEIGHT 1\n"
            "VIEWPOINT 0 0 0 1 0 0 0\n"
            "POINTS 3\n"
            "DATA ascii\n"
            "1.0 2.0 3.0 0.5\n"
            "4.0 5.0 6.0 0.6\n"
            "7.0 8.0 9.0 0.7\n"
        ).encode("utf-8")

        # S3ApHelper モック
        mock_s3ap = MagicMock()
        mock_s3ap_class.return_value = mock_s3ap
        mock_body = MagicMock()
        mock_body.read.return_value = pcd_content
        mock_s3ap.get_object.return_value = {"Body": mock_body}

        # S3 クライアントモック
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3

        # コンテキストモック
        context = MagicMock()
        context.aws_request_id = "test-request-id"

        event = {"Key": "lidar/scan_001.pcd", "Size": 1024}
        result = handler(event, context)

        assert result["status"] == "PASS"
        assert result["file_key"] == "lidar/scan_001.pcd"
        assert result["metrics"]["point_count"] == 3
        assert result["metrics"]["nan_coordinates"] == 0

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
    })
    @patch("functions.point_cloud_qc.handler.boto3.client")
    @patch("functions.point_cloud_qc.handler.S3ApHelper")
    def test_handler_file_read_error(self, mock_s3ap_class, mock_boto3_client):
        """ファイル読み取りエラー時に FAIL を返す"""
        from functions.point_cloud_qc.handler import handler

        mock_s3ap = MagicMock()
        mock_s3ap_class.return_value = mock_s3ap
        mock_s3ap.get_object.side_effect = Exception("Access denied")

        context = MagicMock()
        context.aws_request_id = "test-request-id"

        event = {"Key": "lidar/missing.pcd", "Size": 0}
        result = handler(event, context)

        assert result["status"] == "FAIL"
        assert "Access denied" in result["error"]

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
    })
    @patch("functions.point_cloud_qc.handler.boto3.client")
    @patch("functions.point_cloud_qc.handler.S3ApHelper")
    def test_handler_invalid_pcd(self, mock_s3ap_class, mock_boto3_client):
        """無効な PCD ファイルで FAIL を返す"""
        from functions.point_cloud_qc.handler import handler

        # 無効な PCD データ（FIELDS なし）
        invalid_content = b"This is not a PCD file\nJust random text\n"

        mock_s3ap = MagicMock()
        mock_s3ap_class.return_value = mock_s3ap
        mock_body = MagicMock()
        mock_body.read.return_value = invalid_content
        mock_s3ap.get_object.return_value = {"Body": mock_body}

        context = MagicMock()
        context.aws_request_id = "test-request-id"

        event = {"Key": "lidar/corrupted.pcd", "Size": 100}
        result = handler(event, context)

        assert result["status"] == "FAIL"
        assert "error" in result
