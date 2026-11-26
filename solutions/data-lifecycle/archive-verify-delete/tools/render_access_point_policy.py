#!/usr/bin/env python3
"""Render the S3 Access Point policy this pattern needs, from the stack's outputs.

An FSx for ONTAP S3 Access Point authorizes a request twice: the caller's IAM policy and the access
point's own policy must both allow it. CloudFormation cannot attach the second one, so the deployer
does, after the stack exists:

    aws cloudformation describe-stacks --stack-name <stack> --query 'Stacks[0].Outputs' > outputs.json
    python3 tools/render_access_point_policy.py --outputs outputs.json \\
        --access-point-arn arn:aws:s3:<region>:<account>:accesspoint/<name> > ap-policy.json
    aws s3control put-access-point-policy --account-id <account> --name <name> --policy file://ap-policy.json

Without the policy the first S3 call through the Access Point is denied at run time; the template
and the IAM roles deploy fine without it.

The rendering splits the permissions the way the template's IAM does, so that each right sits with the
smallest set of principals that needs it:

* ``s3:DeleteObject``: the delete function's role only
* ``s3:PutObject`` (and abort of a multipart upload): the restore state machine and the restore Fargate
  task role only. They write restored files back
* ``s3:GetObject``: everything that reads the file (select, record, delete's HeadObject, restore verify,
  the archive copy)
* ``s3:ListBucket``: select, delete, the restore function and the two Fargate roles. Every principal that
  reads a 404 from HeadObject as "the file is not there" needs it: without ListBucket S3 answers a missing
  key with 403, which looks like a permission error and not like an absent file
"""

from __future__ import annotations

import argparse
import json
import sys

# output key -> short name used in the statements
READERS = (
    "SelectRoleArn",
    "RecordRoleArn",
    "DeleteRoleArn",
    "RestoreFunctionRoleArn",
    "ArchiveStateMachineRoleArn",
    "FargateTaskRoleArn",
    "FargateRestoreTaskRoleArn",
)
LISTERS = (
    "SelectRoleArn",
    "DeleteRoleArn",
    "RestoreFunctionRoleArn",
    "FargateTaskRoleArn",
    "FargateRestoreTaskRoleArn",
)
DELETERS = ("DeleteRoleArn",)
WRITERS = ("RestoreStateMachineRoleArn", "FargateRestoreTaskRoleArn")
REQUIRED = (
    "SelectRoleArn",
    "RecordRoleArn",
    "DeleteRoleArn",
    "RestoreFunctionRoleArn",
    "ArchiveStateMachineRoleArn",
    "RestoreStateMachineRoleArn",
)


def outputs_to_dict(outputs) -> dict[str, str]:
    """Accept ``describe-stacks`` Outputs (a list of OutputKey/OutputValue) or a plain mapping."""
    if isinstance(outputs, dict):
        return {str(k): str(v) for k, v in outputs.items()}
    return {o["OutputKey"]: o["OutputValue"] for o in outputs}


def render(outputs: dict[str, str], access_point_arn: str) -> dict:
    if not access_point_arn.startswith("arn:") or ":accesspoint/" not in access_point_arn:
        raise ValueError("access point ARN must look like arn:aws:s3:<region>:<account>:accesspoint/<name>")
    missing = [k for k in REQUIRED if not outputs.get(k)]
    if missing:
        raise ValueError(f"stack outputs missing: {', '.join(missing)}")

    def principals(keys) -> list[str]:
        return [outputs[k] for k in keys if outputs.get(k)]

    objects = f"{access_point_arn}/object/*"
    statements = [
        {
            "Sid": "ReadFiles",
            "Effect": "Allow",
            "Principal": {"AWS": principals(READERS)},
            "Action": ["s3:GetObject"],
            "Resource": [objects],
        },
        {
            "Sid": "ListFiles",
            "Effect": "Allow",
            "Principal": {"AWS": principals(LISTERS)},
            "Action": ["s3:ListBucket"],
            "Resource": [access_point_arn],
        },
        {
            "Sid": "DeleteOnlyByTheDeleteFunction",
            "Effect": "Allow",
            "Principal": {"AWS": principals(DELETERS)},
            "Action": ["s3:DeleteObject"],
            "Resource": [objects],
        },
        {
            "Sid": "WriteOnlyForRestore",
            "Effect": "Allow",
            "Principal": {"AWS": principals(WRITERS)},
            "Action": ["s3:PutObject", "s3:AbortMultipartUpload"],
            "Resource": [objects],
        },
    ]
    return {"Version": "2012-10-17", "Statement": statements}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--outputs", required=True, help="JSON from `aws cloudformation describe-stacks --query Stacks[0].Outputs`"
    )
    parser.add_argument("--access-point-arn", required=True)
    args = parser.parse_args(argv)
    with open(args.outputs, encoding="utf-8") as f:
        outputs = outputs_to_dict(json.load(f))
    try:
        policy = render(outputs, args.access_point_arn)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    json.dump(policy, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
