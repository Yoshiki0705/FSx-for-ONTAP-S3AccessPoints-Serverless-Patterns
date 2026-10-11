"""Fake ``npm`` for the 07 tests.

``npm --version`` prints 10.0.0. ``npm ci`` creates ``node_modules/@playwright/test`` and
``node_modules/.bin/ampx`` under the working directory, so the next prerequisite check
sees an installed tree. ``$STUB_NPM_RC`` makes ``npm ci`` fail.
"""

from __future__ import annotations

import sys
from pathlib import Path

from external_common import exit_code, finish, record


def main(argv: list[str]) -> None:
    """Record the call and simulate ``--version`` and ``ci``.

    Args:
        argv: Arguments after ``npm``.
    """
    record("npm", argv)
    if argv[:1] == ["--version"]:
        print("10.0.0")
        finish(0)
    if argv[:1] == ["ci"]:
        rc = exit_code("STUB_NPM_RC")
        if rc != 0:
            sys.stderr.write("stub: npm ci failed\n")
            finish(rc)
        base = Path.cwd() / "node_modules"
        (base / "@playwright" / "test").mkdir(parents=True, exist_ok=True)
        (base / "@playwright" / "test" / "package.json").write_text("{}", encoding="utf-8")
        (base / ".bin").mkdir(parents=True, exist_ok=True)
        ampx = base / ".bin" / "ampx"
        ampx.write_text("#!/bin/sh\n", encoding="utf-8")
        ampx.chmod(0o755)
        finish(0)
    finish(0)


if __name__ == "__main__":
    main(sys.argv[1:])
