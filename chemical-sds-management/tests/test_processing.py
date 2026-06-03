"""UC28 Chemical SDS Management — Processing Lambda unit tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Dynamic import — sds_extractor
_se_path = Path(__file__).parent.parent / "functions" / "sds_extractor" / "handler.py"
_se_spec = importlib.util.spec_from_file_location("chem_sds_extractor", _se_path)
_se_module = importlib.util.module_from_spec(_se_spec)
sys.modules["chem_sds_extractor"] = _se_module
_se_spec.loader.exec_module(_se_module)

check_ghs_sections = _se_module.check_ghs_sections
get_missing_ghs_sections = _se_module.get_missing_ghs_sections
check_sds_expiry = _se_module.check_sds_expiry
GHS_MANDATORY_SECTIONS = _se_module.GHS_MANDATORY_SECTIONS

# Dynamic import — labbook_analyzer
_la_path = Path(__file__).parent.parent / "functions" / "labbook_analyzer" / "handler.py"
_la_spec = importlib.util.spec_from_file_location("chem_labbook_analyzer", _la_path)
_la_module = importlib.util.module_from_spec(_la_spec)
sys.modules["chem_labbook_analyzer"] = _la_module
_la_spec.loader.exec_module(_la_module)

parse_experiment_data = _la_module.parse_experiment_data


class TestCheckGhsSections:
    def test_all_sections_present(self):
        text = (
            "化学品の名称: テスト物質\n"
            "危険有害性の要約: GHS分類\n"
            "組成及び成分情報\n"
            "応急措置\n"
            "火災時の措置\n"
            "漏出時の措置\n"
            "取扱い及び保管\n"
            "ばく露防止及び保護措置\n"
        )
        result = check_ghs_sections(text)
        assert all(result.values())

    def test_missing_sections(self):
        text = "化学品の名称: テスト物質\n組成: H2O"
        result = check_ghs_sections(text)
        assert result["identification"] is True
        assert result["composition"] is True
        assert result["first_aid"] is False
        assert result["fire_fighting"] is False

    def test_english_sections(self):
        text = (
            "Product identification\n"
            "Hazard classification\n"
            "Composition\n"
            "First aid measures\n"
            "Fire fighting measures\n"
            "Accidental release\n"
            "Handling and storage\n"
            "Exposure controls\n"
        )
        result = check_ghs_sections(text)
        assert all(result.values())

    def test_empty_text(self):
        result = check_ghs_sections("")
        assert not any(result.values())


class TestGetMissingGhsSections:
    def test_no_missing(self):
        ghs_check = {s: True for s in GHS_MANDATORY_SECTIONS}
        result = get_missing_ghs_sections(ghs_check)
        assert result == []

    def test_some_missing(self):
        ghs_check = {s: False for s in GHS_MANDATORY_SECTIONS}
        ghs_check["identification"] = True
        result = get_missing_ghs_sections(ghs_check)
        assert "identification" not in result
        assert len(result) == 7


class TestCheckSdsExpiry:
    def test_expired_sds(self):
        # 2 years ago
        result = check_sds_expiry("2022-01-01", validity_days=365)
        assert result["is_expired"] is True
        assert result["priority"] == "critical"
        assert result["days_since_revision"] > 365

    def test_valid_sds(self):
        # Today
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        result = check_sds_expiry(today, validity_days=365)
        assert result["is_expired"] is False
        assert result["priority"] is None

    def test_no_revision_date(self):
        result = check_sds_expiry(None, validity_days=365)
        assert result["is_expired"] is False
        assert result["days_since_revision"] is None

    def test_invalid_date_format(self):
        result = check_sds_expiry("not-a-date", validity_days=365)
        assert result["is_expired"] is False


class TestParseExperimentData:
    def test_parameters_extraction(self):
        text = "温度: 25°C\n圧力: 1atm\n結果: 成功"
        result = parse_experiment_data(text)
        assert len(result["parameters"]) >= 1
        assert any("温度" in p for p in result["parameters"])

    def test_results_extraction(self):
        text = "実験手順...\n結果: 収率 85%\n生成物 5g"
        result = parse_experiment_data(text)
        assert len(result["results"]) >= 1

    def test_observations_extraction(self):
        text = "観察: 色の変化あり\n備考: pH変動あり"
        result = parse_experiment_data(text)
        assert len(result["observations"]) >= 1

    def test_empty_text(self):
        result = parse_experiment_data("")
        assert result["parameters"] == []
        assert result["results"] == []
        assert result["observations"] == []

    def test_max_items_limit(self):
        text = "\n".join([f"温度: {i}°C" for i in range(50)])
        result = parse_experiment_data(text)
        assert len(result["parameters"]) <= 20
