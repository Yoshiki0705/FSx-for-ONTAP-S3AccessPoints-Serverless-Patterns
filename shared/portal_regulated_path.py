"""Whether an object key names a folder whose contents must not reach a managed AI service.

The predicate already existed twice: `src/utils/regulatedPath.ts` for the browser, which
disables the buttons, and an inline copy in `functions/agent-chat/handler.py`, which
refuses inside the `read_file` tool. The browser copy carries a comment about keeping one
definition of the boundary; the Python copy was written separately anyway, so there were
two that could disagree after an edit to either. This is the Python one, imported by every
endpoint that sends file contents somewhere.

**This is a guard against accidental submission, not the enforcement boundary.** The folder
naming convention is a hint. A deployment that has to guarantee the boundary enforces it
with IAM and the group path prefixes, which is what `portal_path_scope` answers -- a caller
who cannot reach the key cannot submit it here either. What this module adds is that a key
the caller *can* reach still does not get handed to Textract, Comprehend or a model just
because the request bypassed the browser.

That distinction is the reason the check is unconditional rather than configurable. The
browser already refuses these paths, so an operator driving the portal sees no change; the
only caller this newly refuses is one calling AppSync directly, and a deployment intending
to process regulated folders would have had to disable the browser guard too. Adding a
setting would mean the published behaviour depends on a variable nobody sets.

Content is not inspected. A key outside these folders holding regulated data is not
detected here, and `ask-about-file` answers that question separately with its data
classification lookup.
"""

from __future__ import annotations

import re

__all__ = [
    "REGULATED_ROOTS",
    "REGULATED_SEGMENT",
    "is_regulated_path",
    "regulated_path_denial_reason",
]

# A segment anywhere in the key, or one of the roots at the start. Matched against a
# leading-slash form of the key so the first segment is covered by the same expression.
#
# The trailing `[/-]` is what keeps `phishing-report.pdf` from matching `phi`: the segment
# has to end at a separator. Kept identical to the browser copy in `regulatedPath.ts`; the
# two are checked against each other by `shared/tests/test_portal_regulated_path.py`.
REGULATED_SEGMENT = re.compile(r"/(dicom|phi|pii|hipaa|protected-health)[/\-]", re.IGNORECASE)

REGULATED_ROOTS = ("dicom/", "phi/", "pii/")


def is_regulated_path(key: str) -> bool:
    """Whether this key sits in a folder that must not be sent to a managed AI service.

    Args:
        key: The object key, with or without a leading slash.

    Returns:
        True when the key is in a regulated folder.
    """
    lower = (key or "").lower()
    return bool(REGULATED_SEGMENT.search(f"/{lower}")) or lower.startswith(REGULATED_ROOTS)


def regulated_path_denial_reason(key: str) -> str | None:
    """Why this key may not be sent to a managed AI service, or None if it may.

    A reason rather than a bool, matching `portal_external_policy`, so the message the
    caller sees and the message written to the log come from one place. The message names
    the folder convention, because the person hitting this is far more often an
    administrator wondering why an endpoint refused than an attacker probing it.

    Args:
        key: The object key.

    Returns:
        A reason string, or None when the call may proceed.
    """
    if not is_regulated_path(key):
        return None
    return (
        f"AI processing is blocked for '{key}': the key is in a regulated folder "
        f"({', '.join(REGULATED_ROOTS)} or a dicom/phi/pii/hipaa/protected-health segment). "
        "Move the file outside that folder, or process it with a tool that keeps the "
        "contents inside your account."
    )
