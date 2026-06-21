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
  --template-file solutions/industry/legal-compliance/template.yaml \
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
  --template-body file://solutions/industry/financial-idp/template-deploy.yaml \
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

---

## FlexCache 関連のトラブルシューティング

### FlexCache 作成失敗

| 症状 | 原因 | 解決策 |
|------|------|--------|
| ONTAP REST API 404 | Origin volume/SVM が存在しない | volume 名、SVM 名を確認 |
| ONTAP REST API 409 | 同名の FlexCache が既に存在 | 冪等性チェックが正常動作しているか確認 |
| ONTAP REST API 500 | アグリゲート容量不足 | `storage aggregate show` で空き容量確認 |
| Lambda タイムアウト | ONTAP 管理 IP に到達不可 | VPC/SG/ルートテーブル確認 |
| Job state: failure | FlexCache 作成ジョブ失敗 | `GET /api/cluster/jobs/{uuid}` で message 確認 |

### FlexCache 削除失敗

| 症状 | 原因 | 解決策 |
|------|------|--------|
| ONTAP REST API 409 | Volume busy（クライアントがマウント中） | クライアントのアンマウントを確認 |
| ONTAP REST API 404 | 既に削除済み | 冪等性により成功扱い（正常） |
| Lambda タイムアウト | 削除ジョブが長時間実行中 | タイムアウト値を延長（300秒推奨） |

### Orphan FlexCache の検出

```bash
# ONTAP CLI で dynamic FlexCache を確認
ssh admin@<MGMT_IP> "volume flexcache show -vserver svm1 -volume dyn_cache_*"

# Lambda で orphan 検出
aws lambda invoke \
  --function-name dynamic-flexcache-OrphanDetector \
  --payload '{}' \
  response.json
```

### FlexCache + S3 AP アクセス問題

| 症状 | 原因 | 解決策 |
|------|------|--------|
| S3 AP から FlexCache データが見えない | FlexCache volume に S3 AP が attach されていない | FSx コンソールで S3 AP の attach 先を確認 |
| S3 AP AccessDenied | IAM ARN 形式エラー | `arn:aws:s3:{region}:{account}:accesspoint/{name}` 形式を使用 |
| S3 AP タイムアウト | NetworkOrigin 設定の不一致 | VPC 内 Lambda → VPC Origin AP、VPC 外 → Internet Origin AP |

### FlexCache ヘルスチェック失敗

```bash
# ヘルスチェック Lambda のログ確認
aws logs filter-log-events \
  --log-group-name "/aws/lambda/flexcache-anycast-HealthCheck-demo" \
  --filter-pattern "health_status" \
  --start-time $(date -d '30 minutes ago' +%s000) \
  --region ap-northeast-1

# DynamoDB ルーティングテーブル確認
aws dynamodb scan \
  --table-name FlexCacheRoutingTable-demo \
  --region ap-northeast-1
```

### Dynamic FlexCache Workflow の Step Functions 失敗

```bash
# 失敗した実行の詳細確認
aws stepfunctions describe-execution \
  --execution-arn <EXECUTION_ARN> \
  --region ap-northeast-1

# 失敗ステートの入出力確認
aws stepfunctions get-execution-history \
  --execution-arn <EXECUTION_ARN> \
  --region ap-northeast-1 \
  --query "events[?type=='TaskFailed']"
```

### CloudWatch Logs Insights クエリ

```sql
-- FlexCache 操作のエラー検出
fields @timestamp, @message
| filter @message like /FlexCache/ and @message like /ERROR/
| sort @timestamp desc
| limit 50

-- ONTAP REST API レスポンス時間
fields @timestamp, @message
| filter @message like /ONTAP API/
| parse @message '"latency_ms": *' as latency
| stats avg(latency), max(latency), p95(latency) by bin(5m)
```

---

## 7. S3AP ConnectionClosedError（Phase 13 発見）

### 症状

VPC 外 Lambda から Internet-origin S3 Access Point に `ListObjectsV2` を実行すると、`AccessDenied` ではなく `ConnectionClosedError` が返る。

```
ConnectionClosedError: Connection was closed before we received a valid response from endpoint URL:
"https://xxx-ext-s3alias.s3.ap-northeast-1.amazonaws.com/?list-type=2&prefix=_health%2F&max-keys=1"
```

または `ReadTimeoutError`（20秒以上応答なし）。

### 原因

以下のいずれか（または複合）:

1. **S3AP リソースポリシー未設定**: Lambda 実行ロールが S3AP リソースポリシーで Allow されていない
2. **S3AP attachment Lifecycle が AVAILABLE でない**: `CREATED` 状態ではデータプレーンが応答しない
3. **ONTAP ボリュームがオフライン**: S3AP が紐づくボリュームが offline/restricted 状態

### 確認手順

```bash
# 1. S3AP リソースポリシー確認
aws s3control get-access-point-policy \
  --account-id <ACCOUNT_ID> \
  --name <S3AP_NAME> \
  --region ap-northeast-1

# 2. S3AP attachment Lifecycle 確認
aws fsx describe-s3-access-point-attachments \
  --region ap-northeast-1 \
  --query 'S3AccessPointAttachments[?Name==`<S3AP_NAME>`].Lifecycle'

# 3. ボリューム状態確認
aws fsx describe-volumes \
  --volume-ids <VOLUME_ID> \
  --region ap-northeast-1 \
  --query 'Volumes[0].Lifecycle'
```

