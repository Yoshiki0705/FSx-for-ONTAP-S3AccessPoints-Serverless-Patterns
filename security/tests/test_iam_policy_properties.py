"""Property-Based Tests for IAM Policy Security Validation

Hypothesis を使用したプロパティベーステスト。
IAM ポリシーステートメントに管理者アクセス（Action:"*" + Resource:"*"）が
含まれないことを検証するセキュリティプロパティ。

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


def check_iam_policy_no_admin(statement: dict) -> bool:
    """Check that an IAM policy statement does NOT have admin access.

    Admin access is defined as Action:"*" combined with Resource:"*".
    Returns True if the statement is safe (no admin access),
    False if it has admin access (violation detected).

    Args:
        statement: IAM policy statement dict with "Action" and "Resource" keys.

    Returns:
        True if no admin access (safe), False if admin access detected (violation).
    """
    action = statement.get("Action", "")
    resource = statement.get("Resource", "")
    # Violation: both Action and Resource are wildcard "*"
    if action == "*" and resource == "*":
        return False
    return True


# ---------------------------------------------------------------------------
# Property 12: No Admin Access in IAM Policies
# Feature: fsxn-s3ap-serverless-patterns-phase5, Property 12: No Admin Access in IAM Policies
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    statement=st.fixed_dictionaries({
        "Action": st.one_of(
            st.just("*"),
            st.sampled_from(["s3:GetObject", "lambda:InvokeFunction"]),
        ),
        "Resource": st.one_of(
            st.just("*"),
            st.text(min_size=10, max_size=50),
        ),
    }),
)
def test_iam_policy_no_admin_detects_wildcard_violation(
    statement: dict,
):
    """Feature: fsxn-s3ap-serverless-patterns-phase5, Property 12: No Admin Access in IAM Policies

    For any policy statement with Action:"*" AND Resource:"*",
    the check SHALL return False (violation detected).
    For any policy statement where Action != "*" OR Resource != "*",
    the check SHALL return True (no violation).

    **Validates: Requirements 11.1, 20.2**
    """
    # Feature: fsxn-s3ap-serverless-patterns-phase5, Property 12: No Admin Access in IAM Policies
    result = check_iam_policy_no_admin(statement)

    action = statement["Action"]
    resource = statement["Resource"]

    if action == "*" and resource == "*":
        assert result is False, (
            f"Expected violation (False) for Action='*' + Resource='*', "
            f"but got {result}"
        )
    else:
        assert result is True, (
            f"Expected safe (True) for Action='{action}' + Resource='{resource}', "
            f"but got {result}"
        )


@settings(max_examples=100)
@given(
    statement=st.fixed_dictionaries({
        "Action": st.just("*"),
        "Resource": st.just("*"),
    }),
)
def test_iam_policy_no_admin_always_rejects_full_wildcard(
    statement: dict,
):
    """Feature: fsxn-s3ap-serverless-patterns-phase5, Property 12: No Admin Access in IAM Policies

    Any policy statement with BOTH Action:"*" AND Resource:"*" SHALL always
    be detected as a violation (returns False).

    **Validates: Requirements 11.1, 20.2**
    """
    # Feature: fsxn-s3ap-serverless-patterns-phase5, Property 12: No Admin Access in IAM Policies
    result = check_iam_policy_no_admin(statement)
    assert result is False, (
        f"Expected violation for full wildcard statement {statement}, "
        f"but got {result}"
    )


@settings(max_examples=100)
@given(
    statement=st.fixed_dictionaries({
        "Action": st.sampled_from(["s3:GetObject", "lambda:InvokeFunction"]),
        "Resource": st.one_of(
            st.just("*"),
            st.text(min_size=10, max_size=50),
        ),
    }),
)
def test_iam_policy_no_admin_allows_specific_actions(
    statement: dict,
):
    """Feature: fsxn-s3ap-serverless-patterns-phase5, Property 12: No Admin Access in IAM Policies

    Any policy statement where Action is NOT "*" SHALL always be considered
    safe (returns True), regardless of Resource value.

    **Validates: Requirements 11.1, 20.2**
    """
    # Feature: fsxn-s3ap-serverless-patterns-phase5, Property 12: No Admin Access in IAM Policies
    result = check_iam_policy_no_admin(statement)
    assert result is True, (
        f"Expected safe (True) for specific action '{statement['Action']}', "
        f"but got {result}"
    )
