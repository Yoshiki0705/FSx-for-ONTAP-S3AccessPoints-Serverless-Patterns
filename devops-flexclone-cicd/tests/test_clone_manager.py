"""Unit tests for Clone Manager Lambda."""

import importlib.util
import os
from pathlib import Path
from unittest.mock import patch

import pytest


def _load_handler():
    """Dynamically load the handler module."""
    handler_path = Path(__file__).parent.parent / "functions" / "clone_manager" / "handler.py"
    spec = importlib.util.spec_from_file_location("clone_manager_handler", handler_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestCloneManagerSimulation:
    """Tests with SIMULATION_MODE=true (default)."""

    def setup_method(self):
        os.environ["SIMULATION_MODE"] = "true"
        self.module = _load_handler()

    def test_create_clone_success(self):
        event = {
            "action": "CREATE",
            "source_volume": "production_data",
            "requester": "test-pipeline",
            "ttl_hours": 12,
        }
        result = self.module.handler(event, None)
        assert result["status"] == "success"
        assert result["action"] == "CREATE"
        assert result["source_volume"] == "production_data"
        assert result["simulation"] is True
        assert "clone_name" in result
        assert result["ttl_hours"] == 12

    def test_create_clone_missing_source(self):
        event = {"action": "CREATE"}
        result = self.module.handler(event, None)
        assert result["status"] == "error"
        assert "source_volume" in result["message"]

    def test_delete_clone_success(self):
        event = {"action": "DELETE", "clone_name": "devtest_clone_12345"}
        result = self.module.handler(event, None)
        assert result["status"] == "success"
        assert result["action"] == "DELETE"
        assert result["clone_name"] == "devtest_clone_12345"

    def test_delete_clone_missing_name(self):
        event = {"action": "DELETE"}
        result = self.module.handler(event, None)
        assert result["status"] == "error"

    def test_status_clone(self):
        event = {"action": "STATUS", "clone_name": "devtest_clone_12345"}
        result = self.module.handler(event, None)
        assert result["status"] == "success"
        assert result["state"] == "online"

    def test_unknown_action(self):
        event = {"action": "INVALID"}
        result = self.module.handler(event, None)
        assert result["status"] == "error"
        assert "Unknown action" in result["message"]

    def test_default_action_is_create(self):
        event = {"source_volume": "vol1"}
        result = self.module.handler(event, None)
        assert result["action"] == "CREATE"


class TestS3APProvisioner:
    """Tests for S3AP Provisioner."""

    def setup_method(self):
        os.environ["SIMULATION_MODE"] = "true"
        handler_path = Path(__file__).parent.parent / "functions" / "s3ap_provisioner" / "handler.py"
        spec = importlib.util.spec_from_file_location("s3ap_provisioner_handler", handler_path)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def test_provision_success(self):
        event = {
            "clone_name": "devtest_clone_1717776000",
            "junction_path": "/devtest_clone_1717776000",
            "requester": "ci-pipeline",
        }
        result = self.module.handler(event, None)
        assert result["status"] == "success"
        assert "s3ap_name" in result
        assert "s3ap_alias" in result
        assert "usage_example" in result

    def test_provision_missing_clone_name(self):
        event = {}
        result = self.module.handler(event, None)
        assert result["status"] == "error"


class TestTestOrchestrator:
    """Tests for Test Orchestrator."""

    def setup_method(self):
        os.environ["SIMULATION_MODE"] = "true"
        handler_path = Path(__file__).parent.parent / "functions" / "test_orchestrator" / "handler.py"
        spec = importlib.util.spec_from_file_location("test_orchestrator_handler", handler_path)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def test_orchestrate_success(self):
        event = {
            "s3ap_alias": "devtest-clone-xxx-s3alias",
            "clone_name": "devtest_clone_123",
            "test_suite": "integration",
            "test_config": {
                "data_prefix": "testdata/",
                "validation_rules": ["schema", "completeness"],
            },
            "pipeline_run_id": "run-001",
        }
        result = self.module.handler(event, None)
        assert result["status"] == "success"
        assert result["ready_for_cleanup"] is True
        assert result["test_results"]["passed"] > 0
        assert result["test_results"]["failed"] == 0


class TestCleanup:
    """Tests for Cleanup handler."""

    def setup_method(self):
        os.environ["SIMULATION_MODE"] = "true"
        handler_path = Path(__file__).parent.parent / "functions" / "cleanup" / "handler.py"
        spec = importlib.util.spec_from_file_location("cleanup_handler", handler_path)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def test_immediate_cleanup(self):
        event = {"mode": "immediate", "clone_name": "devtest_clone_123"}
        result = self.module.handler(event, None)
        assert result["status"] == "success"
        assert result["mode"] == "immediate"
        assert "devtest_clone_123" in result["deleted"]

    def test_ttl_sweep(self):
        event = {"mode": "ttl_sweep"}
        result = self.module.handler(event, None)
        assert result["status"] == "success"
        assert result["mode"] == "ttl_sweep"
        assert result["expired"] > 0

    def test_immediate_missing_name(self):
        event = {"mode": "immediate"}
        result = self.module.handler(event, None)
        assert result["status"] == "error"
