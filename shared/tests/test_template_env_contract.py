"""ハンドラが必須で読む環境変数を、テンプレートが実際に渡しているかを検証する

## なぜ必要か

`os.environ["X"]` は X が無ければ `KeyError` を投げる。つまり
「ハンドラが必須で読む環境変数」と「テンプレートがその関数に渡す環境変数」の
不一致は、デプロイ後の初回実行で必ず落ちる。

この不一致は既存のどの検査にも掛からなかった:

| 検査 | この不一致を検出するか | 理由 |
|---|:---:|---|
| `cfn-lint` | しない | 環境変数が足りないテンプレートは CloudFormation として正当 |
| テンプレートの部分文字列検査 | しない | 変数名は他の関数や `Parameters` にも出てくるので文字列としては存在する |
| `test_discovery_handlers_behaviour.py` | **しない** | ハーネスが `DEFAULT_ENV` を自分で注入するため、テンプレート側の欠落を隠す |

3 つ目が重要で、ハンドラを実行するテストを足しても、この不一致は隠れたままだった。
実行時に環境変数を与えるテストは「テンプレートが与えてくれるか」を検証できない。

実際に `nonprofit-grant-management` の `OutcomeMatcherFunction` が
`os.environ["S3_ACCESS_POINT"]` を読むのに、テンプレートがそれを渡していない状態で
コミットされていた（このテストを書いた時点で 46 パターン中 1 件）。

## 検証の向き

**必須（既定値なし）で読んでいるのに宣言されていない** ものだけを落とす。

逆向き（宣言されているがハンドラが読まない）は**意図的に検査しない**。
`OUTPUT_S3AP_ALIAS` などは `shared/` 側のモジュールが読むため、handler.py の
AST だけを見ると「未使用」に見える。実測で 99 関数が該当し、そのほとんどが
偽陽性だった。偽陽性 99 件のゲートは無効化されるだけなので、片方向に限定する。

`os.environ.get("X", default)` は既定値があるので対象外。ただし
`os.environ.get("A", os.environ["B"])` の B は**対象**で、Python は既定値の式を
先に評価するため、A が在っても B が無ければ `KeyError` になる。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from shared.testing import load_sam_template

REPO_ROOT = Path(__file__).resolve().parents[2]

TEMPLATES = sorted(
    p.relative_to(REPO_ROOT).as_posix()
    for p in REPO_ROOT.glob("solutions/*/*/template.yaml")
    if ".aws-sam" not in p.as_posix()
)


def _required_env_keys(handler_py: Path) -> set[str]:
    """`os.environ["X"]` の形（既定値なし）で読まれているキー

    添字アクセスのみを集める。`.get()` / `getenv()` は既定値があるので、
    欠落してもクラッシュしない。
    """
    keys: set[str] = set()
    tree = ast.parse(handler_py.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Subscript):
            continue
        value = node.value
        if (
            isinstance(value, ast.Attribute)
            and value.attr == "environ"
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            keys.add(node.slice.value)
    return keys


def _functions_with_code(rel_template: str) -> list[tuple[str, Path]]:
    """(論理 ID, handler.py の絶対パス) の一覧"""
    template_path = REPO_ROOT / rel_template
    tpl = load_sam_template(template_path)
    pairs: list[tuple[str, Path]] = []
    for logical_id, body in tpl.functions().items():
        props = body.get("Properties") or {}
        code_uri = props.get("CodeUri")
        if not isinstance(code_uri, str):
            # インラインコードや別の指定方法。対応関係が引けないので対象外。
            continue
        handler_py = template_path.parent / code_uri.rstrip("/") / "handler.py"
        if handler_py.exists():
            pairs.append((logical_id, handler_py))
    return pairs


def test_templates_are_discovered():
    """対象テンプレートが実際に集まっていることを検証する

    glob が空になると、以下の全テストが「0 件成功」で通ってしまう。
    """
    assert len(TEMPLATES) >= 40, f"expected the pattern templates, found {len(TEMPLATES)}"


@pytest.mark.parametrize("rel_template", TEMPLATES, ids=lambda p: p.split("/")[2])
def test_required_env_vars_are_declared_in_the_template(rel_template):
    """必須で読む環境変数が、その関数の Environment.Variables にあることを検証する

    足りなければ、そのパターンはデプロイ後の初回実行で `KeyError` になる。
    """
    tpl = load_sam_template(REPO_ROOT / rel_template)

    missing: list[str] = []
    for logical_id, handler_py in _functions_with_code(rel_template):
        declared = set(tpl.function_env(logical_id))
        for key in sorted(_required_env_keys(handler_py) - declared):
            missing.append(f"{logical_id} reads os.environ[{key!r}] but the template does not pass it")

    assert not missing, "environment variables required by the handler are not declared:\n  " + "\n  ".join(missing)


@pytest.mark.parametrize("rel_template", TEMPLATES, ids=lambda p: p.split("/")[2])
def test_conditions_only_reference_defined_names(rel_template):
    """Conditions が未定義の名前を参照していないことを検証する

    パラメータを削除して `Conditions` の `!Ref` が残る、という壊れ方を検出する。
    テンプレートを文字列として検査すると、削除した名前が `Conditions` 側に文字列
    として残るため通ってしまう（実測で確認済み）。

    `cfn-lint` も E1020 で検出するので、ここは多重防御。落ちたときに
    「どの名前が」を直接示す点が違う。
    """
    tpl = load_sam_template(REPO_ROOT / rel_template)

    undefined = sorted(tpl.undefined_condition_refs())

    assert not undefined, f"Conditions reference names that are not defined: {undefined}"
