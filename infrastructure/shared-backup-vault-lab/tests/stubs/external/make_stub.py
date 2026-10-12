"""Fake ``make`` for the 07 tests: only ``portal-demo-user`` is simulated.

The output copies the print format of ``scripts/portal_provision_demo_user.py`` (a
contract test pins that format in the real script). Mode ``$STUB_MAKE_MODE``:

* ``created`` (default): the account is created and ``$STUB_MAKE_PASSWORD`` is printed once;
* ``exists``: the account existed, no password is printed;
* ``garbled``: neither a password line nor the notice (a changed print format);
* ``fail``: exit 2 with a message.
"""

from __future__ import annotations

import os
import sys

from external_common import finish, record


def username_of(argv: list[str]) -> str:
    """Find ``--username`` inside the ``ARGS=...`` argument.

    Args:
        argv: Arguments after ``make``.

    Returns:
        The user name, or ``unknown``.
    """
    for arg in argv:
        if arg.startswith("ARGS="):
            words = arg[len("ARGS=") :].split()
            if "--username" in words:
                return words[words.index("--username") + 1]
    return "unknown"


def main(argv: list[str]) -> None:
    """Record the call and print the scenario output.

    Args:
        argv: Arguments after ``make``.
    """
    record("make", argv)
    if "portal-demo-user" not in argv:
        sys.stderr.write("stub: only portal-demo-user is simulated\n")
        finish(2)
    mode = os.environ.get("STUB_MAKE_MODE", "created")
    user = username_of(argv)
    if mode == "fail":
        # A simulated failure of make itself, not a crash of this stub: the "stub:" prefix
        # is reserved for a stub crash, which the harness treats as a test failure.
        sys.stderr.write("make: portal-demo-user failed\n")
        finish(2)
    print("pool     us-east-1_StubPool (sandbox 'stub', ap-northeast-1)")
    print("role     storage-admin -- everything group-gated")
    print()
    if mode == "exists":
        print(f"user     {user} already exists; password unchanged")
    else:
        print(f"user     {user} created, password set (permanent)")
    print()
    print("groups (delegated to grant_portal_roles.py):")
    if mode == "created":
        print()
        print("-" * 68)
        print(f"  username  {user}")
        print(f"  password  {os.environ.get('STUB_MAKE_PASSWORD', 'StubPassword-1!')}")
        print("-" * 68)
        print("Shown once and not written to disk. Hand it over out of band.")
    finish(0)


if __name__ == "__main__":
    main(sys.argv[1:])
