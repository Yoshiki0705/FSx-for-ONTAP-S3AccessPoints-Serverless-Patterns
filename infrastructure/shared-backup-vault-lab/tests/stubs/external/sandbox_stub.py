"""Fake ``scripts/sandbox.sh`` of the portal (``Lab.make_portal`` installs the wrapper).

It records the call and its environment, then exits with ``$STUB_SANDBOX_RC`` (default 0).
Which stacks changed is decided by the aws stub scenario (the before and after answers of
``cloudformation describe-stacks``), not here: 07 must not trust this exit code anyway.
"""

from __future__ import annotations

import sys

from external_common import exit_code, finish, record


def main(argv: list[str]) -> None:
    """Record the call and exit.

    Args:
        argv: Arguments after ``sandbox.sh``.
    """
    record("sandbox.sh", argv)
    finish(exit_code("STUB_SANDBOX_RC"))


if __name__ == "__main__":
    main(sys.argv[1:])
