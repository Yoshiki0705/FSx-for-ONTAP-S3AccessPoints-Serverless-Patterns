"""FPolicy protobuf message parser.

Provides protobuf deserialization for ONTAP 9.15.1+ FPolicy notifications.
Uses a lightweight wire-format decoder that doesn't require compiled .proto files,
making deployment simpler (no protoc compilation step needed).

The parser handles the protobuf wire format directly:
- Field numbers correspond to the schema in proto/fpolicy_notification.proto
- Supports varint, length-delimited (string/bytes), and fixed-width types

Configuration:
    FPOLICY_FORMAT env var: "xml" (default) or "protobuf"

Usage:
    from protobuf_parser import ProtobufParser, is_protobuf_format

    if is_protobuf_format(raw_bytes):
        parser = ProtobufParser()
        event = parser.parse_notification(raw_bytes)
"""

from __future__ import annotations

import logging
import struct
from typing import Any, Optional

logger = logging.getLogger("fpolicy-server.protobuf")

# Wire types
WIRE_VARINT = 0
WIRE_64BIT = 1
WIRE_LENGTH_DELIMITED = 2
WIRE_32BIT = 5

# Field number → field name mapping for FileOperationNotification
NOTIFICATION_FIELDS = {
    1: "file_path",
    2: "volume_name",
    3: "svm_name",
    4: "operation_type",
    5: "client_ip",
    6: "file_size",
    7: "timestamp",
    8: "user_name",
    9: "protocol",
    10: "vs_uuid",
    11: "session_id",
    12: "volume_uuid",
    13: "parent_path",
    14: "new_path",
}

# Field number → field name mapping for HandshakeRequest
HANDSHAKE_REQ_FIELDS = {
    1: "vs_uuid",
    2: "policy_name",
    3: "session_id",
    4: "versions",  # repeated
    5: "vs_name",
}

# Header fields
HEADER_FIELDS = {
    1: "notf_type",
    2: "content_len",
    3: "data_format",
    4: "session_id",
}


def is_protobuf_format(raw_bytes: bytes) -> bool:
    """Detect if a message is in protobuf format (vs XML).

    Heuristic: XML messages start with '<?xml' or '<Header>'.
    Protobuf messages start with a field tag (varint).
    """
    if not raw_bytes:
        return False
    # XML always starts with '<' (0x3C) or whitespace + '<'
    stripped = raw_bytes.lstrip(b"\x00\r\n\t ")
    if stripped.startswith(b"<") or stripped.startswith(b"<?xml"):
        return False
    # Protobuf: first byte is a field tag (field_number << 3 | wire_type)
    # Valid wire types are 0-2, 5. Field number >= 1.
    first_byte = raw_bytes[0]
    wire_type = first_byte & 0x07
    field_number = first_byte >> 3
    return wire_type in (0, 1, 2, 5) and field_number >= 1


class ProtobufDecodeError(Exception):
    """Raised when protobuf decoding fails."""

    pass


