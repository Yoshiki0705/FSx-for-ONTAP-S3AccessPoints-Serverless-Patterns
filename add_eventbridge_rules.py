#!/usr/bin/env python3
"""Add EventBridge Step Functions failure notification rule + SNS Topic Policy to 16 UC templates."""

import re
from pathlib import Path

# UC directory -> State Machine logical name mapping
UC_STATE_MACHINES = {
    "financial-idp": "IdpStateMachine",
    "manufacturing-analytics": "ManufacturingStateMachine",
    "media-vfx": "VfxStateMachine",
    "healthcare-dicom": "DicomStateMachine",
    "semiconductor-eda": "EdaStateMachine",
    "genomics-pipeline": "GenomicsStateMachine",
    "energy-seismic": "SeismicStateMachine",
    "autonomous-driving": "AutonomousDrivingStateMachine",
    "construction-bim": "ConstructionBimStateMachine",
    "retail-catalog": "RetailCatalogStateMachine",
    "logistics-ocr": "LogisticsOcrStateMachine",
    "education-research": "EducationResearchStateMachine",
    "insurance-claims": "InsuranceClaimsStateMachine",
    "defense-satellite": "DefenseSatelliteStateMachine",
    "government-archives": "ArchiveProcessingStateMachine",
    "smart-city-geospatial": "SmartCityStateMachine",
}

BLOCK_TEMPLATE = '''
  # EventBridge rule: notify on Step Functions execution failure/timeout/abort
  StepFunctionsFailureEventRule:
    Type: AWS::Events::Rule
    Condition: CreateCloudWatchAlarms
    Properties:
      Description: !Sub "Notify on ${{AWS::StackName}} Step Functions execution failures"
      EventPattern:
        source:
          - aws.states
        detail-type:
          - "Step Functions Execution Status Change"
        detail:
          status:
            - FAILED
            - TIMED_OUT
            - ABORTED
          stateMachineArn:
            - !Ref {state_machine}
      Targets:
        - Arn: !Ref NotificationTopic
          Id: SnsFailureTarget
          InputTransformer:
            InputPathsMap:
              execName: $.detail.name
              execStatus: $.detail.status
              execArn: $.detail.executionArn
            InputTemplate: '"Step Functions execution <execName> finished with status <execStatus>. ARN: <execArn>"'

  # Allow EventBridge to publish to SNS topic
  EventBridgeToSnsPolicy:
    Type: AWS::SNS::TopicPolicy
    Condition: CreateCloudWatchAlarms
    Properties:
      PolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Sid: AllowEventBridgePublish
            Effect: Allow
            Principal:
              Service: events.amazonaws.com
            Action: sns:Publish
            Resource: !Ref NotificationTopic
            Condition:
              ArnLike:
                aws:SourceArn: !GetAtt StepFunctionsFailureEventRule.Arn
      Topics:
        - !Ref NotificationTopic
'''


def add_eventbridge_block(uc_dir: str, state_machine: str) -> None:
    template_path = Path(uc_dir) / "template-deploy.yaml"
    if not template_path.exists():
        print(f"  ERROR: {template_path} not found")
        return

    content = template_path.read_text()

    # Check if already present
    if "StepFunctionsFailureEventRule" in content:
        print(f"  SKIP: {uc_dir} already has StepFunctionsFailureEventRule")
        return

    block = BLOCK_TEMPLATE.format(state_machine=state_machine)

    # Find the Outputs section to insert before it
    # Look for patterns like "Outputs:" or "# Outputs" followed by "Outputs:"
    outputs_pattern = re.compile(r'^(# =+\n# Outputs\n# =+\n)?Outputs:', re.MULTILINE)
    match = outputs_pattern.search(content)

    if match:
        # Insert before the Outputs section (including any comment header)
        insert_pos = match.start()
        new_content = content[:insert_pos] + block + "\n" + content[insert_pos:]
    else:
        # No Outputs section - append at end of file
        new_content = content.rstrip() + "\n" + block + "\n"

    template_path.write_text(new_content)
    print(f"  OK: {uc_dir} - inserted before {'Outputs' if match else 'end of file'}")


def main():
    base = Path(".")
    for uc_dir, state_machine in UC_STATE_MACHINES.items():
        print(f"Processing {uc_dir}...")
        add_eventbridge_block(uc_dir, state_machine)


if __name__ == "__main__":
    main()
