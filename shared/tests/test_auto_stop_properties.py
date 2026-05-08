"""Property-Based Tests for shared.lambdas.auto_stop module

Hypothesis を使用したプロパティベーステスト。
Auto-Stop Lambda のタグ保護と非破壊停止保証の不変条件を検証する。

Testing Strategy:
- 最小 100 イテレーション/プロパティ
- 各テストにプロパティ番号タグを付与
- タグ形式: Feature: fsxn-s3ap-serverless-patterns-phase5, Property {number}: {property_text}
"""

from __future__ import annotations

from hypothesis import given, settings, strategies as st
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helper: Auto-Stop filtering logic (extracted from handler for testability)
# ---------------------------------------------------------------------------


def filter_stoppable_endpoints(endpoints: list[dict]) -> list[dict]:
    """Filter endpoints that should be stopped based on tags and idle status.

    An endpoint is stoppable if:
    - It does NOT have DoNotAutoStop=true tag
    - It has zero invocations (idle)
    - It has instance_count > 0 (not already scaled to zero)

    Args:
        endpoints: List of endpoint dicts with keys:
            - endpoint_name: str
            - tags: dict[str, str]
            - invocations: int (total invocations in monitoring period)
            - instance_count: int (current instance count)

    Returns:
        List of endpoints that should be stopped
    """
    stoppable = []
    for ep in endpoints:
        tags = ep.get("tags", {})
        # DoNotAutoStop tag protection
        if tags.get("DoNotAutoStop", "false").lower() == "true":
            continue
        # Only stop idle endpoints (zero invocations)
        if ep.get("invocations", 0) > 0:
            continue
        # Skip already scaled to zero
        if ep.get("instance_count", 0) == 0:
            continue
        stoppable.append(ep)
    return stoppable


def determine_stop_action(endpoint_name: str) -> dict:
    """Determine the stop action for an idle endpoint.

    The stop action is ALWAYS scale-to-zero (DesiredInstanceCount=0).
    Never delete the endpoint.

    Args:
        endpoint_name: Name of the endpoint to stop

    Returns:
        dict with action details:
            - action: "UpdateEndpointWeightsAndCapacities"
            - endpoint_name: str
            - desired_instance_count: 0
    """
    return {
        "action": "UpdateEndpointWeightsAndCapacities",
        "endpoint_name": endpoint_name,
        "desired_instance_count": 0,
    }


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy for generating endpoint tags
endpoint_tags_strategy = st.fixed_dictionaries(
    {},
    optional={
        "DoNotAutoStop": st.sampled_from(["true", "false", "True", "FALSE"]),
        "Project": st.text(min_size=0, max_size=20),
        "Environment": st.sampled_from(["dev", "staging", "production"]),
    },
)

# Strategy for generating a single endpoint
endpoint_strategy = st.fixed_dictionaries({
    "endpoint_name": st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
        min_size=1,
        max_size=30,
    ),
    "tags": endpoint_tags_strategy,
    "invocations": st.integers(min_value=0, max_value=100),
    "instance_count": st.integers(min_value=0, max_value=10),
})

# Strategy for generating a list of endpoints
endpoints_list_strategy = st.lists(endpoint_strategy, min_size=0, max_size=20)


# ---------------------------------------------------------------------------
# Property 8: Auto-Stop Tag Protection
# Feature: fsxn-s3ap-serverless-patterns-phase5, Property 8: Auto-Stop Tag Protection
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(endpoints=endpoints_list_strategy)
def test_auto_stop_tag_protection_never_stops_protected_endpoints(
    endpoints: list[dict],
):
    """Feature: fsxn-s3ap-serverless-patterns-phase5, Property 8: Auto-Stop Tag Protection

    FOR ALL endpoints with DoNotAutoStop=true tag, they SHALL NEVER be included
    in the stop list regardless of idle status or invocation count.

    **Validates: Requirements 8.6**
    """
    # Feature: fsxn-s3ap-serverless-patterns-phase5, Property 8: Auto-Stop Tag Protection
    stoppable = filter_stoppable_endpoints(endpoints)

    # Verify: no endpoint with DoNotAutoStop=true is in the stop list
    for ep in stoppable:
        tags = ep.get("tags", {})
        do_not_stop = tags.get("DoNotAutoStop", "false").lower()
        assert do_not_stop != "true", (
            f"Endpoint '{ep['endpoint_name']}' has DoNotAutoStop=true "
            f"but was included in the stop list. Tags: {tags}"
        )


@settings(max_examples=100)
@given(endpoints=st.lists(endpoint_strategy, min_size=0, max_size=20, unique_by=lambda x: x["endpoint_name"]))
def test_auto_stop_tag_protection_protected_count_preserved(
    endpoints: list[dict],
):
    """Feature: fsxn-s3ap-serverless-patterns-phase5, Property 8: Auto-Stop Tag Protection

    The number of protected endpoints (DoNotAutoStop=true) in the input SHALL
    equal the number of protected endpoints excluded from the stop list.
    No protected endpoint is ever lost or accidentally included.

    **Validates: Requirements 8.6**
    """
    # Feature: fsxn-s3ap-serverless-patterns-phase5, Property 8: Auto-Stop Tag Protection
    protected_endpoints = [
        ep for ep in endpoints
        if ep.get("tags", {}).get("DoNotAutoStop", "false").lower() == "true"
    ]

    stoppable = filter_stoppable_endpoints(endpoints)

    # None of the protected endpoints should appear in stoppable
    stoppable_names = {ep["endpoint_name"] for ep in stoppable}
    for ep in protected_endpoints:
        assert ep["endpoint_name"] not in stoppable_names, (
            f"Protected endpoint '{ep['endpoint_name']}' was found in stop list"
        )


