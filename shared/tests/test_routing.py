"""Unit Tests for shared/routing.py — Routing Logic + ServerlessConfig Validation

determine_inference_path と validate_serverless_config の単体テスト。
- 各ルーティングルールの明示的テスト
- エッジケース（file_count=0, file_count=threshold, threshold=1）
- 無効な inference_type に対する ValueError
- validate_serverless_config の有効値・無効値テスト
- カバレッジ目標: 100%
"""

from __future__ import annotations

import pytest

from shared.routing import (
    InferencePath,
    MAX_CONCURRENCY_MAX,
    MAX_CONCURRENCY_MIN,
    VALID_INFERENCE_TYPES,
    VALID_MEMORY_SIZES_MB,
    determine_inference_path,
    validate_serverless_config,
)


# ---------------------------------------------------------------------------
# Tests: determine_inference_path — Routing Rules
# ---------------------------------------------------------------------------


class TestDetermineInferencePath:
    """determine_inference_path のルーティングルールテスト"""

    # Rule 1: inference_type="none" → BATCH_TRANSFORM
    def test_inference_type_none_returns_batch_transform(self):
        """inference_type='none' は常に BATCH_TRANSFORM を返す"""
        result = determine_inference_path(
            file_count=5, batch_threshold=10, inference_type="none"
        )
        assert result == InferencePath.BATCH_TRANSFORM

    def test_inference_type_none_ignores_file_count(self):
        """inference_type='none' は file_count に関係なく BATCH_TRANSFORM"""
        # file_count < threshold でも BATCH_TRANSFORM
        result = determine_inference_path(
            file_count=1, batch_threshold=100, inference_type="none"
        )
        assert result == InferencePath.BATCH_TRANSFORM

        # file_count >= threshold でも BATCH_TRANSFORM
        result = determine_inference_path(
            file_count=100, batch_threshold=10, inference_type="none"
        )
        assert result == InferencePath.BATCH_TRANSFORM

    # Rule 2: inference_type="serverless" → SERVERLESS_INFERENCE
    def test_inference_type_serverless_returns_serverless_inference(self):
        """inference_type='serverless' は常に SERVERLESS_INFERENCE を返す"""
        result = determine_inference_path(
            file_count=5, batch_threshold=10, inference_type="serverless"
        )
        assert result == InferencePath.SERVERLESS_INFERENCE

    def test_inference_type_serverless_ignores_file_count(self):
        """inference_type='serverless' は file_count に関係なく SERVERLESS_INFERENCE"""
        # file_count >= threshold でも SERVERLESS_INFERENCE
        result = determine_inference_path(
            file_count=100, batch_threshold=10, inference_type="serverless"
        )
        assert result == InferencePath.SERVERLESS_INFERENCE

        # file_count=0 でも SERVERLESS_INFERENCE
        result = determine_inference_path(
            file_count=0, batch_threshold=10, inference_type="serverless"
        )
        assert result == InferencePath.SERVERLESS_INFERENCE

    # Rule 3: file_count >= threshold with provisioned → BATCH_TRANSFORM
    def test_file_count_at_threshold_returns_batch_transform(self):
        """file_count == batch_threshold で BATCH_TRANSFORM を返す"""
        result = determine_inference_path(
            file_count=10, batch_threshold=10, inference_type="provisioned"
        )
        assert result == InferencePath.BATCH_TRANSFORM

    def test_file_count_above_threshold_returns_batch_transform(self):
        """file_count > batch_threshold で BATCH_TRANSFORM を返す"""
        result = determine_inference_path(
            file_count=50, batch_threshold=10, inference_type="provisioned"
        )
        assert result == InferencePath.BATCH_TRANSFORM

    # Rule 4: file_count < threshold with provisioned → REALTIME_ENDPOINT
    def test_file_count_below_threshold_provisioned_returns_realtime(self):
        """file_count < batch_threshold AND provisioned で REALTIME_ENDPOINT を返す"""
        result = determine_inference_path(
            file_count=5, batch_threshold=10, inference_type="provisioned"
        )
        assert result == InferencePath.REALTIME_ENDPOINT

    # Edge cases
    def test_file_count_zero(self):
        """file_count=0 のエッジケース"""
        # provisioned: 0 < threshold → REALTIME_ENDPOINT
        result = determine_inference_path(
            file_count=0, batch_threshold=10, inference_type="provisioned"
        )
        assert result == InferencePath.REALTIME_ENDPOINT

        # none: always BATCH_TRANSFORM
        result = determine_inference_path(
            file_count=0, batch_threshold=10, inference_type="none"
        )
        assert result == InferencePath.BATCH_TRANSFORM

    def test_threshold_equals_one(self):
        """batch_threshold=1 のエッジケース"""
        # file_count=0 < 1 → REALTIME_ENDPOINT
        result = determine_inference_path(
            file_count=0, batch_threshold=1, inference_type="provisioned"
        )
        assert result == InferencePath.REALTIME_ENDPOINT

        # file_count=1 >= 1 → BATCH_TRANSFORM
        result = determine_inference_path(
            file_count=1, batch_threshold=1, inference_type="provisioned"
        )
        assert result == InferencePath.BATCH_TRANSFORM

    def test_file_count_equals_threshold_boundary(self):
        """file_count == threshold の境界値テスト（>= なので BATCH_TRANSFORM）"""
        result = determine_inference_path(
            file_count=100, batch_threshold=100, inference_type="provisioned"
        )
        assert result == InferencePath.BATCH_TRANSFORM

    # ValueError for invalid inference_type
    def test_invalid_inference_type_raises_value_error(self):
        """無効な inference_type で ValueError を raise する"""
        with pytest.raises(ValueError, match="Invalid inference_type"):
            determine_inference_path(
                file_count=5, batch_threshold=10, inference_type="invalid"
            )

    def test_empty_inference_type_raises_value_error(self):
        """空文字列の inference_type で ValueError を raise する"""
        with pytest.raises(ValueError, match="Invalid inference_type"):
            determine_inference_path(
                file_count=5, batch_threshold=10, inference_type=""
            )

    def test_case_sensitive_inference_type(self):
        """inference_type は大文字小文字を区別する"""
        with pytest.raises(ValueError, match="Invalid inference_type"):
            determine_inference_path(
                file_count=5, batch_threshold=10, inference_type="Serverless"
            )

        with pytest.raises(ValueError, match="Invalid inference_type"):
            determine_inference_path(
                file_count=5, batch_threshold=10, inference_type="NONE"
            )


