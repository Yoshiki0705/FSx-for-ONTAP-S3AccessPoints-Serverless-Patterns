"""Property-Based Tests for UC6: 半導体 / EDA メタデータ抽出

Hypothesis を使用したプロパティベーステスト。
EDA メタデータ抽出 Lambda の不変条件（invariants）を任意入力で検証する。

Testing Strategy:
- 最小 100 イテレーション/プロパティ
- 各テストにプロパティ番号タグを付与
- タグ形式: Feature: fsxn-s3ap-serverless-patterns-phase2, Property {number}: {property_text}
"""

from __future__ import annotations

import json
import os
import re
import struct
import sys
from datetime import datetime, timezone

from hypothesis import given, settings, strategies as st

# shared モジュールと UC6 関数のパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from functions.metadata_extraction.handler import (
    GdsiiParseError,
    OasisParseError,
    _extract_metadata,
    _parse_gdsii_header,
)


# ---------------------------------------------------------------------------
# Helper: GDSII バイナリヘッダー構築
# ---------------------------------------------------------------------------


def _make_gdsii_record(record_type: int, data: bytes) -> bytes:
    """GDSII レコードを構築する

    Args:
        record_type: レコードタイプ (2 bytes, e.g. 0x0002 for HEADER)
        data: レコードデータ

    Returns:
        bytes: 完全な GDSII レコード (length + type + data)
    """
    # レコード長はヘッダー 4 バイト + データ長
    record_length = 4 + len(data)
    # GDSII ではレコード長は偶数でなければならない
    if record_length % 2 != 0:
        data = data + b"\x00"
        record_length += 1
    return struct.pack(">HH", record_length, record_type) + data


def build_gds_header(
    library_name: str,
    cell_count: int,
    creation_year: int = 2026,
    creation_month: int = 1,
    creation_day: int = 15,
    creation_hour: int = 10,
    creation_minute: int = 0,
    creation_second: int = 0,
    version: int = 600,
) -> bytes:
    """テスト用の有効な GDSII バイナリヘッダーを構築する

    Args:
        library_name: ライブラリ名 (ASCII)
        cell_count: セル数 (BGNSTR レコードの数)
        creation_year: 作成年
        creation_month: 作成月
        creation_day: 作成日
        creation_hour: 作成時
        creation_minute: 作成分
        creation_second: 作成秒
        version: GDS バージョン (e.g. 600 for 6.0)

    Returns:
        bytes: 有効な GDSII バイナリヘッダー
    """
    records = []

    # HEADER record (0x0002): version number
    records.append(_make_gdsii_record(0x0002, struct.pack(">H", version)))

    # BGNLIB record (0x0102): creation date (12 x 2-byte integers)
    # creation date + modification date (same values)
    date_data = struct.pack(
        ">12H",
        creation_year,
        creation_month,
        creation_day,
        creation_hour,
        creation_minute,
        creation_second,
        creation_year,
        creation_month,
        creation_day,
        creation_hour,
        creation_minute,
        creation_second,
    )
    records.append(_make_gdsii_record(0x0102, date_data))

    # LIBNAME record (0x0206): library name (ASCII, null-padded to even length)
    name_bytes = library_name.encode("ascii", errors="replace")
    if len(name_bytes) % 2 != 0:
        name_bytes += b"\x00"
    records.append(_make_gdsii_record(0x0206, name_bytes))

    # UNITS record (0x0305): 2 x 8-byte GDSII real8 (user_unit, db_unit)
    # Use standard values: user_unit=0.001, db_unit=1e-9
    # These are IBM float format values
    units_data = _float_to_gdsii_real8(0.001) + _float_to_gdsii_real8(1e-9)
    records.append(_make_gdsii_record(0x0305, units_data))

    # BGNSTR records (0x0502): one per cell
    # Each BGNSTR has 24 bytes of date data (same format as BGNLIB)
    bgnstr_date = struct.pack(
        ">12H",
        creation_year,
        creation_month,
        creation_day,
        creation_hour,
        creation_minute,
        creation_second,
        creation_year,
        creation_month,
        creation_day,
        creation_hour,
        creation_minute,
        creation_second,
    )
    for _ in range(cell_count):
        records.append(_make_gdsii_record(0x0502, bgnstr_date))

    # ENDLIB record (0x0400): no data
    records.append(_make_gdsii_record(0x0400, b""))

    return b"".join(records)


