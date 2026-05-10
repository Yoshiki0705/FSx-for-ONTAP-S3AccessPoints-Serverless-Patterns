#!/usr/bin/env python3
"""Update each UC's demo-guide.md with the verified Step Functions screenshot from 2026-05-10 re-deployment.

Replaces the placeholder status line and adds the screenshot reference.
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

UCS = {
    "UC1":  ("legal-compliance",        "uc1"),
    "UC2":  ("financial-idp",           "uc2"),
    "UC3":  ("manufacturing-analytics", "uc3"),
    "UC5":  ("healthcare-dicom",        "uc5"),
    "UC7":  ("genomics-pipeline",       "uc7"),
    "UC8":  ("energy-seismic",          "uc8"),
    "UC10": ("construction-bim",        "uc10"),
    "UC12": ("logistics-ocr",           "uc12"),
    "UC13": ("education-research",      "uc13"),
}


def update_guide(uc_key: str, dir_name: str, uc_lower: str) -> bool:
    path = PROJECT_ROOT / dir_name / "docs" / "demo-guide.md"
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")

    old_status = "- 📸 **UI/UX 再撮影**: 未実施（本セッションでは UC6/UC11/UC14 を代表として撮影）"
    new_status = (
        f"- 📸 **UI/UX 再撮影**: ✅ 2026-05-10 再デプロイ検証で撮影済み "
        f"（{uc_key} Step Functions グラフ、Lambda 実行成功を確認）"
    )
    if old_status in text:
        text = text.replace(old_status, new_status)

    # Add Step Functions verified screenshot BEFORE the existing "既存スクリーンショット" section
    marker = "### 既存スクリーンショット（Phase 1-6 から該当分）"
    if marker in text:
        insert_block = (
            "### 2026-05-10 再デプロイ検証で撮影（UI/UX 中心）\n\n"
            f"#### {uc_key} Step Functions Graph view（SUCCEEDED）\n\n"
            f"![{uc_key} Step Functions Graph view（SUCCEEDED）]"
            f"(../../docs/screenshots/masked/{uc_lower}-demo/{uc_lower}-stepfunctions-graph.png)\n\n"
            "Step Functions Graph view は各 Lambda / Parallel / Map ステートの実行状況を\n"
            "色で可視化するエンドユーザー最重要画面。\n\n"
        )
        # Only insert if not already present
        if insert_block.split("\n")[0] not in text:
            text = text.replace(marker, insert_block + marker)

    path.write_text(text, encoding="utf-8")
    return True


def main() -> None:
    for uc_key, (dir_name, uc_lower) in UCS.items():
        updated = update_guide(uc_key, dir_name, uc_lower)
        print(f"[{uc_key}] {'UPDATED' if updated else 'MISSING'}: {dir_name}/docs/demo-guide.md")


if __name__ == "__main__":
    main()
