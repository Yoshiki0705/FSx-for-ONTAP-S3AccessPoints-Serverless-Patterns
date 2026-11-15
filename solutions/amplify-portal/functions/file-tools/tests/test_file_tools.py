"""Tests for the portal's GenU-style tools (functions/file-tools/index.py).

What matters most is what reaches the model and where writes land:
- a file outside the caller's boundary is refused before anything reads it;
- the read mutation cannot write into a folder (only the write mutation's resolver sets
  `writeOperation`);
- web extraction refuses addresses that are not public, on every redirect hop, and
  connects to the address it checked;
- use cases are keyed by the caller.

`S3ApHelper`, Bedrock, DNS and the HTTP request are stubbed.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from shared.exceptions import S3ApHelperError

MODULE_PATH = Path(__file__).resolve().parent.parent / "index.py"
DEFAULT_ALIAS = "default-ap-s3alias"
GROUP_PATH_PREFIXES = {"team-a": ["team-a/"], "team-b": ["team-b/"]}


def ip(*parts: int) -> str:
    return ".".join(str(p) for p in parts)


def load(env: dict[str, str] | None = None) -> Any:
    base = {
        "S3_AP_ALIAS": DEFAULT_ALIAS,
        "GROUP_AP_MAPPING": "{}",
        "GROUP_PATH_PREFIXES": json.dumps(GROUP_PATH_PREFIXES),
        "EXTERNAL_AI_ENABLED": "false",
        "USE_CASES_TABLE_NAME": "use-cases",
        "AWS_REGION": "ap-northeast-1",
        "IMAGE_GENERATION_ENABLED": "true",
        "IMAGE_GENERATION_REGION": "us-west-2",
    }
    base.update(env or {})
    with patch.dict(os.environ, base, clear=False):
        spec = importlib.util.spec_from_file_location("file_tools_under_test", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules["file_tools_under_test"] = module
        spec.loader.exec_module(module)
    module.S3ApHelper = MagicMock()
    module.S3ApHelper.return_value.head_object.return_value = {"ContentLength": 20}
    module.S3ApHelper.return_value.get_object_bytes.return_value = "社内規程の本文".encode()
    module.bedrock = MagicMock()
    module.bedrock.converse.return_value = {"output": {"message": {"content": [{"text": "translated"}]}}}
    return module


def call(module: Any, **event: Any) -> dict:
    event.setdefault("userId", "alice")
    event.setdefault("groups", ["team-a"])
    return module.handler(event, None)


def model_input(module: Any) -> str:
    kwargs = module.bedrock.converse.call_args.kwargs
    return kwargs["system"][0]["text"] + kwargs["messages"][0]["content"][0]["text"]


class TestFileBoundary:
    def test_a_file_inside_the_boundary_reaches_the_model(self) -> None:
        m = load()
        out = call(m, action="translate", key="team-a/policy.md", target="en")
        assert out["success"] is True
        assert "社内規程の本文" in model_input(m)

    def test_a_file_outside_the_boundary_is_refused_before_it_is_read(self) -> None:
        m = load()
        out = call(m, action="translate", key="team-b/salary.md", target="en")
        assert out["success"] is False
        assert not m.S3ApHelper.called
        assert not m.bedrock.converse.called

    def test_an_external_caller_is_refused_when_ai_is_off_for_them(self) -> None:
        m = load()
        out = call(m, action="proofread", key="team-a/policy.md", groups=["team-a", "external"])
        assert out["success"] is False
        assert not m.S3ApHelper.called

    def test_a_regulated_path_is_refused(self) -> None:
        m = load({"GROUP_PATH_PREFIXES": "{}"})
        out = call(m, action="diagram", key="phi/records.txt")
        assert out["success"] is False
        assert not m.bedrock.converse.called


class TestWrites:
    def test_the_read_mutation_cannot_save_an_image(self) -> None:
        m = load()
        m.image_client = MagicMock()
        out = call(m, action="generateImage", folder="team-a/images", prompt="a rack")
        assert out["success"] is False
        assert not m.image_client.called
        assert not m.S3ApHelper.return_value.put_object.called

    def test_the_write_mutation_saves_without_overwriting(self) -> None:
        m = load()
        png = b"\x89PNG fake"
        client = MagicMock()
        client.invoke_model.return_value = {
            "body": MagicMock(
                read=lambda: json.dumps(
                    {"images": [__import__("base64").b64encode(png).decode()], "finish_reasons": [None]}
                ).encode()
            )
        }
        m.image_client = lambda: client
        helper = m.S3ApHelper.return_value
        helper.head_object.side_effect = [{"ContentLength": 1}, S3ApHelperError("missing", error_code="404")]
        out = call(
            m, action="generateImage", folder="team-a/images", fileName="rack", prompt="a rack", writeOperation=True
        )
        assert out["success"] is True
        assert out["key"] == "team-a/images/rack-1.png"
        helper.put_object.assert_called_once()
        assert helper.put_object.call_args.args[0] == "team-a/images/rack-1.png"
        body = json.loads(client.invoke_model.call_args.kwargs["body"])
        assert body == {"prompt": "a rack", "aspect_ratio": "1:1", "output_format": "png"}

    def test_a_folder_outside_the_boundary_is_refused_before_the_model_is_called(self) -> None:
        m = load()
        m.image_client = MagicMock()
        out = call(m, action="generateImage", folder="team-b", prompt="x", writeOperation=True)
        assert out["success"] is False
        assert not m.image_client.called

    def test_image_generation_is_refused_while_disabled(self) -> None:
        m = load({"IMAGE_GENERATION_ENABLED": "false"})
        m.S3ApHelper.return_value.head_object.side_effect = S3ApHelperError("missing", error_code="404")
        out = call(m, action="generateImage", folder="team-a", prompt="x", writeOperation=True)
        assert out == {"success": False, "error": "image generation is not enabled"}

    def test_access_denied_on_the_name_check_is_an_error_not_a_free_name(self) -> None:
        m = load()
        m.S3ApHelper.return_value.head_object.side_effect = S3ApHelperError("denied", error_code="AccessDenied")
        out = call(m, action="saveResult", folder="team-a", fileName="r", content="x", writeOperation=True)
        assert out["success"] is False
        assert not m.S3ApHelper.return_value.put_object.called


class TestWebExtraction:
    @pytest.mark.parametrize(
        "url",
        [
            "http://" + ip(169, 254, 169, 254) + "/latest/meta-data/",
            "http://localhost/",
            "file:///etc/passwd",
            "http://user:pw@example.com/",
            "http://example.com:8080/",
        ],
    )
    def test_urls_that_must_not_be_fetched(self, url: str) -> None:
        m = load()
        m.resolve = lambda host: m.resolve_public(host)
        out = call(m, action="webExtract", url=url)
        assert out["success"] is False
        assert not m.bedrock.converse.called

    def test_address_classification(self) -> None:
        m = load()
        assert not m.is_public_address(ip(10, 0, 0, 1))
        assert not m.is_public_address(ip(172, 16, 5, 4))
        assert not m.is_public_address(ip(192, 168, 1, 1))
        assert not m.is_public_address(ip(100, 64, 0, 1))
        assert not m.is_public_address(ip(169, 254, 169, 254))
        assert not m.is_public_address("::ffff:" + ip(127, 0, 0, 1))
        assert not m.is_public_address("fd00:ec2::254")
        assert m.is_public_address(ip(93, 184, 216, 34))

    def test_a_host_with_any_private_answer_is_refused(self) -> None:
        m = load()
        with patch.object(
            m.socket,
            "getaddrinfo",
            return_value=[(0, 0, 0, "", (ip(93, 184, 216, 34), 0)), (0, 0, 0, "", (ip(10, 1, 2, 3), 0))],
        ):
            with pytest.raises(m.ToolError):
                m.resolve_public("example.com")

    def test_every_redirect_hop_is_checked_and_the_checked_address_is_used(self) -> None:
        m = load()
        m.resolve = lambda host: (
            ip(93, 184, 216, 34) if host == "example.com" else (_ for _ in ()).throw(m.ToolError("not allowed"))
        )
        connected: list[str] = []

        def request(parts: Any, address: str) -> tuple[int, dict, bytes]:
            connected.append(address)
            return 302, {"location": "http://metadata.example/latest"}, b""

        m.request_page = request
        out = call(m, action="webExtract", url="https://example.com/")
        assert out["success"] is False
        assert connected == [ip(93, 184, 216, 34)]
        assert not m.bedrock.converse.called

    def test_the_visible_text_of_a_page_reaches_the_model(self) -> None:
        m = load()
        m.resolve = lambda host: ip(93, 184, 216, 34)
        m.request_page = lambda parts, address: (
            200,
            {"content-type": "text/html; charset=utf-8"},
            b"<title>T</title><script>evil()</script><h1>Hello</h1><p>World &amp; more</p>",
        )
        out = call(m, action="webExtract", url="https://example.com/", task="summary")
        assert out["success"] is True and out["title"] == "T"
        sent = model_input(m)
        assert "Hello" in sent and "World & more" in sent and "evil" not in sent


class TestDiagramAndProofread:
    def test_click_handlers_and_init_directives_are_dropped(self) -> None:
        m = load()
        code = m.extract_mermaid(
            '```mermaid\n%%{init: {"securityLevel":"loose"}}%%\nflowchart TD\nA-->B\nclick A "javascript:alert(1)"\n```'
        )
        assert code == "flowchart TD\nA-->B"

    def test_output_that_is_not_mermaid_is_rejected(self) -> None:
        m = load()
        with pytest.raises(ValueError):
            m.extract_mermaid("<script>alert(1)</script>")

    def test_proofreading_json_in_a_fence(self) -> None:
        m = load()
        out = m.parse_proofread(
            '```json\n{"corrected":"Fixed","issues":[{"original":"teh","suggestion":"the","reason":"typo"}]}\n```'
        )
        assert out == {"corrected": "Fixed", "issues": [{"original": "teh", "suggestion": "the", "reason": "typo"}]}


class TestUseCases:
    def test_use_cases_are_keyed_by_the_caller(self) -> None:
        m = load()
        table = MagicMock()
        table.query.return_value = {"Items": []}
        m.use_cases_table = lambda: table
        out = call(
            m, action="saveUseCase", title="Brief", template="Brief: {{input}}", userId="alice", writeOperation=True
        )
        assert out["success"] is True
        assert table.put_item.call_args.kwargs["Item"]["userId"] == "alice"

    @pytest.mark.parametrize("action", ["saveUseCase", "deleteUseCase", "generateImage", "saveResult"])
    def test_writes_are_refused_through_the_query(self, action: str) -> None:
        m = load()
        table = MagicMock()
        m.use_cases_table = lambda: table
        out = call(
            m, action=action, title="t", template="x", useCaseId="uc-1", folder="team-a", content="c", prompt="p"
        )
        assert out["success"] is False and "write operation" in out["error"]
        assert not table.put_item.called and not table.delete_item.called
        assert not m.S3ApHelper.return_value.put_object.called

    def test_running_another_users_use_case_finds_nothing(self) -> None:
        m = load()
        table = MagicMock()
        table.get_item.return_value = {}
        m.use_cases_table = lambda: table
        out = call(m, action="runUseCase", useCaseId="uc-of-bob", text="x", userId="alice")
        assert out == {"success": False, "error": "use case not found"}
        assert table.get_item.call_args.kwargs["Key"] == {"userId": "alice", "useCaseId": "uc-of-bob"}

    def test_a_template_runs_with_the_input_as_data(self) -> None:
        m = load()
        table = MagicMock()
        table.get_item.return_value = {"Item": {"template": "Brief: {{input}}"}}
        m.use_cases_table = lambda: table
        out = call(m, action="runUseCase", useCaseId="uc-1", text="the plan")
        assert out["success"] is True
        assert "Brief: <input>\nthe plan\n</input>" in model_input(m)
