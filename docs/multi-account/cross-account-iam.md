# クロスアカウント IAM ロール設計

> マルチアカウント環境における IAM ロール引き受けチェーンの設計と実装

## 概要

本ドキュメントでは、FSxN S3AP Serverless Patterns のマルチアカウント環境における IAM ロール設計を定義する。全クロスアカウントロールに External ID 条件と Permission Boundary を適用し、最小権限原則と完全な監査証跡を実現する。

### ロール引き受けチェーン

```
Workload Account Lambda
  → sts:AssumeRole (External ID required)
    → Storage Account Cross-Account Role
      → S3 Access Point → FSx ONTAP Volume
```

---

## ロール命名規則

### 命名パターン

```
{ProjectPrefix}-{AccountType}-{ResourceAccess}-role
```

| 要素 | 説明 | 例 |
|---|---|---|
| `ProjectPrefix` | プロジェクト識別子 | `fsxn-s3ap` |
| `AccountType` | ロールが存在するアカウントタイプ | `workload`, `storage`, `shared`, `management` |
| `ResourceAccess` | アクセス対象リソース | `storage-access`, `readonly`, `admin` |

### ロール一覧

| ロール名 | アカウント | 用途 |
|---|---|---|
| `fsxn-s3ap-workload-storage-access-role` | Storage | Workload Lambda → S3 AP アクセス |
| `fsxn-s3ap-shared-workload-readonly-role` | Workload | Shared Services → Workload 読み取り |
| `fsxn-s3ap-management-admin-role` | Target | Management → 管理操作 |
| `fsxn-s3ap-shared-metric-delivery-role` | Shared Services | Workload → メトリクス配信 |
| `fsxn-s3ap-stacksets-admin-role` | Management | StackSets 管理 |
| `fsxn-s3ap-stacksets-execution-role` | Target | StackSets 実行 |

---

## External ID 条件

### 目的

External ID は **Confused Deputy Problem（混乱した代理問題）** を防止するために使用する。第三者が自身のアカウントからターゲットロールを引き受けることを防ぐ。

### 設計原則

1. **アカウントペアごとに一意**: 同じ External ID を複数のペアで共有しない
2. **推測困難**: UUID v4 形式を推奨（例: `a1b2c3d4-e5f6-7890-abcd-ef1234567890`）
3. **定期ローテーション**: 90 日ごとのローテーションを推奨
4. **安全な保管**: AWS Secrets Manager で管理

### Trust Policy テンプレート

#### Workload → Storage ロール

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowWorkloadAccountAssume",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::WORKLOAD_ACCOUNT_ID:root"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "EXTERNAL_ID_VALUE"
        }
      }
    }
  ]
}
```

#### Shared Services → Workload ロール

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowSharedServicesAssume",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::SHARED_SERVICES_ACCOUNT_ID:root"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "EXTERNAL_ID_VALUE"
        }
      }
    }
  ]
}
```

#### Management → Administration ロール

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowManagementAccountAssume",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::MANAGEMENT_ACCOUNT_ID:root"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "EXTERNAL_ID_VALUE"
        }
      }
    }
  ]
}
```

---

## Permission Boundary 定義

### 目的

Permission Boundary は、クロスアカウントロールが付与できる最大権限を制限する。ロールのポリシーが Permission Boundary を超える権限を付与しても、実効権限は Boundary 内に制限される。

### 共通 Permission Boundary

全クロスアカウントロールに適用する共通の Permission Boundary:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowS3APOperations",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket",
        "s3:GetObjectVersion",
        "s3:GetObjectTagging",
        "s3:PutObjectTagging"
      ],
      "Resource": [
        "arn:aws:s3:*:*:accesspoint/*",
        "arn:aws:s3:*:*:accesspoint/*/object/*"
      ]
    },
    {
      "Sid": "AllowObservability",
      "Effect": "Allow",
      "Action": [
        "cloudwatch:*",
        "logs:*",
        "xray:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "AllowSTS",
      "Effect": "Allow",
      "Action": [
        "sts:AssumeRole",
        "sts:GetCallerIdentity"
      ],
      "Resource": "*"
    },
    {
      "Sid": "DenyIAMEscalation",
      "Effect": "Deny",
      "Action": [
        "iam:CreateUser",
        "iam:CreateRole",
        "iam:DeleteRole",
        "iam:AttachRolePolicy",
        "iam:DetachRolePolicy",
        "iam:PutRolePolicy",
        "iam:DeleteRolePolicy",
        "iam:UpdateAssumeRolePolicy",
        "iam:CreatePolicy",
        "iam:DeletePolicy"
      ],
      "Resource": "*"
    },
    {
      "Sid": "DenyOrganizationsAccess",
      "Effect": "Deny",
      "Action": "organizations:*",
      "Resource": "*"
    }
  ]
}
```

