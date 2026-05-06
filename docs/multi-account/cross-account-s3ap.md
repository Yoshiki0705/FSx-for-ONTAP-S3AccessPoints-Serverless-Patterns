# クロスアカウント S3 Access Point アクセスパターン

> FSx for NetApp ONTAP S3 Access Points を活用したマルチアカウントアクセス設計

## 概要

本ドキュメントでは、ワークロードアカウントの Lambda 関数が中央ストレージアカウントに配置された S3 Access Point（FSx ONTAP）にセキュアにアクセスするためのクロスアカウントパターンを定義する。

### 対象読者

- クラウドアーキテクト
- セキュリティエンジニア
- プラットフォームエンジニア

### 前提条件

- AWS Organizations によるマルチアカウント構成
- FSx for NetApp ONTAP ファイルシステムがストレージアカウントにデプロイ済み
- S3 Access Point が FSx ONTAP ボリュームに対して作成済み

---

## アーキテクチャ

### アクセスフロー

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Workload Account (987654321098)                  │
│                                                                     │
│  ┌──────────────┐    sts:AssumeRole     ┌─────────────────────┐    │
│  │ Lambda       │ ─────────────────────→ │ STS                 │    │
│  │ Function     │    (External ID)       │                     │    │
│  └──────┬───────┘                        └─────────────────────┘    │
│         │                                                           │
└─────────┼───────────────────────────────────────────────────────────┘
          │ Temporary Credentials
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Storage Account (123456789012)                   │
│                                                                     │
│  ┌──────────────────┐         ┌──────────────────────────────┐     │
│  │ Cross-Account    │         │ S3 Access Point              │     │
│  │ IAM Role         │ ──────→ │ (fsxn-s3ap-workload-         │     │
│  │ (with External   │         │  storage-access-role)        │     │
│  │  ID condition)   │         └──────────────┬───────────────┘     │
│  └──────────────────┘                        │                     │
│                                              ▼                     │
│                              ┌──────────────────────────────┐      │
│                              │ FSx for NetApp ONTAP         │      │
│                              │ Volume                        │      │
│                              └──────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────┘
```

### コンポーネント構成

| コンポーネント | アカウント | 役割 |
|---|---|---|
| Lambda Function | Workload | ファイル処理の実行 |
| Lambda Execution Role | Workload | AssumeRole 権限を保持 |
| Cross-Account IAM Role | Storage | S3 AP アクセス権限を保持 |
| S3 Access Point | Storage | FSx ONTAP ボリュームへのアクセスゲートウェイ |
| FSx ONTAP Volume | Storage | 実データの格納先 |
| Permission Boundary | Both | 最大権限の制限 |

---

## IAM ポリシー構造

### 1. リソースベースポリシー（S3 Access Point）

S3 Access Point に設定するリソースベースポリシー。ストレージアカウント内のクロスアカウントアクセスロールからのアクセスを許可する。

> **注意**: Principal にはストレージアカウント側のロール（ワークロードアカウントが AssumeRole で引き受けるロール）を指定する。ワークロードアカウントのロールを直接指定するパターンも技術的には可能だが、External ID による Confused Deputy 防止を実現するには AssumeRole パターンが推奨される。

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowCrossAccountAccess",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::123456789012:role/fsxn-s3ap-workload-storage-access-role"
      },
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket",
        "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-fsxn-ap",
        "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-fsxn-ap/object/*"
      ]
    }
  ]
}
```

### 2. ID ベースポリシー（Lambda 実行ロール）

ワークロードアカウントの Lambda 実行ロールに付与するポリシー。クロスアカウントロールの引き受けのみを許可する。

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowAssumeStorageRole",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::123456789012:role/fsxn-s3ap-workload-storage-access-role",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "unique-external-id-value"
        }
      }
    }
  ]
}
```

### 3. Trust Policy（クロスアカウントロール）

ストレージアカウントのクロスアカウントロールに設定する信頼ポリシー。

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowWorkloadAccountAssume",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::987654321098:root"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "unique-external-id-value"
        }
      }
    }
  ]
}
```

### 4. ONTAP Export Policy 考慮事項

FSx ONTAP の Export Policy は S3 Access Point 経由のアクセスに対して以下の設定が必要:

