"""ゲノミクス / バイオインフォマティクス QC Lambda ハンドラ

FASTQ ファイルの品質チェックを実行する。S3ApHelper の streaming_download で
TB クラスの FASTQ ファイルをストリーミング処理し、先頭 N レコード（設定可能、
デフォルト 10,000）から品質メトリクスを抽出する。

FASTQ フォーマット（4 行 1 レコード）:
    行 1: ヘッダー（@ で始まる）
    行 2: 塩基配列（A, T, G, C, N）
    行 3: セパレータ（+ で始まる）
    行 4: 品質スコア（Phred+33 エンコード: ASCII - 33 = 品質スコア）

品質メトリクス:
    - total_reads: 読み取りレコード数
    - average_quality_score: 平均品質スコア（Phred スケール）
    - gc_content_percentage: GC 含有率（%）
    - sequence_length_distribution: 配列長分布（min, max, mean）
    - pass_filter_rate: フィルタ通過率

切り詰め/不正ファイルはエラーログ出力しワークフロー継続する。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN
    OUTPUT_BUCKET: S3 出力バケット名
    QC_SAMPLE_SIZE: サンプリングレコード数 (デフォルト: 10000)
    QUALITY_THRESHOLD: 品質閾値 (デフォルト: 20.0)
"""

from __future__ import annotations

import gzip
import json
import logging
import os
from datetime import datetime, timezone
from io import BytesIO
from pathlib import PurePosixPath

import boto3

from shared.exceptions import lambda_error_handler
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)

DEFAULT_QC_SAMPLE_SIZE = 10000
DEFAULT_QUALITY_THRESHOLD = 20.0


class FastqParseError(Exception):
    """FASTQ パースエラー"""

    pass


def _parse_fastq_records(
    data_stream,
    max_records: int,
) -> dict:
    """FASTQ レコードをパースし品質メトリクスを計算する

    ストリーミングデータから FASTQ レコードを読み取り、
    品質メトリクスを集計する。4 行 1 レコードのフォーマットに従う。

    Args:
        data_stream: テキスト行を yield するイテレータ
        max_records: 最大読み取りレコード数

    Returns:
        dict: 品質メトリクス
    """
    total_reads = 0
    total_quality_sum = 0.0
    total_bases = 0
    gc_count = 0
    sequence_lengths: list[int] = []
    pass_filter_count = 0

    line_buffer: list[str] = []

    for line in data_stream:
        line = line.rstrip("\n").rstrip("\r")
        line_buffer.append(line)

        if len(line_buffer) < 4:
            continue

        # 4 行揃ったらレコードとして処理
        header_line = line_buffer[0]
        sequence_line = line_buffer[1]
        separator_line = line_buffer[2]
        quality_line = line_buffer[3]
        line_buffer = []

        # ヘッダー行の検証
        if not header_line.startswith("@"):
            logger.warning(
                "Invalid FASTQ header (expected '@'): %s",
                header_line[:50],
            )
            continue

        # セパレータ行の検証
        if not separator_line.startswith("+"):
            logger.warning(
                "Invalid FASTQ separator (expected '+'): %s",
                separator_line[:50],
            )
            continue

        total_reads += 1
        seq_len = len(sequence_line)
        sequence_lengths.append(seq_len)

        # GC 含有率の計算
        seq_upper = sequence_line.upper()
        gc_count += seq_upper.count("G") + seq_upper.count("C")
        total_bases += seq_len

        # 品質スコアの計算（Phred+33 エンコード）
        record_quality_sum = 0.0
        for char in quality_line:
            record_quality_sum += ord(char) - 33
        total_quality_sum += record_quality_sum

        # フィルタ通過判定（レコード平均品質が閾値以上）
        if seq_len > 0:
            record_avg_quality = record_quality_sum / seq_len
            threshold = float(
                os.environ.get("QUALITY_THRESHOLD", DEFAULT_QUALITY_THRESHOLD)
            )
            if record_avg_quality >= threshold:
                pass_filter_count += 1

        if total_reads >= max_records:
            break

    if total_reads == 0:
        raise FastqParseError("No valid FASTQ records found in file")

    # メトリクス計算
    average_quality_score = round(total_quality_sum / total_bases, 1) if total_bases > 0 else 0.0
    gc_content_percentage = round((gc_count / total_bases) * 100, 1) if total_bases > 0 else 0.0
    pass_filter_rate = round(pass_filter_count / total_reads, 2) if total_reads > 0 else 0.0

    seq_min = min(sequence_lengths) if sequence_lengths else 0
    seq_max = max(sequence_lengths) if sequence_lengths else 0
    seq_mean = round(sum(sequence_lengths) / len(sequence_lengths), 1) if sequence_lengths else 0.0

    return {
        "total_reads": total_reads,
        "average_quality_score": average_quality_score,
        "gc_content_percentage": gc_content_percentage,
        "sequence_length_distribution": {
            "min": seq_min,
            "max": seq_max,
            "mean": seq_mean,
        },
        "pass_filter_rate": pass_filter_rate,
    }


