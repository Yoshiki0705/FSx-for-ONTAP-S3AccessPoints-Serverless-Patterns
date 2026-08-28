"""Tests for the declared ONTAP cluster probe.

Every case is a different next action for the operator. A probe that answers "not
available" for all of them is useless: no route, a rejected credential, and an
address that is not ONTAP are fixed in three different places.
"""

from __future__ import annotations

import pytest

from shared.ontap_cluster_probe import CLUSTER_ENDPOINT, ProbeResult, probe_ontap_cluster


def responder(status: int, body: dict | None):
    """A transport that returns one prepared answer."""

    def request(_endpoint: str) -> tuple[int, dict]:
        return status, body or {}

    return request


class TestAnswered:
    """What counts as the cluster being there."""

    def test_a_named_cluster_answers(self) -> None:
        result = probe_ontap_cluster(
            responder(200, {"name": "lab-cluster", "version": {"full": "NetApp Release 9.18.1"}})
        )
        assert result.answered is True
        assert result.cluster_name == "lab-cluster"
        assert result.version == "NetApp Release 9.18.1"
        assert result.reason == ""

    def test_a_missing_version_is_not_a_failure(self) -> None:
        """The name is what proves it; the version is extra."""
        result = probe_ontap_cluster(responder(200, {"name": "lab-cluster"}))
        assert result.answered is True
        assert result.version == ""

    def test_reads_the_cluster_document(self) -> None:
        seen: list[str] = []

        def request(endpoint: str) -> tuple[int, dict]:
            seen.append(endpoint)
            return 200, {"name": "c"}

        probe_ontap_cluster(request)
        assert seen == [CLUSTER_ENDPOINT]


class TestNoRoute:
    """A transport failure is a networking problem, not a credential one."""

    @pytest.mark.parametrize("error", [TimeoutError("timed out"), OSError("unreachable")])
    def test_a_raising_transport_reports_the_route(self, error: Exception) -> None:
        def request(_endpoint: str) -> tuple[int, dict]:
            raise error

        result = probe_ontap_cluster(request)
        assert result.answered is False
        assert "No response" in result.reason
        assert "route" in result.reason
        assert type(error).__name__ in result.reason


class TestRejectedCredential:
    """Named separately because retrying it locks the account out."""

    @pytest.mark.parametrize("status", [401, 403])
    def test_a_refusal_points_at_the_secret(self, status: int) -> None:
        result = probe_ontap_cluster(responder(status, {}))
        assert result.answered is False
        assert "rejected the credential" in result.reason
        assert "secret" in result.reason

    def test_the_refusal_says_it_is_not_retried(
        self,
    ) -> None:
        """A scheduled probe with a wrong password would lock out the account an
        operator needs, and the lockout does not clear on its own."""
        assert "not retried" in probe_ontap_cluster(responder(401, {})).reason


class TestNotOntap:
    """Reached something, but not a cluster."""

    @pytest.mark.parametrize("status", [200, 404, 500, 502])
    def test_an_unusable_answer_never_counts_as_available(self, status: int) -> None:
        assert probe_ontap_cluster(responder(status, {})).answered is False

    def test_a_non_200_points_at_the_address(self) -> None:
        result = probe_ontap_cluster(responder(502, {}))
        assert "management LIF" in result.reason
        assert "502" in result.reason

    def test_a_200_without_a_name_is_probably_not_ontap(self) -> None:
        result = probe_ontap_cluster(responder(200, {"records": []}))
        assert result.answered is False
        assert "not ONTAP" in result.reason

    def test_a_blank_name_is_not_a_name(self) -> None:
        assert probe_ontap_cluster(responder(200, {"name": "   "})).answered is False


class TestResultShape:
    """Defaults, so a failure cannot look partly successful."""

    def test_a_failure_carries_no_cluster_name(self) -> None:
        result = probe_ontap_cluster(responder(401, {"name": "should-be-ignored"}))
        assert result.cluster_name == ""

    def test_defaults_are_empty(self) -> None:
        result = ProbeResult(answered=False)
        assert (result.cluster_name, result.version, result.reason) == ("", "", "")
