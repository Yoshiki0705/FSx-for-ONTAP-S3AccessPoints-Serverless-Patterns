"""Tests for the boundary on answering questions about a file's contents.

This endpoint sends file content to a model, so an unchecked key is a read of the whole
file by another route -- the answer carries the contents back.

`shared/tests/test_portal_path_scope.py` covers `scope_for_caller` itself. What is
asserted here is that this handler calls it, before anything reads the object, and in
the right order relative to the other two refusals it makes. Order is a property of the
handler rather than of the shared module, and it is the part that leaks: refusing a key
because the file is CONFIDENTIAL tells the caller the file exists and how it is
labelled, which is more than a caller outside the boundary should learn.

`S3ApHelper` and Bedrock are stubbed. What matters is which access point the helper was
constructed with, and whether it was constructed at all.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

MODULE_PATH = Path(__file__).resolve().parent.parent / "index.py"

DEFAULT_ALIAS = "default-ap-s3alias"
TEAM_A_ALIAS = "team-a-ap-s3alias"
GROUP_AP_MAPPING = {"team-a": TEAM_A_ALIAS}
GROUP_PATH_PREFIXES = {"team-a": ["team-a/"], "team-b": ["team-b/"]}

INSIDE = "team-a/thermal-spec.pdf"
OUTSIDE = "team-b/thermal-spec.pdf"


def load_module(env: dict[str, str] | None = None) -> Any:
    """Import index.py fresh, since its configuration is read at import time.

    Args:
        env: Environment overrides applied on top of the defaults below.

    Returns:
        The imported module, with `S3ApHelper` and Bedrock already stubbed.
    """
    base = {
        "S3_AP_ALIAS": DEFAULT_ALIAS,
        "GROUP_AP_MAPPING": json.dumps(GROUP_AP_MAPPING),
        "GROUP_PATH_PREFIXES": json.dumps(GROUP_PATH_PREFIXES),
        "CLASSIFICATION_TABLE_NAME": "",
        "EXTERNAL_AI_ENABLED": "true",
        "AWS_REGION": "ap-northeast-1",
    }
    base.update(env or {})
    with patch.dict(os.environ, base, clear=False):
        spec = importlib.util.spec_from_file_location("ask_about_file_under_test", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules["ask_about_file_under_test"] = module
        spec.loader.exec_module(module)

    module.S3ApHelper = MagicMock()
    module.S3ApHelper.return_value.head_object.return_value = {"ContentLength": 12}
    module.S3ApHelper.return_value.get_object_bytes.return_value = b"file content"
    module.bedrock = MagicMock()
    module.bedrock.converse.return_value = {"output": {"message": {"content": [{"text": "the answer"}]}}}
    return module


def call(module: Any, key: str, groups: list[str] | None = None, question: str = "what is this?") -> dict:
    """Invoke the handler as the resolver would, with an attributed caller.

    Args:
        module: The freshly imported handler module.
        key: The object key being asked about.
        groups: The caller's Cognito groups.
        question: The question to ask.

    Returns:
        The handler's response.
    """
    return module.handler({"key": key, "question": question, "groups": groups or []}, None)


def read_alias(module: Any) -> str:
    """The access point the object was read through.

    Args:
        module: The freshly imported handler module.

    Returns:
        The alias `S3ApHelper` was constructed with.
    """
    return module.S3ApHelper.call_args.args[0]


def nothing_was_read(module: Any) -> bool:
    """Whether the handler refused before the object could be opened.

    Args:
        module: The freshly imported handler module.

    Returns:
        True when `S3ApHelper` was never constructed.
    """
    return not module.S3ApHelper.called


class TestTheKeyBoundary:
    def test_a_key_outside_the_boundary_is_refused(self) -> None:
        module = load_module()
        result = call(module, OUTSIDE, groups=["team-a"])
        assert result["answer"] == ""
        assert "outside the prefixes" in result["error"]

    def test_nothing_is_read_when_the_key_is_refused(self) -> None:
        # The refusal has to happen before the read, not alongside it. A handler that
        # fetched first and refused after would already have the contents in memory and
        # a GetObject in the access log.
        module = load_module()
        call(module, OUTSIDE, groups=["team-a"])
        assert nothing_was_read(module)

    def test_no_model_is_called_when_the_key_is_refused(self) -> None:
        module = load_module()
        call(module, OUTSIDE, groups=["team-a"])
        assert not module.bedrock.converse.called

    def test_a_key_inside_the_boundary_is_answered(self) -> None:
        module = load_module()
        result = call(module, INSIDE, groups=["team-a"])
        assert result["error"] is None
        assert result["answer"] == "the answer"

    def test_a_traversal_segment_is_refused(self) -> None:
        module = load_module()
        result = call(module, "team-a/../team-b/secret.pdf", groups=["team-a"])
        assert "'..' segment" in result["error"]
        assert nothing_was_read(module)

    def test_an_unconfined_caller_may_name_anything(self) -> None:
        module = load_module(env={"GROUP_PATH_PREFIXES": "{}"})
        result = call(module, OUTSIDE, groups=["team-a"])
        assert result["error"] is None


class TestAccessPointRouting:
    def test_a_mapped_group_reads_through_its_own_access_point(self) -> None:
        # The prefixes decide which key may be named; the access point decides which
        # ONTAP identity opens it. Checking the key while reading as the default
        # identity reads the right key on the wrong volume.
        module = load_module()
        call(module, INSIDE, groups=["team-a"])
        assert read_alias(module) == TEAM_A_ALIAS

    def test_an_unmapped_caller_reads_through_the_default(self) -> None:
        module = load_module()
        call(module, "anything/file.pdf", groups=["team-c"])
        assert read_alias(module) == DEFAULT_ALIAS

    def test_an_unconfigured_access_point_is_reported_rather_than_used(self) -> None:
        module = load_module(env={"S3_AP_ALIAS": "", "GROUP_AP_MAPPING": "{}"})
        result = call(module, "any/file.pdf", groups=["team-c"])
        assert result["error"] == "S3_AP_ALIAS is not configured"
        assert nothing_was_read(module)


class TestRefusalOrder:
    def test_the_boundary_runs_before_the_classification_check(self) -> None:
        # Refusing on classification would confirm the file exists and disclose its
        # label. The boundary's refusal names only the field.
        module = load_module(env={"CLASSIFICATION_TABLE_NAME": "classifications"})
        with patch.object(module, "check_classification") as classification:
            result = call(module, OUTSIDE, groups=["team-a"])
        assert not classification.called
        assert "outside the prefixes" in result["error"]

    def test_a_confidential_file_inside_the_boundary_is_still_blocked(self) -> None:
        # The two checks answer different questions, so passing the boundary is not
        # permission to send the contents to a model.
        module = load_module(env={"CLASSIFICATION_TABLE_NAME": "classifications"})
        with patch.object(module, "check_classification", return_value=(False, "CONFIDENTIAL")):
            result = call(module, INSIDE, groups=["team-a"])
        assert result["blocked"] is True
        assert result["classification"] == "CONFIDENTIAL"
        assert not module.bedrock.converse.called

    def test_a_missing_question_is_refused_before_the_key_is_considered(self) -> None:
        # The answer does not depend on the key, so this refusal reveals nothing about
        # it -- and it must not depend on the key being valid either.
        module = load_module()
        result = call(module, OUTSIDE, groups=["team-a"], question="")
        assert "Missing required parameters" in result["error"]

    def test_an_external_caller_is_refused_before_the_key_is_considered(self) -> None:
        # Whether this caller may use an AI endpoint at all does not depend on which
        # key was asked for, so answering in that order keeps the denial from
        # confirming the key exists.
        module = load_module(env={"EXTERNAL_AI_ENABLED": ""})
        result = call(module, INSIDE, groups=["team-a", "external"])
        assert result["answer"] == ""
        assert result["error"]
        assert nothing_was_read(module)


class TestTheRegulatedFolderGuard:
    """The folder convention, enforced here and not only in the browser.

    `shared/tests/test_portal_regulated_path.py` covers the predicate. What is asserted
    here is that this handler consults it, that nothing is read when it refuses, and where
    it sits relative to the other two refusals -- which is the part a caller can observe.
    """

    def test_a_regulated_key_is_refused(self) -> None:
        module = load_module()
        result = call(module, "phi/patient-1.txt")
        assert result["answer"] == ""
        assert result["blocked"] is True
        assert "regulated folder" in result["error"]

    def test_nothing_is_read_when_the_key_is_regulated(self) -> None:
        # The contents must not reach the process, let alone the model. A handler that
        # fetched first would have the file in memory and a GetObject in the access log.
        module = load_module()
        call(module, "phi/patient-1.txt")
        assert nothing_was_read(module)

    def test_the_model_is_not_called_for_a_regulated_key(self) -> None:
        module = load_module()
        call(module, "dicom/study/image.dcm")
        assert not module.bedrock.converse.called

    def test_refused_even_with_no_classification_table(self) -> None:
        # The default deployment. `CLASSIFICATION_TABLE_NAME` is empty, so the
        # classification check allows everything; the folder convention is the only guard
        # left, which is why it cannot be the one that is configurable.
        module = load_module({"CLASSIFICATION_TABLE_NAME": ""})
        result = call(module, "pii/export.csv")
        assert result["blocked"] is True

    def test_a_key_outside_the_boundary_is_refused_on_scope_first(self) -> None:
        # Both refusals apply to this key. Scope has to win, or the message would tell a
        # caller outside the boundary which folders are regulated in a prefix they cannot
        # reach.
        module = load_module()
        result = call(module, "team-b/phi/patient-1.txt", groups=["team-a"])
        assert "outside the prefixes" in result["error"]
        assert "regulated folder" not in result["error"]

    def test_a_permitted_key_still_answers(self) -> None:
        module = load_module()
        result = call(module, INSIDE, groups=["team-a"])
        assert result["answer"] == "the answer"
        assert read_alias(module) == TEAM_A_ALIAS
