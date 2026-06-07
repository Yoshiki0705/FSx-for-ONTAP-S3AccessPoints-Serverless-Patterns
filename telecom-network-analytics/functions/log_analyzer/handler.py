"""通信業界 (UC18) Log Analyzer Lambda ハンドラ

ネットワーク機器ログ (syslog RFC 5424 / SNMP trap) をパースし、
機器障害の識別およびキャパシティ閾値超過の検出を行う。

パース対象:
    - syslog RFC 5424 形式
    - SNMP trap データ (JSON 形式)

検出対象:
    - 機器障害 (link-down, hardware error, process crash)
    - キャパシティ閾値超過 (デフォルト: プロビジョニング容量の 80%)

Requirements: 2.3, 2.5, 2.6, 13.6

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    OUTPUT_BUCKET: 出力バケット名
    CAPACITY_THRESHOLD_PERCENT: キャパシティ閾値 (default: 80)
    SNS_TOPIC_ARN: 通知先 SNS トピック ARN
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)

# デフォルトキャパシティ閾値 (%)
DEFAULT_CAPACITY_THRESHOLD_PERCENT = 80

# 機器障害パターン (syslog メッセージで検出)
EQUIPMENT_FAILURE_PATTERNS = [
    re.compile(r"link[- ]?down", re.IGNORECASE),
    re.compile(r"hardware[- ]?error", re.IGNORECASE),
    re.compile(r"process[- ]?crash", re.IGNORECASE),
    re.compile(r"interface[- ]?down", re.IGNORECASE),
    re.compile(r"port[- ]?down", re.IGNORECASE),
    re.compile(r"module[- ]?failure", re.IGNORECASE),
    re.compile(r"fan[- ]?failure", re.IGNORECASE),
    re.compile(r"power[- ]?supply[- ]?failure", re.IGNORECASE),
    re.compile(r"memory[- ]?error", re.IGNORECASE),
    re.compile(r"disk[- ]?failure", re.IGNORECASE),
]

# キャパシティ関連のパターン (使用率抽出用)
UTILIZATION_PATTERN = re.compile(
    r"(?:utilization|usage|capacity|load)[:\s]*(\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)

# RFC 5424 Syslog パーサー
# フォーマット: <priority>version timestamp hostname app-name procid msgid structured-data msg
RFC5424_PATTERN = re.compile(
    r"^<(\d{1,3})>(\d+)\s+"  # PRI + VERSION
    r"(\S+)\s+"  # TIMESTAMP
    r"(\S+)\s+"  # HOSTNAME
    r"(\S+)\s+"  # APP-NAME
    r"(\S+)\s+"  # PROCID
    r"(\S+)\s+"  # MSGID
    r"(?:\[([^\]]*)\]\s*)*"  # STRUCTURED-DATA (optional)
    r"(.*)$"  # MSG
)

# BSD Syslog (RFC 3164) フォールバック
RFC3164_PATTERN = re.compile(
    r"^<(\d{1,3})>?"  # PRI (optional)
    r"(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+"  # TIMESTAMP (Mon DD HH:MM:SS)
    r"(\S+)\s+"  # HOSTNAME
    r"(\S+?)(?:\[(\d+)\])?:\s+"  # APP-NAME[PID]
    r"(.*)$"  # MSG
)

# Severity レベル (RFC 5424)
SEVERITY_LEVELS = {
    0: "emergency",
    1: "alert",
    2: "critical",
    3: "error",
    4: "warning",
    5: "notice",
    6: "informational",
    7: "debug",
}


def parse_syslog_rfc5424(line: str) -> dict[str, Any] | None:
    """RFC 5424 形式の syslog 行をパースする。

    RFC 5424 にマッチしない場合は RFC 3164 (BSD) フォールバックを試行。

    Args:
        line: syslog 行文字列

    Returns:
        dict | None: パースされたログエントリ、またはパース失敗時 None
    """
    line = line.strip()
    if not line:
        return None

    # RFC 5424 を試行
    match = RFC5424_PATTERN.match(line)
    if match:
        priority = int(match.group(1))
        facility = priority >> 3
        severity = priority & 0x07

        return {
            "format": "rfc5424",
            "priority": priority,
            "facility": facility,
            "severity": severity,
            "severity_label": SEVERITY_LEVELS.get(severity, "unknown"),
            "version": int(match.group(2)),
            "timestamp": match.group(3),
            "hostname": match.group(4),
            "app_name": match.group(5),
            "proc_id": match.group(6),
            "msg_id": match.group(7),
            "structured_data": match.group(8) or "",
            "message": match.group(9).strip(),
        }

    # RFC 3164 フォールバック
    match = RFC3164_PATTERN.match(line)
    if match:
        priority = int(match.group(1)) if match.group(1) else 13  # default user.notice
        facility = priority >> 3
        severity = priority & 0x07

        return {
            "format": "rfc3164",
            "priority": priority,
            "facility": facility,
            "severity": severity,
            "severity_label": SEVERITY_LEVELS.get(severity, "unknown"),
            "timestamp": match.group(2),
            "hostname": match.group(3),
            "app_name": match.group(4),
            "proc_id": match.group(5) or "-",
            "message": match.group(6).strip(),
        }

    return None


def parse_snmp_trap(content: str) -> list[dict[str, Any]]:
    """SNMP trap データ (JSON 形式) をパースする。

    想定フォーマット: JSON Lines (1行1トラップ) または JSON 配列。

    Args:
        content: SNMP trap ファイルの内容

    Returns:
        list[dict]: パースされたトラップデータのリスト
    """
    traps = []

    # JSON 配列形式を試行
    content_stripped = content.strip()
    if content_stripped.startswith("["):
        try:
            data = json.loads(content_stripped)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        traps.append(_normalize_snmp_trap(item))
                return traps
        except json.JSONDecodeError:
            pass

    # JSON Lines 形式
    for line in content_stripped.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                traps.append(_normalize_snmp_trap(obj))
        except json.JSONDecodeError:
            continue

    return traps


def _normalize_snmp_trap(raw: dict[str, Any]) -> dict[str, Any]:
    """SNMP trap データを正規化する。

    Args:
        raw: 生の SNMP trap JSON オブジェクト

    Returns:
        dict: 正規化された SNMP trap データ
    """
    return {
        "source": "snmp_trap",
        "agent_address": raw.get("agent_address", raw.get("agentAddress", "")),
        "enterprise": raw.get("enterprise", raw.get("snmpTrapOID", "")),
        "generic_trap": raw.get("generic_trap", raw.get("genericTrap", -1)),
        "specific_trap": raw.get("specific_trap", raw.get("specificTrap", -1)),
        "timestamp": raw.get("timestamp", raw.get("sysUpTime", "")),
        "variables": raw.get("variables", raw.get("varbinds", [])),
        "message": raw.get("message", raw.get("description", "")),
        "severity": raw.get("severity", "warning"),
    }


def identify_equipment_failures(
    log_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """ログエントリから機器障害を識別する。

    検出対象: link-down, hardware error, process crash 等。

    Args:
        log_entries: パースされたログエントリのリスト

    Returns:
        list[dict]: 識別された機器障害のリスト
    """
    failures = []

    for entry in log_entries:
        message = entry.get("message", "")
        if not message:
            continue

        for pattern in EQUIPMENT_FAILURE_PATTERNS:
            if pattern.search(message):
                failures.append(
                    {
                        "type": pattern.pattern.replace(r"[- ]?", "-").lower(),
                        "hostname": entry.get("hostname", "unknown"),
                        "app_name": entry.get("app_name", "unknown"),
                        "timestamp": entry.get("timestamp", ""),
                        "severity": entry.get("severity_label", entry.get("severity", "unknown")),
                        "message": message[:500],  # メッセージ長制限
                        "source": entry.get("format", entry.get("source", "unknown")),
                    }
                )
                break  # 1エントリにつき最初にマッチしたパターンのみ

    return failures


def detect_capacity_breaches(
    log_entries: list[dict[str, Any]],
    threshold_percent: float = DEFAULT_CAPACITY_THRESHOLD_PERCENT,
) -> list[dict[str, Any]]:
    """キャパシティ閾値超過を検出する。

    ログメッセージから使用率パーセンテージを抽出し、
    閾値を超過しているエントリを報告する。

    Args:
        log_entries: パースされたログエントリのリスト
        threshold_percent: 閾値パーセンテージ (デフォルト: 80%)

    Returns:
        list[dict]: 閾値超過検出結果のリスト
    """
    breaches = []

    for entry in log_entries:
        message = entry.get("message", "")
        if not message:
            continue

        match = UTILIZATION_PATTERN.search(message)
        if match:
            utilization = float(match.group(1))
            if utilization >= threshold_percent:
                breaches.append(
                    {
                        "hostname": entry.get("hostname", "unknown"),
                        "app_name": entry.get("app_name", "unknown"),
                        "timestamp": entry.get("timestamp", ""),
                        "utilization_percent": utilization,
                        "threshold_percent": threshold_percent,
                        "exceeded_by": round(utilization - threshold_percent, 2),
                        "message": message[:500],
                        "source": entry.get("format", entry.get("source", "unknown")),
                    }
                )

    return breaches


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Log Analyzer Lambda ハンドラ

    Step Functions Map State から呼び出され、ネットワーク機器ログを処理する。

    Event 形式:
        {
            "key": "logs/syslog/router-01.log",
            "size": 524288,
            "manifest_key": "manifests/2026/06/02/xxx.json"
        }

    Processing Flow:
        1. S3 AP からファイル取得
        2. ファイル形式判定 (syslog / SNMP trap)
        3. パース実行
        4. 機器障害識別
        5. キャパシティ閾値超過検出
        6. 結果を S3 出力に書き出し

    Returns:
        dict: 処理結果 (status, log_entries_count, failures, breaches)
    """
    file_key = event.get("key", event.get("Key", ""))
    file_size = event.get("size", event.get("Size", 0))

    logger.info(
        "Log Analyzer started: key=%s, size=%d",
        file_key,
        file_size,
    )

    # 環境設定
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    output_bucket = os.environ.get("OUTPUT_BUCKET", "")
    capacity_threshold = float(os.environ.get("CAPACITY_THRESHOLD_PERCENT", DEFAULT_CAPACITY_THRESHOLD_PERCENT))
    s3_client = boto3.client("s3")

    # Step 1: ファイル取得
    try:
        with xray_subsegment(
            name="s3ap_get_object",
            annotations={
                "service_name": "s3",
                "operation": "GetObject",
                "use_case": "telecom-network-analytics",
            },
        ):
            response = s3ap.get_object(file_key)
            content = response["Body"].read()
            response["Body"].close()
    except Exception as e:
        logger.error("Failed to retrieve file %s: %s", file_key, str(e))
        return {
            "key": file_key,
            "status": "error",
            "error_category": "retrieval_error",
            "error_details": str(e),
        }

    # Step 2: ファイル内容デコード
    try:
        text_content = content.decode("utf-8", errors="replace")
    except Exception as e:
        logger.error("Failed to decode file %s: %s", file_key, str(e))
        if output_bucket:
            _record_error(s3_client, output_bucket, file_key, "decode_error", str(e))
        return {
            "key": file_key,
            "status": "parse_error",
            "error_category": "decode_error",
            "error_details": str(e),
        }

    # Step 3: パース (形式判定)
    log_entries: list[dict[str, Any]] = []
    parse_errors = 0

    with xray_subsegment(
        name="log_parse",
        annotations={
            "service_name": "log_parser",
            "operation": "Parse",
            "use_case": "telecom-network-analytics",
        },
    ):
        # SNMP trap (JSON形式) かどうかを判定
        stripped = text_content.strip()
        if stripped.startswith("[") or stripped.startswith("{"):
            # SNMP trap として試行
            traps = parse_snmp_trap(text_content)
            if traps:
                log_entries.extend(traps)
            else:
                # JSON っぽいが trap でなければ syslog としてフォールバック
                for line in text_content.split("\n"):
                    entry = parse_syslog_rfc5424(line)
                    if entry:
                        log_entries.append(entry)
                    elif line.strip():
                        parse_errors += 1
        else:
            # syslog として処理
            for line in text_content.split("\n"):
                entry = parse_syslog_rfc5424(line)
                if entry:
                    log_entries.append(entry)
                elif line.strip():
                    parse_errors += 1

    if not log_entries and parse_errors > 0:
        # 全行パース失敗
        error_msg = f"No valid log entries parsed from {file_key} ({parse_errors} unparseable lines)"
        logger.warning(error_msg)
        if output_bucket:
            _record_error(s3_client, output_bucket, file_key, "parse_error", error_msg)
        return {
            "key": file_key,
            "status": "parse_error",
            "error_category": "parse_error",
            "error_details": error_msg,
            "log_entries_count": 0,
            "parse_errors": parse_errors,
        }

    # Step 4: 機器障害識別
    with xray_subsegment(
        name="identify_failures",
        annotations={
            "service_name": "log_analyzer",
            "operation": "IdentifyFailures",
            "use_case": "telecom-network-analytics",
        },
    ):
        failures = identify_equipment_failures(log_entries)

    # Step 5: キャパシティ閾値超過検出
    with xray_subsegment(
        name="detect_breaches",
        annotations={
            "service_name": "log_analyzer",
            "operation": "DetectBreaches",
            "use_case": "telecom-network-analytics",
        },
    ):
        breaches = detect_capacity_breaches(log_entries, capacity_threshold)

    # Step 6: 結果構築
    result = {
        "key": file_key,
        "status": "success",
        "log_entries_count": len(log_entries),
        "parse_errors": parse_errors,
        "equipment_failures": failures,
        "equipment_failures_count": len(failures),
        "capacity_breaches": breaches,
        "capacity_breaches_count": len(breaches),
        "threshold_percent": capacity_threshold,
        "processing_timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # 結果書き出し
    if output_bucket:
        date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
        file_basename = file_key.rsplit("/", 1)[-1] if "/" in file_key else file_key
        result_key = f"results/logs/{date_prefix}/{file_basename}.result.json"
        try:
            s3_client.put_object(
                Bucket=output_bucket,
                Key=result_key,
                Body=json.dumps(result, default=str, ensure_ascii=False),
                ContentType="application/json",
            )
        except Exception as e:
            logger.error("Failed to write result for %s: %s", file_key, str(e))

    # EMF メトリクス
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="log_analyzer")
    metrics.set_dimension("UseCase", "telecom-network-analytics")
    metrics.put_metric("LogEntriesProcessed", float(len(log_entries)), "Count")
    metrics.put_metric("EquipmentFailures", float(len(failures)), "Count")
    metrics.put_metric("CapacityBreaches", float(len(breaches)), "Count")
    metrics.put_metric("FilesProcessed", 1.0, "Count")
    metrics.flush()

    logger.info(
        "Log Analyzer completed: key=%s, entries=%d, failures=%d, breaches=%d",
        file_key,
        len(log_entries),
        len(failures),
        len(breaches),
    )

    return result


def _record_error(
    s3_client,
    output_bucket: str,
    file_key: str,
    error_category: str,
    error_details: str,
) -> None:
    """エラーレコードを errors/cdr/ プレフィックス下に書き出す。

    Args:
        s3_client: boto3 S3 クライアント
        output_bucket: 出力バケット名
        file_key: 失敗したファイルのキー
        error_category: エラーカテゴリ
        error_details: エラー詳細
    """
    error_record = {
        "file_path": file_key,
        "error_category": error_category,
        "error_details": error_details,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    file_basename = file_key.rsplit("/", 1)[-1] if "/" in file_key else file_key
    error_key = f"errors/cdr/{date_prefix}/{file_basename}.error.json"

    try:
        s3_client.put_object(
            Bucket=output_bucket,
            Key=error_key,
            Body=json.dumps(error_record, ensure_ascii=False),
            ContentType="application/json",
        )
        logger.info("Error recorded: %s → %s", file_key, error_key)
    except Exception as e:
        logger.error("Failed to record error for %s: %s", file_key, str(e))
