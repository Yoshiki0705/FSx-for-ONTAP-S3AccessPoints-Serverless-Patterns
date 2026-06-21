"""UC19 Report Lambda — Unit Tests

アセットカタログ生成ロジックのテスト:
- カタログレコード構築 (JSON + CSV)
- モデレーション評価 (requires-review フラグ付け)
- CSV 生成
- EMF メトリクス出力

Requirements: 13.4
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

# shared モジュールのパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Report handler
_report_path = os.path.join(os.path.dirname(__file__), "..", "functions", "report", "handler.py")
_report_spec = importlib.util.spec_from_file_location("adtech_report_handler", _report_path)
_report_module = importlib.util.module_from_spec(_report_spec)
_report_spec.loader.exec_module(_report_module)

evaluate_moderation_status = _report_module.evaluate_moderation_status
build_catalog_record = _report_module.build_catalog_record
generate_csv_content = _report_module.generate_csv_content
aggregate_results = _report_module.aggregate_results
get_moderation_threshold = _report_module.get_moderation_threshold


# ============================================================
# evaluate_moderation_status() テスト
# ============================================================


class TestEvaluateModerationStatus:
    """モデレーション評価のテスト"""

    def test_requires_review_at_threshold(self):
        """確信度が閾値と一致する場合 requires-review"""
        labels = [{"name": "Violence", "confidence": 80.0}]
        result = evaluate_moderation_status(labels, threshold=80.0)
        assert result["review_status"] == "requires-review"
        assert result["violation_category"] == "Violence"
        assert result["violation_confidence"] == 80.0

    def test_requires_review_above_threshold(self):
        """確信度が閾値を超える場合 requires-review"""
        labels = [{"name": "Explicit Nudity", "confidence": 95.0}]
        result = evaluate_moderation_status(labels, threshold=80.0)
        assert result["review_status"] == "requires-review"
        assert result["violation_category"] == "Explicit Nudity"

    def test_approved_below_threshold(self):
        """確信度が閾値未満の場合 approved"""
        labels = [{"name": "Suggestive", "confidence": 65.0}]
        result = evaluate_moderation_status(labels, threshold=80.0)
        assert result["review_status"] == "approved"
        assert result["violation_category"] is None
        assert result["violation_confidence"] is None

    def test_approved_empty_labels(self):
        """ラベルが空の場合 approved"""
        result = evaluate_moderation_status([], threshold=80.0)
        assert result["review_status"] == "approved"

    def test_first_violation_returned(self):
        """複数ラベルの場合、最初の閾値超過が返される"""
        labels = [
            {"name": "Suggestive", "confidence": 60.0},
            {"name": "Violence", "confidence": 85.0},
            {"name": "Explicit", "confidence": 92.0},
        ]
        result = evaluate_moderation_status(labels, threshold=80.0)
        assert result["violation_category"] == "Violence"
        assert result["violation_confidence"] == 85.0


# ============================================================
# build_catalog_record() テスト
# ============================================================


class TestBuildCatalogRecord:
    """カタログレコード構築のテスト"""

    def test_basic_record(self):
        """基本的なカタログレコードが正しく構築される"""
        asset_result = {
            "key": "creatives/banner.jpg",
            "status": "success",
            "moderation_labels": [],
            "tags": ["Car", "Road"],
            "tag_count": 2,
            "compliance": {"status": "compliant", "violations": []},
            "processing_timestamp": "2026-06-01T00:00:00Z",
        }

        record = build_catalog_record(asset_result, None, threshold=80.0)

        assert record["asset_key"] == "creatives/banner.jpg"
        assert record["status"] == "success"
        assert record["review_status"] == "approved"
        assert record["tags"] == ["Car", "Road"]
        assert record["tag_count"] == 2
        assert record["compliance_status"] == "compliant"
        assert record["text_compliance_status"] == "not_checked"

    def test_record_with_moderation_violation(self):
        """モデレーション違反ありのレコード"""
        asset_result = {
            "key": "creatives/ad.jpg",
            "status": "success",
            "moderation_labels": [
                {"name": "Violence", "confidence": 90.0, "parent_name": ""},
            ],
            "tags": ["Person"],
            "tag_count": 1,
            "compliance": {"status": "non-compliant", "violations": []},
            "processing_timestamp": "2026-06-01T00:00:00Z",
        }

        record = build_catalog_record(asset_result, None, threshold=80.0)

        assert record["review_status"] == "requires-review"
        assert record["violation_category"] == "Violence"
        assert record["violation_confidence"] == 90.0

    def test_record_with_text_compliance(self):
        """Text Compliance 結果が統合される"""
        asset_result = {
            "key": "creatives/banner.jpg",
            "status": "success",
            "moderation_labels": [],
            "tags": [],
            "tag_count": 0,
            "compliance": {"status": "compliant", "violations": []},
            "processing_timestamp": "2026-06-01T00:00:00Z",
        }
        text_result = {
            "key": "creatives/banner.jpg",
            "status": "success",
            "compliance_result": "non-compliant",
        }

        record = build_catalog_record(asset_result, text_result, threshold=80.0)

        assert record["text_compliance_status"] == "non-compliant"


# ============================================================
# generate_csv_content() テスト
# ============================================================


class TestGenerateCsvContent:
    """CSV 生成のテスト"""

    def test_csv_header_and_rows(self):
        """CSV にヘッダーとデータ行が含まれる"""
        records = [
            {
                "asset_key": "img.jpg",
                "status": "success",
                "review_status": "approved",
                "violation_category": None,
                "violation_confidence": None,
                "tags": ["Car", "Road"],
                "tag_count": 2,
                "compliance_status": "compliant",
                "moderation_labels": [],
                "text_compliance_status": "not_checked",
                "processing_timestamp": "2026-06-01T00:00:00Z",
            }
        ]

        csv_content = generate_csv_content(records)

        lines = csv_content.strip().split("\n")
        assert len(lines) == 2  # header + 1 row
        assert "asset_key" in lines[0]
        assert "img.jpg" in lines[1]

    def test_csv_with_moderation_labels(self):
        """モデレーションラベルが ; 区切りで CSV に含まれる"""
        records = [
            {
                "asset_key": "ad.jpg",
                "status": "success",
                "review_status": "requires-review",
                "violation_category": "Violence",
                "violation_confidence": 90.0,
                "tags": [],
                "tag_count": 0,
                "compliance_status": "non-compliant",
                "moderation_labels": [
                    {"name": "Violence", "confidence": 90.0},
                    {"name": "Graphic", "confidence": 85.0},
                ],
                "text_compliance_status": "compliant",
                "processing_timestamp": "2026-06-01T00:00:00Z",
            }
        ]

        csv_content = generate_csv_content(records)

        assert "Violence(90.0%)" in csv_content
        assert "Graphic(85.0%)" in csv_content

    def test_csv_empty_records(self):
        """空レコードリストの場合ヘッダーのみ"""
        csv_content = generate_csv_content([])
        lines = csv_content.strip().split("\n")
        assert len(lines) == 1  # header only
        assert "asset_key" in lines[0]

    def test_csv_tags_semicolon_separated(self):
        """タグが ; 区切りで出力される"""
        records = [
            {
                "asset_key": "img.png",
                "status": "success",
                "review_status": "approved",
                "violation_category": None,
                "violation_confidence": None,
                "tags": ["Car", "Road", "Sky"],
                "tag_count": 3,
                "compliance_status": "compliant",
                "moderation_labels": [],
                "text_compliance_status": "not_checked",
                "processing_timestamp": "2026-06-01T00:00:00Z",
            }
        ]

        csv_content = generate_csv_content(records)

        assert "Car;Road;Sky" in csv_content


# ============================================================
# aggregate_results() テスト
# ============================================================


class TestAggregateResults:
    """結果集約のテスト"""

    def test_aggregate_normal(self):
        """正常な結果集約"""
        event = {
            "visual_results": [
                {"key": "a.jpg", "status": "success"},
                {"key": "b.jpg", "status": "success"},
            ],
            "text_results": [
                {"key": "a.jpg", "status": "success", "compliance_result": "compliant"},
            ],
        }
        visual, text = aggregate_results(event)
        assert len(visual) == 2
        assert len(text) == 1

    def test_aggregate_empty(self):
        """空イベントの場合は空リスト"""
        event = {}
        visual, text = aggregate_results(event)
        assert visual == []
        assert text == []

    def test_aggregate_non_list(self):
        """リスト以外の値は空リストに正規化"""
        event = {"visual_results": "invalid", "text_results": 123}
        visual, text = aggregate_results(event)
        assert visual == []
        assert text == []


# ============================================================
# get_moderation_threshold() テスト
# ============================================================


class TestGetModerationThreshold:
    """モデレーション閾値取得のテスト"""

    def test_default_threshold(self):
        """デフォルト値は 80.0"""
        with pytest.MonkeyPatch.context() as m:
            m.delenv("MODERATION_CONFIDENCE_THRESHOLD", raising=False)
            assert get_moderation_threshold() == 80.0

    def test_custom_threshold(self):
        """カスタム値が設定される"""
        with pytest.MonkeyPatch.context() as m:
            m.setenv("MODERATION_CONFIDENCE_THRESHOLD", "90")
            assert get_moderation_threshold() == 90.0

    def test_invalid_threshold_fallback(self):
        """無効な値のフォールバック"""
        with pytest.MonkeyPatch.context() as m:
            m.setenv("MODERATION_CONFIDENCE_THRESHOLD", "abc")
            assert get_moderation_threshold() == 80.0
