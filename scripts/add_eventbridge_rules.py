#!/usr/bin/env python3
"""
Phase 11 Req 2: UC 別 EventBridge ディスパッチルール追加スクリプト

各 UC テンプレートに FPolicy EventBridge Rule + IAM Role を追加する。
- EventBridge Rule: fsxn-fpolicy-events バスからイベントを受信
- ファイルパスプレフィックス/拡張子でフィルタリング
- Condition: IsEventDrivenOrHybrid で制御
- ターゲット: UC の Step Functions StateMachine
"""

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# UC routing configuration
# Each UC has: (dir_name, state_machine_ref, prefixes, suffixes, operations)
UC_ROUTING = [
    {
        "dir": "legal-compliance",
        "state_machine": "ComplianceStateMachine",
        "rule_name": "FPolicyComplianceRule",
        "role_name": "FPolicyEventRuleRole",
        "prefixes": ["/legal/", "/compliance/", "/audit/"],
        "suffixes": [".pdf", ".docx", ".xlsx"],
        "operations": ["create", "write", "rename", "delete"],
    },
    {
        "dir": "financial-idp",
        "state_machine": "IdpStateMachine",
        "rule_name": "FPolicyIdpRule",
        "role_name": "FPolicyEventRuleRole",
        "prefixes": ["/finance/", "/invoices/", "/contracts/"],
        "suffixes": [".pdf", ".tiff", ".png", ".jpg"],
        "operations": ["create", "write"],
    },
    {
        "dir": "manufacturing-analytics",
        "state_machine": "ManufacturingStateMachine",
        "rule_name": "FPolicyManufacturingRule",
        "role_name": "FPolicyEventRuleRole",
        "prefixes": ["/manufacturing/", "/iot/", "/sensors/"],
        "suffixes": [".csv", ".json", ".parquet"],
        "operations": ["create", "write"],
    },
    {
        "dir": "media-vfx",
        "state_machine": "VfxStateMachine",
        "rule_name": "FPolicyVfxRule",
        "role_name": "FPolicyEventRuleRole",
        "prefixes": ["/media/", "/vfx/", "/renders/"],
        "suffixes": [".exr", ".dpx", ".mov", ".mp4"],
        "operations": ["create", "write", "rename"],
    },
    {
        "dir": "healthcare-dicom",
        "state_machine": "DicomStateMachine",
        "rule_name": "FPolicyDicomRule",
        "role_name": "FPolicyEventRuleRole",
        "prefixes": ["/healthcare/", "/dicom/", "/medical/"],
        "suffixes": [".dcm", ".dicom"],
        "operations": ["create", "write"],
    },
    {
        "dir": "insurance-claims",
        "state_machine": "InsuranceClaimsStateMachine",
        "rule_name": "FPolicyInsuranceRule",
        "role_name": "FPolicyEventRuleRole",
        "prefixes": ["/insurance/", "/claims/"],
        "suffixes": [".pdf", ".jpg", ".png", ".tiff"],
        "operations": ["create", "write"],
    },
    {
        "dir": "construction-bim",
        "state_machine": "ConstructionBimStateMachine",
        "rule_name": "FPolicyBimRule",
        "role_name": "FPolicyEventRuleRole",
        "prefixes": ["/construction/", "/bim/", "/cad/"],
        "suffixes": [".ifc", ".rvt", ".dwg", ".nwd"],
        "operations": ["create", "write", "rename"],
    },
    {
        "dir": "genomics-pipeline",
        "state_machine": "GenomicsStateMachine",
        "rule_name": "FPolicyGenomicsRule",
        "role_name": "FPolicyEventRuleRole",
        "prefixes": ["/genomics/", "/sequencing/"],
        "suffixes": [".fastq", ".bam", ".vcf", ".fasta"],
        "operations": ["create", "write"],
    },
    {
        "dir": "logistics-ocr",
        "state_machine": "LogisticsOcrStateMachine",
        "rule_name": "FPolicyLogisticsRule",
        "role_name": "FPolicyEventRuleRole",
        "prefixes": ["/logistics/", "/shipping/", "/warehouse/"],
        "suffixes": [".pdf", ".jpg", ".png", ".tiff"],
        "operations": ["create", "write"],
    },
    {
        "dir": "retail-catalog",
        "state_machine": "RetailCatalogStateMachine",
        "rule_name": "FPolicyRetailRule",
        "role_name": "FPolicyEventRuleRole",
        "prefixes": ["/retail/", "/catalog/", "/products/"],
        "suffixes": [".jpg", ".png", ".csv", ".json"],
        "operations": ["create", "write", "rename"],
    },
    {
        "dir": "autonomous-driving",
        "state_machine": "AutonomousDrivingStateMachine",
        "rule_name": "FPolicyAutonomousRule",
        "role_name": "FPolicyEventRuleRole",
        "prefixes": ["/autonomous/", "/lidar/", "/camera/"],
        "suffixes": [".pcd", ".bag", ".mp4", ".json"],
        "operations": ["create", "write"],
    },
    {
        "dir": "semiconductor-eda",
        "state_machine": "EdaStateMachine",
        "rule_name": "FPolicyEdaRule",
        "role_name": "FPolicyEventRuleRole",
        "prefixes": ["/eda/", "/design/", "/simulation/"],
        "suffixes": [".gds", ".oasis", ".spice", ".lib"],
        "operations": ["create", "write", "rename"],
    },
    {
        "dir": "energy-seismic",
        "state_machine": "SeismicStateMachine",
        "rule_name": "FPolicySeismicRule",
        "role_name": "FPolicyEventRuleRole",
        "prefixes": ["/energy/", "/seismic/", "/survey/"],
        "suffixes": [".segy", ".sgy", ".las", ".json"],
        "operations": ["create", "write"],
    },
    {
        "dir": "education-research",
        "state_machine": "EducationResearchStateMachine",
        "rule_name": "FPolicyEducationRule",
        "role_name": "FPolicyEventRuleRole",
        "prefixes": ["/education/", "/research/", "/papers/"],
        "suffixes": [".pdf", ".tex", ".docx", ".ipynb"],
        "operations": ["create", "write", "rename"],
    },
    {
        "dir": "defense-satellite",
        "state_machine": None,  # Simplified template — no StateMachine
        "target_function": "DiscoveryFunction",
        "rule_name": "FPolicySatelliteRule",
        "role_name": "FPolicyEventRuleRole",
        "prefixes": ["/defense/", "/satellite/", "/imagery/"],
        "suffixes": [".tiff", ".nitf", ".jp2", ".geotiff"],
        "operations": ["create", "write"],
    },
    {
        "dir": "government-archives",
        "state_machine": None,  # Simplified template — no StateMachine
        "target_function": "DiscoveryFunction",
        "rule_name": "FPolicyArchivesRule",
        "role_name": "FPolicyEventRuleRole",
        "prefixes": ["/government/", "/archives/", "/records/"],
        "suffixes": [".pdf", ".tiff", ".xml"],
        "operations": ["create", "write", "rename", "delete"],
    },
    {
        "dir": "smart-city-geospatial",
        "state_machine": None,  # Simplified template — no StateMachine
        "target_function": "DiscoveryFunction",
        "rule_name": "FPolicySmartCityRule",
        "role_name": "FPolicyEventRuleRole",
        "prefixes": ["/smartcity/", "/geospatial/", "/gis/"],
        "suffixes": [".geojson", ".shp", ".tiff", ".las"],
        "operations": ["create", "write"],
    },
]


