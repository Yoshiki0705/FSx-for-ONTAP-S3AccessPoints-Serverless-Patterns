"""Property-based tests for the report aggregation.

The report handler aggregates an arbitrary list of per-file results from the Map
state. These properties assert the aggregation stays consistent for any shape of
input the workflow can produce.
"""

from __future__ import annotations

import os
from unittest.mock import patch

from helpers import load_handler
from hypothesis import given, settings
from hypothesis import strategies as st

_result = st.fixed_dictionaries(
    {
        "status": st.sampled_from(["completed", "error"]),
        "category": st.sampled_from(["sap_idoc", "data_extract", "general", "unknown"]),
        "human_review": st.fixed_dictionaries({"requires_review": st.booleans()}),
    }
)


@settings(deadline=None, max_examples=100)
@given(results=st.lists(_result, max_size=50))
def test_summary_counts_are_consistent(results):
    """Succeeded + failed equals total, and review count never exceeds total."""
    module = load_handler("report")
    with patch.dict(os.environ, {"DATA_CLASSIFICATION": "INTERNAL"}), patch.object(module._sns, "publish"):
        out = module.handler({"processed": results}, None)

    summary = out["report"]["summary"]
    total = summary["total_files"]
    assert total == len(results)
    assert summary["succeeded"] + summary["failed"] == total
    assert 0 <= summary["human_review_required"] <= total
    assert 0.0 <= summary["success_rate_pct"] <= 100.0


@settings(deadline=None, max_examples=50)
@given(results=st.lists(_result, min_size=1, max_size=50))
def test_category_breakdown_sums_to_total(results):
    """The per-category counts sum to the total file count."""
    module = load_handler("report")
    with patch.dict(os.environ, {"DATA_CLASSIFICATION": "INTERNAL"}), patch.object(module._sns, "publish"):
        out = module.handler({"processed": results}, None)

    report = out["report"]
    assert sum(report["category_breakdown"].values()) == report["summary"]["total_files"]
