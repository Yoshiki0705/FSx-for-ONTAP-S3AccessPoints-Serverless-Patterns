"""Runtime configuration shared by the handlers and the Fargate entrypoint."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

import boto3

from shared.archive_verify.plan import DEFAULT_MIN_FILE_BYTES, DEFAULT_THRESHOLD_BYTES, SelectionFilters
from shared.data_classification import DataClassification

MANIFEST_PREFIX = "manifests/"

# Ledger, manifests and results carry file paths, and a path can hold a person's name, a
# patient or case identifier. RESTRICTED is the label shared/data_classification.py defines for
# data with limited access; the stack parameter DataClassification can raise or lower it.
DEFAULT_CLASSIFICATION = DataClassification.RESTRICTED.value


def _split(value: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in value.split(",") if x.strip())


def _classification(value: str) -> str:
    try:
        return DataClassification(value.upper()).value
    except ValueError:
        return DEFAULT_CLASSIFICATION


@dataclass(frozen=True)
class RuntimeConfig:
    access_point: str
    archive_bucket: str
    archive_prefix: str
    second_copy_bucket: str
    ledger_table: str
    threshold_bytes: int
    fargate_enabled: bool
    ontap_enabled: bool
    approval_timeout_seconds: int
    sns_topic_arn: str
    stack_name: str
    fargate_subnets: tuple[str, ...]
    fargate_security_groups: tuple[str, ...]
    fargate_assign_public_ip: str
    map_concurrency: int
    restore_poll_minutes: int
    restore_max_wait_hours: int
    min_file_bytes: int
    exclude_patterns: tuple[str, ...]
    exclude_prefixes: tuple[str, ...]
    require_separate_approver: bool
    fargate_timeout_seconds: int
    data_classification: str
    approval_validity_hours: float
    approval_token_key_id: str

    @classmethod
    def from_env(cls) -> RuntimeConfig:
        env = os.environ
        return cls(
            access_point=env.get("ACCESS_POINT", ""),
            archive_bucket=env.get("ARCHIVE_BUCKET", ""),
            archive_prefix=env.get("ARCHIVE_PREFIX", "data/"),
            second_copy_bucket=env.get("SECOND_COPY_BUCKET", ""),
            ledger_table=env.get("LEDGER_TABLE", ""),
            threshold_bytes=int(env.get("LARGE_FILE_THRESHOLD_BYTES", DEFAULT_THRESHOLD_BYTES)),
            fargate_enabled=env.get("FARGATE_ENABLED", "false") == "true",
            ontap_enabled=env.get("ONTAP_ENABLED", "false") == "true",
            approval_timeout_seconds=int(env.get("APPROVAL_TIMEOUT_HOURS", "72")) * 3600,
            sns_topic_arn=env.get("SNS_TOPIC_ARN", ""),
            stack_name=env.get("STACK_NAME", ""),
            fargate_subnets=tuple(x for x in env.get("FARGATE_SUBNETS", "").split(",") if x),
            fargate_security_groups=tuple(x for x in env.get("FARGATE_SECURITY_GROUPS", "").split(",") if x),
            fargate_assign_public_ip=env.get("FARGATE_ASSIGN_PUBLIC_IP", "DISABLED"),
            map_concurrency=int(env.get("MAP_CONCURRENCY", "1")),
            restore_poll_minutes=int(env.get("RESTORE_POLL_MINUTES", "30")),
            restore_max_wait_hours=int(env.get("RESTORE_MAX_WAIT_HOURS", "72")),
            min_file_bytes=int(env.get("MIN_FILE_BYTES", DEFAULT_MIN_FILE_BYTES)),
            exclude_patterns=_split(env.get("EXCLUDE_PATTERNS", "")),
            exclude_prefixes=_split(env.get("EXCLUDE_PREFIXES", "")),
            require_separate_approver=env.get("REQUIRE_SEPARATE_APPROVER", "true") != "false",
            fargate_timeout_seconds=int(env.get("FARGATE_TIMEOUT_SECONDS", "7200")),
            data_classification=_classification(env.get("DATA_CLASSIFICATION", "")),
            approval_validity_hours=float(env.get("APPROVAL_VALIDITY_HOURS", "24")),
            approval_token_key_id=env.get("APPROVAL_TOKEN_KEY_ID", ""),
        )

    def public(self) -> dict:
        """The part of the configuration the state machine reads (no ARNs of secrets)."""
        return {
            "accessPoint": self.access_point,
            "archiveBucket": self.archive_bucket,
            "archivePrefix": self.archive_prefix,
            "secondCopyBucket": self.second_copy_bucket,
            "largeFileThresholdBytes": self.threshold_bytes,
            "fargateEnabled": self.fargate_enabled,
            "approvalTimeoutSeconds": self.approval_timeout_seconds,
            "fargateSubnets": list(self.fargate_subnets),
            "fargateSecurityGroups": list(self.fargate_security_groups),
            "fargateAssignPublicIp": self.fargate_assign_public_ip,
            "mapConcurrency": self.map_concurrency,
            "fargateTimeoutSeconds": self.fargate_timeout_seconds,
            "requireSeparateApprover": self.require_separate_approver,
        }

    def default_filters(self) -> SelectionFilters:
        """Stack-level selection filters (minimum size and exclusions)."""
        return SelectionFilters(
            min_size_bytes=self.min_file_bytes,
            exclude_patterns=self.exclude_patterns,
            exclude_prefixes=self.exclude_prefixes,
        )

    def classification_fields(self) -> dict:
        """``data_classification`` and its label, as other patterns write them."""
        c = DataClassification(self.data_classification)
        return {"data_classification": c.value, "data_classification_label": c.label}


def put_json(bucket: str, key: str, body, session: boto3.Session | None = None) -> None:
    """Write ``body`` as JSON to a regular (non Access Point) bucket."""
    (session or boto3.Session()).client("s3").put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(body, ensure_ascii=False, default=str).encode("utf-8"),
        ContentType="application/json",
    )


def get_json(bucket: str, key: str, session: boto3.Session | None = None):
    """Read a JSON document from a regular bucket."""
    resp = (session or boto3.Session()).client("s3").get_object(Bucket=bucket, Key=key)
    return json.loads(resp["Body"].read())
