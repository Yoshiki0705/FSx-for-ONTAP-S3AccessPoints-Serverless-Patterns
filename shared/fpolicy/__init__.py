"""shared.fpolicy — FPolicy プロトコル処理モジュール

NetApp ONTAP FPolicy サーバーが送信する protobuf メッセージの
TCP フレーミング方式を正しくパースするためのモジュール。

Usage:
    from shared.fpolicy import ProtobufFrameReader, FramingMode, FramingError
"""

from shared.fpolicy.protobuf_reader import (
    FramingError,
    FramingMode,
    ProtobufFrameReader,
)

__all__ = [
    "FramingError",
    "FramingMode",
    "ProtobufFrameReader",
]
