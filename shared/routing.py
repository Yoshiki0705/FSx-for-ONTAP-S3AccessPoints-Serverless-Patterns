"""shared.routing - 推論ルーティングロジック共通モジュール

UC9 Step Functions ワークフローの 4-way ルーティング決定ロジックと
SageMaker ServerlessConfig / InferenceComponents バリデーションを提供する。

設計方針:
- file_count + InferenceType の組み合わせで決定論的にルーティング
- InferenceType="serverless" は file_count 閾値に関係なく Serverless パスへ
- InferenceType="components" は file_count 閾値に関係なく Inference Components パスへ
- InferenceType="none" は常に Batch Transform（エンドポイント未作成時）
- ServerlessConfig パラメータは AWS SageMaker の制約に準拠

Usage:
    from shared.routing import InferencePath, determine_inference_path, validate_serverless_config

    path = determine_inference_path(file_count=5, batch_threshold=10, inference_type="serverless")
    assert path == InferencePath.SERVERLESS_INFERENCE

    path = determine_inference_path(file_count=5, batch_threshold=10, inference_type="components")
    assert path == InferencePath.INFERENCE_COMPONENTS

    is_valid, error = validate_serverless_config(memory_size_mb=4096, max_concurrency=5)
    assert is_valid is True
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

# SageMaker Serverless Inference で許可される MemorySizeInMB 値
VALID_MEMORY_SIZES_MB: frozenset[int] = frozenset({1024, 2048, 3072, 4096, 5120, 6144})

# SageMaker Serverless Inference MaxConcurrency の有効範囲
MAX_CONCURRENCY_MIN: int = 1
MAX_CONCURRENCY_MAX: int = 200

# 有効な InferenceType 値
VALID_INFERENCE_TYPES: frozenset[str] = frozenset({"provisioned", "serverless", "none", "components"})


class InferencePath(Enum):
    """推論ルーティングパスの列挙型。

    Step Functions Choice State で選択される 4 つの推論パスを定義する。

    Values:
        BATCH_TRANSFORM: SageMaker Batch Transform（大量ファイル or エンドポイント未作成時）
        REALTIME_ENDPOINT: SageMaker Real-time Endpoint（少量ファイル + provisioned）
        SERVERLESS_INFERENCE: SageMaker Serverless Inference（serverless 指定時）
        INFERENCE_COMPONENTS: SageMaker Inference Components（components 指定時、scale-to-zero 対応）
    """

    BATCH_TRANSFORM = "batch_transform"
    REALTIME_ENDPOINT = "realtime_endpoint"
    SERVERLESS_INFERENCE = "serverless_inference"
    INFERENCE_COMPONENTS = "inference_components"


def determine_inference_path(
    file_count: int,
    batch_threshold: int,
    inference_type: str,
) -> InferencePath:
    """推論ルーティングパスを決定する。

    file_count と inference_type の組み合わせに基づき、決定論的に
    1 つの推論パスを選択する。同一入力に対して常に同一結果を返す。

    ルーティングロジック（優先順位順）:
        1. inference_type == "none" → BATCH_TRANSFORM（エンドポイント未作成）
        2. inference_type == "serverless" → SERVERLESS_INFERENCE
        3. inference_type == "components" → INFERENCE_COMPONENTS
        4. file_count >= batch_threshold → BATCH_TRANSFORM
        5. file_count < batch_threshold AND inference_type == "provisioned" → REALTIME_ENDPOINT

    Args:
        file_count: 処理対象ファイル数（0 以上の整数）
        batch_threshold: バッチ処理閾値（1 以上の整数）
        inference_type: 推論タイプ ("provisioned", "serverless", "none", "components")

    Returns:
        InferencePath: 選択された推論パス（常に 1 つ）

    Raises:
        ValueError: inference_type が {"provisioned", "serverless", "none", "components"} に含まれない場合
    """
    if inference_type not in VALID_INFERENCE_TYPES:
        raise ValueError(
            f"Invalid inference_type '{inference_type}'. "
            f"Must be one of: {', '.join(sorted(VALID_INFERENCE_TYPES))}"
        )

    # Rule 1: No endpoint created → always batch
    if inference_type == "none":
        return InferencePath.BATCH_TRANSFORM

    # Rule 2: Serverless type → always serverless path
    if inference_type == "serverless":
        return InferencePath.SERVERLESS_INFERENCE

    # Rule 3: Components type → always inference components path
    if inference_type == "components":
        return InferencePath.INFERENCE_COMPONENTS

    # Rule 4: Large file count → batch transform
    if file_count >= batch_threshold:
        return InferencePath.BATCH_TRANSFORM

    # Rule 5: Small file count + provisioned → realtime endpoint
    return InferencePath.REALTIME_ENDPOINT


def validate_serverless_config(
    memory_size_mb: int,
    max_concurrency: int,
    provisioned_concurrency: int = 0,
) -> tuple[bool, Optional[str]]:
    """SageMaker ServerlessConfig パラメータをバリデーションする。

    AWS SageMaker Serverless Inference の制約に基づき、
    ServerlessConfig ブロックのパラメータ値を検証する。

    バリデーションルール:
        - MemorySizeInMB: {1024, 2048, 3072, 4096, 5120, 6144} のいずれか
        - MaxConcurrency: [1, 200] の範囲内
        - ProvisionedConcurrency: 0 以上（0 = 無効）

    Args:
        memory_size_mb: メモリサイズ (MB)
        max_concurrency: 最大同時実行数
        provisioned_concurrency: プロビジョンド同時実行数（デフォルト: 0 = 無効）

    Returns:
        tuple[bool, Optional[str]]: (is_valid, error_message)
            - is_valid が True の場合、error_message は None
            - is_valid が False の場合、error_message にエラー詳細を含む
    """
    # Validate MemorySizeInMB
    if memory_size_mb not in VALID_MEMORY_SIZES_MB:
        return (
            False,
            f"Invalid MemorySizeInMB: {memory_size_mb}. "
            f"Must be one of: {sorted(VALID_MEMORY_SIZES_MB)}",
        )

    # Validate MaxConcurrency
    if max_concurrency < MAX_CONCURRENCY_MIN or max_concurrency > MAX_CONCURRENCY_MAX:
        return (
            False,
            f"Invalid MaxConcurrency: {max_concurrency}. "
            f"Must be in range [{MAX_CONCURRENCY_MIN}, {MAX_CONCURRENCY_MAX}]",
        )

    # Validate ProvisionedConcurrency
    if provisioned_concurrency < 0:
        return (
            False,
            f"Invalid ProvisionedConcurrency: {provisioned_concurrency}. "
            "Must be >= 0",
        )

    return (True, None)


def validate_inference_config(
    inference_type: str,
    endpoint_name: str = "",
    component_name: str = "",
) -> tuple[bool, Optional[str]]:
    """推論設定をバリデーションする。

    inference_type に応じて必要なパラメータが設定されているか検証する。

    バリデーションルール:
        - inference_type: VALID_INFERENCE_TYPES のいずれか
        - inference_type == "provisioned" or "serverless" or "components":
          endpoint_name が必須
        - inference_type == "components": component_name が必須

    Args:
        inference_type: 推論タイプ
        endpoint_name: SageMaker Endpoint 名（provisioned/serverless/components で必須）
        component_name: Inference Component 名（components で必須）

    Returns:
        tuple[bool, Optional[str]]: (is_valid, error_message)
            - is_valid が True の場合、error_message は None
            - is_valid が False の場合、error_message にエラー詳細を含む
    """
    # Validate inference_type
    if inference_type not in VALID_INFERENCE_TYPES:
        return (
            False,
            f"Invalid inference_type '{inference_type}'. "
            f"Must be one of: {', '.join(sorted(VALID_INFERENCE_TYPES))}",
        )

    # "none" requires no additional parameters
    if inference_type == "none":
        return (True, None)

    # provisioned / serverless / components require endpoint_name
    if not endpoint_name:
        return (
            False,
            f"endpoint_name is required when inference_type='{inference_type}'",
        )

    # components additionally requires component_name
    if inference_type == "components" and not component_name:
        return (
            False,
            "component_name is required when inference_type='components'",
        )

    return (True, None)