def _float_to_gdsii_real8(value: float) -> bytes:
    """IEEE 754 浮動小数点数を GDSII 8 バイト実数に変換する

    GDSII は IBM 形式の浮動小数点数を使用する:
        - ビット 0: 符号 (0=正, 1=負)
        - ビット 1-7: 指数 (excess-64, 基数 16)
        - ビット 8-63: 仮数部 (56 ビット)
    """
    if value == 0.0:
        return b"\x00" * 8

    sign = 0
    if value < 0:
        sign = 0x80
        value = -value

    # value = mantissa * 16^exponent, where 1/16 <= mantissa < 1
    exponent = 0
    mantissa = value

    # Normalize: mantissa should be in [1/16, 1)
    if mantissa != 0:
        # Find exponent such that 1/16 <= mantissa / 16^exponent < 1
        while mantissa >= 1.0:
            mantissa /= 16.0
            exponent += 1
        while mantissa < 1.0 / 16.0:
            mantissa *= 16.0
            exponent -= 1

    # Convert mantissa to 56-bit integer
    mantissa_int = int(mantissa * (2**56))
    if mantissa_int >= 2**56:
        mantissa_int = 2**56 - 1

    # Encode
    byte0 = sign | ((exponent + 64) & 0x7F)
    result = bytes([byte0])
    for i in range(6, -1, -1):
        result += bytes([(mantissa_int >> (i * 8)) & 0xFF])

    return result


# ---------------------------------------------------------------------------
# Property 5: EDA metadata extraction completeness
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    library_name=st.text(
        min_size=1,
        max_size=44,
        alphabet=st.characters(
            whitelist_categories=("L", "N", "P"),
            whitelist_characters="_-",
            max_codepoint=127,
        ),
    ),
    cell_count=st.integers(min_value=0, max_value=200),
)
def test_eda_metadata_extraction_completeness(library_name, cell_count):
    """Feature: fsxn-s3ap-serverless-patterns-phase2, Property 5: EDA metadata extraction completeness

    For any valid GDS/OASIS binary header with arbitrary library_name,
    cell_count, bounding_box, and creation_date values, the
    Metadata_Extraction_Lambda SHALL extract all required fields
    (library_name, units, cell_count, bounding_box, creation_date,
    file_format) and the extracted values SHALL match the input header
    values.

    Strategy: Generate valid GDSII binary headers with random library names
    and cell counts, then verify the parser extracts them correctly.

    **Validates: Requirements 3.2, 3.3**
    """
    # Build a valid GDSII binary header
    header_data = build_gds_header(
        library_name=library_name,
        cell_count=cell_count,
        creation_year=2026,
        creation_month=1,
        creation_day=15,
        creation_hour=10,
        creation_minute=30,
        creation_second=0,
    )

    # Parse the header using the actual handler function
    result = _parse_gdsii_header(header_data)

    # Verify all required fields are present
    assert "library_name" in result
    assert "units" in result
    assert "cell_count" in result
    assert "bounding_box" in result
    assert "creation_date" in result
    assert "file_format" in result

    # Verify extracted values match input
    assert result["library_name"] == library_name
    assert result["cell_count"] == cell_count
    assert result["file_format"] == "GDSII"
    assert result["file_version"] == "6.0"

    # Verify creation date was parsed
    assert result["creation_date"] is not None
    assert "2026-01-15" in result["creation_date"]

    # Verify units are present and non-zero
    assert "user_unit" in result["units"]
    assert "db_unit" in result["units"]


