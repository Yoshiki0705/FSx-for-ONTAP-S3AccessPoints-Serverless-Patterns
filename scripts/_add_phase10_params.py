#!/usr/bin/env python3
"""Phase 10 パラメータ一括追加スクリプト.

全 17 UC テンプレートに以下のパラメータを追加:
- TriggerMode (POLLING/EVENT_DRIVEN/HYBRID)
- AlarmProfile (BATCH/REALTIME/HIGH_VOLUME/CUSTOM)
- CustomFailureThreshold
- CustomErrorThreshold
- MaxConcurrencyUpperBound
- OntapApiRateLimit
- EnableCostScheduling
- BusinessHoursStart
- BusinessHoursEnd

Conditions:
- EnablePolling
- EnableEventDriven
- EnableIdempotency
- UseCustomProfile
- EnableCostSchedulingCondition

Mappings:
- AlarmProfileConfig
"""

import re
from pathlib import Path

UC_DIRS = [
    "legal-compliance",
    "financial-idp",
    "manufacturing-analytics",
    "logistics-ocr",
    "healthcare-dicom",
    "semiconductor-eda",
    "genomics-pipeline",
    "energy-seismic",
    "autonomous-driving",
    "construction-bim",
    "retail-catalog",
    "media-vfx",
    "education-research",
    "insurance-claims",
    "defense-satellite",
    "government-archives",
    "smart-city-geospatial",
]

# Default alarm profiles per UC
ALARM_PROFILES = {
    "legal-compliance": "BATCH",
    "financial-idp": "REALTIME",
    "manufacturing-analytics": "BATCH",
    "logistics-ocr": "BATCH",
    "healthcare-dicom": "REALTIME",
    "semiconductor-eda": "HIGH_VOLUME",
    "genomics-pipeline": "HIGH_VOLUME",
    "energy-seismic": "HIGH_VOLUME",
    "autonomous-driving": "REALTIME",
    "construction-bim": "BATCH",
    "retail-catalog": "REALTIME",
    "media-vfx": "HIGH_VOLUME",
    "education-research": "BATCH",
    "insurance-claims": "REALTIME",
    "defense-satellite": "BATCH",
    "government-archives": "BATCH",
    "smart-city-geospatial": "REALTIME",
}

PARAMS_BLOCK = """
  # --- Phase 10: TriggerMode ---
  TriggerMode:
    Type: String
    Default: "POLLING"
    AllowedValues: ["POLLING", "EVENT_DRIVEN", "HYBRID"]
    Description: |
      トリガーモード。POLLING=既存のEventBridge Scheduler+Discovery Lambda、
      EVENT_DRIVEN=FPolicy イベント駆動のみ、HYBRID=両方（冪等性ストアで重複排除）。

  # --- Phase 10: AlarmProfile ---
  AlarmProfile:
    Type: String
    Default: "{alarm_profile}"
    AllowedValues: ["BATCH", "REALTIME", "HIGH_VOLUME", "CUSTOM"]
    Description: |
      アラーム閾値プロファイル。BATCH=定期バッチ向け（緩い閾値）、
      REALTIME=リアルタイム向け（厳しい閾値）、HIGH_VOLUME=大量処理向け、
      CUSTOM=CustomFailureThreshold/CustomErrorThreshold で個別指定。

  CustomFailureThreshold:
    Type: Number
    Default: 10
    MinValue: 1
    MaxValue: 100
    Description: CUSTOM プロファイル時の Step Functions 失敗率閾値（%）

  CustomErrorThreshold:
    Type: Number
    Default: 3
    MinValue: 1
    MaxValue: 100
    Description: CUSTOM プロファイル時の Discovery Lambda エラー閾値（回/時間）

  # --- Phase 10: MaxConcurrency ---
  MaxConcurrencyUpperBound:
    Type: Number
    Default: 40
    MinValue: 1
    MaxValue: 1000
    Description: Step Functions Map State の MaxConcurrency 上限値

  OntapApiRateLimit:
    Type: Number
    Default: 100
    MinValue: 1
    MaxValue: 10000
    Description: ONTAP API の秒間リクエスト上限（MaxConcurrency 算出に使用）

  # --- Phase 10: CostScheduling ---
  EnableCostScheduling:
    Type: String
    Default: "false"
    AllowedValues: ["true", "false"]
    Description: 営業時間ベースのスケジュール動的変更を有効化

  BusinessHoursStart:
    Type: Number
    Default: 9
    MinValue: 0
    MaxValue: 23
    Description: 営業時間開始（時、JST）

  BusinessHoursEnd:
    Type: Number
    Default: 18
    MinValue: 0
    MaxValue: 23
    Description: 営業時間終了（時、JST）
"""

