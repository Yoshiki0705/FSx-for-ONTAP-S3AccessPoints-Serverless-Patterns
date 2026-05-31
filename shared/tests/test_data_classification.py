"""Tests for shared.data_classification module."""

import os
from unittest.mock import patch


from shared.data_classification import DataClassification, get_classification


class TestDataClassification:
    """DataClassification enum tests."""

    def test_internal_default(self):
        assert DataClassification.INTERNAL.value == "INTERNAL"
        assert "Internal" in DataClassification.INTERNAL.label

    def test_public_sector_classifications(self):
        assert DataClassification.UNCLASSIFIED.value == "UNCLASSIFIED"
        assert DataClassification.CUI.value == "CUI"
        assert DataClassification.CONFIDENTIAL.value == "CONFIDENTIAL"

    def test_enterprise_classifications(self):
        assert DataClassification.PUBLIC.value == "PUBLIC"
        assert DataClassification.RESTRICTED.value == "RESTRICTED"
        assert DataClassification.HIGHLY_RESTRICTED.value == "HIGHLY_RESTRICTED"


class TestGetClassification:
    """get_classification() tests."""

    def test_default_is_internal(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("DATA_CLASSIFICATION", None)
            result = get_classification()
            assert result == DataClassification.INTERNAL

    def test_env_override_cui(self):
        with patch.dict(os.environ, {"DATA_CLASSIFICATION": "CUI"}):
            result = get_classification()
            assert result == DataClassification.CUI

    def test_env_override_case_insensitive(self):
        with patch.dict(os.environ, {"DATA_CLASSIFICATION": "public"}):
            result = get_classification()
            assert result == DataClassification.PUBLIC

    def test_invalid_value_falls_back_to_internal(self):
        with patch.dict(os.environ, {"DATA_CLASSIFICATION": "INVALID_VALUE"}):
            result = get_classification()
            assert result == DataClassification.INTERNAL
