"""FPolicy External Server — ONTAP FPolicy TCP サーバー.

ONTAP FPolicy の外部サーバーとして TCP 接続を受け付け、
ファイル操作イベントを受信して SQS に転送する。

ECS Fargate タスクまたは EC2 インスタンスとしてデプロイする。
Lambda では実装不可（長時間 TCP 接続が必要なため）。

Configuration (環境変数):
    FPOLICY_PORT: TCP リスンポート (default: 9898)
    SQS_QUEUE_URL: Ingestion Queue の URL
    AWS_REGION: AWS リージョン (default: ap-northeast-1)
    MODE: 動作モード (realtime / batch, default: realtime)
    LOG_DIR: Batch モード時のログ出力ディレクトリ
    WRITE_COMPLETE_DELAY_SEC: NFSv3 write-complete 待機秒数 (default: 5)
    SCHEMA_PATH: JSON Schema ファイルパス

Protocol:
    - ONTAP が TCP 接続を開始（サーバーはパッシブ）
    - 非同期モード（asynchronous）: NOTI_REQ にレスポンス不要
    - NEGO_REQ のみレスポンス（NEGO_RESP）が必要
    - KEEP_ALIVE_REQ はログのみ（レスポンス不要）

Reference:
    - NetApp Docs: https://docs.netapp.com/us-en/ontap-technical-reports/
      ontap-security-hardening/create-fpolicy.html
    - Shengyu Fang: https://github.com/YhunerFSY/ontap-fpolicy-aws-integration
"""

from __future__ import annotations

import json
import logging
import os
import re
import socket
import struct
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import boto3

# Protobuf parser (lazy import to avoid dependency when using XML mode)
try:
    from .protobuf_parser import (
        ProtobufParser,
        is_protobuf_format,
    )

    PROTOBUF_AVAILABLE = True
except ImportError:
    try:
        from protobuf_parser import ProtobufParser, is_protobuf_format

        PROTOBUF_AVAILABLE = True
    except ImportError:
        PROTOBUF_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("fpolicy-server")

# --- Configuration ---
FPOLICY_PORT = int(os.environ.get("FPOLICY_PORT", "9898"))
SQS_QUEUE_URL = os.environ.get("SQS_QUEUE_URL", "")
AWS_REGION = os.environ.get("AWS_REGION", "ap-northeast-1")
MODE = os.environ.get("MODE", "realtime")  # realtime or batch
LOG_DIR = os.environ.get("LOG_DIR", "/var/log/fpolicy")
WRITE_COMPLETE_DELAY_SEC = int(os.environ.get("WRITE_COMPLETE_DELAY_SEC", "5"))
SCHEMA_PATH = os.environ.get(
    "SCHEMA_PATH",
    str(Path(__file__).parent.parent / "schemas" / "fpolicy-event-schema.json"),
)
FPOLICY_FORMAT = os.environ.get("FPOLICY_FORMAT", "xml")  # xml or protobuf

# Protocol constants
XML_DECL = b'<?xml version="1.0"?>'
SEPARATOR = b"\n\n"
PREFERRED_VERSIONS = ["1.2", "1.1", "1.0", "2.0", "3.0"]


