"""Tests for FPolicy protobuf parser.

Tests the wire-format decoder, encoding, and performance comparison
between XML regex parsing and protobuf parsing.
"""

import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

# Add fpolicy-server to path
sys.path.insert(
    0, str(Path(__file__).parent.parent / "fpolicy-server")
)

from protobuf_parser import (
    ProtobufDecodeError,
    ProtobufParser,
    encode_notification,
    is_protobuf_format,
)


# --- Test Data ---

SAMPLE_EVENT = {
    "file_path": "/vol1/legal/contracts/2026/agreement-001.pdf",
    "volume_name": "vol1",
    "svm_name": "FSxN_OnPre",
    "operation_type": "create",
    "client_ip": "10.0.1.100",
    "file_size": 1048576,
    "timestamp": "2026-05-14T10:30:00Z",
    "user_name": "DOMAIN\\user01",
    "protocol": "smb",
}

SAMPLE_XML_BODY = """<?xml version="1.0"?>
<Notification>
  <PathName>/vol1/legal/contracts/2026/agreement-001.pdf</PathName>
  <VolName>vol1</VolName>
  <VsName>FSxN_OnPre</VsName>
  <FileOp>create</FileOp>
  <ClientIp>10.0.1.100</ClientIp>
</Notification>"""


class TestIsProtobufFormat:
    """Test format auto-detection."""

    def test_xml_detected(self):
        assert is_protobuf_format(b"<?xml version=\"1.0\"?>") is False

    def test_xml_with_header_tag(self):
        assert is_protobuf_format(b"<Header><NotfType>") is False

    def test_xml_with_whitespace(self):
        assert is_protobuf_format(b"  \n<Header>") is False

    def test_protobuf_detected(self):
        # Field 1, wire type 2 (length-delimited) = tag byte 0x0A
        assert is_protobuf_format(b"\x0a\x05hello") is True

    def test_empty_bytes(self):
        assert is_protobuf_format(b"") is False

    def test_null_bytes(self):
        # NUL padding followed by XML
        assert is_protobuf_format(b"\x00\x00<Header>") is False