def generate_event_pattern(prefixes, suffixes, operations):
    """Generate EventBridge event pattern YAML."""
    ops_yaml = "\n".join(f'              - "{op}"' for op in operations)
    prefix_yaml = "\n".join(f'              - prefix: "{p}"' for p in prefixes)
    suffix_yaml = "\n".join(f'              - suffix: "{s}"' for s in suffixes)

    return f"""        source:
          - "fsxn.fpolicy"
        detail-type:
          - "FPolicy File Operation"
        detail:
          operation_type:
{ops_yaml}
          file_path:
{prefix_yaml}
{suffix_yaml}"""


def generate_sfn_rule_resources(uc):
    """Generate EventBridge Rule + IAM Role for Step Functions target."""
    event_pattern = generate_event_pattern(
        uc["prefixes"], uc["suffixes"], uc["operations"]
    )
    state_machine = uc["state_machine"]

    return f"""
  # -----------------------------------------------------------------
  # FPolicy EventBridge Rule (EVENT_DRIVEN / HYBRID)
  # -----------------------------------------------------------------
  {uc["role_name"]}:
    Type: AWS::IAM::Role
    Condition: IsEventDrivenOrHybrid
    Properties:
      RoleName: !Sub "${{AWS::StackName}}-fpolicy-rule-role"
      AssumeRolePolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Effect: Allow
            Principal:
              Service: events.amazonaws.com
            Action: sts:AssumeRole
      Policies:
        - PolicyName: InvokeStepFunctions
          PolicyDocument:
            Version: "2012-10-17"
            Statement:
              - Effect: Allow
                Action:
                  - states:StartExecution
                Resource:
                  - !Ref {state_machine}

  {uc["rule_name"]}:
    Type: AWS::Events::Rule
    Condition: IsEventDrivenOrHybrid
    Properties:
      Name: !Sub "${{AWS::StackName}}-fpolicy-trigger"
      EventBusName: !Ref FPolicyEventBusName
      EventPattern:
{event_pattern}
      State: ENABLED
      Targets:
        - Id: step-functions-target
          Arn: !Ref {state_machine}
          RoleArn: !GetAtt {uc["role_name"]}.Arn
"""


