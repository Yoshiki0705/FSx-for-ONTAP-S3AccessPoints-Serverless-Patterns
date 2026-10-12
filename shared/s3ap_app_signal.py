"""Dependency-free CloudWatch EMF + X-Ray instrumentation for Lambda handlers.

Why this module has no third-party dependency
---------------------------------------------
The previous version of this file imported ``aws_lambda_powertools``. That
package is installed nowhere in this repository -- there is no runtime
``requirements.txt``, no Lambda Layer that carries it, and no template that
adds a Powertools layer ARN. Meanwhile ``shared/python/build-layer.sh`` globs
``shared/python/*.py`` into the shared layer, so the module *was* shipped to
Lambda while being unimportable there. Nothing imported it, so the breakage
stayed latent.

It is also consumed across repository boundaries: the Amplify Gen2 file portal
in ``FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns`` bundles its own Python dependencies
through Amplify's own packaging, so a drop-in module that needs a extra layer
attached is materially harder to adopt than one that needs none.

Hence: standard library only. CloudWatch Embedded Metric Format (EMF) needs
nothing but ``print``, and X-Ray degrades to a no-op when its SDK is absent.

What it provides
----------------
1. :class:`EmfMetrics` -- CloudWatch custom metrics via EMF, no ``PutMetricData``
   call and therefore no IAM permission and no API latency in the handler.
2. :func:`xray_subsegment` / :func:`xray_annotate` -- X-Ray custom subsegments
   and annotations, no-op when ``aws_xray_sdk`` is missing or
   ``ENABLE_XRAY=false``.
3. :func:`instrument_handler` -- one decorator that produces duration, success
   and error metrics for a Lambda handler.
4. :func:`emit_s3ap_app_signal` and the join-key helpers -- the application-layer
   half of correlating a portal request against an FSx for ONTAP audit log
   entry. See "Join-key correlation" below.

Join-key correlation
--------------------
FSx for ONTAP audit records have **no free-form field**, so a trace ID cannot be
propagated into them. The normalized audit schema
(``shared/python/ontap_audit_parser.py``) is exactly: timestamp, event_type,
source, svm, user, domain, client_ip, operation, access_protocol, path, result,
raw.

Two of those look like identity and are not, for traffic arriving over an S3
access point:

* ``user`` / ``domain`` -- ONTAP writes the literal string ``"Not Present"`` for
  the subject attributes of every operation on the S3 access path. The parser
  normalizes that to ``""``. Separately, an S3 access point attaches with a
  single ``FileSystemIdentity``, so even a populated subject would be that one
  identity rather than the end user.
* ``client_ip`` -- the address ONTAP saw. A Lambda outside the VPC reaching an
  Internet-origin access point presents its egress address, not the browser's.

What remains is the object path, the operation and the time. So correlation is a
deterministic join on ``(object key, operation, time window)``, and the end-user
attribution is supplied by the *application* side of the join -- carried here as
an X-Ray annotation and an EMF property.

Usage::

    from observability import (
        EmfMetrics, instrument_handler, emit_s3ap_app_signal,
    )

    @instrument_handler(namespace="FSxONTAPAppSignals", service="portal-list-files")
    def lambda_handler(event, context):
        emit_s3ap_app_signal(
            object_key="data/object.txt",
            operation="GET",
            principal=event["identity"]["sub"],
        )

Environment variables
---------------------
``ENABLE_S3AP_APP_SIGNAL``    Opt-in for :func:`emit_s3ap_app_signal`. Default
                              ``false`` -- the function emits nothing until this
                              is set to ``true``/``1``/``yes``.
``ENABLE_XRAY``               ``false`` disables subsegments and annotations.
``EMF_NAMESPACE``             Default CloudWatch namespace.
``ENVIRONMENT``               Value of the ``Environment`` dimension.
``APP_SIGNAL_HASH_PRINCIPAL`` ``false`` records the principal verbatim instead
                              of hashing it. Default is to hash.
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
import re
import time
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)

# CloudWatch rejects metric names outside this shape, and rejects them at
# ingestion time rather than at flush time -- meaning a bad name is silently
# absent from the console rather than raising in the handler. Validated here so
# the failure is loud and local.
_METRIC_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")
_METRIC_NAME_MAX_LENGTH = 256

# The EMF units this module accepts. CloudWatch defines more; this is the subset
# the callers here need, kept closed so a typo does not become a dropped metric.
_VALID_UNITS = frozenset({"Count", "Milliseconds", "Seconds", "Bytes", "Kilobytes", "Megabytes", "Percent", "None"})

# CloudWatch caps a single EMF record at 100 metric definitions.
_MAX_METRICS_PER_RECORD = 100

# CloudWatch caps a dimension set at 30 dimensions.
_MAX_DIMENSIONS = 30

DEFAULT_NAMESPACE = "FSxONTAPObservability"
APP_SIGNAL_NAMESPACE = "FSxONTAPAppSignals"

# --- Metric names ----------------------------------------------------------
# Only names this module actually emits. An earlier version also carried a set of
# aspirational constants for shipper handlers -- RecordsShipped, DeliveryFailures
# and similar -- that nothing referenced. They were inherited from the dead
# Powertools-based module this replaced, and keeping them would have reproduced
# the problem being fixed: exported names with no caller, which drift from
# whatever the handlers actually emit and mislead the next reader.


# Handler-level metrics produced by instrument_handler.
METRIC_HANDLER_DURATION_MS = "HandlerDurationMs"
METRIC_HANDLER_SUCCESS = "HandlerSuccess"
METRIC_HANDLER_ERRORS = "HandlerErrors"
METRIC_COLD_START = "ColdStart"

# Application-layer signal metrics.
METRIC_S3AP_OPERATIONS = "S3apOperations"

# --- Cold start detection --------------------------------------------------
# Module import happens once per execution environment, so a module-level flag
# distinguishes the first invocation in that environment from later ones.
_COLD_START = True


def _is_xray_enabled() -> bool:
    return os.environ.get("ENABLE_XRAY", "true").strip().lower() not in {"false", "0", "no"}


def _hash_principal_enabled() -> bool:
    return os.environ.get("APP_SIGNAL_HASH_PRINCIPAL", "true").strip().lower() not in {
        "false",
        "0",
        "no",
    }


def _app_signal_enabled() -> bool:
    # Inverted relative to the two helpers above: this signal is sample
    # instrumentation and ships OFF, so an unset variable disables it. Only an
    # explicit opt-in turns it on.
    return os.environ.get("ENABLE_S3AP_APP_SIGNAL", "false").strip().lower() in {
        "true",
        "1",
        "yes",
    }


# ─── CloudWatch EMF ─────────────────────────────────────────────────────────


class EmfMetrics:
    """Emit CloudWatch custom metrics as an EMF record on stdout.

    CloudWatch Logs extracts the metrics from the record, so the handler needs
    no ``cloudwatch:PutMetricData`` permission and pays no API round trip.

    Cost note: every distinct combination of dimension values is a separate
    custom metric for billing. Adding one dimension with 50 values to a set of
    10 metric names produces 500 custom metrics, not 10. Keep dimension
    cardinality low and put high-cardinality values in *properties* instead --
    properties are searchable in CloudWatch Logs Insights and are not billed as
    metrics.

    Usage::

        metrics = EmfMetrics(namespace="FSxONTAPAppSignals", service="list-files")
        metrics.set_dimension("Operation", "GET")
        metrics.put_metric("S3apOperations", 1, "Count")
        metrics.set_property("object_key", "data/object.txt")
        metrics.flush()
    """

    def __init__(
        self,
        namespace: str | None = None,
        service: str | None = None,
        *,
        environment: str | None = None,
    ) -> None:
        self._namespace = namespace or os.environ.get("EMF_NAMESPACE", DEFAULT_NAMESPACE)
        self._service = service
        self._metrics: list[dict[str, Any]] = []
        self._dimensions: dict[str, str] = {}
        self._properties: dict[str, Any] = {}

        if service:
            self._dimensions["ServiceName"] = service
        self._dimensions["Environment"] = (
            environment if environment is not None else os.environ.get("ENVIRONMENT", "dev")
        )

    # -- mutators ----------------------------------------------------------

    def put_metric(self, name: str, value: float, unit: str = "None") -> None:
        """Add a metric to the pending record.

        Raises:
            ValueError: the name is malformed, the unit is unknown, or the
                record already holds the maximum number of metrics.
        """
        self._validate_metric_name(name)
        if unit not in _VALID_UNITS:
            raise ValueError(f"Invalid unit {unit!r}. Must be one of: {', '.join(sorted(_VALID_UNITS))}")
        if len(self._metrics) >= _MAX_METRICS_PER_RECORD:
            raise ValueError(
                f"An EMF record holds at most {_MAX_METRICS_PER_RECORD} metrics; flush() before adding more"
            )
        self._metrics.append({"Name": name, "Unit": unit, "Value": value})

    def set_dimension(self, name: str, value: str) -> None:
        """Set a dimension. Dimensions multiply billed metric count -- see the
        class docstring before adding one."""
        if not name:
            raise ValueError("Dimension name must not be empty")
        if name not in self._dimensions and len(self._dimensions) >= _MAX_DIMENSIONS:
            raise ValueError(f"A dimension set holds at most {_MAX_DIMENSIONS} dimensions")
        self._dimensions[name] = str(value)

    def set_property(self, name: str, value: Any) -> None:
        """Attach a non-metric field. Not billed as a metric; searchable in
        CloudWatch Logs Insights. This is where high-cardinality values go."""
        if not name:
            raise ValueError("Property name must not be empty")
        self._properties[name] = value

    # -- output ------------------------------------------------------------

    def flush(self) -> dict[str, Any] | None:
        """Write the EMF record to stdout and reset.

        Returns the record that was written, or ``None`` when there was no
        metric to write. Returning it keeps the shape assertable in tests
        without capturing stdout.
        """
        if not self._metrics:
            return None

        record: dict[str, Any] = {
            "_aws": {
                "Timestamp": int(time.time() * 1000),
                "CloudWatchMetrics": [
                    {
                        "Namespace": self._namespace,
                        "Dimensions": [list(self._dimensions.keys())],
                        "Metrics": [{"Name": m["Name"], "Unit": m["Unit"]} for m in self._metrics],
                    }
                ],
            },
        }
        record.update(self._dimensions)
        for metric in self._metrics:
            record[metric["Name"]] = metric["Value"]
        record.update(self._properties)

        print(json.dumps(record, default=str))

        self._metrics = []
        self._properties = {}
        return record

    @staticmethod
    def _validate_metric_name(name: str) -> None:
        if not name:
            raise ValueError("Metric name must not be empty")
        if len(name) > _METRIC_NAME_MAX_LENGTH:
            raise ValueError(
                f"Metric name exceeds {_METRIC_NAME_MAX_LENGTH} characters ({len(name)}): {name[:50]!r}..."
            )
        if not _METRIC_NAME_PATTERN.match(name):
            raise ValueError(
                f"Metric name {name!r} contains characters CloudWatch rejects; use letters, digits and underscore only"
            )


# ─── X-Ray ──────────────────────────────────────────────────────────────────


@contextmanager
def xray_subsegment(
    name: str,
    annotations: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
):
    """Open an X-Ray custom subsegment.

    A no-op pass-through when ``aws_xray_sdk`` is not installed, when
    ``ENABLE_XRAY=false``, or when there is no active segment (which is the
    normal case under pytest). Yields the subsegment, or ``None`` when
    inactive, so a caller can tell whether it got one.
    """
    if not _is_xray_enabled():
        yield None
        return

    try:
        from aws_xray_sdk.core import xray_recorder
    except ImportError:
        logger.debug("aws_xray_sdk absent; subsegment %r skipped", name)
        yield None
        return

    try:
        subsegment = xray_recorder.begin_subsegment(name)
    except Exception as exc:  # pragma: no cover - depends on SDK internals
        # A missing or broken recorder context must not fail the handler whose
        # work this is only describing.
        logger.debug("X-Ray subsegment %r could not begin: %s", name, exc)
        yield None
        return

    if subsegment is None:
        # No active segment: begin_subsegment returns None rather than raising.
        logger.debug("No active X-Ray segment; subsegment %r skipped", name)
        yield None
        return

    try:
        _apply_annotations(subsegment, annotations)
        if metadata:
            for key, value in metadata.items():
                subsegment.put_metadata(key, value)
        yield subsegment
    except Exception as exc:
        subsegment.add_exception(exc)
        raise
    finally:
        xray_recorder.end_subsegment()


def xray_annotate(annotations: dict[str, Any]) -> bool:
    """Annotate the current X-Ray segment or subsegment.

    Annotations are indexed and therefore filterable in the X-Ray console,
    which is what makes them usable as a join key. Returns whether the
    annotations were applied.
    """
    if not _is_xray_enabled() or not annotations:
        return False
    try:
        from aws_xray_sdk.core import xray_recorder
    except ImportError:
        logger.debug("aws_xray_sdk absent; annotations skipped")
        return False
    try:
        entity = xray_recorder.current_subsegment() or xray_recorder.current_segment()
    except Exception as exc:  # pragma: no cover - depends on SDK internals
        logger.debug("No X-Ray entity to annotate: %s", exc)
        return False
    if entity is None:
        return False
    _apply_annotations(entity, annotations)
    return True


def _apply_annotations(entity: Any, annotations: dict[str, Any] | None) -> None:
    """Put annotations on an X-Ray entity, coercing unsupported types.

    X-Ray annotations accept only str, int, float and bool. Anything else is
    dropped by the SDK rather than converted, so it is stringified here -- a
    dropped join key is worse than a stringified one.
    """
    if not annotations:
        return
    for key, value in annotations.items():
        if not isinstance(value, (str, int, float, bool)):
            value = str(value)
        entity.put_annotation(key, value)


# ─── Join-key correlation ───────────────────────────────────────────────────

# ONTAP audit ``ObjectName`` carries the volume in parentheses ahead of the
# in-volume path: "(vol1);/data/object.txt". Captured on FSx for ONTAP,
# ONTAP 9.18.1P3D1, xml audit format -- see
# shared/python/tests/test_ontap_audit_parser.py.
_AUDIT_PATH_VOLUME_PREFIX = re.compile(r"^\((?P<volume>[^)]*)\);")

# ONTAP audit ``EventName`` values observed on the S3 access path, mapped onto
# the S3 verb an application would recognise.
#
# Every entry is confirmed against captured audit output. An EventName absent
# from this table is normalized by _normalize_operation instead of being guessed
# at, because a wrong guess produces a join key that silently never matches.
#
# Measured 2026-08-30 on FSx for ONTAP, ONTAP 9.18.1P3D1, xml audit format, on a
# mixed-security-style volume reached through an S3 access point with a WINDOWS
# file-system identity:
#
#   PUT    -> EventID 4656, EventName "Create Object",   Source HTTP
#   GET    -> EventID 4663, EventName "Read Object",     Source HTTP
#   LIST   -> EventID 4663, EventName "S3A List Object", Source S3
#   DELETE -> EventID 9998, EventName "Unlink Object",   Source HTTP
#
# "Write Object" is carried over from earlier captured output on the same ONTAP
# release; ONTAP audits an upload as Create and, for a rewrite, as Write, so both
# map to PUT.
ONTAP_EVENT_TO_S3_VERB = {
    "Create Object": "PUT",
    "Write Object": "PUT",
    "Read Object": "GET",
    "S3A List Object": "LIST",
    "Unlink Object": "DELETE",
}

# The access_protocol values that mean "this operation arrived over the S3
# access point" rather than over SMB or NFS. ONTAP uses HTTP for object
# operations and S3 for bucket-level ones.
S3_ACCESS_PROTOCOLS = frozenset({"HTTP", "S3"})

# Events the audit subsystem writes about *itself*. They are not file operations
# and must not produce a join key.
#
# Found by running the correlator against a real audit volume. These records
# carry ``Source`` = ``http``, so the access-path filter lets them through, and
# they have no object path, so each one would emit a join key with an empty
# object key.
#
# **The EventID is the reliable signal, not the name.** Two different names were
# observed on the same ID: `Audit Enabled` in the active log and `Audit Policy
# Changed` in a rotated one, both EventID 4719. Enumerating names alone missed
# the second and it was excluded only incidentally, by having no path.
AUDIT_MANAGEMENT_EVENT_IDS = frozenset({"4719"})

AUDIT_MANAGEMENT_EVENTS = frozenset(
    {
        "Audit Enabled",
        "Audit Disabled",
        "Audit Policy Changed",
    }
)


def audit_path_to_object_key(audit_path: str) -> str:
    """Convert an ONTAP audit path to the S3 object key that produced it.

    ``"(vol1);/data/object.txt"`` becomes ``"data/object.txt"``.

    The volume prefix is stripped because it names the ONTAP volume, not part
    of the key, and the leading slash is stripped because an S3 key has none.
    Splitting happens on the first ``);`` only, so a path that itself contains
    that sequence survives.
    """
    if not audit_path:
        return ""
    stripped = _AUDIT_PATH_VOLUME_PREFIX.sub("", audit_path.strip(), count=1)
    return stripped.lstrip("/")


def audit_path_volume(audit_path: str) -> str:
    """Return the volume name from an ONTAP audit path, or ``""`` if absent."""
    if not audit_path:
        return ""
    match = _AUDIT_PATH_VOLUME_PREFIX.match(audit_path.strip())
    return match.group("volume") if match else ""


def _normalize_operation(operation: str) -> str:
    """Reduce an operation name to a comparable token.

    Applied to both sides of the join so that an ONTAP ``EventName`` and an
    application's S3 verb land on the same string when they mean the same
    thing.
    """
    if not operation:
        return ""
    mapped = ONTAP_EVENT_TO_S3_VERB.get(operation.strip())
    if mapped:
        return mapped
    return re.sub(r"\s+", "_", operation.strip()).upper()


def normalize_object_key(object_key: str) -> str:
    """Reduce an S3 object key to the form used in a join key."""
    return (object_key or "").strip().lstrip("/")


def s3ap_join_key(object_key: str, operation: str) -> str:
    """Build the deterministic join key for one S3 access point operation.

    The same key must be derivable from either side of the correlation:

    * application side -- from the object key it asked for and the S3 verb it
      used;
    * audit side -- from :func:`audit_path_to_object_key` on ``path`` and the
      ``operation`` field.

    The key deliberately excludes time. Time is the third element of the join
    and is matched as a *window*, because the application timestamp and the
    ONTAP timestamp are taken by different clocks at different points in the
    request.
    """
    return f"{_normalize_operation(operation)}|{normalize_object_key(object_key)}"


def join_key_from_audit_event(event: dict[str, Any]) -> str:
    """Build the join key from a normalized audit event.

    Expects the schema produced by ``ontap_audit_parser.normalize_event``.
    """
    return s3ap_join_key(
        object_key=audit_path_to_object_key(event.get("path", "")),
        operation=event.get("operation", ""),
    )


def is_s3_access_path(event: dict[str, Any]) -> bool:
    """Whether a normalized audit event arrived over the S3 access point.

    Filtering on this before joining avoids matching an SMB or NFS operation on
    the same file, which would attribute a file-protocol access to a portal
    user who never made it.

    Note that this is necessary but not sufficient for a joinable record --
    see :func:`is_joinable_audit_event`.
    """
    return str(event.get("access_protocol", "")).strip().upper() in S3_ACCESS_PROTOCOLS


def is_audit_management_event(event: dict[str, Any]) -> bool:
    """Whether the record describes the audit subsystem rather than a file.

    Matched on EventID first, because the same ID was observed carrying two
    different names. The name set is the fallback for inputs where the ID did
    not survive normalization.
    """
    if str(event.get("event_type", "")).strip() in AUDIT_MANAGEMENT_EVENT_IDS:
        return True
    return str(event.get("operation", "")).strip() in AUDIT_MANAGEMENT_EVENTS


def is_joinable_audit_event(event: dict[str, Any]) -> bool:
    """Whether a normalized audit event can take part in the correlation.

    Three conditions, each of which was needed in practice:

    1. it arrived over the S3 access path, so an SMB or NFS touch of the same
       file is not attributed to an application user;
    2. it is not the audit subsystem describing itself;
    3. it has a path. A record with no path cannot be joined to an object, and
       emitting one produces a key that matches every other pathless record.
       A LIST is *not* excluded by this: its path is the volume root
       (``(vol);/``), which is non-empty even though the object key is.
    """
    return (
        is_s3_access_path(event) and not is_audit_management_event(event) and bool(str(event.get("path", "")).strip())
    )


def principal_token(principal: str) -> str:
    """Reduce an end-user identifier to what should be recorded.

    Hashed by default. A Cognito subject is a pseudonymous identifier rather
    than a name, but it is still an identifier for a natural person, and this
    value lands in CloudWatch Logs and in X-Ray annotations, which have their
    own retention and their own readers. Set
    ``APP_SIGNAL_HASH_PRINCIPAL=false`` to record it verbatim where the
    deployment has decided that is appropriate.

    The digest is truncated to 16 hex characters: enough to distinguish users
    within a deployment, short enough to read in a console.
    """
    if not principal:
        return ""
    if not _hash_principal_enabled():
        return principal
    return hashlib.sha256(principal.encode("utf-8")).hexdigest()[:16]


def emit_s3ap_app_signal(
    object_key: str,
    operation: str,
    *,
    principal: str = "",
    metrics: EmfMetrics | None = None,
    namespace: str | None = None,
    service: str | None = None,
    extra_properties: dict[str, Any] | None = None,
    flush: bool = True,
) -> dict[str, Any]:
    """Record the application-layer half of one S3 access point operation.

    Emits the join key twice, because the two consumers index differently:

    * as an **X-Ray annotation** (``s3ap_join_key``), which X-Ray indexes and
      can therefore be filtered on to find the trace for a given audit entry;
    * as an **EMF property**, which lands in CloudWatch Logs and is queryable
      from Logs Insights alongside the audit log records.

    The object key goes in a property rather than a dimension so that key
    cardinality does not multiply the billed custom metric count.

    Returns the signal fields that were emitted, so a caller (or a test) can
    assert on them without capturing stdout or standing up X-Ray.

    Off by default. Gated on ``ENABLE_S3AP_APP_SIGNAL`` so a deployment that
    has not opted in emits nothing -- no EMF record, no metric, no X-Ray
    annotation -- and the function returns an empty dict to signal that.
    """
    if not _app_signal_enabled():
        return {}

    key = s3ap_join_key(object_key, operation)
    token = principal_token(principal)
    verb = _normalize_operation(operation)
    normalized_key = normalize_object_key(object_key)

    signal: dict[str, Any] = {
        "s3ap_join_key": key,
        "s3ap_object_key": normalized_key,
        "s3ap_operation": verb,
        "app_signal_emitted_at_ms": int(time.time() * 1000),
    }
    if token:
        signal["app_principal"] = token

    owned = metrics is None
    sink = metrics or EmfMetrics(
        namespace=namespace or APP_SIGNAL_NAMESPACE,
        service=service,
    )
    sink.set_dimension("Operation", verb or "UNKNOWN")
    sink.put_metric(METRIC_S3AP_OPERATIONS, 1, "Count")
    for name, value in signal.items():
        sink.set_property(name, value)
    if extra_properties:
        for name, value in extra_properties.items():
            sink.set_property(name, value)

    # Annotations are indexed by X-Ray and so are filterable; the object key is
    # attached as metadata instead, since it is not something to filter on and
    # may be long.
    xray_annotate(
        {
            "s3ap_join_key": key,
            "s3ap_operation": verb,
            **({"app_principal": token} if token else {}),
        }
    )

    if flush and owned:
        sink.flush()
    return signal


# ─── Handler instrumentation ────────────────────────────────────────────────


def instrument_handler(
    namespace: str | None = None,
    service: str | None = None,
    *,
    capture_cold_start: bool = True,
):
    """Decorate a Lambda handler with duration, outcome and cold-start metrics.

    Produces ``HandlerDurationMs``, ``HandlerSuccess``, ``HandlerErrors`` and
    (on the first invocation in an execution environment) ``ColdStart``, and
    wraps the call in an X-Ray subsegment when X-Ray is available.

    The metrics are flushed in a ``finally`` block so a raising handler still
    reports its duration and its error -- an error metric that only appears
    when the handler succeeds is worse than none.

    Usage::

        @instrument_handler(namespace="FSxONTAPAppSignals", service="list-files")
        def lambda_handler(event, context):
            ...
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(event, context=None):
            global _COLD_START
            cold = _COLD_START
            _COLD_START = False

            resolved_service = service or str(getattr(context, "function_name", None) or func.__name__)
            metrics = EmfMetrics(
                namespace=namespace or os.environ.get("EMF_NAMESPACE", DEFAULT_NAMESPACE),
                service=resolved_service,
            )

            started = time.perf_counter()
            success = False
            try:
                with xray_subsegment(
                    name=f"{resolved_service}.handler",
                    annotations={
                        "service_name": resolved_service,
                        "operation": "lambda_handler",
                        "cold_start": cold,
                    },
                ):
                    result = func(event, context)
                success = True
                return result
            finally:
                elapsed_ms = (time.perf_counter() - started) * 1000
                metrics.put_metric(METRIC_HANDLER_DURATION_MS, elapsed_ms, "Milliseconds")
                metrics.put_metric(METRIC_HANDLER_SUCCESS, 1 if success else 0, "Count")
                metrics.put_metric(METRIC_HANDLER_ERRORS, 0 if success else 1, "Count")
                if capture_cold_start and cold:
                    metrics.put_metric(METRIC_COLD_START, 1, "Count")
                aws_request_id = getattr(context, "aws_request_id", None)
                if aws_request_id:
                    metrics.set_property("aws_request_id", aws_request_id)
                metrics.flush()

        return wrapper

    return decorator


__all__ = [
    "APP_SIGNAL_NAMESPACE",
    "DEFAULT_NAMESPACE",
    "METRIC_COLD_START",
    "METRIC_HANDLER_DURATION_MS",
    "METRIC_HANDLER_ERRORS",
    "METRIC_HANDLER_SUCCESS",
    "METRIC_S3AP_OPERATIONS",
    "ONTAP_EVENT_TO_S3_VERB",
    "AUDIT_MANAGEMENT_EVENTS",
    "AUDIT_MANAGEMENT_EVENT_IDS",
    "S3_ACCESS_PROTOCOLS",
    "EmfMetrics",
    "audit_path_to_object_key",
    "audit_path_volume",
    "emit_s3ap_app_signal",
    "instrument_handler",
    "is_audit_management_event",
    "is_joinable_audit_event",
    "is_s3_access_path",
    "join_key_from_audit_event",
    "normalize_object_key",
    "principal_token",
    "s3ap_join_key",
    "xray_annotate",
    "xray_subsegment",
]