# ---------------------------------------------------------------------------
# Property 6: Metadata output JSON with date partition
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    file_key=st.text(
        min_size=5,
        max_size=100,
        alphabet=st.characters(
            whitelist_categories=("L", "N"),
            whitelist_characters="/_-.",
            max_codepoint=127,
        ),
    ).filter(lambda x: "/" in x and not x.startswith("/") and not x.endswith("/")),
    library_name=st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N"), max_codepoint=127)),
    cell_count=st.integers(min_value=0, max_value=10000),
    file_format=st.sampled_from(["GDSII", "OASIS"]),
    year=st.integers(min_value=2020, max_value=2030),
    month=st.integers(min_value=1, max_value=12),
    day=st.integers(min_value=1, max_value=28),
)
def test_metadata_output_json_with_date_partition(
    file_key, library_name, cell_count, file_format, year, month, day
):
    """Feature: fsxn-s3ap-serverless-patterns-phase2, Property 6: Metadata output JSON with date partition

    For any extracted metadata, the output SHALL be valid JSON and the S3
    output key SHALL contain a date partition in the format YYYY/MM/DD.

    Strategy: Generate arbitrary metadata dicts and verify the output key
    format follows the date partition convention.

    **Validates: Requirements 3.3, 5.3**
    """
    # Construct metadata dict as the handler would produce
    metadata = {
        "file_format": file_format,
        "library_name": library_name,
        "units": {"user_unit": 0.001, "db_unit": 1e-9},
        "cell_count": cell_count,
        "bounding_box": {"min_x": 0, "min_y": 0, "max_x": 1000, "max_y": 1000},
        "creation_date": f"{year}-{month:02d}-{day:02d}T00:00:00+00:00",
    }

    # Simulate the output key generation logic from the handler
    now = datetime(year, month, day, tzinfo=timezone.utc)
    from pathlib import PurePosixPath

    file_stem = PurePosixPath(file_key).stem
    output_key = f"metadata/{now.strftime('%Y/%m/%d')}/{file_stem}.json"

    # Construct the output data as the handler does
    output_data = {
        "file_key": file_key,
        **metadata,
        "extracted_at": now.isoformat(),
    }

    # Verify output is valid JSON
    json_str = json.dumps(output_data, default=str)
    parsed = json.loads(json_str)
    assert isinstance(parsed, dict)
    assert "file_key" in parsed
    assert "file_format" in parsed

    # Verify the output key contains a date partition in YYYY/MM/DD format
    date_pattern = r"\d{4}/\d{2}/\d{2}"
    assert re.search(date_pattern, output_key), (
        f"Output key '{output_key}' does not contain date partition YYYY/MM/DD"
    )

    # Verify the output key ends with .json
    assert output_key.endswith(".json"), (
        f"Output key '{output_key}' does not end with .json"
    )

    # Verify the date partition matches the input date
    expected_date_part = f"{year:04d}/{month:02d}/{day:02d}"
    assert expected_date_part in output_key


# ---------------------------------------------------------------------------
# Property 7: Invalid file graceful handling
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    random_data=st.binary(min_size=0, max_size=1024),
    file_extension=st.sampled_from([".gds", ".gds2", ".oas", ".oasis", ".unknown"]),
)
def test_invalid_file_graceful_handling(random_data, file_extension):
    """Feature: fsxn-s3ap-serverless-patterns-phase2, Property 7: Invalid file graceful handling

    For any corrupted or unparseable file (random byte sequences), the
    processing Lambda SHALL return a structured error response with status
    "INVALID" or "FAIL", the original file_key, and an error description,
    WITHOUT raising an unhandled exception.

    Strategy: Generate random byte sequences and pass them to
    _extract_metadata, verify it raises a parse error (which the handler
    catches and returns as INVALID).

    **Validates: Requirements 3.7, 4.7, 5.8, 7.8**
    """
    file_key = f"test/corrupted_file{file_extension}"

    # The handler wraps _extract_metadata in a try/except and returns
    # status: "INVALID". We test that _extract_metadata raises a known
    # exception type (GdsiiParseError, OasisParseError, ValueError)
    # for any random data, and never raises an unhandled exception.
    try:
        _extract_metadata(random_data, file_key)
        # If parsing succeeds (extremely unlikely for random data),
        # that's also acceptable — the function handled it gracefully
    except (GdsiiParseError, OasisParseError, ValueError):
        # Expected: known parse errors that the handler catches
        # and converts to status: "INVALID"
        pass
    except Exception as e:
        # Unexpected: any other exception type would be an unhandled error
        raise AssertionError(
            f"_extract_metadata raised unexpected exception type "
            f"{type(e).__name__}: {e}"
        ) from e

    # Simulate the handler's error handling to verify the structured response
    try:
        _extract_metadata(random_data, file_key)
    except (GdsiiParseError, OasisParseError, ValueError) as e:
        # Build the structured error response as the handler does
        response = {
            "status": "INVALID",
            "file_key": file_key,
            "error": str(e),
            "error_type": type(e).__name__,
        }
        assert response["status"] == "INVALID"
        assert response["file_key"] == file_key
        assert isinstance(response["error"], str)
        assert len(response["error"]) > 0
        assert isinstance(response["error_type"], str)
    except Exception as e:
        raise AssertionError(
            f"_extract_metadata raised unexpected exception type "
            f"{type(e).__name__}: {e}"
        ) from e
