"""Tests for running a stored agent or team.

The Agent Directory and the team wizard could save a definition and nothing could
run it: `chat` took a message, a history and one of three built-in modes, with no
parameter for a stored agent. The button that would have run one passed an empty
handler, so the whole feature was a registry — you could describe an agent and
never use it.

Running one executes instructions somebody else wrote, so the cases pinned here
are the ones where being wrong matters:

  * a definition that is not yours and not shared must not run
  * a tool name a definition asks for that this deployment does not implement must
    not be handed to the model
  * the HITL approval tool must be present whether or not the definition selected it
  * naming both an agent and a team must be refused rather than resolved by
    precedence, which would run instructions the caller did not ask for
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import agent_chat_handler as handler
import pytest


def _table_returning(item):
    """A DynamoDB resource whose `get_item` yields `item` (or nothing)."""
    table = MagicMock()
    table.get_item.return_value = {"Item": item} if item is not None else {}
    resource = MagicMock()
    resource.Table.return_value = table
    return resource, table


AGENT = {
    "agentId": "agent-1",
    "name": "Contract reader",
    "systemPrompt": "You read contracts and answer questions about them.",
    "tools": ["read_file", "kb_search"],
    "isShared": False,
    "createdBy": "owner@example.com",
}


class TestStoredAgent:
    def test_owner_may_run_their_own_agent(self):
        resource, _ = _table_returning(AGENT)
        with patch.object(handler.boto3, "resource", return_value=resource):
            runtime, error = handler._agent_runtime("owner@example.com", "agent-1")
        assert error is None
        assert runtime["name"] == "Contract reader"
        assert runtime["systemPrompt"] == AGENT["systemPrompt"]

    def test_a_private_agent_of_another_user_is_refused(self):
        resource, _ = _table_returning(AGENT)
        with patch.object(handler.boto3, "resource", return_value=resource):
            runtime, error = handler._agent_runtime("someone@example.com", "agent-1")
        assert runtime is None
        assert "not shared" in error["error"]

    def test_a_shared_agent_runs_for_anyone(self):
        resource, _ = _table_returning({**AGENT, "isShared": True})
        with patch.object(handler.boto3, "resource", return_value=resource):
            runtime, error = handler._agent_runtime("someone@example.com", "agent-1")
        assert error is None
        assert runtime["systemPrompt"] == AGENT["systemPrompt"]

    def test_an_agent_with_no_prompt_is_refused(self):
        """Otherwise it would run as a general assistant wearing the agent's name."""
        resource, _ = _table_returning({**AGENT, "systemPrompt": "  "})
        with patch.object(handler.boto3, "resource", return_value=resource):
            runtime, error = handler._agent_runtime("owner@example.com", "agent-1")
        assert runtime is None
        assert "no system prompt" in error["error"]

    def test_a_missing_agent_names_the_id(self):
        resource, _ = _table_returning(None)
        with patch.object(handler.boto3, "resource", return_value=resource):
            runtime, error = handler._agent_runtime("owner@example.com", "ghost")
        assert runtime is None
        assert "ghost" in error["error"]


class TestToolNarrowing:
    def test_an_unimplemented_tool_is_dropped(self):
        """A definition is written through a form, so it can name anything."""
        assert handler._runnable_tools(["read_file", "delete_everything"]) == [
            "read_file",
            "request_action_approval",
        ]

    def test_the_approval_tool_is_always_present(self):
        assert "request_action_approval" in handler._runnable_tools([])
        assert "request_action_approval" in handler._runnable_tools(["list_files"])

    def test_it_is_not_added_twice(self):
        tools = handler._runnable_tools(["request_action_approval", "list_files"])
        assert tools.count("request_action_approval") == 1

    def test_every_selectable_tool_in_the_creator_form_is_runnable(self):
        """The form's checkboxes and the handler's tool table must agree.

        A tool offered in the UI and missing here would be silently dropped from
        every agent saved with it.
        """
        offered = [
            "list_files",
            "read_file",
            "search_files",
            "get_volume_summary",
            "kb_search",
            "request_action_approval",
        ]
        assert handler._runnable_tools(offered) == offered


