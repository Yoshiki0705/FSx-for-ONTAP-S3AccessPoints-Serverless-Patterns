"""Property-Based Tests for UC9 Phase 3: SageMaker Batch Transform 統合

Hypothesis を使用したプロパティベーステスト。
SageMaker Callback Pattern の Task_Token round-trip、
Point count invariant、Error state propagation を検証する。

Testing Strategy:
- 最小 100 イテレーション/プロパティ
- 各テストにプロパティ番号タグを付与
- タグ形式: Feature: fsxn-s3ap-serverless-patterns-phase3, Property {number}: {property_text}
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

from hypothesis import given, settings, strategies as st

# shared モジュールと UC9 関数のパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 環境変数設定（インポート前に必要）
os.environ.setdefault("OUTPUT_BUCKET", "test-output-bucket")
os.environ.setdefault("MOCK_MODE", "true")
os.environ.setdefault("SAGEMAKER_MODEL_NAME", "test-model")
os.environ.setdefault("SAGEMAKER_INSTANCE_TYPE", "ml.m5.xlarge")
os.environ.setdefault("USE_CASE", "autonomous-driving")
os.environ.setdefault("REGION", "ap-northeast-1")
os.environ.setdefault("ENABLE_XRAY", "false")

from functions.sagemaker_invoke.handler import (
    generate_mock_segmentation,
    _handle_mock_mode,
)
from functions.sagemaker_callback.handler import (
    handle_job_failure,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Task Token: 任意の非空文字列（Step Functions が生成する一意トークン）
task_token_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S"),
        blacklist_characters="\x00",
    ),
    min_size=1,
    max_size=200,
)

# Point count: 正の整数
point_count_strategy = st.integers(min_value=1, max_value=10000)

# Job status: Failed or Stopped
failed_job_status_strategy = st.sampled_from(["Failed", "Stopped"])

# Error message: 非空文字列
error_message_strategy = st.text(min_size=1, max_size=500)


# ---------------------------------------------------------------------------
# Property 5: Task_Token propagation round-trip (invoke → callback)
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(task_token=task_token_strategy, point_count=point_count_strategy)
def test_task_token_round_trip(task_token, point_count):
    """Feature: fsxn-s3ap-serverless-patterns-phase3, Property 5: Task_Token propagation round-trip (invoke → callback)

    For all valid task tokens (arbitrary strings), invoking sagemaker_invoke
    in MOCK_MODE=true results in SendTaskSuccess being called with the same
    task_token.

    Strategy: Generate arbitrary task tokens and point counts, invoke mock mode,
    verify SendTaskSuccess is called with the exact same token.

    **Validates: Requirements 4.2, 4.5, 5.3**
    """
    event = {
        "task_token": task_token,
        "input_s3_path": "s3://test-bucket/input/",
        "point_count": point_count,
    }

    with patch("functions.sagemaker_invoke.handler.boto3") as mock_boto3:
        mock_sfn = MagicMock()
        mock_boto3.client.return_value = mock_sfn

        mock_writer = MagicMock()
        mock_writer.build_s3_uri.return_value = (
            "s3://test-output-bucket/sagemaker-output/out.json"
        )

        result = _handle_mock_mode(event, task_token, mock_writer)

        # SendTaskSuccess が呼ばれたことを確認
        mock_sfn.send_task_success.assert_called_once()
        call_kwargs = mock_sfn.send_task_success.call_args[1]

        # Task Token が正確に伝播されていることを確認
        assert call_kwargs["taskToken"] == task_token, (
            f"Task token mismatch: expected '{task_token}', "
            f"got '{call_kwargs['taskToken']}'"
        )

        # 出力に正しいメタデータが含まれることを確認
        output = json.loads(call_kwargs["output"])
        assert output["status"] == "COMPLETED"
        assert output["point_count"] == point_count


# ---------------------------------------------------------------------------
# Property 6: Point count invariant (input points == output labels)
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(point_count=point_count_strategy)
def test_point_count_invariant(point_count):
    """Feature: fsxn-s3ap-serverless-patterns-phase3, Property 6: Point count invariant (input points == output points)

    For all valid point cloud inputs with point_count N, the mock
    segmentation output contains exactly N labels.

    Strategy: Generate random point counts, run mock segmentation,
    verify output label count equals input point count.

    **Validates: Requirements 4.7, 5.3**
    """
    labels = generate_mock_segmentation(point_count)

    # ラベル数が入力ポイント数と一致することを確認
    assert len(labels) == point_count, (
        f"Point count invariant violated: input={point_count}, "
        f"output_labels={len(labels)}"
    )

    # 各ラベルが有効な範囲内であることを確認
    for label in labels:
        assert isinstance(label, int), f"Label is not int: {type(label)}"
        assert 0 <= label <= 9, f"Label out of range: {label}"


# ---------------------------------------------------------------------------
# Property 7: Error state propagation (failed job → SendTaskFailure)
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    task_token=task_token_strategy,
    job_status=failed_job_status_strategy,
    error_message=error_message_strategy,
)
def test_error_state_propagation(task_token, job_status, error_message):
    """Feature: fsxn-s3ap-serverless-patterns-phase3, Property 7: Error state propagation (failed job → SendTaskFailure)

    For all failed job states, sagemaker_callback calls SendTaskFailure
    with the correct task_token and a non-empty error message.

    Strategy: Generate arbitrary task tokens, failed job statuses, and error
    messages. Verify SendTaskFailure is called with correct parameters.

    **Validates: Requirements 4.6, 5.3**
    """
    mock_sfn = MagicMock()
    job_name = f"test-job-{job_status.lower()}"

    result = handle_job_failure(mock_sfn, task_token, job_name, error_message)

    # SendTaskFailure が呼ばれたことを確認
    mock_sfn.send_task_failure.assert_called_once()
    call_kwargs = mock_sfn.send_task_failure.call_args[1]

    # Task Token が正確に伝播されていることを確認
    assert call_kwargs["taskToken"] == task_token, (
        f"Task token mismatch: expected '{task_token}', "
        f"got '{call_kwargs['taskToken']}'"
    )

    # エラーメッセージが非空であることを確認
    assert call_kwargs["cause"], "Error message (cause) must not be empty"
    assert len(call_kwargs["cause"]) > 0

    # エラーコードが設定されていることを確認
    assert call_kwargs["error"] == "SageMakerTransformJobFailed"

    # 結果が正しいアクションを示すことを確認
    assert result["action"] == "SendTaskFailure"
