"""Property-Based Tests for UC9: 自動運転 / ADAS

Hypothesis を使用したプロパティベーステスト。
点群 QC バリデーションと COCO 互換アノテーション出力の不変条件を検証する。

Testing Strategy:
- 最小 100 イテレーション/プロパティ
- 各テストにプロパティ番号タグを付与
- タグ形式: Feature: fsxn-s3ap-serverless-patterns-phase2, Property {number}: {property_text}
"""

from __future__ import annotations

import json
import math
import os
import sys

from hypothesis import given, settings, strategies as st

# shared モジュールと UC9 関数のパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from functions.point_cloud_qc.handler import (
    parse_pcd_header,
    validate_point_cloud,
)
from functions.annotation_manager.handler import (
    build_coco_annotations,
    COCO_CATEGORIES,
)


# ---------------------------------------------------------------------------
# Helper: PCD ファイルデータ生成
# ---------------------------------------------------------------------------


def build_pcd_data(
    point_count: int,
    inject_nan: int = 0,
    mismatch_header: bool = False,
    x_range: tuple[float, float] = (-50.0, 50.0),
    y_range: tuple[float, float] = (-50.0, 50.0),
    z_range: tuple[float, float] = (-5.0, 15.0),
) -> str:
    """テスト用の PCD ファイルデータを生成する

    Args:
        point_count: 生成するポイント数
        inject_nan: NaN を注入するポイント数
        mismatch_header: ヘッダーのポイント数を不一致にする
        x_range: X 座標の範囲
        y_range: Y 座標の範囲
        z_range: Z 座標の範囲

    Returns:
        str: PCD ファイルの内容（テキスト形式）
    """
    # ヘッダーのポイント数（不一致テスト用）
    header_points = point_count + 10 if mismatch_header else point_count

    header = (
        "# .PCD v0.7\n"
        "VERSION 0.7\n"
        "FIELDS x y z intensity\n"
        "SIZE 4 4 4 4\n"
        "TYPE F F F F\n"
        "COUNT 1 1 1 1\n"
        f"WIDTH {header_points}\n"
        "HEIGHT 1\n"
        "VIEWPOINT 0 0 0 1 0 0 0\n"
        f"POINTS {header_points}\n"
        "DATA ascii\n"
    )

    # データ行生成
    lines = []
    import random

    random.seed(42)  # 再現性のため固定シード

    for i in range(point_count):
        if i < inject_nan:
            # NaN を注入
            lines.append("nan nan nan 0.5")
        else:
            x = random.uniform(x_range[0], x_range[1])
            y = random.uniform(y_range[0], y_range[1])
            z = random.uniform(z_range[0], z_range[1])
            intensity = random.uniform(0.0, 1.0)
            lines.append(f"{x:.6f} {y:.6f} {z:.6f} {intensity:.6f}")

    return header + "\n".join(lines)


# ---------------------------------------------------------------------------
# Property 12: Point cloud QC validation
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    point_count=st.integers(min_value=10, max_value=500),
    inject_nan=st.integers(min_value=0, max_value=5),
    mismatch_header=st.booleans(),
)
def test_point_cloud_qc_validation(point_count, inject_nan, mismatch_header):
    """Feature: fsxn-s3ap-serverless-patterns-phase2, Property 12: Point cloud QC validation

    For any point cloud data with a header declaring point_count P and
    coordinate arrays, the Point_Cloud_QC_Lambda SHALL report status "PASS"
    if and only if: (a) actual points == P, (b) no NaN coordinates,
    (c) point_density > 0. Otherwise "FAIL".

    Strategy: Generate point cloud headers with random point_count, inject
    NaN or count mismatches, verify PASS/FAIL logic.

    **Validates: Requirements 6.3, 6.4**
    """
    # NaN 注入数はポイント数を超えない
    actual_nan = min(inject_nan, point_count)

    # PCD データ生成
    pcd_data = build_pcd_data(
        point_count=point_count,
        inject_nan=actual_nan,
        mismatch_header=mismatch_header,
    )

    # ヘッダーパース
    header = parse_pcd_header(pcd_data)

    # データ行取得
    lines = pcd_data.split("\n")
    data_start = 0
    for i, line in enumerate(lines):
        if line.strip().upper().startswith("DATA"):
            data_start = i + 1
            break
    data_lines = lines[data_start:]

    # バリデーション実行
    metrics = validate_point_cloud(header, data_lines)
    status = metrics["status"]

    # PASS 条件の検証
    # (a) actual points == declared points
    # (b) no NaN coordinates
    # (c) point_density > 0
    should_pass = (
        not mismatch_header  # ヘッダー一致
        and actual_nan == 0  # NaN なし
        and metrics["point_density"] > 0  # 密度 > 0
    )

    if should_pass:
        assert status == "PASS", (
            f"Expected PASS but got FAIL. "
            f"mismatch={mismatch_header}, nan={actual_nan}, "
            f"density={metrics['point_density']}, "
            f"reasons={metrics.get('failure_reasons', [])}"
        )
    else:
        assert status == "FAIL", (
            f"Expected FAIL but got PASS. "
            f"mismatch={mismatch_header}, nan={actual_nan}, "
            f"density={metrics['point_density']}"
        )

    # メトリクスの構造検証
    assert "point_count" in metrics
    assert "coordinate_bounds" in metrics
    assert "point_density" in metrics
    assert "nan_coordinates" in metrics
    assert "header_point_count_match" in metrics

    # NaN カウントの検証
    assert metrics["nan_coordinates"] == actual_nan

    # ヘッダー一致の検証
    assert metrics["header_point_count_match"] == (not mismatch_header)


