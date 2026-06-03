"""UC20 Travel Document Processing — Processing Lambdas unit tests."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Dynamic import — reservation_extractor
_re_path = (
    Path(__file__).parent.parent / "functions" / "reservation_extractor" / "handler.py"
)
_re_spec = importlib.util.spec_from_file_location("travel_reservation_handler", _re_path)
_re_module = importlib.util.module_from_spec(_re_spec)
sys.modules["travel_reservation_handler"] = _re_module
_re_spec.loader.exec_module(_re_module)

# Dynamic import — facility_inspector
_fi_path = (
    Path(__file__).parent.parent / "functions" / "facility_inspector" / "handler.py"
)
_fi_spec = importlib.util.spec_from_file_location("travel_facility_handler", _fi_path)
_fi_module = importlib.util.module_from_spec(_fi_spec)
sys.modules["travel_facility_handler"] = _fi_module
_fi_spec.loader.exec_module(_fi_module)


class TestReservationExtractor:
    """予約文書抽出ロジックのテスト"""

    def test_detect_language_japanese(self):
        mock_client = MagicMock()
        mock_client.detect_dominant_language.return_value = {
            "Languages": [{"LanguageCode": "ja", "Score": 0.99}]
        }
        result = _re_module.detect_language("日本語のテキストサンプルです。テストデータ。", mock_client)
        assert result == "ja"

    def test_detect_language_english(self):
        mock_client = MagicMock()
        mock_client.detect_dominant_language.return_value = {
            "Languages": [{"LanguageCode": "en", "Score": 0.95}]
        }
        result = _re_module.detect_language(
            "This is an English document sample text.", mock_client
        )
        assert result == "en"

    def test_detect_language_short_text_defaults_ja(self):
        mock_client = MagicMock()
        result = _re_module.detect_language("短い", mock_client)
        assert result == "ja"

    def test_detect_language_failure_defaults_ja(self):
        mock_client = MagicMock()
        mock_client.detect_dominant_language.side_effect = RuntimeError("API error")
        result = _re_module.detect_language("Some text for detection.", mock_client)
        assert result == "ja"

    def test_get_textract_hints_japanese(self):
        hints = _re_module.get_textract_hints("ja")
        assert hints == ["JAPANESE"]

    def test_get_textract_hints_english(self):
        hints = _re_module.get_textract_hints("en")
        assert hints == ["ENGLISH"]

    def test_get_textract_hints_unknown(self):
        hints = _re_module.get_textract_hints("xx")
        assert hints is None

    def test_extract_structured_data_with_dates(self):
        text = "チェックイン: 2026-01-15\nチェックアウト: 2026-01-18\n金額: ¥50,000\n部屋: ツイン"
        result = _re_module.extract_structured_data(text, "ja")
        assert result["check_in_date"] == "2026-01-15"
        assert result["check_out_date"] == "2026-01-18"
        assert result["amount"] == "¥50,000"
        assert result["room_type"] == "ツイン"

    def test_extract_structured_data_english(self):
        text = "Check-in: 2026-03-10\nCheck-out: 2026-03-12\nAmount: $350.00\nRoom: Double"
        result = _re_module.extract_structured_data(text, "en")
        assert result["check_in_date"] == "2026-03-10"
        assert result["check_out_date"] == "2026-03-12"
        assert result["amount"] == "$350.00"
        assert result["room_type"] == "double"  # keyword match is case-insensitive

    def test_extract_structured_data_empty_text(self):
        result = _re_module.extract_structured_data("", "ja")
        assert result["guest_name"] is None
        assert result["check_in_date"] is None
        assert result["room_type"] is None
        assert result["amount"] is None

    def test_extract_guest_name_japanese(self):
        text = "お名前: 田中太郎\nチェックイン: 2026-01-15"
        result = _re_module.extract_structured_data(text, "ja")
        assert result["guest_name"] == "田中太郎"

    def test_extract_guest_name_english(self):
        text = "Guest: John Smith\nCheck-in: 2026-01-15"
        result = _re_module.extract_structured_data(text, "en")
        assert result["guest_name"] == "John Smith"


class TestFacilityInspector:
    """施設点検ロジックのテスト"""

    def test_calculate_cleanliness_score_clean(self):
        labels = [
            {"Name": "Clean", "Confidence": 95.0},
            {"Name": "Tidy", "Confidence": 90.0},
        ]
        score = _fi_module.calculate_cleanliness_score(labels)
        assert 70 <= score <= 100

    def test_calculate_cleanliness_score_dirty(self):
        labels = [
            {"Name": "Stain", "Confidence": 95.0},
            {"Name": "Mold", "Confidence": 90.0},
            {"Name": "Dirt", "Confidence": 85.0},
        ]
        score = _fi_module.calculate_cleanliness_score(labels)
        assert score < 70

    def test_calculate_cleanliness_score_empty_labels(self):
        score = _fi_module.calculate_cleanliness_score([])
        assert score == 70  # base score

    def test_calculate_cleanliness_score_below_threshold(self):
        labels = [
            {"Name": "Stain", "Confidence": 50.0},  # Below MIN_CONFIDENCE_THRESHOLD
        ]
        score = _fi_module.calculate_cleanliness_score(labels)
        assert score == 70  # No impact from below-threshold labels

    def test_calculate_cleanliness_score_bounds(self):
        # Maximum negative: many damage + dirt labels at 100% confidence
        labels = [
            {"Name": name, "Confidence": 100.0}
            for name in ["Stain", "Mold", "Dirt", "Crack", "Rust", "Corrosion",
                         "Debris", "Garbage", "Grime", "Damage"]
        ]
        score = _fi_module.calculate_cleanliness_score(labels)
        assert 0 <= score <= 100

    def test_detect_damage_with_damages(self):
        labels = [
            {"Name": "Crack", "Confidence": 85.0, "Instances": []},
            {"Name": "Rust", "Confidence": 92.0, "Instances": []},
            {"Name": "Floor", "Confidence": 99.0, "Instances": []},
        ]
        damages = _fi_module.detect_damage(labels)
        assert len(damages) == 2
        assert damages[0]["type"] == "Crack"
        assert damages[1]["type"] == "Rust"

    def test_detect_damage_below_threshold(self):
        labels = [
            {"Name": "Crack", "Confidence": 50.0, "Instances": []},
        ]
        damages = _fi_module.detect_damage(labels)
        assert len(damages) == 0

    def test_detect_damage_no_damage(self):
        labels = [
            {"Name": "Floor", "Confidence": 99.0, "Instances": []},
            {"Name": "Wall", "Confidence": 95.0, "Instances": []},
        ]
        damages = _fi_module.detect_damage(labels)
        assert len(damages) == 0

    def test_generate_recommendations_no_issues(self):
        mock_client = MagicMock()
        result = _fi_module.generate_maintenance_recommendations(
            damages=[], cleanliness_score=90, bedrock_client=mock_client, model_id="test"
        )
        assert len(result) == 1
        assert "No immediate maintenance" in result[0]

    def test_generate_recommendations_bedrock_failure(self):
        mock_client = MagicMock()
        mock_client.invoke_model.side_effect = RuntimeError("Bedrock error")
        result = _fi_module.generate_maintenance_recommendations(
            damages=[{"type": "Crack", "confidence": 85.0}],
            cleanliness_score=50,
            bedrock_client=mock_client,
            model_id="test",
        )
        # Should fallback to static recommendations
        assert len(result) >= 1
