"""Runtime configuration shared by the handlers and the Fargate entrypoint."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

import boto3

from shared.archive_verify.plan import DEFAULT_THRESHOLD_BYTES

MANIFEST_PREFIX = "manifests/"


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
            map_concurrency=int(env.get("MAP_CONCURRENCY", "10")),
            restore_poll_minutes=int(env.get("RESTORE_POLL_MINUTES", "30")),
            restore_max_wait_hours=int(env.get("RESTORE_MAX_WAIT_HOURS", "72")),
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
        }


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