# ---------------------------------------------------------------------------
# Tests: validate_serverless_config — Valid Values
# ---------------------------------------------------------------------------


class TestValidateServerlessConfigValid:
    """validate_serverless_config の有効値テスト"""

    @pytest.mark.parametrize(
        "memory_size",
        [1024, 2048, 3072, 4096, 5120, 6144],
    )
    def test_all_valid_memory_sizes(self, memory_size: int):
        """全 6 つの有効な MemorySizeInMB 値で valid を返す"""
        is_valid, error = validate_serverless_config(
            memory_size_mb=memory_size, max_concurrency=5
        )
        assert is_valid is True
        assert error is None

    def test_min_max_concurrency(self):
        """MaxConcurrency=1（最小値）で valid を返す"""
        is_valid, error = validate_serverless_config(
            memory_size_mb=4096, max_concurrency=1
        )
        assert is_valid is True
        assert error is None

    def test_max_max_concurrency(self):
        """MaxConcurrency=200（最大値）で valid を返す"""
        is_valid, error = validate_serverless_config(
            memory_size_mb=4096, max_concurrency=200
        )
        assert is_valid is True
        assert error is None

    def test_valid_provisioned_concurrency(self):
        """ProvisionedConcurrency=0（デフォルト）で valid を返す"""
        is_valid, error = validate_serverless_config(
            memory_size_mb=4096, max_concurrency=5, provisioned_concurrency=0
        )
        assert is_valid is True
        assert error is None

    def test_positive_provisioned_concurrency(self):
        """ProvisionedConcurrency > 0 で valid を返す"""
        is_valid, error = validate_serverless_config(
            memory_size_mb=4096, max_concurrency=5, provisioned_concurrency=3
        )
        assert is_valid is True
        assert error is None

    def test_typical_configuration(self):
        """典型的な構成（4096MB, concurrency=5）で valid を返す"""
        is_valid, error = validate_serverless_config(
            memory_size_mb=4096, max_concurrency=5
        )
        assert is_valid is True
        assert error is None


