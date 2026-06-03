# S3 Access Points for FSx for ONTAP — 二段階認可モデル

🌐 **Language / 言語**: [日本語](s3ap-authorization-model.md) | [English](s3ap-authorization-model.en.md)

## 概要

Amazon S3 Access Points for FSx for ONTAP は **デュアルレイヤー認可モデル** を採用しています。S3 API 経由のリクエストが成功するには、AWS 側の認可とファイルシステム側の認可の **両方** が許可する必要があります。

> **設計原則**: S3 API はファイルシステムのセマンティクスを除去しません。S3 Access Point を経由しても、ボリューム上のファイルアクセス権限は引き続き適用されます。

## 認可フロー

```
┌─────────────────────────────────────────────────────────────┐
│                    S3 API Request                            │
│            (GetObject / PutObject / ListObjectsV2)          │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: AWS-side Authorization                            │
│                                                             │
│  以下のすべてのポリシーが評価され、すべてが許可する必要がある:  │
│  • IAM identity-based policy（呼び出し元の権限）             │
│  • S3 Access Point resource policy                          │
│  • VPC endpoint policy（VPC 制限の場合）                     │
│  • Service Control Policies (SCP)                           │
│                                                             │
│  → いずれかが Deny → AccessDenied                           │
└─────────────────────────┬───────────────────────────────────┘
                          │ (すべて許可)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  Layer 2: File-system-side Authorization                    │
│                                                             │
│  Access Point に関連付けられたファイルシステム ID で認可:      │
│  • UNIX identity (UID) → UNIX セキュリティスタイルのボリューム │
│    - mode-bits または NFSv4 ACLs で制御                      │
│  • Windows identity (domain\user) → NTFS スタイルのボリューム │
│    - Windows ACLs で制御                                     │
│                                                             │
│  → ファイルシステムユーザーの権限がアクセスレベルを決定        │
└─────────────────────────────────────────────────────────────┘
```

## Layer 1: AWS-side Authorization

### 評価されるポリシー

| ポリシータイプ | 説明 | 設定場所 |
|--------------|------|---------|
| IAM identity-based policy | 呼び出し元（Lambda Role 等）の権限 | IAM Console |
| S3 Access Point resource policy | AP 自体のリソースポリシー | `s3control put-access-point-policy` |
| VPC endpoint policy | VPC 制限 AP の場合のエンドポイントポリシー | VPC Console |
| Service Control Policies | Organizations レベルの制御 | AWS Organizations |

### IAM ポリシーの ARN 形式

S3 Access Points for FSx for ONTAP では、通常の S3 バケット ARN とは異なる形式を使用します:

```json
{
  "Effect": "Allow",
  "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
  "Resource": "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-fsxn-ap"
},
{
  "Effect": "Allow",
  "Action": ["s3:GetObject", "s3:PutObject"],
  "Resource": "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-fsxn-ap/object/*"
}
```

> **注意**: S3 AP エイリアス（`xxx-ext-s3alias`）を `arn:aws:s3:::` 形式で使用しても IAM では認識されません。必ず `arn:aws:s3:{region}:{account}:accesspoint/{name}` 形式を使用してください。

## Layer 2: File-system-side Authorization

### ファイルシステム ID の役割

S3 Access Point 作成時に指定するファイルシステム ID が、すべての S3 API リクエストの認可に使用されます:

- **読み取り専用ユーザー** を関連付けた場合 → 読み取りリクエストのみ認可、書き込みはブロック
- **読み書きユーザー** を関連付けた場合 → 読み取り・書き込みの両方が認可

### セキュリティスタイルとの対応

| ボリュームのセキュリティスタイル | 使用する ID タイプ | 権限制御方式 |
|-------------------------------|-------------------|-------------|
| UNIX | UNIX identity (UID) | mode-bits / NFSv4 ACLs |
| NTFS | Windows identity (domain\user) | Windows ACLs |

### 重要な動作特性

1. **NFS/SMB アクセスへの影響なし**: S3 Access Point をアタッチしても、NFS/SMB 経由の既存アクセスは一切変更されません。AP ポリシーの制限は AP 経由のリクエストにのみ適用されます。

2. **Block Public Access**: FSx for ONTAP にアタッチされた S3 AP は常に Block Public Access が有効であり、変更できません。

3. **MISCONFIGURED 状態**: ファイルシステム ID が解決できなくなった場合、AP は `MISCONFIGURED` 状態に遷移します。Amazon FSx が定期的にチェックし、問題解決時に自動的に `AVAILABLE` に戻ります。

## Least-Privilege 設計ガイドライン

最小権限の原則を適用するには、**両方のレイヤー** でアクセスを制限する必要があります:

