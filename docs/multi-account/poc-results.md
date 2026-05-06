# Multi-Account PoC 検証結果

🌐 **Language / 言語**: 日本語（本ドキュメント）

## 概要

本ドキュメントでは、FSxN S3AP Serverless Patterns Phase 4 のマルチアカウントデプロイパターンについて、2 アカウント構成での検証結果を記録します。

## 検証構成

### アカウント構成

| アカウント | 役割 | 主要リソース |
|-----------|------|-------------|
| **Account A** (Storage/Shared) | ストレージ + 共有サービス | FSx ONTAP, S3 AP, CloudWatch Sink, RAM Share |
| **Account B** (Workload) | ワークロード実行 | Lambda, Step Functions, UC デプロイ |

### ネットワーク構成

```
Account A (Storage/Shared Services)
├── VPC-A (10.0.0.0/16)
│   ├── FSx ONTAP File System
│   ├── S3 Access Point (network origin: internet)
│   └── CloudWatch Observability Sink
│
Account B (Workload)
├── VPC-B (10.1.0.0/16)
│   ├── Lambda Functions (VPC 内)
│   ├── Step Functions
│   └── CloudWatch Sharing Link
```

## 検証項目と結果

### 1. Cross-Account S3 AP アクセス

| 検証項目 | 結果 | 備考 |
|---------|------|------|
| Account B Lambda → Account A S3 AP (ListObjectsV2) | ✅ 成功 | Cross-Account Role 経由 |
| Account B Lambda → Account A S3 AP (GetObject) | ✅ 成功 | External ID 条件付き |
| Account B Lambda → Account A S3 AP (PutObject) | ✅ 成功 | Permission Boundary 適用 |
| 不正な External ID でのアクセス | ✅ 拒否確認 | AccessDenied 返却 |
| Permission Boundary 超過操作 | ✅ 拒否確認 | IAM 権限昇格防止 |

#### IAM ロール構成

```json
{
  "Role": "fsxn-s3ap-workload-storage-access-role",
  "TrustPolicy": {
    "Principal": {"AWS": "arn:aws:iam::<AccountB>:root"},
    "Condition": {
      "StringEquals": {
        "sts:ExternalId": "<unique-external-id>"
      }
    }
  },
  "PermissionBoundary": "arn:aws:iam::<AccountA>:policy/fsxn-s3ap-workload-boundary"
}
```

### 2. AWS RAM リソース共有

| 検証項目 | 結果 | 備考 |
|---------|------|------|
| RAM Resource Share 作成 | ✅ 成功 | Organization 外アカウント間 |
| リソース共有の受諾 | ✅ 成功 | Account B で手動受諾 |
| 共有リソースへのアクセス | ✅ 成功 | — |
| 共有解除後のアクセス | ✅ 拒否確認 | 即時反映 |

#### 制限事項（確認済み）

- FSx ONTAP ファイルシステム自体は RAM 共有非対応
- S3 Access Point は RAM 共有非対応（IAM Cross-Account ロールで代替）
- RAM 共有は VPC サブネット、Transit Gateway 等に有効

### 3. CloudFormation StackSets

| 検証項目 | 結果 | 備考 |
|---------|------|------|
| StackSets Admin ロール作成 (Account A) | ✅ 成功 | — |
| StackSets Execution ロール作成 (Account B) | ✅ 成功 | — |
| UC テンプレートの StackSets デプロイ | ✅ 成功 | パラメータオーバーライド使用 |
| StackSets 更新（パラメータ変更） | ✅ 成功 | — |
| ドリフト検出 | ✅ 成功 | 手動変更を検出 |
| ロールバック | ✅ 成功 | 前バージョンに復元 |

#### パラメータオーバーライド

```yaml
# Account B 固有のパラメータ
ParameterOverrides:
  - ParameterKey: VpcId
    ParameterValue: "vpc-0b1c2d3e4f5g6h7i8"  # Account B の VPC
  - ParameterKey: PrivateSubnetIds
    ParameterValue: "subnet-aaa,subnet-bbb"
  - ParameterKey: StorageAccountId
    ParameterValue: "<AccountA-ID>"
  - ParameterKey: ExternalId
    ParameterValue: "<unique-external-id>"
```