| 設定項目 | 値 | 説明 |
|---|---|---|
| Protocol | `s3` | S3 プロトコルを許可 |
| Client Match | S3 AP サブネット CIDR | VPC 内の S3 AP エンドポイントサブネット |
| RO Rule | `any` | 読み取りアクセスルール |
| RW Rule | `any` | 書き込みアクセスルール |
| Superuser | `none` | root アクセスの制限 |

```bash
# ONTAP CLI での Export Policy 設定例
vserver export-policy rule create \
  -vserver svm1 \
  -policyname s3ap_cross_account \
  -ruleindex 1 \
  -protocol s3 \
  -clientmatch 10.0.0.0/16 \
  -rorule any \
  -rwrule any \
  -superuser none
```

---

## シナリオ別設定

### シナリオ 1: 同一リージョン（Same-Region）

ワークロードアカウントとストレージアカウントが同一リージョン（ap-northeast-1）に存在する場合。

**特徴:**
- レイテンシが最小
- データ転送コストなし（同一リージョン内）
- 標準的な S3 API エンドポイントを使用

**Lambda コード例:**

```python
import boto3

def get_cross_account_client(role_arn: str, external_id: str, region: str = "ap-northeast-1"):
    """クロスアカウントロールを引き受けて S3 クライアントを取得する。"""
    sts_client = boto3.client("sts")
    response = sts_client.assume_role(
        RoleArn=role_arn,
        RoleSessionName="fsxn-s3ap-cross-account-session",
        ExternalId=external_id,
        DurationSeconds=3600,
    )
    credentials = response["Credentials"]
    return boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=credentials["AccessKeyId"],
        aws_secret_access_key=credentials["SecretAccessKey"],
        aws_session_token=credentials["SessionToken"],
    )

def handler(event, context):
    """同一リージョンでのクロスアカウント S3 AP アクセス。"""
    s3_client = get_cross_account_client(
        role_arn="arn:aws:iam::123456789012:role/fsxn-s3ap-workload-storage-access-role",
        external_id="unique-external-id-value",
    )
    # S3 Access Point 経由でオブジェクトを取得
    response = s3_client.get_object(
        Bucket="arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-fsxn-ap",
        Key="data/input-file.csv",
    )
    return {"statusCode": 200, "body": response["Body"].read().decode("utf-8")}
```

### シナリオ 2: クロスリージョン（Cross-Region）

ワークロードアカウント（us-east-1）からストレージアカウント（ap-northeast-1）の S3 AP にアクセスする場合。

**特徴:**
- リージョン間データ転送コストが発生
- レイテンシが増加（リージョン間通信）
- S3 クライアントのリージョン指定が必須

**追加考慮事項:**
- VPC Endpoint はリージョン固有のため、クロスリージョンでは使用不可
- インターネット経由または VPN/Direct Connect 経由でアクセス
- データ転送量に応じたコスト最適化が必要

**Lambda コード例:**

```python
def handler(event, context):
    """クロスリージョンでのクロスアカウント S3 AP アクセス。"""
    # ストレージアカウントのリージョンを指定
    s3_client = get_cross_account_client(
        role_arn="arn:aws:iam::123456789012:role/fsxn-s3ap-workload-storage-access-role",
        external_id="unique-external-id-value",
        region="ap-northeast-1",  # ストレージアカウントのリージョン
    )
    # クロスリージョンアクセス
    response = s3_client.get_object(
        Bucket="arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-fsxn-ap",
        Key="data/input-file.csv",
    )
    return {"statusCode": 200, "body": "Cross-region access successful"}
```

---

## セキュリティ分析

### Trust Boundary（信頼境界）の定義

