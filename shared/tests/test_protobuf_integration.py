"""shared/tests/test_protobuf_integration.py — ProtobufFrameReader 統合ヘルパーのユニットテスト

環境変数 PROTOBUF_FRAMING_MODE による制御と、
create_fpolicy_reader / read_fpolicy_message_v2 の動作を検証する。
"""

from __future__ import annotations

import asyncio
import os
import struct
from unittest.mock import patch

import pytest

from shared.fpolicy.protobuf_reader import FramingMode, ProtobufFrameReader
from shared.integrations.protobuf_integration import (
    ENV_PROTOBUF_FRAMING_MODE,
    create_fpolicy_reader,
    read_fpolicy_message_v2,
)


def _make_stream_reader(data: bytes) -> asyncio.StreamReader:
    """テスト用の asyncio.StreamReader を作成する。"""
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()
    return reader


class TestCreateFpolicyReader:
    """create_fpolicy_reader() のテスト。"""

    def test_returns_none_when_env_not_set(self) -> None:
        """PROTOBUF_FRAMING_MODE 未設定時は None を返す。"""
        with patch.dict(os.environ, {}, clear=True):
            # 環境変数を確実に削除
            os.environ.pop(ENV_PROTOBUF_FRAMING_MODE, None)
            stream = _make_stream_reader(b"")
            result = create_fpolicy_reader(stream)
            assert result is None

    def test_returns_none_when_env_empty(self) -> None:
        """PROTOBUF_FRAMING_MODE が空文字列の場合は None を返す。"""
        with patch.dict(os.environ, {ENV_PROTOBUF_FRAMING_MODE: ""}):
            stream = _make_stream_reader(b"")
            result = create_fpolicy_reader(stream)
            assert result is None

    def test_returns_reader_for_auto_detect(self) -> None:
        """AUTO_DETECT モードで ProtobufFrameReader を返す。"""
        with patch.dict(os.environ, {ENV_PROTOBUF_FRAMING_MODE: "AUTO_DETECT"}):
            stream = _make_stream_reader(b"")
            result = create_fpolicy_reader(stream)
            assert isinstance(result, ProtobufFrameReader)

    def test_returns_reader_for_length_prefixed(self) -> None:
        """LENGTH_PREFIXED モードで ProtobufFrameReader を返す。"""
        with patch.dict(os.environ, {ENV_PROTOBUF_FRAMING_MODE: "LENGTH_PREFIXED"}):
            stream = _make_stream_reader(b"")
            result = create_fpolicy_reader(stream)
            assert isinstance(result, ProtobufFrameReader)

    def test_returns_reader_for_frameless(self) -> None:
        """FRAMELESS モードで ProtobufFrameReader を返す。"""
        with patch.dict(os.environ, {ENV_PROTOBUF_FRAMING_MODE: "FRAMELESS"}):
            stream = _make_stream_reader(b"")
            result = create_fpolicy_reader(stream)
            assert isinstance(result, ProtobufFrameReader)

    def test_case_insensitive(self) -> None:
        """モード値は大文字小文字を区別しない。"""
        with patch.dict(os.environ, {ENV_PROTOBUF_FRAMING_MODE: "auto_detect"}):
            stream = _make_stream_reader(b"")
            result = create_fpolicy_reader(stream)
            assert isinstance(result, ProtobufFrameReader)

    def test_raises_on_invalid_mode(self) -> None:
        """無効なモード値で ValueError を raise する。"""
        with patch.dict(os.environ, {ENV_PROTOBUF_FRAMING_MODE: "INVALID_MODE"}):
            stream = _make_stream_reader(b"")
            with pytest.raises(ValueError, match="Invalid PROTOBUF_FRAMING_MODE"):
                create_fpolicy_reader(stream)

    def test_custom_max_message_size(self) -> None:
        """カスタム max_message_size が渡される。"""
        with patch.dict(os.environ, {ENV_PROTOBUF_FRAMING_MODE: "LENGTH_PREFIXED"}):
            stream = _make_stream_reader(b"")
            result = create_fpolicy_reader(stream, max_message_size=512)
            assert isinstance(result, ProtobufFrameReader)
            # ProtobufFrameReader の内部属性を確認
            assert result._max_message_size == 512


class TestReadFpolicyMessageV2:
    """read_fpolicy_message_v2() のテスト。"""

    @pytest.mark.asyncio
    async def test_with_protobuf_frame_reader(self) -> None:
        """ProtobufFrameReader が渡された場合、そのまま read_message() を使用する。"""
        payload = b"hello protobuf"
        # LENGTH_PREFIXED フォーマット: 4バイト長さ + ペイロード
        data = struct.pack(">I", len(payload)) + payload
        stream = _make_stream_reader(data)
        reader = ProtobufFrameReader(
            reader=stream, mode=FramingMode.LENGTH_PREFIXED
        )
        result = await read_fpolicy_message_v2(reader)
        assert result == payload

    @pytest.mark.asyncio
    async def test_with_stream_reader_env_set(self) -> None:
        """StreamReader + 環境変数設定時は ProtobufFrameReader を使用する。"""
        payload = b"test message"
        data = struct.pack(">I", len(payload)) + payload
        stream = _make_stream_reader(data)

        with patch.dict(
            os.environ, {ENV_PROTOBUF_FRAMING_MODE: "LENGTH_PREFIXED"}
        ):
            result = await read_fpolicy_message_v2(stream)
            assert result == payload

    @pytest.mark.asyncio
    async def test_with_stream_reader_env_not_set(self) -> None:
        """StreamReader + 環境変数未設定時はレガシーフォールバックを使用する。"""
        payload = b"legacy message"
        # レガシーフォーマット: 4バイト big-endian 長さ + ペイロード
        data = struct.pack(">I", len(payload)) + payload
        stream = _make_stream_reader(data)

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop(ENV_PROTOBUF_FRAMING_MODE, None)
            result = await read_fpolicy_message_v2(stream)
            assert result == payload

    @pytest.mark.asyncio
    async def test_eof_returns_none(self) -> None:
        """EOF 時は None を返す。"""
        stream = _make_stream_reader(b"")

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop(ENV_PROTOBUF_FRAMING_MODE, None)
            result = await read_fpolicy_message_v2(stream)
            assert result is None

    @pytest.mark.asyncio
    async def test_legacy_fallback_invalid_length(self) -> None:
        """レガシーフォールバックで無効な長さの場合は None を返す。"""
        # 長さ 0 のメッセージ
        data = struct.pack(">I", 0)
        stream = _make_stream_reader(data)

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop(ENV_PROTOBUF_FRAMING_MODE, None)
            result = await read_fpolicy_message_v2(stream)
            assert result is None

    @pytest.mark.asyncio
    async def test_frameless_mode_varint(self) -> None:
        """FRAMELESS モードで varint-delimited メッセージを読み取る。"""
        payload = b"varint msg"
        # varint エンコード: 長さ < 128 なので 1 バイト
        varint_len = len(payload).to_bytes(1, "big")  # 10 < 128
        data = varint_len + payload
        stream = _make_stream_reader(data)

        with patch.dict(os.environ, {ENV_PROTOBUF_FRAMING_MODE: "FRAMELESS"}):
            result = await read_fpolicy_message_v2(stream)
            assert result == payload