class ProtobufParser:
    """Lightweight protobuf wire-format parser for FPolicy messages.

    Decodes protobuf binary messages without requiring compiled .proto files.
    Field mappings are defined in-code based on the schema.
    """

    def parse_notification(self, data: bytes) -> dict[str, Any]:
        """Parse a FileOperationNotification protobuf message.

        Args:
            data: Raw protobuf bytes (body portion after header separation)

        Returns:
            Dict with field names and values matching the notification schema.
        """
        return self._decode_message(data, NOTIFICATION_FIELDS)

    def parse_header(self, data: bytes) -> dict[str, Any]:
        """Parse an FPolicyHeader protobuf message.

        Args:
            data: Raw protobuf bytes for the header portion

        Returns:
            Dict with header field names and values.
        """
        return self._decode_message(data, HEADER_FIELDS)

    def parse_handshake_request(self, data: bytes) -> dict[str, Any]:
        """Parse a HandshakeRequest protobuf message.

        Args:
            data: Raw protobuf bytes for the handshake body

        Returns:
            Dict with handshake field names and values.
        """
        result = {}
        offset = 0
        while offset < len(data):
            field_number, wire_type, offset = self._read_tag(data, offset)
            if field_number == 0:
                break

            field_name = HANDSHAKE_REQ_FIELDS.get(field_number)

            if wire_type == WIRE_VARINT:
                value, offset = self._read_varint(data, offset)
                if field_name:
                    result[field_name] = value
            elif wire_type == WIRE_LENGTH_DELIMITED:
                value, offset = self._read_length_delimited(data, offset)
                if field_name:
                    # Handle repeated field (versions)
                    if field_name == "versions":
                        if field_name not in result:
                            result[field_name] = []
                        result[field_name].append(
                            value.decode("utf-8", errors="replace")
                        )
                    else:
                        result[field_name] = value.decode(
                            "utf-8", errors="replace"
                        )
            elif wire_type == WIRE_64BIT:
                offset += 8
            elif wire_type == WIRE_32BIT:
                offset += 4
            else:
                raise ProtobufDecodeError(
                    f"Unknown wire type {wire_type} at offset {offset}"
                )

        return result

    def _decode_message(
        self, data: bytes, field_map: dict[int, str]
    ) -> dict[str, Any]:
        """Generic protobuf message decoder.

        Args:
            data: Raw protobuf bytes
            field_map: Mapping of field_number → field_name

        Returns:
            Dict with decoded field values.
        """
        result: dict[str, Any] = {}
        offset = 0

        while offset < len(data):
            try:
                field_number, wire_type, offset = self._read_tag(data, offset)
            except (IndexError, ProtobufDecodeError):
                break

            if field_number == 0:
                break

            field_name = field_map.get(field_number)

            try:
                if wire_type == WIRE_VARINT:
                    value, offset = self._read_varint(data, offset)
                    if field_name:
                        result[field_name] = value
                elif wire_type == WIRE_LENGTH_DELIMITED:
                    value, offset = self._read_length_delimited(data, offset)
                    if field_name:
                        result[field_name] = value.decode(
                            "utf-8", errors="replace"
                        )
                elif wire_type == WIRE_64BIT:
                    if offset + 8 <= len(data):
                        value = struct.unpack_from("<q", data, offset)[0]
                        offset += 8
                        if field_name:
                            result[field_name] = value
                    else:
                        break
                elif wire_type == WIRE_32BIT:
                    if offset + 4 <= len(data):
                        value = struct.unpack_from("<i", data, offset)[0]
                        offset += 4
                        if field_name:
                            result[field_name] = value
                    else:
                        break
                else:
                    # Unknown wire type — skip rest
                    logger.warning(
                        "Unknown wire type %d for field %d at offset %d",
                        wire_type,
                        field_number,
                        offset,
                    )
                    break
            except (IndexError, struct.error, ProtobufDecodeError):
                break

        return result

    @staticmethod
    def _read_tag(data: bytes, offset: int) -> tuple[int, int, int]:
        """Read a protobuf field tag (varint encoding).

        Returns:
            (field_number, wire_type, new_offset)
        """
        if offset >= len(data):
            return 0, 0, offset

        value = 0
        shift = 0
        while offset < len(data):
            byte = data[offset]
            offset += 1
            value |= (byte & 0x7F) << shift
            if (byte & 0x80) == 0:
                break
            shift += 7
            if shift > 63:
                raise ProtobufDecodeError("Varint too long for tag")

        wire_type = value & 0x07
        field_number = value >> 3
        return field_number, wire_type, offset

    @staticmethod
    def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
        """Read a varint value.

        Returns:
            (value, new_offset)
        """
        value = 0
        shift = 0
        while offset < len(data):
            byte = data[offset]
            offset += 1
            value |= (byte & 0x7F) << shift
            if (byte & 0x80) == 0:
                break
            shift += 7
            if shift > 63:
                raise ProtobufDecodeError("Varint too long")
        return value, offset

    @staticmethod
    def _read_length_delimited(data: bytes, offset: int) -> tuple[bytes, int]:
        """Read a length-delimited field (string, bytes, embedded message).

        Returns:
            (raw_bytes, new_offset)
        """
        # Read length as varint
        length = 0
        shift = 0
        while offset < len(data):
            byte = data[offset]
            offset += 1
            length |= (byte & 0x7F) << shift
            if (byte & 0x80) == 0:
                break
            shift += 7
            if shift > 63:
                raise ProtobufDecodeError("Length varint too long")

        if offset + length > len(data):
            raise ProtobufDecodeError(
                f"Length-delimited field extends beyond data: "
                f"need {length} bytes at offset {offset}, have {len(data) - offset}"
            )

        value = data[offset : offset + length]
        return value, offset + length


def encode_notification(event: dict[str, Any]) -> bytes:
    """Encode an FPolicy event dict to protobuf wire format.

    Used for testing and benchmarking. Encodes using the
    FileOperationNotification schema field numbers.

    Args:
        event: Dict with field names matching NOTIFICATION_FIELDS values.

    Returns:
        Protobuf-encoded bytes.
    """
    # Reverse map: field_name → field_number
    name_to_number = {v: k for k, v in NOTIFICATION_FIELDS.items()}

    parts = []
    for field_name, value in event.items():
        field_number = name_to_number.get(field_name)
        if field_number is None:
            continue

        if isinstance(value, str):
            encoded = value.encode("utf-8")
            tag = (field_number << 3) | WIRE_LENGTH_DELIMITED
            parts.append(_encode_varint(tag) + _encode_varint(len(encoded)) + encoded)
        elif isinstance(value, int):
            tag = (field_number << 3) | WIRE_VARINT
            parts.append(_encode_varint(tag) + _encode_varint(value))

    return b"".join(parts)


def _encode_varint(value: int) -> bytes:
    """Encode an integer as a protobuf varint."""
    parts = []
    while value > 0x7F:
        parts.append((value & 0x7F) | 0x80)
        value >>= 7
    parts.append(value & 0x7F)
    return bytes(parts)
