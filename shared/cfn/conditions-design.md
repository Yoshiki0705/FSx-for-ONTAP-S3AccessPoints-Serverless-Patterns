# CloudFormation Conditions 設計書

## 概要

本ドキュメントは、コスト構造分析（`docs/cost-analysis.md`）の結果に基づき、CloudFormation テンプレートにおけるオプショナルリソース制御の Conditions パターンを定義する。

固定費が発生する常時稼働リソースを opt-in 方式にすることで、デモ/PoC 環境での予期しない課金を防止する。

---

## 1. Parameters 定義

```yaml
Parameters:
  # --- オプショナルリソース制御 ---
  EnableVpcEndpoints:
    Type: String
    Default: "false"
    AllowedValues: ["true", "false"]
    Description: >-
      Interface VPC Endpoints を有効化する（月額 ~$28.80）。
      本番環境では true を推奨。デモ/PoC 環境では false（デフォルト）を推奨。
      有効化すると Secrets Manager, FSx, CloudWatch, SNS の Interface Endpoints が作成される。
      S3 Gateway Endpoint は無料のため常に作成される。

  EnableCloudWatchAlarms:
    Type: String
    Default: "false"
    AllowedValues: ["true", "false"]
    Description: >-
      CloudWatch Alarms を有効化する（$0.10/アラーム/月）。
      Step Functions 実行失敗、Lambda エラーレートの監視アラームが作成される。
      本番環境では true を推奨。

  EnableAthenaWorkgroup:
    Type: String
    Default: "true"
    AllowedValues: ["true", "false"]
    Description: >-
      Athena Workgroup を有効化する（UC1, UC3 で使用）。
      Athena 自体はクエリ実行時のみ課金（$5.00/TB スキャン）のため、デフォルト有効。
      UC2, UC4, UC5 など Athena を使用しないユースケースでは false に設定可能。

  # --- 必須パラメータ（常にデフォルト有効） ---
  S3AccessPointAlias:
    Type: String
    Description: FSx ONTAP S3 Access Point Alias
    AllowedPattern: "^[a-z0-9-]+-ext-s3alias$"

  OntapSecretName:
    Type: String
    Description: Secrets Manager secret name for ONTAP credentials

  OntapManagementIp:
    Type: String
    Description: ONTAP cluster management IP address

  ScheduleExpression:
    Type: String
    Default: "rate(1 hour)"
    Description: EventBridge Scheduler expression (rate or cron)

  VpcId:
    Type: AWS::EC2::VPC::Id
    Description: VPC ID for Lambda functions

  PrivateSubnetIds:
    Type: List<AWS::EC2::Subnet::Id>
    Description: Private subnet IDs for Lambda functions

  OutputBucketName:
    Type: String
    Description: S3 bucket name for output data

  NotificationEmail:
    Type: String
    Description: Email address for SNS notifications
```

---

## 2. Conditions 定義

```yaml
Conditions:
  CreateVpcEndpoints:
    !Equals [!Ref EnableVpcEndpoints, "true"]

  CreateCloudWatchAlarms:
    !Equals [!Ref EnableCloudWatchAlarms, "true"]

  CreateAthenaWorkgroup:
    !Equals [!Ref EnableAthenaWorkgroup, "true"]
```

---

## 3. Conditions とリソースのマッピング

### 3.1 `CreateVpcEndpoints` が制御するリソース

`EnableVpcEndpoints=true` の場合のみ作成される Interface VPC Endpoints。

| リソース論理名 | リソースタイプ | サービス | 月額コスト |
|--------------|-------------|---------|-----------|
| `SecretsManagerEndpoint` | `AWS::EC2::VPCEndpoint` | `com.amazonaws.${Region}.secretsmanager` | ~$7.20 |
| `FsxEndpoint` | `AWS::EC2::VPCEndpoint` | `com.amazonaws.${Region}.fsx` | ~$7.20 |
| `CloudWatchEndpoint` | `AWS::EC2::VPCEndpoint` | `com.amazonaws.${Region}.monitoring` | ~$7.20 |
| `SnsEndpoint` | `AWS::EC2::VPCEndpoint` | `com.amazonaws.${Region}.sns` | ~$7.20 |
| `VpcEndpointSecurityGroup` | `AWS::EC2::SecurityGroup` | — | 無料 |

**適用例**:

```yaml
Resources:
  SecretsManagerEndpoint:
    Type: AWS::EC2::VPCEndpoint
    Condition: CreateVpcEndpoints
    Properties:
      VpcId: !Ref VpcId
      ServiceName: !Sub "com.amazonaws.${AWS::Region}.secretsmanager"
      VpcEndpointType: Interface
      SubnetIds: !Ref PrivateSubnetIds
      SecurityGroupIds:
        - !Ref VpcEndpointSecurityGroup
      PrivateDnsEnabled: true

  FsxEndpoint:
    Type: AWS::EC2::VPCEndpoint
    Condition: CreateVpcEndpoints
    Properties:
      VpcId: !Ref VpcId
      ServiceName: !Sub "com.amazonaws.${AWS::Region}.fsx"
      VpcEndpointType: Interface
      SubnetIds: !Ref PrivateSubnetIds
      SecurityGroupIds:
        - !Ref VpcEndpointSecurityGroup
      PrivateDnsEnabled: true

  CloudWatchEndpoint:
    Type: AWS::EC2::VPCEndpoint
    Condition: CreateVpcEndpoints
    Properties:
      VpcId: !Ref VpcId
      ServiceName: !Sub "com.amazonaws.${AWS::Region}.monitoring"
      VpcEndpointType: Interface
      SubnetIds: !Ref PrivateSubnetIds
      SecurityGroupIds:
        - !Ref VpcEndpointSecurityGroup
      PrivateDnsEnabled: true

  SnsEndpoint:
    Type: AWS::EC2::VPCEndpoint
    Condition: CreateVpcEndpoints
    Properties:
      VpcId: !Ref VpcId
      ServiceName: !Sub "com.amazonaws.${AWS::Region}.sns"
      VpcEndpointType: Interface
      SubnetIds: !Ref PrivateSubnetIds
      SecurityGroupIds:
        - !Ref VpcEndpointSecurityGroup
      PrivateDnsEnabled: true

  VpcEndpointSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Condition: CreateVpcEndpoints
    Properties:
      GroupDescription: Security group for VPC Endpoints
      VpcId: !Ref VpcId
      SecurityGroupIngress:
        - IpProtocol: tcp
          FromPort: 443
          ToPort: 443
          SourceSecurityGroupId: !Ref LambdaSecurityGroup
```

> **注意**: S3 Gateway Endpoint は無料のため、Condition を適用せず常に作成する。

```yaml
  S3GatewayEndpoint:
    Type: AWS::EC2::VPCEndpoint
    # Condition なし — 常に作成（無料）
    Properties:
      VpcId: !Ref VpcId
      ServiceName: !Sub "com.amazonaws.${AWS::Region}.s3"
      VpcEndpointType: Gateway
      RouteTableIds:
        - !Ref PrivateRouteTable
```

### 3.2 `CreateCloudWatchAlarms` が制御するリソース

`EnableCloudWatchAlarms=true` の場合のみ作成される監視アラーム。

| リソース論理名 | リソースタイプ | 監視対象 | 月額コスト |
|--------------|-------------|---------|-----------|
| `StepFunctionsFailureAlarm` | `AWS::CloudWatch::Alarm` | Step Functions 実行失敗 | $0.10 |
| `LambdaErrorRateAlarm` | `AWS::CloudWatch::Alarm` | Lambda エラーレート | $0.10 |
| `LambdaThrottleAlarm` | `AWS::CloudWatch::Alarm` | Lambda スロットリング | $0.10 |

**適用例**:

```yaml
Resources:
  StepFunctionsFailureAlarm:
    Type: AWS::CloudWatch::Alarm
    Condition: CreateCloudWatchAlarms
    Properties:
      AlarmName: !Sub "${AWS::StackName}-sfn-failure"
      AlarmDescription: Step Functions workflow execution failure
      Namespace: AWS/States
      MetricName: ExecutionsFailed
      Dimensions:
        - Name: StateMachineArn
          Value: !Ref StateMachine
      Statistic: Sum
      Period: 300
      EvaluationPeriods: 1
      Threshold: 1
      ComparisonOperator: GreaterThanOrEqualToThreshold
      AlarmActions:
        - !Ref NotificationTopic

  LambdaErrorRateAlarm:
    Type: AWS::CloudWatch::Alarm
    Condition: CreateCloudWatchAlarms
    Properties:
      AlarmName: !Sub "${AWS::StackName}-lambda-errors"
      AlarmDescription: Lambda function error rate
      Namespace: AWS/Lambda
      MetricName: Errors
      Statistic: Sum
      Period: 300
      EvaluationPeriods: 1
      Threshold: 5
      ComparisonOperator: GreaterThanOrEqualToThreshold
      AlarmActions:
        - !Ref NotificationTopic

  LambdaThrottleAlarm:
    Type: AWS::CloudWatch::Alarm
    Condition: CreateCloudWatchAlarms
    Properties:
      AlarmName: !Sub "${AWS::StackName}-lambda-throttles"
      AlarmDescription: Lambda function throttling
      Namespace: AWS/Lambda
      MetricName: Throttles
      Statistic: Sum
      Period: 300
      EvaluationPeriods: 1
      Threshold: 1
      ComparisonOperator: GreaterThanOrEqualToThreshold
      AlarmActions:
        - !Ref NotificationTopic
```