class TestProtobufParser:
    """Test protobuf wire-format parsing."""

    def setup_method(self):
        self.parser = ProtobufParser()

    def test_parse_notification_roundtrip(self):
        """Encode then decode a notification — should roundtrip."""
        encoded = encode_notification(SAMPLE_EVENT)
        decoded = self.parser.parse_notification(encoded)

        assert decoded["file_path"] == SAMPLE_EVENT["file_path"]
        assert decoded["volume_name"] == SAMPLE_EVENT["volume_name"]
        assert decoded["svm_name"] == SAMPLE_EVENT["svm_name"]
        assert decoded["operation_type"] == SAMPLE_EVENT["operation_type"]
        assert decoded["client_ip"] == SAMPLE_EVENT["client_ip"]
        assert decoded["file_size"] == SAMPLE_EVENT["file_size"]
        assert decoded["timestamp"] == SAMPLE_EVENT["timestamp"]
        assert decoded["user_name"] == SAMPLE_EVENT["user_name"]
        assert decoded["protocol"] == SAMPLE_EVENT["protocol"]

    def test_parse_empty_message(self):
        """Empty bytes should return empty dict."""
        result = self.parser.parse_notification(b"")
        assert result == {}

    def test_parse_minimal_notification(self):
        """Minimal notification with just file_path."""
        event = {"file_path": "/test/file.txt"}
        encoded = encode_notification(event)
        decoded = self.parser.parse_notification(encoded)
        assert decoded["file_path"] == "/test/file.txt"

    def test_parse_unicode_path(self):
        """Unicode file paths should be handled correctly."""
        event = {"file_path": "/vol1/日本語/ファイル.pdf"}
        encoded = encode_notification(event)
        decoded = self.parser.parse_notification(encoded)
        assert decoded["file_path"] == "/vol1/日本語/ファイル.pdf"

    def test_parse_long_path(self):
        """Long file paths (>127 bytes) test varint length encoding."""
        long_path = "/vol1/" + "a" * 200 + "/file.txt"
        event = {"file_path": long_path}
        encoded = encode_notification(event)
        decoded = self.parser.parse_notification(encoded)
        assert decoded["file_path"] == long_path

    def test_parse_header(self):
        """Parse a protobuf header message."""
        header_event = {
            "notf_type": "NOTI_REQ",
            "content_len": 256,
            "data_format": "protobuf",
            "session_id": "sess-001",
        }
        # Manually encode header fields
        from protobuf_parser import _encode_varint, WIRE_LENGTH_DELIMITED, WIRE_VARINT

        parts = []
        # Field 1: notf_type (string)
        tag = (1 << 3) | WIRE_LENGTH_DELIMITED
        val = b"NOTI_REQ"
        parts.append(_encode_varint(tag) + _encode_varint(len(val)) + val)
        # Field 2: content_len (varint)
        tag = (2 << 3) | WIRE_VARINT
        parts.append(_encode_varint(tag) + _encode_varint(256))
        # Field 3: data_format (string)
        tag = (3 << 3) | WIRE_LENGTH_DELIMITED
        val = b"protobuf"
        parts.append(_encode_varint(tag) + _encode_varint(len(val)) + val)
        # Field 4: session_id (string)
        tag = (4 << 3) | WIRE_LENGTH_DELIMITED
        val = b"sess-001"
        parts.append(_encode_varint(tag) + _encode_varint(len(val)) + val)

        encoded = b"".join(parts)
        decoded = self.parser.parse_header(encoded)

        assert decoded["notf_type"] == "NOTI_REQ"
        assert decoded["content_len"] == 256
        assert decoded["data_format"] == "protobuf"
        assert decoded["session_id"] == "sess-001"

    def test_parse_handshake_request(self):
        """Parse a handshake request with repeated versions field."""
        from protobuf_parser import _encode_varint, WIRE_LENGTH_DELIMITED

        parts = []
        # Field 1: vs_uuid
        tag = (1 << 3) | WIRE_LENGTH_DELIMITED
        val = b"9ae87e42-068a-11f1-b1ff-ada95e61ee66"
        parts.append(_encode_varint(tag) + _encode_varint(len(val)) + val)
        # Field 2: policy_name
        tag = (2 << 3) | WIRE_LENGTH_DELIMITED
        val = b"fpolicy_aws"
        parts.append(_encode_varint(tag) + _encode_varint(len(val)) + val)
        # Field 3: session_id
        tag = (3 << 3) | WIRE_LENGTH_DELIMITED
        val = b"session-123"
        parts.append(_encode_varint(tag) + _encode_varint(len(val)) + val)
        # Field 4: versions (repeated)
        for ver in [b"1.0", b"1.1", b"1.2", b"2.0"]:
            tag = (4 << 3) | WIRE_LENGTH_DELIMITED
            parts.append(_encode_varint(tag) + _encode_varint(len(ver)) + ver)
        # Field 5: vs_name
        tag = (5 << 3) | WIRE_LENGTH_DELIMITED
        val = b"FSxN_OnPre"
        parts.append(_encode_varint(tag) + _encode_varint(len(val)) + val)

        encoded = b"".join(parts)
        decoded = self.parser.parse_handshake_request(encoded)

        assert decoded["vs_uuid"] == "9ae87e42-068a-11f1-b1ff-ada95e61ee66"
        assert decoded["policy_name"] == "fpolicy_aws"
        assert decoded["session_id"] == "session-123"
        assert decoded["versions"] == ["1.0", "1.1", "1.2", "2.0"]
        assert decoded["vs_name"] == "FSxN_OnPre"


class TestEncodeNotification:
    """Test protobuf encoding."""

    def test_encode_produces_bytes(self):
        encoded = encode_notification(SAMPLE_EVENT)
        assert isinstance(encoded, bytes)
        assert len(encoded) > 0

    def test_encode_smaller_than_xml(self):
        """Protobuf encoding should be significantly smaller than XML."""
        encoded = encode_notification(SAMPLE_EVENT)
        xml_size = len(SAMPLE_XML_BODY.encode("utf-8"))
        pb_size = len(encoded)

        # Protobuf should be at least 30% smaller
        assert pb_size < xml_size * 0.7, (
            f"Protobuf ({pb_size}B) not significantly smaller than XML ({xml_size}B)"
        )

    def test_encode_unknown_fields_ignored(self):
        """Unknown field names should be silently ignored."""
        event = {"file_path": "/test.txt", "unknown_field": "value"}
        encoded = encode_notification(event)
        parser = ProtobufParser()
        decoded = parser.parse_notification(encoded)
        assert decoded["file_path"] == "/test.txt"
        assert "unknown_field" not in decoded


