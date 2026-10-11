"""Fake ``scripts/portal_preflight.py`` of the repository (``Lab.make_portal`` copies it).

Only ``--print-sandbox-identifier`` is simulated: it prints ``$STUB_PREFLIGHT_ID`` (default
``lab-sandbox``) and exits with ``$STUB_PREFLIGHT_RC`` (default 0).
"""

from __future__ import annotations

import os
import sys

from external_common import exit_code, finish, record


def main(argv: list[str]) -> None:
    """Record the call and answer ``--print-sandbox-identifier``.

    Args:
        argv: Arguments after the script name.
    """
    record("portal_preflight.py", argv)
    rc = exit_code("STUB_PREFLIGHT_RC")
    if rc == 0 and argv[:1] == ["--print-sandbox-identifier"]:
        print(os.environ.get("STUB_PREFLIGHT_ID", "lab-sandbox"))
    finish(rc)


if __name__ == "__main__":
    main(sys.argv[1:])
