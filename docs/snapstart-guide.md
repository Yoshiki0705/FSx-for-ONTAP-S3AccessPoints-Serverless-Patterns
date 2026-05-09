# Lambda SnapStart ガイド

## 概要

Lambda SnapStart は、Lambda 関数の初期化フェーズ（Init phase）のメモリスナップショットをキャッシュし、コールドスタート時間を大幅に削減する機能です。本プロジェクトでは全 14 ユースケースの Lambda 関数で SnapStart をオプトインで有効化できます。

## 仕組み

### 通常のコールドスタート

```
┌─────────────────────────────────────────────────────────────┐
│ Cold Start (1–3 秒)                                          │
├──────────────────────┬──────────────────────────────────────┤
│ Init Phase (1–2s)    │ Invoke Phase (実処理)                  │
│ - ランタイム起動      │                                       │
│ - モジュールインポート │                                       │
│ - グローバル初期化    │                                       │
└──────────────────────┴──────────────────────────────────────┘
```

### SnapStart 有効時

```
┌─────────────────────────────────────────────────────────────┐
│ Cold Start (100–500ms)                                       │
├──────────┬──────────────────────────────────────────────────┤
│ Restore  │ Invoke Phase (実処理)                              │
│ (100ms)  │                                                   │
│ スナップ │                                                   │
│ ショット │                                                   │
│ 復元     │                                                   │
└──────────┴──────────────────────────────────────────────────┘
```

### 動作原理

1. **バージョン公開時**: Lambda がコードを初期化し、メモリ + ディスク状態のスナップショットを取得
2. **コールドスタート時**: スナップショットからマイクロ VM を復元（Init Phase をスキップ）
3. **キャッシュ**: スナップショットは暗号化されてキャッシュされ、複数の実行環境で再利用

## コールドスタート比較

| 項目 | SnapStart なし | SnapStart あり |
|------|---------------|---------------|
| コールドスタート時間 | 1–3 秒 | 100–500ms |
| Init Phase | 毎回実行 | スキップ（スナップショット復元） |
| 追加コスト | なし | なし（追加料金不要） |
| 適用対象 | $LATEST | Published Versions のみ |

## 有効化手順

### 1. パラメータ設定

デプロイ時に `EnableSnapStart=true` を指定します：

```bash
aws cloudformation deploy \
  --template-file template-deploy.yaml \
  --stack-name fsxn-s3ap-legal-compliance \
  --parameter-overrides \
    EnableSnapStart=true \
    S3AccessPointAlias=vol-demo-xxxxx-ext-s3alias \
    ... (その他のパラメータ)
```

### 2. バージョン公開

SnapStart は Published Versions にのみ適用されます。CloudFormation でデプロイすると、Lambda 関数の更新時に自動的に新しいバージョンが公開されます。

手動でバージョンを公開する場合：

```bash
aws lambda publish-version \
  --function-name fsxn-s3ap-legal-compliance-discovery
```

### 3. 動作確認

SnapStart が有効化されていることを確認：

```bash
aws lambda get-function-configuration \
  --function-name fsxn-s3ap-legal-compliance-discovery \
  --query 'SnapStart'
```

期待される出力：
```json
{
  "ApplyOn": "PublishedVersions",
  "OptimizationStatus": "On"
}
```

## テンプレート設定

各 template-deploy.yaml での設定パターン：

```yaml
Parameters:
  EnableSnapStart:
    Type: String
    Default: "false"
    AllowedValues: ["true", "false"]
    Description: Lambda SnapStart を有効化する（コールドスタート削減）

Conditions:
  SnapStartEnabled:
    !Equals [!Ref EnableSnapStart, "true"]

Resources:
  DiscoveryFunction:
    Type: AWS::Lambda::Function
    Properties:
      Runtime: python3.13
      SnapStart:
        !If
          - SnapStartEnabled
          - ApplyOn: PublishedVersions
          - !Ref AWS::NoValue
      # ... 他のプロパティ
```

### Condition 設計のポイント

- `!If + !Ref AWS::NoValue` パターンにより、SnapStart 無効時はプロパティ自体が省略される
- デフォルト `false` のため、既存デプロイに影響なし
- SnapStart 非対応リージョンでも `false` のままならデプロイ可能

