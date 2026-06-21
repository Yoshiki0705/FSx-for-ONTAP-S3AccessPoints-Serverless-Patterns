"""UC26 Real Estate Portfolio — Processing Lambda unit tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Dynamic import — property_analyzer
_pa_path = Path(__file__).parent.parent / "functions" / "property_analyzer" / "handler.py"
_pa_spec = importlib.util.spec_from_file_location("realestate_property_analyzer", _pa_path)
_pa_module = importlib.util.module_from_spec(_pa_spec)
sys.modules["realestate_property_analyzer"] = _pa_module
_pa_spec.loader.exec_module(_pa_module)

check_pii_in_image = _pa_module.check_pii_in_image
ROOM_LABELS = _pa_module.ROOM_LABELS
AMENITY_LABELS = _pa_module.AMENITY_LABELS

# Dynamic import — contract_extractor
_ce_path = Path(__file__).parent.parent / "functions" / "contract_extractor" / "handler.py"
_ce_spec = importlib.util.spec_from_file_location("realestate_contract_extractor", _ce_path)
_ce_module = importlib.util.module_from_spec(_ce_spec)
sys.modules["realestate_contract_extractor"] = _ce_module
_ce_spec.loader.exec_module(_ce_module)

extract_lease_terms = _ce_module.extract_lease_terms


class TestCheckPiiInImage:
    """PII 検出ロジックのテスト"""

    def test_no_pii_detected(self):
        text_detections = [
            {"text": "Welcome", "confidence": 95.0},
            {"text": "Room 101", "confidence": 90.0},
        ]
        assert check_pii_in_image(text_detections) is False

    def test_pii_nameplate_detected(self):
        text_detections = [
            {"text": "表札: 田中", "confidence": 95.0},
        ]
        assert check_pii_in_image(text_detections) is True

    def test_pii_document_detected(self):
        text_detections = [
            {"text": "document on table", "confidence": 90.0},
        ]
        assert check_pii_in_image(text_detections) is True

    def test_pii_many_text_lines(self):
        # 10+ text lines indicates document in frame
        text_detections = [{"text": f"line {i}", "confidence": 90.0} for i in range(12)]
        assert check_pii_in_image(text_detections) is True

    def test_empty_detections(self):
        assert check_pii_in_image([]) is False


class TestExtractLeaseTerms:
    """契約条件抽出ロジックのテスト"""

    def test_rent_extraction_yen(self):
        text = "賃料: 150,000円\n契約期間: 2年"
        result = extract_lease_terms(text, [])
        assert result["rent_amount"] == 150000

    def test_rent_extraction_man_yen(self):
        text = "月額家賃: 15万円"
        result = extract_lease_terms(text, [])
        assert result["rent_amount"] == 150000

    def test_lease_period_years(self):
        text = "賃料: 100,000円\n契約期間: 2年"
        result = extract_lease_terms(text, [])
        assert result["lease_period_months"] == 24

    def test_lease_period_months(self):
        text = "賃貸期間: 6ヶ月"
        result = extract_lease_terms(text, [])
        assert result["lease_period_months"] == 6

    def test_tenant_from_entities(self):
        text = "テナント: 田中太郎"
        entities = [{"text": "田中太郎", "type": "PERSON", "score": 0.95}]
        result = extract_lease_terms(text, entities)
        assert result["tenant_name"] == "田中太郎"

    def test_special_conditions(self):
        text = "賃料: 100,000円\nペット飼育禁止\n解約は3ヶ月前通知"
        result = extract_lease_terms(text, [])
        assert len(result["special_conditions"]) == 2

    def test_empty_text(self):
        result = extract_lease_terms("", [])
        assert result["rent_amount"] is None
        assert result["lease_period_months"] is None
        assert result["tenant_name"] is None

    def test_special_conditions_limit(self):
        text = "\n".join([f"特約条件{i}: 内容あり" for i in range(20)])
        result = extract_lease_terms(text, [])
        assert len(result["special_conditions"]) <= 10
