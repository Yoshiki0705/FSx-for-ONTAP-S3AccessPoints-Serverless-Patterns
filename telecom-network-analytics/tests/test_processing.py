"""UC18 通信業界 Processing Lambda ユニットテスト

CDR Analyzer, Log Analyzer, Anomaly Detector のパース処理・
統計計算・異常検出ロジックをテストする。
AWS サービス呼び出し (S3, Athena, Bedrock) は unittest.mock でモック化。
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

# CDR Analyzer handler
_cdr_path = os.path.join(os.path.dirname(__file__), "..", "functions", "cdr_analyzer", "handler.py")
_cdr_spec = importlib.util.spec_from_file_location("cdr_handler", _cdr_path)
_cdr_module = importlib.util.module_from_spec(_cdr_spec)
_cdr_spec.loader.exec_module(_cdr_module)

parse_csv_cdr = _cdr_module.parse_csv_cdr
parse_asn1_cdr = _cdr_module.parse_asn1_cdr
parse_cdr_file = _cdr_module.parse_cdr_file
compute_traffic_statistics = _cdr_module.compute_traffic_statistics
record_parse_error = _cdr_module.record_parse_error

# Log Analyzer handler
_log_path = os.path.join(os.path.dirname(__file__), "..", "functions", "log_analyzer", "handler.py")
_log_spec = importlib.util.spec_from_file_location("log_handler", _log_path)
_log_module = importlib.util.module_from_spec(_log_spec)
_log_spec.loader.exec_module(_log_module)

parse_syslog_rfc5424 = _log_module.parse_syslog_rfc5424
parse_snmp_trap = _log_module.parse_snmp_trap
identify_equipment_failures = _log_module.identify_equipment_failures
detect_capacity_breaches = _log_module.detect_capacity_breaches

# Anomaly Detector handler
_anomaly_path = os.path.join(os.path.dirname(__file__), "..", "functions", "anomaly_detector", "handler.py")
_anomaly_spec = importlib.util.spec_from_file_location("anomaly_handler", _anomaly_path)
_anomaly_module = importlib.util.module_from_spec(_anomaly_spec)
_anomaly_spec.loader.exec_module(_anomaly_module)

calculate_baseline_statistics = _anomaly_module.calculate_baseline_statistics
detect_anomalies = _anomaly_module.detect_anomalies
invoke_bedrock_anomaly_classification = _anomaly_module.invoke_bedrock_anomaly_classification


# =========================================================================
# CDR Analyzer — CSV パースのテスト
# =========================================================================


class TestParseCsvCdr:
    """CSV CDR パースのテスト"""

    def test_standard_csv_parses_correctly(self):
        """標準的な CSV CDR が正しくパースされる"""
        csv_content = (
            "caller_id,callee_id,duration,timestamp,cell_tower_id\n"
            "+81901234567,+81801234567,120,2026-06-02 10:00:00,TOWER-001\n"
            "+81901234568,+81801234568,60,2026-06-02 10:05:00,TOWER-002\n"
        )
        records = parse_csv_cdr(csv_content)
        assert len(records) == 2
        assert records[0]["caller_id"] == "+81901234567"
        assert records[0]["callee_id"] == "+81801234567"
        assert records[0]["duration"] == 120.0
        assert records[0]["timestamp"] == "2026-06-02 10:00:00"
        assert records[0]["cell_tower_id"] == "TOWER-001"

    def test_alternative_header_names(self):
        """代替ヘッダー名 (calling_number 等) が認識される"""
        csv_content = (
            "calling_number,called_number,call_duration,start_time,tower_id\n"
            "09012345678,08012345678,90,2026-06-02 11:00:00,T-100\n"
        )
        records = parse_csv_cdr(csv_content)
        assert len(records) == 1
        assert records[0]["caller_id"] == "09012345678"
        assert records[0]["callee_id"] == "08012345678"
        assert records[0]["duration"] == 90.0

    def test_empty_csv_raises_error(self):
        """ヘッダーのない CSV で ValueError が発生する"""
        with pytest.raises(ValueError, match="no header row"):
            parse_csv_cdr("")

    def test_invalid_duration_defaults_to_zero(self):
        """不正な duration 値は 0.0 にデフォルトする"""
        csv_content = (
            "caller_id,callee_id,duration,timestamp\n"
            "+81900000000,+81800000000,invalid,2026-06-02 12:00:00\n"
        )
        records = parse_csv_cdr(csv_content)
        assert len(records) == 1
        assert records[0]["duration"] == 0.0

    def test_row_with_only_timestamp_is_valid(self):
        """timestamp のみのレコードも有効として扱われる"""
        csv_content = (
            "caller_id,timestamp\n"
            ",2026-06-02 12:00:00\n"
        )
        records = parse_csv_cdr(csv_content)
        assert len(records) == 1


# =========================================================================
# CDR Analyzer — ASN.1 パースのテスト
# =========================================================================


class TestParseAsn1Cdr:
    """ASN.1 デコード済み CDR パースのテスト"""

    def test_json_lines_format(self):
        """JSON Lines 形式の ASN.1 CDR が正しくパースされる"""
        content = (
            '{"callingPartyNumber": "09011111111", "calledPartyNumber": "08022222222", '
            '"callDuration": "180", "answerTime": "2026-06-02T10:00:00Z", "cellId": "CELL-A"}\n'
            '{"callingPartyNumber": "09033333333", "calledPartyNumber": "08044444444", '
            '"callDuration": "45", "answerTime": "2026-06-02T10:01:00Z", "cellId": "CELL-B"}\n'
        )
        records = parse_asn1_cdr(content.encode("utf-8"))
        assert len(records) == 2
        assert records[0]["caller_id"] == "09011111111"
        assert records[0]["duration"] == 180.0
        assert records[1]["cell_tower_id"] == "CELL-B"

    def test_standard_field_names(self):
        """標準フィールド名 (caller_id 等) がそのまま使用される"""
        content = '{"caller_id": "111", "callee_id": "222", "duration": 30, "timestamp": "2026-01-01T00:00:00Z"}\n'
        records = parse_asn1_cdr(content.encode("utf-8"))
        assert len(records) == 1
        assert records[0]["caller_id"] == "111"

    def test_empty_content_raises_error(self):
        """空コンテンツで ValueError が発生する"""
        with pytest.raises(ValueError):
            parse_asn1_cdr(b"")


# =========================================================================
# CDR Analyzer — parse_cdr_file ディスパッチテスト
# =========================================================================


class TestParseCdrFile:
    """ファイル拡張子による CDR パーサー選択テスト"""

    def test_csv_extension_dispatches_to_csv_parser(self):
        """'.csv' 拡張子が CSV パーサーにディスパッチされる"""
        content = b"caller_id,timestamp\n111,2026-01-01T00:00:00Z\n"
        records = parse_cdr_file("data/test.csv", content)
        assert len(records) == 1

    def test_asn1_extension_dispatches_to_asn1_parser(self):
        """'.asn1' 拡張子が ASN.1 パーサーにディスパッチされる"""
        content = b'{"caller_id": "111", "timestamp": "2026-01-01T00:00:00Z"}\n'
        records = parse_cdr_file("data/test.asn1", content)
        assert len(records) == 1

    def test_unsupported_extension_raises_error(self):
        """未サポート拡張子で ValueError が発生する"""
        with pytest.raises(ValueError, match="Unsupported"):
            parse_cdr_file("data/test.xyz", b"some content")


# =========================================================================
# CDR Analyzer — トラフィック統計計算テスト
# =========================================================================


class TestComputeTrafficStatistics:
    """トラフィック統計計算のテスト"""

    def test_empty_records_returns_zeros(self):
        """空リストで全メトリクスが 0 を返す"""
        stats = compute_traffic_statistics([])
        assert stats["total_records"] == 0
        assert stats["average_duration"] == 0.0
        assert stats["peak_concurrent_calls"] == 0

    def test_single_record_statistics(self):
        """1 レコードの統計計算"""
        records = [{"caller_id": "111", "duration": 120.0, "timestamp": "2026-06-02 10:00:00"}]
        stats = compute_traffic_statistics(records)
        assert stats["total_records"] == 1
        assert stats["average_duration"] == 120.0

    def test_multiple_records_average_duration(self):
        """複数レコードの平均通話時間"""
        records = [
            {"caller_id": "111", "duration": 60.0, "timestamp": "2026-06-02 10:00:00"},
            {"caller_id": "222", "duration": 120.0, "timestamp": "2026-06-02 10:05:00"},
            {"caller_id": "333", "duration": 180.0, "timestamp": "2026-06-02 10:10:00"},
        ]
        stats = compute_traffic_statistics(records)
        assert stats["total_records"] == 3
        assert stats["average_duration"] == 120.0

    def test_hourly_volume_grouping(self):
        """時間帯別通話件数のグルーピング"""
        records = [
            {"caller_id": "a", "duration": 10.0, "timestamp": "2026-06-02 10:00:00"},
            {"caller_id": "b", "duration": 20.0, "timestamp": "2026-06-02 10:30:00"},
            {"caller_id": "c", "duration": 30.0, "timestamp": "2026-06-02 11:00:00"},
        ]
        stats = compute_traffic_statistics(records)
        hourly = stats["call_volume_per_hour"]
        assert hourly.get("2026-06-02 10:00") == 2
        assert hourly.get("2026-06-02 11:00") == 1


# =========================================================================
# Log Analyzer — syslog パースのテスト
# =========================================================================


class TestParseSyslogRfc5424:
    """RFC 5424 / RFC 3164 syslog パースのテスト"""

    def test_rfc5424_format(self):
        """RFC 5424 形式のログ行が正しくパースされる"""
        line = "<134>1 2026-06-02T10:00:00Z router-01 bgpd 12345 MSG-001 - BGP peer 10.0.0.1 established"
        result = parse_syslog_rfc5424(line)
        assert result is not None
        assert result["format"] == "rfc5424"
        assert result["hostname"] == "router-01"
        assert result["app_name"] == "bgpd"
        assert "BGP peer" in result["message"]
        assert result["severity_label"] == "informational"

    def test_rfc3164_format(self):
        """RFC 3164 (BSD) 形式のログ行が正しくパースされる"""
        line = "<134>Jun  2 10:00:00 switch-01 kernel: link-down on interface eth0"
        result = parse_syslog_rfc5424(line)
        assert result is not None
        assert result["format"] == "rfc3164"
        assert result["hostname"] == "switch-01"
        assert "link-down" in result["message"]

    def test_empty_line_returns_none(self):
        """空行は None を返す"""
        assert parse_syslog_rfc5424("") is None
        assert parse_syslog_rfc5424("   ") is None

    def test_unparseable_line_returns_none(self):
        """パース不能な行は None を返す"""
        assert parse_syslog_rfc5424("random garbage text") is None

    def test_severity_extraction(self):
        """Severity レベルが正しく抽出される (emergency=0, debug=7)"""
        # priority 8 = facility 1, severity 0 (emergency)
        line = "<8>1 2026-06-02T10:00:00Z host app - - - Emergency alert"
        result = parse_syslog_rfc5424(line)
        assert result is not None
        assert result["severity"] == 0
        assert result["severity_label"] == "emergency"


# =========================================================================
# Log Analyzer — SNMP trap パースのテスト
# =========================================================================


class TestParseSnmpTrap:
    """SNMP trap データパースのテスト"""

    def test_json_array_format(self):
        """JSON 配列形式の SNMP trap データ"""
        content = json.dumps([
            {"agent_address": "10.0.0.1", "enterprise": "1.3.6.1.4.1.9", "message": "link-down"},
            {"agent_address": "10.0.0.2", "enterprise": "1.3.6.1.4.1.9", "message": "power failure"},
        ])
        traps = parse_snmp_trap(content)
        assert len(traps) == 2
        assert traps[0]["agent_address"] == "10.0.0.1"
        assert traps[0]["source"] == "snmp_trap"

    def test_json_lines_format(self):
        """JSON Lines 形式の SNMP trap データ"""
        content = (
            '{"agentAddress": "10.0.0.1", "snmpTrapOID": "1.3.6.1.4.1.9", "description": "link-down"}\n'
            '{"agentAddress": "10.0.0.2", "snmpTrapOID": "1.3.6.1.4.1.9", "description": "fan failure"}\n'
        )
        traps = parse_snmp_trap(content)
        assert len(traps) == 2
        assert traps[0]["agent_address"] == "10.0.0.1"
        assert traps[1]["message"] == "fan failure"

    def test_empty_content_returns_empty(self):
        """空コンテンツで空リストを返す"""
        assert parse_snmp_trap("") == []


# =========================================================================
# Log Analyzer — 機器障害識別のテスト
# =========================================================================


class TestIdentifyEquipmentFailures:
    """機器障害識別のテスト"""

    def test_link_down_detected(self):
        """link-down パターンが検出される"""
        entries = [{"message": "Interface eth0 link-down detected", "hostname": "sw1", "app_name": "linkd", "timestamp": "2026-01-01", "severity_label": "error"}]
        failures = identify_equipment_failures(entries)
        assert len(failures) == 1
        assert "link" in failures[0]["type"]

    def test_hardware_error_detected(self):
        """hardware error パターンが検出される"""
        entries = [{"message": "Module 3 hardware error reported", "hostname": "router1", "app_name": "hwmon", "timestamp": "2026-01-01", "severity_label": "critical"}]
        failures = identify_equipment_failures(entries)
        assert len(failures) == 1

    def test_process_crash_detected(self):
        """process crash パターンが検出される"""
        entries = [{"message": "BGP process crash observed", "hostname": "core-rtr", "app_name": "bgpd", "timestamp": "2026-01-01", "severity_label": "alert"}]
        failures = identify_equipment_failures(entries)
        assert len(failures) == 1

    def test_no_failure_in_normal_message(self):
        """正常なメッセージでは障害が検出されない"""
        entries = [{"message": "Routing table updated successfully", "hostname": "rtr1", "app_name": "routing", "timestamp": "2026-01-01", "severity_label": "informational"}]
        failures = identify_equipment_failures(entries)
        assert len(failures) == 0

    def test_empty_entries_returns_empty(self):
        """空リストで空リストを返す"""
        assert identify_equipment_failures([]) == []


# =========================================================================
# Log Analyzer — キャパシティ閾値超過検出のテスト
# =========================================================================


class TestDetectCapacityBreaches:
    """キャパシティ閾値超過検出のテスト"""

    def test_breach_at_default_threshold(self):
        """デフォルト閾値 80% で超過が検出される"""
        entries = [{"message": "CPU utilization: 95%", "hostname": "host1", "app_name": "monitor", "timestamp": "2026-01-01"}]
        breaches = detect_capacity_breaches(entries, threshold_percent=80.0)
        assert len(breaches) == 1
        assert breaches[0]["utilization_percent"] == 95.0
        assert breaches[0]["exceeded_by"] == 15.0

    def test_below_threshold_not_detected(self):
        """閾値未満は検出されない"""
        entries = [{"message": "Memory usage: 50%", "hostname": "host1", "app_name": "monitor", "timestamp": "2026-01-01"}]
        breaches = detect_capacity_breaches(entries, threshold_percent=80.0)
        assert len(breaches) == 0

    def test_exactly_at_threshold_is_breach(self):
        """閾値ちょうどは超過として検出される"""
        entries = [{"message": "Disk capacity: 80.0%", "hostname": "host1", "app_name": "monitor", "timestamp": "2026-01-01"}]
        breaches = detect_capacity_breaches(entries, threshold_percent=80.0)
        assert len(breaches) == 1

    def test_custom_threshold(self):
        """カスタム閾値 (90%) のテスト"""
        entries = [{"message": "Network load: 85%", "hostname": "host1", "app_name": "monitor", "timestamp": "2026-01-01"}]
        breaches = detect_capacity_breaches(entries, threshold_percent=90.0)
        assert len(breaches) == 0


# =========================================================================
# Anomaly Detector — ベースライン統計計算のテスト
# =========================================================================


class TestCalculateBaselineStatistics:
    """ベースライン統計計算のテスト"""

    def test_empty_values(self):
        """空リストで mean=0, stddev=0, count=0 を返す"""
        stats = calculate_baseline_statistics([])
        assert stats == {"mean": 0.0, "stddev": 0.0, "count": 0}

    def test_single_value(self):
        """1 値で stddev=0"""
        stats = calculate_baseline_statistics([100.0])
        assert stats["mean"] == 100.0
        assert stats["stddev"] == 0.0
        assert stats["count"] == 1

    def test_multiple_values(self):
        """複数値の統計計算"""
        values = [10.0, 20.0, 30.0, 40.0, 50.0]
        stats = calculate_baseline_statistics(values)
        assert stats["mean"] == 30.0
        assert stats["count"] == 5
        assert stats["stddev"] > 0

    def test_identical_values_zero_stddev(self):
        """同一値のリストで stddev=0"""
        stats = calculate_baseline_statistics([5.0, 5.0, 5.0, 5.0])
        assert stats["mean"] == 5.0
        assert stats["stddev"] == 0.0


# =========================================================================
# Anomaly Detector — 3σ 異常検出のテスト
# =========================================================================


class TestDetectAnomalies:
    """3σ 異常検出のテスト"""

    def test_no_anomalies_within_threshold(self):
        """閾値内の値では異常が検出されない"""
        current = {"call_volume": 100.0}
        baseline = {"call_volume": {"mean": 100.0, "stddev": 10.0, "count": 7}}
        anomalies = detect_anomalies(current, baseline, threshold_stddev=3.0)
        assert len(anomalies) == 0

    def test_anomaly_detected_above_threshold(self):
        """3σ 超過の値で異常が検出される"""
        current = {"call_volume": 200.0}
        baseline = {"call_volume": {"mean": 100.0, "stddev": 10.0, "count": 7}}
        anomalies = detect_anomalies(current, baseline, threshold_stddev=3.0)
        assert len(anomalies) == 1
        assert anomalies[0]["metric_name"] == "call_volume"
        assert anomalies[0]["deviation_direction"] == "above"
        assert anomalies[0]["z_score"] == 10.0

    def test_anomaly_detected_below_threshold(self):
        """下方向の 3σ 超過で異常が検出される"""
        current = {"call_volume": 50.0}
        baseline = {"call_volume": {"mean": 100.0, "stddev": 10.0, "count": 7}}
        anomalies = detect_anomalies(current, baseline, threshold_stddev=3.0)
        assert len(anomalies) == 1
        assert anomalies[0]["deviation_direction"] == "below"

    def test_insufficient_baseline_data_skipped(self):
        """ベースラインデータ不足 (count < 2) はスキップされる"""
        current = {"call_volume": 200.0}
        baseline = {"call_volume": {"mean": 100.0, "stddev": 10.0, "count": 1}}
        anomalies = detect_anomalies(current, baseline, threshold_stddev=3.0)
        assert len(anomalies) == 0

    def test_zero_stddev_skipped(self):
        """stddev=0 のメトリクスはスキップされる"""
        current = {"call_volume": 200.0}
        baseline = {"call_volume": {"mean": 100.0, "stddev": 0.0, "count": 5}}
        anomalies = detect_anomalies(current, baseline, threshold_stddev=3.0)
        assert len(anomalies) == 0

    def test_metric_not_in_baseline_ignored(self):
        """ベースラインにないメトリクスは無視される"""
        current = {"new_metric": 100.0}
        baseline = {"call_volume": {"mean": 50.0, "stddev": 5.0, "count": 7}}
        anomalies = detect_anomalies(current, baseline, threshold_stddev=3.0)
        assert len(anomalies) == 0

    def test_custom_threshold_stddev(self):
        """カスタム閾値 (2σ) のテスト"""
        current = {"call_volume": 125.0}
        baseline = {"call_volume": {"mean": 100.0, "stddev": 10.0, "count": 7}}
        # z_score = 2.5, which is > 2.0
        anomalies = detect_anomalies(current, baseline, threshold_stddev=2.0)
        assert len(anomalies) == 1


# =========================================================================
# Anomaly Detector — Bedrock 推論テスト (モック)
# =========================================================================


class TestInvokeBedrockAnomalyClassification:
    """Bedrock 推論呼び出しテスト (モック)"""

    def test_no_anomalies_returns_normal(self):
        """異常がない場合は 'normal' 分類を返す"""
        result = invoke_bedrock_anomaly_classification(None, [])
        assert result["classification"] == "normal"
        assert result["explanation"] == "No anomalies detected"

    def test_successful_bedrock_response(self):
        """Bedrock が正常レスポンスを返す場合"""
        mock_client = MagicMock()
        response_body = {
            "content": [{"type": "text", "text": json.dumps({
                "classification": "traffic_surge",
                "explanation": "Unusual traffic increase",
                "recommendations": ["Scale up capacity", "Monitor closely"],
            })}]
        }
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps(response_body).encode()
        mock_client.invoke_model.return_value = {"body": mock_body}

        anomalies = [{"metric_name": "call_volume", "z_score": 5.0, "current_value": 500}]
        result = invoke_bedrock_anomaly_classification(mock_client, anomalies)

        assert result["classification"] == "traffic_surge"
        assert "Unusual traffic" in result["explanation"]
        assert len(result["recommendations"]) == 2

    def test_bedrock_non_json_response(self):
        """Bedrock が JSON でないレスポンスを返す場合"""
        mock_client = MagicMock()
        response_body = {
            "content": [{"type": "text", "text": "This is plain text without JSON"}]
        }
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps(response_body).encode()
        mock_client.invoke_model.return_value = {"body": mock_body}

        anomalies = [{"metric_name": "call_volume", "z_score": 4.0}]
        result = invoke_bedrock_anomaly_classification(mock_client, anomalies)

        assert result["classification"] == "unknown"
        assert "plain text" in result["explanation"]


# =========================================================================
# CDR Analyzer — エラー記録テスト (モック)
# =========================================================================


class TestRecordParseError:
    """CDR パースエラー記録のテスト"""

    def test_error_recorded_to_s3(self):
        """エラーが errors/cdr/ プレフィックス下に記録される"""
        mock_s3 = MagicMock()
        record_parse_error(
            s3_client=mock_s3,
            output_bucket="test-bucket",
            file_key="cdr/2026/06/02/corrupt.csv",
            error_category="parse_error",
            error_details="Invalid CSV structure",
        )
        mock_s3.put_object.assert_called_once()
        call_kwargs = mock_s3.put_object.call_args[1]
        assert call_kwargs["Bucket"] == "test-bucket"
        assert "errors/cdr/" in call_kwargs["Key"]
        body = json.loads(call_kwargs["Body"])
        assert body["file_path"] == "cdr/2026/06/02/corrupt.csv"
        assert body["error_category"] == "parse_error"

    def test_error_record_failure_handled_gracefully(self):
        """S3 書き込み失敗時も例外を発生させない"""
        mock_s3 = MagicMock()
        mock_s3.put_object.side_effect = Exception("S3 error")
        # Should not raise
        record_parse_error(
            s3_client=mock_s3,
            output_bucket="test-bucket",
            file_key="cdr/file.csv",
            error_category="parse_error",
            error_details="Some error",
        )
