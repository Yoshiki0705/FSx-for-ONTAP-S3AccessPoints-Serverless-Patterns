"""UC16 Government Archives Discovery Lambda

FSx ONTAP S3 Access Point から公文書（PDF, TIFF, EML, DOCX）の一覧を取得する。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

from shared.exceptions import lambda_error_handler
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = frozenset({
    ".pdf", ".tif", ".tiff", ".eml", ".msg", ".docx", ".xlsx"
})


def _classify_document_type(key: str) -> str:
    lower = key.lower()
    if lower.endswith(".pdf"):
        return "pdf"
    if lower.endswith((".tif", ".tiff")):
        return "scanned_image"
    if lower.endswith((".eml", ".msg")):
        return "email"
    if lower.endswith(".docx"):
        return "word"
    if lower.endswith(".xlsx"):
        return "excel"
    return "unknown"


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    s3ap_output = S3ApHelper(
        os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"])
    )
    prefix = os.environ.get("PREFIX_FILTER", "archives/")
    suffix_filter = os.environ.get(
        "SUFFIX_FILTER", ",".join(sorted(SUPPORTED_FORMATS))
    )

    logger.info(
        "UC16 Discovery started: access_point=%s, prefix=%r",
        os.environ["S3_ACCESS_POINT"],
        prefix,
    )

    with xray_subsegment(
        name="s3ap_list_objects",
        annotations={
            "service_name": "s3",
            "operation": "ListObjectsV2",
            "use_case": "government-archives",
        },
    ):
        all_objects = []
        for single_suffix in suffix_filter.split(","):
            single_suffix = single_suffix.strip()
            if single_suffix:
                all_objects.extend(
                    s3ap.list_objects(prefix=prefix, suffix=single_suffix)
                )

    seen_keys = set()
    objects = []
    doc_types = {"pdf": 0, "scanned_image": 0, "email": 0, "word": 0, "excel": 0, "unknown": 0}
    for obj in all_objects:
        if obj["Key"] not in seen_keys:
            seen_keys.add(obj["Key"])
            obj["DocumentType"] = _classify_document_type(obj["Key"])
            doc_types[obj["DocumentType"]] += 1
            objects.append(obj)

    manifest = {
        "execution_id": context.aws_request_id,
        "timestamp": datetime.utcnow().isoformat(),
        "total_objects": len(objects),
        "objects": objects,
        "document_types": doc_types,
    }

    manifest_key = (
        f"manifests/{datetime.utcnow().strftime('%Y/%m/%d')}"
        f"/{context.aws_request_id}.json"
    )
    s3ap_output.put_object(
        key=manifest_key,
        body=json.dumps(manifest, default=str),
        content_type="application/json",
    )

    logger.info(
        "UC16 Discovery completed: total_objects=%d, manifest=%s",
        len(objects),
        manifest_key,
    )

    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="discovery")
    metrics.set_dimension("UseCase", "government-archives")
    metrics.put_metric("FilesProcessed", float(len(objects)), "Count")
    metrics.flush()

    return {
        "manifest_key": manifest_key,
        "total_objects": len(objects),
        "objects": objects,
        "document_types": doc_types,
    }
