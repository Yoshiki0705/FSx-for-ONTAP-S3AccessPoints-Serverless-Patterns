# Phase 6B 検証結果

**検証日**: 2026-05-09
**リージョン**: ap-northeast-1 (東京)
**アカウント**: <ACCOUNT_ID>

---

## Theme C: CloudFormation Guard Hooks

### デプロイ結果

| リソース | ステータス | 物理 ID |
|---------|-----------|---------|
| Guard Hooks スタック | UPDATE_COMPLETE | fsxn-s3ap-guard-hooks |
| S3 バケット | CREATE_COMPLETE | fsxn-s3ap-guard-rules-<ACCOUNT_ID> |
| IAM ロール | CREATE_COMPLETE | fsxn-s3ap-guard-hooks-hook-execution-role |
| CloudWatch LogGroup | CREATE_COMPLETE | /aws/cloudformation/hooks/fsxn-s3ap-guard-hooks |
| GuardHook | CREATE_COMPLETE | FSxNS3AP::Guard::Hook |

### Guard ルールファイル（S3）

```
s3://fsxn-s3ap-guard-rules-<ACCOUNT_ID>/cfn-guard-rules/
├── encryption-required.guard    (1.5 KB)
├── iam-least-privilege.guard    (1.7 KB)
├── lambda-limits.guard          (1.4 KB)
├── no-public-access.guard       (1.7 KB)
└── sagemaker-security.guard     (2.5 KB)
```

### Hook 動作確認

テストスタック（暗号化なし S3 バケット）をデプロイし、Hook invocation を確認:

```
ResourceStatus: CREATE_IN_PROGRESS
ResourceStatusReason: "Hook invocations complete. Resource creation initiated"
```

- **モード**: WARN（警告のみ、デプロイ続行）
- **結果**: Hook が正常に呼び出され、ルール評価が実行された

### デプロイ時の知見

1. **Alias パターン制約**: `^(?!(?i)aws)[A-Za-z0-9]{2,64}::[A-Za-z0-9]{2,64}::[A-Za-z0-9]{2,64}$`
   - ハイフン不可、`AWS` プレフィックス不可
   - 正しい例: `FSxNS3AP::Guard::Hook`

2. **TargetFilters 構造**: `Actions` をトップレベルに配置
   ```yaml
   TargetFilters:
     Actions:
       - CREATE
       - UPDATE
   ```

3. **StackFilters**: 自スタックを除外して無限ループ防止
   ```yaml
   StackFilters:
     FilteringCriteria: ALL
     StackNames:
       Exclude:
         - !Ref "AWS::StackName"
   ```

---

## Theme D: SageMaker Inference Components

### デプロイ結果

| リソース | ステータス | 物理 ID |
|---------|-----------|---------|
| IC Demo スタック | CREATE_COMPLETE | phase6b-ic-demo |
| SageMaker Model | CREATE_COMPLETE | phase6b-ic-demo-model |
| EndpointConfig | CREATE_COMPLETE | phase6b-ic-demo-config |
| Endpoint | InService | phase6b-ic-demo-endpoint |
| Inference Component | InService | phase6b-ic-demo-component |
| ScalableTarget | Active | MinCapacity=0, MaxCapacity=2 |
| ScalingPolicy | Active | StepScaling |

### scale-to-zero 設定確認

```json
{
  "ResourceId": "inference-component/phase6b-ic-demo-component",
  "MinCapacity": 0,
  "MaxCapacity": 2,
  "ScalableDimension": "sagemaker:inference-component:DesiredCopyCount"
}
```

### デプロイ時の知見（重要）

1. **EndpointConfig の構成差異**（Inference Components モード）:
   - `ModelName` を ProductionVariant から**削除**する
   - `InitialVariantWeight` を**削除**する
   - `ExecutionRoleArn` を EndpointConfig レベルで**追加**する
   - `RoutingConfig.RoutingStrategy: LEAST_OUTSTANDING_REQUESTS` を**追加**する
   - `ManagedInstanceScaling` を**追加**する（scale-to-zero 用）

2. **ComputeResourceRequirements の制約**:
   - インスタンスタイプのキャパシティ内に収める必要がある
   - ml.m5.large (2 vCPU, 8GB): `NumberOfCpuCoresRequired <= 1`, `MinMemoryRequiredInMb <= 2048` が安全
   - 超過すると `"not enough hardware resources"` エラー

3. **正しい EndpointConfig 構成**:
   ```yaml
   ProductionVariants:
     - VariantName: "primary"
       InstanceType: "ml.m5.large"
       InitialInstanceCount: 1
       RoutingConfig:
         RoutingStrategy: LEAST_OUTSTANDING_REQUESTS
       ManagedInstanceScaling:
         Status: ENABLED
         MinInstanceCount: 0
         MaxInstanceCount: 2
   ```

---

## テスト結果

```
310 passed, 0 failed, 30 warnings in 135.30s
```

### cfn-lint 結果

```
shared/cfn/guard-hooks.yaml: 0 errors
autonomous-driving/template-deploy.yaml: 0 errors
scripts/demo-inference-components.yaml: 0 errors
```

---

## クリーンアップ手順

デモリソースの削除（コスト停止）:

```bash
# Inference Components デモスタック削除
aws cloudformation delete-stack --stack-name phase6b-ic-demo --region ap-northeast-1

# Guard Hooks スタック削除（必要に応じて）
aws cloudformation delete-stack --stack-name fsxn-s3ap-guard-hooks --region ap-northeast-1
```

---

## スクリーンショット一覧

### 撮影済み（Theme C）

| ファイル | 内容 |
|---------|------|
| `guard-hooks-stack-deployed.png` | CloudFormation スタック一覧 |
| `guard-hooks-resources.png` | リソースタブ（4 リソース） |
| `guard-hooks-s3-rules.png` | S3 バケット内ルールファイル |
| `guard-hooks-enabled.png` | Hooks 一覧（Enabled/WARN） |

### 撮影待ち（Theme D）

| ファイル | 内容 |
|---------|------|
| `sagemaker-inference-component.png` | Inference Component 詳細画面 |
| `sagemaker-endpoint-components.png` | Endpoint の IC タブ |
| `autoscaling-scalable-target.png` | ScalableTarget（MinCapacity=0） |

**Note**: Theme D のスクリーンショットは MCP ブラウザ復旧後に撮影予定。
リソースは `phase6b-ic-demo` スタックとして稼働中。
