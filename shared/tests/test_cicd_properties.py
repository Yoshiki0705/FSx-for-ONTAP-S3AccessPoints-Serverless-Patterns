"""Property-Based Tests for CI/CD Pipeline Logic

Hypothesis を使用したプロパティベーステスト。
CI/CD パイプラインのゲーティングロジックとデプロイステージ順序の不変条件を検証する。

Testing Strategy:
- 最小 100 イテレーション/プロパティ
- 各テストにプロパティ番号タグを付与
- タグ形式: Feature: fsxn-s3ap-serverless-patterns-phase5, Property {number}: {property_text}
"""

from __future__ import annotations

from hypothesis import given, settings, strategies as st


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------


def determine_ci_status(stage_results: list[str]) -> str:
    """Determine the final CI pipeline status from individual stage results.

    Returns "success" only if ALL stages pass, "failure" if ANY stage fails.

    Args:
        stage_results: List of stage results, each "pass" or "fail".

    Returns:
        "success" if all stages passed, "failure" if any stage failed.
    """
    if not stage_results:
        return "failure"
    for result in stage_results:
        if result == "fail":
            return "failure"
    return "success"


def can_deploy_production(staging_result: str, smoke_result: str) -> bool:
    """Determine if production deployment is allowed.

    Production deployment is allowed ONLY when both staging deployment
    succeeded AND smoke tests passed.

    Args:
        staging_result: Result of staging deployment ("success" or "failure").
        smoke_result: Result of smoke tests ("success" or "failure").

    Returns:
        True if production deployment is allowed, False otherwise.
    """
    return staging_result == "success" and smoke_result == "success"


# ---------------------------------------------------------------------------
# Property 10: CI Strict Gating
# Feature: fsxn-s3ap-serverless-patterns-phase5, Property 10: CI Strict Gating
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    stage_results=st.lists(
        st.sampled_from(["pass", "fail"]),
        min_size=1,
        max_size=10,
    ),
)
def test_ci_strict_gating_failure_when_any_fail(
    stage_results: list[str],
):
    """Feature: fsxn-s3ap-serverless-patterns-phase5, Property 10: CI Strict Gating

    For any list of stage results where at least one stage is "fail",
    the final CI status SHALL be "failure".

    **Validates: Requirements 9.4, 9.5**
    """
    # Feature: fsxn-s3ap-serverless-patterns-phase5, Property 10: CI Strict Gating
    status = determine_ci_status(stage_results)

    has_failure = any(r == "fail" for r in stage_results)

    if has_failure:
        assert status == "failure", (
            f"Expected 'failure' when stage_results contains 'fail': "
            f"{stage_results}, but got '{status}'"
        )
    else:
        assert status == "success", (
            f"Expected 'success' when all stages pass: "
            f"{stage_results}, but got '{status}'"
        )


@settings(max_examples=100)
@given(
    stage_results=st.lists(
        st.sampled_from(["pass", "fail"]),
        min_size=1,
        max_size=10,
    ),
)
def test_ci_strict_gating_success_only_when_all_pass(
    stage_results: list[str],
):
    """Feature: fsxn-s3ap-serverless-patterns-phase5, Property 10: CI Strict Gating

    The final CI status SHALL be "success" ONLY when ALL stages are "pass".
    This is the converse: success implies all pass.

    **Validates: Requirements 9.4, 9.5**
    """
    # Feature: fsxn-s3ap-serverless-patterns-phase5, Property 10: CI Strict Gating
    status = determine_ci_status(stage_results)

    all_pass = all(r == "pass" for r in stage_results)

    if status == "success":
        assert all_pass, (
            f"CI status is 'success' but not all stages passed: "
            f"{stage_results}"
        )
    if all_pass:
        assert status == "success", (
            f"All stages passed but CI status is '{status}': "
            f"{stage_results}"
        )


# ---------------------------------------------------------------------------
# Property 11: Deployment Stage Ordering
# Feature: fsxn-s3ap-serverless-patterns-phase5, Property 11: Deployment Stage Ordering
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    staging_result=st.sampled_from(["success", "failure"]),
    smoke_result=st.sampled_from(["success", "failure"]),
)
def test_deployment_stage_ordering_production_allowed_only_on_both_success(
    staging_result: str,
    smoke_result: str,
):
    """Feature: fsxn-s3ap-serverless-patterns-phase5, Property 11: Deployment Stage Ordering

    Production deployment SHALL be allowed ONLY when both staging_result=="success"
    AND smoke_result=="success".

    **Validates: Requirements 10.2, 10.4, 10.5**
    """
    # Feature: fsxn-s3ap-serverless-patterns-phase5, Property 11: Deployment Stage Ordering
    allowed = can_deploy_production(staging_result, smoke_result)

    if staging_result == "success" and smoke_result == "success":
        assert allowed is True, (
            f"Expected production deployment allowed when staging={staging_result} "
            f"and smoke={smoke_result}, but got {allowed}"
        )
    else:
        assert allowed is False, (
            f"Expected production deployment blocked when staging={staging_result} "
            f"and smoke={smoke_result}, but got {allowed}"
        )


@settings(max_examples=100)
@given(
    staging_result=st.sampled_from(["success", "failure"]),
    smoke_result=st.sampled_from(["success", "failure"]),
)
def test_deployment_stage_ordering_blocked_on_any_failure(
    staging_result: str,
    smoke_result: str,
):
    """Feature: fsxn-s3ap-serverless-patterns-phase5, Property 11: Deployment Stage Ordering

    Production deployment SHALL be blocked when staging fails OR smoke test fails.

    **Validates: Requirements 10.2, 10.4, 10.5**
    """
    # Feature: fsxn-s3ap-serverless-patterns-phase5, Property 11: Deployment Stage Ordering
    allowed = can_deploy_production(staging_result, smoke_result)

    if staging_result == "failure" or smoke_result == "failure":
        assert allowed is False, (
            f"Expected production deployment blocked when staging={staging_result} "
            f"or smoke={smoke_result} is failure, but got {allowed}"
        )
    else:
        assert allowed is True, (
            f"Expected production deployment allowed when both succeed, "
            f"but got {allowed}"
        )
