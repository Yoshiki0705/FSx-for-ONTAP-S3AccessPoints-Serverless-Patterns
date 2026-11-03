"""Tests for the SAM template helper `shared.testing.load_sam_template`.

`function_env` has to return what a function really receives. SAM merges
`Globals.Function.Environment.Variables` into every `AWS::Serverless::Function`; a helper that
reads only the function's own block reports a variable as "not passed" when the template passes it
through Globals, which is how `test_template_env_contract` failed on a correct template.
"""

from __future__ import annotations

from pathlib import Path

from shared.testing import SamTemplate, load_sam_template

TEMPLATE = """\
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Globals:
  Function:
    Environment:
      Variables:
        FROM_GLOBALS: !Ref SomeParameter
        OVERRIDDEN: global-value
Resources:
  PlainFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: functions/plain/
  OwnFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: functions/own/
      Environment:
        Variables:
          OWN_ONLY: !Sub "${AWS::StackName}-x"
          OVERRIDDEN: function-value
  NativeFunction:
    Type: AWS::Lambda::Function
    Properties:
      Code: {ZipFile: "x"}
      Environment:
        Variables:
          NATIVE_ONLY: "1"
"""


def load(tmp_path: Path, text: str = TEMPLATE) -> SamTemplate:
    """Write a template to a temporary file and parse it.

    Args:
        tmp_path: pytest's temporary directory.
        text: Template text. Defaults to `TEMPLATE`.

    Returns:
        The parsed template.
    """
    path = tmp_path / "template.yaml"
    path.write_text(text, encoding="utf-8")
    return load_sam_template(path)


def test_a_function_without_its_own_block_receives_the_globals(tmp_path: Path) -> None:
    assert set(load(tmp_path).function_env("PlainFunction")) == {"FROM_GLOBALS", "OVERRIDDEN"}


def test_own_variables_are_merged_with_the_globals_and_win_on_the_same_key(tmp_path: Path) -> None:
    env = load(tmp_path).function_env("OwnFunction")
    assert set(env) == {"FROM_GLOBALS", "OVERRIDDEN", "OWN_ONLY"}
    assert env["OVERRIDDEN"] == "function-value"


def test_globals_do_not_apply_to_a_native_lambda_function(tmp_path: Path) -> None:
    assert set(load(tmp_path).function_env("NativeFunction")) == {"NATIVE_ONLY"}


def test_a_template_without_globals_returns_only_the_function_block(tmp_path: Path) -> None:
    text = TEMPLATE.split("Globals:")[0] + "Resources:" + TEMPLATE.split("Resources:", 1)[1]
    tpl = load(tmp_path, text)
    assert tpl.function_env("PlainFunction") == {}
    assert set(tpl.function_env("OwnFunction")) == {"OWN_ONLY", "OVERRIDDEN"}


def test_an_unknown_function_has_no_environment(tmp_path: Path) -> None:
    assert load(tmp_path).function_env("Missing") == {}


def test_all_function_env_names_include_what_comes_from_globals(tmp_path: Path) -> None:
    assert load(tmp_path).all_function_env_names() == {"FROM_GLOBALS", "OVERRIDDEN", "OWN_ONLY", "NATIVE_ONLY"}