class TestTeam:
    def _team(self, members, **overrides):
        return {
            "teamId": "team-1",
            "name": "Review board",
            "description": "Reads and reviews.",
            "agents": json.dumps(members),
            "isShared": False,
            "createdBy": "owner@example.com",
            **overrides,
        }

    def test_a_team_pools_its_members_prompts_and_tools(self):
        team = self._team(
            [
                {"agentId": "agent-1", "name": "Reader", "role": "collaborator"},
                {"agentId": "agent-2", "name": "Reviewer", "role": "reviewer"},
            ]
        )
        second = {**AGENT, "agentId": "agent-2", "name": "Reviewer", "tools": ["list_files"]}

        def table_for(_name):
            table = MagicMock()
            table.get_item.side_effect = lambda Key: {
                "Item": {
                    "team-1": team,
                    "agent-1": AGENT,
                    "agent-2": second,
                }[next(iter(Key.values()))]
            }
            return table

        resource = MagicMock()
        resource.Table.side_effect = table_for
        with patch.object(handler.boto3, "resource", return_value=resource):
            runtime, error = handler._team_runtime("owner@example.com", "team-1")

        assert error is None
        assert "Review board" in runtime["systemPrompt"]
        # Each member's own instructions and role reach the prompt.
        assert AGENT["systemPrompt"] in runtime["systemPrompt"]
        assert "role: reviewer" in runtime["systemPrompt"]
        # Tools are the union, narrowed to what exists.
        assert set(runtime["tools"]) == {"read_file", "kb_search", "list_files", "request_action_approval"}

    def test_a_one_member_team_is_refused(self):
        resource, _ = _table_returning(self._team([{"agentId": "agent-1", "name": "Reader"}]))
        with patch.object(handler.boto3, "resource", return_value=resource):
            runtime, error = handler._team_runtime("owner@example.com", "team-1")
        assert runtime is None
        assert "at least 2" in error["error"]

    def test_an_unreachable_member_is_named_rather_than_failing_the_run(self):
        """A deleted or unshared member should not take the rest of the team down."""
        team = self._team(
            [
                {"agentId": "agent-1", "name": "Reader", "role": "collaborator"},
                {"agentId": "gone", "name": "Ghost", "role": "reviewer"},
                {"agentId": "agent-2", "name": "Reviewer", "role": "reviewer"},
            ]
        )
        second = {**AGENT, "agentId": "agent-2", "tools": ["list_files"]}
        items = {"team-1": team, "agent-1": AGENT, "agent-2": second}

        def table_for(_name):
            table = MagicMock()
            table.get_item.side_effect = lambda Key: (
                {"Item": items[next(iter(Key.values()))]} if next(iter(Key.values())) in items else {}
            )
            return table

        resource = MagicMock()
        resource.Table.side_effect = table_for
        with patch.object(handler.boto3, "resource", return_value=resource):
            runtime, error = handler._team_runtime("owner@example.com", "team-1")

        assert error is None
        assert runtime["unavailable"] and "Ghost" in runtime["unavailable"][0]
        assert "Members unavailable for this run" in runtime["systemPrompt"]

    def test_a_team_whose_every_member_is_unreachable_is_refused(self):
        team = self._team(
            [
                {"agentId": "gone-1", "name": "One"},
                {"agentId": "gone-2", "name": "Two"},
            ]
        )

        def table_for(_name):
            table = MagicMock()
            table.get_item.side_effect = lambda Key: {"Item": team} if next(iter(Key.values())) == "team-1" else {}
            return table

        resource = MagicMock()
        resource.Table.side_effect = table_for
        with patch.object(handler.boto3, "resource", return_value=resource):
            runtime, error = handler._team_runtime("owner@example.com", "team-1")
        assert runtime is None
        assert "No member of this team could be run" in error["error"]


class TestResolveRunTarget:
    def test_neither_id_is_the_built_in_mode_path(self):
        assert handler._resolve_run_target("someone", {"message": "hi"}) == (None, None)

    def test_naming_both_is_refused(self):
        runtime, error = handler._resolve_run_target("someone", {"agentId": "a", "teamId": "t"})
        assert runtime is None
        assert "not both" in error["error"]


class TestChatAction:
    """The `chat` branch has to pass the resolved definition to the loop."""

    def _event(self, params):
        return {"action": "chat", "userId": "owner@example.com", "params": params}

    def test_a_stored_agent_replaces_the_mode_presets(self):
        resource, _ = _table_returning(AGENT)
        with (
            patch.object(handler.boto3, "resource", return_value=resource),
            patch.object(handler, "run_agent_loop", return_value={"answer": "ok", "toolCalls": []}) as loop,
        ):
            result = handler.handler(self._event({"message": "hi", "agentId": "agent-1"}), None)

        assert result["ranAs"] == "Contract reader"
        kwargs = loop.call_args.kwargs
        assert kwargs["system_prompt"] == AGENT["systemPrompt"]
        assert set(kwargs["allowed_tools"]) == {"read_file", "kb_search", "request_action_approval"}

    def test_a_refused_definition_does_not_reach_the_model(self):
        resource, _ = _table_returning(AGENT)
        with (
            patch.object(handler.boto3, "resource", return_value=resource),
            patch.object(handler, "run_agent_loop") as loop,
        ):
            result = handler.handler(
                {"action": "chat", "userId": "other@example.com", "params": {"message": "hi", "agentId": "agent-1"}},
                None,
            )
        assert "not shared" in result["error"]
        loop.assert_not_called()

    def test_without_a_definition_the_loop_keeps_its_presets(self):
        with patch.object(handler, "run_agent_loop", return_value={"answer": "ok", "toolCalls": []}) as loop:
            result = handler.handler(self._event({"message": "hi", "mode": "kb"}), None)
        assert "ranAs" not in result
        kwargs = loop.call_args.kwargs
        assert kwargs["system_prompt"] is None
        assert kwargs["allowed_tools"] is None
        assert kwargs["mode"] == "kb"


@pytest.mark.parametrize("mode", ["multi", "kb", "agent"])
def test_the_built_in_modes_still_have_a_prompt_and_tools(mode):
    """The override is opt-in, so the presets must remain complete."""
    assert handler.SYSTEM_PROMPTS[mode]
    assert handler.TOOLS_BY_MODE[mode]