def generate_lambda_rule_resources(uc):
    """Generate EventBridge Rule + IAM Role for Lambda target (simplified templates)."""
    event_pattern = generate_event_pattern(
        uc["prefixes"], uc["suffixes"], uc["operations"]
    )
    target_function = uc["target_function"]

    return f"""
  # -----------------------------------------------------------------
  # FPolicy EventBridge Rule (EVENT_DRIVEN / HYBRID)
  # -----------------------------------------------------------------
  {uc["role_name"]}:
    Type: AWS::IAM::Role
    Condition: IsEventDrivenOrHybrid
    Properties:
      RoleName: !Sub "${{AWS::StackName}}-fpolicy-rule-role"
      AssumeRolePolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Effect: Allow
            Principal:
              Service: events.amazonaws.com
            Action: sts:AssumeRole
      Policies:
        - PolicyName: InvokeLambda
          PolicyDocument:
            Version: "2012-10-17"
            Statement:
              - Effect: Allow
                Action:
                  - lambda:InvokeFunction
                Resource:
                  - !GetAtt {target_function}.Arn

  {uc["rule_name"]}:
    Type: AWS::Events::Rule
    Condition: IsEventDrivenOrHybrid
    Properties:
      Name: !Sub "${{AWS::StackName}}-fpolicy-trigger"
      EventBusName: !Ref FPolicyEventBusName
      EventPattern:
{event_pattern}
      State: ENABLED
      Targets:
        - Id: lambda-target
          Arn: !GetAtt {target_function}.Arn

  FPolicyLambdaPermission:
    Type: AWS::Lambda::Permission
    Condition: IsEventDrivenOrHybrid
    Properties:
      FunctionName: !Ref {target_function}
      Action: lambda:InvokeFunction
      Principal: events.amazonaws.com
      SourceArn: !GetAtt {uc["rule_name"]}.Arn
"""


def add_eventbridge_rule(uc):
    """Add EventBridge Rule resources to a UC template."""
    template_path = PROJECT_ROOT / uc["dir"] / "template.yaml"
    if not template_path.exists():
        return {"path": str(template_path), "status": "error", "reason": "file not found"}

    content = template_path.read_text()

    # Check if already has FPolicy rule
    if uc["rule_name"] in content or "fpolicy-trigger" in content:
        return {"path": str(template_path), "status": "skipped", "reason": "already has FPolicy EventBridge Rule"}

    # Generate the resources
    if uc["state_machine"]:
        resources = generate_sfn_rule_resources(uc)
    else:
        resources = generate_lambda_rule_resources(uc)

    # Find the right insertion point — before Outputs section or at end of file
    outputs_match = re.search(r"^# =+\n# Outputs\n# =+\nOutputs:", content, re.MULTILINE)
    if not outputs_match:
        outputs_match = re.search(r"^Outputs:", content, re.MULTILINE)

    if outputs_match:
        # Insert before Outputs
        insert_pos = outputs_match.start()
        content = content[:insert_pos] + resources + "\n" + content[insert_pos:]
    else:
        # Append at end of file
        content = content.rstrip() + "\n" + resources

    template_path.write_text(content)
    return {"path": str(template_path), "status": "updated", "changes": [
        f"added {uc['rule_name']} (EventBridge Rule)",
        f"added {uc['role_name']} (IAM Role for EventBridge)",
        f"filters: prefixes={uc['prefixes']}, suffixes={uc['suffixes']}",
        f"operations: {uc['operations']}",
    ]}


def main():
    results = []
    for uc in UC_ROUTING:
        result = add_eventbridge_rule(uc)
        results.append(result)

    print("=" * 70)
    print("UC EventBridge Dispatch Rule Results")
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
