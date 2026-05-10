# Phase 6A 検証結果

**検証日**: 2026年5月9日  
**検証リージョン**: ap-northeast-1 (東京)  
**検証対象**: fsxn-eda-uc6 (UC6: 半導体 EDA) スタック

---

## 検証サマリー

| # | 検証項目 | 結果 | 備考 |
|---|---------|------|------|
| 1 | cfn-lint 全 15 template-deploy.yaml バリデーション | ✅ PASS | 0 errors、W2530 warnings は SnapStart conditional の既知制限 |
| 2 | Lambda Runtime: python3.13 移行 | ✅ PASS | 全 UC6 関数（discovery, metadata-extraction, drc-aggregation, report-generation）で python3.13 確認 |
| 3 | SnapStart デフォルト無効（EnableSnapStart=false） | ✅ PASS | Lambda コンソールで SnapStart: "None" 表示 |
| 4 | CloudFormation スタック更新（EnableSnapStart=true） | ✅ PASS | UPDATE_COMPLETE、既存 Lambda 関数への破壊的変更なし |
| 5 | SnapStart 有効化確認（ApplyOn: PublishedVersions） | ✅ PASS | Lambda コンソールで "PublishedVersions" 表示 |
| 6 | Lambda バージョン公開（OptimizationStatus: On） | ✅ PASS | Version 1 で OptimizationStatus: "On" |
| 7 | Step Functions ワークフロー実行 | ✅ PASS | 21.977 秒で Succeeded |
| 8 | EventBridge Scheduler 定期実行 | ✅ PASS | 1時間ごとに自動実行、全 17 回 Succeeded |

---

## 実行ログ抜粋

### cfn-lint 結果（CloudShell）

```
=== cfn-lint validation ===
autonomous-driving/template-deploy.yaml: 0 errors
construction-bim/template-deploy.yaml: 0 errors
education-research/template-deploy.yaml: 0 errors
energy-seismic/template-deploy.yaml: 0 errors
event-driven-prototype/template-deploy.yaml: 0 errors
financial-idp/template-deploy.yaml: 0 errors
genomics-pipeline/template-deploy.yaml: 0 errors
healthcare-dicom/template-deploy.yaml: 0 errors
insurance-claims/template-deploy.yaml: 0 errors
legal-compliance/template-deploy.yaml: 0 errors
logistics-ocr/template-deploy.yaml: 0 errors
manufacturing-analytics/template-deploy.yaml: 0 errors
media-vfx/template-deploy.yaml: 0 errors
retail-catalog/template-deploy.yaml: 0 errors
semiconductor-eda/template-deploy.yaml: 0 errors
```

### SnapStart 有効化フロー

```bash
# 1. スタック更新
$ aws cloudformation update-stack --stack-name fsxn-eda-uc6 \
    --parameters ParameterKey=EnableSnapStart,ParameterValue=true ... \
    --capabilities CAPABILITY_NAMED_IAM
{
    "StackId": "arn:aws:cloudformation:ap-northeast-1:...:stack/fsxn-eda-uc6/...",
    "OperationId": "124291a0-4b77-11f1-9148-0ee54d7fac19"
}

# 2. スタック更新完了待ち
$ aws cloudformation wait stack-update-complete --stack-name fsxn-eda-uc6
DONE: Stack update complete

# 3. SnapStart 設定確認（$LATEST）
$ aws lambda get-function-configuration --function-name fsxn-eda-uc6-discovery
{
    "Runtime": "python3.13",
    "SnapStart": {
        "ApplyOn": "PublishedVersions",
        "OptimizationStatus": "Off"   # ← $LATEST では常に Off
    }
}

# 4. バージョン公開
$ aws lambda publish-version --function-name fsxn-eda-uc6-discovery
{
    "Version": "1",
    "SnapStart": {
        "ApplyOn": "PublishedVersions",
        "OptimizationStatus": "On"    # ← Published Version で On
    }
}

# 5. Step Functions 実行
$ aws stepfunctions start-execution --state-machine-arn ...
Execution started: arn:aws:states:...:execution:fsxn-eda-uc6-workflow:6c384f06-...
```

---

## 重要な発見事項

### 発見 1: `$LATEST` の OptimizationStatus は常に "Off"

**事実**: Lambda の `$LATEST` バージョンでは `SnapStart.OptimizationStatus` が常に `"Off"` として返される。`"On"` になるのは Published Version のみ。

**影響**: SnapStart の効果を得るには、**必ずバージョン公開と呼び出し側の ARN 更新の両方が必要**。

### 発見 2: Step Functions は `$LATEST` を呼び出している

**事実**: 本プロジェクトの Step Functions State Machine は `${FunctionName.Arn}` を Resource として指定しており、これは `$LATEST` を指す。

**影響**: `EnableSnapStart=true` でスタック更新しバージョンを公開しても、**Step Functions は引き続き `$LATEST` を呼び出すため、コールドスタート改善効果は得られない**。

