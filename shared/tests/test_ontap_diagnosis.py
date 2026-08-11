"""Tests for shared.ontap_diagnosis.

The module exists because of one afternoon. The portal reported

    Volume 'vol1' not found on SVM 'fsxsvm01'

and offered advice about VPC subnets, security groups and the management LIF, while the
AWS control plane listed that volume, in that SVM, as CREATED. Nothing was wrong with the
network. ONTAP had answered

    {"error": {"message": "User is not authorized."}}

which has no `records` key, and the handler's `if not data.get("records")` branch called
that a missing volume.

The first case below is that exact body. It is the one this file exists to keep working.
"""

from __future__ import annotations

import json

from shared.ontap_diagnosis import (
    OntapFailure,
    diagnose_exception,
    diagnose_response,
    not_configured,
)


class TestCredentialsRejected:
    """The failure that was reported as a missing volume."""

    BODY = json.dumps({"error": {"message": "User is not authorized.", "code": "6691623"}})

    def test_a_401_is_a_credentials_problem(self):
        diagnosis = diagnose_response(401, self.BODY, subject="volume 'vol1' on SVM 'fsxsvm01'")
        assert diagnosis is not None
        assert diagnosis.failure is OntapFailure.CREDENTIALS_REJECTED
        assert diagnosis.status == 401

    def test_a_403_is_the_same_class(self):
        """401 points at the password and 403 at the role, and both send the reader to
        the same place: the secret, not the network."""
        diagnosis = diagnose_response(403, self.BODY)
        assert diagnosis is not None
        assert diagnosis.failure is OntapFailure.CREDENTIALS_REJECTED

    def test_it_says_the_network_is_not_the_problem(self):
        """The whole point. The old advice pointed at subnets and security groups."""
        diagnosis = diagnose_response(401, self.BODY)
        assert diagnosis is not None
        assert "rather than the network" in diagnosis.message

    def test_ontaps_own_message_and_code_survive(self):
        """A support case will ask for the code."""
        diagnosis = diagnose_response(401, self.BODY)
        assert diagnosis is not None
        assert "User is not authorized." in diagnosis.message
        assert diagnosis.ontap_code == "6691623"

    def test_it_is_not_confused_with_a_missing_volume(self):
        """The regression: this body has no `records`, and that used to be the whole test."""
        diagnosis = diagnose_response(401, self.BODY, expected_records=True)
        assert diagnosis is not None
        assert diagnosis.failure is not OntapFailure.NOT_FOUND


class TestNotFound:
    """ONTAP answered, and the named object genuinely is not there."""

    def test_an_empty_collection_is_a_naming_problem(self):
        diagnosis = diagnose_response(200, json.dumps({"records": [], "num_records": 0}), subject="volume 'vol9'")
        assert diagnosis is not None
        assert diagnosis.failure is OntapFailure.NOT_FOUND
        assert "volume 'vol9'" in diagnosis.message

    def test_it_says_the_connection_works(self):
        """So the reader does not go and check the network, which is what happened."""
        diagnosis = diagnose_response(200, json.dumps({"records": []}))
        assert diagnosis is not None
        assert "connection works" in diagnosis.message

    def test_a_populated_collection_is_not_a_failure(self):
        assert diagnose_response(200, json.dumps({"records": [{"uuid": "abc"}]})) is None

    def test_a_single_object_get_is_not_judged_on_records(self):
        """`GET /storage/volumes/{uuid}` has no `records`, and that is not a finding."""
        body = json.dumps({"uuid": "abc", "name": "vol1"})
        assert diagnose_response(200, body, expected_records=False) is None


class TestOntapError:
    """Anything else, passed through rather than flattened."""

    def test_a_500_keeps_its_status(self):
        diagnosis = diagnose_response(500, json.dumps({"error": {"message": "internal"}}))
        assert diagnosis is not None
        assert diagnosis.failure is OntapFailure.ONTAP_ERROR
        assert diagnosis.status == 500
        assert "internal" in diagnosis.message

    def test_a_2xx_carrying_an_error_body_is_reported(self):
        """Rare, and previously indistinguishable from an empty collection."""
        diagnosis = diagnose_response(200, json.dumps({"error": {"message": "odd"}}))
        assert diagnosis is not None
        assert diagnosis.failure is OntapFailure.ONTAP_ERROR

    def test_a_body_that_is_not_json_does_not_raise(self):
        """An HTML error page from something in front of the LIF, for instance."""
        diagnosis = diagnose_response(502, b"<html>gateway</html>")
        assert diagnosis is not None
        assert diagnosis.failure is OntapFailure.ONTAP_ERROR
        assert "502" in diagnosis.message


class TestUnreachable:
    """No response at all -- the only class the original advice was written for."""

    def test_an_exception_names_the_layer_to_check(self):
        diagnosis = diagnose_exception(TimeoutError("timed out"), mgmt_ip="172.30.131.210")
        assert diagnosis.failure is OntapFailure.UNREACHABLE
        assert "172.30.131.210" in diagnosis.message
        assert "TCP/443" in diagnosis.message

    def test_the_exception_type_is_reported(self):
        """Which one it is does not change the fix, but it belongs in the detail."""
        diagnosis = diagnose_exception(ConnectionRefusedError("refused"))
        assert "ConnectionRefusedError" in diagnosis.message

    def test_there_is_no_status(self):
        """Absent, rather than zero: the absence is the finding."""
        assert diagnose_exception(TimeoutError()).status is None


class TestNotConfigured:
    def test_it_names_what_is_missing(self):
        diagnosis = not_configured(["VOLUME_NAME", "ONTAP_MGMT_IP"])
        assert diagnosis.failure is OntapFailure.NOT_CONFIGURED
        assert "ONTAP_MGMT_IP" in diagnosis.message
        assert "VOLUME_NAME" in diagnosis.message

    def test_the_list_is_ordered_so_the_message_is_stable(self):
        """Two deployments missing the same things should read identically."""
        first = not_configured(["b", "a"]).message
        second = not_configured(["a", "b"]).message
        assert first == second


class TestWireFormat:
    """What crosses the GraphQL boundary."""

    def test_error_stays_a_plain_string(self):
        """The existing panels read `error` and are migrated one at a time."""
        payload = diagnose_response(401, json.dumps({"error": {"message": "nope"}})).as_dict()
        assert isinstance(payload["error"], str)

    def test_the_class_is_a_plain_string_too(self):
        """A `str` enum, so neither side needs a conversion table."""
        payload = diagnose_response(200, json.dumps({"records": []})).as_dict()
        assert payload["errorClass"] == "NOT_FOUND"

    def test_status_and_code_are_omitted_when_absent(self):
        """A key that is present and null reads as "we looked and there was none"."""
        payload = diagnose_exception(TimeoutError()).as_dict()
        assert "errorStatus" not in payload
        assert "errorCode" not in payload

    def test_status_is_included_when_there_was_a_response(self):
        payload = diagnose_response(503, b"{}").as_dict()
        assert payload["errorStatus"] == 503
