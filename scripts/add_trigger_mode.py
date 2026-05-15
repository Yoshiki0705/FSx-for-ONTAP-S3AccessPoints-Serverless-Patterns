#!/usr/bin/env python3
"""
Phase 11 Req 1: TriggerMode 全 17 UC 統合スクリプト

legal-compliance/template.yaml の参照実装を残り 16 UC テンプレートに展開する。
各 UC の template.yaml に以下を追加:
1. Parameters: TriggerMode + FPolicyEventBusName
2. Conditions: IsPolling, IsEventDriven, IsHybrid, IsPollingOrHybrid, IsEventDrivenOrHybrid
3. 既存の EventBridge Scheduler リソースに Condition: IsPollingOrHybrid を追加
"""

import re
import sys
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).parent.parent

# UCs to update (excluding legal-compliance which already has it, and event-driven-fpolicy which is infra)
UC_DIRS = [
    "financial-idp",
    "manufacturing-analytics",
    "media-vfx",
    "healthcare-dicom",
    "insurance-claims",
    "construction-bim",
    "genomics-pipeline",
    "logistics-ocr",
    "retail-catalog",
    "autonomous-driving",
    "semiconductor-eda",
    "energy-seismic",
    "education-research",
    "defense-satellite",
    "government-archives",
    "smart-city-geospatial",
]

# TriggerMode parameters snippet (to be inserted before Conditions section)
TRIGGER_MODE_PARAMS = """
  # --- TriggerMode (Phase 11 Req 1) ---
  TriggerMode:
    Type: String
    Default: "POLLING"
    AllowedValues: ["POLLING", "EVENT_DRIVEN", "HYBRID"]
    Description: >
      トリガーモードの選択。
      POLLING: 既存の EventBridge Scheduler + Discovery Lambda（デフォルト）。
      EVENT_DRIVEN: FPolicy イベント駆動のみ（Scheduler 無効化）。
      HYBRID: 両方有効（Idempotency Store で重複排除）。

  FPolicyEventBusName:
    Type: String
    Default: "fsxn-fpolicy-events"
    Description: FPolicy EventBridge カスタムバス名（EVENT_DRIVEN / HYBRID 時に使用）
"""

# TriggerMode conditions snippet (to be inserted at end of Conditions section)
TRIGGER_MODE_CONDITIONS = """  # TriggerMode Conditions
  IsPolling:
    !Equals [!Ref TriggerMode, "POLLING"]
  IsEventDriven:
    !Equals [!Ref TriggerMode, "EVENT_DRIVEN"]
  IsHybrid:
    !Equals [!Ref TriggerMode, "HYBRID"]
  IsPollingOrHybrid:
    !Or
      - !Condition IsPolling
      - !Condition IsHybrid
  IsEventDrivenOrHybrid:
    !Or
      - !Condition IsEventDriven
      - !Condition IsHybrid
"""


def add_trigger_mode_to_simple_template(template_path: Path) -> dict:
    """Add TriggerMode to simplified SAM-local-only templates (no Conditions/Scheduler).

    These templates (defense-satellite, government-archives, smart-city-geospatial)
    have minimal structure. We add Parameters + Conditions before Resources.
    """
    content = template_path.read_text()
    changes = []

    # Check if already has TriggerMode
    if "TriggerMode:" in content and "IsPollingOrHybrid" in content:
        return {"path": str(template_path), "status": "skipped", "reason": "already has TriggerMode"}

    # For simple templates: add TriggerMode params to existing Parameters section
    # and add a Conditions section before Resources
    params_to_add = """  # --- TriggerMode (Phase 11 Req 1) ---
  TriggerMode:
    Type: String
    Default: "POLLING"
    AllowedValues: ["POLLING", "EVENT_DRIVEN", "HYBRID"]
    Description: >
      トリガーモードの選択。
      POLLING: 既存の EventBridge Scheduler + Discovery Lambda（デフォルト）。
      EVENT_DRIVEN: FPolicy イベント駆動のみ（Scheduler 無効化）。
      HYBRID: 両方有効（Idempotency Store で重複排除）。
  FPolicyEventBusName:
    Type: String
    Default: "fsxn-fpolicy-events"
    Description: FPolicy EventBridge カスタムバス名（EVENT_DRIVEN / HYBRID 時に使用）

"""

    conditions_section = """# =====================================================================
# Conditions
# =====================================================================
Conditions:
  # TriggerMode Conditions
  IsPolling:
    !Equals [!Ref TriggerMode, "POLLING"]
  IsEventDriven:
    !Equals [!Ref TriggerMode, "EVENT_DRIVEN"]
  IsHybrid:
    !Equals [!Ref TriggerMode, "HYBRID"]
  IsPollingOrHybrid:
    !Or
      - !Condition IsPolling
      - !Condition IsHybrid
  IsEventDrivenOrHybrid:
    !Or
      - !Condition IsEventDriven
      - !Condition IsHybrid

"""

    # Find Resources: section and insert params before it, conditions before it
    resources_match = re.search(r"^Resources:", content, re.MULTILINE)
    if not resources_match:
        return {"path": str(template_path), "status": "error", "reason": "could not find Resources section"}

    # Insert TriggerMode params at end of Parameters section (before Resources)
    # Find the last parameter entry before Resources
    insert_pos = resources_match.start()
    content = content[:insert_pos] + params_to_add + conditions_section + content[insert_pos:]
    changes.append("added TriggerMode + FPolicyEventBusName parameters")
    changes.append("added Conditions section with TriggerMode conditions")
    changes.append("NOTE: no EventBridge Scheduler in this simplified template (SAM local only)")

    template_path.write_text(content)
    return {"path": str(template_path), "status": "updated", "changes": changes}