### 3.3 `CreateAthenaWorkgroup` が制御するリソース

`EnableAthenaWorkgroup=true` の場合のみ作成される Athena 関連リソース。

| リソース論理名 | リソースタイプ | 用途 | 月額コスト |
|--------------|-------------|------|-----------|
| `AthenaWorkgroup` | `AWS::Athena::WorkGroup` | クエリ実行環境 | 無料（クエリ実行時のみ課金） |
| `GlueDatabase` | `AWS::Glue::Database` | データカタログ DB | 無料（100万オブジェクトまで） |
| `GlueTable` | `AWS::Glue::Table` | データカタログテーブル | 無料（100万オブジェクトまで） |

**適用例**:

```yaml
Resources:
  AthenaWorkgroup:
    Type: AWS::Athena::WorkGroup
    Condition: CreateAthenaWorkgroup
    Properties:
      Name: !Sub "${AWS::StackName}-workgroup"
      WorkGroupConfiguration:
        ResultConfiguration:
          OutputLocation: !Sub "s3://${OutputBucket}/athena-results/"
        EnforceWorkGroupConfiguration: true
        BytesScannedCutoffPerQuery: 1073741824  # 1GB limit

  GlueDatabase:
    Type: AWS::Glue::Database
    Condition: CreateAthenaWorkgroup
    Properties:
      CatalogId: !Ref AWS::AccountId
      DatabaseInput:
        Name: !Sub "${AWS::StackName}_db"
        Description: Data catalog for FSxN S3AP analysis

  GlueTable:
    Type: AWS::Glue::Table
    Condition: CreateAthenaWorkgroup
    Properties:
      CatalogId: !Ref AWS::AccountId
      DatabaseName: !Ref GlueDatabase
      TableInput:
        Name: acl_data
        StorageDescriptor:
          Columns:
            - Name: object_key
              Type: string
            - Name: volume_uuid
              Type: string
            - Name: security_style
              Type: string
            - Name: acls
              Type: string
            - Name: collected_at
              Type: timestamp
          Location: !Sub "s3://${OutputBucket}/acl-data/"
          InputFormat: org.apache.hadoop.mapred.TextInputFormat
          OutputFormat: org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat
          SerdeInfo:
            SerializationLibrary: org.openx.data.jsonserde.JsonSerDe
        PartitionKeys:
          - Name: year
            Type: string
          - Name: month
            Type: string
          - Name: day
            Type: string
```

---

## 4. ユースケース別 Conditions 使用マトリックス

| Condition | UC1 法務 | UC2 金融 | UC3 製造 | UC4 メディア | UC5 医療 |
|-----------|---------|---------|---------|------------|---------|
| `CreateVpcEndpoints` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `CreateCloudWatchAlarms` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `CreateAthenaWorkgroup` | ✅ | — | ✅ | — | — |

> UC2, UC4, UC5 は Athena を使用しないため、`EnableAthenaWorkgroup=false` に設定可能。

---

## 5. デプロイシナリオ別パラメータ設定

### 5.1 デモ/PoC 環境（最小コスト）

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name fsxn-s3ap-demo \
  --parameter-overrides \
    EnableVpcEndpoints=false \
    EnableCloudWatchAlarms=false \
    EnableAthenaWorkgroup=true \
    S3AccessPointAlias=vol-demo-xxxxx-ext-s3alias \
    OntapSecretName=fsxn-ontap-credentials \
    OntapManagementIp=10.0.0.1 \
    VpcId=vpc-xxxxxxxx \
    PrivateSubnetIds=subnet-aaaa,subnet-bbbb \
    OutputBucketName=fsxn-s3ap-output-demo \
    NotificationEmail=admin@example.com
