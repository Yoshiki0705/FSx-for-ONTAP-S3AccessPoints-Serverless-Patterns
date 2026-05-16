# FSx for ONTAP S3 Access Points — 仕様・制約・トラブルシューティング

**作成日**: 2026-05-16
**最終更新**: 2026-05-16
**対象**: 全 UC テンプレート、shared モジュール、Canary/Lambda 実装者

---

## 概要

FSx for ONTAP S3 Access Point（以下 S3 AP）は、ONTAP ボリューム上のファイルを Amazon S3 API 経由で**読み取り専用**アクセスするためのブリッジ機能。本プロジェクトの全 17 UC で S3 AP 経由のファイル読み取りを使用する。

**重要な前提**:
- S3 AP は**読み取り専用**。`PutObject` は使用不可
- 書き込みは NFS/SMB プロトコル経由でのみ可能
- 通常の S3 バケットとは異なるデータプレーンを使用する

---

## 1. 認証モデル（デュアルレイヤー）

S3 AP へのアクセスには **2 つのレイヤーの両方** が許可する必要がある。

### レイヤー 1: AWS IAM 認証

| 要素 | 説明 |
|------|------|
| Identity-based policy | 呼び出し元 IAM ロール/ユーザーのポリシー |
| Resource policy | S3 AP 自体に設定するリソースポリシー（デフォルト未設定） |

### レイヤー 2: ファイルシステム認証

| ボリュームスタイル | 使用する identity | 認可方式 |
|------------------|-----------------|---------|
| UNIX | UNIX UID/GID | mode-bits / NFSv4 ACL |
| NTFS | Windows AD ユーザー | Windows ACL |

S3 AP 作成時に指定した file system identity の権限でファイルアクセスが認可される。

---

## 2. IAM ポリシー ARN 形式

### 正しい ARN 形式

```
# ListBucket（バケットレベル操作）
arn:aws:s3:{region}:{account-id}:accesspoint/{access-point-name}

# GetObject（オブジェクトレベル操作）
arn:aws:s3:{region}:{account-id}:accesspoint/{access-point-name}/object/*
```

### よくある間違い

```
# ❌ S3 AP エイリアスをバケット ARN として使用
arn:aws:s3:::fsxn-eda-s3ap-xxx-ext-s3alias

# ❌ GetBucketLocation を S3 AP に対して使用
Action: s3:GetBucketLocation  ← S3 AP では無効

# ❌ PutObject を FSx ONTAP S3 AP に対して使用
Action: s3:PutObject  ← 読み取り専用のため使用不可
```

### CloudFormation テンプレートでの正しい記述

```yaml
Parameters:
  S3AccessPointName:
    Type: String
    Description: S3 Access Point 名（エイリアスではない）

Resources:
  LambdaRole:
    Type: AWS::IAM::Role
    Properties:
      Policies:
        - PolicyName: S3APReadAccess
          PolicyDocument:
            Statement:
              - Sid: ListBucket
                Effect: Allow
                Action: s3:ListBucket
                Resource: !Sub "arn:aws:s3:${AWS::Region}:${AWS::AccountId}:accesspoint/${S3AccessPointName}"
              - Sid: GetObject
                Effect: Allow
                Action: s3:GetObject
                Resource: !Sub "arn:aws:s3:${AWS::Region}:${AWS::AccountId}:accesspoint/${S3AccessPointName}/object/*"
```

---

## 3. S3 AP リソースポリシー

デフォルトでは S3 AP にリソースポリシーは設定されていない。
IAM identity-based policy に加えて、S3 AP リソースポリシーの設定が必要な場合がある。

### 設定コマンド

```bash
aws s3control put-access-point-policy \
  --account-id <ACCOUNT_ID> \
  --name <AP_NAME> \
  --region ap-northeast-1 \
  --policy '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"AWS": "arn:aws:iam::<ACCOUNT_ID>:role/<ROLE_NAME>"},
      "Action": ["s3:ListBucket", "s3:GetObject"],
      "Resource": [
        "arn:aws:s3:ap-northeast-1:<ACCOUNT_ID>:accesspoint/<AP_NAME>",
        "arn:aws:s3:ap-northeast-1:<ACCOUNT_ID>:accesspoint/<AP_NAME>/object/*"
      ]
    }]
  }'
```

### 無効なアクション（MalformedPolicy エラー）