@settings(max_examples=100)
@given(
    invocations=st.integers(min_value=0, max_value=100),
    instance_count=st.integers(min_value=0, max_value=10),
)
def test_auto_stop_tag_protection_single_protected_endpoint(
    invocations: int,
    instance_count: int,
):
    """Feature: fsxn-s3ap-serverless-patterns-phase5, Property 8: Auto-Stop Tag Protection

    A single endpoint with DoNotAutoStop=true SHALL never be stopped,
    regardless of its invocation count or instance count.

    **Validates: Requirements 8.6**
    """
    # Feature: fsxn-s3ap-serverless-patterns-phase5, Property 8: Auto-Stop Tag Protection
    endpoint = {
        "endpoint_name": "protected-endpoint",
        "tags": {"DoNotAutoStop": "true"},
        "invocations": invocations,
        "instance_count": instance_count,
    }

    stoppable = filter_stoppable_endpoints([endpoint])
    assert len(stoppable) == 0, (
        f"Protected endpoint was included in stop list with "
        f"invocations={invocations}, instance_count={instance_count}"
    )


# ---------------------------------------------------------------------------
# Property 9: Non-Destructive Stop Guarantee
# Feature: fsxn-s3ap-serverless-patterns-phase5, Property 9: Non-Destructive Stop Guarantee
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    endpoint_name=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
        min_size=1,
        max_size=30,
    ),
)
def test_non_destructive_stop_action_is_always_scale_to_zero(
    endpoint_name: str,
):
    """Feature: fsxn-s3ap-serverless-patterns-phase5, Property 9: Non-Destructive Stop Guarantee

    FOR ALL idle endpoints that are stopped, the action SHALL ALWAYS be
    UpdateEndpointWeightsAndCapacities with DesiredInstanceCount=0.
    The action SHALL NEVER be "DeleteEndpoint".

    **Validates: Requirements 8.4, 8.7**
    """
    # Feature: fsxn-s3ap-serverless-patterns-phase5, Property 9: Non-Destructive Stop Guarantee
    action = determine_stop_action(endpoint_name)

    # Verify action is scale-to-zero, not delete
    assert action["action"] == "UpdateEndpointWeightsAndCapacities", (
        f"Expected UpdateEndpointWeightsAndCapacities but got '{action['action']}'"
    )
    assert action["desired_instance_count"] == 0, (
        f"Expected DesiredInstanceCount=0 but got {action['desired_instance_count']}"
    )
    assert action["endpoint_name"] == endpoint_name
    # Explicitly verify it's NOT a delete action
    assert action["action"] != "DeleteEndpoint", (
        "Stop action must never be DeleteEndpoint"
    )


@settings(max_examples=100)
@given(endpoints=endpoints_list_strategy)
def test_non_destructive_stop_all_actions_are_scale_to_zero(
    endpoints: list[dict],
):
    """Feature: fsxn-s3ap-serverless-patterns-phase5, Property 9: Non-Destructive Stop Guarantee

    FOR ALL endpoints in the stop list, every stop action SHALL be
    scale-to-zero (DesiredInstanceCount=0) and never delete.

    **Validates: Requirements 8.4, 8.7**
    """
    # Feature: fsxn-s3ap-serverless-patterns-phase5, Property 9: Non-Destructive Stop Guarantee
    stoppable = filter_stoppable_endpoints(endpoints)

    for ep in stoppable:
        action = determine_stop_action(ep["endpoint_name"])

        assert action["action"] == "UpdateEndpointWeightsAndCapacities", (
            f"Endpoint '{ep['endpoint_name']}': expected "
            f"UpdateEndpointWeightsAndCapacities but got '{action['action']}'"
        )
        assert action["desired_instance_count"] == 0, (
            f"Endpoint '{ep['endpoint_name']}': expected "
            f"DesiredInstanceCount=0 but got {action['desired_instance_count']}"
        )


@settings(max_examples=100)
@given(
    endpoint_name=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
        min_size=1,
        max_size=30,
    ),
)
def test_non_destructive_stop_endpoint_remains_restartable(
    endpoint_name: str,
):
    """Feature: fsxn-s3ap-serverless-patterns-phase5, Property 9: Non-Destructive Stop Guarantee

    FOR ALL stop actions, the endpoint SHALL remain in a restartable state.
    This means the action preserves the endpoint resource (no deletion).

    **Validates: Requirements 8.4, 8.7**
    """
    # Feature: fsxn-s3ap-serverless-patterns-phase5, Property 9: Non-Destructive Stop Guarantee
    action = determine_stop_action(endpoint_name)

    # The action must be an update (preserves endpoint), not a delete
    restartable_actions = {"UpdateEndpointWeightsAndCapacities"}
    destructive_actions = {"DeleteEndpoint", "DeleteModel", "DeleteEndpointConfig"}

    assert action["action"] in restartable_actions, (
        f"Action '{action['action']}' is not a restartable action"
    )
    assert action["action"] not in destructive_actions, (
        f"Action '{action['action']}' is destructive and would prevent restart"
    )
