"""Tests for ProtobufFrameReader.

Tests the adaptive protobuf TCP frame reader with LENGTH_PREFIXED,
FRAMELESS, and AUTO_DETECT modes.
"""

from __future__ import annotations

import asyncio
import struct

import pytest

from shared.fpolicy.protobuf_reader import (
    FramingError,
    FramingMode,
    ProtobufFrameReader,
)


# --- Helpers ---


def _encode_varint(value: int) -> bytes:
    """Encode an integer as a protobuf varint."""
    parts = []
    while value > 0x7F:
        parts.append((value & 0x7F) | 0x80)
        value >>= 7
    parts.append(value & 0x7F)
    return bytes(parts)


def _make_length_prefixed_stream(messages: list[bytes]) -> bytes:
    """Create a LENGTH_PREFIXED stream from a list of messages."""
    stream = b""
    for msg in messages:
        stream += struct.pack(">I", len(msg)) + msg
    return stream


def _make_varint_delimited_stream(messages: list[bytes]) -> bytes:
    """Create a varint-delimited stream from a list of messages."""
    stream = b""
    for msg in messages:
        stream += _encode_varint(len(msg)) + msg
    return stream


def _make_stream_reader(data: bytes) -> asyncio.StreamReader:
    """Create an asyncio.StreamReader pre-loaded with data."""
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()
    return reader


# --- Tests: FramingMode enum ---


class TestFramingMode:
    """Test FramingMode enum values."""

    def test_length_prefixed_value(self):
        assert FramingMode.LENGTH_PREFIXED.value == "LENGTH_PREFIXED"

    def test_frameless_value(self):
        assert FramingMode.FRAMELESS.value == "FRAMELESS"

    def test_auto_detect_value(self):
        assert FramingMode.AUTO_DETECT.value == "AUTO_DETECT"


# --- Tests: FramingError ---


class TestFramingError:
    """Test FramingError exception class."""

    def test_basic_error(self):
        err = FramingError("test error")
        assert str(err) == "test error"
        assert err.offset == 0
        assert err.data == b""

    def test_error_with_offset_and_data(self):
        err = FramingError("bad frame", offset=42, data=b"\x01\x02\x03")
        assert str(err) == "bad frame"
        assert err.offset == 42
        assert err.data == b"\x01\x02\x03"


# --- Tests: LENGTH_PREFIXED mode ---


class TestLengthPrefixedMode:
    """Test LENGTH_PREFIXED framing mode."""

    @pytest.mark.asyncio
    async def test_single_message(self):
        payload = b"hello protobuf"
        stream_data = _make_length_prefixed_stream([payload])
        reader = _make_stream_reader(stream_data)

        frame_reader = ProtobufFrameReader(
            reader=reader, mode=FramingMode.LENGTH_PREFIXED
        )
        result = await frame_reader.read_message()

        assert result == payload
        assert frame_reader.messages_read == 1
        assert frame_reader.bytes_read == 4 + len(payload)

    @pytest.mark.asyncio
    async def test_multiple_messages(self):
        messages = [b"msg1", b"message two", b"third message here"]
        stream_data = _make_length_prefixed_stream(messages)
        reader = _make_stream_reader(stream_data)

        frame_reader = ProtobufFrameReader(
            reader=reader, mode=FramingMode.LENGTH_PREFIXED
        )

        results = []
        async for msg in frame_reader.read_messages():
            results.append(msg)

        assert results == messages
        assert frame_reader.messages_read == 3

    @pytest.mark.asyncio
    async def test_eof_returns_none(self):
        reader = _make_stream_reader(b"")
        frame_reader = ProtobufFrameReader(
            reader=reader, mode=FramingMode.LENGTH_PREFIXED
        )
        result = await frame_reader.read_message()
        assert result is None

    @pytest.mark.asyncio
    async def test_max_size_exceeded(self):
        # Create a message that exceeds max size
        max_size = 100
        payload = b"x" * 200
        stream_data = _make_length_prefixed_stream([payload])
        reader = _make_stream_reader(stream_data)

        frame_reader = ProtobufFrameReader(
            reader=reader,
            mode=FramingMode.LENGTH_PREFIXED,
            max_message_size=max_size,
        )

        with pytest.raises(FramingError, match="exceeds max"):
            await frame_reader.read_message()

    @pytest.mark.asyncio
    async def test_incomplete_payload_returns_none(self):
        # Header says 100 bytes but only 10 available
        header = struct.pack(">I", 100)
        stream_data = header + b"x" * 10
        reader = _make_stream_reader(stream_data)

        frame_reader = ProtobufFrameReader(
            reader=reader, mode=FramingMode.LENGTH_PREFIXED
        )
        result = await frame_reader.read_message()
        assert result is None

    @pytest.mark.asyncio
    async def test_bytes_read_accumulates(self):
        messages = [b"aaa", b"bbbbb"]
        stream_data = _make_length_prefixed_stream(messages)
        reader = _make_stream_reader(stream_data)

        frame_reader = ProtobufFrameReader(
            reader=reader, mode=FramingMode.LENGTH_PREFIXED
        )

        await frame_reader.read_message()
        assert frame_reader.bytes_read == 4 + 3

        await frame_reader.read_message()
        assert frame_reader.bytes_read == (4 + 3) + (4 + 5)


