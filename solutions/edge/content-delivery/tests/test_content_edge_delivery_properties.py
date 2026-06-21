"""content-edge-delivery プロパティベーステスト（hypothesis）

QA 観点: permission-aware フィルタと PII マスクの不変条件を property-based で検証する。
hypothesis 未インストール環境（一部のローカル）では自動 skip される。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# hypothesis はCI(requirements-dev)に存在。未導入環境ではスキップ。
pytest.importorskip("hypothesis")
from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def _load(function_name: str):
    module_name = f"prop_content_edge_delivery_{function_name}"
    handler_path = Path(__file__).resolve().parent.parent / "functions" / function_name / "handler.py"
    spec = importlib.util.spec_from_file_location(module_name, handler_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_publish = _load("publish")
_log_sync = _load("delivery_log_sync")


@given(
    keys=st.lists(st.text(min_size=1, max_size=40), max_size=20),
    suffix=st.sampled_from(["", ".mp4", ".m3u8", ".ts"]),
)
@settings(max_examples=100, deadline=None)
def test_filter_targets_subset_and_suffix_invariant(keys, suffix):
    """_filter_targets は常に入力の部分集合であり、空サフィックス以外は suffix 一致のみ。"""
    objects = [{"Key": k} for k in keys]
    out = _publish._filter_targets(objects, suffix)
    assert all(o in objects for o in out)
    if suffix:
        assert all(o["Key"].lower().endswith(suffix) for o in out)
    else:
        assert out == objects


@given(ip=st.text(max_size=30))
@settings(max_examples=100, deadline=None)
def test_redact_ip_never_returns_full_ipv4(ip):
    """_redact_ip は完全な 4 オクテット数値 IPv4 をそのまま返さない（下位をマスク）。"""
    redacted = _log_sync._redact_ip(ip)
    parts = ip.split(".")
    if len(parts) == 4 and all(p.isdigit() for p in parts):
        assert redacted.endswith(".x.x")
