"""Unit Tests for UC8: 坑井ログ異常検知 Lambda

LAS/CSV ファイルパース、異常検知ロジック、ハンドラの正常系・異常系をテストする。

Requirements: 13.1, 13.2
"""

from __future__ import annotations

import json
import math
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# shared モジュールと UC8 関数のパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from functions.anomaly_detection.handler import (
    _detect_anomalies,
    _parse_csv_file,
    _parse_las_file,
)


# ---------------------------------------------------------------------------
# _parse_las_file tests
# ---------------------------------------------------------------------------


class TestParseLasFile:
    """LAS ファイルパースのテスト"""

    def test_valid_las_file(self):
        """有効な LAS ファイルを正しくパースする"""
        content = """~VERSION INFORMATION
VERS.                 2.0 : CWLS LOG ASCII STANDARD
~WELL INFORMATION
WELL.                 WELL-A1 : Well Name
~CURVE INFORMATION
DEPT .M                : Depth
GR   .GAPI             : Gamma Ray
NPHI .V/V              : Neutron Porosity
~A
1000.0 50.0 0.25
1000.5 55.0 0.28
1001.0 48.0 0.22
"""
        curve_names, data_rows = _parse_las_file(content)

        assert curve_names == ["DEPT", "GR", "NPHI"]
        assert len(data_rows) == 3
        assert data_rows[0] == [1000.0, 50.0, 0.25]
        assert data_rows[1] == [1000.5, 55.0, 0.28]
        assert data_rows[2] == [1001.0, 48.0, 0.22]

    def test_las_file_with_comments(self):
        """コメント行を含む LAS ファイルを正しくパースする"""
        content = """# This is a comment
~C
DEPT .M : Depth
GR   .GAPI : Gamma Ray
~A
# Data starts here
100.0 45.0
200.0 50.0
"""
        curve_names, data_rows = _parse_las_file(content)

        assert curve_names == ["DEPT", "GR"]
        assert len(data_rows) == 2

    def test_las_file_no_curves(self):
        """カーブ定義がない LAS ファイルは ValueError を raise する"""
        content = """~V
VERS. 2.0
~A
100.0 45.0
"""
        with pytest.raises(ValueError, match="No curve definitions found"):
            _parse_las_file(content)

    def test_las_file_no_data(self):
        """データがない LAS ファイルは ValueError を raise する"""
        content = """~C
DEPT .M : Depth
GR   .GAPI : Gamma Ray
"""
        with pytest.raises(ValueError, match="No data found"):
            _parse_las_file(content)

    def test_las_file_invalid_values(self):
        """不正な数値は NaN として処理する"""
        content = """~C
DEPT .M : Depth
GR   .GAPI : Gamma Ray
~A
100.0 INVALID
200.0 50.0
"""
        curve_names, data_rows = _parse_las_file(content)

        assert len(data_rows) == 2
        assert math.isnan(data_rows[0][1])
        assert data_rows[1][1] == 50.0


# ---------------------------------------------------------------------------
# _parse_csv_file tests
# ---------------------------------------------------------------------------


class TestParseCsvFile:
    """CSV ファイルパースのテスト"""

    def test_valid_csv_file(self):
        """有効な CSV ファイルを正しくパースする"""
        content = """DEPT,GR,NPHI,RHOB
1000.0,50.0,0.25,2.65
1000.5,55.0,0.28,2.60
1001.0,48.0,0.22,2.70
"""
        column_names, data_rows = _parse_csv_file(content)

        assert column_names == ["DEPT", "GR", "NPHI", "RHOB"]
        assert len(data_rows) == 3
        assert data_rows[0] == [1000.0, 50.0, 0.25, 2.65]

    def test_csv_file_empty(self):
        """空の CSV ファイルは ValueError を raise する"""
        content = ""
        with pytest.raises(ValueError):
            _parse_csv_file(content)

    def test_csv_file_header_only(self):
        """ヘッダーのみの CSV ファイルは ValueError を raise する"""
        content = "DEPT,GR,NPHI\n"
        with pytest.raises(ValueError, match="No data rows found"):
            _parse_csv_file(content)

    def test_csv_file_with_spaces(self):
        """スペースを含む CSV ファイルを正しくパースする"""
        content = """DEPT, GR, NPHI
1000.0, 50.0, 0.25
1000.5, 55.0, 0.28
"""
        column_names, data_rows = _parse_csv_file(content)

        assert column_names == ["DEPT", "GR", "NPHI"]
        assert len(data_rows) == 2
        assert data_rows[0] == [1000.0, 50.0, 0.25]


