# AWS RAM による FSx ONTAP リソース共有

> AWS Resource Access Manager を活用したマルチアカウントリソース共有パターン

## 概要

本ドキュメントでは、AWS RAM (Resource Access Manager) を使用して FSx for NetApp ONTAP 関連リソースを複数アカウントで共有するパターンを定義する。

### 重要な制限事項

> **注意**: FSx for NetApp ONTAP の S3 Access Points は、現時点で AWS RAM による直接共有をサポートしていません。本ドキュメントでは、RAM で共有可能なリソース（VPC サブネット等）と、代替パターン（クロスアカウント IAM）を組み合わせたアプローチを説明します。

---

## RAM 共有可能リソースの整理

### FSx ONTAP 関連リソースの RAM 対応状況

| リソースタイプ | RAM 共有 | 代替パターン |
|---|---|---|
| VPC Subnet | ✅ 対応 | — |
| FSx File System | ❌ 非対応 | クロスアカウント IAM |
| FSx Volume | ❌ 非対応 | クロスアカウント IAM |
| S3 Access Point | ❌ 非対応 | S3 AP リソースポリシー + IAM |
| Transit Gateway | ✅ 対応 | — |
| Route 53 Resolver Rule | ✅ 対応 | — |

### 推奨アーキテクチャ

RAM で共有可能なネットワークリソースと、クロスアカウント IAM パターンを組み合わせる:

```
┌─────────────────────────────────────────────────────────────────┐
│ Management Account                                              │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ AWS RAM Resource Share                                   │   │
│  │  • VPC Subnets (FSx ONTAP 配置サブネット)               │   │
│  │  • Transit Gateway                                       │   │
│  │  • Route 53 Resolver Rules                              │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
          │ RAM Sharing
          ▼
┌─────────────────────────────────────────────────────────────────┐
│ Workload Accounts                                               │
│                                                                 │
│  • 共有サブネットにリソース配置可能                             │
│  • クロスアカウント IAM で S3 AP にアクセス                    │
│  • Transit Gateway 経由で FSx ONTAP に接続                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## CloudFormation テンプレート

リファレンス実装: [`shared/cfn/ram-resource-share.yaml`](../../shared/cfn/ram-resource-share.yaml)

### Organization 共有モード

AWS Organizations 全体でリソースを共有する場合:

```bash
aws cloudformation deploy \
  --template-file shared/cfn/ram-resource-share.yaml \
  --stack-name fsxn-ram-share \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    ShareName=fsxn-shared-resources \
    EnableOrganizationSharing=true \
    OrganizationArn=arn:aws:organizations::123456789012:organization/o-example \
    FsxSubnetIds=subnet-abc123,subnet-def456 \
    EnableSubnetSharing=true
```

### 個別アカウント共有モード

特定のアカウント ID にのみ共有する場合:

```bash
aws cloudformation deploy \
  --template-file shared/cfn/ram-resource-share.yaml \
  --stack-name fsxn-ram-share \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    ShareName=fsxn-shared-resources \
    EnableOrganizationSharing=false \
    TargetAccountIds=111111111111,222222222222,333333333333 \
    FsxSubnetIds=subnet-abc123 \
    EnableSubnetSharing=true
```

---

## 代替パターン: S3 Access Point クロスアカウントアクセス

FSx ONTAP S3 Access Points が RAM 非対応のため、以下の代替パターンを使用する:

### パターン概要

1. **ストレージアカウント**: S3 Access Point にリソースベースポリシーを設定
2. **ストレージアカウント**: クロスアカウント IAM ロールを作成（External ID 条件付き）
3. **ワークロードアカウント**: Lambda 実行ロールに AssumeRole 権限を付与
4. **ワークロードアカウント**: Lambda が AssumeRole → S3 AP アクセス

詳細は [Cross-Account S3 AP アクセスパターン](./cross-account-s3ap.md) を参照。

---

## 運用ガイダンス

### アカウントの追加

#### Organization 共有の場合

新しいアカウントが Organization に参加すると自動的に共有リソースにアクセス可能になる。

```bash
# 確認コマンド
aws ram get-resource-share-associations \
  --association-type PRINCIPAL \
  --resource-share-arns arn:aws:ram:ap-northeast-1:123456789012:resource-share/xxx