def _streaming_text_lines(s3ap: S3ApHelper, key: str):
    """S3ApHelper のストリーミングダウンロードからテキスト行を yield する

    .fastq.gz ファイルの場合は gzip 展開を行う。
    TB クラスのファイルでもメモリに全体をロードしない。

    Args:
        s3ap: S3ApHelper インスタンス
        key: オブジェクトキー

    Yields:
        str: テキスト行
    """
    is_gzipped = key.endswith(".gz")

    if is_gzipped:
        # gzip 圧縮ファイル: チャンクを結合して gzip 展開
        # ストリーミングで gzip を展開するため、BytesIO + GzipFile を使用
        buffer = BytesIO()
        for chunk in s3ap.streaming_download(key):
            buffer.write(chunk)

        buffer.seek(0)
        with gzip.open(buffer, "rt", encoding="utf-8", errors="replace") as gz:
            for line in gz:
                yield line
    else:
        # 非圧縮ファイル: チャンクをテキスト行に分割
        remainder = ""
        for chunk in s3ap.streaming_download(key):
            text = remainder + chunk.decode("utf-8", errors="replace")
            lines = text.split("\n")
            # 最後の要素は不完全な行の可能性があるため保持
            remainder = lines[-1]
            for line in lines[:-1]:
                yield line
        # 残りのテキストを yield
        if remainder:
            yield remainder


@lambda_error_handler
def handler(event, context):
    """ゲノミクス / バイオインフォマティクス QC Lambda

    FASTQ ファイルをストリーミングダウンロードし、先頭 N レコードから
    品質メトリクスを抽出する。切り詰め/不正ファイルはエラーログ出力し
    ワークフローを継続する。

    Args:
        event: Map ステートからの入力
            {"Key": "samples/sample_001.fastq.gz", "Size": 5368709120, ...}

    Returns:
        dict: status, file_key, quality_metrics, output_key
              または status: "ERROR", file_key, error, error_type
    """
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    output_bucket = os.environ["OUTPUT_BUCKET"]
    file_key = event["Key"]
    sample_size = int(os.environ.get("QC_SAMPLE_SIZE", DEFAULT_QC_SAMPLE_SIZE))

    logger.info(
        "QC started: file_key=%s, sample_size=%d",
        file_key,
        sample_size,
    )

    try:
        # ストリーミングダウンロードで FASTQ レコードをパース
        text_lines = _streaming_text_lines(s3ap, file_key)
        quality_metrics = _parse_fastq_records(text_lines, sample_size)

    except (FastqParseError, UnicodeDecodeError, gzip.BadGzipFile) as e:
        logger.warning(
            "Failed to parse FASTQ file %s: %s", file_key, str(e)
        )
        return {
            "status": "ERROR",
            "file_key": file_key,
            "error": str(e),
            "error_type": type(e).__name__,
        }
    except Exception as e:
        logger.error(
            "Unexpected error processing FASTQ file %s: %s",
            file_key,
            str(e),
        )
        return {
            "status": "ERROR",
            "file_key": file_key,
            "error": str(e),
            "error_type": type(e).__name__,
        }

    # 日付パーティション付き出力キー生成
    now = datetime.now(timezone.utc)
    file_stem = PurePosixPath(file_key).stem
    # .fastq.gz の場合、stem は "sample_001.fastq" になるので再度 stem を取得
    if file_stem.endswith(".fastq"):
        file_stem = PurePosixPath(file_stem).stem
    output_key = f"qc/{now.strftime('%Y/%m/%d')}/{file_stem}_qc.json"

    # 品質メトリクス JSON を S3 出力バケットに書き込み
    output_data = {
        "file_key": file_key,
        "quality_metrics": quality_metrics,
        "sample_size": sample_size,
        "extracted_at": now.isoformat(),
    }

    s3_client = boto3.client("s3")
    s3_client.put_object(
        Bucket=output_bucket,
        Key=output_key,
        Body=json.dumps(output_data, default=str).encode("utf-8"),
        ContentType="application/json",
    )

    logger.info(
        "QC completed: file_key=%s, output_key=%s, "
        "total_reads=%d, avg_quality=%.1f, gc_content=%.1f%%",
        file_key,
        output_key,
        quality_metrics["total_reads"],
        quality_metrics["average_quality_score"],
        quality_metrics["gc_content_percentage"],
    )

    return {
        "status": "SUCCESS",
        "file_key": file_key,
        "quality_metrics": quality_metrics,
        "output_key": output_key,
    }
