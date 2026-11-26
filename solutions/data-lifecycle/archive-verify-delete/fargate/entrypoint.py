"""Fargate task for files above the Lambda threshold (default 5 GiB).

Reads ``TASK_INPUT`` (JSON, set by the state machine) and runs one of three modes:

* ``archive``       hash the file through the Access Point, write the digests to the ledger, then
                    copy it to the archive bucket with a multipart ``UploadPartCopy`` and
                    ``ChecksumAlgorithm=CRC64NVME`` (``FULL_OBJECT``, equal to the whole-file CRC)
* ``second``        copy to the second bucket (the ledger already holds the digests)
* ``restore``       copy from the archive bucket back to the Access Point

Exit codes: 0 done, 2 bad input, 3 the source changed (set aside as ``CHANGED``), 1 any other
failure. A non-zero exit makes ``ecs:runTask.sync`` fail, and the state machine's Catch handles it.
"""

from __future__ import annotations

import json
import logging
import os
import sys

from shared.archive_verify import ledger as L
from shared.archive_verify.checksums import CRC64NVME, hash_stream
from shared.archive_verify.ledger import Ledger
from shared.archive_verify.plan import etag_equal
from shared.exceptions import S3ApHelperError
from shared.s3ap_helper import S3ApHelper

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("archive-task")

EXIT_OK, EXIT_ERROR, EXIT_BAD_INPUT, EXIT_CHANGED = 0, 1, 2, 3
PART_SIZE = 64 * 1024 * 1024
HASH_READ_BYTES = 16 * 1024 * 1024


def _extra_args(copy: dict, *, with_checksum: bool) -> dict:
    args = {
        "CopySourceIfMatch": copy["ifMatch"],
        "StorageClass": copy["storageClass"],
        "ContentType": copy["contentType"],
        "Metadata": copy["metadata"],
        "MetadataDirective": "REPLACE",
    }
    if with_checksum:
        args["ChecksumAlgorithm"] = CRC64NVME
    return args


def run_archive(task: dict, helper: S3ApHelper, ledger: Ledger) -> int:
    run_id, item, copy = task["runId"], task["item"], task["copy"]
    key, size, etag = item["key"], int(item["size"]), item["etag"]

    head = helper.head_object(key)
    if not etag_equal(head["ETag"], etag) or int(head["ContentLength"]) != size:
        ledger.update(run_id, key, L.CHANGED, reason="source changed before hashing")
        return EXIT_CHANGED
    digest = hash_stream(helper.streaming_download(key, HASH_READ_BYTES))
    after = helper.head_object(key)
    if digest.size != size or not etag_equal(after["ETag"], etag):
        ledger.update(run_id, key, L.CHANGED, reason="source changed while it was being read")
        return EXIT_CHANGED
    ledger.update(run_id, key, L.RECORDED, **digest.as_ledger())
    logger.info("hashed %s bytes; copying with %s", size, CRC64NVME)
    helper.copy_between(
        helper.bucket_param,
        key,
        copy["bucket"],
        copy["key"],
        _extra_args(copy, with_checksum=True),
        multipart_threshold=1,  # the Lambda path handles everything below the threshold
        multipart_chunksize=PART_SIZE,
    )
    ledger.update(run_id, key, L.COPIED, only_if_status=L.RECORDED, copiedAt=L.now_iso())
    return EXIT_OK


def run_second(task: dict, helper: S3ApHelper, ledger: Ledger) -> int:
    copy = task["secondCopy"]
    helper.copy_between(
        helper.bucket_param,
        task["item"]["key"],
        copy["bucket"],
        copy["key"],
        _extra_args(copy, with_checksum=True),
        multipart_threshold=1,
        multipart_chunksize=PART_SIZE,
    )
    return EXIT_OK


def run_restore(task: dict, helper: S3ApHelper, ledger: Ledger) -> int:
    copy = task["copy"]
    helper.copy_between(
        copy["copySource"].split("/", 1)[0],
        copy["copySource"].split("/", 1)[1],
        helper.bucket_param,
        copy["key"],
        {},
        multipart_threshold=1,
        multipart_chunksize=PART_SIZE,
    )
    return EXIT_OK


def main() -> int:
    try:
        mode = os.environ["TASK_MODE"]
        task = json.loads(os.environ["TASK_INPUT"])
        access_point = os.environ["ACCESS_POINT"]
        ledger = Ledger(os.environ["LEDGER_TABLE"])
    except (KeyError, json.JSONDecodeError) as e:
        logger.error("bad input: %s", e)
        return EXIT_BAD_INPUT
    helper = S3ApHelper(access_point)
    runners = {"archive": run_archive, "second": run_second, "restore": run_restore}
    if mode not in runners:
        logger.error("unknown TASK_MODE %r", mode)
        return EXIT_BAD_INPUT
    try:
        return runners[mode](task, helper, ledger)
    except S3ApHelperError as e:
        logger.error("S3 error (%s): %s", e.error_code, e)
        return EXIT_ERROR
    except Exception:  # noqa: BLE001 - the exit code is the contract
        logger.exception("unexpected failure")
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