# --- Tests: FRAMELESS mode ---


class TestFramelessMode:
    """Test FRAMELESS (varint-delimited) framing mode."""

    @pytest.mark.asyncio
    async def test_single_message(self):
        payload = b"hello varint"
        stream_data = _make_varint_delimited_stream([payload])
        reader = _make_stream_reader(stream_data)

        frame_reader = ProtobufFrameReader(
            reader=reader, mode=FramingMode.FRAMELESS
        )
        result = await frame_reader.read_message()

        assert result == payload
        assert frame_reader.messages_read == 1

    @pytest.mark.asyncio
    async def test_multiple_messages(self):
        messages = [b"first", b"second", b"third"]
        stream_data = _make_varint_delimited_stream(messages)
        reader = _make_stream_reader(stream_data)

        frame_reader = ProtobufFrameReader(
            reader=reader, mode=FramingMode.FRAMELESS
        )

        results = []
        async for msg in frame_reader.read_messages():
            results.append(msg)

        assert results == messages
        assert frame_reader.messages_read == 3

    @pytest.mark.asyncio
    async def test_large_varint_length(self):
        """Test message with length requiring multi-byte varint (>127 bytes)."""
        payload = b"x" * 200
        stream_data = _make_varint_delimited_stream([payload])
        reader = _make_stream_reader(stream_data)

        frame_reader = ProtobufFrameReader(
            reader=reader, mode=FramingMode.FRAMELESS
        )
        result = await frame_reader.read_message()

        assert result == payload
        assert len(result) == 200

    @pytest.mark.asyncio
    async def test_eof_returns_none(self):
        reader = _make_stream_reader(b"")
        frame_reader = ProtobufFrameReader(
            reader=reader, mode=FramingMode.FRAMELESS
        )
        result = await frame_reader.read_message()
        assert result is None

    @pytest.mark.asyncio
    async def test_max_size_exceeded(self):
        max_size = 50
        payload = b"x" * 100
        stream_data = _make_varint_delimited_stream([payload])
        reader = _make_stream_reader(stream_data)

        frame_reader = ProtobufFrameReader(
            reader=reader,
            mode=FramingMode.FRAMELESS,
            max_message_size=max_size,
        )

        with pytest.raises(FramingError, match="exceeds max"):
            await frame_reader.read_message()

    @pytest.mark.asyncio
    async def test_bytes_read_accumulates(self):
        messages = [b"abc", b"defgh"]
        stream_data = _make_varint_delimited_stream(messages)
        reader = _make_stream_reader(stream_data)

        frame_reader = ProtobufFrameReader(
            reader=reader, mode=FramingMode.FRAMELESS
        )

        await frame_reader.read_message()
        # varint(3) = 1 byte + payload 3 bytes = 4
        assert frame_reader.bytes_read == 1 + 3

        await frame_reader.read_message()
        # varint(5) = 1 byte + payload 5 bytes = 6
        assert frame_reader.bytes_read == (1 + 3) + (1 + 5)


# --- Tests: AUTO_DETECT mode ---