```

**推定月額コスト**: ~$1〜$3（変動費のみ）

> ⚠️ `EnableVpcEndpoints=false` の場合、Lambda は VPC 外で実行するか、NAT Gateway 経由でインターネットアクセスが必要です。

### 5.2 本番環境（フル機能）

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name fsxn-s3ap-production \
  --parameter-overrides \
    EnableVpcEndpoints=true \
    EnableCloudWatchAlarms=true \
    EnableAthenaWorkgroup=true \
    S3AccessPointAlias=vol-prod-xxxxx-ext-s3alias \
    OntapSecretName=fsxn-ontap-credentials-prod \
    OntapManagementIp=10.0.1.1 \
    ScheduleExpression="rate(30 minutes)" \
    VpcId=vpc-yyyyyyyy \
    PrivateSubnetIds=subnet-cccc,subnet-dddd \
    OutputBucketName=fsxn-s3ap-output-prod \
    NotificationEmail=ops-team@example.com
```

**推定月額コスト**: ~$30〜$75（固定費 + 中規模変動費）

### 5.3 開発環境（Athena 不要の UC 向け）

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name fsxn-s3ap-dev-uc2 \
  --parameter-overrides \
    EnableVpcEndpoints=false \
    EnableCloudWatchAlarms=false \
    EnableAthenaWorkgroup=false \
    S3AccessPointAlias=vol-dev-xxxxx-ext-s3alias \
    OntapSecretName=fsxn-ontap-credentials-dev \
    OntapManagementIp=10.0.2.1 \
    VpcId=vpc-zzzzzzzz \
    PrivateSubnetIds=subnet-eeee,subnet-ffff \
    OutputBucketName=fsxn-s3ap-output-dev \
    NotificationEmail=dev@example.com
```

**推定月額コスト**: ~$0.30〜$3（変動費のみ）

---

## 6. Conditions 使用時の注意事項

### 6.1 Condition 付きリソースの参照

Condition 付きリソースを他のリソースから参照する場合、`!If` 関数を使用する。

```yaml
# Lambda の VPC 設定（VPC Endpoints が有効な場合のみ VPC 内で実行）
DiscoveryLambda:
  Type: AWS::Lambda::Function
  Properties:
    # ...
    VpcConfig:
      !If
        - CreateVpcEndpoints
        - SecurityGroupIds:
            - !Ref LambdaSecurityGroup
          SubnetIds: !Ref PrivateSubnetIds
        - !Ref "AWS::NoValue"
```

### 6.2 Outputs での Condition 使用

```yaml
Outputs:
  VpcEndpointIds:
    Condition: CreateVpcEndpoints
    Description: Created VPC Endpoint IDs
    Value: !Join
      - ","
      - - !Ref SecretsManagerEndpoint
        - !Ref FsxEndpoint
        - !Ref CloudWatchEndpoint
        - !Ref SnsEndpoint

  AthenaWorkgroupName:
    Condition: CreateAthenaWorkgroup
    Description: Athena Workgroup name
    Value: !Ref AthenaWorkgroup
```

### 6.3 Lambda 環境変数での Condition 使用

Athena Lambda は `CreateAthenaWorkgroup` が true の場合のみ Workgroup 名を環境変数に設定する。

```yaml
AthenaAnalysisLambda:
  Type: AWS::Lambda::Function
  Properties:
    Environment:
      Variables:
        ATHENA_WORKGROUP:
          !If
            - CreateAthenaWorkgroup
            - !Ref AthenaWorkgroup
            - ""
        GLUE_DATABASE:
          !If
            - CreateAthenaWorkgroup
            - !Ref GlueDatabase
            - ""
```

---

## 7. 設計根拠まとめ

| 設計判断 | 根拠 |
|---------|------|
| Interface VPC Endpoints をデフォルト無効 | 月額 ~$28.80 の固定費。デモ/PoC で最大のコスト要因 |
| CloudWatch Alarms をデフォルト無効 | 本番運用向け機能。デモ/PoC では不要 |
| Athena Workgroup をデフォルト有効 | クエリ実行時のみ課金。固定費なし。UC1/UC3 で必須 |
| S3 Gateway Endpoint を常時作成 | 完全無料。VPC 内 Lambda の S3 アクセスに必須 |
| EventBridge Scheduler を常時作成 | 月間 1,400万回まで無料。全 UC で必須 |
| SNS Topic を常時作成 | 月間 100万リクエストまで無料。通知に必須 |
| Lambda/Step Functions を常時作成 | リクエストベース課金。実行しなければ $0 |