# ---------------------------------------------------------------------------
# _detect_anomalies tests
# ---------------------------------------------------------------------------


class TestDetectAnomalies:
    """異常検知ロジックのテスト"""

    def test_no_anomalies(self):
        """全値が閾値内の場合は異常なし"""
        curve_names = ["DEPT", "GR"]
        # All values are very close to the mean
        data_rows = [
            [100.0, 50.0],
            [100.5, 50.1],
            [101.0, 49.9],
            [101.5, 50.0],
            [102.0, 50.2],
        ]
        anomalies = _detect_anomalies(curve_names, data_rows, threshold_std=3.0)
        assert anomalies == []

    def test_clear_anomaly(self):
        """明確な異常値を検出する"""
        curve_names = ["DEPT", "GR"]
        # Normal values around 50, with one extreme outlier at 500
        # With 20 data points, the outlier won't inflate std as much
        data_rows = [
            [100.0, 50.0],
            [100.5, 51.0],
            [101.0, 49.0],
            [101.5, 50.5],
            [102.0, 500.0],  # Clear anomaly - very extreme
            [102.5, 50.0],
            [103.0, 49.5],
            [103.5, 51.0],
            [104.0, 50.0],
            [104.5, 50.5],
            [105.0, 50.0],
            [105.5, 51.0],
            [106.0, 49.0],
            [106.5, 50.5],
            [107.0, 50.0],
            [107.5, 49.5],
            [108.0, 51.0],
            [108.5, 50.0],
            [109.0, 50.5],
            [109.5, 50.0],
        ]
        anomalies = _detect_anomalies(curve_names, data_rows, threshold_std=3.0)

        assert len(anomalies) >= 1
        # The anomaly at depth 102.0 with value 500.0 should be detected
        anomaly_depths = [a["depth"] for a in anomalies]
        assert 102.0 in anomaly_depths

    def test_multiple_sensors(self):
        """複数センサーカラムの異常を検出する"""
        curve_names = ["DEPT", "GR", "NPHI"]
        data_rows = [
            [100.0, 50.0, 0.25],
            [100.5, 51.0, 0.26],
            [101.0, 49.0, 0.24],
            [101.5, 50.5, 0.25],
            [102.0, 500.0, 5.00],  # Both sensors anomalous - very extreme
            [102.5, 50.0, 0.25],
            [103.0, 49.5, 0.24],
            [103.5, 51.0, 0.26],
            [104.0, 50.0, 0.25],
            [104.5, 50.5, 0.25],
            [105.0, 50.0, 0.25],
            [105.5, 51.0, 0.26],
            [106.0, 49.0, 0.24],
            [106.5, 50.5, 0.25],
            [107.0, 50.0, 0.25],
            [107.5, 49.5, 0.24],
            [108.0, 51.0, 0.26],
            [108.5, 50.0, 0.25],
            [109.0, 50.5, 0.25],
            [109.5, 50.0, 0.25],
        ]
        anomalies = _detect_anomalies(curve_names, data_rows, threshold_std=3.0)

        # Should detect anomalies in both GR and NPHI
        sensors = {a["sensor"] for a in anomalies}
        assert "GR" in sensors
        assert "NPHI" in sensors

    def test_empty_data(self):
        """空データの場合は異常なし"""
        anomalies = _detect_anomalies([], [], threshold_std=3.0)
        assert anomalies == []

    def test_single_row(self):
        """1 行のみの場合は異常なし（標準偏差計算不可）"""
        curve_names = ["DEPT", "GR"]
        data_rows = [[100.0, 50.0]]
        anomalies = _detect_anomalies(curve_names, data_rows, threshold_std=3.0)
        assert anomalies == []

    def test_all_same_values(self):
        """全値が同じ場合は異常なし（標準偏差 = 0）"""
        curve_names = ["DEPT", "GR"]
        data_rows = [[float(i), 50.0] for i in range(10)]
        anomalies = _detect_anomalies(curve_names, data_rows, threshold_std=3.0)
        assert anomalies == []

    def test_threshold_sensitivity(self):
        """閾値を下げると検出数が増える"""
        curve_names = ["DEPT", "GR"]
        data_rows = [
            [100.0, 50.0],
            [100.5, 55.0],
            [101.0, 45.0],
            [101.5, 60.0],
            [102.0, 40.0],
            [102.5, 70.0],  # Moderate outlier
            [103.0, 50.0],
            [103.5, 50.0],
            [104.0, 50.0],
            [104.5, 50.0],
        ]

        anomalies_strict = _detect_anomalies(curve_names, data_rows, threshold_std=3.0)
        anomalies_loose = _detect_anomalies(curve_names, data_rows, threshold_std=1.0)

        # Lower threshold should detect more or equal anomalies
        assert len(anomalies_loose) >= len(anomalies_strict)

    def test_anomaly_fields(self):
        """異常レコードに必要なフィールドが含まれる"""
        curve_names = ["DEPT", "GR"]
        data_rows = [
            [100.0, 50.0],
            [100.5, 51.0],
            [101.0, 49.0],
            [101.5, 50.5],
            [102.0, 500.0],  # Anomaly - very extreme
            [102.5, 50.0],
            [103.0, 49.5],
            [103.5, 51.0],
            [104.0, 50.0],
            [104.5, 50.5],
            [105.0, 50.0],
            [105.5, 51.0],
            [106.0, 49.0],
            [106.5, 50.5],
            [107.0, 50.0],
            [107.5, 49.5],
            [108.0, 51.0],
            [108.5, 50.0],
            [109.0, 50.5],
            [109.5, 50.0],
        ]
        anomalies = _detect_anomalies(curve_names, data_rows, threshold_std=3.0)

        assert len(anomalies) >= 1
        for anomaly in anomalies:
            assert "depth" in anomaly
            assert "sensor" in anomaly
            assert "value" in anomaly
            assert "threshold" in anomaly
            assert "std_deviations" in anomaly

    def test_nan_values_excluded(self):
        """NaN 値は統計計算から除外される"""
        curve_names = ["DEPT", "GR"]
        data_rows = [
            [100.0, 50.0],
            [100.5, float("nan")],
            [101.0, 49.0],
            [101.5, 50.5],
            [102.0, 51.0],
            [102.5, 50.0],
            [103.0, 49.5],
            [103.5, 51.0],
            [104.0, 50.0],
            [104.5, 50.5],
        ]
        # Should not crash and NaN should not be flagged as anomaly
        anomalies = _detect_anomalies(curve_names, data_rows, threshold_std=3.0)
        for anomaly in anomalies:
            assert not math.isnan(anomaly["value"])


