"""Fake ``npx`` for the 07 tests.

* ``npx playwright install chromium`` creates the file ``$STUB_CHROMIUM_PATH``.
* ``npx playwright test ... --reporter=json`` prints the report found in the file
  ``$STUB_NPX_REPORT`` (default: one passing test), writes ``$STUB_NPX_STDERR`` to
  standard error, and exits with ``$STUB_NPX_RC`` (default 0).

Nothing starts a browser or reaches a network.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from external_common import exit_code, finish, record

DEFAULT_REPORT = {
    "suites": [{"title": "shared-vault-lab.spec.ts", "specs": [{"title": "default stub test", "ok": True}]}],
    "stats": {"expected": 1, "skipped": 0, "unexpected": 0, "flaky": 0},
}


def main(argv: list[str]) -> None:
    """Record the call and answer ``playwright install`` and ``playwright test``.

    Args:
        argv: Arguments after ``npx``.
    """
    record("npx", argv)
    if argv[:3] == ["playwright", "install", "chromium"]:
        path = os.environ.get("STUB_CHROMIUM_PATH", "")
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text("chromium", encoding="utf-8")
        finish(exit_code("STUB_NPX_INSTALL_RC"))
    if argv[:2] == ["playwright", "test"]:
        report = os.environ.get("STUB_NPX_REPORT", "")
        if report:
            sys.stdout.write(Path(report).read_text(encoding="utf-8"))
        else:
            sys.stdout.write(json.dumps(DEFAULT_REPORT))
        sys.stderr.write(os.environ.get("STUB_NPX_STDERR", ""))
        finish(exit_code("STUB_NPX_RC"))
    finish(0)


if __name__ == "__main__":
    main(sys.argv[1:])
