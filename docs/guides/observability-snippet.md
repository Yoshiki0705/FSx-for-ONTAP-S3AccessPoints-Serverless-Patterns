# Observability テンプレートスニペット（Phase 9 Theme A）

各 UC の `template-deploy.yaml` に追加するスニペット。
UC 固有の `!Ref` 名を置換して使用する。

---

## 1. Parameters セクションに追加

```yaml
  EnableCloudWatchAlarms:
    Type: String
    Default: "false"
    AllowedValues: ["true", "false"]
    Description: CloudWatch Alarms + EventBridge failure notifications を有効化する
```

## 2. Conditions セクションに追加

```yaml
  CreateCloudWatchAlarms:
    !Equals [!Ref EnableCloudWatchAlarms, "true"]
```

## 3. Resources セクションに追加（Outputs の直前）

以下の `<STATE_MACHINE_REF>` と `<DISCOVERY_FUNCTION_REF>` を UC 固有の論理名に置換:

```yaml
  # -----------------------------------------------------------------
  # CloudWatch Alarms (conditional on CreateCloudWatchAlarms)
  # -----------------------------------------------------------------
  StepFunctionsFailureAlarm:
    Type: AWS::CloudWatch::Alarm
    Condition: CreateCloudWatchAlarms
    Properties:
      AlarmName: !Sub "${AWS::StackName}-sfn-failures"
      AlarmDescription: Step Functions execution failures
      Namespace: AWS/States
      MetricName: ExecutionsFailed
      Dimensions:
        - Name: StateMachineArn
          Value: !Ref <STATE_MACHINE_REF>
      Statistic: Sum
      Period: 300
      EvaluationPeriods: 1
      Threshold: 1
      ComparisonOperator: GreaterThanOrEqualToThreshold
      TreatMissingData: notBreaching
      AlarmActions:
        - !Ref NotificationTopic

  DiscoveryErrorAlarm:
    Type: AWS::CloudWatch::Alarm
    Condition: CreateCloudWatchAlarms
    Properties:
      AlarmName: !Sub "${AWS::StackName}-discovery-errors"
      AlarmDescription: Discovery Lambda error rate
      Namespace: AWS/Lambda
      MetricName: Errors
      Dimensions:
        - Name: FunctionName
          Value: !Ref <DISCOVERY_FUNCTION_REF>
      Statistic: Sum
      Period: 300
      EvaluationPeriods: 1
      Threshold: 3
      ComparisonOperator: GreaterThanOrEqualToThreshold
      TreatMissingData: notBreaching
      AlarmActions:
        - !Ref NotificationTopic

  # EventBridge rule: notify on Step Functions execution failure/timeout/abort
  StepFunctionsFailureEventRule:
    Type: AWS::Events::Rule
    Condition: CreateCloudWatchAlarms
    Properties:
      Description: !Sub "Notify on ${AWS::StackName} Step Functions execution failures"
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
            - !Ref <STATE_MACHINE_REF>
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
```

## 4. UC 固有の置換マッピング

| UC | `<STATE_MACHINE_REF>` | `<DISCOVERY_FUNCTION_REF>` |
|----|----------------------|---------------------------|
| UC2 financial-idp | IdpStateMachine | DiscoveryFunction |
| UC3 manufacturing-analytics | AnalyticsStateMachine | DiscoveryFunction |
| UC4 media-vfx | VfxStateMachine | DiscoveryFunction |
| UC5 healthcare-dicom | DicomStateMachine | DiscoveryFunction |
| UC6 semiconductor-eda | EdaStateMachine | DiscoveryFunction |
| UC7 genomics-pipeline | GenomicsStateMachine | DiscoveryFunction |
| UC8 energy-seismic | SeismicStateMachine | DiscoveryFunction |
| UC9 autonomous-driving | DrivingStateMachine | DiscoveryFunction |
| UC10 construction-bim | BimStateMachine | DiscoveryFunction |
| UC11 retail-catalog | CatalogStateMachine | DiscoveryFunction |
| UC12 logistics-ocr | LogisticsStateMachine | DiscoveryFunction |
| UC13 education-research | ResearchStateMachine | DiscoveryFunction |
| UC14 insurance-claims | ClaimsStateMachine | DiscoveryFunction |
| UC15 defense-satellite | SatelliteStateMachine | DiscoveryFunction |
| UC16 government-archives | ArchivesStateMachine | DiscoveryFunction |
| UC17 smart-city-geospatial | GeospatialStateMachine | DiscoveryFunction |

**注意**: 実際の論理名は各 UC の template-deploy.yaml を確認すること。
上記は命名規則に基づく推定値。

## 5. 前提条件

- `NotificationTopic` リソースが既に存在すること（全 UC で作成済み）
- `EnableCloudWatchAlarms` パラメータが Parameters セクションに存在すること
- `CreateCloudWatchAlarms` Condition が Conditions セクションに存在すること
