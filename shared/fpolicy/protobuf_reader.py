"""shared.fpolicy.protobuf_reader — Protobuf TCP Frame Reader

Phase 11 で実装した read_fpolicy_message() を frameless protobuf ワイヤーフォーマットに
対応させるアダプティブリーダー。NetApp FPolicy サーバーが送信する protobuf メッセージの
TCP フレーミング方式（LENGTH_PREFIXED / FRAMELESS）を自動検出し、正しくパースする。

設計方針:
- AUTO_DETECT: 最初の数バイトを検査し、length-prefixed か frameless かを判定
- LENGTH_PREFIXED: 4バイト big-endian 長さヘッダー → ペイロード読み取り
- FRAMELESS: varint-delimited protobuf メッセージの境界検出
- メッセージサイズ上限の強制（DoS 防止）
- 不正フレームデータに対する堅牢なエラーハンドリング

Usage:
    from shared.fpolicy.protobuf_reader import ProtobufFrameReader, FramingMode

    reader = ProtobufFrameReader(
        reader=stream_reader,
        mode=FramingMode.AUTO_DETECT,
        max_message_size=1_048_576,
    )
    async for message in reader.read_messages():
        process(message)
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from enum import Enum

logger = logging.getLogger(__name__)


class FramingMode(Enum):
    """protobuf メッセージのフレーミング方式。"""

    LENGTH_PREFIXED = "LENGTH_PREFIXED"  # 4-byte big-endian length header
    FRAMELESS = "FRAMELESS"  # Delimited protobuf (varint-prefixed)
    AUTO_DETECT = "AUTO_DETECT"  # Probe first bytes to determine mode


class FramingError(Exception):
    """フレーミング処理中のエラー。

    不正なフレームデータ、サイズ超過、プロトコル違反時に raise される。
    """

    def __init__(self, message: str, offset: int = 0, data: bytes = b"") -> None:
        super().__init__(message)
        self.offset = offset
        self.data = data


class ProtobufFrameReader:
    """アダプティブ protobuf TCP フレームリーダー。

    AUTO_DETECT モードでは最初のメッセージ読み取り時にフレーミング方式を自動判定する。
    LENGTH_PREFIXED と FRAMELESS の両方式に対応し、堅牢なエラーハンドリングを提供する。

    Args:
        reader: asyncio.StreamReader インスタンス
        mode: フレーミングモード（デフォルト: AUTO_DETECT）
        max_message_size: メッセージサイズ上限（バイト、デフォルト: 1MB）
    """

    def __init__(
        self,
        reader: asyncio.StreamReader,
        mode: FramingMode = FramingMode.AUTO_DETECT,
        max_message_size: int = 1_048_576,  # 1 MB
    ) -> None:
        self._reader = reader
        self._mode = mode
        self._detected_mode: FramingMode | None = (
            mode if mode != FramingMode.AUTO_DETECT else None
        )
        self._max_message_size = max_message_size
        self._messages_read: int = 0
        self._bytes_read: int = 0
        self._buffer: bytes = b""

    @property
    def _effective_mode(self) -> FramingMode | None:
        """現在有効なフレーミングモードを返す。"""
        if self._mode == FramingMode.AUTO_DETECT:
            return self._detected_mode
        return self._mode

    async def read_message(self) -> bytes | None:
        """ストリームから次の完全な protobuf メッセージを読み取る。

        Returns:
            メッセージバイト列。EOF/コネクションクローズ時は None。

        Raises:
            FramingError: 不正なフレームデータまたはサイズ超過時
        """
        try:
            if self._mode == FramingMode.AUTO_DETECT and self._detected_mode is None:
                return await self._auto_detect_and_read()
            elif self._effective_mode == FramingMode.LENGTH_PREFIXED:
                return await self._read_length_prefixed()
            else:  # FRAMELESS
                return await self._read_varint_delimited()
        except asyncio.IncompleteReadError:
            return None
        except FramingError:
            raise
        except Exception as e:
            logger.error("Unexpected error reading protobuf frame: %s", e)
            return None

    async def read_messages(self) -> AsyncIterator[bytes]:
        """protobuf メッセージを yield する非同期ジェネレータ。

        Yields:
            各メッセージのバイト列

        Raises:
            FramingError: 不正なフレームデータまたはサイズ超過時
        """
        while True:
            message = await self.read_message()
            if message is None:
                return
            yield message

    async def _read_bytes(self, n: int) -> bytes:
        """内部バッファとストリームから n バイトを正確に読み取る。

        バッファにデータがあればそこから優先的に消費し、
        不足分をストリームから読み取る。

        Raises:
            asyncio.IncompleteReadError: 十分なデータがない場合
        """
        if not self._buffer:
            return await self._reader.readexactly(n)

        if len(self._buffer) >= n:
            result = self._buffer[:n]
            self._buffer = self._buffer[n:]
            return result

        # バッファの残り + ストリームから不足分を読み取る
        result = self._buffer
        remaining = n - len(self._buffer)
        self._buffer = b""
        try:
            rest = await self._reader.readexactly(remaining)
        except asyncio.IncompleteReadError as e:
            raise asyncio.IncompleteReadError(result + e.partial, n)
        return result + rest

    async def _read_one_byte(self) -> bytes | None:
        """内部バッファまたはストリームから 1 バイトを読み取る。

        Returns:
            1 バイトの bytes。EOF 時は None。
        """
        if self._buffer:
            b = self._buffer[:1]
            self._buffer = self._buffer[1:]
            return b
        try:
            return await self._reader.readexactly(1)
        except asyncio.IncompleteReadError:
            return None

    async def _auto_detect_and_read(self) -> bytes | None:
        """最初の数バイトを検査してフレーミング方式を自動判定し、メッセージを読み取る。

        Heuristic: 最初の 4 バイトが妥当な uint32 長さ（0 < length <= max_message_size）
        を形成する場合は LENGTH_PREFIXED と判定。それ以外は FRAMELESS（varint-delimited）。
        """
        try:
            peek = await self._reader.readexactly(4)
        except asyncio.IncompleteReadError as e:
            if not e.partial:
                return None
            # 4 バイト未満しか読めなかった場合は FRAMELESS と判定
            self._detected_mode = FramingMode.FRAMELESS
            self._buffer = e.partial
            return await self._read_varint_delimited()

        if not peek:
            return None

        # Heuristic: 最初の 4 バイトが妥当な長さヘッダーか検査
        candidate_length = int.from_bytes(peek, "big")

        if 0 < candidate_length <= self._max_message_size:
            # LENGTH_PREFIXED と判定
            self._detected_mode = FramingMode.LENGTH_PREFIXED
            logger.debug(
                "Auto-detected framing mode: LENGTH_PREFIXED (first length=%d)",
                candidate_length,
            )
            try:
                payload = await self._reader.readexactly(candidate_length)
            except asyncio.IncompleteReadError:
                return None
            self._messages_read += 1
            self._bytes_read += 4 + candidate_length
            return payload
        else:
            # FRAMELESS（varint-delimited）と判定
            self._detected_mode = FramingMode.FRAMELESS
            logger.debug("Auto-detected framing mode: FRAMELESS")
            # peek を buffer に保存して varint として再処理
            self._buffer = peek
            return await self._read_varint_delimited()

    async def _read_length_prefixed(self) -> bytes | None:
        """LENGTH_PREFIXED モードでメッセージを読み取る。

        4 バイト big-endian 長さヘッダー → ペイロード読み取り。
        """
        try:
            header = await self._read_bytes(4)
        except asyncio.IncompleteReadError:
            return None

        length = int.from_bytes(header, "big")

        if length == 0:
            self._log_malformed_data(header, "Zero-length message in LENGTH_PREFIXED mode")
            raise FramingError(
                "Zero-length message in LENGTH_PREFIXED mode",
                offset=self._bytes_read,
                data=header,
            )

        if length > self._max_message_size:
            self._log_malformed_data(
                header,
                f"Message size {length} exceeds max {self._max_message_size}",
            )
            raise FramingError(
                f"Message size {length} exceeds max {self._max_message_size}",
                offset=self._bytes_read,
                data=header,
            )

        try:
            payload = await self._read_bytes(length)
        except asyncio.IncompleteReadError:
            return None

        self._messages_read += 1
        self._bytes_read += 4 + length
        return payload

    async def _read_varint_delimited(self) -> bytes | None:
        """FRAMELESS モードで varint-delimited メッセージを読み取る。

        varint（最大 5 バイト、uint32）で長さを読み取り、その後ペイロードを読み取る。
        """
        length, varint_bytes_consumed = await self._read_varint()
        if length is None:
            return None

        if length == 0:
            self._log_malformed_data(b"\x00", "Zero-length message in FRAMELESS mode")
            raise FramingError(
                "Zero-length message in FRAMELESS mode",
                offset=self._bytes_read,
                data=b"\x00",
            )

        if length > self._max_message_size:
            self._log_malformed_data(
                b"",
                f"Message size {length} exceeds max {self._max_message_size}",
            )
            raise FramingError(
                f"Message size {length} exceeds max {self._max_message_size}",
                offset=self._bytes_read,
                data=b"",
            )

        try:
            payload = await self._read_bytes(length)
        except asyncio.IncompleteReadError:
            return None

        self._messages_read += 1
        self._bytes_read += varint_bytes_consumed + length
        return payload

    async def _read_varint(self) -> tuple[int | None, int]:
        """varint を読み取る（最大 5 バイト、uint32）。

        Returns:
            (decoded_value, bytes_consumed) のタプル。
            EOF 時は (None, 0)。

        Raises:
            FramingError: varint が 5 バイトを超える場合
        """
        length = 0
        shift = 0
        bytes_consumed = 0

        for _ in range(5):
            byte_data = await self._read_one_byte()
            if byte_data is None:
                if bytes_consumed == 0:
                    return None, 0
                # 途中で EOF — 不完全な varint
                return None, 0

            b = byte_data[0]
            length |= (b & 0x7F) << shift
            shift += 7
            bytes_consumed += 1

            if (b & 0x80) == 0:
                return length, bytes_consumed

        # 5 バイト読んでもまだ continuation bit が立っている
        self._log_malformed_data(b"", "Varint too long (> 5 bytes)")
        raise FramingError(
            "Varint too long (> 5 bytes)",
            offset=self._bytes_read,
            data=b"",
        )

    def _log_malformed_data(self, data: bytes, reason: str) -> None:
        """不正フレームデータをログ出力する（先頭 32 バイトの hex dump）。"""
        hex_dump = data[:32].hex() if data else "(empty)"
        logger.warning(
            "Malformed protobuf frame data: %s | offset=%d | first_32_bytes=%s",
            reason,
            self._bytes_read,
            hex_dump,
        )

    @property
    def detected_mode(self) -> FramingMode:
        """検出されたフレーミングモードを返す。"""
        if self._detected_mode is not None:
            return self._detected_mode
        return self._mode

    @property
    def messages_read(self) -> int:
        """読み取ったメッセージ数を返す。"""
        return self._messages_read

    @property
    def bytes_read(self) -> int:
        """読み取ったバイト数を返す。"""
        return self._bytes_read
