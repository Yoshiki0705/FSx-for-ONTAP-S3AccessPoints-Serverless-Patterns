"""Protobuf Frame Reader プロパティベーステスト.

Property 7: LENGTH_PREFIXED Round-Trip
  - 4バイト長さプレフィックスでエンコードしたメッセージが正確に復元される
Property 8: FRAMELESS Round-Trip
  - varint-delimited でエンコードしたメッセージが正確に復元される
Property 9: Max Size Enforcement
  - max_message_size を超えるメッセージで FramingError が raise される
Property 10: Counter Accuracy
  - messages_read と bytes_read が正確にカウントされる

**Validates: Requirements 6.2, 6.3, 6.4, 6.7**
"""

from __future__ import annotations

import asyncio
import struct

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from shared.fpolicy.protobuf_reader import (
    FramingError,
    FramingMode,
    ProtobufFrameReader,
)


# --- Helpers ---


def _encode_varint(value: int) -> bytes:
    """Encode an integer as a protobuf varint (unsigned)."""
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


async def _read_all_messages(frame_reader: ProtobufFrameReader) -> list[bytes]:
    """Read all messages from a ProtobufFrameReader."""
    messages = []
    async for msg in frame_reader.read_messages():
        messages.append(msg)
    return messages


# --- Hypothesis Strategies ---

# Message payload: non-empty binary data (1 to 1000 bytes)
message_payload_strategy = st.binary(min_size=1, max_size=1000)

# List of message payloads (1 to 10 messages)
message_list_strategy = st.lists(
    st.binary(min_size=1, max_size=500),
    min_size=1,
    max_size=10,
)

# Larger single message (up to max_message_size boundary)
large_message_strategy = st.binary(min_size=1, max_size=4096)


# --- Property 7: LENGTH_PREFIXED Round-Trip ---