### Layer 1 での制限例

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"AWS": "arn:aws:iam::123456789012:role/ProcessingLambdaRole"},
      "Action": ["s3:GetObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-fsxn-ap",
        "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-fsxn-ap/object/*"
      ],
      "Condition": {
        "StringEquals": {"aws:PrincipalOrgID": "o-xxxxx"}
      }
    }
  ]
}
```

### Layer 2 での制限例

- 処理対象ディレクトリのみに読み取り権限を持つ専用ユーザーを作成
- root (UID 0) の使用を避ける（全ファイルへのアクセスが許可されるため）
- NTFS 環境では、必要最小限の AD グループメンバーシップを持つサービスアカウントを使用

## 本プロジェクトでの適用

本リポジトリの 28 UC + 6 FC パターンでは、以下の設計を採用しています:

| コンポーネント | Layer 1 設計 | Layer 2 設計 |
|--------------|-------------|-------------|
| Discovery Lambda | ListBucket + GetObject のみ | 対象ボリュームの読み取り権限を持つ UNIX ユーザー |
| Processing Lambda | GetObject のみ（入力読み取り） | 同上 |
| Output Lambda (FSXN_S3AP mode) | PutObject 追加 | 出力ディレクトリへの書き込み権限を持つユーザー |

## トラブルシューティング

| 症状 | 可能性のある原因 | 確認ポイント |
|------|----------------|------------|
| IAM で許可しているのに AccessDenied | ファイルシステム ID の権限不足 | S3 AP に紐づく UNIX/Windows ID のファイル/ディレクトリ権限を確認 |
| ListBucket は成功するが GetObject で AccessDenied | ファイル ACL / export policy / security style の不一致 | 対象ファイルの実効権限を `ls -la` (UNIX) or `icacls` (NTFS) で確認 |
| PutObject が失敗する | ディレクトリ書き込み権限不足 | 親ディレクトリの書き込み権限を確認。ファイルシステム ID が read-only の場合は書き込み不可 |
| VPC 内 Lambda からタイムアウト | Internet Origin AP に S3 Gateway EP 経由でアクセス | Lambda を VPC 外に配置、または NAT Gateway 経由に変更 |
| MISCONFIGURED 状態 | ファイルシステム ID が解決不能 | UNIX UID が存在するか、Windows ユーザーが AD で有効か確認 |
| 特定ディレクトリのみ AccessDenied | ONTAP export policy の制限 | SVM の export policy rules を確認（NFS export と S3 AP は別経路だが同じ volume permission） |

### 確認コマンド例

> **注意**: 以下のコマンドはすべて読み取り専用（read-only）のトラブルシューティング用です。環境に変更を加えるものではありません。

```bash
# === AWS CLI ===

# 1. S3 AP resource policy の確認
aws s3control get-access-point-policy \
  --account-id <ACCOUNT_ID> \
  --name <AP_NAME>

# 2. IAM Policy Simulator で権限確認
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::<ACCOUNT_ID>:role/<LAMBDA_ROLE> \
  --action-names s3:GetObject s3:ListBucket \
  --resource-arns "arn:aws:s3:<REGION>:<ACCOUNT_ID>:accesspoint/<AP_NAME>/object/*"

# 3. CloudTrail で AccessDenied イベント確認
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=GetObject \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%SZ) \
  --query 'Events[?contains(CloudTrailEvent, `AccessDenied`)]'

# 4. S3 AP に紐づく filesystem identity 確認
aws fsx describe-data-repository-associations \
  --query 'Associations[?AssociationType==`S3_ACCESS_POINT`].{Name:ResourceARN,Identity:S3}'

# === ONTAP CLI ===

# 5. ONTAP 側: 対象パスの ACL / permission 確認 (UNIX)
# SSH or ONTAP CLI 経由
vserver security file-directory show -vserver <SVM_NAME> -path <PATH>

# === VPC / Network ===

# 6. VPC Endpoint policy 確認
aws ec2 describe-vpc-endpoints \
  --filters Name=service-name,Values=com.amazonaws.<REGION>.s3 \
  --query 'VpcEndpoints[*].{Id:VpcEndpointId,Policy:PolicyDocument}'
```

## 参考リンク

- [Managing access point access — Amazon FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-ap-manage-access-fsxn.html)
- [Accessing your data via Amazon S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [Enabling AI-powered analytics on enterprise file data (AWS Storage Blog)](https://aws.amazon.com/blogs/storage/enabling-ai-powered-analytics-on-enterprise-file-data-configuring-s3-access-points-for-amazon-fsx-for-netapp-ontap-with-active-directory/)
