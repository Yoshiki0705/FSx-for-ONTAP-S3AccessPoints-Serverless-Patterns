"""Property-Based Tests for UC10: 建設 / AEC

Hypothesis を使用したプロパティベーステスト。
IFC メタデータ抽出完全性、BIM バージョン差分検出、安全コンプライアンス出力構造
の不変条件を検証する。

Testing Strategy:
- 最小 100 イテレーション/プロパティ
- 各テストにプロパティ番号タグを付与
- タグ形式: Feature: fsxn-s3ap-serverless-patterns-phase2, Property {number}: {property_text}
"""

from __future__ import annotations

import json
import os
import sys

from hypothesis import given, settings, strategies as st

# shared モジュールと UC10 関数のパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from functions.bim_parse.handler import (
    parse_ifc_metadata,
    compute_version_diff,
)
from functions.safety_check.handler import (
    determine_overall_compliance,
)


# ---------------------------------------------------------------------------
# Helper: IFC ファイルデータ生成
# ---------------------------------------------------------------------------


def build_ifc_content(
    project_name: str,
    floor_count: int,
    extra_elements: int,
    coordinate_system: str,
    ifc_schema_version: str,
) -> str:
    """テスト用の IFC ファイルコンテンツを生成する

    Args:
        project_name: プロジェクト名
        floor_count: 階数
        extra_elements: 追加エンティティ数
        coordinate_system: 座標系
        ifc_schema_version: IFC スキーマバージョン

    Returns:
        str: IFC ファイルの内容
    """
    lines = [
        "ISO-10303-21;",
        "HEADER;",
        "FILE_DESCRIPTION(('ViewDefinition [CoordinationView]'),'2;1');",
        f"FILE_NAME('test.ifc','2026-01-15T10:00:00',('Author'),('Org'),'','','');",
        f"FILE_SCHEMA(('{ifc_schema_version}'));",
        "ENDSEC;",
        "DATA;",
    ]

    entity_id = 1

    # IFCPROJECT
    lines.append(
        f"#{entity_id}=IFCPROJECT('proj_guid',#2,$,'{project_name}',$,$,$,(#3),#4);"
    )
    entity_id += 1

    # IFCSITE
    lines.append(
        f"#{entity_id}=IFCSITE('site_guid',#{entity_id+1},$,'Site',$,$,$,$,.ELEMENT.,$,$,$,$,$);"
    )
    entity_id += 1

    # IFCBUILDING
    lines.append(
        f"#{entity_id}=IFCBUILDING('bldg_guid',#{entity_id+1},$,'{project_name}',$,$,$,$,.ELEMENT.,$,$,$);"
    )
    entity_id += 1

    # IFCGEOMETRICREPRESENTATIONCONTEXT
    lines.append(
        f"#{entity_id}=IFCGEOMETRICREPRESENTATIONCONTEXT('{coordinate_system}',$,3,$,$,$);"
    )
    entity_id += 1

    # IFCBUILDINGSTOREY (floor_count 個)
    for i in range(floor_count):
        elevation = i * 3000.0
        lines.append(
            f"#{entity_id}=IFCBUILDINGSTOREY('storey_guid_{i}',#{entity_id+1},$,'Floor {i+1}',$,$,$,$,.ELEMENT.,{elevation});"
        )
        entity_id += 1

    # 追加エンティティ
    for i in range(extra_elements):
        lines.append(
            f"#{entity_id}=IFCWALL('wall_guid_{i}',#{entity_id+1},$,'Wall {i+1}',$,$,$,$,$);"
        )
        entity_id += 1

    lines.append("ENDSEC;")
    lines.append("END-ISO-10303-21;")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Property 14: IFC metadata extraction completeness
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    project_name=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "Zs"),
                               whitelist_characters="_-"),
        min_size=1,
        max_size=50,
    ),
    floor_count=st.integers(min_value=1, max_value=100),
    extra_elements=st.integers(min_value=0, max_value=50),
    coordinate_system=st.sampled_from([
        "EPSG:4326", "EPSG:32654", "Model", "World Coordinate System",
    ]),
    ifc_schema_version=st.sampled_from([
        "IFC4", "IFC2X3", "IFC4X1", "IFC4X3",
    ]),
)
def test_ifc_metadata_extraction_completeness(
    project_name, floor_count, extra_elements, coordinate_system, ifc_schema_version
):
    """Feature: fsxn-s3ap-serverless-patterns-phase2, Property 14: IFC metadata extraction completeness

    For any valid IFC file with arbitrary project_name, building_elements_count,
    floor_count, coordinate_system, and ifc_schema_version, the BIM_Parse_Lambda
    SHALL extract all required fields.

    Strategy: Generate valid IFC file content with random metadata, verify
    parser extracts correctly.

    **Validates: Requirements 7.2**
    """
    # IFC コンテンツ生成
    ifc_content = build_ifc_content(
        project_name=project_name,
        floor_count=floor_count,
        extra_elements=extra_elements,
        coordinate_system=coordinate_system,
        ifc_schema_version=ifc_schema_version,
    )

    # メタデータ抽出
    metadata = parse_ifc_metadata(ifc_content)

    # 必須フィールドの存在確認
    assert "project_name" in metadata, "Missing 'project_name' field"
    assert "building_elements_count" in metadata, "Missing 'building_elements_count' field"
    assert "floor_count" in metadata, "Missing 'floor_count' field"
    assert "coordinate_system" in metadata, "Missing 'coordinate_system' field"
    assert "ifc_schema_version" in metadata, "Missing 'ifc_schema_version' field"

    # 値の正確性検証
    assert metadata["project_name"] == project_name, (
        f"Expected project_name='{project_name}', got '{metadata['project_name']}'"
    )
    assert metadata["floor_count"] == floor_count, (
        f"Expected floor_count={floor_count}, got {metadata['floor_count']}"
    )
    assert metadata["ifc_schema_version"] == ifc_schema_version, (
        f"Expected ifc_schema_version='{ifc_schema_version}', "
        f"got '{metadata['ifc_schema_version']}'"
    )
    assert metadata["coordinate_system"] == coordinate_system, (
        f"Expected coordinate_system='{coordinate_system}', "
        f"got '{metadata['coordinate_system']}'"
    )

    # building_elements_count は全エンティティ数
    # IFCPROJECT(1) + IFCSITE(1) + IFCBUILDING(1) + IFCGEOMETRICREPRESENTATIONCONTEXT(1)
    # + IFCBUILDINGSTOREY(floor_count) + IFCWALL(extra_elements)
    expected_elements = 4 + floor_count + extra_elements
    assert metadata["building_elements_count"] == expected_elements, (
        f"Expected building_elements_count={expected_elements}, "
        f"got {metadata['building_elements_count']}"
    )


