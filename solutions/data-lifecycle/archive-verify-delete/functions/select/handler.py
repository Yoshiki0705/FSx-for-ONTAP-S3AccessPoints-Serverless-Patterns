"""Plan and select: validate the start input, then list the files to archive.

Actions (``event["action"]``):

* ``plan``            validate the input and return the configuration the state machine reads
* ``list``            ``selection=MTIME``: list the Access Point and filter on ``LastModified``
* ``from_candidates`` ``selection=ATIME``: take the candidate list written by the ONTAP REST
                      function, confirm each file through the Access Point, and select
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from shared.archive_verify.plan import is_older_than, normalize_archive_input
from shared.archive_verify.runtime import MANIFEST_PREFIX, RuntimeConfig, get_json, put_json
from shared.exceptions import InvalidInput, S3ApHelperError, lambda_error_handler
from shared.observability import trace_lambda_handler
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)


def selection_key(run_id: str) -> str:
    return f"{MANIFEST_PREFIX}{run_id}-selection.json"


def candidates_key(run_id: str) -> str:
    return f"{MANIFEST_PREFIX}{run_id}-candidates.json"


def _item(cfg: RuntimeConfig, key: str, size: int, etag: str, last_modified: str, attrs: dict | None) -> dict:
    item = {
        "key": key,
        "size": int(size),
        "etag": etag,
        "lastModified": last_modified,
        "isLarge": int(size) > cfg.threshold_bytes,
    }
    if attrs:
        item["attrs"] = attrs
    return item


def _finish(cfg: RuntimeConfig, run_id: str, items: list[dict], max_files: int) -> dict:
    """Drop files that Lambda cannot hash when no Fargate task is configured, cut, write."""
    skipped_large = 0
    kept: list[dict] = []
    for item in items:
        if item["isLarge"] and not cfg.fargate_enabled:
            skipped_large += 1
            continue
        kept.append(item)
    kept = kept[:max_files]
    put_json(cfg.archive_bucket, selection_key(run_id), kept)
    return {
        "count": len(kept),
        "totalBytes": sum(i["size"] for i in kept),
        "skippedLarge": skipped_large,
        "bucket": cfg.archive_bucket,
        "key": selection_key(run_id),
    }


def _plan(event: dict, context, cfg: RuntimeConfig) -> dict:
    plan = normalize_archive_input(
        event.get("input") or {},
        execution_name=event.get("executionName", ""),
        ontap_enabled=cfg.ontap_enabled,
    )
    return {
        "runId": plan.run_id,
        "prefix": plan.prefix,
        "storageClass": plan.storage_class,
        "olderThanDays": plan.older_than_days,
        "selection": plan.selection,
        "maxFiles": plan.max_files,
        "dryRun": plan.dry_run,
        "captureAttributes": plan.capture_attributes,
        "config": cfg.public(),
    }


def _list(event: dict, cfg: RuntimeConfig) -> dict:
    run_id, prefix = event["runId"], event.get("prefix", "")
    helper = S3ApHelper(cfg.access_point)
    objects = helper.list_objects(prefix=prefix)
    older = [
        o
        for o in objects
        if not o["Key"].endswith("/") and is_older_than(o["LastModified"], int(event["olderThanDays"]))
    ]
    older.sort(key=lambda o: o["LastModified"])
    items = [_item(cfg, o["Key"], o["Size"], o["ETag"], o["LastModified"], None) for o in older]
    return _finish(cfg, run_id, items, int(event["maxFiles"]))


def _from_candidates(event: dict, cfg: RuntimeConfig) -> dict:
    run_id = event["runId"]
    candidates = get_json(cfg.archive_bucket, candidates_key(run_id))
    helper = S3ApHelper(cfg.access_point)

    def confirm(c: dict) -> dict | None:
        try:
            head = helper.head_object(c["key"])
        except S3ApHelperError as e:
            if e.error_code in ("404", "NoSuchKey", "NotFound"):
                logger.info("candidate no longer on the Access Point: %s", c["key"])
                return None
            raise
        return _item(
            cfg,
            c["key"],
            head["ContentLength"],
            head["ETag"],
            head["LastModified"].isoformat(),
            c.get("attrs"),
        )

    limit = int(event["maxFiles"])
    with ThreadPoolExecutor(max_workers=16) as pool:
        confirmed = [i for i in pool.map(confirm, candidates[: limit * 2]) if i]
    return _finish(cfg, run_id, confirmed, limit)


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    cfg = RuntimeConfig.from_env()
    action = event.get("action")
    if action == "plan":
        return _plan(event, context, cfg)
    if action == "list":
        return _list(event, cfg)
    if action == "from_candidates":
        return _from_candidates(event, cfg)
    raise InvalidInput(f"unknown action {action!r}")