### 解決策

```bash
# S3AP リソースポリシーに Lambda ロールを追加
aws s3control put-access-point-policy \
  --account-id <ACCOUNT_ID> \
  --name <S3AP_NAME> \
  --region ap-northeast-1 \
  --policy '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"AWS": "arn:aws:iam::<ACCOUNT_ID>:role/<LAMBDA_ROLE_NAME>"},
      "Action": ["s3:ListBucket", "s3:GetObject"],
      "Resource": [
        "arn:aws:s3:ap-northeast-1:<ACCOUNT_ID>:accesspoint/<S3AP_NAME>",
        "arn:aws:s3:ap-northeast-1:<ACCOUNT_ID>:accesspoint/<S3AP_NAME>/object/*"
      ]
    }]
  }'
```

### 重要な注意点

- FSx for ONTAP S3AP は通常の S3 とは異なるデータプレーンを使用する
- 認証/認可エラーが `AccessDenied` ではなく `ConnectionClosedError` として表面化する場合がある
- IAM identity-based policy だけでなく、S3AP resource policy の両方が必要
- S3AP attachment の Lifecycle が `AVAILABLE` であることを必ず確認する


---

## 8. FPolicy Protobuf モード切り替え（Phase 13 発見）

### 症状

ONTAP CLI で FPolicy external engine の format を protobuf に変更しようとすると `invalid argument "-format"` エラーが発生する。

```
FsxId01234567890abc:> fpolicy policy external-engine modify -vserver FSxN_OnPre -engine-name my_engine -format protobuf
Error: invalid argument "-format"
```

### 原因

ONTAP 9.17.1 では、FPolicy external engine の `format` フィールドは **REST API でのみ変更可能**。CLI には `-format` パラメータが実装されていない。

### 解決策

REST API の PATCH メソッドを使用する：

```bash
# 1. FPolicy ポリシーを無効化
fpolicy disable -vserver <SVM_NAME> -policy-name <POLICY_NAME>

# 2. REST API で format を変更
curl -sk -X PATCH \
  -u "fsxadmin:<PASSWORD>" \
  -H "Content-Type: application/json" \
  -d '{"format": "protobuf"}' \
  "https://<FS_MGMT_IP>/api/protocols/fpolicy/<SVM_UUID>/engines/<ENGINE_NAME>"

# 3. FPolicy ポリシーを再有効化
fpolicy enable -vserver <SVM_NAME> -policy-name <POLICY_NAME> -sequence-number 1
```

### 重要な注意点

- `<FS_MGMT_IP>` はファイルシステム管理 IP（SVM 管理 IP ではない）
- format 変更は FPolicy disable 中にのみ可能
- Keep-alive interval (PT2M) は XML/protobuf 共通
- Buffer サイズ: recv=256KB, send=1MB（ProtobufFrameReader の max_message_size は 1MB 以上に設定）

---

## 9. fsxadmin 認証エラー "User is not authorized"（Phase 13 発見）

### 症状

ONTAP REST API に fsxadmin で認証すると `6691623: User is not authorized` エラーが返る。

### 原因

以下のいずれか：
1. **SVM 管理 IP に接続している** — fsxadmin はファイルシステム管理 IP でのみ認証可能
2. **パスワードが不正** — Secrets Manager のパスワードと ONTAP 側が不一致
3. **パスワードに特殊文字** — シェル経由で渡す際にエスケープ問題

### 確認手順

```bash
# ファイルシステム管理 IP を確認（これを使う）
aws fsx describe-file-systems --file-system-ids <FS_ID> \
  --query 'FileSystems[0].OntapConfiguration.Endpoints.Management.IpAddresses[0]'

# SVM 管理 IP（これは fsxadmin では使えない）
aws fsx describe-storage-virtual-machines \
  --query 'StorageVirtualMachines[0].Endpoints.Management.IpAddresses[0]'
```

### 解決策

```python
# Python で安全にパスワードリセット + Secrets Manager 更新
import boto3, json, secrets, string

chars = string.ascii_letters + string.digits + "!@"
new_password = "".join(secrets.choice(chars) for _ in range(20))

fsx = boto3.client("fsx", region_name="ap-northeast-1")
fsx.update_file_system(
    FileSystemId="fs-xxx",
    OntapConfiguration={"FsxAdminPassword": new_password}
)

sm = boto3.client("secretsmanager", region_name="ap-northeast-1")
sm.put_secret_value(
    SecretId="fsx-ontap-fsxadmin-credentials",
    SecretString=json.dumps({"username": "fsxadmin", "password": new_password})
)
```

### 重要な注意点

- シェルスクリプトでパスワードを扱う場合、特殊文字のエスケープ問題が発生しやすい
- Python boto3 で直接操作するのが最も安全
- パスワードリセット後、反映に 30-60 秒かかる場合がある
