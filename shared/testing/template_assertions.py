"""SAM / CloudFormation テンプレートを構造として検査するためのヘルパー

## なぜこれが必要か

パターン側のテンプレート検査は、テンプレートを文字列として読み、部分文字列の
有無だけを見ている:

    with open(template_path) as f:
        content = f.read()
    assert "EnableVpcEndpoints" in content

これは「そのファイルのどこかにその文字列がある」ことしか示さない。次のいずれでも
通ってしまう:

- `Description` や YAML コメントに名前が出てくるだけで、`Parameters` には無い
- `Parameters` から消えたが `Conditions` の `!Ref` が残っている（デプロイ不能な
  壊れたテンプレート）
- 環境変数として渡すつもりの名前が、実際にはどの関数の `Environment` にも無い

つまり「壊れたテンプレート」を緑にできる。パラメータを消してもテストが落ちない
ことは実際に確認済み（`Conditions` 側の参照が文字列として残るため）。

ここでは YAML として解析し、`Parameters` / `Resources` / `Conditions` の
どこに在るかを問う。名前が期待した場所に無ければ落ちる。

## CloudFormation の短縮タグ

`!Ref` `!Sub` `!GetAtt` `!Equals` などは YAML の独自タグなので
`yaml.safe_load` は `could not determine a constructor` で失敗する。ここでは
タグを保持したプレースホルダとして読み込む。値そのものの検証はしないので、
解決はしない（解決には CloudFormation が必要で、それは cfn-lint の仕事）。

## 使い方

    from shared.testing import load_sam_template

    tpl = load_sam_template("solutions/industry/media-vfx/template.yaml")
    assert "EnableVpcEndpoints" in tpl.parameters
    assert "SUFFIX_FILTER" in tpl.all_function_env_names()
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class _CfnTag:
    """`!Ref` などの短縮タグを、解決せずに保持するだけの値

    等価判定と文字列化ができれば十分。テストが見るのは構造（キーの有無や
    ネストの位置）で、intrinsic の評価結果ではない。
    """

    __slots__ = ("tag", "value")

    def __init__(self, tag: str, value: Any) -> None:
        self.tag = tag
        self.value = value

    def __repr__(self) -> str:  # pragma: no cover - デバッグ表示のみ
        return f"{self.tag} {self.value!r}"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, _CfnTag):
            return self.tag == other.tag and self.value == other.value
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.tag, repr(self.value)))


class _CfnLoader(yaml.SafeLoader):
    """CloudFormation の短縮タグを受け付ける SafeLoader

    SafeLoader を継承しているので、任意 Python オブジェクトの構築は起きない。
    """


def _construct_cfn_tag(loader: yaml.SafeLoader, tag_suffix: str, node: yaml.Node) -> _CfnTag:
    if isinstance(node, yaml.ScalarNode):
        value: Any = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node, deep=True)
    else:
        value = loader.construct_mapping(node, deep=True)
    return _CfnTag(f"!{tag_suffix}", value)


_CfnLoader.add_multi_constructor("!", _construct_cfn_tag)


# SAM / CloudFormation で Lambda 関数を表すリソースタイプ
_FUNCTION_TYPES = ("AWS::Serverless::Function", "AWS::Lambda::Function")


@dataclass(frozen=True)
class SamTemplate:
    """解析済みテンプレート

    Attributes:
        path: 読み込んだテンプレートのパス
        raw: YAML をそのまま辞書にしたもの
    """

    path: Path
    raw: dict[str, Any]

    @property
    def parameters(self) -> dict[str, Any]:
        return self.raw.get("Parameters") or {}

    @property
    def resources(self) -> dict[str, Any]:
        return self.raw.get("Resources") or {}

    @property
    def conditions(self) -> dict[str, Any]:
        return self.raw.get("Conditions") or {}

    @property
    def outputs(self) -> dict[str, Any]:
        return self.raw.get("Outputs") or {}

    def functions(self) -> dict[str, dict[str, Any]]:
        """Lambda 関数リソースを論理 ID -> リソース定義 で返す"""
        return {
            logical_id: body
            for logical_id, body in self.resources.items()
            if isinstance(body, dict) and body.get("Type") in _FUNCTION_TYPES
        }

    def function_env(self, logical_id: str) -> dict[str, Any]:
        """指定した関数の Environment.Variables を返す"""
        body = self.functions().get(logical_id, {})
        props = body.get("Properties") or {}
        env = props.get("Environment") or {}
        return env.get("Variables") or {}

    def all_function_env_names(self) -> set[str]:
        """テンプレート内の全 Lambda 関数の環境変数名の集合

        「どの関数か」を問わず「環境変数として実際に渡されているか」を見たい
        ケース用。特定の関数を問うなら `function_env()` を使う。
        """
        names: set[str] = set()
        for logical_id in self.functions():
            names.update(self.function_env(logical_id).keys())
        return names

    def resources_of_type(self, resource_type: str) -> dict[str, dict[str, Any]]:
        return {
            logical_id: body
            for logical_id, body in self.resources.items()
            if isinstance(body, dict) and body.get("Type") == resource_type
        }

    def undefined_condition_refs(self) -> set[str]:
        """`Conditions` から参照されているが `Parameters` に無い名前

        パラメータを削除したのに Conditions の `!Ref` が残っている、という
        壊れ方を検出する。部分文字列検査ではこれが通ってしまう。
        """
        referenced = _collect_refs(self.conditions)
        known = set(self.parameters) | set(self.resources)
        # 疑似パラメータ（AWS::Region など）は定義対象外
        return {name for name in referenced - known if not name.startswith("AWS::")}


def _collect_refs(node: Any) -> set[str]:
    """入れ子構造の中の `!Ref` / `Ref:` の参照先名を集める"""
    found: set[str] = set()
    if isinstance(node, _CfnTag):
        if node.tag == "!Ref" and isinstance(node.value, str):
            found.add(node.value)
        else:
            found |= _collect_refs(node.value)
    elif isinstance(node, dict):
        for key, value in node.items():
            if key == "Ref" and isinstance(value, str):
                found.add(value)
            else:
                found |= _collect_refs(value)
    elif isinstance(node, list):
        for item in node:
            found |= _collect_refs(item)
    return found


def load_sam_template(template_path: str | Path) -> SamTemplate:
    """テンプレートを解析して `SamTemplate` を返す

    Args:
        template_path: 絶対パス、またはリポジトリルートからの相対パス

    Returns:
        SamTemplate: 解析済みテンプレート

    Raises:
        FileNotFoundError: テンプレートが存在しない
        yaml.YAMLError: YAML として壊れている（部分文字列検査では検出できない）
    """
    path = Path(template_path)
    if not path.is_absolute():
        # このファイルは shared/testing/ にあるので、2 つ上がリポジトリルート
        candidate = Path(__file__).resolve().parents[2] / path
        path = candidate if candidate.exists() else path
    if not path.exists():
        raise FileNotFoundError(f"template not found: {path}")

    # `yaml.load(..., Loader=_CfnLoader)` と等価だが、ローダーを直接使う。
    # `yaml.load` は渡した Loader に関係なく「安全でない読み込み」として静的解析に
    # 検出されるため（bandit B506 / ruff S506）、抑制コメントで黙らせるより、
    # 実際に使うローダーが読んで分かる形にする。_CfnLoader は SafeLoader 派生なので
    # 任意 Python オブジェクトの構築は起きない。
    with path.open(encoding="utf-8") as handle:
        loader = _CfnLoader(handle)
        try:
            raw = loader.get_single_data()
        finally:
            loader.dispose()

    if not isinstance(raw, dict):
        raise AssertionError(f"template did not parse to a mapping: {path}")
    return SamTemplate(path=path, raw=raw)