class TestLengthPrefixedRoundTrip:
    """Property 7: Protobuf LENGTH_PREFIXED Round-Trip.

    **Validates: Requirements 6.2**

    任意のバイト列メッセージを 4バイト big-endian 長さプレフィックスで
    エンコードしたストリームから、元のメッセージを正確に復元できることを検証する。
    """

    @pytest.mark.property
    @given(message=message_payload_strategy)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_single_message_round_trip(self, message: bytes):
        """単一メッセージの LENGTH_PREFIXED ラウンドトリップ."""
        stream_data = _make_length_prefixed_stream([message])
        reader = _make_stream_reader(stream_data)

        frame_reader = ProtobufFrameReader(
            reader=reader,
            mode=FramingMode.LENGTH_PREFIXED,
            max_message_size=len(message) + 1,
        )

        result = asyncio.get_event_loop().run_until_complete(
            frame_reader.read_message()
        )

        assert result == message, (
            f"Round-trip failed: sent {len(message)} bytes, "
            f"got {len(result) if result else 'None'} bytes"
        )

    @pytest.mark.property
    @given(messages=message_list_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_multiple_messages_round_trip(self, messages: list[bytes]):
        """複数メッセージの LENGTH_PREFIXED ラウンドトリップ."""
        max_size = max(len(m) for m in messages) + 1
        stream_data = _make_length_prefixed_stream(messages)
        reader = _make_stream_reader(stream_data)

        frame_reader = ProtobufFrameReader(
            reader=reader,
            mode=FramingMode.LENGTH_PREFIXED,
            max_message_size=max_size,
        )

        results = asyncio.get_event_loop().run_until_complete(
            _read_all_messages(frame_reader)
        )

        assert results == messages, (
            f"Round-trip failed: sent {len(messages)} messages, "
            f"got {len(results)} messages"
        )
        assert frame_reader.messages_read == len(messages)

    @pytest.mark.property
    @given(messages=message_list_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_bytes_read_equals_stream_length(self, messages: list[bytes]):
        """bytes_read がストリーム全体の長さと一致する."""
        stream_data = _make_length_prefixed_stream(messages)
        max_size = max(len(m) for m in messages) + 1
        reader = _make_stream_reader(stream_data)

        frame_reader = ProtobufFrameReader(
            reader=reader,
            mode=FramingMode.LENGTH_PREFIXED,
            max_message_size=max_size,
        )

        asyncio.get_event_loop().run_until_complete(
            _read_all_messages(frame_reader)
        )

        expected_bytes = sum(4 + len(m) for m in messages)
        assert frame_reader.bytes_read == expected_bytes, (
            f"Expected bytes_read={expected_bytes}, got {frame_reader.bytes_read}"
        )

    @pytest.mark.property
    @given(message=message_payload_strategy)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_message_count_increments_correctly(self, message: bytes):
        """messages_read が正確にインクリメントされる."""
        # Create stream with 3 copies of the same message
        messages = [message, message, message]
        stream_data = _make_length_prefixed_stream(messages)
        max_size = len(message) + 1
        reader = _make_stream_reader(stream_data)

        frame_reader = ProtobufFrameReader(
            reader=reader,
            mode=FramingMode.LENGTH_PREFIXED,
            max_message_size=max_size,
        )

        asyncio.get_event_loop().run_until_complete(
            _read_all_messages(frame_reader)
        )

        assert frame_reader.messages_read == 3


# --- Property 8: FRAMELESS Round-Trip ---


class TestFramelessRoundTrip:
    """Property 8: Protobuf FRAMELESS Round-Trip.

    **Validates: Requirements 6.3**

    任意のバイト列メッセージを varint-delimited でエンコードしたストリームから、
    元のメッセージを正確に復元できることを検証する。
    """

    @pytest.mark.property
    @given(message=message_payload_strategy)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_single_message_round_trip(self, message: bytes):
        """単一メッセージの FRAMELESS (varint-delimited) ラウンドトリップ."""
        stream_data = _make_varint_delimited_stream([message])
        reader = _make_stream_reader(stream_data)

        frame_reader = ProtobufFrameReader(
            reader=reader,
            mode=FramingMode.FRAMELESS,
            max_message_size=len(message) + 1,
        )

        result = asyncio.get_event_loop().run_until_complete(
            frame_reader.read_message()
        )

        assert result == message, (
            f"Round-trip failed: sent {len(message)} bytes, "
            f"got {len(result) if result else 'None'} bytes"
        )

    @pytest.mark.property
    @given(messages=message_list_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_multiple_messages_round_trip(self, messages: list[bytes]):
        """複数メッセージの FRAMELESS ラウンドトリップ."""
        max_size = max(len(m) for m in messages) + 1
        stream_data = _make_varint_delimited_stream(messages)
        reader = _make_stream_reader(stream_data)

        frame_reader = ProtobufFrameReader(
            reader=reader,
            mode=FramingMode.FRAMELESS,
            max_message_size=max_size,
        )

        results = asyncio.get_event_loop().run_until_complete(
            _read_all_messages(frame_reader)
        )

        assert results == messages, (
            f"Round-trip failed: sent {len(messages)} messages, "
            f"got {len(results)} messages"
        )
        assert frame_reader.messages_read == len(messages)

    @pytest.mark.property
    @given(messages=message_list_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_bytes_read_equals_stream_length(self, messages: list[bytes]):
        """bytes_read がストリーム全体の長さと一致する."""
        stream_data = _make_varint_delimited_stream(messages)
        max_size = max(len(m) for m in messages) + 1
        reader = _make_stream_reader(stream_data)

        frame_reader = ProtobufFrameReader(
            reader=reader,
            mode=FramingMode.FRAMELESS,
            max_message_size=max_size,
        )

        asyncio.get_event_loop().run_until_complete(
            _read_all_messages(frame_reader)
        )

        expected_bytes = sum(len(_encode_varint(len(m))) + len(m) for m in messages)
        assert frame_reader.bytes_read == expected_bytes, (
            f"Expected bytes_read={expected_bytes}, got {frame_reader.bytes_read}"
        )

    @pytest.mark.property
    @given(
        message=st.binary(min_size=128, max_size=1000),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_large_varint_round_trip(self, message: bytes):
        """128バイト以上のメッセージ（マルチバイト varint）のラウンドトリップ."""
        # Messages >= 128 bytes require multi-byte varint encoding
        stream_data = _make_varint_delimited_stream([message])
        reader = _make_stream_reader(stream_data)

        frame_reader = ProtobufFrameReader(
            reader=reader,
            mode=FramingMode.FRAMELESS,
            max_message_size=len(message) + 1,
        )

        result = asyncio.get_event_loop().run_until_complete(
            frame_reader.read_message()
        )

        assert result == message
        # Verify varint was multi-byte
        varint_len = len(_encode_varint(len(message)))
        assert varint_len >= 2, (
            f"Expected multi-byte varint for {len(message)} bytes, "
            f"got {varint_len}-byte varint"
        )

    @pytest.mark.property
    @given(
        messages=st.lists(
            st.binary(min_size=1, max_size=300),
            min_size=2,
            max_size=8,
        ),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_message_ordering_preserved(self, messages: list[bytes]):
        """メッセージの順序が保持される."""
        max_size = max(len(m) for m in messages) + 1
        stream_data = _make_varint_delimited_stream(messages)
        reader = _make_stream_reader(stream_data)

        frame_reader = ProtobufFrameReader(
            reader=reader,
            mode=FramingMode.FRAMELESS,
            max_message_size=max_size,
        )

        results = asyncio.get_event_loop().run_until_complete(
            _read_all_messages(frame_reader)
        )

        for i, (expected, actual) in enumerate(zip(messages, results)):
            assert expected == actual, (
                f"Message {i} mismatch: expected {len(expected)} bytes, "
                f"got {len(actual)} bytes"
            )



# --- Property 9: Max Size Enforcement ---


class TestMaxSizeEnforcement:
    """Property 9: Protobuf Max Size Enforcement.

    **Validates: Requirements 6.4**

    max_message_size を超えるメッセージで FramingError が raise されることを検証する。
    LENGTH_PREFIXED と FRAMELESS の両モードで検証する。
    """

    @pytest.mark.property
    @given(
        max_size=st.integers(min_value=10, max_value=500),
        excess=st.integers(min_value=1, max_value=500),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_length_prefixed_oversized_raises_framing_error(
        self, max_size: int, excess: int
    ):
        """LENGTH_PREFIXED: max_message_size 超過で FramingError が raise される."""
        message_size = max_size + excess
        # Create a stream with a length header indicating oversized message
        stream_data = struct.pack(">I", message_size) + b"\x00" * message_size
        reader = _make_stream_reader(stream_data)

        frame_reader = ProtobufFrameReader(
            reader=reader,
            mode=FramingMode.LENGTH_PREFIXED,
            max_message_size=max_size,
        )

        with pytest.raises(FramingError) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                frame_reader.read_message()
            )

        assert "exceeds max" in str(exc_info.value).lower() or "exceeds" in str(exc_info.value)

    @pytest.mark.property
    @given(
        max_size=st.integers(min_value=10, max_value=500),
        excess=st.integers(min_value=1, max_value=500),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_frameless_oversized_raises_framing_error(
        self, max_size: int, excess: int
    ):
        """FRAMELESS: max_message_size 超過で FramingError が raise される."""
        message_size = max_size + excess
        # Create a varint-delimited stream with oversized message length
        stream_data = _encode_varint(message_size) + b"\x00" * message_size
        reader = _make_stream_reader(stream_data)

        frame_reader = ProtobufFrameReader(
            reader=reader,
            mode=FramingMode.FRAMELESS,
            max_message_size=max_size,
        )

        with pytest.raises(FramingError) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                frame_reader.read_message()
            )

        assert "exceeds max" in str(exc_info.value).lower() or "exceeds" in str(exc_info.value)

    @pytest.mark.property
    @given(
        message=st.binary(min_size=1, max_size=100),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_within_limit_does_not_raise(self, message: bytes):
        """max_message_size 以内のメッセージでは FramingError が raise されない."""
        max_size = len(message) + 1  # Just above message size
        stream_data = _make_length_prefixed_stream([message])
        reader = _make_stream_reader(stream_data)

        frame_reader = ProtobufFrameReader(
            reader=reader,
            mode=FramingMode.LENGTH_PREFIXED,
            max_message_size=max_size,
        )

        result = asyncio.get_event_loop().run_until_complete(
            frame_reader.read_message()
        )

        assert result == message  # No error, message read successfully


# --- Property 10: Counter Accuracy ---


class TestCounterAccuracy:
    """Property 10: Protobuf Counter Accuracy.

    **Validates: Requirements 6.7**

    全メッセージ読み取り後、messages_read がメッセージ数と一致し、
    bytes_read が消費した総バイト数と一致することを検証する。
    """

    @pytest.mark.property
    @given(messages=message_list_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_length_prefixed_counter_accuracy(self, messages: list[bytes]):
        """LENGTH_PREFIXED: messages_read と bytes_read が正確."""
        max_size = max(len(m) for m in messages) + 1
        stream_data = _make_length_prefixed_stream(messages)
        reader = _make_stream_reader(stream_data)

        frame_reader = ProtobufFrameReader(
            reader=reader,
            mode=FramingMode.LENGTH_PREFIXED,
            max_message_size=max_size,
        )

        asyncio.get_event_loop().run_until_complete(
            _read_all_messages(frame_reader)
        )

        # messages_read must equal message count
        assert frame_reader.messages_read == len(messages), (
            f"messages_read={frame_reader.messages_read}, expected={len(messages)}"
        )

        # bytes_read must equal total consumed bytes (4-byte header + payload per message)
        expected_bytes = sum(4 + len(m) for m in messages)
        assert frame_reader.bytes_read == expected_bytes, (
            f"bytes_read={frame_reader.bytes_read}, expected={expected_bytes}"
        )

    @pytest.mark.property
    @given(messages=message_list_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_frameless_counter_accuracy(self, messages: list[bytes]):
        """FRAMELESS: messages_read と bytes_read が正確."""
        max_size = max(len(m) for m in messages) + 1
        stream_data = _make_varint_delimited_stream(messages)
        reader = _make_stream_reader(stream_data)

        frame_reader = ProtobufFrameReader(
            reader=reader,
            mode=FramingMode.FRAMELESS,
            max_message_size=max_size,
        )

        asyncio.get_event_loop().run_until_complete(
            _read_all_messages(frame_reader)
        )

        # messages_read must equal message count
        assert frame_reader.messages_read == len(messages), (
            f"messages_read={frame_reader.messages_read}, expected={len(messages)}"
        )

        # bytes_read must equal total consumed bytes (varint header + payload per message)
        expected_bytes = sum(len(_encode_varint(len(m))) + len(m) for m in messages)
        assert frame_reader.bytes_read == expected_bytes, (
            f"bytes_read={frame_reader.bytes_read}, expected={expected_bytes}"
        )

    @pytest.mark.property
    @given(
        messages=st.lists(
            st.binary(min_size=1, max_size=200),
            min_size=1,
            max_size=5,
        ),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_counters_start_at_zero(self, messages: list[bytes]):
        """カウンターは初期状態で 0."""
        max_size = max(len(m) for m in messages) + 1
        stream_data = _make_length_prefixed_stream(messages)
        reader = _make_stream_reader(stream_data)

        frame_reader = ProtobufFrameReader(
            reader=reader,
            mode=FramingMode.LENGTH_PREFIXED,
            max_message_size=max_size,
        )

        # Before reading, counters should be 0
        assert frame_reader.messages_read == 0
        assert frame_reader.bytes_read == 0

        # Read one message
        asyncio.get_event_loop().run_until_complete(
            frame_reader.read_message()
        )

        # After reading one message
        assert frame_reader.messages_read == 1
        assert frame_reader.bytes_read == 4 + len(messages[0])
