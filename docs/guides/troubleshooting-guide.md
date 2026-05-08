# トラブルシューティング手順書

本ドキュメントでは、FSx for ONTAP S3 AP Serverless Patterns で発生しうるエラーと対処法を説明します。

## 目次

1. [AccessDenied エラー](#1-accessdenied-エラー)
2. [VPC Endpoint 到達不能](#2-vpc-endpoint-到達不能)
3. [ONTAP API タイムアウト](#3-ontap-api-タイムアウト)
4. [Athena クエリ失敗](#4-athena-クエリ失敗)
5. [その他のよくあるエラー](#5-その他のよくあるエラー)
6. [Lambda VPC 内実行時の S3 AP タイムアウト](#6-lambda-vpc-内実行時の-s3-ap-タイムアウト)
7. [同一 VPC に複数スタックデプロイ時の S3 Gateway Endpoint 競合](#7-同一-vpc-に複数スタックデプロイ時の-s3-gateway-endpoint-競合)

---

## 1. AccessDenied エラー

### 症状

Lambda 関数のログに以下のようなエラーが出力される:

```
S3ApHelperError: Access denied to S3 Access Point '<your-ap-alias>'.
Verify that the IAM role has s3:ListBucket permission on the Access Point
and that the Access Point policy allows the operation.
```

### 原因と対処法

#### 原因 1: IAM ロールの権限不足

**確認方法**:

```bash
# Lambda 関数の実行ロールを確認
aws lambda get-function-configuration \
  --function-name <your-lambda-function-name> \
  --query "Role" \
  --region ap-northeast-1

# ロールのポリシーを確認
aws iam list-attached-role-policies \
  --role-name <your-role-name>
```

**対処法**: Lambda 関数の IAM ロールに以下の権限を追加:

```json
{
  "Effect": "Allow",
  "Action": [
    "s3:ListBucket",
    "s3:GetObject",
    "s3:PutObject",
    "s3:HeadObject"
  ],
  "Resource": [
    "arn:aws:s3:<region>:<account-id>:accesspoint/<ap-name>",
    "arn:aws:s3:<region>:<account-id>:accesspoint/<ap-name>/object/*"
  ]
}
```

#### 原因 2: S3 Access Point ポリシーの制限

**確認方法**:

```bash
# S3 AP ポリシーの確認
aws s3control get-access-point-policy \
  --account-id <your-account-id> \
  --name <your-ap-name> \
  --region ap-northeast-1
```

**対処法**: S3 AP ポリシーで Lambda 実行ロールからのアクセスを許可する。

#### 原因 3: S3 AP のネットワークオリジン設定

**確認方法**:

```bash
# S3 AP のネットワークオリジンを確認
aws s3control get-access-point \
  --account-id <your-account-id> \
  --name <your-ap-name> \
  --region ap-northeast-1
```

**対処法**:
- Lambda が VPC 内で実行される場合、S3 AP のネットワークオリジンが `VPC` なら S3 Gateway VPC Endpoint が必要
- Athena を使用する UC（UC1, UC3）では、S3 AP のネットワークオリジンを `Internet` に設定する必要がある

> **参考**: S3 AP のネットワークオリジン制約については [README.md の互換性マトリックス](../../README.md) を参照してください。

#### 原因 4: S3AccessPointName パラメータ未指定による ARN ベース権限不足

> **UC6 デプロイ検証（2026-05-09）で発見された問題**

**症状**: IAM ポリシーが S3 AP Alias ベースのみで構成され、ARN ベースの権限が不足している場合に `AccessDenied` が発生する。

**確認方法**:

```bash
# Lambda 実行ロールのポリシーを確認
aws iam get-role-policy \
  --role-name <your-stack-name>-discovery-role \
  --policy-name DiscoveryPolicy \
  --region ap-northeast-1
```

ポリシーに `arn:aws:s3:<region>:<account-id>:accesspoint/<ap-name>` 形式のリソースが含まれていない場合、この問題に該当する。

**対処法**: CloudFormation テンプレートの `S3AccessPointName` パラメータに S3 AP の名前（Alias ではなく作成時に指定した名前）を指定してスタックを更新する:

```bash
aws cloudformation deploy \
  --template-file <uc>/template-deploy.yaml \
  --stack-name <your-stack-name> \
  --parameter-overrides \
    S3AccessPointName=<your-s3ap-name> \
    ... \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

> **推奨**: 本番環境では常に `S3AccessPointName` を指定してください。Alias ベースのみの IAM ポリシーは一部の環境で `AccessDenied` を引き起こします。

---

## 2. VPC Endpoint 到達不能

### 症状

Lambda 関数のログに以下のようなエラーが出力される:

```
ConnectTimeoutError: Connect timeout on endpoint URL
botocore.exceptions.EndpointConnectionError: Could not connect to the endpoint URL
```

### 原因と対処法

#### 原因 1: VPC Endpoint が作成されていない

**確認方法**:

```bash
# VPC Endpoint の一覧確認
aws ec2 describe-vpc-endpoints \
  --filters "Name=vpc-id,Values=<your-vpc-id>" \
  --query "VpcEndpoints[].{Id:VpcEndpointId,Service:ServiceName,Type:VpcEndpointType,State:State}" \
  --region ap-northeast-1
```

**対処法**: `EnableVpcEndpoints=true` でスタックを再デプロイ:

```bash
aws cloudformation deploy \
  --template-file legal-compliance/template.yaml \
  --stack-name fsxn-legal-compliance \
  --parameter-overrides \
    EnableVpcEndpoints=true \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
  --region ap-northeast-1
```

#### 原因 2: セキュリティグループの設定不備

**確認方法**:

```bash
# VPC Endpoint のセキュリティグループを確認
aws ec2 describe-vpc-endpoints \
  --vpc-endpoint-ids <your-vpce-id> \
  --query "VpcEndpoints[0].Groups" \
  --region ap-northeast-1

# セキュリティグループのインバウンドルールを確認
aws ec2 describe-security-groups \
  --group-ids <your-sg-id> \
  --query "SecurityGroups[0].IpPermissions" \
  --region ap-northeast-1
```

**対処法**: VPC Endpoint のセキュリティグループで、Lambda のセキュリティグループからの HTTPS (443) インバウンドを許可する。

#### 原因 3: サブネットのルートテーブル設定

**確認方法**:

```bash
# サブネットのルートテーブルを確認
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=<your-subnet-id>" \
  --query "RouteTables[0].Routes" \
  --region ap-northeast-1
```

**対処法**: S3 Gateway VPC Endpoint がルートテーブルに関連付けられていることを確認する。

---

## 3. ONTAP API タイムアウト

### 症状

Lambda 関数のログに以下のようなエラーが出力される:

```
OntapClientError: Request timeout for GET /storage/volumes
OntapClientError: Max retries exceeded for GET /storage/volumes
```

### 原因と対処法

#### 原因 1: ONTAP 管理 IP への接続不可

**確認方法**:

Lambda が VPC 内で実行されている場合、ONTAP 管理 IP への TCP 443 接続が可能か確認する。

**対処法**:
- Lambda のセキュリティグループで ONTAP 管理 IP への HTTPS アウトバウンドを許可
- ONTAP 側のファイアウォールで Lambda サブネットからのアクセスを許可

#### 原因 2: Secrets Manager からの認証情報取得失敗

**確認方法**:

```bash
# シークレットの存在確認
aws secretsmanager describe-secret \
  --secret-id <your-ontap-secret-name> \
  --region ap-northeast-1
```

**対処法**:
- シークレット名が正しいことを確認
- Lambda の IAM ロールに `secretsmanager:GetSecretValue` 権限があることを確認
- Secrets Manager VPC Endpoint が有効であることを確認（VPC 内 Lambda の場合）

#### 原因 3: ONTAP のレスポンス遅延

**対処法**:
- OntapClient のタイムアウト値を増加（デフォルト: connect=10s, read=30s）
- Lambda 関数のタイムアウト値を増加（CloudFormation テンプレートで設定）

---

## 4. Athena クエリ失敗

### 症状

Athena Analysis Lambda のログに以下のようなエラーが出力される:

```
FAILED: SemanticException Table not found
FAILED: HIVE_METASTORE_ERROR
InvalidRequestException: Query has not yet finished
```

### 原因と対処法

#### 原因 1: Glue Data Catalog テーブルが存在しない

**確認方法**:

```bash
# Glue データベースとテーブルの確認
aws glue get-tables \
  --database-name <your-glue-database-name> \
  --region ap-northeast-1
```

**対処法**: Athena Analysis Lambda が Glue テーブルを自動作成するため、先に ACL Collection Lambda が正常に完了していることを確認する。

#### 原因 2: S3 AP のネットワークオリジンが VPC

Athena は AWS マネージドインフラから S3 にアクセスするため、VPC origin の S3 AP にはアクセスできない。

**対処法**: UC1（法務）と UC3（製造業）で使用する S3 AP は `Internet` ネットワークオリジンで作成する。

#### 原因 3: Athena Workgroup の設定不備

**確認方法**:

```bash
# Athena Workgroup の確認
aws athena get-work-group \
  --work-group <your-workgroup-name> \
  --region ap-northeast-1
```

**対処法**: Workgroup の出力先 S3 バケットが正しく設定されていることを確認する。

---

## 5. その他のよくあるエラー

### Lambda メモリ不足

**症状**: `Runtime.ExitError` または `SIGKILL`

**対処法**: Lambda 関数のメモリサイズを増加（CloudFormation テンプレートで設定）。

### Lambda タイムアウト

**症状**: `Task timed out after X seconds`

**対処法**:
- Lambda 関数のタイムアウト値を増加
- 処理対象のオブジェクト数が多い場合、Map ステートの並列度を調整

### Textract / Rekognition / Bedrock のサービスエラー

**症状**: `ThrottlingException` または `ServiceUnavailableException`

**対処法**:
- Step Functions の Retry 設定で自動リトライされる（デフォルト: 3 回、指数バックオフ）
- 頻発する場合はサービスクォータの引き上げを申請

### CloudFormation デプロイ失敗

**症状**: `ROLLBACK_COMPLETE` または `UPDATE_ROLLBACK_COMPLETE`

**確認方法**:

```bash
# スタックイベントの確認（失敗原因の特定）
aws cloudformation describe-stack-events \
  --stack-name fsxn-legal-compliance \
  --query "StackEvents[?ResourceStatus=='CREATE_FAILED' || ResourceStatus=='UPDATE_FAILED'].{Resource:LogicalResourceId,Reason:ResourceStatusReason}" \
  --region ap-northeast-1
```

**よくある原因**:

| 原因 | 対処法 |
|------|--------|
| IAM ロール作成権限不足 | `CAPABILITY_IAM` を指定してデプロイ |
| S3 バケット名の重複 | ユニークなバケット名を指定 |
| VPC/サブネットが存在しない | パラメータの VPC ID / サブネット ID を確認 |
| サービスクォータ超過 | AWS サポートにクォータ引き上げを申請 |

---

## 6. Lambda VPC 内実行時の S3 AP タイムアウト

> **UC1 デプロイ検証（2026-05-03）で発見された問題**

### 症状

VPC 内で実行される Lambda 関数が S3 Access Point に対して `ListObjectsV2` や `PutObject` を実行すると、Lambda のタイムアウト（デフォルト 300 秒）まで応答がなくタイムアウトする。

```
Task timed out after 300.00 seconds
```

CloudWatch Logs にはエラーメッセージが出力されず、単純にタイムアウトする点が特徴。

### 根本原因

S3 Gateway VPC Endpoint に `RouteTableIds` が指定されていない場合、プライベートサブネットのルートテーブルに S3 へのルートが追加されない。その結果、S3 / S3 AP へのトラフィックがデフォルトルート（0.0.0.0/0）に従うが、プライベートサブネットに NAT Gateway や Internet Gateway がない場合、パケットがドロップされタイムアウトする。

さらに、S3 AP の DNS 名（`<alias>-ext-s3alias.s3.amazonaws.com`）の VPC 内 DNS 解決にも注意が必要。

### 確認方法

```bash
# 1. S3 Gateway Endpoint のルートテーブル関連付けを確認
aws ec2 describe-vpc-endpoints \
  --filters "Name=vpc-id,Values=<your-vpc-id>" \
            "Name=service-name,Values=com.amazonaws.ap-northeast-1.s3" \
  --query "VpcEndpoints[].{Id:VpcEndpointId,RouteTableIds:RouteTableIds}" \
  --region ap-northeast-1

# 2. プライベートサブネットのルートテーブルを確認
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=<your-private-subnet-id>" \
  --query "RouteTables[0].Routes" \
  --region ap-northeast-1

# 3. S3 AP の DNS 解決を確認（VPC 内から実行）
nslookup <your-ap-alias>-ext-s3alias.s3.amazonaws.com
```

### 対処法

#### 対処法 A: PoC / デモ環境向け（推奨）

Lambda の `VpcConfig` を削除し、VPC 外で実行する。S3 AP の network origin が `internet` であれば、VPC 外 Lambda から問題なくアクセス可能。

**メリット**:
- VPC Endpoint 不要（コスト削減）
- ネットワーク設定の複雑さを回避
- S3 AP へのアクセスが即座に動作

**制約**:
- ONTAP REST API への直接アクセスには ONTAP 管理 IP への到達性が必要
- セキュリティ要件が厳しい環境には不適

#### 対処法 B: 本番環境向け

1. **S3 Gateway Endpoint にルートテーブルを関連付ける**:

   CloudFormation テンプレートの `S3GatewayEndpoint` リソースに `RouteTableIds` を追加:

   ```yaml
   S3GatewayEndpoint:
     Type: AWS::EC2::VPCEndpoint
     Properties:
       VpcId: !Ref VpcId
       ServiceName: !Sub "com.amazonaws.${AWS::Region}.s3"
       VpcEndpointType: Gateway
       RouteTableIds:
         - !Ref PrivateRouteTableId
   ```

2. **VPC DNS 解決の確認**:
   - VPC の `enableDnsSupport` と `enableDnsHostnames` が `true` であることを確認
   - S3 AP の DNS 名が VPC 内から正しく解決されることを確認

3. **必要に応じて Interface VPC Endpoints を有効化**:
   - `EnableVpcEndpoints=true` でデプロイし、Secrets Manager / FSx / CloudWatch / SNS 用の Interface Endpoints を作成

### 関連パラメータ

| パラメータ | 説明 |
|-----------|------|
| `PrivateRouteTableId` | プライベートサブネットのルートテーブル ID。S3 Gateway Endpoint に関連付けるために必須 |
| `EnableVpcEndpoints` | Interface VPC Endpoints の有効化。本番環境では `true` 推奨 |

---

## 7. 同一 VPC に複数スタックデプロイ時の S3 Gateway Endpoint 競合

> **UC2-UC5 デプロイ検証（2026-05-02）で発見された問題**

### 症状

2 番目以降のスタック作成時に以下のエラーで ROLLBACK:

```
Resource handler returned message: "route table rtb-xxxxx already has a route
with destination-prefix-list-id pl-xxxxx (Service: Ec2, Status Code: 400)"
(HandlerErrorCode: AlreadyExists)
```

### 根本原因

各テンプレートが独自に S3 Gateway VPC Endpoint を作成するが、同一 VPC 内に同一サービスの Gateway Endpoint は 1 つしか存在できない。最初のスタック（例: UC1）で作成された S3 Gateway Endpoint が既に存在するため、2 番目以降のスタックで競合が発生する。

### 対処法

`EnableS3GatewayEndpoint` パラメータを `false` に設定して、S3 Gateway Endpoint の作成をスキップする:

```bash
# 2 番目以降のスタックでは S3 Gateway Endpoint を無効化
aws cloudformation create-stack \
  --stack-name fsxn-financial-idp \
  --template-body file://financial-idp/template-deploy.yaml \
  --parameters \
    ParameterKey=EnableS3GatewayEndpoint,ParameterValue=false \
    ...
```

### 関連パラメータ

| パラメータ | デフォルト | 説明 |
|-----------|-----------|------|
| `EnableS3GatewayEndpoint` | `true` | S3 Gateway VPC Endpoint を作成する。同一 VPC に既存の場合は `false` に設定 |

### 注意事項

- 単独デプロイ（1 つの UC のみ）の場合は `true`（デフォルト）のまま使用
- 複数 UC を同一 VPC にデプロイする場合は、最初のスタックのみ `true`、残りは `false`
- S3 Gateway Endpoint は無料のため、コスト面での影響はなし

---

## ログ収集テンプレート

問題報告時に以下の情報を収集してください:

```bash
# 1. スタック情報
aws cloudformation describe-stacks \
  --stack-name <your-stack-name> \
  --region ap-northeast-1

# 2. Lambda 関数のエラーログ（直近 1 時間）
aws logs filter-log-events \
  --log-group-name "/aws/lambda/<your-function-name>" \
  --filter-pattern "ERROR" \
  --start-time $(date -d '1 hour ago' +%s000) \
  --region ap-northeast-1

# 3. Step Functions 実行履歴
aws stepfunctions get-execution-history \
  --execution-arn <your-execution-arn> \
  --region ap-northeast-1

# 4. VPC Endpoint の状態
aws ec2 describe-vpc-endpoints \
  --filters "Name=vpc-id,Values=<your-vpc-id>" \
  --region ap-northeast-1
```
