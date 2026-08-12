"""Turn an ONTAP REST outcome into something the person reading it can act on.

Every ONTAP failure in the portal used to arrive as one of two sentences: "ONTAP
connection not configured" or "Volume 'x' not found on SVM 'y'". The panels then
rendered the same advice for both -- check the VPC subnet, the security group, the
management LIF -- because the only distinction the UI could make was "we have data" or
"we do not".

That advice was wrong for the failure that actually happened. On the verification
environment the portal reported

    Volume 'vol1' not found on SVM 'fsxsvm01'

while the AWS control plane listed that volume, in that SVM, as CREATED. The request
had reached ONTAP over TLS, Secrets Manager had returned the credentials, and ONTAP had
answered with

    {"error": {"message": "User is not authorized."}}

which carries no `records` key -- so the handler's `if not data.get("records")` branch
called it a missing volume. Somebody following the on-screen advice would have spent the
afternoon on subnets and security groups, all of which were fine, for a stale password.

The classes below exist so that each failure names the thing to go and look at. They are
deliberately coarse: five classes a reader can act on differently, rather than a taxonomy
of every ONTAP status code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any


class OntapFailure(str, Enum):
    """What went wrong, in terms of what the reader should do next.

    A `str` enum so the value crosses the GraphQL boundary and reaches the UI without a
    conversion table on either side.
    """

    NOT_CONFIGURED = "NOT_CONFIGURED"
    """No management IP or secret name. The deployment did not set them."""

    UNREACHABLE = "UNREACHABLE"
    """The request never got an HTTP response: routing, security group, or a LIF that
    is not listening. This is the only class the old advice was written for."""

    CREDENTIALS_REJECTED = "CREDENTIALS_REJECTED"
    """ONTAP answered, and refused the credentials. The secret's contents, not the
    network."""

    NOT_FOUND = "NOT_FOUND"
    """ONTAP answered and was happy to; the SVM or volume named in the configuration
    does not exist on this cluster."""

    ONTAP_ERROR = "ONTAP_ERROR"
    """Anything else ONTAP said, passed through with its status and message rather than
    flattened into one of the above."""


@dataclass(frozen=True)
class OntapDiagnosis:
    """A failure, its class, and the fact that distinguishes it from the others."""

    failure: OntapFailure
    message: str
    """One sentence, in English, naming what to look at. The UI translates by class and
    shows this as the detail."""

    status: int | None = None
    """The HTTP status, when there was a response. Absent means there was none, which is
    itself the finding."""

    ontap_code: str | None = None
    """ONTAP's own error code, which is what a support case will ask for."""

    def as_dict(self) -> dict[str, Any]:
        """The shape the handlers put on the wire.

        `error` stays a plain string so the existing panels keep working while they are
        migrated; `errorClass` is what the new UI switches on.
        """
        payload: dict[str, Any] = {"error": self.message, "errorClass": self.failure.value}
        if self.status is not None:
            payload["errorStatus"] = self.status
        if self.ontap_code:
            payload["errorCode"] = self.ontap_code
        return payload


# ONTAP answers an unauthenticated or unauthorised call with either of these, depending
# on version and endpoint, and the body says "User is not authorized." for both. Which
# one arrived is worth reporting -- 401 points at the password, 403 at the role -- but
# both send the reader to the same place, so they share a class.
_AUTH_STATUSES = (401, 403)


def diagnose_response(
    status: int,
    body: bytes | str,
    *,
    expected_records: bool = True,
    subject: str = "",
) -> OntapDiagnosis | None:
    """Classify a response. Returns None when the response is usable.

    Args:
        status: the HTTP status ONTAP returned.
        body: the raw response body.
        expected_records: whether this call was a collection query whose emptiness means
            "the thing you named is not here". A single-object GET has no `records`, so
            its absence is not a finding.
        subject: what was being looked for, for the message -- `volume 'vol1' on SVM
            'fsxsvm01'`.

    Returns:
        A diagnosis, or None if the call succeeded and returned what it should.
    """
    parsed = _parse(body)
    ontap_message = _ontap_message(parsed)
    ontap_code = _ontap_code(parsed)

    if status in _AUTH_STATUSES:
        return OntapDiagnosis(
            failure=OntapFailure.CREDENTIALS_REJECTED,
            message=(
                f"ONTAP refused the credentials (HTTP {status}"
                + (f": {ontap_message}" if ontap_message else "")
                + "). The request reached the cluster, so this is the secret's contents "
                "rather than the network."
            ),
            status=status,
            ontap_code=ontap_code,
        )

    if status >= 400:
        return OntapDiagnosis(
            failure=OntapFailure.ONTAP_ERROR,
            message=f"ONTAP returned HTTP {status}" + (f": {ontap_message}" if ontap_message else ""),
            status=status,
            ontap_code=ontap_code,
        )

    # A 2xx whose body is an ONTAP error object. Rare, and it used to be indistinguishable
    # from an empty collection.
    if ontap_message and "records" not in parsed:
        return OntapDiagnosis(
            failure=OntapFailure.ONTAP_ERROR,
            message=f"ONTAP returned {status} with an error body: {ontap_message}",
            status=status,
            ontap_code=ontap_code,
        )

    if expected_records and not parsed.get("records"):
        return OntapDiagnosis(
            failure=OntapFailure.NOT_FOUND,
            message=(
                f"ONTAP answered normally and has no {subject or 'matching object'}. "
                "The connection works; the name in the configuration does not match this "
                "cluster."
            ),
            status=status,
        )

    return None


def diagnose_exception(error: BaseException, *, mgmt_ip: str = "") -> OntapDiagnosis:
    """Classify a request that never produced a response.

    urllib3 wraps a refused connection, a DNS failure and a timeout in different
    exception types, and the distinction does not change what the reader does about it:
    nothing answered on TCP/443. What matters is saying so, rather than reporting it as a
    missing volume.
    """
    where = f" at {mgmt_ip}" if mgmt_ip else ""
    return OntapDiagnosis(
        failure=OntapFailure.UNREACHABLE,
        message=(
            f"No response from the ONTAP management LIF{where}: {type(error).__name__}. "
            "Check the route from the Lambda subnet, the security group on TCP/443, and "
            "that the management IP is the one for this file system."
        ),
    )


def not_configured(missing: list[str]) -> OntapDiagnosis:
    """The deployment did not supply what the handler needs."""
    return OntapDiagnosis(
        failure=OntapFailure.NOT_CONFIGURED,
        message="ONTAP connection not configured; missing: " + ", ".join(sorted(missing)),
    )


def _parse(body: bytes | str) -> dict[str, Any]:
    """The body as a dict, or an empty one. A body that is not JSON is not a crash."""
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _ontap_message(parsed: dict[str, Any]) -> str:
    error = parsed.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        return str(message) if message else ""
    return str(error) if error else ""


def _ontap_code(parsed: dict[str, Any]) -> str | None:
    error = parsed.get("error")
    if isinstance(error, dict) and error.get("code"):
        return str(error["code"])
    return None