# ---------------------------------------------------------------------------
# Tests: validate_serverless_config — Invalid Values (Boundary Cases)
# ---------------------------------------------------------------------------


class TestValidateServerlessConfigInvalid:
    """validate_serverless_config の無効値テスト（境界ケース）"""

    # Invalid MemorySizeInMB
    def test_memory_size_below_minimum(self):
        """MemorySizeInMB < 1024 で invalid を返す"""
        is_valid, error = validate_serverless_config(
            memory_size_mb=512, max_concurrency=5
        )
        assert is_valid is False
        assert "MemorySizeInMB" in error

    def test_memory_size_above_maximum(self):
        """MemorySizeInMB > 6144 で invalid を返す"""
        is_valid, error = validate_serverless_config(
            memory_size_mb=8192, max_concurrency=5
        )
        assert is_valid is False
        assert "MemorySizeInMB" in error

    def test_memory_size_not_in_valid_set(self):
        """有効セットに含まれない MemorySizeInMB で invalid を返す"""
        # 1500 は 1024 と 2048 の間だが有効セットに含まれない
        is_valid, error = validate_serverless_config(
            memory_size_mb=1500, max_concurrency=5
        )
        assert is_valid is False
        assert "MemorySizeInMB" in error

    def test_memory_size_zero(self):
        """MemorySizeInMB=0 で invalid を返す"""
        is_valid, error = validate_serverless_config(
            memory_size_mb=0, max_concurrency=5
        )
        assert is_valid is False
        assert "MemorySizeInMB" in error

    # Invalid MaxConcurrency
    def test_max_concurrency_below_minimum(self):
        """MaxConcurrency=0 で invalid を返す"""
        is_valid, error = validate_serverless_config(
            memory_size_mb=4096, max_concurrency=0
        )
        assert is_valid is False
        assert "MaxConcurrency" in error

    def test_max_concurrency_negative(self):
        """MaxConcurrency < 0 で invalid を返す"""
        is_valid, error = validate_serverless_config(
            memory_size_mb=4096, max_concurrency=-1
        )
        assert is_valid is False
        assert "MaxConcurrency" in error

    def test_max_concurrency_above_maximum(self):
        """MaxConcurrency > 200 で invalid を返す"""
        is_valid, error = validate_serverless_config(
            memory_size_mb=4096, max_concurrency=201
        )
        assert is_valid is False
        assert "MaxConcurrency" in error

    # Invalid ProvisionedConcurrency
    def test_provisioned_concurrency_negative(self):
        """ProvisionedConcurrency < 0 で invalid を返す"""
        is_valid, error = validate_serverless_config(
            memory_size_mb=4096, max_concurrency=5, provisioned_concurrency=-1
        )
        assert is_valid is False
        assert "ProvisionedConcurrency" in error

    # Validation priority: first invalid field is reported
    def test_memory_validated_before_concurrency(self):
        """MemorySizeInMB が先にバリデーションされる"""
        is_valid, error = validate_serverless_config(
            memory_size_mb=999, max_concurrency=999
        )
        assert is_valid is False
        assert "MemorySizeInMB" in error