**対策**: 以下のいずれかの対応が必要：
- **パターン A** (推奨): Alias "live" を作成し、Step Functions 定義を更新
- **パターン B**: Step Functions 定義で Version 番号付き ARN を直接指定
- **パターン C** (将来): SAM Transform への移行

詳細は `docs/snapstart-guide.md` を参照。

### 発見 3: CloudFormation での Lambda Version 自動管理の限界

**事実**: `AWS::Lambda::Version` リソースを CloudFormation で定義しても、コードハッシュが変わらない限り新バージョンは作成されない。Logical ID にハッシュを含める等の回避策が必要。

**影響**: 完全な IaC 自動化は困難。本プロジェクトでは以下の方針を採用：
- テンプレートには Version/Alias を含めない
- `scripts/enable-snapstart.sh` で手動公開を自動化
- ドキュメントで運用手順を明記

### 発見 4: スタック更新時のパラメータ指定の煩雑さ

**事実**: `--use-previous-template` でスタックを更新する場合、**全パラメータを明示的に `UsePreviousValue=true` で指定する必要がある**（20+パラメータ）。1つでも漏らすとエラー。

**対策**: `scripts/enable-snapstart.sh` でパラメータ指定を自動化。

---

## 撮影したスクリーンショット（8枚）

| ファイル名 | 内容 |
|-----------|------|
| `phase6a-cfn-lint-validation.png` | CloudShell: cfn-lint 全15テンプレート 0 errors |
| `phase6a-lambda-functions-list.png` | Lambda 関数一覧: UC6 全関数 Python 3.13 |
| `phase6a-lambda-runtime-python313.png` | Discovery 関数詳細: Runtime python3.13 |
| `phase6a-lambda-snapstart-none.png` | SnapStart デフォルト無効状態 (None) |
| `phase6a-lambda-snapstart-config.png` | SnapStart 有効化後: PublishedVersions |
| `phase6a-cfn-stack-parameters.png` | CloudFormation パラメータ: EnableSnapStart |
| `phase6a-snapstart-enabled-verification.png` | CloudShell: SnapStart 有効化 + バージョン公開 + ワークフロー実行 |
| `phase6a-stepfunctions-executions.png` | Step Functions: 全17回 Succeeded |

---

## Phase 6A 完了ステータス

### 完了した項目

- ✅ **Theme A**: Lambda SnapStart 設定追加
  - 全 15 template-deploy.yaml に `EnableSnapStart` パラメータ追加
  - 全 Lambda 関数に SnapStart Condition 追加
  - Runtime 更新: python3.12 → python3.13
  - `docs/snapstart-guide.md` 作成（実検証結果を反映）

- ✅ **Theme B**: SAM CLI ローカルテスト基盤
  - `events/` ディレクトリ構造（14 UC 分）
  - `events/env.json` 環境変数テンプレート
  - `samconfig.toml` サンプル
  - `scripts/local-test.sh` 一括テストスクリプト
  - `docs/local-testing-guide.md` 作成

- ✅ **運用スクリプト**
  - `scripts/enable-snapstart.sh`: SnapStart 有効化ワンショット
  - `scripts/verify-snapstart.sh`: SnapStart 動作検証

### 残課題（Phase 7 以降の検討事項）

1. **Lambda Version/Alias の IaC 化**
   - SAM Transform への移行で `AutoPublishAlias` を利用可能にする
   - 全 15 テンプレートの書き換えが必要（大規模改修）

2. **Step Functions Definition の Condition 化**
   - `EnableSnapStart=true` 時に Alias ARN を呼ぶ条件分岐
   - SAM Transform 移行と合わせて実施

3. **E2E コールドスタート比較測定**
   - SnapStart 有効/無効の実行時間を統計的に比較
   - CloudWatch Logs Insights で測定

4. **SnapStart 対応リージョンの Condition バリデーション**
   - 非対応リージョンで `EnableSnapStart=true` を指定した際のエラーハンドリング強化

---

## 既存テストの状況

### Pass

- 全 295 テスト（`shared/tests/`）が PASS
- Phase 6A の変更による新規失敗テストなし

### 既知の失敗（Phase 6A とは無関係）

- `shared/tests/test_auto_stop.py::TestScaleToZeroAction::test_scale_to_zero_calls_update_with_zero_instances`
  - 原因: SageMaker auto-stop ロジックのテスト期待値ミスマッチ
  - Phase 6A の変更とは無関係（既存バグ）
  - 修正: 別途対応（`docs/remaining-issues-checklist.md` に記載）

---

## 参考情報

- Phase 6A spec: `.kiro/specs/fsxn-s3ap-serverless-patterns-phase6a/`
- 実装 commit ログ（git log 参照）
- 検証時の AWS アカウント: <ACCOUNT_ID>
- 検証時の IAM ユーザー: yoshiki