```
┌─────────────────────────────────────────────────────────────┐
│ Trust Boundary 1: AWS Organization                          │
│                                                             │
│  ┌───────────────────┐    ┌───────────────────────────┐    │
│  │ Trust Boundary 2: │    │ Trust Boundary 3:         │    │
│  │ Workload Account  │    │ Storage Account           │    │
│  │                   │    │                           │    │
│  │ • Lambda Function │    │ • S3 Access Point         │    │
│  │ • Lambda Role     │    │ • Cross-Account Role      │    │
│  │                   │    │ • FSx ONTAP Volume        │    │
│  └───────────────────┘    └───────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Least-Privilege（最小権限）原則

| レイヤー | 制限方法 | 詳細 |
|---|---|---|
| Lambda Role | Identity Policy | `sts:AssumeRole` のみ、特定ロール ARN に限定 |
| Cross-Account Role | Trust Policy | External ID 条件、特定アカウントのみ許可 |
| Cross-Account Role | Identity Policy | S3 AP 操作のみ、特定 AP ARN に限定 |
| Permission Boundary | Managed Policy | S3 AP + CloudWatch Logs のみ許可 |
| S3 Access Point | Resource Policy | 特定ロールからのアクセスのみ許可 |
| ONTAP Export Policy | Network + Protocol | S3 プロトコル、特定サブネットのみ |

### External ID による Confused Deputy 防止

External ID は以下の目的で使用する:

1. **混乱した代理問題の防止**: 第三者が自身のアカウントからストレージアカウントのロールを引き受けることを防止
2. **テナント分離**: マルチテナント環境で各テナントのアクセスを分離
3. **監査証跡**: CloudTrail ログで External ID を確認可能

**推奨事項:**
- External ID は UUID v4 形式を推奨
- アカウントペアごとに一意の External ID を生成
- External ID は AWS Secrets Manager で管理

### CloudTrail 監査設定

クロスアカウントロール引き受けイベントを監視するための EventBridge ルール:

```json
{
  "source": ["aws.sts"],
  "detail-type": ["AWS API Call via CloudTrail"],
  "detail": {
    "eventSource": ["sts.amazonaws.com"],
    "eventName": ["AssumeRole"],
    "requestParameters": {
      "roleArn": ["arn:aws:iam::123456789012:role/fsxn-s3ap-workload-storage-access-role"]
    }
  }
}
```

**監視すべきイベント:**

| イベント | 意味 | アクション |
|---|---|---|
| `AssumeRole` 成功 | 正常なクロスアカウントアクセス | ログ記録 |
| `AssumeRole` 失敗（AccessDenied） | 不正なアクセス試行 | アラート発火 |
| 未知の Source IP からの `AssumeRole` | 潜在的な不正アクセス | 即座に調査 |
| 通常時間外の `AssumeRole` | 異常なアクセスパターン | アラート発火 |

---

## CloudFormation テンプレート

リファレンス実装: [`shared/cfn/cross-account-s3ap-policy.yaml`](../../shared/cfn/cross-account-s3ap-policy.yaml)

### デプロイ手順

```bash
# 1. ストレージアカウントでデプロイ
aws cloudformation deploy \
  --template-file shared/cfn/cross-account-s3ap-policy.yaml \
  --stack-name fsxn-cross-account-s3ap \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    StorageAccountId=123456789012 \
    WorkloadAccountId=987654321098 \
    S3AccessPointArn=arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-fsxn-ap \
    ExternalId=$(uuidgen)

# 2. S3 Access Point にリソースベースポリシーを設定
aws s3control put-access-point-policy \
  --account-id 123456789012 \
  --name my-fsxn-ap \
  --policy file://s3ap-resource-policy.json
```

---

## 運用ガイダンス

### ローテーション

- **External ID**: 90 日ごとにローテーション推奨
- **一時認証情報**: 最大 1 時間（`DurationSeconds=3600`）
- **ローテーション手順**: 新旧 External ID を並行して許可 → 全ワークロード更新 → 旧 ID 削除

### トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| AccessDenied on AssumeRole | External ID 不一致 | External ID の値を確認 |
| AccessDenied on S3 GetObject | S3 AP ポリシー未設定 | リソースベースポリシーを確認 |
| Slow response | クロスリージョンアクセス | リージョン配置を見直し |
| Timeout | VPC Endpoint 未設定 | S3 VPC Endpoint を追加 |

---

## 関連ドキュメント

- [Cross-Account IAM ロール設計](./cross-account-iam.md)
- [AWS RAM リソース共有](./ram-sharing.md)
- [Shared Services アーキテクチャ](./shared-services-architecture.md)
- [StackSets デプロイガイド](./stacksets-deployment.md)
