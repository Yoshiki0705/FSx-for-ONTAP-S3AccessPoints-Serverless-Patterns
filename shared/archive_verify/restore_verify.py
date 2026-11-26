"""Check a restored file against the digests the ledger recorded before the delete.

A restore copies the archived object back through the Access Point. The copy is only as good
as the object that was archived, and the archive was verified against a hash taken *before*
the delete. This reads the restored file back through the Access Point, hashes it, and compares
size, SHA-256 and CRC64NVME with the ledger. The ledger moves to ``RESTORE_VERIFIED`` or
``RESTORE_MISMATCH``; ``RESTORED`` alone means the copy call succeeded and nothing more.
"""

from __future__ import annotations

from shared.archive_verify import ledger as L
from shared.archive_verify.checksums import hash_stream
from shared.archive_verify.ledger import Ledger
from shared.s3ap_helper import S3ApHelper

READ_CHUNK_BYTES = 16 * 1024 * 1024


def compare_digest(item: dict, digest) -> tuple[bool, str]:
    """``(ok, reason)`` for a restored file's digest against a ledger item."""
    if not item.get("sha256") or not item.get("crc64nvme"):
        return False, "the ledger holds no digest for this file"
    if int(item["size"]) != digest.size:
        return False, f"size differs: restored={digest.size} ledger={item['size']}"
    if item["sha256"] != digest.sha256_hex:
        return False, "SHA-256 differs from the ledger"
    if item["crc64nvme"] != digest.crc64nvme_b64:
        return False, "CRC64NVME differs from the ledger"
    return True, "match"


def verify_restored(helper: S3ApHelper, ledger: Ledger, run_id: str, key: str, restore_run_id: str) -> dict:
    item = ledger.get(run_id, key)
    if item is None:
        return {"key": key, "status": L.RESTORE_MISMATCH, "reason": "no ledger item"}
    digest = hash_stream(helper.streaming_download(key, READ_CHUNK_BYTES))
    ok, reason = compare_digest(item, digest)
    status = L.RESTORE_VERIFIED if ok else L.RESTORE_MISMATCH
    ledger.update(
        run_id,
        key,
        status,
        only_if_status=L.RESTORED,
        also_if={"restoreRunId": restore_run_id},
        restoreVerifiedAt=L.now_iso(),
        restoreVerifyReason=reason,
    )
    return {"key": key, "status": status, "reason": reason}
