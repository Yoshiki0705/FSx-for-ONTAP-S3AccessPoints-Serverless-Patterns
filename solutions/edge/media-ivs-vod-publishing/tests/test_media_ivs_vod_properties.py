"""media-ivs-vod-publishing プロパティベーステスト（hypothesis）

repo 慣習に合わせ、ハンドラをモジュールロードして純粋関数の不変条件を検証する
（function-scoped fixture を使わないことで hypothesis の health check 問題を回避）。

検証する不変条件:
- `_score_package` の confidence は常に [0.0, 1.0]、master 判定は master 名一致と整合
- master manifest 有 + セグメント有 → AUTO_APPROVE 相当（confidence >= 0.85）
- manifest もセグメントも無い → REJECT 相当（confidence < 0.30）
- `_extract_recording_context` は Recording End イベントから status と prefix を取り出す
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytest.importorskip("hypothesis")
from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent))


def _load(function_name: str):
    module_name = f"prop_media_ivs_vod_{function_name}"
    handler_path = Path(__file__).resolve().parent.parent / "functions" / function_name / "handler.py"
    spec = importlib.util.spec_from_file_location(module_name, handler_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_publish = _load("publish")

_names = st.sampled_from(["master.m3u8", "index.m3u8", "0.ts", "1.ts", "seg.m4s", "thumb.jpg", "meta.json"])


@given(names=st.lists(_names, max_size=10))
@settings(max_examples=100, deadline=None)
def test_score_package_confidence_bounds(names):
    """confidence は常に [0,1]、master_key は keys の部分集合か空。"""
    keys = [f"ivs/v1/a/b/c/{n}" for n in names]
    confidence, has_master, master_key = _publish._score_package(keys, "master.m3u8")
    assert 0.0 <= confidence <= 1.0
    assert has_master == any(k.endswith("master.m3u8") for k in keys)
    if master_key:
        assert master_key in keys
    else:
        assert has_master is False


@given(seg=st.sampled_from(["0.ts", "1.m4s", "v.mp4"]))
@settings(max_examples=50, deadline=None)
def test_master_plus_segments_is_high_confidence(seg):
    """master manifest + セグメント → AUTO_APPROVE 相当（>= 0.85）。"""
    keys = ["p/master.m3u8", f"p/{seg}"]
    confidence, has_master, _ = _publish._score_package(keys, "master.m3u8")
    assert has_master is True
    assert confidence >= 0.85


@given(junk=st.lists(st.sampled_from(["thumb.jpg", "meta.json", "notes.txt"]), max_size=5))
@settings(max_examples=50, deadline=None)
def test_no_manifest_no_segments_is_low_confidence(junk):
    """manifest もセグメントも無い → REJECT 相当（< 0.30）。"""
    keys = [f"p/{n}" for n in junk]
    confidence, has_master, _ = _publish._score_package(keys, "master.m3u8")
    assert has_master is False
    assert confidence < 0.30


@given(prefix=st.text(min_size=1, max_size=40).filter(lambda s: "\x00" not in s))
@settings(max_examples=50, deadline=None)
def test_extract_context_recording_end(prefix):
    """Recording End イベントから status と prefix を正しく取り出す。"""
    event = {
        "detail": {
            "recording_status": "Recording End",
            "recording_s3_key_prefix": prefix,
            "recording_s3_bucket_name": "b",
            "recording_session_id": "s",
            "channel_name": "c",
        }
    }
    ctx = _publish._extract_recording_context(event)
    assert ctx["recording_status"] == "Recording End"
    assert ctx["recording_prefix"] == prefix
