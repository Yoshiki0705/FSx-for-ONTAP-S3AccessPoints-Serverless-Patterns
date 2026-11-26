"""OntapClient.list_directory: path encoding and pagination."""

from __future__ import annotations

from unittest.mock import MagicMock

from shared.ontap_client import OntapClient, OntapClientConfig


def _client(pages):
    client = OntapClient(OntapClientConfig(management_ip="<management-ip>", secret_name="s"), session=MagicMock())
    client._request = MagicMock(side_effect=pages)
    return client


def test_root_and_nested_paths_are_encoded():
    c = _client([{"records": []}, {"records": []}])
    c.list_directory("uuid-1", "")
    c.list_directory("uuid-1", "a b/c")
    paths = [call.args[1] for call in c._request.call_args_list]
    assert paths == ["/storage/volumes/uuid-1/files/%2F", "/storage/volumes/uuid-1/files/a%20b%2Fc"]


def test_follows_next_links_until_exhausted():
    c = _client(
        [
            {"records": [{"name": "a"}], "_links": {"next": {"href": "/api/storage/volumes/u/files/%2F?start.name=a"}}},
            {"records": [{"name": "b"}]},
        ]
    )
    assert [r["name"] for r in c.list_directory("u")] == ["a", "b"]
    assert c._request.call_args_list[1].args[1] == "/storage/volumes/u/files/%2F?start.name=a"
