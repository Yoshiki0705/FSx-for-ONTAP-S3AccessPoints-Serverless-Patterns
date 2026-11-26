"""Plan and select: validate the start input, then list the files to archive.

Actions (``event["action"]``):

* ``plan``            validate the input and return the configuration the state machine reads.
                      Refuses a ``runId`` that already has ledger items unless ``resume`` is true
                      (and refuses ``resume`` for a run that has none)
* ``list``            ``selection=MTIME``: list the Access Point and filter on ``LastModified``
* ``from_candidates`` ``selection=ATIME``: take the candidate list written by the ONTAP REST
                      function, confirm each file through the Access Point, and select
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from shared.archive_verify import ledger as L
from shared.archive_verify.ledger import Ledger
from shared.archive_verify.plan import SelectionFilters, is_older_than, normalize_archive_input
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


MAX_RECORDED_SKIPS = 10_000


def _filters(event: dict, cfg: RuntimeConfig) -> SelectionFilters:
    return SelectionFilters.from_dict(event.get("filters"), cfg.default_filters())


def _finish(
    cfg: RuntimeConfig,
    run_id: str,
    items: list[dict],
    max_files: int,
    filters: SelectionFilters,
    ledger: Ledger | None = None,
    name_excluded: dict | None = None,
) -> dict:
    """Apply the size rules, drop files Lambda cannot hash without Fargate, cut, write.

    A file above the Access Point upload limit is recorded in the ledger as
    ``SKIPPED_TOO_LARGE`` (a restore could not write it back) and counted in the result.
    Files below the minimum size are only counted: there can be millions of them.
    """
    exclusions = {"tooLarge": 0, "tooSmall": 0, "pattern": 0, "prefix": 0, **(name_excluded or {})}
    skipped_large = 0
    kept: list[dict] = []
    too_large: list[dict] = []
    for item in items:
        reason = filters.size_exclusion(int(item["size"]))
        if reason:
            exclusions[reason] += 1
            if reason == "tooLarge":
                too_large.append(item)
            continue
        if item["isLarge"] and not cfg.fargate_enabled:
            skipped_large += 1
            continue
        kept.append(item)
    if too_large:
        ledger = ledger or Ledger(cfg.ledger_table)
        for item in too_large[:MAX_RECORDED_SKIPS]:
            ledger.put(
                run_id,
                item["key"],
                L.SKIPPED_TOO_LARGE,
                size=int(item["size"]),
                etag=item["etag"],
                reason=f"above the Access Point upload limit ({filters.max_file_bytes} bytes)",
            )
    kept = kept[:max_files]
    put_json(cfg.archive_bucket, selection_key(run_id), kept)
    return {
        "count": len(kept),
        "totalBytes": sum(i["size"] for i in kept),
        "skippedLarge": skipped_large,
        "skippedTooLarge": exclusions["tooLarge"],
        "exclusions": exclusions,
        "bucket": cfg.archive_bucket,
        "key": selection_key(run_id),
    }


def _plan(event: dict, context, cfg: RuntimeConfig, ledger: Ledger | None = None) -> dict:
    plan = normalize_archive_input(
        event.get("input") or {},
        execution_name=event.get("executionName", ""),
        ontap_enabled=cfg.ontap_enabled,
        default_filters=cfg.default_filters(),
        require_separate_approver=cfg.require_separate_approver,
    )
    ledger = ledger or Ledger(cfg.ledger_table)
    has_items = ledger.has_items(plan.run_id)
    if has_items and not plan.resume:
        raise InvalidInput(
            f"runId {plan.run_id!r} already has ledger items. Use a new runId, or pass "
            '"resume": true to continue this run (it settles interrupted items and asks for a new approval)'
        )
    if plan.resume and not has_items:
        raise InvalidInput(f"resume was requested but runId {plan.run_id!r} has no ledger items")
    return {
        "runId": plan.run_id,
        "prefix": plan.prefix,
        "storageClass": plan.storage_class,
        "olderThanDays": plan.older_than_days,
        "selection": plan.selection,
        "maxFiles": plan.max_files,
        "dryRun": plan.dry_run,
        "captureAttributes": plan.capture_attributes,
        "filters": plan.filters.as_dict(),
        "requestedBy": plan.requested_by,
        "resume": plan.resume,
        "config": cfg.public(),
    }


def _list(event: dict, cfg: RuntimeConfig) -> dict:
    run_id, prefix = event["runId"], event.get("prefix", "")
    filters = _filters(event, cfg)
    helper = S3ApHelper(cfg.access_point)
    objects = helper.list_objects(prefix=prefix)
    by_name = {"pattern": 0, "prefix": 0}
    older = []
    for o in objects:
        if o["Key"].endswith("/") or not is_older_than(o["LastModified"], int(event["olderThanDays"])):
            continue
        reason = filters.key_exclusion(o["Key"])
        if reason:
            by_name[reason] += 1
            continue
        older.append(o)
    older.sort(key=lambda o: o["LastModified"])
    items = [_item(cfg, o["Key"], o["Size"], o["ETag"], o["LastModified"], None) for o in older]
    return _finish(cfg, run_id, items, int(event["maxFiles"]), filters, name_excluded=by_name)


def _from_candidates(event: dict, cfg: RuntimeConfig) -> dict:
    run_id = event["runId"]
    filters = _filters(event, cfg)
    all_candidates = get_json(cfg.archive_bucket, candidates_key(run_id))
    by_name = {"pattern": 0, "prefix": 0}
    candidates = []
    for c in all_candidates:
        reason = filters.key_exclusion(c["key"])
        if reason:
            by_name[reason] += 1
        else:
            candidates.append(c)
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
    return _finish(cfg, run_id, confirmed, limit, filters, name_excluded=by_name)


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