CONDITIONS_BLOCK = """
  # --- Phase 10 Conditions ---
  EnablePolling: !Or
    - !Equals [!Ref TriggerMode, "POLLING"]
    - !Equals [!Ref TriggerMode, "HYBRID"]
  EnableEventDriven: !Or
    - !Equals [!Ref TriggerMode, "EVENT_DRIVEN"]
    - !Equals [!Ref TriggerMode, "HYBRID"]
  EnableIdempotency: !Equals [!Ref TriggerMode, "HYBRID"]
  UseCustomProfile: !Equals [!Ref AlarmProfile, "CUSTOM"]
  EnableCostSchedulingCondition: !Equals [!Ref EnableCostScheduling, "true"]
"""

MAPPINGS_BLOCK = """
# --- Phase 10 Mappings ---
Mappings:
  AlarmProfileConfig:
    BATCH:
      FailureThreshold: "10"
      ErrorThreshold: "3"
      EvaluationPeriods: "3"
    REALTIME:
      FailureThreshold: "5"
      ErrorThreshold: "1"
      EvaluationPeriods: "1"
    HIGH_VOLUME:
      FailureThreshold: "15"
      ErrorThreshold: "5"
      EvaluationPeriods: "5"
    CUSTOM:
      FailureThreshold: "10"
      ErrorThreshold: "3"
      EvaluationPeriods: "3"
"""


def add_params_to_template(template_path: Path, uc_name: str) -> bool:
    """テンプレートに Phase 10 パラメータを追加."""
    content = template_path.read_text(encoding="utf-8")

    # Skip if already has Phase 10 params
    if "TriggerMode:" in content:
        print(f"  SKIP (already has TriggerMode): {uc_name}")
        return False

    alarm_profile = ALARM_PROFILES.get(uc_name, "BATCH")
    params_to_add = PARAMS_BLOCK.replace("{alarm_profile}", alarm_profile)

    # Find the end of Parameters section (before Conditions)
    # Look for the Conditions: line
    conditions_match = re.search(r"^Conditions:", content, re.MULTILINE)
    if not conditions_match:
        print(f"  ERROR (no Conditions section): {uc_name}")
        return False

    # Insert params before Conditions
    insert_pos = conditions_match.start()
    content = content[:insert_pos] + params_to_add + "\n" + content[insert_pos:]

    # Add Phase 10 Conditions after existing Conditions
    # Find the first resource or mapping after Conditions
    conditions_end = content.find("Conditions:", insert_pos + len(params_to_add))
    if conditions_end == -1:
        conditions_end = content.find("Conditions:")

    # Find the next top-level section after Conditions
    # Look for lines that start with a letter and end with ':'
    after_conditions = content[conditions_end:]
    # Find all condition entries and insert after the last one
    # Simple approach: find "Resources:" or "Mappings:" after Conditions
    resources_match = re.search(r"^Resources:", after_conditions, re.MULTILINE)
    mappings_match = re.search(r"^Mappings:", after_conditions, re.MULTILINE)

    if resources_match and (not mappings_match or resources_match.start() < mappings_match.start()):
        # Insert conditions before Resources
        abs_pos = conditions_end + resources_match.start()
        content = content[:abs_pos] + CONDITIONS_BLOCK + "\n" + content[abs_pos:]
    elif mappings_match:
        abs_pos = conditions_end + mappings_match.start()
        content = content[:abs_pos] + CONDITIONS_BLOCK + "\n" + content[abs_pos:]

    # Add Mappings if not already present
    if "AlarmProfileConfig:" not in content:
        # Find Resources: section and insert Mappings before it
        resources_pos = content.find("\nResources:")
        if resources_pos != -1:
            content = content[:resources_pos] + "\n" + MAPPINGS_BLOCK + content[resources_pos:]

    template_path.write_text(content, encoding="utf-8")
    print(f"  DONE: {uc_name} (AlarmProfile={alarm_profile})")
    return True


def main():
    project_root = Path(__file__).parent.parent
    modified = 0

    print("Phase 10: Adding TriggerMode, AlarmProfile, MaxConcurrency, CostScheduling params")
    print("=" * 70)

    for uc_dir in UC_DIRS:
        template_path = project_root / uc_dir / "template-deploy.yaml"
        if not template_path.exists():
            print(f"  MISSING: {uc_dir}/template-deploy.yaml")
            continue

        if add_params_to_template(template_path, uc_dir):
            modified += 1

    print(f"\n{'=' * 70}")
    print(f"Modified: {modified}/{len(UC_DIRS)} templates")


if __name__ == "__main__":
    main()
