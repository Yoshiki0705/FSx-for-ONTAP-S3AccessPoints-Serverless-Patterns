"""The preflight has to name the stage that broke, not merely fail.

The defect it exists for: every stage below passed -- the file system was AVAILABLE, the
SVM and volume existed under exactly the configured names, the secret was readable -- and
the portal still showed "Volume 'vol1' not found on SVM 'fsxsvm01'" with advice about
subnets. So the case worth testing hardest is the one where stages 1 to 5 pass and 6
fails: a tool that reported "something is wrong" would have been no better than the UI.

The AWS calls are replaced with recorded responses. This is not a claim that the real
API behaves this way; it is a claim about how the script reads answers of that shape.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_ontap_connection import (  # noqa: E402
    Outcome,
    check_configuration,
    check_ontap_auth,
    check_secret,
    check_svm,
    check_volume,
    parse_portal_config,
    report,
    run_checks,
)


def _portal_amplify_dir() -> Path:
    """Where the portal's config files live, relative to this test."""
    return Path(__file__).resolve().parents[2] / "solutions" / "amplify-portal" / "amplify"


CONFIG = {
    "ontapMgmtIp": "10.0.1.10",
    "ontapSecretName": "fsx-ontap-fsxadmin-credentials",
    "ontapVolumeName": "vol1",
    "ontapSvmName": "fsxsvm01",
}

FS_AVAILABLE = {
    "FileSystems": [
        {
            "Lifecycle": "AVAILABLE",
            "OntapConfiguration": {"Endpoints": {"Management": {"IpAddresses": ["10.0.1.10"]}}},
        }
    ]
}

SVMS = {
    "StorageVirtualMachines": [
        {
            "Name": "fsxsvm01",
            "Lifecycle": "CREATED",
            "StorageVirtualMachineId": "svm-0123456789abcdef0",
        }
    ]
}

VOLUMES = {
    "Volumes": [
        {
            "Name": "vol1",
            "Lifecycle": "CREATED",
            "VolumeId": "fsvol-0123456789abcdef0",
            "OntapConfiguration": {"JunctionPath": "/vol1"},
        }
    ]
}

SECRET_OK = {"SecretString": json.dumps({"username": "fsxadmin", "password": "x" * 24})}


class FakeAws:
    """Answers the script's calls from a table keyed on the first two argv words."""

    def __init__(self, responses: dict[tuple[str, str], object], region: str | None = None):
        self.responses = responses
        self.region = region
        self.calls: list[tuple[str, ...]] = []

    def run(self, *args: str) -> tuple[int, str, str]:
        self.calls.append(args)
        entry = self.responses.get((args[0], args[1]))
        if entry is None:
            return 254, "", "not stubbed"
        if isinstance(entry, tuple):
            return entry
        return 0, json.dumps(entry), ""


def healthy(auth_response: dict | None = None) -> FakeAws:
    """Every AWS-side stage passing. Stage 6 answers with whatever is passed."""
    responses: dict[tuple[str, str], object] = {
        ("fsx", "describe-file-systems"): FS_AVAILABLE,
        ("fsx", "describe-storage-virtual-machines"): SVMS,
        ("fsx", "describe-volumes"): VOLUMES,
        ("secretsmanager", "get-secret-value"): SECRET_OK,
    }
    if auth_response is not None:
        responses[("lambda", "invoke")] = (
            0,
            json.dumps(auth_response) + '\n{"StatusCode": 200}',
            "",
        )
    return FakeAws(responses)


def outcomes(stages) -> dict[str, Outcome]:
    return {stage.name: stage.outcome for stage in stages}


class TestTheCaseItWasWrittenFor:
    def test_it_reports_the_credentials_when_everything_else_is_correct(self):
        """Stages 1-5 pass; ONTAP refuses the password. Exactly what happened."""
        aws = healthy(
            {
                "volumes": [],
                "error": "User is not authorized.",
                "errorClass": "CREDENTIALS_REJECTED",
                "errorStatus": 401,
            }
        )
        stages = run_checks(aws, CONFIG, "fs-0123456789abcdef0", "ResourceMgmtFunction")

        assert outcomes(stages) == {
            "configuration": Outcome.OK,
            "file system": Outcome.OK,
            "SVM": Outcome.OK,
            "volume": Outcome.OK,
            "secret": Outcome.OK,
            "ONTAP auth": Outcome.FAIL,
        }

        text = report(stages)
        # The two commands, because doing only the first leaves the portal broken.
        assert "aws fsx update-file-system" in text
        assert "aws secretsmanager put-secret-value" in text
        # And it must not send the reader to the network, which is what the UI did.
        assert "security group" not in text.split("ONTAP auth")[1]

    def test_a_passing_volume_stage_is_what_makes_that_conclusion_available(self):
        """The volume the portal blamed is confirmed present, by name and state."""
        stage = check_volume(healthy(), "svm-0123456789abcdef0", "vol1")
        assert stage.outcome is Outcome.OK
        assert stage.facts["Lifecycle"] == "CREATED"