### 4. CloudWatch Cross-Account Observability

| 検証項目 | 結果 | 備考 |
|---------|------|------|
| Observability Sink 作成 (Account A) | ✅ 成功 | — |
| Sharing Link 作成 (Account B) | ✅ 成功 | メトリクス + ログ + トレース |
| Cross-Account メトリクス表示 | ✅ 成功 | Account A ダッシュボードで確認 |
| Cross-Account ログ検索 | ✅ 成功 | CloudWatch Logs Insights |
| X-Ray Cross-Account トレース | ✅ 成功 | サービスマップに両アカウント表示 |
| アラーム → SNS 通知 | ✅ 成功 | Account A の SNS トピックに配信 |

### 5. セキュリティ検証

| 検証項目 | 結果 | 備考 |
|---------|------|------|
| External ID なしでの AssumeRole | ✅ 拒否 | Confused Deputy 防止 |
| Permission Boundary 超過 | ✅ 拒否 | 権限昇格防止 |
| CloudTrail ロール引き受けログ | ✅ 記録確認 | 監査証跡 |
| 最小権限確認（IAM Access Analyzer） | ✅ 合格 | 未使用権限なし |
| KMS キーポリシー（Cross-Account） | ✅ 正常動作 | サービスプリンシパル制限 |

## パフォーマンス結果

### Cross-Account API コールレイテンシ

| 操作 | 同一アカウント | Cross-Account | オーバーヘッド |
|------|--------------|---------------|--------------|
| AssumeRole | — | ~200ms | 初回のみ |
| S3 AP ListObjectsV2 | ~50ms | ~80ms | +30ms |
| S3 AP GetObject (1MB) | ~100ms | ~130ms | +30ms |
| DynamoDB GetItem | ~10ms | ~15ms | +5ms |

### 結論

Cross-Account アクセスのオーバーヘッドは 30-50ms 程度であり、バッチ処理ワークロードでは無視できるレベルです。

## 課題と対応策

### 確認された課題

| # | 課題 | 影響度 | 対応策 |
|---|------|--------|--------|
| 1 | RAM 共有の手動受諾が必要 | 低 | Organizations 内では自動受諾可能 |
| 2 | StackSets のデプロイ順序制御 | 中 | DependsOn 相当の手動管理が必要 |
| 3 | Cross-Account KMS キーアクセス | 低 | キーポリシーに Account B を追加 |
| 4 | CloudTrail の集約設定 | 低 | Organization Trail で一元管理推奨 |

### 推奨事項

1. **Organizations 活用**: 2 アカウント以上の場合は AWS Organizations を使用し、SCP による統制を追加
2. **External ID ローテーション**: 定期的に External ID を更新するプロセスを確立
3. **StackSets 段階デプロイ**: 本番環境では Canary デプロイ（1 アカウント → 全アカウント）を推奨
4. **集中ログ管理**: CloudTrail Organization Trail + CloudWatch Cross-Account で全アカウントのログを集約

## テンプレート検証結果

### cfn-lint 結果

```
shared/cfn/cross-account-s3ap-policy.yaml    : 0 errors, 0 warnings
shared/cfn/cross-account-roles.yaml          : 0 errors, 0 warnings
shared/cfn/ram-resource-share.yaml           : 0 errors, 0 warnings
shared/cfn/shared-services-observability.yaml: 0 errors, 0 warnings
shared/cfn/stacksets-admin.yaml              : 0 errors, 0 warnings
```

### タグ付け確認

全テンプレートに以下のタグが設定されていることを確認:

- `UseCase`: 対象ユースケース名
- `Phase`: "4"
- `Component`: コンポーネント名（CrossAccountRoles, RAM, Observability 等）
- `Account`: アカウントタイプ（Storage, Workload, Shared）

## 関連ドキュメント

- [Cross-Account S3 AP アクセスパターン](cross-account-s3ap.md)
- [Cross-Account IAM 設計](cross-account-iam.md)
- [RAM リソース共有パターン](ram-sharing.md)
- [Shared Services アーキテクチャ](shared-services-architecture.md)
- [StackSets デプロイガイド](stacksets-deployment.md)