# ---------------------------------------------------------------------------
# Property 13: COCO-compatible annotation output
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    num_results=st.integers(min_value=0, max_value=5),
    num_detections_per_frame=st.integers(min_value=0, max_value=10),
    labels=st.lists(
        st.sampled_from([
            "Car", "Pedestrian", "Traffic Sign", "Lane",
            "Truck", "Bicycle", "Building", "Tree", "Unknown",
        ]),
        min_size=1,
        max_size=5,
    ),
)
def test_coco_compatible_annotation_output(
    num_results, num_detections_per_frame, labels
):
    """Feature: fsxn-s3ap-serverless-patterns-phase2, Property 13: COCO-compatible annotation output

    For any set of detection results, the output SHALL contain "images",
    "annotations", "categories" arrays where each annotation references
    valid image_id and category_id.

    Strategy: Generate random detection results, run annotation formatting,
    verify COCO structure.

    **Validates: Requirements 6.6**
    """
    # 検出結果を生成
    detection_results = []
    for i in range(num_results):
        detections = []
        for frame_idx in range(min(2, num_detections_per_frame)):
            objects = []
            for label in labels[:num_detections_per_frame]:
                objects.append({
                    "label": label,
                    "confidence": 85.0,
                    "bounding_box": {
                        "left": 0.1,
                        "top": 0.2,
                        "width": 0.3,
                        "height": 0.4,
                    },
                })
            detections.append({
                "frame_index": frame_idx,
                "timestamp_ms": frame_idx * 1000,
                "objects": objects,
            })

        detection_results.append({
            "file_key": f"video_{i}.mp4",
            "frames_extracted": 10,
            "detections": detections,
        })

    # COCO アノテーション構築
    coco = build_coco_annotations(detection_results)

    # 構造検証: 必須キーの存在
    assert "images" in coco, "Missing 'images' key in COCO output"
    assert "annotations" in coco, "Missing 'annotations' key in COCO output"
    assert "categories" in coco, "Missing 'categories' key in COCO output"

    # 型検証
    assert isinstance(coco["images"], list)
    assert isinstance(coco["annotations"], list)
    assert isinstance(coco["categories"], list)

    # カテゴリは常に存在する
    assert len(coco["categories"]) > 0

    # 有効な category_id のセット
    valid_category_ids = {cat["id"] for cat in coco["categories"]}

    # 有効な image_id のセット
    valid_image_ids = {img["id"] for img in coco["images"]}

    # 各アノテーションが有効な image_id と category_id を参照する
    for ann in coco["annotations"]:
        assert "id" in ann, "Annotation missing 'id'"
        assert "image_id" in ann, "Annotation missing 'image_id'"
        assert "category_id" in ann, "Annotation missing 'category_id'"
        assert "bbox" in ann, "Annotation missing 'bbox'"

        assert ann["image_id"] in valid_image_ids, (
            f"Annotation references invalid image_id: {ann['image_id']}, "
            f"valid: {valid_image_ids}"
        )
        assert ann["category_id"] in valid_category_ids, (
            f"Annotation references invalid category_id: {ann['category_id']}, "
            f"valid: {valid_category_ids}"
        )

        # bbox は [x, y, width, height] 形式
        assert isinstance(ann["bbox"], list)
        assert len(ann["bbox"]) == 4

    # 各画像の id はユニーク
    image_ids = [img["id"] for img in coco["images"]]
    assert len(image_ids) == len(set(image_ids)), "Duplicate image IDs found"

    # 各アノテーションの id はユニーク
    ann_ids = [ann["id"] for ann in coco["annotations"]]
    assert len(ann_ids) == len(set(ann_ids)), "Duplicate annotation IDs found"

    # JSON シリアライズ可能であることを確認
    json_str = json.dumps(coco, default=str)
    parsed = json.loads(json_str)
    assert parsed == coco