### 権限昇格の防止

Permission Boundary により以下の攻撃を防止:

| 攻撃パターン | 防止方法 |
|---|---|
| 新規ロール作成による権限昇格 | `iam:CreateRole` を Deny |
| ポリシー変更による権限拡大 | `iam:AttachRolePolicy` を Deny |
| Trust Policy 変更 | `iam:UpdateAssumeRolePolicy` を Deny |
| Organization 操作 | `organizations:*` を Deny |

---

## CloudTrail イベントパターン

### ロール引き受け監視

全クロスアカウントロールの引き受けイベントを EventBridge で監視:

```json
{
  "source": ["aws.sts"],
  "detail-type": ["AWS API Call via CloudTrail"],
  "detail": {
    "eventSource": ["sts.amazonaws.com"],
    "eventName": ["AssumeRole"],
    "requestParameters": {
      "roleArn": [
        {"prefix": "arn:aws:iam::ACCOUNT_ID:role/fsxn-s3ap-"}
      ]
    }
  }
}
```

### 監視すべきイベント

| イベント | CloudTrail フィールド | アクション |
|---|---|---|
| ロール引き受け成功 | `eventName: AssumeRole`, `errorCode: null` | ログ記録 |
| ロール引き受け失敗 | `eventName: AssumeRole`, `errorCode: AccessDenied` | アラート |
| External ID 不一致 | `errorMessage: "External ID does not match"` | 即座に調査 |
| 未知の Source IP | `sourceIPAddress` が許可リスト外 | アラート |
| 営業時間外のアクセス | `eventTime` が定義時間外 | アラート |

### アラート設定例

```yaml
# CloudWatch Alarm: 失敗した AssumeRole の検知
Type: AWS::CloudWatch::Alarm
Properties:
  AlarmName: fsxn-s3ap-failed-assume-role
  Namespace: AWS/CloudTrail
  MetricName: AssumeRoleFailures
  Statistic: Sum
  Period: 300
  EvaluationPeriods: 1
  Threshold: 3
  ComparisonOperator: GreaterThanOrEqualToThreshold
```

---

## CloudFormation テンプレート

リファレンス実装: [`shared/cfn/cross-account-roles.yaml`](../../shared/cfn/cross-account-roles.yaml)

### デプロイ手順

```bash
aws cloudformation deploy \
  --template-file shared/cfn/cross-account-roles.yaml \
  --stack-name fsxn-cross-account-roles \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    StorageAccountId=111111111111 \
    WorkloadAccountId=222222222222 \
    SharedServicesAccountId=333333333333 \
    ManagementAccountId=444444444444 \
    ExternalIdStorage=$(uuidgen) \
    ExternalIdSharedServices=$(uuidgen) \
    ExternalIdManagement=$(uuidgen)
```

---

## External ID ローテーション手順

### ローテーションプロセス

1. **新しい External ID を生成**
2. **Trust Policy を更新**: 新旧両方の External ID を許可
3. **全クライアントを更新**: 新しい External ID を使用するよう設定変更
4. **旧 External ID を削除**: Trust Policy から旧 ID を削除
5. **Secrets Manager を更新**: 新しい値を保存

### ゼロダウンタイムローテーション

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"AWS": "arn:aws:iam::WORKLOAD_ACCOUNT:root"},
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": [
            "OLD_EXTERNAL_ID",
            "NEW_EXTERNAL_ID"
          ]
        }
      }
    }
  ]
}
```

---

## セキュリティベストプラクティス

### 必須要件

1. **全ロールに External ID を設定**: 例外なし
2. **全ロールに Permission Boundary を適用**: 権限昇格防止
3. **MaxSessionDuration を制限**: 最大 1 時間（3600 秒）
4. **CloudTrail 監視を有効化**: 全 AssumeRole イベントを記録
5. **定期的な棚卸し**: 未使用ロールの検出と削除

### 推奨事項

- External ID は Secrets Manager で管理
- IAM Access Analyzer で未使用権限を検出
- SCP で Organization レベルの制限を追加
- GuardDuty で異常なロール引き受けパターンを検知

---

## 関連ドキュメント

- [Cross-Account S3 AP アクセスパターン](./cross-account-s3ap.md)
- [AWS RAM リソース共有](./ram-sharing.md)
- [Shared Services アーキテクチャ](./shared-services-architecture.md)
- [StackSets デプロイガイド](./stacksets-deployment.md)