# ---------------------------------------------------------------------------
# Tests: determine_inference_path — "components" routing (Phase 6B)
# ---------------------------------------------------------------------------


class TestDetermineInferencePathComponents:
    """determine_inference_path の "components" ルーティングテスト（Phase 6B）"""

    def test_inference_type_components_returns_inference_components(self):
        """inference_type='components' は常に INFERENCE_COMPONENTS を返す"""
        result = determine_inference_path(
            file_count=5, batch_threshold=10, inference_type="components"
        )
        assert result == InferencePath.INFERENCE_COMPONENTS

    def test_inference_type_components_ignores_file_count(self):
        """inference_type='components' は file_count に関係なく INFERENCE_COMPONENTS"""
        # file_count >= threshold でも INFERENCE_COMPONENTS
        result = determine_inference_path(
            file_count=100, batch_threshold=10, inference_type="components"
        )
        assert result == InferencePath.INFERENCE_COMPONENTS

        # file_count=0 でも INFERENCE_COMPONENTS
        result = determine_inference_path(
            file_count=0, batch_threshold=10, inference_type="components"
        )
        assert result == InferencePath.INFERENCE_COMPONENTS

    def test_components_has_higher_priority_than_batch_threshold(self):
        """components は batch_threshold より優先される"""
        # file_count >= threshold でも components が優先
        result = determine_inference_path(
            file_count=1000, batch_threshold=10, inference_type="components"
        )
        assert result == InferencePath.INFERENCE_COMPONENTS

    def test_inference_components_enum_value(self):
        """INFERENCE_COMPONENTS の enum 値が正しい"""
        assert InferencePath.INFERENCE_COMPONENTS.value == "inference_components"


# ---------------------------------------------------------------------------
# Tests: validate_inference_config (Phase 6B)
# ---------------------------------------------------------------------------

from shared.routing import validate_inference_config


class TestValidateInferenceConfig:
    """validate_inference_config のテスト（Phase 6B）"""

    def test_none_type_requires_no_params(self):
        """inference_type='none' は追加パラメータ不要"""
        is_valid, error = validate_inference_config(inference_type="none")
        assert is_valid is True
        assert error is None

    def test_provisioned_requires_endpoint_name(self):
        """inference_type='provisioned' は endpoint_name が必須"""
        is_valid, error = validate_inference_config(
            inference_type="provisioned", endpoint_name=""
        )
        assert is_valid is False
        assert "endpoint_name" in error

    def test_provisioned_with_endpoint_name_valid(self):
        """inference_type='provisioned' + endpoint_name で valid"""
        is_valid, error = validate_inference_config(
            inference_type="provisioned", endpoint_name="my-endpoint"
        )
        assert is_valid is True
        assert error is None

    def test_serverless_requires_endpoint_name(self):
        """inference_type='serverless' は endpoint_name が必須"""
        is_valid, error = validate_inference_config(
            inference_type="serverless", endpoint_name=""
        )
        assert is_valid is False
        assert "endpoint_name" in error

    def test_components_requires_endpoint_and_component_name(self):
        """inference_type='components' は endpoint_name と component_name が必須"""
        # Both missing
        is_valid, error = validate_inference_config(
            inference_type="components", endpoint_name="", component_name=""
        )
        assert is_valid is False
        assert "endpoint_name" in error

        # endpoint_name only
        is_valid, error = validate_inference_config(
            inference_type="components",
            endpoint_name="my-endpoint",
            component_name="",
        )
        assert is_valid is False
        assert "component_name" in error

        # Both provided
        is_valid, error = validate_inference_config(
            inference_type="components",
            endpoint_name="my-endpoint",
            component_name="my-component",
        )
        assert is_valid is True
        assert error is None

    def test_invalid_inference_type(self):
        """無効な inference_type で invalid を返す"""
        is_valid, error = validate_inference_config(inference_type="invalid")
        assert is_valid is False
        assert "Invalid inference_type" in error
