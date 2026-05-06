"""ゲノミクス / バイオインフォマティクス バリアント集計 Lambda ハンドラ

VCF (Variant Call Format) ファイルのバリアント統計を集計する。
S3ApHelper でファイルを取得し、バリアントレコードをパースして
統計情報（total_variants, snp_count, indel_count, ti_tv_ratio,
het_hom_ratio）を計算する。

VCF フォーマット:
    - # で始まる行: ヘッダー（スキップ）
    - データ行: CHROM POS ID REF ALT QUAL FILTER INFO [FORMAT SAMPLE...]
    - SNP: REF と ALT が共に 1 塩基
    - Indel: REF または ALT の長さが異なる
    - Transition (Ti): A↔G, C↔T の置換
    - Transversion (Tv): その他の置換

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN
    OUTPUT_BUCKET: S3 出力バケット名
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
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)

# Transition ペア（A↔G, C↔T）
TRANSITIONS = frozenset({("A", "G"), ("G", "A"), ("C", "T"), ("T", "C")})


class VcfParseError(Exception):
    """VCF パースエラー"""

    pass


def _is_snp(ref: str, alt: str) -> bool:
    """SNP かどうかを判定する

    Args:
        ref: リファレンス塩基
        alt: 代替塩基

    Returns:
        bool: SNP の場合 True
    """
    return len(ref) == 1 and len(alt) == 1


def _is_transition(ref: str, alt: str) -> bool:
    """Transition（遷移型置換）かどうかを判定する

    Transition: A↔G, C↔T
    Transversion: その他の SNP 置換

    Args:
        ref: リファレンス塩基
        alt: 代替塩基

    Returns:
        bool: Transition の場合 True
    """
    return (ref.upper(), alt.upper()) in TRANSITIONS


def _parse_vcf_records(data_stream) -> dict:
    """VCF レコードをパースしバリアント統計を計算する

    Args:
        data_stream: テキスト行を yield するイテレータ

    Returns:
        dict: バリアント統計
    """
    total_variants = 0
    snp_count = 0
    indel_count = 0
    transition_count = 0
    transversion_count = 0
    het_count = 0
    hom_count = 0

    for line in data_stream:
        line = line.rstrip("\n").rstrip("\r")

        # ヘッダー行をスキップ
        if line.startswith("#") or not line.strip():
            continue

        fields = line.split("\t")
        if len(fields) < 5:
            logger.warning("Skipping malformed VCF line: %s", line[:80])
            continue

        ref = fields[3].upper()
        alt_field = fields[4].upper()

        # 複数 ALT アレル対応（カンマ区切り）
        alt_alleles = alt_field.split(",")

        for alt in alt_alleles:
            alt = alt.strip()
            # 構造変異や特殊記号をスキップ
            if alt in (".", "*", "<DEL>", "<INS>", "<DUP>", "<INV>", "<CNV>"):
                continue

            total_variants += 1

            if _is_snp(ref, alt):
                snp_count += 1
                if _is_transition(ref, alt):
                    transition_count += 1
                else:
                    transversion_count += 1
            else:
                indel_count += 1

        # ヘテロ/ホモ接合性の判定（FORMAT + SAMPLE カラムがある場合）
        if len(fields) >= 10:
            format_field = fields[8]
            sample_field = fields[9]

            # GT (Genotype) フィールドの位置を特定
            format_keys = format_field.split(":")
            if "GT" in format_keys:
                gt_index = format_keys.index("GT")
                sample_values = sample_field.split(":")
                if gt_index < len(sample_values):
                    gt = sample_values[gt_index]
                    # GT フォーマット: 0/1 (het), 1/1 (hom), 0|1 (phased het)
                    alleles = gt.replace("|", "/").split("/")
                    if len(alleles) == 2:
                        if alleles[0] != alleles[1]:
                            het_count += 1
                        elif alleles[0] != "0":
                            hom_count += 1

    if total_variants == 0:
        raise VcfParseError("No valid variant records found in VCF file")

    # Ti/Tv ratio の計算
    ti_tv_ratio = (
        round(transition_count / transversion_count, 2)
        if transversion_count > 0
        else 0.0
    )

    # Het/Hom ratio の計算
    het_hom_ratio = (
        round(het_count / hom_count, 2) if hom_count > 0 else 0.0
    )

    return {
        "total_variants": total_variants,
        "snp_count": snp_count,
        "indel_count": indel_count,
        "ti_tv_ratio": ti_tv_ratio,
        "het_hom_ratio": het_hom_ratio,
    }


def _streaming_text_lines(s3ap: S3ApHelper, key: str):
    """S3ApHelper のストリーミングダウンロードからテキスト行を yield する

    .vcf.gz ファイルの場合は gzip 展開を行う。

    Args:
        s3ap: S3ApHelper インスタンス
        key: オブジェクトキー

    Yields:
        str: テキスト行
    """
    is_gzipped = key.endswith(".gz")

    if is_gzipped:
        buffer = BytesIO()
        for chunk in s3ap.streaming_download(key):
            buffer.write(chunk)

        buffer.seek(0)
        with gzip.open(buffer, "rt", encoding="utf-8", errors="replace") as gz:
            for line in gz:
                yield line
    else:
        remainder = ""
        for chunk in s3ap.streaming_download(key):
            text = remainder + chunk.decode("utf-8", errors="replace")
            lines = text.split("\n")
            remainder = lines[-1]
            for line in lines[:-1]:
                yield line
        if remainder:
            yield remainder


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """ゲノミクス / バイオインフォマティクス バリアント集計 Lambda

    VCF ファイルをパースし、バリアント統計（total_variants, snp_count,
    indel_count, ti_tv_ratio, het_hom_ratio）を集計する。

    Args:
        event: Map ステートからの入力
            {"Key": "variants/sample_001.vcf.gz", "Size": 104857600, ...}

    Returns:
        dict: status, file_key, variant_statistics, output_key
              または status: "ERROR", file_key, error, error_type
    """
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    output_bucket = os.environ["OUTPUT_BUCKET"]
    file_key = event["Key"]

    logger.info("Variant Aggregation started: file_key=%s", file_key)

    try:
        text_lines = _streaming_text_lines(s3ap, file_key)
        variant_statistics = _parse_vcf_records(text_lines)

    except (VcfParseError, UnicodeDecodeError, gzip.BadGzipFile) as e:
        logger.warning(
            "Failed to parse VCF file %s: %s", file_key, str(e)
        )
        return {
            "status": "ERROR",
            "file_key": file_key,
            "error": str(e),
            "error_type": type(e).__name__,
        }
    except Exception as e:
        logger.error(
            "Unexpected error processing VCF file %s: %s",
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
    # .vcf.gz の場合、stem は "sample_001.vcf" になるので再度 stem を取得
    if file_stem.endswith(".vcf"):
        file_stem = PurePosixPath(file_stem).stem
    output_key = f"variants/{now.strftime('%Y/%m/%d')}/{file_stem}_stats.json"

    # バリアント統計 JSON を S3 出力バケットに書き込み
    output_data = {
        "file_key": file_key,
        "variant_statistics": variant_statistics,
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
        "Variant Aggregation completed: file_key=%s, output_key=%s, "
        "total_variants=%d, snp=%d, indel=%d, ti_tv=%.2f",
        file_key,
        output_key,
        variant_statistics["total_variants"],
        variant_statistics["snp_count"],
        variant_statistics["indel_count"],
        variant_statistics["ti_tv_ratio"],
    )


    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="variant_aggregation")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "genomics-pipeline"))
    metrics.put_metric("FilesProcessed", 1.0, "Count")
    metrics.flush()

    return {
        "status": "SUCCESS",
        "file_key": file_key,
        "variant_statistics": variant_statistics,
        "output_key": output_key,
    }