def add_trigger_mode_to_template(template_path: Path) -> dict:
    """Add TriggerMode parameters and conditions to a UC template.

    Returns dict with status info.
    """
    content = template_path.read_text()
    original = content
    changes = []

    # 1. Check if already has TriggerMode
    if "TriggerMode:" in content and "IsPollingOrHybrid" in content:
        return {"path": str(template_path), "status": "skipped", "reason": "already has TriggerMode"}

    # 2. Check if this is a simplified template (no Conditions section)
    has_conditions = bool(re.search(r"^Conditions:", content, re.MULTILINE))
    has_full_structure = "# =====" in content  # Full templates have section dividers

    if not has_conditions and not has_full_structure:
        return add_trigger_mode_to_simple_template(template_path)

    # 2. Add TriggerMode parameters before Conditions section
    # Find the line "# ====...Conditions..." or "Conditions:" section header
    conditions_header_pattern = re.compile(
        r"(# =+\n# Conditions\n# =+\nConditions:)",
        re.MULTILINE,
    )
    match = conditions_header_pattern.search(content)
    if not match:
        # Try simpler pattern
        conditions_header_pattern = re.compile(r"^(Conditions:)", re.MULTILINE)
        match = conditions_header_pattern.search(content)

    if match:
        # Insert parameters before the Conditions section header
        insert_pos = match.start()
        content = content[:insert_pos] + TRIGGER_MODE_PARAMS + "\n" + content[insert_pos:]
        changes.append("added TriggerMode + FPolicyEventBusName parameters")
    else:
        return {"path": str(template_path), "status": "error", "reason": "could not find Conditions section"}

    # 3. Add TriggerMode conditions at end of Conditions section
    # Find the Resources section header to know where Conditions end
    resources_header_pattern = re.compile(
        r"(# =+\n# Resources\n# =+\nResources:)",
        re.MULTILINE,
    )
    match = resources_header_pattern.search(content)
    if not match:
        resources_header_pattern = re.compile(r"^(Resources:)", re.MULTILINE)
        match = resources_header_pattern.search(content)

    if match:
        # Insert conditions just before Resources section
        insert_pos = match.start()
        content = content[:insert_pos] + TRIGGER_MODE_CONDITIONS + content[insert_pos:]
        changes.append("added TriggerMode conditions (IsPolling, IsEventDriven, IsHybrid, IsPollingOrHybrid, IsEventDrivenOrHybrid)")
    else:
        return {"path": str(template_path), "status": "error", "reason": "could not find Resources section"}

    # 4. Add Condition: IsPollingOrHybrid to EventBridge Scheduler resource
    # Pattern: find "Type: AWS::Scheduler::Schedule" and add Condition before Properties
    scheduler_pattern = re.compile(
        r"(  \w+Schedule(?:r)?:\n    Type: AWS::Scheduler::Schedule\n)(    Properties:)",
        re.MULTILINE,
    )
    scheduler_match = scheduler_pattern.search(content)
    if scheduler_match:
        # Insert Condition line between Type and Properties
        replacement = scheduler_match.group(1) + "    Condition: IsPollingOrHybrid\n" + scheduler_match.group(2)
        content = content[:scheduler_match.start()] + replacement + content[scheduler_match.end():]
        changes.append("added Condition: IsPollingOrHybrid to EventBridge Scheduler")
    else:
        # Try alternate pattern where resource name varies
        scheduler_pattern2 = re.compile(
            r"(  \w+:\n    Type: AWS::Scheduler::Schedule\n)(    Properties:)",
            re.MULTILINE,
        )
        scheduler_match2 = scheduler_pattern2.search(content)
        if scheduler_match2:
            replacement = scheduler_match2.group(1) + "    Condition: IsPollingOrHybrid\n" + scheduler_match2.group(2)
            content = content[:scheduler_match2.start()] + replacement + content[scheduler_match2.end():]
            changes.append("added Condition: IsPollingOrHybrid to EventBridge Scheduler")
        else:
            changes.append("WARNING: no EventBridge Scheduler found (may be expected for some UCs)")

    # Write back
    template_path.write_text(content)

    return {"path": str(template_path), "status": "updated", "changes": changes}


def main():
    results = []
    for uc_dir in UC_DIRS:
        template_path = PROJECT_ROOT / uc_dir / "template.yaml"
        if not template_path.exists():
            results.append({"path": str(template_path), "status": "error", "reason": "file not found"})
            continue
        result = add_trigger_mode_to_template(template_path)
        results.append(result)

    # Print results
    print("=" * 70)
    print("TriggerMode Integration Results")
    print("=" * 70)
    for r in results:
        status = r["status"]
        path = r["path"]
        if status == "updated":
            print(f"  ✅ {path}")
            for c in r.get("changes", []):
                print(f"     - {c}")
        elif status == "skipped":
            print(f"  ⏭️  {path} ({r.get('reason', '')})")
        else:
            print(f"  ❌ {path} ({r.get('reason', '')})")
    print("=" * 70)

    updated = sum(1 for r in results if r["status"] == "updated")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    errors = sum(1 for r in results if r["status"] == "error")
    print(f"Summary: {updated} updated, {skipped} skipped, {errors} errors")

    if errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