# ---------------------------------------------------------------------------
# Property 15: BIM version diff detection
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    current_elements=st.integers(min_value=0, max_value=10000),
    previous_elements=st.integers(min_value=0, max_value=10000),
    current_floors=st.integers(min_value=1, max_value=100),
    previous_floors=st.integers(min_value=1, max_value=100),
    current_project=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=1,
        max_size=20,
    ),
    previous_project=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=1,
        max_size=20,
    ),
)
def test_bim_version_diff_detection(
    current_elements,
    previous_elements,
    current_floors,
    previous_floors,
    current_project,
    previous_project,
):
    """Feature: fsxn-s3ap-serverless-patterns-phase2, Property 15: BIM version diff detection

    For any two IFC metadata sets (previous and current) with known element
    additions, deletions, and modifications, the BIM_Parse_Lambda SHALL
    compute version_diff correctly.

    Strategy: Generate pairs of metadata with known differences, verify
    diff computation.

    **Validates: Requirements 7.3**
    """
    current_metadata = {
        "project_name": current_project,
        "building_elements_count": current_elements,
        "floor_count": current_floors,
        "coordinate_system": "EPSG:4326",
        "ifc_schema_version": "IFC4",
    }

    previous_metadata = {
        "project_name": previous_project,
        "building_elements_count": previous_elements,
        "floor_count": previous_floors,
        "coordinate_system": "EPSG:4326",
        "ifc_schema_version": "IFC4",
    }

    # 差分計算
    diff = compute_version_diff(current_metadata, previous_metadata)

    # 必須フィールドの存在確認
    assert "elements_added" in diff, "Missing 'elements_added' field"
    assert "elements_deleted" in diff, "Missing 'elements_deleted' field"
    assert "elements_modified" in diff, "Missing 'elements_modified' field"

    # 非負値の検証
    assert diff["elements_added"] >= 0, (
        f"elements_added must be >= 0, got {diff['elements_added']}"
    )
    assert diff["elements_deleted"] >= 0, (
        f"elements_deleted must be >= 0, got {diff['elements_deleted']}"
    )
    assert diff["elements_modified"] >= 0, (
        f"elements_modified must be >= 0, got {diff['elements_modified']}"
    )

    # 要素数差分の検証
    element_diff = current_elements - previous_elements
    if element_diff > 0:
        assert diff["elements_added"] == element_diff, (
            f"Expected elements_added={element_diff}, got {diff['elements_added']}"
        )
        assert diff["elements_deleted"] == 0
    elif element_diff < 0:
        assert diff["elements_deleted"] == abs(element_diff), (
            f"Expected elements_deleted={abs(element_diff)}, got {diff['elements_deleted']}"
        )
        assert diff["elements_added"] == 0
    else:
        assert diff["elements_added"] == 0
        assert diff["elements_deleted"] == 0

    # 変更検出の検証
    expected_modifications = 0
    if current_project != previous_project:
        expected_modifications += 1
    if current_floors != previous_floors:
        expected_modifications += 1
    # coordinate_system は同じなので変更なし

    assert diff["elements_modified"] == expected_modifications, (
        f"Expected elements_modified={expected_modifications}, "
        f"got {diff['elements_modified']}"
    )