```

#### 個別アカウント共有の場合

```bash
# 新しいアカウントを追加
aws ram associate-resource-share \
  --resource-share-arn arn:aws:ram:ap-northeast-1:123456789012:resource-share/xxx \
  --principals 444444444444

# 追加されたアカウントで招待を承認
aws ram accept-resource-share-invitation \
  --resource-share-invitation-arn arn:aws:ram:ap-northeast-1:444444444444:resource-share-invitation/xxx
```

### アカウントの削除

```bash
# アカウントを共有から削除
aws ram disassociate-resource-share \
  --resource-share-arn arn:aws:ram:ap-northeast-1:123456789012:resource-share/xxx \
  --principals 444444444444
```

**注意事項:**
- 削除前に、対象アカウントが共有リソースを使用していないことを確認
- 共有サブネットに配置されたリソース（ENI 等）がある場合、先に削除が必要
- 削除は即座に反映される（猶予期間なし）

### 使用量モニタリング

#### CloudWatch メトリクス

テンプレートで作成されるダッシュボードで以下を監視:

- Resource Share Invitations 数
- 共有リソースへのアクセスパターン
- アカウント別の使用状況

#### AWS Config ルール（推奨）

```yaml
# RAM 共有の設定変更を検知する Config ルール
Type: AWS::Config::ConfigRule
Properties:
  ConfigRuleName: ram-resource-share-compliance
  Source:
    Owner: AWS
    SourceIdentifier: RAM_RESOURCE_SHARE_COMPLIANCE
```

### コスト配分

#### タグベースのコスト配分

テンプレートでは `SharedResourceCostCenter` タグを使用してコスト配分を実現:

| タグキー | 値の例 | 用途 |
|---|---|---|
| `SharedResourceCostCenter` | `shared-infrastructure` | 共有インフラコスト |
| `WorkloadAccount` | `111111111111` | アカウント別コスト追跡 |
| `UseCase` | `uc09-autonomous-driving` | ユースケース別コスト |

#### コスト配分の考え方

```
┌─────────────────────────────────────────────────────────┐
│ FSx ONTAP コスト（ストレージアカウント負担）            │
│  • ファイルシステム料金                                 │
│  • ストレージ容量料金                                   │
│  • バックアップ料金                                     │
├─────────────────────────────────────────────────────────┤
│ データ転送コスト（使用アカウント負担）                  │
│  • S3 AP 経由のデータ転送                              │
│  • クロスリージョン転送（該当する場合）                 │
├─────────────────────────────────────────────────────────┤
│ コンピュートコスト（ワークロードアカウント負担）        │
│  • Lambda 実行料金                                      │
│  • Step Functions 実行料金                              │
└─────────────────────────────────────────────────────────┘
```

---

## FSx ONTAP リソース共有の制限事項

### 現在の制限

1. **S3 Access Points**: RAM 非対応。クロスアカウント IAM パターンを使用
2. **File System**: RAM 非対応。VPC サブネット共有 + NFS/SMB マウントで代替
3. **Volume**: RAM 非対応。S3 AP 経由またはネットワーク接続で代替
4. **SVM (Storage Virtual Machine)**: RAM 非対応

### 将来の対応可能性

AWS は継続的に RAM 対応リソースを拡大している。FSx ONTAP リソースが RAM 対応になった場合:

1. テンプレートの `ResourceArns` に FSx リソース ARN を追加
2. クロスアカウント IAM パターンから RAM 共有パターンに移行
3. リソースベースポリシーの簡素化が可能

---

## セキュリティ考慮事項

### Organization 共有のリスク

- Organization 内の全アカウントがアクセス可能になる
- OU (Organizational Unit) 単位での制限は RAM 単体では不可
- SCP (Service Control Policy) と組み合わせてアクセス制御を強化

### 推奨セキュリティ設定

1. **AllowExternalPrincipals: false** — Organization 外部への共有を禁止
2. **SCP による制限** — 特定 OU のみ RAM 共有を利用可能に制限
3. **CloudTrail 監視** — RAM API コールを監視
4. **定期的な棚卸し** — 不要な共有を定期的に削除

---

## 関連ドキュメント

- [Cross-Account S3 AP アクセスパターン](./cross-account-s3ap.md)
- [Cross-Account IAM ロール設計](./cross-account-iam.md)
- [Shared Services アーキテクチャ](./shared-services-architecture.md)
- [StackSets デプロイガイド](./stacksets-deployment.md)
