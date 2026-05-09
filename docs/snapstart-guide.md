# Lambda SnapStart ガイド

## 概要

Lambda SnapStart は、Lambda 関数の初期化フェーズ（Init phase）のメモリスナップショットをキャッシュし、コールドスタート時間を大幅に削減する機能です。本プロジェクトでは全 14 ユースケースの Lambda 関数で SnapStart をオプトインで有効化できます。

---

## ⚠️ 重要: SnapStart の前提条件

SnapStart で実際にコールドスタート改善効果を得るには、以下の **3つの条件全て** を満たす必要があります：

1. **`EnableSnapStart=true` でスタックデプロイ/更新**
2. **Lambda 関数の Published Version を作成**（`$LATEST` には SnapStart は適用されない）
3. **呼び出し側（Step Functions 等）が Version ARN または Alias ARN を指定**

本プロジェクトの現在の CloudFormation テンプレートでは、**条件 1 のみ自動化**しています。条件 2 は `scripts/enable-snapstart.sh` で自動化でき、条件 3 については運用ガイダンスを後述します。

---

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

---

## 有効化手順

### 方法 1: 自動化スクリプトを使用（推奨）

本プロジェクトは、SnapStart 有効化を一括実行するスクリプトを提供しています：

```bash
# スタック更新 + バージョン公開 + 検証 を一括実行
./scripts/enable-snapstart.sh <stack-name> [region]

# 例
./scripts/enable-snapstart.sh fsxn-eda-uc6
./scripts/enable-snapstart.sh fsxn-legal-compliance ap-northeast-1
```

このスクリプトは以下を自動実行します：

1. 現在のスタックパラメータを取得
2. `EnableSnapStart=true` でスタック更新
3. スタック内の全 Lambda 関数を列挙
4. 各関数の新バージョンを公開
5. SnapStart 最適化ステータスを確認

### 方法 2: 手動実行

#### Step 1: スタックパラメータ更新

```bash
aws cloudformation update-stack \
  --stack-name fsxn-eda-uc6 \
  --use-previous-template \
  --parameters ParameterKey=EnableSnapStart,ParameterValue=true \
               ParameterKey=DeployBucket,UsePreviousValue=true \
               # ... 他のパラメータも全て UsePreviousValue=true で指定 \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1

aws cloudformation wait stack-update-complete \
  --stack-name fsxn-eda-uc6 \
  --region ap-northeast-1
```

#### Step 2: Lambda バージョン公開

```bash
aws lambda publish-version \
  --function-name fsxn-eda-uc6-discovery
```

出力例:
```json
{
    "Version": "1",
    "SnapStart": {
        "ApplyOn": "PublishedVersions",
        "OptimizationStatus": "On"
    }
}
```

`OptimizationStatus: "On"` が表示されれば SnapStart 最適化が完了しています。

#### Step 3: 動作検証

```bash
./scripts/verify-snapstart.sh fsxn-eda-uc6
```

---

## Step Functions から SnapStart バージョンを呼び出す

### 現状の制限

本プロジェクトの Step Functions State Machine は、Lambda ARN として `${FunctionName.Arn}` を参照しており、これは `$LATEST` を指します。**SnapStart は `$LATEST` には適用されません。**

### 運用パターン

#### パターン A: Alias を手動作成して Step Functions を更新（中規模）

```bash
# 1. Alias "live" を作成（初回のみ）
aws lambda create-alias \
  --function-name fsxn-eda-uc6-discovery \
  --name live \
  --function-version 1

# 2. Step Functions State Machine の定義を更新
#    Resource を "arn:aws:lambda:...:function:fsxn-eda-uc6-discovery:live" に変更
aws stepfunctions update-state-machine \
  --state-machine-arn arn:aws:states:...:stateMachine:fsxn-eda-uc6-workflow \
  --definition file://updated-definition.json

# 3. コード更新時の運用
aws lambda publish-version --function-name fsxn-eda-uc6-discovery
aws lambda update-alias \
  --function-name fsxn-eda-uc6-discovery \
  --name live \
  --function-version <new-version>
```

#### パターン B: 直接 Version ARN を指定（小規模・一回限り）

Step Functions State Machine の Resource を固定バージョン ARN に変更：

```json
{
  "Resource": "arn:aws:lambda:ap-northeast-1:123456789012:function:fsxn-eda-uc6-discovery:1"
}
```

コード更新時は毎回 Resource を更新する必要があり、運用負荷が高いため推奨しません。

#### パターン C: SAM Transform への移行（大規模な改修）

SAM の `AWS::Serverless::Function` は `AutoPublishAlias` プロパティをサポートしており、コード変更時に自動的に新バージョンを公開して Alias を更新します。

```yaml
Transform: AWS::Serverless-2016-10-31

Resources:
  DiscoveryFunction:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: python3.13
      SnapStart:
        ApplyOn: PublishedVersions
      AutoPublishAlias: live   # SAM が自動で Version + Alias を管理
```

ただし、本プロジェクトは現在 Raw CloudFormation（`AWS::Lambda::Function`）を使用しており、SAM への移行は大規模な書き換えが必要です。将来的な検討事項として Phase 7 以降の候補です。

---

## コールドスタート比較

| 項目 | SnapStart なし | SnapStart あり |
|------|---------------|---------------|
| コールドスタート時間 | 1–3 秒 | 100–500ms |
| Init Phase | 毎回実行 | スキップ（スナップショット復元） |
| 追加コスト | なし | なし（追加料金不要） |
| 適用対象 | $LATEST | Published Versions のみ |
| 公開時の処理時間 | 即時 | スナップショット作成に数分 |