class FPolicyServer:
    """FPolicy 外部サーバー（TCP）.

    ONTAP からの TCP 接続を受け付け、ファイルイベントを処理する。
    非同期モードで動作し、NOTI_REQ にはレスポンスを返さない。
    """

    def __init__(
        self,
        port: int = FPOLICY_PORT,
        sqs_queue_url: str = SQS_QUEUE_URL,
        aws_region: str = AWS_REGION,
        mode: str = MODE,
        write_complete_delay_sec: int = WRITE_COMPLETE_DELAY_SEC,
        fpolicy_format: str = FPOLICY_FORMAT,
    ) -> None:
        self.port = port
        self.sqs_queue_url = sqs_queue_url
        self.aws_region = aws_region
        self.mode = mode
        self.write_complete_delay_sec = write_complete_delay_sec
        self.fpolicy_format = fpolicy_format
        self._sqs_client: Any = None
        self._cw_client: Any = None
        self._running = False
        # Session context: store SVM/policy info from NEGO_REQ per connection
        self._session_context: dict[str, dict[str, str]] = {}
        # Default SVM/volume from environment (fallback)
        self._default_svm_name = os.environ.get("SVM_NAME", "")
        self._default_volume_name = os.environ.get("VOLUME_NAME", "")
        # Protobuf parser (initialized if format is protobuf)
        self._protobuf_parser: Optional[Any] = None
        if self.fpolicy_format == "protobuf":
            if PROTOBUF_AVAILABLE:
                self._protobuf_parser = ProtobufParser()
                logger.info("Protobuf parser initialized (format=protobuf)")
            else:
                logger.warning(
                    "FPOLICY_FORMAT=protobuf but protobuf_parser not available, "
                    "falling back to auto-detect mode"
                )

    @property
    def sqs_client(self) -> Any:
        if self._sqs_client is None:
            self._sqs_client = boto3.client("sqs", region_name=self.aws_region)
        return self._sqs_client

    @property
    def cw_client(self) -> Any:
        if self._cw_client is None:
            self._cw_client = boto3.client(
                "cloudwatch", region_name=self.aws_region
            )
        return self._cw_client

    def start(self) -> None:
        """サーバーを起動し、接続を待ち受ける."""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", self.port))
        server.listen(5)
        self._running = True

        logger.info(
            "FPolicy Server started on port %d (mode=%s, delay=%ds, format=%s)",
            self.port,
            self.mode,
            self.write_complete_delay_sec,
            self.fpolicy_format,
        )
        if self.sqs_queue_url:
            logger.info("SQS Queue: %s", self.sqs_queue_url)

        try:
            while self._running:
                conn, addr = server.accept()
                thread = threading.Thread(
                    target=self.handle_client,
                    args=(conn, addr),
                    daemon=True,
                )
                thread.start()
        except KeyboardInterrupt:
            logger.info("Server shutting down...")
        finally:
            self._running = False
            server.close()

    def stop(self) -> None:
        """サーバーを停止する."""
        self._running = False

    def handle_client(self, conn: socket.socket, addr: tuple) -> None:
        """クライアント接続を処理する（スレッド単位）."""
        logger.info("[+] Connection from %s", addr)
        # Timeout must exceed ONTAP keep_alive_interval (default 2min=120s)
        # Set to 300s to safely receive KEEP_ALIVE before timeout
        conn.settimeout(300.0)

        # Per-connection session context (populated by NEGO_REQ)
        conn_ctx: dict[str, str] = {}

        try:
            while self._running:
                raw_msg = self.read_fpolicy_message(conn)
                if raw_msg is None:
                    logger.info("[-] Connection closed: %s", addr)
                    break

                # Auto-detect format or use configured format
                if self._protobuf_parser and PROTOBUF_AVAILABLE:
                    if is_protobuf_format(raw_msg):
                        self._dispatch_protobuf_message(conn, raw_msg, conn_ctx)
                        continue

                # Default: XML format
                header_str, body_str = self.parse_header_and_body(raw_msg)
                self._dispatch_message(conn, header_str, body_str, conn_ctx)

        except socket.timeout:
            logger.warning("[-] Timeout: %s", addr)
        except Exception as e:
            logger.error("[Error] %s: %s", addr, str(e))
        finally:
            conn.close()

    def read_fpolicy_message(self, conn: socket.socket) -> Optional[bytes]:
        """FPolicy メッセージを TCP フレーミングに従って読み取る.

        Frame format: b'"' + 4-byte big-endian length + b'"' + payload

        Note: After handshake, ONTAP may send KEEP_ALIVE or STATUS_REQ
        before any NOTI_REQ. The server must stay connected and keep reading.
        """
        # Read opening quote — may receive non-quote bytes (e.g. NUL padding)
        attempts = 0
        while True:
            b = self._recvall(conn, 1)
            if b is None:
                return None
            if b == b'"':
                break
            # Log unexpected bytes for debugging
            attempts += 1
            if attempts <= 5:
                logger.debug(
                    "[Proto] Skipping unexpected byte: 0x%02x", b[0]
                )
            if attempts > 1024:
                logger.warning("[Proto] Too many unexpected bytes, closing")
                return None

        # Read 4-byte length
        len_bytes = self._recvall(conn, 4)
        if len_bytes is None:
            return None
        msg_len = struct.unpack(">I", len_bytes)[0]

        # Read closing quote
        closing = self._recvall(conn, 1)
        if closing is None:
            return None

        # Sanity check
        if msg_len == 0 or msg_len > 10 * 1024 * 1024:
            logger.warning("Invalid message length: %d", msg_len)
            return None

        # Read payload
        return self._recvall(conn, msg_len)

    def parse_header_and_body(self, raw_bytes: bytes) -> tuple[str, str]:
        """FPolicy メッセージを Header と Body に分割する.

        区切り: b'\\n\\n'
        """
        parts = raw_bytes.split(b"\n\n", 1)
        header_str = parts[0].strip().decode("utf-8", errors="ignore")
        body_str = (
            parts[1].strip(b"\x00\n\r").decode("utf-8", errors="ignore")
            if len(parts) > 1
            else ""
        )
        return header_str, body_str

    def send_nego_resp(
        self,
        conn: socket.socket,
        session_id: str,
        selected_version: str,
        vs_uuid: str,
        policy_name: str,
    ) -> None:
        """NEGO_RESP を送信する（ハンドシェイク応答）."""
        body_xml = (
            "<HandshakeResp>"
            f"<VsUUID>{vs_uuid}</VsUUID>"
            f"<PolicyName>{policy_name}</PolicyName>"
            f"<SessionId>{session_id}</SessionId>"
            f"<ProtVersion>{selected_version}</ProtVersion>"
            "</HandshakeResp>"
        )
        body_part = XML_DECL + body_xml.encode("utf-8")
        content_len = len(body_part)

        header_xml = (
            "<Header>"
            "<NotfType>NEGO_RESP</NotfType>"
            f"<ContentLen>{content_len}</ContentLen>"
            "<DataFormat>XML</DataFormat>"
            "</Header>"
        )
        header_part = XML_DECL + header_xml.encode("utf-8")

        payload = header_part + SEPARATOR + body_part + b"\x00"
        frame = b'"' + struct.pack(">I", len(payload)) + b'"' + payload
        conn.sendall(frame)
        logger.info(
            "[Send] NEGO_RESP | Version=%s | Policy=%s",
            selected_version,
            policy_name,
        )

    def handle_noti_req(self, body_str: str, conn_ctx: dict[str, str] = None) -> None:
        """NOTI_REQ（ファイルイベント通知）を処理する.

        非同期モード: レスポンス不要。
        """
        if conn_ctx is None:
            conn_ctx = {}

        # Debug: log raw body for troubleshooting (first 500 chars)
        logger.debug("[NOTI_REQ] Raw body (500): %s", body_str[:500])

        # Extract file path from XML — multiple fallback patterns
        ontap_path = self._extract_xml_value(
            body_str,
            ["PathName", "Path", "FileName", "Name"],
        )

        if not ontap_path:
            logger.warning("[NOTI_REQ] No path found in body")
            return

        # Strip any residual XML tags from extracted path
        ontap_path = re.sub(r"<[^>]+>", "", ontap_path).strip()
        # Clean Windows path separators
        ontap_path = ontap_path.replace("\\", "/").lstrip("/")

        # Extract operation type from XML
        operation = self._extract_xml_value(
            body_str,
            ["FileOp", "NotfType", "OpType", "Operation"],
        )
        operation = operation.lower() if operation else "create"

        # Extract volume name — ONTAP uses various tag names
        volume_name = self._extract_xml_value(
            body_str,
            ["VolName", "VolumeName", "Volume", "Vol"],
        )
        if not volume_name:
            volume_name = self._default_volume_name or "vol1"

        # Extract SVM name — ONTAP uses various tag names
        svm_name = self._extract_xml_value(
            body_str,
            ["VsName", "VserverName", "Vserver", "SvmName"],
        )
        if not svm_name:
            # Fallback: use session context from NEGO_REQ, then env var
            svm_name = (
                conn_ctx.get("svm_name")
                or self._default_svm_name
                or "unknown"
            )

        # Extract client IP
        client_ip = self._extract_xml_value(
            body_str,
            ["ClientIp", "ClientIP", "SourceIp", "SourceIP"],
        )

        logger.info("[Event] %s %s", operation, ontap_path)

        # NFSv3 write-complete delay
        # NOTE: This fixed delay is a fallback, not a correctness guarantee.
        # For multi-GB files, use rename-based commit, marker files, or
        # size-stability checks at the UC level instead.
        if self.write_complete_delay_sec > 0:
            time.sleep(self.write_complete_delay_sec)

        # Convert ONTAP path to S3 key
        s3_key = self.convert_ontap_path_to_s3_key(ontap_path)

        # Build FPolicy event
        fpolicy_event = {
            "event_id": str(uuid.uuid4()),
            "operation_type": self._normalize_operation(operation),
            "file_path": ontap_path,
            "volume_name": volume_name,
            "svm_name": svm_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "file_size": 0,  # Not available from FPolicy notification
        }
        if client_ip:
            fpolicy_event["client_ip"] = client_ip

        if self.mode == "realtime":
            self._send_to_sqs(fpolicy_event)
        else:
            self._write_to_log(fpolicy_event)

    def convert_ontap_path_to_s3_key(self, ontap_path: str) -> str:
        """ONTAP ファイルパスを S3 キーに変換する.

        例: /vol_name/subdir/file.txt → subdir/file.txt
        ボリュームルートプレフィックスを除去する。
        Windows パス区切り文字も変換する。
        """
        # Normalize path separators
        path = ontap_path.replace("\\", "/")

        # Remove leading volume prefix (e.g., /vol_name/ or /vol1/)
        parts = path.strip("/").split("/", 1)
        if len(parts) > 1:
            return parts[1]
        return parts[0] if parts else path.strip("/")

    # --- Private methods ---

    def _dispatch_message(
        self, conn: socket.socket, header_str: str, body_str: str,
        conn_ctx: dict[str, str],
    ) -> None:
        """メッセージタイプに応じて処理を振り分ける."""
        if "<NotfType>NEGO_REQ</NotfType>" in header_str:
            self._handle_nego_req(conn, body_str, conn_ctx)
        elif (
            "<NotfType>KEEP_ALIVE_REQ</NotfType>" in header_str
            or "<NotfType>KEEP_ALIVE</NotfType>" in header_str
        ):
            logger.info("[KeepAlive] Received — connection healthy")
        elif "<NotfType>ALERT_MSG</NotfType>" in header_str:
            alert_match = re.search(
                r"<AlertMsg>(.*?)</AlertMsg>", header_str + body_str
            )
            logger.warning(
                "[ALERT] %s",
                alert_match.group(1) if alert_match else "No message",
            )
        elif "<NotfType>NOTI_REQ</NotfType>" in header_str:
            self.handle_noti_req(body_str, conn_ctx)
        elif "<NotfType>SCREEN_REQ</NotfType>" in header_str:
            self.handle_noti_req(body_str, conn_ctx)
        elif "<NotfType>STATUS_REQ</NotfType>" in header_str:
            logger.debug("[StatusReq] Received (no response needed for async)")
        else:
            # Log unknown message types for debugging
            notf_match = re.search(r"<NotfType>(.*?)</NotfType>", header_str)
            notf_type = notf_match.group(1) if notf_match else "UNKNOWN"
            logger.info(
                "[Message] Type=%s | Header(100)=%s",
                notf_type,
                header_str[:100],
            )

    def _dispatch_protobuf_message(
        self, conn: socket.socket, raw_msg: bytes, conn_ctx: dict[str, str]
    ) -> None:
        """protobuf フォーマットのメッセージを処理する.

        protobuf メッセージは header + body の 2 部構成。
        header/body の区切りは XML と同じ b'\\n\\n' を使用する。
        """
        assert self._protobuf_parser is not None

        # Split header and body (same framing as XML)
        parts = raw_msg.split(b"\n\n", 1)
        header_bytes = parts[0]
        body_bytes = parts[1] if len(parts) > 1 else b""

        # Parse header to determine message type
        header = self._protobuf_parser.parse_header(header_bytes)
        notf_type = header.get("notf_type", "")

        if notf_type == "NEGO_REQ":
            # Parse handshake and respond (still XML response for compatibility)
            handshake = self._protobuf_parser.parse_handshake_request(body_bytes)
            session_id = handshake.get("session_id", "")
            policy_name = handshake.get("policy_name", "")
            vs_uuid = handshake.get("vs_uuid", "")
            vs_name = handshake.get("vs_name", "")

            if vs_name:
                conn_ctx["svm_name"] = vs_name
            conn_ctx["vs_uuid"] = vs_uuid
            conn_ctx["policy_name"] = policy_name

            versions = handshake.get("versions", [])
            selected_version = "1.0"
            for v in PREFERRED_VERSIONS:
                if v in versions:
                    selected_version = v
                    break

            logger.info(
                "[Handshake/PB] Policy=%s | Session=%s | VsUUID=%s",
                policy_name, session_id, vs_uuid,
            )
            self.send_nego_resp(
                conn, session_id, selected_version, vs_uuid, policy_name
            )

        elif notf_type in ("NOTI_REQ", "SCREEN_REQ"):
            self._handle_protobuf_notification(body_bytes, conn_ctx)

        elif notf_type in ("KEEP_ALIVE_REQ", "KEEP_ALIVE"):
            logger.info("[KeepAlive/PB] Received — connection healthy")

        else:
            logger.info("[Message/PB] Type=%s", notf_type)

    def _handle_protobuf_notification(
        self, body_bytes: bytes, conn_ctx: dict[str, str]
    ) -> None:
        """protobuf NOTI_REQ を処理する."""
        assert self._protobuf_parser is not None

        notification = self._protobuf_parser.parse_notification(body_bytes)

        ontap_path = notification.get("file_path", "")
        if not ontap_path:
            logger.warning("[NOTI_REQ/PB] No file_path in notification")
            return

        # Clean path
        ontap_path = ontap_path.replace("\\", "/").lstrip("/")

        operation = notification.get("operation_type", "create")
        volume_name = notification.get("volume_name", self._default_volume_name or "vol1")
        svm_name = notification.get(
            "svm_name",
            conn_ctx.get("svm_name") or self._default_svm_name or "unknown",
        )
        client_ip = notification.get("client_ip", "")

        logger.info("[Event/PB] %s %s", operation, ontap_path)

        # NFSv3 write-complete delay
        if self.write_complete_delay_sec > 0:
            time.sleep(self.write_complete_delay_sec)

        # Build FPolicy event (same format as XML path)
        fpolicy_event = {
            "event_id": str(uuid.uuid4()),
            "operation_type": self._normalize_operation(operation),
            "file_path": ontap_path,
            "volume_name": volume_name,
            "svm_name": svm_name,
            "timestamp": notification.get(
                "timestamp", datetime.now(timezone.utc).isoformat()
            ),
            "file_size": notification.get("file_size", 0),
        }
        if client_ip:
            fpolicy_event["client_ip"] = client_ip
        if notification.get("user_name"):
            fpolicy_event["user_name"] = notification["user_name"]
        if notification.get("protocol"):
            fpolicy_event["protocol"] = notification["protocol"]

        if self.mode == "realtime":
            self._send_to_sqs(fpolicy_event)
        else:
            self._write_to_log(fpolicy_event)

    def _handle_nego_req(
        self, conn: socket.socket, body_str: str, conn_ctx: dict[str, str]
    ) -> None:
        """NEGO_REQ ハンドシェイクを処理する."""
        session_match = re.search(r"<SessionId>(.*?)</SessionId>", body_str)
        policy_match = re.search(r"<PolicyName>(.*?)</PolicyName>", body_str)
        vs_uuid_match = re.search(r"<VsUUID>(.*?)</VsUUID>", body_str)

        session_id = session_match.group(1) if session_match else ""
        policy_name = policy_match.group(1) if policy_match else ""
        vs_uuid = vs_uuid_match.group(1) if vs_uuid_match else ""

        # Extract SVM name from NEGO_REQ body (if available)
        svm_match = re.search(r"<VsName>(.*?)</VsName>", body_str)
        if svm_match:
            conn_ctx["svm_name"] = svm_match.group(1)
        conn_ctx["vs_uuid"] = vs_uuid
        conn_ctx["policy_name"] = policy_name

        # Version negotiation
        vers_matches = re.findall(r"<Vers>(.*?)</Vers>", body_str)
        selected_version = "1.0"
        for v in PREFERRED_VERSIONS:
            if v in vers_matches:
                selected_version = v
                break

        logger.info(
            "[Handshake] Policy=%s | Session=%s | VsUUID=%s",
            policy_name, session_id, vs_uuid,
        )
        self.send_nego_resp(
            conn, session_id, selected_version, vs_uuid, policy_name
        )

    def _send_to_sqs(self, fpolicy_event: dict) -> None:
        """FPolicy イベントを SQS に送信する."""
        if not self.sqs_queue_url:
            logger.warning("SQS_QUEUE_URL not configured, skipping send")
            return

        try:
            message_body = json.dumps(fpolicy_event, ensure_ascii=False)
            self.sqs_client.send_message(
                QueueUrl=self.sqs_queue_url,
                MessageBody=message_body,
            )
            logger.info(
                "[SQS] Sent: %s (%s)",
                fpolicy_event["file_path"],
                fpolicy_event["operation_type"],
            )
        except Exception as e:
            logger.error("[SQS Error] %s", str(e))
            self._emit_metric("FPolicyIngestionFailures")

    def _write_to_log(self, fpolicy_event: dict) -> None:
        """FPolicy イベントを JSON Lines ログファイルに書き込む."""
        log_dir = Path(LOG_DIR)
        log_dir.mkdir(parents=True, exist_ok=True)

        today = datetime.now().strftime("%Y-%m-%d")
        log_file = log_dir / f"fpolicy_events_{today}.jsonl"

        line = json.dumps(fpolicy_event, ensure_ascii=False) + "\n"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line)

        logger.debug("[Log] Written to %s", log_file)

    def _emit_metric(self, metric_name: str, value: float = 1.0) -> None:
        """CloudWatch メトリクスを出力する."""
        try:
            self.cw_client.put_metric_data(
                Namespace="FSxN-S3AP-Patterns",
                MetricData=[
                    {
                        "MetricName": metric_name,
                        "Value": value,
                        "Unit": "Count",
                    }
                ],
            )
        except Exception as e:
            logger.warning("Failed to emit metric %s: %s", metric_name, str(e))

    @staticmethod
    def _extract_xml_value(xml_str: str, tag_names: list[str]) -> Optional[str]:
        """XML 文字列から指定タグの値を抽出する（複数タグ名フォールバック対応）.

        Args:
            xml_str: XML を含む文字列
            tag_names: 試行するタグ名のリスト（優先順）

        Returns:
            最初にマッチしたタグの内容。残留 XML タグは除去済み。
            マッチなしの場合は None。
        """
        for tag in tag_names:
            # Case-insensitive search for the tag
            match = re.search(
                rf"<{tag}>(.*?)</{tag}>",
                xml_str,
                re.IGNORECASE | re.DOTALL,
            )
            if match:
                value = match.group(1).strip()
                # Strip any nested/residual XML tags from the value
                value = re.sub(r"<[^>]+>", "", value).strip()
                if value:
                    return value
        return None

    @staticmethod
    def _normalize_operation(operation: str) -> str:
        """FPolicy 操作名を正規化する."""
        op_map = {
            "create": "create",
            "open": "create",
            "write": "write",
            "close": "write",
            "delete": "delete",
            "rename": "rename",
            "setattr": "write",
        }
        return op_map.get(operation.lower(), "create")

    @staticmethod
    def _recvall(sock: socket.socket, n: int) -> Optional[bytes]:
        """ソケットから正確に n バイト受信する."""
        data = bytearray()
        while len(data) < n:
            packet = sock.recv(n - len(data))
            if not packet:
                return None
            data.extend(packet)
        return bytes(data)


def main() -> None:
    """メインエントリポイント."""
    server = FPolicyServer()
    server.start()


if __name__ == "__main__":
    main()
