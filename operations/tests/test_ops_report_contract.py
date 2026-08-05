"""operations/ 6 パターンの report ハンドラに共通する出力契約のテスト

AGENTS.md の検証チェックリストは「出力を追加するなら data_classification を含める」
と定めているが、operations/ の 6 パターンはいずれも欠いていた。個別テストに 6 回
同じ検査を書くのではなく、ここで横断的に固定する。

パターン固有のロジック（推奨の出し方、コスト計算など）は各パターンのテストの仕事。
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

OPS_PATTERNS = [
    "capacity-rightsizing",
    "storage-efficiency",
    "tiering-optimizer",
    "snapshot-lifecycle",
    "cost-optimization",
    "qos-monitoring",
]


def _load_report_module(pattern: str):
    """report ハンドラを読み込む。

    ハンドラはパッケージではなくファイルなので、パスから直接読み込む。
    モジュール名は毎回変えて、パターン間で同名衝突が起きないようにする。
    """
    path = REPO_ROOT / "operations" / pattern / "functions" / "report" / "handler.py"
    assert path.exists(), f"report handler not found for {pattern}"
    mod_name = f"ops_report_{pattern.replace('-', '_')}_{uuid.uuid4().hex[:8]}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(mod_name, None)
        raise
    return module, mod_name


@pytest.fixture(params=OPS_PATTERNS, ids=OPS_PATTERNS)
def report_module(request):
    module, mod_name = _load_report_module(request.param)
    yield request.param, module
    sys.modules.pop(mod_name, None)


def test_report_handler_exposes_data_classification(report_module):
    """report ハンドラが分類ラベルのヘルパーを持つことを検証する"""
    pattern, module = report_module

    assert hasattr(module, "_data_classification"), f"{pattern} report handler has no _data_classification()"


def test_default_classification_is_internal(report_module, monkeypatch):
    """既定の分類が INTERNAL であることを検証する

    OPS のレポートは容量・コスト・QoS 設定といった運用メタデータで、顧客データ
    そのものではない。PUBLIC は誤り、CUI 等は過剰。
    """
    _, module = report_module
    monkeypatch.delenv("DATA_CLASSIFICATION", raising=False)

    assert module._data_classification() == "INTERNAL"


def test_classification_is_overridable(report_module, monkeypatch):
    """環境変数で分類を上書きできることを検証する

    規制環境では同じレポートをより厳しい分類で扱う必要がある。
    """
    _, module = report_module
    monkeypatch.setenv("DATA_CLASSIFICATION", "RESTRICTED")

    assert module._data_classification() == "RESTRICTED"


def test_classification_label_is_a_known_value(report_module, monkeypatch):
    """既定値が shared/data_classification.py のラベル集合に含まれることを検証する

    ここが独自の文字列に変わると、下流の分類ベースの処理と噛み合わなくなる。
    """
    from shared.data_classification import DataClassification

    _, module = report_module
    monkeypatch.delenv("DATA_CLASSIFICATION", raising=False)

    known = {c.value for c in DataClassification}
    assert module._data_classification() in known


def test_all_six_patterns_are_covered():
    """6 パターン全てが対象になっていることを検証する

    パターンを増やしたときにこのリストへの追加を忘れると、その 1 つだけ
    契約が守られない状態になる。
    """
    found = sorted(p.parent.parent.parent.name for p in REPO_ROOT.glob("operations/*/functions/report/handler.py"))
    assert found == sorted(OPS_PATTERNS), f"OPS_PATTERNS is out of sync with the tree: {found}"