---

## CloudFormation テンプレート設定

各 `template-deploy.yaml` での設定パターン：

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

---

## 制約事項

### 技術的制約

1. **Published Versions のみ**: `$LATEST` には適用されない。バージョン公開が必要
2. **Python 3.13+ 必須**: Python 3.12 以前のランタイムでは利用不可
3. **スナップショット公開時の待ち時間**: 公開後、最適化完了まで数分～十数分かかる
4. **スナップショットの一意性**: 各実行環境は独立したスナップショットから復元される（状態共有なし）
5. **ネットワーク接続**: スナップショット復元後にネットワーク接続が再確立される

### 互換性に関する注意

1. **ランダム値の一意性**: `random` モジュールのシードがスナップショット時に固定される可能性がある。一意性が必要な場合は復元後に再シードする
2. **一時ファイル**: `/tmp` の内容はスナップショットに含まれない
3. **外部接続**: DB コネクション等はスナップショット復元後に再接続が必要

### 本プロジェクトでの対応状況

本プロジェクトの Lambda 関数は以下の理由で SnapStart と互換性があります：

- 外部接続（ONTAP REST API, AWS SDK）は各呼び出し時に新規作成
- ランダム値の一意性に依存する処理なし
- `/tmp` への永続的な状態保存なし

### CloudFormation の仕様制限

CloudFormation で `AWS::Lambda::Version` を定義しても、**コード（S3Key）が変わらない限り新バージョンは作成されません**。本プロジェクトではこの制約を回避するため、以下のアプローチを採用しています：

- テンプレートには Version リソースを含めない
- SnapStart 有効化後、`aws lambda publish-version` を手動実行（または `scripts/enable-snapstart.sh` を使用）
- コード更新毎に再実行が必要

より高度な自動化が必要な場合は、SAM Transform への移行（前述「パターン C」）を検討してください。

---

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

---

## 動作検証

### 実機検証結果（ap-northeast-1, fsxn-eda-uc6 スタック）

2026年5月の動作検証で得られた結果：

#### 1. SnapStart 設定の確認

```bash
aws lambda get-function-configuration \
  --function-name fsxn-eda-uc6-discovery \
  --query 'SnapStart'
```

EnableSnapStart=false（デフォルト）:
```json
null
```

EnableSnapStart=true + バージョン公開後:
```json
{
    "ApplyOn": "PublishedVersions",
    "OptimizationStatus": "Off"
}
```
※ `$LATEST` の OptimizationStatus は常に "Off"

#### 2. バージョン公開後

```json
{
    "Version": "1",
    "SnapStart": {
        "ApplyOn": "PublishedVersions",
        "OptimizationStatus": "On"
    }
}
```

`OptimizationStatus: "On"` で SnapStart が有効化された。

#### 3. Step Functions 実行時間

- SnapStart 無効 + `$LATEST`: 約 20–22 秒（VPC 内 Lambda 4 関数の順次実行）
- SnapStart 有効 + `$LATEST`: 約 20–22 秒（**変化なし** — SnapStart は `$LATEST` には効かない）
- SnapStart 有効 + Published Version を呼び出し: 未検証（Step Functions 定義の更新が必要）

この結果から、実運用で SnapStart の効果を得るには、Step Functions の Resource を Alias/Version ARN に変更する必要があることが判明しました。

---

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
  --function-name fsxn-eda-uc6-discovery

# 最新バージョンの SnapStart 状態を確認
aws lambda get-function-configuration \
  --function-name fsxn-eda-uc6-discovery \
  --qualifier <version-number> \
  --query 'SnapStart'
```

### コールドスタートが改善されない

**症状**: SnapStart 有効後もコールドスタートが遅い

**最頻出原因**: 呼び出し側が `$LATEST` を指している

**確認方法**:

```bash
# Step Functions State Machine の定義から Lambda ARN を確認
aws stepfunctions describe-state-machine \
  --state-machine-arn <arn> \
  --query 'definition' \
  --output text | python3 -m json.tool | grep -i "Resource.*lambda"
```

出力の Resource ARN に `:<version>` または `:<alias-name>` が付いていない場合、`$LATEST` を呼び出しています。

**解決**: 前述「Step Functions から SnapStart バージョンを呼び出す」セクションの運用パターン A または B を実施してください。

### その他の確認事項

```bash
# CloudWatch Logs で SnapStart 復元を確認
aws logs filter-log-events \
  --log-group-name /aws/lambda/fsxn-eda-uc6-discovery \
  --filter-pattern "RESTORE"
```

`RESTORE_START` / `RESTORE_RUNTIME_DONE` イベントが記録されていれば SnapStart が実際に動作しています。

### デプロイエラー

**症状**: CloudFormation デプロイ時にエラー

**確認事項**:
1. Runtime が `python3.13` になっているか（`python3.12` では SnapStart 不可）
2. リージョンが SnapStart に対応しているか
3. 対応していないリージョンでは `EnableSnapStart=false` に設定

---

## 参考リンク

- [AWS Lambda SnapStart ドキュメント](https://docs.aws.amazon.com/lambda/latest/dg/snapstart.html)
- [Lambda SnapStart for Python (AWS Blog)](https://aws.amazon.com/blogs/compute/reducing-cold-starts-for-python-lambda-functions-with-snapstart/)
- [SnapStart のベストプラクティス](https://docs.aws.amazon.com/lambda/latest/dg/snapstart-best-practices.html)
- [AWS SAM AutoPublishAlias](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-resource-function.html#sam-function-autopublishalias)
