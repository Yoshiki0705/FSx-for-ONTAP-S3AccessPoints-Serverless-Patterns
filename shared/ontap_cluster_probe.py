"""Deciding whether a declared ONTAP cluster answered.

A declared platform appears in the portal only once something answers for it. For
a cluster whose management interface is the ONTAP REST API, "answered" means
``GET /api/cluster`` returned a cluster name -- and the distinctions between the
ways it can fail to are the whole content of this module, because each one leads an
operator to a different action:

* No route at all. The cluster is not listed, and the reason says the request never
  reached anything. The next step is networking: a VPN, Direct Connect or Transit
  Gateway attachment, and a security group that permits 443 outbound.
* Reached and refused the credential. The cluster is not listed either, but the
  reason is the secret. Naming this separately matters more here than elsewhere:
  ONTAP locks an account after five failed attempts with ``lockout-duration`` at 0,
  so a probe that retries a wrong password on a schedule locks out the very account
  an operator needs. Nothing here retries.
* Reached, authenticated, and answered something else. Almost always not ONTAP: a
  load balancer, or a management address that has been reassigned.

The transport is injected. This module makes no request itself, so the decisions
can be tested without a cluster, and the VPC-resident caller supplies whichever
HTTP client it already has.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

#: What a probe reads. Deliberately the smallest endpoint that proves the API is
#: ONTAP's and the credential was accepted: the cluster's own name.
CLUSTER_ENDPOINT = "/cluster?fields=name,version"


@dataclass(frozen=True)
class ProbeResult:
    """What a probe found, and why it decided that.

    Attributes:
        answered: Whether the cluster is confirmed to exist and accept the
            credential. Only a true here may put a platform in the inventory.
        cluster_name: The name ONTAP reports, when it answered.
        version: The version string, when ONTAP reported one.
        reason: Why it did not answer, in terms of the next action to take. Empty
            when it did.
    """

    answered: bool
    cluster_name: str = ""
    version: str = ""
    reason: str = ""


def probe_ontap_cluster(
    request: Callable[[str], tuple[int, dict]],
    endpoint: str = CLUSTER_ENDPOINT,
) -> ProbeResult:
    """Ask a cluster whether it is there, and classify the answer.

    Args:
        request: Performs a GET against the cluster's REST API and returns the
            status code and the decoded body. It is expected to raise for a
            transport failure, which is reported as no route rather than as a
            refusal.
        endpoint: The path to read. Overridable for a caller that has already
            fetched the cluster document.

    Returns:
        The result. ``answered`` is true only when the cluster named itself.
    """
    try:
        status, body = request(endpoint)
    except Exception as exc:  # noqa: BLE001 - every transport failure is "no route"
        return ProbeResult(
            answered=False,
            reason=(
                f"No response from the management address ({type(exc).__name__}). "
                "Check the route from this VPC to the cluster and that the security "
                "group permits outbound 443."
            ),
        )

    if status in (401, 403):
        return ProbeResult(
            answered=False,
            reason=(
                f"The cluster answered but rejected the credential (HTTP {status}). "
                "Check the secret named in the declaration. This is not retried: "
                "ONTAP locks an account after repeated failures and the lockout does "
                "not clear on its own."
            ),
        )

    if status != 200:
        return ProbeResult(
            answered=False,
            reason=(
                f"The management address answered with HTTP {status}, which is not "
                "an ONTAP cluster document. Check that the address is the cluster "
                "management LIF and not a load balancer or a reassigned address."
            ),
        )

    name = str((body or {}).get("name") or "").strip()
    if not name:
        return ProbeResult(
            answered=False,
            reason=(
                "The management address answered 200 without naming a cluster, so what is there is probably not ONTAP."
            ),
        )

    return ProbeResult(
        answered=True,
        cluster_name=name,
        version=str(((body or {}).get("version") or {}).get("full") or "").strip(),
    )
