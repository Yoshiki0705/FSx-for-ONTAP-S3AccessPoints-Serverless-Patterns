"""The portal's multi-tenancy boundary: which object keys a caller may name.

Two rules, and both are authorization rather than validation, which is why they live
together and why they live here.

`allowed_prefixes` turns a caller's Cognito groups into the path prefixes they may
touch. `reject_key` decides whether one key is acceptable, the prefix check being the
last and most important of its tests.

Why a module rather than a third copy
-------------------------------------
This logic existed twice: `_allowed_prefixes` in `functions/list-files` and
`_get_allowed_prefixes` in `functions/agent-chat`. The first said so in its own
docstring -- "Two copies of a boundary can disagree, so if a third consumer appears
this belongs in a shared module" -- and the thumbnail path was the third consumer.

The two copies did agree when they were merged here, but only by luck: one returned
`sorted(set(...))` and the other `list(set(...))` after an extra early return that
made no difference to any caller. That is the shape a boundary drifts through --
edits that look equivalent until one of them is not.

The prefix mapping is a parameter, not read from the environment here. Each handler
parses `GROUP_PATH_PREFIXES` once at import as it always did, so this module has no
import-time environment dependency and can be tested without one.
"""

from __future__ import annotations

# S3's own limit. A longer key is refused before the call so the failure names the
# key rather than arriving as an opaque ClientError.
MAX_KEY_BYTES = 1024

# A caller in this group is not confined to prefixes.
UNRESTRICTED_GROUP = "storage-admin"


def allowed_prefixes(
    user_groups: list[str] | None,
    group_path_prefixes: dict[str, list[str]] | None,
) -> list[str]:
    """Path prefixes this caller may see, or `[]` for no restriction.

    An empty list means unrestricted, not "nothing allowed". That reading is load
    bearing in three places, so it is stated here rather than rediscovered: no
    configured mapping, no groups on the caller, a caller in `storage-admin`, and a
    caller whose groups carry no prefixes all mean the same thing -- the deployment
    is not using per-team prefixes for this caller, so nothing is filtered.

    Args:
        user_groups: The caller's Cognito groups.
        group_path_prefixes: Group name to the prefixes it may access.

    Returns:
        Sorted, de-duplicated prefixes, or an empty list for no restriction.
    """
    if not group_path_prefixes or not user_groups:
        return []
    if UNRESTRICTED_GROUP in user_groups:
        return []
    prefixes: list[str] = []
    for group in user_groups:
        prefixes.extend(group_path_prefixes.get(group, []))
    return sorted(set(prefixes))


def reject_key(key: str, allowed: list[str], *, field: str) -> dict | None:
    """Why this key may not be used, or None if it may.

    Every action that names an object runs its keys through here. Three classes of
    problem, and the order matters only in what the caller is told first.

    Shape. An empty key, a leading separator, a doubled separator, a control
    character, or anything over S3's length limit. None of these can be produced by
    the UI, so a request carrying one is not a mistake worth guessing at.

    A `..` segment. S3 keys are literal -- `a/../b` is a key, not a path, and no
    resolution happens. That is exactly why it is refused: it means one thing to the
    prefix comparison below and another to a person, and a key that reads as an
    escape has no legitimate use in this portal.

    Scope. The prefix list is the multi-tenancy boundary. It was once applied to the
    notification inbox alone, so where per-team prefixes were configured, a caller
    could rename, trash or restore an object under another team's prefix by naming it
    directly, and mint a presigned PUT into it. The endpoint is authenticated but the
    key was never checked against the caller.

    Args:
        key: The object key from the request.
        allowed: Prefixes this caller may touch; empty means unrestricted.
        field: Request field the key arrived in, named in the message.

    Returns:
        A failure payload fragment, or None when the key is acceptable.
    """
    if not key:
        return {"error": f"{field} is required"}
    if len(key.encode("utf-8")) > MAX_KEY_BYTES:
        return {"error": f"{field} exceeds the {MAX_KEY_BYTES}-byte key limit"}
    if key.startswith("/") or "//" in key:
        return {"error": f"{field} must not start with or contain an empty path segment"}
    if any(segment == ".." for segment in key.split("/")):
        return {"error": f"{field} must not contain a '..' segment"}
    if any(character < " " or character == "\x7f" for character in key):
        return {"error": f"{field} must not contain control characters"}
    if allowed and not any(key.startswith(prefix) for prefix in allowed):
        # Names the boundary without listing every other tenant's prefixes.
        return {"error": f"{field} is outside the prefixes your groups may access"}
    return None