## 制約事項

### 技術的制約

1. **Published Versions のみ**: `$LATEST` には適用されない。バージョン公開が必要
2. **Python 3.13+ 必須**: Python 3.12 以前のランタイムでは利用不可
3. **スナップショットの一意性**: 各実行環境は独立したスナップショットから復元される（状態共有なし）
4. **ネットワーク接続**: スナップショット復元後にネットワーク接続が再確立される（VPC Lambda でも対応済み）

### 互換性に関する注意

1. **ランダム値の一意性**: `random` モジュールのシードがスナップショット時に固定される可能性がある。一意性が必要な場合は復元後に再シードする
2. **一時ファイル**: `/tmp` の内容はスナップショットに含まれない
3. **外部接続**: DB コネクション等はスナップショット復元後に再接続が必要

### 本プロジェクトでの対応状況

本プロジェクトの Lambda 関数は以下の理由で SnapStart と互換性があります：

- 外部接続（ONTAP REST API, AWS SDK）は各呼び出し時に新規作成
- ランダム値の一意性に依存する処理なし
- `/tmp` への永続的な状態保存なし

## リージョン可用性

Lambda SnapStart for Python は以下のリージョンで利用可能です（2026年5月時点）：

| リージョン | 利用可能 |
|-----------|---------|
| us-east-1 (バージニア) | ✅ |
| us-east-2 (オハイオ) | ✅ |
| us-west-2 (オレゴン) | ✅ |
| eu-west-1 (アイルランド) | ✅ |
| eu-central-1 (フランクフルト) | ✅ |
| ap-northeast-1 (東京) | ✅ |
| ap-southeast-1 (シンガポール) | ✅ |
| ap-southeast-2 (シドニー) | ✅ |

最新の対応状況は AWS ドキュメントで確認してください：
https://docs.aws.amazon.com/lambda/latest/dg/snapstart.html

### 非対応リージョンでの動作

`EnableSnapStart=false`（デフォルト）のままデプロイすれば、SnapStart 非対応リージョンでもエラーなくデプロイできます。Condition により SnapStart プロパティ自体が省略されるためです。

## トラブルシューティング

### SnapStart が有効にならない

**症状**: `OptimizationStatus` が `Off` のまま

**確認事項**:
1. `EnableSnapStart=true` でデプロイしたか確認
2. Lambda バージョンが公開されているか確認
3. リージョンが SnapStart for Python に対応しているか確認

```bash
# バージョン一覧を確認
aws lambda list-versions-by-function \
  --function-name fsxn-s3ap-legal-compliance-discovery

# 最新バージョンの SnapStart 状態を確認
aws lambda get-function-configuration \
  --function-name fsxn-s3ap-legal-compliance-discovery \
  --qualifier <version-number> \
  --query 'SnapStart'
```

### コールドスタートが改善されない

**症状**: SnapStart 有効後もコールドスタートが遅い

**確認事項**:
1. `$LATEST` ではなく Published Version を呼び出しているか
2. スナップショットの作成が完了しているか（公開直後は数分かかる場合がある）
3. CloudWatch Logs で `RESTORE_START` / `RESTORE_RUNTIME_DONE` が記録されているか

```bash
# CloudWatch Logs で SnapStart 復元を確認
aws logs filter-log-events \
  --log-group-name /aws/lambda/fsxn-s3ap-legal-compliance-discovery \
  --filter-pattern "RESTORE"
```

### デプロイエラー

**症状**: CloudFormation デプロイ時にエラー

**確認事項**:
1. Runtime が `python3.13` になっているか（`python3.12` では SnapStart 不可）
2. リージョンが SnapStart に対応しているか
3. 対応していないリージョンでは `EnableSnapStart=false` に設定

## 参考リンク

- [AWS Lambda SnapStart ドキュメント](https://docs.aws.amazon.com/lambda/latest/dg/snapstart.html)
- [Lambda SnapStart for Python (AWS Blog)](https://aws.amazon.com/blogs/compute/reducing-cold-starts-for-python-lambda-functions-with-snapstart/)
- [SnapStart のベストプラクティス](https://docs.aws.amazon.com/lambda/latest/dg/snapstart-best-practices.html)
