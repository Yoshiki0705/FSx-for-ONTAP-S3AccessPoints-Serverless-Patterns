"""Tests for the folder watch inbox in functions/list-files.

The interesting behaviour is the filtering: an event must survive the Cognito
group boundary before the user's own watch list narrows it further. A watch is
per-user and unconstrained, so if the order were reversed a user could learn that
a path exists outside their scope by watching a prefix that covers it.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

MODULE_PATH = Path(__file__).resolve().parent.parent / "index.py"


def load_module(env: dict[str, str]):
    """Import index.py fresh, since its constants are read at import time."""
    with patch.dict(os.environ, env, clear=False):
        spec = importlib.util.spec_from_file_location("list_files_under_test", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules["list_files_under_test"] = module
        spec.loader.exec_module(module)
    return module


EVENTS = [
    {
        "id": "1",
        "fileKey": "engineering/cad/part.step",
        "timestamp": "2026-08-07T10:00:00Z",
        "source": "FPOLICY",
        "eventType": "CREATE",
        "fileName": "part.step",
        "fileSize": 10,
    },
    {
        "id": "2",
        "fileKey": "finance/q3.xlsx",
        "timestamp": "2026-08-07T11:00:00Z",
        "source": "FPOLICY",
        "eventType": "MODIFY",
        "fileName": "q3.xlsx",
        "fileSize": 20,
    },
    {
        "id": "3",
        "fileKey": "shared/notes.txt",
        "timestamp": "2026-08-07T12:00:00Z",
        "source": "SFTP",
        "eventType": "CREATE",
        "fileName": "notes.txt",
        "fileSize": 30,
    },
]


def run_inbox(module, event, records=EVENTS):
    table = MagicMock()
    table.scan.return_value = {"Items": list(records)}
    resource = MagicMock()
    resource.Table.return_value = table
    with patch.object(module.boto3, "resource", return_value=resource):
        return module.handler({"action": "listNotifications", **event}, None)


@pytest.fixture
def single_tenant():
    return load_module({"NOTIFICATION_TABLE_NAME": "notifications", "GROUP_PATH_PREFIXES": "{}"})


@pytest.fixture
def multi_tenant():
    return load_module(
        {
            "NOTIFICATION_TABLE_NAME": "notifications",
            "GROUP_PATH_PREFIXES": json.dumps({"engineering": ["engineering/", "shared/"]}),
        }
    )


def test_reports_not_configured_when_no_table():
    module = load_module({"NOTIFICATION_TABLE_NAME": "", "GROUP_PATH_PREFIXES": "{}"})
    result = module.handler({"action": "listNotifications"}, None)
    # The UI keys its "this deployment cannot receive events" message on this flag,
    # so an empty list is never mistaken for "nothing has happened".
    assert result["configured"] is False
    assert result["notifications"] == []


def test_returns_events_newest_first(single_tenant):
    result = run_inbox(single_tenant, {})
    assert result["configured"] is True
    assert [n["id"] for n in result["notifications"]] == ["3", "2", "1"]


def test_group_scope_hides_other_tenants(multi_tenant):
    result = run_inbox(multi_tenant, {"groups": ["engineering"]})
    keys = [n["fileKey"] for n in result["notifications"]]
    assert "finance/q3.xlsx" not in keys
    assert "engineering/cad/part.step" in keys
    assert "shared/notes.txt" in keys


def test_watch_cannot_widen_the_group_scope(multi_tenant):
    # Watching the root is allowed — a watch is the user's own record — but it must
    # not reveal a path the group boundary excludes.
    result = run_inbox(multi_tenant, {"groups": ["engineering"], "watchedPrefixes": ""})
    assert all(not n["fileKey"].startswith("finance/") for n in result["notifications"])

    widened = run_inbox(multi_tenant, {"groups": ["engineering"], "watchedPrefixes": "finance/"})
    assert widened["notifications"] == []


def test_watches_narrow_within_the_scope(multi_tenant):
    result = run_inbox(multi_tenant, {"groups": ["engineering"], "watchedPrefixes": "engineering/cad/"})
    assert [n["fileKey"] for n in result["notifications"]] == ["engineering/cad/part.step"]


def test_storage_admin_sees_every_tenant(multi_tenant):
    result = run_inbox(multi_tenant, {"groups": ["storage-admin"]})
    assert len(result["notifications"]) == 3


def test_single_tenant_deployment_applies_no_group_filter(single_tenant):
    # With no GROUP_PATH_PREFIXES configured the portal is single-tenant, and the
    # file listing behaves the same way, so the inbox must not invent a boundary.
    result = run_inbox(single_tenant, {"groups": ["engineering"]})
    assert len(result["notifications"]) == 3


def test_max_results_is_capped(single_tenant):
    many = [{**EVENTS[0], "id": str(i), "timestamp": f"2026-08-07T10:{i:02d}:00Z"} for i in range(300)]
    result = run_inbox(single_tenant, {"maxResults": 5000}, records=many)
    # An unbounded page would let one caller pull the whole table in a request.
    assert len(result["notifications"]) == 200


def test_scan_failure_is_reported_not_swallowed(single_tenant):
    table = MagicMock()
    table.scan.side_effect = RuntimeError("ProvisionedThroughputExceeded")
    resource = MagicMock()
    resource.Table.return_value = table
    with patch.object(single_tenant.boto3, "resource", return_value=resource):
        result = single_tenant.handler({"action": "listNotifications"}, None)
    assert result["configured"] is True
    assert "ProvisionedThroughputExceeded" in result["error"]