class TestAutoDetectMode:
    """Test AUTO_DETECT framing mode."""

    @pytest.mark.asyncio
    async def test_detects_length_prefixed(self):
        """When first 4 bytes form a valid length, detect LENGTH_PREFIXED."""
        payload = b"hello auto-detect"
        stream_data = _make_length_prefixed_stream([payload])
        reader = _make_stream_reader(stream_data)

        frame_reader = ProtobufFrameReader(
            reader=reader, mode=FramingMode.AUTO_DETECT
        )
        result = await frame_reader.read_message()

        assert result == payload
        assert frame_reader.detected_mode == FramingMode.LENGTH_PREFIXED

    @pytest.mark.asyncio
    async def test_detects_frameless(self):
        """When first 4 bytes don't form a valid length, detect FRAMELESS."""
        # Create a varint-delimited message where the first 4 bytes
        # would form a very large uint32 (> max_message_size)
        payload = b"x" * 10
        stream_data = _make_varint_delimited_stream([payload])
        reader = _make_stream_reader(stream_data)

        # Set max_message_size low enough that the 4-byte interpretation
        # would exceed it, forcing FRAMELESS detection
        frame_reader = ProtobufFrameReader(
            reader=reader,
            mode=FramingMode.AUTO_DETECT,
            max_message_size=5_000_000,
        )
        result = await frame_reader.read_message()

        # varint for length 10 is 0x0A, followed by 10 bytes of 'x'
        # First 4 bytes: 0x0A + 3 bytes of 'x' = 0x0A787878
        # As uint32 big-endian: 176,095,352 which is > 5MB? No, 5M = 5_000_000
        # 0x0A787878 = 175,700,088 which is > 5_000_000
        # So it should detect FRAMELESS
        assert result == payload
        assert frame_reader.detected_mode == FramingMode.FRAMELESS

    @pytest.mark.asyncio
    async def test_auto_detect_eof(self):
        """EOF during auto-detect returns None."""
        reader = _make_stream_reader(b"")
        frame_reader = ProtobufFrameReader(
            reader=reader, mode=FramingMode.AUTO_DETECT
        )
        result = await frame_reader.read_message()
        assert result is None

    @pytest.mark.asyncio
    async def test_auto_detect_then_continues(self):
        """After auto-detection, subsequent reads use detected mode."""
        messages = [b"first", b"second"]
        stream_data = _make_length_prefixed_stream(messages)
        reader = _make_stream_reader(stream_data)

        frame_reader = ProtobufFrameReader(
            reader=reader, mode=FramingMode.AUTO_DETECT
        )

        results = []
        async for msg in frame_reader.read_messages():
            results.append(msg)

        assert results == messages
        assert frame_reader.detected_mode == FramingMode.LENGTH_PREFIXED
        assert frame_reader.messages_read == 2


# --- Tests: read_messages async generator ---


class TestReadMessages:
    """Test the read_messages async generator."""

    @pytest.mark.asyncio
    async def test_empty_stream(self):
        reader = _make_stream_reader(b"")
        frame_reader = ProtobufFrameReader(
            reader=reader, mode=FramingMode.LENGTH_PREFIXED
        )

        results = []
        async for msg in frame_reader.read_messages():
            results.append(msg)

        assert results == []

    @pytest.mark.asyncio
    async def test_yields_all_messages(self):
        messages = [b"a", b"bb", b"ccc", b"dddd"]
        stream_data = _make_length_prefixed_stream(messages)
        reader = _make_stream_reader(stream_data)

        frame_reader = ProtobufFrameReader(
            reader=reader, mode=FramingMode.LENGTH_PREFIXED
        )

        results = []
        async for msg in frame_reader.read_messages():
            results.append(msg)

        assert results == messages


# --- Tests: Properties ---


class TestProperties:
    """Test properties of ProtobufFrameReader."""

    @pytest.mark.asyncio
    async def test_detected_mode_before_read(self):
        reader = _make_stream_reader(b"")
        frame_reader = ProtobufFrameReader(
            reader=reader, mode=FramingMode.AUTO_DETECT
        )
        # Before any read, detected_mode returns AUTO_DETECT
        assert frame_reader.detected_mode == FramingMode.AUTO_DETECT

    @pytest.mark.asyncio
    async def test_detected_mode_explicit(self):
        reader = _make_stream_reader(b"")
        frame_reader = ProtobufFrameReader(
            reader=reader, mode=FramingMode.LENGTH_PREFIXED
        )
        assert frame_reader.detected_mode == FramingMode.LENGTH_PREFIXED

    @pytest.mark.asyncio
    async def test_messages_read_starts_at_zero(self):
        reader = _make_stream_reader(b"")
        frame_reader = ProtobufFrameReader(reader=reader)
        assert frame_reader.messages_read == 0

    @pytest.mark.asyncio
    async def test_bytes_read_starts_at_zero(self):
        reader = _make_stream_reader(b"")
        frame_reader = ProtobufFrameReader(reader=reader)
        assert frame_reader.bytes_read == 0
