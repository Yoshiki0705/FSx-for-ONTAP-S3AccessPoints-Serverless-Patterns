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

Why access point routing lives here too
---------------------------------------
`resolve_ap_alias` answers the other half of the same question. The prefixes decide
which keys a caller may name; the access point decides which ONTAP identity the call
then runs as, and therefore what the NAS permissions allow. Measurement showed the
two are not interchangeable: with per-identity access points on one volume, a caller
denied a directory's contents could still see its name, because the parent directory
grants traversal. Neither half is redundant, and separating them across modules is
how one of them came to be skipped.

It also existed twice before landing here -- in `functions/list-files` and
`functions/thumbnails` -- while two other functions that were handed the mapping
never consulted it at all. A presigned URL signed against the default access point
carries the default identity, so a caller whose group maps to a read-only access
point was measured reading and writing through the permissive one.
"""

from __future__ import annotations

# S3's own limit. A longer key is refused before the call so the failure names the
# key rather than arriving as an opaque ClientError.
MAX_KEY_BYTES = 1024

# The role that may be exempt from the prefixes. Must match `ROLE_STORAGE_ADMIN` in
# `amplify/portal-groups.ts`; `tests/infrastructure/backend-assertions.test.ts` asserts
# the two sides agree, because a rename on one side only would leave this looking
# configured while matching nobody.
UNRESTRICTED_ROLE = "storage-admin"

# The scope that revokes that exemption. Must match `SCOPE_EXTERNAL`.
#
# The condition is the *absence* of this scope rather than the presence of `internal`,
# and the direction is the whole point. Every `storage-admin` in a deployed user pool
# predates the scope axis and holds neither scope, so requiring `internal` would
# confine all of them the moment this ships -- a change that arrives as an outage.
# Requiring the absence of `external` leaves them exactly as they were and confines
# only a caller somebody deliberately marked as outside the organisation.
CONFINED_SCOPE = "external"

# Kept as the previous name. Nothing in this repository imports it, but the module is
# on a Lambda layer, and a layer version outlives the deployment that built it.
UNRESTRICTED_GROUP = UNRESTRICTED_ROLE

# The role axis. Must match `PORTAL_ROLES` in `amplify/portal-groups.ts`, which
# `tests/infrastructure/backend-assertions.test.ts` asserts.
#
# Named here because role-keyed settings have to be matched against roles and not
# against whatever groups the caller happens to hold. Matching any group would let
# `{"external": true}` in a role setting grant every outside caller at once, which reads
# like "external users may do this" and quietly cancels the distinction the setting
# exists to draw.
PORTAL_ROLES = ("viewer", "contributor", UNRESTRICTED_ROLE, "auditor")


def allowed_prefixes(
    user_groups: list[str] | None,
    group_path_prefixes: dict[str, list[str]] | None,
) -> list[str]:
    """Path prefixes this caller may see, or `[]` for no restriction.

    An empty list means unrestricted, not "nothing allowed". That reading is load
    bearing in three places, so it is stated here rather than rediscovered: no
    configured mapping, no groups on the caller, an unconfined administrator, and a
    caller whose groups carry no prefixes all mean the same thing -- the deployment
    is not using per-team prefixes for this caller, so nothing is filtered.

    The administrator exemption is conditional. `storage-admin` is exempt unless the
    caller also holds `external`, which is how an administrator account belonging to
    somebody outside the organisation stays inside the boundary. Without that
    condition the two axes would not be independent: granting an outside member any
    administrative capability would have silently granted them the whole volume.

    Args:
        user_groups: The caller's Cognito groups.
        group_path_prefixes: Group name to the prefixes it may access.

    Returns:
        Sorted, de-duplicated prefixes, or an empty list for no restriction.
    """
    if not group_path_prefixes or not user_groups:
        return []
    if UNRESTRICTED_ROLE in user_groups and CONFINED_SCOPE not in user_groups:
        return []
    prefixes: list[str] = []
    for group in user_groups:
        prefixes.extend(group_path_prefixes.get(group, []))
    return sorted(set(prefixes))


def resolve_ap_alias(
    user_groups: list[str] | None,
    group_ap_mapping: dict[str, str] | None,
    default_alias: str,
) -> str:
    """The access point this caller reads and writes through.

    The alias decides which ONTAP File System Identity the request executes as, so
    choosing it by group is what makes per-team visibility a mechanism rather than a
    convention. A caller in no mapped group falls back to the default.

    Iteration order is the mapping's, so a caller in two mapped groups gets the one
    declared first. That is worth stating because it is configuration-dependent
    rather than obvious: put the narrower group earlier if a user can be in both.

    Args:
        user_groups: The caller's Cognito groups.
        group_ap_mapping: Group name to the access point alias it reads through.
        default_alias: Alias for a caller with no mapped group.

    Returns:
        The alias to use, or `default_alias` when no group matches. May be empty
        when nothing is configured, which callers report rather than treating as a
        bucket name.
    """
    if group_ap_mapping and user_groups:
        for group_name, ap_alias in group_ap_mapping.items():
            if group_name in user_groups:
                return ap_alias
    return default_alias


def prefix_is_reachable(prefix: str, allowed: list[str]) -> bool:
    """Whether a caller confined to `allowed` may navigate to or through `prefix`.

    Deliberately bidirectional, and that is the whole subtlety. A prefix inside an
    allowed one is reachable because its contents are permitted. A prefix that is an
    *ancestor* of an allowed one is also reachable, because otherwise a caller
    restricted to `team-a/reports/` could never open `team-a/` to get there, and the
    restriction would be a dead end rather than a boundary.

    Args:
        prefix: The prefix being listed or navigated to.
        allowed: Prefixes this caller may access; empty means unrestricted.

    Returns:
        True when the prefix may be shown, including for an unrestricted caller.
    """
    if not allowed:
        return True
    return any(prefix.startswith(p) or p.startswith(prefix) for p in allowed)


def key_is_visible(key: str, allowed: list[str]) -> bool:
    """Whether an object key may appear in a listing for a caller confined to `allowed`.

    One-directional, unlike `prefix_is_reachable`. A prefix may be shown because the
    caller has to pass through it, but an object is either inside the boundary or it
    is not: a file sitting beside an allowed folder is not made visible by proximity
    to it.

    Args:
        key: The object key from the listing.
        allowed: Prefixes this caller may access; empty means unrestricted.

    Returns:
        True when the object may be shown, including for an unrestricted caller.
    """
    if not allowed:
        return True
    return any(key.startswith(p) for p in allowed)


def scope_for_caller(
    user_groups: list[str] | None,
    *,
    group_ap_mapping: dict[str, str] | None,
    group_path_prefixes: dict[str, list[str]] | None,
    default_alias: str,
    key: str,
    field: str = "key",
) -> tuple[str, dict | None]:
    """Resolve where a caller reads and whether it may name this key, in one call.

    Every endpoint that takes an object key from the client needs the same two
    decisions, and the reason to hand them out together is that taking only one is
    the failure that keeps happening: the access point without the key check reads
    anything on the caller's own volume, and the key check without the access point
    reads the right key on the wrong volume as the wrong identity.

    Eight endpoints took a client-supplied key while making neither decision. They
    are the endpoints that read file *content* -- text extraction, entity analysis,
    label detection, question answering -- so a caller could name another team's key
    and receive the contents back through the answer, without ever listing it.

    Args:
        user_groups: The caller's Cognito groups.
        group_ap_mapping: Group name to the access point alias it reads through.
        group_path_prefixes: Group name to the prefixes it may access.
        default_alias: Alias for a caller with no mapped group.
        key: The object key from the request.
        field: Request field the key arrived in, named in any refusal.

    Returns:
        `(alias, None)` when the caller may proceed, or `(alias, refusal)` where
        `refusal` is a payload fragment naming why. The alias is returned in both
        cases so a caller can log the attempt against the right access point.
    """
    groups = user_groups or []
    alias = resolve_ap_alias(groups, group_ap_mapping, default_alias)
    if not alias:
        return "", {"error": "S3_AP_ALIAS is not configured"}
    return alias, reject_key(key, allowed_prefixes(groups, group_path_prefixes), field=field)


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
