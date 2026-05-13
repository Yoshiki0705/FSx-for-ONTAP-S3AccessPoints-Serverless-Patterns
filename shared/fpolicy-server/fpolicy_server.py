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
    ) -> None:
        self.port = port
        self.sqs_queue_url = sqs_queue_url
        self.aws_region = aws_region
        self.mode = mode
        self.write_complete_delay_sec = write_complete_delay_sec
        self._sqs_client: Any = None
        self._cw_client: Any = None
        self._running = False

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
            "FPolicy Server started on port %d (mode=%s, delay=%ds)",
            self.port,
            self.mode,
            self.write_complete_delay_sec,
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
        conn.settimeout(120.0)

        try:
            while self._running:
                raw_msg = self.read_fpolicy_message(conn)
                if raw_msg is None:
                    logger.info("[-] Connection closed: %s", addr)
                    break

                header_str, body_str = self.parse_header_and_body(raw_msg)
                self._dispatch_message(conn, header_str, body_str)

        except socket.timeout:
            logger.warning("[-] Timeout: %s", addr)
        except Exception as e:
            logger.error("[Error] %s: %s", addr, str(e))
        finally:
            conn.close()

    def read_fpolicy_message(self, conn: socket.socket) -> Optional[bytes]:
        """FPolicy メッセージを TCP フレーミングに従って読み取る.

        Frame format: b'"' + 4-byte big-endian length + b'"' + payload
        """
        # Read opening quote
        while True:
            b = self._recvall(conn, 1)
            if b is None:
                return None
            if b == b'"':
                break

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

    def handle_noti_req(self, body_str: str) -> None:
        """NOTI_REQ（ファイルイベント通知）を処理する.

        非同期モード: レスポンス不要。
        """
        # Extract file path from XML
        path_match = re.search(r"<Path>(.*?)</Path>", body_str)
        if not path_match:
            # Try PathName (SCREEN_REQ format)
            path_match = re.search(r"<PathName>(.*?)</PathName>", body_str)

        if not path_match:
            logger.warning("[NOTI_REQ] No path found in body")
            return

        ontap_path = path_match.group(1)

        # Extract operation type
        op_match = re.search(r"<FileOp>(.*?)</FileOp>", body_str)
        operation = op_match.group(1).lower() if op_match else "create"

        # Extract volume name
        vol_match = re.search(r"<VolName>(.*?)</VolName>", body_str)
        volume_name = vol_match.group(1) if vol_match else "unknown"

        # Extract SVM name
        svm_match = re.search(r"<VsName>(.*?)</VsName>", body_str)
        svm_name = svm_match.group(1) if svm_match else "unknown"

        # Extract client IP
        ip_match = re.search(r"<ClientIp>(.*?)</ClientIp>", body_str)
        client_ip = ip_match.group(1) if ip_match else None

        logger.info("[Event] %s %s", operation, ontap_path)

        # NFSv3 write-complete delay
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
        self, conn: socket.socket, header_str: str, body_str: str
    ) -> None:
        """メッセージタイプに応じて処理を振り分ける."""
        if "<NotfType>NEGO_REQ</NotfType>" in header_str:
            self._handle_nego_req(conn, body_str)
        elif (
            "<NotfType>KEEP_ALIVE_REQ</NotfType>" in header_str
            or "<NotfType>KEEP_ALIVE</NotfType>" in header_str
        ):
            logger.debug("[KeepAlive] Received")
        elif "<NotfType>ALERT_MSG</NotfType>" in header_str:
            alert_match = re.search(
                r"<AlertMsg>(.*?)</AlertMsg>", header_str + body_str
            )
            logger.warning(
                "[ALERT] %s",
                alert_match.group(1) if alert_match else "No message",
            )
        elif "<NotfType>NOTI_REQ</NotfType>" in header_str:
            self.handle_noti_req(body_str)
        elif "<NotfType>SCREEN_REQ</NotfType>" in header_str:
            self.handle_noti_req(body_str)  # Same processing as NOTI_REQ
        else:
            logger.debug("[Unknown] %s", header_str[:100])

    def _handle_nego_req(self, conn: socket.socket, body_str: str) -> None:
        """NEGO_REQ ハンドシェイクを処理する."""
        session_match = re.search(r"<SessionId>(.*?)</SessionId>", body_str)
        policy_match = re.search(r"<PolicyName>(.*?)</PolicyName>", body_str)
        vs_uuid_match = re.search(r"<VsUUID>(.*?)</VsUUID>", body_str)

        session_id = session_match.group(1) if session_match else ""
        policy_name = policy_match.group(1) if policy_match else ""
        vs_uuid = vs_uuid_match.group(1) if vs_uuid_match else ""

        # Version negotiation
        vers_matches = re.findall(r"<Vers>(.*?)</Vers>", body_str)
        selected_version = "1.0"
        for v in PREFERRED_VERSIONS:
            if v in vers_matches:
                selected_version = v
                break

        logger.info(
            "[Handshake] Policy=%s | Session=%s", policy_name, session_id
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