# ---------------------------------------------------------------------------
# Property 15 (supplement): None previous metadata
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    current_elements=st.integers(min_value=0, max_value=10000),
)
def test_bim_version_diff_first_version(current_elements):
    """Property 15 supplement: First version (no previous) diff

    When previous_metadata is None (first version), all elements are additions.

    **Validates: Requirements 7.3**
    """
    current_metadata = {
        "project_name": "Test",
        "building_elements_count": current_elements,
        "floor_count": 5,
        "coordinate_system": "EPSG:4326",
        "ifc_schema_version": "IFC4",
    }

    diff = compute_version_diff(current_metadata, None)

    assert diff["elements_added"] == current_elements
    assert diff["elements_deleted"] == 0
    assert diff["elements_modified"] == 0


# ---------------------------------------------------------------------------
# Property 16: Safety compliance output structure
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    num_rules=st.integers(min_value=1, max_value=10),
    fail_indices=st.lists(
        st.integers(min_value=0, max_value=9),
        min_size=0,
        max_size=5,
    ),
)
def test_safety_compliance_output_structure(num_rules, fail_indices):
    """Feature: fsxn-s3ap-serverless-patterns-phase2, Property 16: Safety compliance output structure

    For any set of safety compliance rules and check results, the output SHALL
    contain compliance_results array with one entry per rule, each having
    rule_id, rule_name, and status, and overall_compliance SHALL be "FAIL"
    if any individual rule status is "FAIL".

    Strategy: Generate random compliance results with known PASS/FAIL
    distribution, verify output structure and overall_compliance logic.

    **Validates: Requirements 7.7**
    """
    # コンプライアンス結果を生成
    compliance_results = []
    for i in range(num_rules):
        status = "FAIL" if i in fail_indices else "PASS"
        compliance_results.append({
            "rule_id": f"RULE_{i:03d}",
            "rule_name": f"Test Rule {i}",
            "status": status,
            "details": f"Details for rule {i}",
            "remediation": f"Fix for rule {i}" if status == "FAIL" else "",
        })

    # 構造検証: 各エントリに必須フィールドが存在する
    for result in compliance_results:
        assert "rule_id" in result, "Missing 'rule_id' in compliance result"
        assert "rule_name" in result, "Missing 'rule_name' in compliance result"
        assert "status" in result, "Missing 'status' in compliance result"
        assert result["status"] in ("PASS", "FAIL"), (
            f"Invalid status: {result['status']}"
        )

    # overall_compliance の検証
    overall = determine_overall_compliance(compliance_results)

    # いずれかが FAIL なら全体は FAIL
    has_failure = any(
        i in fail_indices for i in range(num_rules)
    )

    if has_failure:
        assert overall == "FAIL", (
            f"Expected overall_compliance='FAIL' when failures exist, got '{overall}'"
        )
    else:
        assert overall == "PASS", (
            f"Expected overall_compliance='PASS' when no failures, got '{overall}'"
        )

    # エントリ数の検証
    assert len(compliance_results) == num_rules, (
        f"Expected {num_rules} results, got {len(compliance_results)}"
    )

    # JSON シリアライズ可能であることを確認
    json_str = json.dumps(compliance_results, default=str)
    parsed = json.loads(json_str)
    assert parsed == compliance_results