以下のアクションは S3 AP リソースポリシーで使用不可:
- `s3:GetBucketLocation`
- `s3:PutBucketPolicy`
- `s3:PutObject`（FSx ONTAP S3 AP の場合）

---

## 4. ネットワークアクセスの制約

### 最重要: FSx ONTAP S3 AP は通常の S3 Gateway VPC Endpoint では到達不可

| アクセス元 | 結果 | 理由 |
|-----------|------|------|
| VPC 外（Internet） | ✅ 動作 | NetworkOrigin=Internet の場合 |
| VPC 内 + S3 Gateway EP | ❌ タイムアウト | FSx データプレーンは S3 EP 経由でルーティングされない |
| VPC 内 + NAT Gateway | ✅ 動作 | インターネット経由で S3 AP エンドポイントに到達 |

### 根本原因

FSx ONTAP S3 AP は S3 サービスのデータプレーンではなく、**FSx ONTAP 固有のデータプレーン**を経由する。
S3 Gateway VPC Endpoint は通常の S3 バケットへのトラフィックのみルーティングし、FSx S3 AP のトラフィックは対象外。

### Lambda/Canary の推奨構成

| チェック対象 | VPC 設定 | 理由 |
|------------|---------|------|
| ONTAP REST API (/api/cluster) | VPC 内 | 管理 IP はプライベート |
| S3 AP (ListObjectsV2, GetObject) | VPC 外 or NAT Gateway 経由 | S3 AP データプレーンの制約 |

**推奨**: 2 つの Lambda/Canary に分離する
- Lambda A (VPC 内): ONTAP ヘルスチェック
- Lambda B (VPC 外): S3 AP ヘルスチェック

---

## 5. boto3 での使用方法

```python
import boto3

s3 = boto3.client("s3")

# S3 AP エイリアスを Bucket パラメータに渡す
# boto3 が内部的に S3 AP エンドポイントにルーティング
response = s3.list_objects_v2(
    Bucket="<S3_AP_ALIAS>",  # xxx-ext-s3alias 形式
    Prefix="path/to/files/",
    MaxKeys=100,
)

response = s3.get_object(
    Bucket="<S3_AP_ALIAS>",
    Key="path/to/file.pdf",
)
content = response["Body"].read()
response["Body"].close()

# ⚠️ ファイル内容をログや API レスポンスに含めないこと（機密データ保護）
```

---

## 6. トラブルシューティング

| 症状 | 原因 | 解決策 |
|------|------|--------|
| `AccessDenied` on ListObjectsV2 | IAM Resource ARN が間違い | `arn:aws:s3:{region}:{account}:accesspoint/{name}` 形式を使用 |
| `AccessDenied` (IAM 正しいのに) | S3 AP リソースポリシー未設定 | `s3control put-access-point-policy` で追加 |
| `ServiceUnavailable` | VPC 内からのアクセス | VPC 外実行 or NAT Gateway 経由 |
| `Connection timed out` (120s) | S3 Gateway EP 経由で FSx S3 AP に到達不可 | Lambda の VPC 設定を外す |
| `MalformedPolicy` | 無効なアクション使用 | ListBucket + GetObject のみ使用 |
| `PutObject` 失敗 | FSx ONTAP S3 AP は読み取り専用 | NFS/SMB 経由で書き込み |
| `MISCONFIGURED` 状態 | file system identity が解決不可 | ボリュームのマウント状態を確認 |

---

## 7. テスト設計の注意事項

### ユニットテスト（moto）
- `moto` の S3 モックを使用し、S3 AP エイリアスをバケット名として扱う
- IAM 認証のモックは不要（moto は認証をスキップ）

### 統合テスト（実環境）
- NetworkOrigin（Internet/VPC）を事前に確認: `aws s3control get-access-point`
- ヘルスマーカーファイルは NFS 経由で事前作成が必要
- VPC 内 Lambda のテストでは S3 AP アクセスがタイムアウトすることを想定

### Property-Based テスト
- S3 AP の読み取り専用制約をプロパティとして検証可能
- ファイル内容がレスポンスに漏洩しないことを検証（Property 16）

---

## 参考ドキュメント

- [Managing access point access (AWS Docs)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-ap-manage-access-fsxn.html)
- [Configuring IAM policies for access points (S3 Docs)](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-points-policies.html)
- [FSx ONTAP S3 AP announcement (AWS Blog)](https://aws.amazon.com/blogs/aws/amazon-fsx-for-netapp-ontap-now-integrates-with-amazon-s3-for-seamless-data-access/)