# ---------------------------------------------------------------------------
# handler tests (mocked AWS calls)
# ---------------------------------------------------------------------------


class TestHandler:
    """ハンドラの正常系・異常系テスト"""

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
        "ANOMALY_THRESHOLD_STD": "3.0",
    })
    @patch("functions.anomaly_detection.handler.boto3")
    @patch("functions.anomaly_detection.handler.S3ApHelper")
    def test_handler_las_success(self, mock_s3ap_class, mock_boto3):
        """正常系: LAS ファイルの異常検知が成功する"""
        from functions.anomaly_detection.handler import handler

        las_content = """~C
DEPT .M : Depth
GR   .GAPI : Gamma Ray
~A
1000.0 50.0
1000.5 51.0
1001.0 49.0
1001.5 50.5
1002.0 500.0
1002.5 50.0
1003.0 49.5
1003.5 51.0
1004.0 50.0
1004.5 50.5
1005.0 50.0
1005.5 51.0
1006.0 49.0
1006.5 50.5
1007.0 50.0
1007.5 49.5
1008.0 51.0
1008.5 50.0
1009.0 50.5
1009.5 50.0
"""
        mock_s3ap = MagicMock()
        mock_response = MagicMock()
        mock_response.__getitem__ = lambda self, key: MagicMock(
            read=MagicMock(return_value=las_content.encode("utf-8"))
        ) if key == "Body" else None
        mock_s3ap.get_object.return_value = {"Body": MagicMock(read=MagicMock(return_value=las_content.encode("utf-8")))}
        mock_s3ap_class.return_value = mock_s3ap

        mock_s3_client = MagicMock()
        mock_boto3.client.return_value = mock_s3_client

        event = {"Key": "wells/well_A1.las", "Size": 5242880}
        context = MagicMock()
        context.aws_request_id = "test-request-id"

        result = handler(event, context)

        assert result["status"] == "SUCCESS"
        assert result["file_key"] == "wells/well_A1.las"
        assert result["total_anomalies"] >= 1
        assert "output_key" in result

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
        "ANOMALY_THRESHOLD_STD": "3.0",
    })
    @patch("functions.anomaly_detection.handler.boto3")
    @patch("functions.anomaly_detection.handler.S3ApHelper")
    def test_handler_csv_success(self, mock_s3ap_class, mock_boto3):
        """正常系: CSV ファイルの異常検知が成功する"""
        from functions.anomaly_detection.handler import handler

        csv_content = """DEPT,GR,NPHI
1000.0,50.0,0.25
1000.5,51.0,0.26
1001.0,49.0,0.24
1001.5,50.5,0.25
1002.0,500.0,5.00
1002.5,50.0,0.25
1003.0,49.5,0.24
1003.5,51.0,0.26
1004.0,50.0,0.25
1004.5,50.5,0.25
1005.0,50.0,0.25
1005.5,51.0,0.26
1006.0,49.0,0.24
1006.5,50.5,0.25
1007.0,50.0,0.25
1007.5,49.5,0.24
1008.0,51.0,0.26
1008.5,50.0,0.25
1009.0,50.5,0.25
1009.5,50.0,0.25
"""
        mock_s3ap = MagicMock()
        mock_s3ap.get_object.return_value = {"Body": MagicMock(read=MagicMock(return_value=csv_content.encode("utf-8")))}
        mock_s3ap_class.return_value = mock_s3ap

        mock_s3_client = MagicMock()
        mock_boto3.client.return_value = mock_s3_client

        event = {"Key": "wells/well_B2.csv", "Size": 1048576}
        context = MagicMock()
        context.aws_request_id = "test-request-id"

        result = handler(event, context)

        assert result["status"] == "SUCCESS"
        assert result["file_key"] == "wells/well_B2.csv"
        assert result["total_anomalies"] >= 1

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
        "ANOMALY_THRESHOLD_STD": "3.0",
    })
    @patch("functions.anomaly_detection.handler.S3ApHelper")
    def test_handler_unsupported_format(self, mock_s3ap_class):
        """異常系: 非対応ファイル形式は INVALID を返す"""
        from functions.anomaly_detection.handler import handler

        mock_s3ap = MagicMock()
        mock_s3ap.get_object.return_value = {"Body": MagicMock(read=MagicMock(return_value=b"some data"))}
        mock_s3ap_class.return_value = mock_s3ap

        event = {"Key": "wells/data.xyz", "Size": 1000}
        context = MagicMock()
        context.aws_request_id = "test-request-id"

        result = handler(event, context)

        assert result["status"] == "INVALID"
        assert result["error_type"] == "UnsupportedFormat"

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
        "ANOMALY_THRESHOLD_STD": "3.0",
    })
    @patch("functions.anomaly_detection.handler.S3ApHelper")
    def test_handler_download_error(self, mock_s3ap_class):
        """異常系: ダウンロードエラー時は INVALID を返す"""
        from functions.anomaly_detection.handler import handler

        mock_s3ap = MagicMock()
        mock_s3ap.get_object.side_effect = Exception("Connection timeout")
        mock_s3ap_class.return_value = mock_s3ap

        event = {"Key": "wells/error.las", "Size": 5000}
        context = MagicMock()
        context.aws_request_id = "test-request-id"

        result = handler(event, context)

        assert result["status"] == "INVALID"
        assert result["error_type"] == "DownloadError"
