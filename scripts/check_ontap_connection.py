#!/usr/bin/env python3
"""Say which link in the ONTAP chain is broken, before anyone opens the portal.

Why this exists
---------------
The portal reported

    Volume 'vol1' not found on SVM 'fsxsvm01'

under the heading "ONTAP connection required", with advice about the VPC, the subnet
and the security group. Every one of those was fine. `aws fsx describe-volumes` listed
that volume, in that SVM, as CREATED. The request had reached the cluster over TLS.
ONTAP had answered

    {"error": {"message": "User is not authorized."}}

because the password in Secrets Manager no longer matched the one the file system held.
The handler checked only whether a `records` key came back, so an authorisation failure
and a missing volume were the same event to it.

Six things have to line up for an ONTAP panel to show data, and a failure in any of
them used to produce the same sentence. This walks them in order and names the one that
broke, so the reader spends their time on the right layer.

    1. configuration   the four values the portal needs were supplied
    2. file system     it exists, it is AVAILABLE, and the management IP is its own
    3. SVM             the configured name exists on that file system
    4. volume          the configured name exists on that SVM, and is CREATED
    5. secret          it exists, is JSON, and carries a username and a password
    6. ONTAP auth      ONTAP accepts those credentials

Stage 6 is the one that was wrong and the one hardest to check: the management LIF is
private, so a laptop outside the VPC cannot reach it. Rather than skip it, `--via-lambda`
asks the deployed function -- which is inside the VPC -- to make the call, and reads the
class back out of its answer. That is how the original diagnosis was actually made.

Usage
-----
    # From the portal's config
    python3 scripts/check_ontap_connection.py --config solutions/amplify-portal/amplify/portal-config.ts

    # Explicitly
    python3 scripts/check_ontap_connection.py \
        --file-system-id fs-0123456789abcdef0 \
        --svm fsxsvm01 --volume vol1 \
        --secret fsx-ontap-fsxadmin-credentials

    # Include stage 6 by asking the deployed function to make the call
    python3 scripts/check_ontap_connection.py --config <path> \
        --via-lambda amplify-...-ResourceMgmtFunction...

Exit status is 1 if any stage failed, so it can gate a deploy. Stages that could not be
attempted -- no credentials, no --via-lambda -- are reported as SKIP and do not fail.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

# The four values the portal needs, as they are named in portal-config.ts. Read from
# there rather than restated, so a rename is a parse failure and not a silent mismatch.
_CONFIG_KEYS = ("ontapMgmtIp", "ontapSecretName", "ontapVolumeName", "ontapSvmName")


class Outcome(str, Enum):
    OK = "OK"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass
class Stage:
    """One link in the chain, and what it turned out to be."""

    name: str
    outcome: Outcome
    detail: str
    """One sentence. On a failure this is what to do about it, not just what happened."""

    facts: dict[str, str] = field(default_factory=dict)
    """What was observed, so the reader can check the tool's reasoning rather than
    trust it."""


class Aws:
    """The AWS calls this makes, in one place so the tests can replace them.

    Shelling out to the CLI rather than using boto3: this runs before anything is
    deployed, in an environment that has the CLI configured, and the same commands are
    what the reader will paste when they follow the advice. A boto3 traceback is not
    something to hand to somebody debugging their first deployment.
    """

    def __init__(self, region: str | None = None) -> None:
        self.region = region

    def run(self, *args: str) -> tuple[int, str, str]:
        command = ["aws", *args]
        if self.region:
            command += ["--region", self.region]
        try:
            completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
                command, capture_output=True, text=True, timeout=60, check=False
            )
        except FileNotFoundError:
            return 127, "", "aws CLI not found on PATH"
        except subprocess.TimeoutExpired:
            return 124, "", "aws CLI timed out"
        return completed.returncode, completed.stdout, completed.stderr


def parse_portal_config(text: str) -> dict[str, str]:
    """The four ONTAP values out of portal-config.ts.

    A regex rather than a TypeScript parse: requiring node to read a config file would
    make this unusable in the situation it is for.

    Two shapes have to be read. The interface declares `ontapMgmtIp: string;`, which
    carries no value, and the config assigns
    `ontapMgmtIp: process.env.ONTAP_MGMT_IP || "10.0.0.1"`, where the value is the
    fallback. So the pattern takes the first quoted literal after the key on the same
    statement, and the declaration -- having none before its semicolon -- is skipped
    rather than read as an empty value. The environment variable wins at deploy time; if
    one is set here, pass --mgmt-ip and the rest to say so.
    """
    found: dict[str, str] = {}
    for key in _CONFIG_KEYS:
        match = re.search(rf"{key}\s*:\s*[^;\n]*?[\"'`]([^\"'`]*)[\"'`]", text)
        if match:
            found[key] = match.group(1)
    return found


def check_configuration(config: dict[str, str]) -> Stage:
    """Stage 1: were the four values supplied at all."""
    missing = [key for key in _CONFIG_KEYS if not config.get(key)]
    if missing:
        return Stage(
            name="configuration",
            outcome=Outcome.FAIL,
            detail=(
                "Set " + ", ".join(missing) + " in amplify/portal-config.ts and deploy again. Until then the portal "
                "runs in DemoMode: file browsing, AI processing and upload work, and the "
                "ONTAP panels have nothing to show."
            ),
            facts={key: config.get(key, "") for key in _CONFIG_KEYS},
        )
    return Stage(
        name="configuration",
        outcome=Outcome.OK,
        detail="All four values are set.",
        facts={key: config[key] for key in _CONFIG_KEYS},
    )


def check_file_system(aws: Aws, file_system_id: str, mgmt_ip: str) -> tuple[Stage, dict]:
    """Stage 2: the file system exists, is AVAILABLE, and owns that management IP."""
    code, out, err = aws.run(
        "fsx",
        "describe-file-systems",
        "--file-system-ids",
        file_system_id,
        "--output",
        "json",
    )
    if code != 0:
        return (
            Stage(
                name="file system",
                outcome=Outcome.FAIL,
                detail=(
                    f"describe-file-systems failed for {file_system_id}. Check the ID and "
                    "the region, and that these credentials can read FSx."
                ),
                facts={"stderr": err.strip()[:400]},
            ),
            {},
        )

    systems = json.loads(out or "{}").get("FileSystems", [])
    if not systems:
        return (
            Stage(
                name="file system",
                outcome=Outcome.FAIL,
                detail=f"No file system {file_system_id} in this account and region.",
            ),
            {},
        )

    system = systems[0]
    lifecycle = system.get("Lifecycle", "")
    actual_ip = (
        (system.get("OntapConfiguration") or {})
        .get("Endpoints", {})
        .get("Management", {})
        .get("IpAddresses", [None])[0]
    )

    facts = {"Lifecycle": lifecycle, "managementIp": str(actual_ip)}

    if lifecycle != "AVAILABLE":
        return (
            Stage(
                name="file system",
                outcome=Outcome.FAIL,
                detail=(
                    f"The file system is {lifecycle}, not AVAILABLE. Nothing else in this "
                    "chain can succeed until it is."
                ),
                facts=facts,
            ),
            system,
        )

    if mgmt_ip and actual_ip and mgmt_ip != actual_ip:
        # This one is worth its own stage. A management IP left over from a previous
        # file system produces a timeout, which reads as a security group problem.
        return (
            Stage(
                name="file system",
                outcome=Outcome.FAIL,
                detail=(
                    f"ontapMgmtIp is {mgmt_ip}, but this file system's management LIF is "
                    f"{actual_ip}. Requests to the configured address will time out, which "
                    "looks like a network problem and is not one."
                ),
                facts=facts,
            ),
            system,
        )

    return (
        Stage(
            name="file system",
            outcome=Outcome.OK,
            detail="AVAILABLE, and the configured management IP is its own.",
            facts=facts,
        ),
        system,
    )


def check_svm(aws: Aws, file_system_id: str, svm_name: str) -> tuple[Stage, str]:
    """Stage 3: an SVM of that name on that file system. Returns its ID when found."""
    code, out, err = aws.run(
        "fsx",
        "describe-storage-virtual-machines",
        "--filters",
        f"Name=file-system-id,Values={file_system_id}",
        "--output",
        "json",
    )
    if code != 0:
        return (
            Stage(
                name="SVM",
                outcome=Outcome.FAIL,
                detail="describe-storage-virtual-machines failed.",
                facts={"stderr": err.strip()[:400]},
            ),
            "",
        )

    svms = json.loads(out or "{}").get("StorageVirtualMachines", [])
    names = {svm.get("Name", ""): svm for svm in svms}
    if svm_name not in names:
        return (
            Stage(
                name="SVM",
                outcome=Outcome.FAIL,
                detail=(
                    f"No SVM named {svm_name!r} on this file system. It has: "
                    + (", ".join(sorted(n for n in names if n)) or "(none)")
                    + ". Correct ontapSvmName."
                ),
                facts={"configured": svm_name},
            ),
            "",
        )

    svm = names[svm_name]
    lifecycle = svm.get("Lifecycle", "")
    svm_id = svm.get("StorageVirtualMachineId", "")
    facts = {"StorageVirtualMachineId": svm_id, "Lifecycle": lifecycle}
    if lifecycle == "MISCONFIGURED":
        # MISCONFIGURED is usually Active Directory, and it is worth naming because the
        # SVM still answers for everything that does not need the domain.
        return (
            Stage(
                name="SVM",
                outcome=Outcome.FAIL,
                detail=(
                    "The SVM is MISCONFIGURED, which for an AD-joined SVM means it cannot "
                    "reach a domain controller. SMB and WINDOWS-type access points will "
                    "fail while everything else appears healthy."
                ),
                facts=facts,
            ),
            svm_id,
        )
    return (
        Stage(name="SVM", outcome=Outcome.OK, detail=f"{svm_name} is {lifecycle}.", facts=facts),
        svm_id,
    )


def check_volume(aws: Aws, svm_id: str, volume_name: str) -> Stage:
    """Stage 4: a volume of that name on that SVM.

    This is the stage the portal used to blame for every failure, which is why it is
    worth checking separately: when it passes, a "volume not found" from the portal is
    known to be about something else.
    """
    code, out, err = aws.run(
        "fsx",
        "describe-volumes",
        "--filters",
        f"Name=storage-virtual-machine-id,Values={svm_id}",
        "--output",
        "json",
    )
    if code != 0:
        return Stage(
            name="volume",
            outcome=Outcome.FAIL,
            detail="describe-volumes failed.",
            facts={"stderr": err.strip()[:400]},
        )

    volumes = json.loads(out or "{}").get("Volumes", [])
    names = {volume.get("Name", ""): volume for volume in volumes}
    if volume_name not in names:
        return Stage(
            name="volume",
            outcome=Outcome.FAIL,
            detail=(
                f"No volume named {volume_name!r} on this SVM. It has: "
                + (", ".join(sorted(n for n in names if n)) or "(none)")
                + ". Correct ontapVolumeName."
            ),
            facts={"configured": volume_name},
        )

    volume = names[volume_name]
    return Stage(
        name="volume",
        outcome=Outcome.OK,
        detail=f"{volume_name} is {volume.get('Lifecycle', '')}.",
        facts={
            "VolumeId": volume.get("VolumeId", ""),
            "Lifecycle": volume.get("Lifecycle", ""),
            "JunctionPath": (volume.get("OntapConfiguration") or {}).get("JunctionPath", ""),
        },
    )


def check_secret(aws: Aws, secret_name: str) -> Stage:
    """Stage 5: the secret is readable, is JSON, and has both fields.

    The password itself is never printed. Its length is, because a secret written with
    a trailing newline by a shell heredoc is a real and invisible cause of stage 6
    failing, and the length is what shows it.
    """
    code, out, err = aws.run("secretsmanager", "get-secret-value", "--secret-id", secret_name, "--output", "json")
    if code != 0:
        return Stage(
            name="secret",
            outcome=Outcome.FAIL,
            detail=(
                f"Could not read the secret {secret_name!r}. Check the name and that these "
                "credentials -- and the Lambda's role -- may read it."
            ),
            facts={"stderr": err.strip()[:400]},
        )

    try:
        payload = json.loads(json.loads(out or "{}").get("SecretString", ""))
    except (ValueError, TypeError):
        return Stage(
            name="secret",
            outcome=Outcome.FAIL,
            detail=('The secret is not JSON. The portal expects {"username": "fsxadmin", "password": "..."}.'),
        )

    if not isinstance(payload, dict) or not payload.get("password"):
        return Stage(
            name="secret",
            outcome=Outcome.FAIL,
            detail=('The secret has no "password". The portal expects {"username": "fsxadmin", "password": "..."}.'),
        )

    password = str(payload["password"])
    facts = {
        "username": str(payload.get("username", "(absent, defaults to fsxadmin)")),
        "passwordLength": str(len(password)),
    }
    if password != password.strip():
        return Stage(
            name="secret",
            outcome=Outcome.FAIL,
            detail=(
                "The password has leading or trailing whitespace, which ONTAP will not "
                "accept and which nothing in the console will show you. Write it with "
                "--secret-string on one line rather than from a file."
            ),
            facts=facts,
        )

    return Stage(
        name="secret",
        outcome=Outcome.OK,
        detail="Readable, JSON, and carries a username and password.",
        facts=facts,
    )


def check_ontap_auth(aws: Aws, function_name: str) -> Stage:
    """Stage 6: does ONTAP accept the credentials.

    Asked through the deployed function because the management LIF is private. The
    function's answer now carries a class (see shared/ontap_diagnosis.py), so this reads
    the class rather than matching on message text.
    """
    payload = json.dumps({"action": "listVolumes", "userId": "preflight", "groups": ["storage-admin"]})
    code, out, err = aws.run(
        "lambda",
        "invoke",
        "--function-name",
        function_name,
        "--payload",
        payload,
        "--cli-binary-format",
        "raw-in-base64-out",
        "/dev/stdout",
    )
    if code != 0:
        return Stage(
            name="ONTAP auth",
            outcome=Outcome.SKIP,
            detail=f"Could not invoke {function_name}. Check the name and invoke permission.",
            facts={"stderr": err.strip()[:400]},
        )

    # `aws lambda invoke /dev/stdout` writes the payload and then the CLI's own JSON
    # summary, so the response is the first JSON object on stdout.
    try:
        decoder = json.JSONDecoder()
        response, _ = decoder.raw_decode(out.lstrip())
    except ValueError:
        return Stage(
            name="ONTAP auth",
            outcome=Outcome.SKIP,
            detail="The function's response could not be parsed.",
            facts={"stdout": out.strip()[:400]},
        )

    if not isinstance(response, dict):
        return Stage(
            name="ONTAP auth",
            outcome=Outcome.SKIP,
            detail="The function returned something other than an object.",
        )

    error = response.get("error")
    if not error:
        return Stage(
            name="ONTAP auth",
            outcome=Outcome.OK,
            detail="ONTAP accepted the credentials and answered.",
            facts={"volumes": str(len(response.get("volumes") or []))},
        )

    error_class = str(response.get("errorClass") or "")
    advice = {
        "CREDENTIALS_REJECTED": (
            "ONTAP refused the credentials. The request reached the cluster, so the network "
            "is fine. Reset the file system's admin password and write the same value into "
            "the secret -- both halves, or the portal stays broken:\n"
            "    aws fsx update-file-system --file-system-id <fs-id> \\\n"
            "      --ontap-configuration FsxAdminPassword='<new>'\n"
            "    aws secretsmanager put-secret-value --secret-id <secret> \\\n"
            '      --secret-string \'{"username":"fsxadmin","password":"<new>"}\''
        ),
        "UNREACHABLE": (
            "Nothing answered on TCP/443. Check the route from the function's subnet to the "
            "management LIF and that the security group allows 443."
        ),
        "NOT_CONFIGURED": ("The function has no management IP or secret name. It was deployed without them."),
        "NOT_FOUND": (
            "ONTAP answered and does not have what the configuration names. Stages 3 and 4 "
            "checked the AWS side, so this points at a name the cluster sees differently."
        ),
    }.get(error_class, f"ONTAP reported: {error}")

    return Stage(
        name="ONTAP auth",
        outcome=Outcome.FAIL,
        detail=advice,
        facts={
            "errorClass": error_class or "(none -- an older deployment)",
            "error": str(error)[:300],
            "errorStatus": str(response.get("errorStatus", "")),
        },
    )


def run_checks(
    aws: Aws,
    config: dict[str, str],
    file_system_id: str,
    via_lambda: str | None,
) -> list[Stage]:
    """Walk the chain, stopping where continuing would only produce noise."""
    stages = [check_configuration(config)]
    if stages[-1].outcome is Outcome.FAIL:
        # Nothing downstream can be attempted, and reporting five more failures would
        # bury the one that matters.
        return stages

    if not file_system_id:
        stages.append(
            Stage(
                name="file system",
                outcome=Outcome.SKIP,
                detail=(
                    "Pass --file-system-id to check stages 2 to 4. The portal's config "
                    "holds a management IP, not a file system ID."
                ),
            )
        )
    else:
        fs_stage, _ = check_file_system(aws, file_system_id, config["ontapMgmtIp"])
        stages.append(fs_stage)
        if fs_stage.outcome is Outcome.OK:
            svm_stage, svm_id = check_svm(aws, file_system_id, config["ontapSvmName"])
            stages.append(svm_stage)
            if svm_id:
                stages.append(check_volume(aws, svm_id, config["ontapVolumeName"]))

    stages.append(check_secret(aws, config["ontapSecretName"]))

    if via_lambda:
        stages.append(check_ontap_auth(aws, via_lambda))
    else:
        stages.append(
            Stage(
                name="ONTAP auth",
                outcome=Outcome.SKIP,
                detail=(
                    "Not checked. The management LIF is private, so this has to be asked "
                    "from inside the VPC: pass --via-lambda <function-name> to have the "
                    "deployed function make the call. Every stage above can pass while this "
                    "one fails -- that is the case this script was written for."
                ),
            )
        )
    return stages


_MARKS = {Outcome.OK: "PASS", Outcome.FAIL: "FAIL", Outcome.SKIP: "SKIP"}


def report(stages: list[Stage]) -> str:
    """The stages, in order, with the failures' advice."""
    lines = ["ONTAP connection preflight", ""]
    for index, stage in enumerate(stages, start=1):
        lines.append(f"  {index}. [{_MARKS[stage.outcome]}] {stage.name}")
        for key, value in stage.facts.items():
            lines.append(f"        {key}: {value}")
        if stage.outcome is not Outcome.OK:
            for line in stage.detail.splitlines():
                lines.append(f"        {line}")
        else:
            lines.append(f"        {stage.detail}")
        lines.append("")

    failed = [stage for stage in stages if stage.outcome is Outcome.FAIL]
    skipped = [stage for stage in stages if stage.outcome is Outcome.SKIP]
    if failed:
        lines.append(f"{len(failed)} stage(s) failed: " + ", ".join(s.name for s in failed))
        lines.append("Fix the earliest one first; the later ones may be its symptoms.")
    elif skipped:
        lines.append("No failures. Not everything was checked: " + ", ".join(s.name for s in skipped) + ".")
    else:
        lines.append("Every stage passed. The ONTAP panels have what they need.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", help="path to amplify/portal-config.ts")
    parser.add_argument("--mgmt-ip", default="")
    parser.add_argument("--secret", default="")
    parser.add_argument("--volume", default="")
    parser.add_argument("--svm", default="")
    parser.add_argument("--file-system-id", default="", help="enables stages 2 to 4")
    parser.add_argument("--via-lambda", default="", help="function to ask for stage 6")
    parser.add_argument("--region", default="")
    args = parser.parse_args(argv)

    config: dict[str, str] = {}
    if args.config:
        try:
            config = parse_portal_config(Path(args.config).read_text(encoding="utf-8"))
        except OSError as error:
            print(f"Could not read {args.config}: {error}", file=sys.stderr)
            return 2

    # Explicit flags win, so a single value can be overridden without editing the config.
    for key, value in (
        ("ontapMgmtIp", args.mgmt_ip),
        ("ontapSecretName", args.secret),
        ("ontapVolumeName", args.volume),
        ("ontapSvmName", args.svm),
    ):
        if value:
            config[key] = value

    stages = run_checks(Aws(args.region or None), config, args.file_system_id, args.via_lambda or None)
    print(report(stages))
    return 1 if any(stage.outcome is Outcome.FAIL for stage in stages) else 0


if __name__ == "__main__":
    sys.exit(main())