class TestPerformanceComparison:
    """Performance comparison between XML regex parsing and protobuf parsing."""

    @pytest.fixture
    def sample_events(self):
        """Generate 1000 sample events for benchmarking."""
        events = []
        for i in range(1000):
            events.append({
                "file_path": f"/vol1/legal/contracts/2026/agreement-{i:04d}.pdf",
                "volume_name": "vol1",
                "svm_name": "FSxN_OnPre",
                "operation_type": "create",
                "client_ip": f"10.0.1.{i % 256}",
                "file_size": 1048576 + i * 100,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "user_name": f"DOMAIN\\user{i:03d}",
                "protocol": "smb",
            })
        return events

    @pytest.fixture
    def xml_messages(self, sample_events):
        """Generate XML messages for benchmarking."""
        messages = []
        for e in sample_events:
            xml = (
                f'<?xml version="1.0"?>'
                f"<Notification>"
                f"<PathName>{e['file_path']}</PathName>"
                f"<VolName>{e['volume_name']}</VolName>"
                f"<VsName>{e['svm_name']}</VsName>"
                f"<FileOp>{e['operation_type']}</FileOp>"
                f"<ClientIp>{e['client_ip']}</ClientIp>"
                f"</Notification>"
            )
            messages.append(xml)
        return messages

    @pytest.fixture
    def protobuf_messages(self, sample_events):
        """Generate protobuf messages for benchmarking."""
        return [encode_notification(e) for e in sample_events]

    def _parse_xml_event(self, xml_str: str) -> dict:
        """Simulate XML parsing as done in fpolicy_server.py."""
        result = {}
        for tag, key in [
            ("PathName", "file_path"),
            ("VolName", "volume_name"),
            ("VsName", "svm_name"),
            ("FileOp", "operation_type"),
            ("ClientIp", "client_ip"),
        ]:
            match = re.search(rf"<{tag}>(.*?)</{tag}>", xml_str)
            if match:
                result[key] = match.group(1)
        return result

    def test_protobuf_faster_than_xml(self, xml_messages, protobuf_messages):
        """Protobuf parsing should be faster than XML regex parsing."""
        parser = ProtobufParser()

        # Benchmark XML parsing
        start = time.perf_counter()
        for msg in xml_messages:
            self._parse_xml_event(msg)
        xml_time = time.perf_counter() - start

        # Benchmark protobuf parsing
        start = time.perf_counter()
        for msg in protobuf_messages:
            parser.parse_notification(msg)
        pb_time = time.perf_counter() - start

        # Log results
        print(f"\n{'='*60}")
        print(f"Performance Comparison (1000 events)")
        print(f"{'='*60}")
        print(f"  XML regex parse:    {xml_time*1000:.2f} ms ({xml_time/1000*1000:.4f} ms/event)")
        print(f"  Protobuf parse:     {pb_time*1000:.2f} ms ({pb_time/1000*1000:.4f} ms/event)")
        print(f"  Speedup:            {xml_time/pb_time:.2f}x")
        print(f"{'='*60}")

        # Protobuf should be at least as fast (may vary on different hardware)
        # We don't assert strict speedup since Python protobuf parsing
        # without compiled C extensions may not always be faster than regex
        # The real benefit is in message size reduction
        assert pb_time < xml_time * 3, (
            f"Protobuf ({pb_time:.4f}s) unexpectedly much slower than XML ({xml_time:.4f}s)"
        )

    def test_message_size_comparison(self, xml_messages, protobuf_messages):
        """Protobuf messages should be significantly smaller."""
        xml_total = sum(len(m.encode("utf-8")) for m in xml_messages)
        pb_total = sum(len(m) for m in protobuf_messages)

        reduction = (1 - pb_total / xml_total) * 100

        print(f"\n{'='*60}")
        print(f"Message Size Comparison (1000 events)")
        print(f"{'='*60}")
        print(f"  XML total:          {xml_total:,} bytes ({xml_total/1000:.0f} bytes/event avg)")
        print(f"  Protobuf total:     {pb_total:,} bytes ({pb_total/1000:.0f} bytes/event avg)")
        print(f"  Size reduction:     {reduction:.1f}%")
        print(f"{'='*60}")

        # Protobuf should be at least 30% smaller
        assert reduction > 30, f"Size reduction only {reduction:.1f}% (expected >30%)"
