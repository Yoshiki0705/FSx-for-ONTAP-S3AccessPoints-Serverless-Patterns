# Dynamic FlexCache Workflow — コスト最適化

## コスト構造

### ジョブ実行時のみ発生するコスト

| コスト項目 | 単位 | 概算 | 備考 |
|-----------|------|------|------|
| FlexCache ストレージ | GB/月（按分） | $0.13/GB/月 | ジョブ時間のみ |
| Lambda 実行 | リクエスト + 実行時間 | ~$0.01/ジョブ | 5-6 Lambda 呼び出し |
| Step Functions | 状態遷移 | ~$0.001/ジョブ | 10-15 遷移 |
| Secrets Manager | API コール | $0.05/10,000コール | |
| CloudWatch Logs | GB | $0.50/GB | |

### 常時発生するコスト

| コスト項目 | 単位 | 概算 | 備考 |
|-----------|------|------|------|
| S3 出力バケット | GB/月 | $0.023/GB | レポート保存 |
| SNS | メッセージ | $0.50/100万 | 通知 |
| DynamoDB (オプション) | RCU/WCU | PAY_PER_REQUEST | ジョブ状態管理 |

## コスト最適化戦略

### 1. ジョブ実行時のみ FlexCache を作成

```
コスト比較:
- 常時 FlexCache (500GB): $65/月
- ジョブ単位 FlexCache (500GB × 8時間/日 × 20日): ~$7/月
- 削減率: 89%
```

### 2. ジョブ完了後に自動削除

- `CleanupOnFailure=true` で失敗時も削除
- Orphan 検出 Lambda で残存キャッシュを定期削除
- TTL ベースの自動削除（作成から N 時間後）

### 3. Prepopulate 対象を限定

```python
# ❌ 全ディレクトリを prepopulate
prepopulate_dirs = ["/"]  # 数TB のデータを全てフェッチ

# ✅ 必要なディレクトリのみ
prepopulate_dirs = [
    "/scene01/textures/",  # 50GB
    "/scene01/geo/",       # 20GB
]
# 合計 70GB のみフェッチ → WAN 転送コスト削減
```

### 4. FlexCache サイズの最適化

```
推奨サイズ = ホットデータ量 × 1.2（マージン）

例:
- レンダリングジョブ: input assets 200GB → FlexCache 240GB
- EDA ジョブ: Tools+Libs 100GB → FlexCache 120GB
- CAE ジョブ: mesh 50GB → FlexCache 60GB
```

### 5. S3 AP 処理を必要ファイルだけに限定

```python
# ❌ 全ファイルを処理
objects = s3.list_objects_v2(Bucket=s3ap_alias)

# ✅ 必要なプレフィックスのみ
objects = s3.list_objects_v2(
    Bucket=s3ap_alias,
    Prefix="results/latest/",
    MaxKeys=100,
)
```

### 6. VPC Endpoint のオプショナル化

```yaml
# VPC Endpoints は高コスト（$7.2/月/endpoint × 複数）
# PoC/デモでは VPC 外 Lambda を使用
EnableVpcEndpoints:
  Type: String
  Default: 'false'  # PoC ではオフ
```

### 7. Orphan Cache の定期削除

```python
# 1時間ごとに orphan 検出・削除
# コスト: Lambda 実行 ~$0.001/回 × 24回/日 = $0.024/日
# 削減効果: orphan 1個 (500GB) = $2.17/日 の無駄を防止
```

## コスト見積もりテンプレート

### 小規模 PoC（月間 50 ジョブ）

| 項目 | 計算 | 月額 |
|------|------|------|
| FlexCache (200GB × 2時間 × 50回) | 200GB × 50 × 2/720 × $0.13 | $3.61 |
| Lambda (6回/ジョブ × 50) | 300回 × 256MB × 10秒 | $0.05 |
| Step Functions | 50 × 15遷移 | $0.02 |
| S3 (レポート) | 50 × 10KB | $0.00 |
| SNS | 50通知 | $0.00 |
| **合計** | | **~$4/月** |

### 中規模（月間 500 ジョブ）

| 項目 | 計算 | 月額 |
|------|------|------|
| FlexCache (500GB × 4時間 × 500回) | | $180 |
| Lambda | 3000回 | $0.50 |
| Step Functions | 500 × 15 | $0.19 |
| S3 | | $0.01 |
| **合計** | | **~$181/月** |

### 大規模（月間 5000 ジョブ）

| 項目 | 計算 | 月額 |
|------|------|------|
| FlexCache (1TB × 8時間 × 5000回) | | $7,222 |
| Lambda | 30000回 | $5.00 |
| Step Functions | 5000 × 15 | $1.88 |
| **合計** | | **~$7,229/月** |

**比較**: 常時 FlexCache (1TB) = $130/月 × 5000ジョブ分のデータ保持は非現実的

## タグ別コスト配賦

```yaml
Tags:
  - Key: CostCenter
    Value: !Ref CostCenter
  - Key: Project
    Value: !Ref ProjectName
  - Key: JobType
    Value: !Ref JobType  # render / eda / cae
```

AWS Cost Explorer でタグ別にコストを可視化し、プロジェクト/ジョブタイプ別の配賦を実現。
