"""What a portal caller from outside the organisation may do.

Separate from `portal_path_scope` because the question is a different one. That module
answers "which data does this caller reach", enforced by the access point and the path
prefixes. This one answers "may this caller use a capability at all", where the
capability is not about reach but about where data ends up: file contents sent to a
model, or a bearer URL that outlives the request.

Deliberately not expressed as AppSync authorization. Two reasons, both practical:

  The AI endpoints number six. Writing `allow.groups` on each would spread the meaning
  of `external` across six declarations, and the seventh endpoint added later would be
  written by copying a neighbour that predates the rule.

  These are data-handling decisions rather than authorization ones. `ask-about-file`
  already refuses on data classification in the handler, which is the same layer and
  the same kind of judgement; putting the scope check somewhere else would split one
  decision across two places.

Every function here takes its configuration explicitly rather than reading the
environment, so a caller cannot be silently unrestricted by a missing variable -- the
absence shows up at the call site, where the default is written down.
"""

from __future__ import annotations

from shared.portal_path_scope import CONFINED_SCOPE, PORTAL_ROLES

__all__ = [
    "DENIED_SHARE_LINK_MAX_EXPIRY_SECONDS",
    "EXTERNAL_SCOPE",
    "ai_denial_reason",
    "is_external",
    "share_link_denial_reason",
    "share_link_expiry_ceiling",
]

# How long a presigned URL may live when the caller is external and their role does not
# allow share links.
#
# A ceiling rather than a refusal, because refusing would take away downloading as well.
# The portal serves file previews and downloads through presigned URLs, so an external
# member denied them outright could not retrieve a file at all -- which is the thing
# they were invited to do.
#
# The number matches the shortest lifetime the share dialog offers, so denying the role
# removes every longer option while leaving preview and download untouched. Stated
# plainly: this bounds the exposure window, it does not prevent forwarding. Any
# presigned URL can be passed on while it is valid; what changes is for how long.
DENIED_SHARE_LINK_MAX_EXPIRY_SECONDS = 300

# The scope that marks a caller as outside the organisation: a member with no Windows
# or UNIX account on the file system, identified only by an email address.
#
# Aliased from the boundary module rather than repeated, so a rename cannot leave the
# two halves disagreeing about who is external.
EXTERNAL_SCOPE = CONFINED_SCOPE


def is_external(user_groups: list[str] | None) -> bool:
    """Whether this caller is outside the organisation.

    Args:
        user_groups: The caller's Cognito groups.

    Returns:
        True when the caller holds the external scope.
    """
    return bool(user_groups) and EXTERNAL_SCOPE in user_groups


def ai_denial_reason(
    user_groups: list[str] | None,
    *,
    ai_enabled: bool,
) -> str | None:
    """Why this caller may not use an AI endpoint, or None if they may.

    Returns a reason rather than a bool so the message the caller sees and the message
    written to the log come from the same place. The message names the setting, because
    the person hitting this is an administrator wondering why a feature is missing far
    more often than an attacker probing for one.

    Args:
        user_groups: The caller's Cognito groups.
        ai_enabled: Whether the deployment allows external callers on AI endpoints.

    Returns:
        A reason string, or None when the call may proceed.
    """
    if not is_external(user_groups) or ai_enabled:
        return None
    return (
        "AI features are not available to external users in this deployment. "
        "An administrator can enable them with externalDefaults.aiEnabled."
    )


def share_link_denial_reason(
    user_groups: list[str] | None,
    *,
    share_links_by_role: dict[str, bool] | None,
) -> str | None:
    """Why this caller may not mint a share link, or None if they may.

    Only external callers are subject to this. A share link is a bearer credential: it
    is redeemable without AWS credentials until it expires, so whoever the recipient
    forwards it to has the same access. Whether that is acceptable depends on the
    organisation, which is why the answer is configuration and not a constant.

    A role absent from the mapping is denied, and an empty mapping therefore denies
    every external caller. That is the shipped default: a typo in a role name fails
    closed instead of quietly granting.

    Holding several roles grants the most permissive answer among them, matching how
    roles combine everywhere else -- a contributor who is also a viewer is a
    contributor.

    Args:
        user_groups: The caller's Cognito groups.
        share_links_by_role: Role name to whether that role may mint share links.

    Returns:
        A reason string, or None when the call may proceed.
    """
    if not is_external(user_groups):
        return None
    mapping = share_links_by_role or {}
    # Only the caller's roles are consulted, not every group they hold. Matching any
    # group would make `{"external": true}` grant every outside caller, which is how
    # somebody would naturally write "external users may share" and which would erase
    # the per-role distinction this setting exists to express. Restricted here, and
    # `backend.ts` refuses a non-role key at synth so the intent is not silently lost.
    held_roles = [group for group in (user_groups or []) if group in PORTAL_ROLES]
    if any(mapping.get(role) is True for role in held_roles):
        return None
    return (
        "Share links are not available to external users with this role. "
        "An administrator can allow them with "
        "externalDefaults.shareLinksByRole."
    )


def share_link_expiry_ceiling(
    user_groups: list[str] | None,
    *,
    share_links_by_role: dict[str, bool] | None,
) -> int | None:
    """The longest presigned URL lifetime this caller may ask for, or None for no limit.

    For the endpoints that both serve the caller's own download and produce links meant
    to be handed on. The two cannot be told apart from the request: the portal's preview,
    its download button and its share dialog all call the same query, and the shortest
    lifetime the share dialog offers is the same as the preview's. A `purpose` flag would
    not help either, since the caller chooses what to send.

    So the control is the lifetime rather than the act. A caller whose role allows share
    links has no ceiling. A caller whose role does not keeps preview and download and
    loses the longer lifetimes that make a link worth passing on.

    Use `share_link_denial_reason` instead where the endpoint exists only to hand a link
    to somebody else -- a QR code has no in-session use to preserve.

    Args:
        user_groups: The caller's Cognito groups.
        share_links_by_role: Role name to whether that role may mint share links.

    Returns:
        A ceiling in seconds, or None when the caller may ask for any lifetime.
    """
    if share_link_denial_reason(user_groups, share_links_by_role=share_links_by_role) is None:
        return None
    return DENIED_SHARE_LINK_MAX_EXPIRY_SECONDS
