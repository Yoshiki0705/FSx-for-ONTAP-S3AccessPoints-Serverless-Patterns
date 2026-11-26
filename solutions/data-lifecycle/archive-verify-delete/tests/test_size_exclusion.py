"""Files above the Access Point upload limit are left out of the selection by default.

The Access Point accepts uploads of at most 50 GiB (FSx for ONTAP User Guide, "Access point
compatibility"), and a restore writes through it. A larger file could be copied and deleted
but not restored to the Access Point.
"""

from __future__ import annotations

from avd_support import load_handler

select = load_handler("select")

GIB = 1024**3


class FakeHelper:
    def __init__(self, objects):
        self._objects = objects

    def list_objects(self, prefix=""):
        return self._objects


def _obj(key, size):
    return {"Key": key, "Size": size, "ETag": '"e"', "LastModified": "2020-01-01T00:00:00+00:00"}


def test_a_file_above_50_gib_is_skipped_and_recorded(aws, ledger, lambda_context, monkeypatch):
    monkeypatch.setattr(
        select, "S3ApHelper", lambda ap: FakeHelper([_obj("big.bin", 51 * GIB), _obj("ok.bin", 200_000)])
    )
    out = select.handler(
        {"action": "list", "runId": "r1", "prefix": "", "olderThanDays": 0, "maxFiles": 10}, lambda_context
    )
    assert out["count"] == 1
    assert out["skippedTooLarge"] == 1
    assert ledger.get("r1", "big.bin")["status"] == "SKIPPED_TOO_LARGE"