class TestStagesAreDistinguished:
    def test_a_wrong_volume_name_lists_the_ones_that_exist(self):
        stage = check_volume(healthy(), "svm-0123456789abcdef0", "vol2")
        assert stage.outcome is Outcome.FAIL
        # Listing them turns "not found" into a correction the reader can apply.
        assert "vol1" in stage.detail

    def test_a_wrong_svm_name_lists_the_ones_that_exist(self):
        stage, svm_id = check_svm(healthy(), "fs-0123456789abcdef0", "svm-typo")
        assert stage.outcome is Outcome.FAIL
        assert "fsxsvm01" in stage.detail
        assert svm_id == ""

    def test_a_misconfigured_svm_is_named_rather_than_called_healthy(self):
        aws = FakeAws(
            {
                (
                    "fsx",
                    "describe-storage-virtual-machines",
                ): {
                    "StorageVirtualMachines": [
                        {
                            "Name": "fsxsvm01",
                            "Lifecycle": "MISCONFIGURED",
                            "StorageVirtualMachineId": "svm-1",
                        }
                    ]
                }
            }
        )
        stage, _ = check_svm(aws, "fs-1", "fsxsvm01")
        assert stage.outcome is Outcome.FAIL
        assert "domain controller" in stage.detail

    def test_a_stale_management_ip_is_not_left_to_look_like_a_firewall(self):
        """The configured address belonging to a previous file system times out."""
        stages = run_checks(
            FakeAws(
                {
                    ("fsx", "describe-file-systems"): FS_AVAILABLE,
                    ("secretsmanager", "get-secret-value"): SECRET_OK,
                }
            ),
            {**CONFIG, "ontapMgmtIp": "10.0.9.99"},
            "fs-0123456789abcdef0",
            None,
        )
        fs_stage = next(s for s in stages if s.name == "file system")
        assert fs_stage.outcome is Outcome.FAIL
        assert "10.0.1.10" in fs_stage.detail

    def test_whitespace_in_the_password_is_reported_because_nothing_else_shows_it(self):
        aws = FakeAws(
            {
                ("secretsmanager", "get-secret-value"): {
                    "SecretString": json.dumps({"username": "fsxadmin", "password": "secret\n"})
                }
            }
        )
        stage = check_secret(aws, "some-secret")
        assert stage.outcome is Outcome.FAIL
        assert "whitespace" in stage.detail

    def test_the_password_is_never_printed(self):
        aws = FakeAws(
            {
                ("secretsmanager", "get-secret-value"): {
                    "SecretString": json.dumps({"username": "fsxadmin", "password": "Pa55w0rd-do-not-log"})
                }
            }
        )
        stage = check_secret(aws, "some-secret")
        assert stage.outcome is Outcome.OK
        assert "Pa55w0rd-do-not-log" not in report([stage])
        # The length is shown, since a trailing newline is otherwise invisible.
        assert stage.facts["passwordLength"] == "19"


class TestItDoesNotOverclaim:
    def test_the_unchecked_stage_says_so_and_does_not_fail_the_run(self):
        """A green run that skipped stage 6 must not read as "the portal will work"."""
        stages = run_checks(healthy(), CONFIG, "fs-0123456789abcdef0", None)
        auth = next(s for s in stages if s.name == "ONTAP auth")
        assert auth.outcome is Outcome.SKIP
        assert "--via-lambda" in auth.detail

        text = report(stages)
        assert "Not everything was checked" in text
        assert "Every stage passed" not in text

    def test_missing_configuration_stops_rather_than_reporting_five_symptoms(self):
        stages = run_checks(healthy(), {}, "fs-0123456789abcdef0", None)
        assert len(stages) == 1
        assert stages[0].outcome is Outcome.FAIL
        assert "DemoMode" in stages[0].detail

    def test_an_uninvokable_function_is_a_skip_not_a_verdict_on_ontap(self):
        aws = FakeAws({("lambda", "invoke"): (255, "", "AccessDeniedException")})
        stage = check_ontap_auth(aws, "SomeFunction")
        assert stage.outcome is Outcome.SKIP

    def test_a_response_without_a_class_is_passed_through_verbatim(self):
        """An older deployment. Repeating ONTAP's words beats inventing a cause."""
        aws = healthy({"volumes": [], "error": "User is not authorized."})
        stage = check_ontap_auth(aws, "SomeFunction")
        assert stage.outcome is Outcome.FAIL
        assert "User is not authorized." in stage.detail
        assert "older deployment" in stage.facts["errorClass"]

    def test_a_successful_call_is_reported_as_success(self):
        aws = healthy({"volumes": [{"name": "vol1"}]})
        stage = check_ontap_auth(aws, "SomeFunction")
        assert stage.outcome is Outcome.OK
        assert stage.facts["volumes"] == "1"

    def test_every_stage_passing_says_exactly_that(self):
        stages = run_checks(healthy({"volumes": [{"name": "vol1"}]}), CONFIG, "fs-1", "Fn")
        assert "Every stage passed" in report(stages)


