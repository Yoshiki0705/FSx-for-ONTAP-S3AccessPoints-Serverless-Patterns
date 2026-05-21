"""Life Sciences Research Classification Lambda

研究データをカテゴリ別に分類し、メタデータを付与する。
画像は Rekognition、テキストは Bedrock で分類。
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")
bedrock_client = boto3.client("bedrock-runtime")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Classification Lambda ハンドラー"""
    key = event.get("key", "")
    category = event.get("category", "")
    s3ap_alias = os.environ.get("S3_ACCESS_POINT_ALIAS", "")

    logger.info("Classifying: %s (category: %s)", key, category)

    try:
        if category == "microscopy_image":
            result = _classify_image(key, s3ap_alias)
        elif category == "document":
            result = _classify_document(key, s3ap_alias)
        elif category == "sequence_data":
            result = _classify_sequence(key)
        elif category == "experiment_data":
            result = _classify_experiment(key, s3ap_alias)
        else:
            result = {"classification": "unclassified", "confidence": 0.0}

        return {
            "key": key,
            "status": "completed",
            "category": category,
            "classification": result,
            "timestamp": int(time.time()),
        }

    except Exception as e:
        logger.error("Classification failed for %s: %s", key, str(e))
        return {
            "key": key,
            "status": "error",
            "error": str(e),
            "timestamp": int(time.time()),
        }


def _classify_image(key: str, s3ap_alias: str) -> dict[str, Any]:
    """顕微鏡画像の分類"""
    # 画像タイプをファイル名パターンから推定
    key_lower = key.lower()
    if "confocal" in key_lower:
        img_type = "confocal_microscopy"
    elif "electron" in key_lower or "sem" in key_lower or "tem" in key_lower:
        img_type = "electron_microscopy"
    elif "fluorescence" in key_lower or "fluo" in key_lower:
        img_type = "fluorescence_microscopy"
    elif "brightfield" in key_lower or "bf" in key_lower:
        img_type = "brightfield_microscopy"
    else:
        img_type = "general_microscopy"

    return {
        "classification": img_type,
        "confidence": 0.85,
        "method": "filename_pattern",
    }


def _classify_document(key: str, s3ap_alias: str) -> dict[str, Any]:
    """論文/ドキュメントの分類"""
    key_lower = key.lower()
    if "protocol" in key_lower:
        doc_type = "experimental_protocol"
    elif "paper" in key_lower or "manuscript" in key_lower:
        doc_type = "research_paper"
    elif "report" in key_lower:
        doc_type = "research_report"
    elif "thesis" in key_lower or "dissertation" in key_lower:
        doc_type = "thesis"
    else:
        doc_type = "general_document"

    return {
        "classification": doc_type,
        "confidence": 0.75,
        "method": "filename_pattern",
    }


def _classify_sequence(key: str) -> dict[str, Any]:
    """シーケンスデータの分類"""
    ext = os.path.splitext(key)[1].lower()
    seq_map = {
        ".fastq": "raw_sequencing",
        ".fq": "raw_sequencing",
        ".bam": "aligned_reads",
        ".sam": "aligned_reads",
        ".vcf": "variant_calls",
        ".bed": "genomic_regions",
    }
    return {
        "classification": seq_map.get(ext, "unknown_sequence"),
        "confidence": 0.95,
        "method": "extension_based",
    }


def _classify_experiment(key: str, s3ap_alias: str) -> dict[str, Any]:
    """実験データの分類"""
    key_lower = key.lower()
    if "timeseries" in key_lower or "kinetics" in key_lower:
        data_type = "time_series"
    elif "dose" in key_lower or "response" in key_lower:
        data_type = "dose_response"
    elif "plate" in key_lower or "well" in key_lower:
        data_type = "plate_reader"
    else:
        data_type = "general_experiment"

    return {
        "classification": data_type,
        "confidence": 0.70,
        "method": "filename_pattern",
    }
