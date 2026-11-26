"""Record one file in the ledger and prepare its copy parameters.

For files at or below the threshold the SHA-256 and CRC64NVME are computed here by
reading the file through the Access Point once. Larger files are hashed by the
Fargate task, so only the metadata is recorded.

The ETag and size seen when the file was listed must still hold when it is read
(before and after the read). If they do not, the file changed while being recorded and
is set aside as ``CHANGED``; nothing downstream touches it.
"""

from __future__ import annotations

import logging

from shared.archive_verify import ledger as L
from shared.archive_verify.checksums import hash_stream
from shared.archive_verify.ledger import Ledger
from shared.archive_verify.plan import (
    archive_key,
    build_metadata,
    copy_source,
    etag_equal,
    guess_content_type,
)
from shared.archive_verify.runtime import RuntimeConfig
from shared.exceptions import lambda_error_handler
from shared.observability import trace_lambda_handler
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)


def _copy_params(
    cfg: RuntimeConfig, bucket: str, run_id: str, key: str, etag: str, storage_class: str, metadata: dict
) -> dict:
    return {
        "bucket": bucket,
        "key": archive_key(cfg.archive_prefix, run_id, key),
        "copySource": copy_source(cfg.access_point, key),
        "ifMatch": etag,
        "storageClass": storage_class,
        "contentType": guess_content_type(key),
        "metadata": metadata,
    }


def record_file(
    cfg: RuntimeConfig,
    *,
    run_id: str,
    item: dict,
    attrs: dict | None,
    storage_class: str,
    helper: S3ApHelper | None = None,
    ledger: Ledger | None = None,
) -> dict:
    """Core of the handler, separated so tests can inject fakes."""
    helper = helper or S3ApHelper(cfg.access_point)
    ledger = ledger or Ledger(cfg.ledger_table)
    key, size, etag = item["key"], int(item["size"]), item["etag"]

    def changed(reason: str) -> dict:
        ledger.put(run_id, key, L.CHANGED, size=size, etag=etag, reason=reason)
        return {"status": L.CHANGED, "reason": reason, "key": key}

    head = helper.head_object(key)
    if not etag_equal(head["ETag"], etag) or int(head["ContentLength"]) != size:
        return changed("source changed between listing and recording")

    digest_attrs: dict = {}
    if not item["isLarge"]:
        digest = hash_stream(helper.streaming_download(key))
        after = helper.head_object(key)
        if digest.size != size or not etag_equal(after["ETag"], etag):
            return changed("source changed while it was being read")
        digest_attrs = digest.as_ledger()

    metadata = build_metadata(key, etag, item["lastModified"], attrs, run_id)
    second = bool(cfg.second_copy_bucket)
    ledger.put(
        run_id,
        key,
        L.RECORDED,
        size=size,
        etag=etag,
        lastModified=item["lastModified"],
        isLarge=bool(item["isLarge"]),
        storageClass=storage_class,
        archiveBucket=cfg.archive_bucket,
        archiveKey=archive_key(cfg.archive_prefix, run_id, key),
        secondCopyRequired=second,
        attrs=attrs or None,
        **digest_attrs,
    )
    out = {
        "status": L.RECORDED,
        "key": key,
        "size": size,
        "etag": etag,
        "isLarge": bool(item["isLarge"]),
        "copy": _copy_params(cfg, cfg.archive_bucket, run_id, key, etag, storage_class, metadata),
    }
    if second:
        out["secondCopy"] = _copy_params(cfg, cfg.second_copy_bucket, run_id, key, etag, storage_class, metadata)
    return out


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    cfg = RuntimeConfig.from_env()
    return record_file(
        cfg,
        run_id=event["runId"],
        item=event["item"],
        attrs=event.get("attrs") or event["item"].get("attrs"),
        storage_class=event["storageClass"],
    )