class TestConfigParsing:
    def test_it_reads_the_four_values_from_the_portal_config(self):
        source = """
        export const config = {
          ontapMgmtIp: "10.0.1.10",
          ontapSecretName: 'fsx-ontap-fsxadmin-credentials',
          ontapVolumeName: `vol1`,
          ontapSvmName: "fsxsvm01",
          unrelated: "ignored",
        };
        """
        assert parse_portal_config(source) == CONFIG

    def test_an_empty_string_counts_as_absent(self):
        """`ontapMgmtIp: ""` is how a DemoMode deployment looks, not a typo."""
        parsed = parse_portal_config(
            'ontapMgmtIp: "",\nontapSecretName: "s",\nontapVolumeName: "v",\nontapSvmName: "m",'
        )
        stage = check_configuration(parsed)
        assert stage.outcome is Outcome.FAIL
        assert "ontapMgmtIp" in stage.detail


@pytest.mark.parametrize(
    ("error_class", "expected_phrase"),
    [
        ("CREDENTIALS_REJECTED", "refused the credentials"),
        ("UNREACHABLE", "TCP/443"),
        ("NOT_CONFIGURED", "deployed without them"),
        ("NOT_FOUND", "does not have what the configuration names"),
    ],
)
def test_each_class_gets_its_own_advice(error_class: str, expected_phrase: str):
    """Five classes exist so that five different next steps can be given."""
    aws = healthy({"error": "something", "errorClass": error_class})
    stage = check_ontap_auth(aws, "SomeFunction")
    assert stage.outcome is Outcome.FAIL
    assert expected_phrase in stage.detail


class TestItReadsTheRealConfigShape:
    """The first version of the parser read none of these four.

    It required a quote immediately after the colon. The actual file assigns
    `ontapMgmtIp: process.env.ONTAP_MGMT_IP || "172.30.131.210"`, so every value came
    back absent and the preflight would have reported an unconfigured deployment on a
    configured one -- a new wrong answer in place of the old one.
    """

    SOURCE = """
    export interface PortalConfig {
      ontapMgmtIp: string;
      ontapSecretName: string;
      ontapSvmName: string;
      ontapVolumeName: string;
    }

    export const config: PortalConfig = {
      ontapMgmtIp: process.env.ONTAP_MGMT_IP || "172.30.131.210",
      ontapSecretName: process.env.ONTAP_SECRET_NAME || "fsx-ontap-fsxadmin-credentials",
      ontapSvmName: process.env.ONTAP_SVM_NAME || "fsxsvm01",
      ontapVolumeName: process.env.ONTAP_VOLUME_NAME || "vol1",
    };
    """

    def test_it_takes_the_fallback_and_not_the_type_declaration(self):
        assert parse_portal_config(self.SOURCE) == {
            "ontapMgmtIp": "172.30.131.210",
            "ontapSecretName": "fsx-ontap-fsxadmin-credentials",
            "ontapSvmName": "fsxsvm01",
            "ontapVolumeName": "vol1",
        }

    def test_the_shipped_example_config_parses(self):
        """Against the tracked example, so a rename fails here rather than in the field.

        The example rather than `portal-config.ts`: that file is gitignored, because it holds
        one environment's values. A test that read it passed on the machine that had one and
        failed in CI, which is the wrong way round. The example is what every new deployment
        is copied from, so it is the shape worth guarding.

        Its four values are empty, because a fresh copy is DemoMode. That makes this two
        assertions in one: the parser still recognises the shipped shape, and an unconfigured
        deployment is reported as unconfigured rather than passing quietly.
        """
        example = _portal_amplify_dir() / "portal-config.example.ts"
        parsed = parse_portal_config(example.read_text(encoding="utf-8"))

        # Found, so the pattern still matches the file. Empty, so stage 1 must fail.
        assert set(parsed) == set(CONFIG), f"the parser no longer finds all four: {sorted(parsed)}"
        stage = check_configuration(parsed)
        assert stage.outcome is Outcome.FAIL
        for key in CONFIG:
            assert key in stage.detail

    @pytest.mark.skipif(
        not (_portal_amplify_dir() / "portal-config.ts").exists(),
        reason="portal-config.ts is gitignored; present only on a machine with a deployment",
    )
    def test_a_real_config_reports_configured(self):
        """Where a deployment's own config exists, stage 1 should pass on it."""
        parsed = parse_portal_config((_portal_amplify_dir() / "portal-config.ts").read_text(encoding="utf-8"))
        assert check_configuration(parsed).outcome is Outcome.OK
