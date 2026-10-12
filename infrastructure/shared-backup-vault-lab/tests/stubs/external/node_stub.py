"""Fake ``node`` for the 07 tests.

``node --version`` prints ``$STUB_NODE_VERSION`` (default v20.11.0). ``node -e <code>``
prints ``$STUB_CHROMIUM_PATH``: it stands in for
``chromium.executablePath()``, whose result 07 checks for existence.
"""

from __future__ import annotations

import os
import sys

from external_common import finish, record


def main(argv: list[str]) -> None:
    """Record the call and answer ``--version`` or ``-e``.

    Args:
        argv: Arguments after ``node``.
    """
    record("node", argv)
    if argv[:1] == ["--version"]:
        print(os.environ.get("STUB_NODE_VERSION", "v20.11.0"))
        finish(0)
    if argv[:1] == ["-e"]:
        path = os.environ.get("STUB_CHROMIUM_PATH", "")
        if not path:
            sys.stderr.write("stub: STUB_CHROMIUM_PATH is not set\n")
            finish(1)
        print(path)
        finish(0)
    finish(0)


if __name__ == "__main__":
    main(sys.argv[1:])
