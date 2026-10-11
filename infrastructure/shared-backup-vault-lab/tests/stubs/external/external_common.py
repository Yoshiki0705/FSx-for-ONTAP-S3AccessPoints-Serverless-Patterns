"""Shared recording for the fake external commands (node, npm, npx, make, sandbox.sh).

Each fake appends one line ``<name> <arguments>`` to ``$STUB_EXTERNAL_LOG`` (the format
``Lab.add_tool`` uses) and one JSON record to ``$STUB_EXTERNAL_JSONL`` with the working
directory and the environment values the tests assert on.

The recorded environment never holds a secret: the password is reduced to a SHA-256
digest, so a test can tell WHICH password reached the child without the value being
written anywhere.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

# Environment values copied into the record as they are.
PLAIN_ENV = (
    "AWS_PROFILE",
    "AWS_REGION",
    "AWS_DEFAULT_REGION",
    "AWS_DEFAULT_PROFILE",
    "AMPLIFY_PORTAL_REGION",
    "AMPLIFY_PORTAL_SANDBOX_IDENTIFIER",
    "AMPLIFY_PORTAL_BACKUP_REGIONS",
    "AMPLIFY_PORTAL_BACKUP_VAULT_ARNS",
    "AMPLIFY_PORTAL_RESTORE_ROLE_ARN",
    "AMPLIFY_PORTAL_RESTORE_SVM_IDS",
    "AMPLIFY_PORTAL_RESTORE_FILE_SYSTEM_IDS",
    "LAB_LAG_VAULT_NAME",
    "LAB_OWNER_ACCOUNT_ID",
    "LAB_SECOND_REGION",
    "LAB_UI_EXPECT",
    "LAB_CAPTURE_DIR",
    "PORTAL_URL",
    "PORTAL_USER",
    "CI",
)


def record(name: str, argv: list[str]) -> None:
    """Append the call to the text log and the JSON log.

    Args:
        name: Command name as the script named it (``sandbox.sh``, ``npx``, ...).
        argv: Arguments after the command.
    """
    text_log = os.environ.get("STUB_EXTERNAL_LOG", "")
    if text_log:
        with open(text_log, "a", encoding="utf-8") as handle:
            handle.write(f"{name} {' '.join(argv)}\n")
    json_log = os.environ.get("STUB_EXTERNAL_JSONL", "")
    if not json_log:
        return
    env = {key: os.environ.get(key) for key in PLAIN_ENV}
    env["AWS_ACCESS_KEY_ID_set"] = "AWS_ACCESS_KEY_ID" in os.environ
    env["AWS_SECRET_ACCESS_KEY_set"] = "AWS_SECRET_ACCESS_KEY" in os.environ
    env["AWS_SESSION_TOKEN_set"] = "AWS_SESSION_TOKEN" in os.environ
    password = os.environ.get("PORTAL_PASSWORD")
    env["PORTAL_PASSWORD_sha256"] = hashlib.sha256(password.encode("utf-8")).hexdigest() if password else None
    entry = {"name": name, "argv": argv, "cwd": str(Path.cwd().resolve()), "env": env}
    with open(json_log, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def exit_code(variable: str, default: int = 0) -> int:
    """Read an exit code from the environment.

    Args:
        variable: Environment variable name.
        default: Value when the variable is unset or empty.

    Returns:
        The exit code.
    """
    raw = os.environ.get(variable, "")
    return int(raw) if raw else default


def finish(code: int) -> None:
    """Exit with ``code`` after flushing the streams.

    Args:
        code: Process exit code.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    sys.exit(code)
