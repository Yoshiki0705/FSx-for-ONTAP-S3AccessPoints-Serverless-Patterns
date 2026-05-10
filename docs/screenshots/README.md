# Screenshots ディレクトリ構成

## ルール

1. **GitHub に公開するのは `/masked` のみ**。`/originals` はマスク前のスクリーンショット格納用（`.gitignore` で除外）
2. **Phase名をprefixとしてファイル名に記載**（例: `phase1-cloudformation-stack.png`）
3. `/masked` 配下と `/originals` 配下に **Phase名フォルダー** で分類

## ディレクトリ構造

```
docs/screenshots/
├── masked/                          ← GitHub 公開対象（マスク済み）
│   ├── phase1/                      Phase 1: Initial Deployment
│   ├── phase2/                      Phase 2: Batch Expansion
│   ├── phase3/                      Phase 3: Streaming & Observability
│   ├── phase4/                      Phase 4: Event-Driven Architecture
│   ├── phase5/                      Phase 5: Cost Optimization & Multi-Region
│   ├── phase6a/                     Phase 6A: Runtime Modernization
│   ├── phase6b/                     Phase 6B: Production Hardening
│   └── phase7/                      Phase 7: Public Sector UC Expansion (UC15-17)
├── originals/                       ← マスク前の原本（非公開）
│   ├── phase1/
│   ├── phase2/
│   ├── phase3/
│   ├── phase4/
│   ├── phase5/
│   ├── phase6a/
│   ├── phase6b/
│   └── phase7/
├── README.md                        ← このファイル
└── MASK_GUIDE.md                    ← マスク手順ガイド
```

## Phase 別ファイル一覧

### Phase 1: Initial Deployment (FSx ONTAP + Step Functions)

| ファイル名 | 内容 |
|-----------|------|
| `phase1-athena-query-history.png` | Athena クエリ履歴 |
| `phase1-bedrock-model-catalog.png` | Bedrock モデルカタログ |
| `phase1-cloudformation-stack.png` | CloudFormation スタック |
| `phase1-cloudformation-uc1-deployed.png` | UC1 スタックデプロイ完了 |
| `phase1-cloudwatch-log-groups.png` | CloudWatch ロググループ |
| `phase1-comprehend-console.png` | Comprehend コンソール |
| `phase1-eventbridge-scheduler.png` | EventBridge Scheduler |
| `phase1-fsx-file-systems.png` | FSx ファイルシステム一覧 |
| `phase1-fsx-filesystem-detail.png` | FSx ファイルシステム詳細 |
| `phase1-fsx-s3-access-point.png` | FSx S3 Access Point |
| `phase1-fsx-volume-detail.png` | FSx ボリューム詳細 |
| `phase1-fsx-volumes-list.png` | FSx ボリューム一覧 |
| `phase1-glue-data-catalog-tables.png` | Glue Data Catalog テーブル |
| `phase1-lambda-all-functions.png` | Lambda 関数一覧 |
| `phase1-rekognition-label-detection.png` | Rekognition ラベル検出 |
| `phase1-secrets-manager.png` | Secrets Manager |
| `phase1-sns-topics.png` | SNS トピック |
| `phase1-step-functions-all-succeeded.png` | Step Functions 全成功 |
| `phase1-step-functions-all-workflows.png` | Step Functions 全ワークフロー |
| `phase1-step-functions-uc1-created.png` | UC1 ワークフロー作成 |
| `phase1-step-functions-uc1-e2e-execution.png` | UC1 E2E 実行 |
| `phase1-step-functions-uc1-execution.png` | UC1 実行結果 |
| `phase1-step-functions-uc1-succeeded.png` | UC1 成功 |
| `phase1-step-functions-uc1-workflow.png` | UC1 ワークフロー図 |
| `phase1-step-functions-workflow.png` | Step Functions ワークフロー |

### Phase 2: Batch Expansion (Multi-UC)

| ファイル名 | 内容 |
|-----------|------|
| `phase2-athena-query-history.png` | Athena クエリ履歴 (Phase 2) |
| `phase2-bedrock-model-catalog.png` | Bedrock モデルカタログ (Phase 2) |
| `phase2-cloudformation-all-stacks.png` | 全 CloudFormation スタック |
| `phase2-cloudformation-phase2-stacks.png` | Phase 2 スタック |
| `phase2-comprehend-medical-console.png` | Comprehend Medical コンソール |
| `phase2-comprehend-medical-genomics-analysis-fullpage.png` | ゲノミクス分析（全画面） |
| `phase2-comprehend-medical-genomics-analysis.png` | ゲノミクス分析 |
| `phase2-comprehend-medical-realtime-analysis-fullpage.png` | リアルタイム分析（全画面） |
| `phase2-comprehend-medical-realtime-analysis.png` | リアルタイム分析 |
| `phase2-comprehend-medical-welcome.png` | Comprehend Medical ウェルカム |
| `phase2-eventbridge-all-schedules.png` | EventBridge 全スケジュール |
| `phase2-eventbridge-phase2-schedules.png` | Phase 2 スケジュール |
| `phase2-lambda-phase2-functions.png` | Phase 2 Lambda 関数 |
| `phase2-rekognition-label-detection.png` | Rekognition ラベル検出 (Phase 2) |
| `phase2-step-functions-phase2-all-workflows.png` | Phase 2 全ワークフロー |
| `phase2-step-functions-uc6-execution-graph.png` | UC6 実行グラフ |
| `phase2-textract-analyze-document.png` | Textract ドキュメント分析 |
| `phase2-textract-console.png` | Textract コンソール |

### Phase 3: Streaming & Observability

| ファイル名 | 内容 |
|-----------|------|
| `phase3-cloudshell-validation.png` | CloudShell バリデーション |
| `phase3-cloudwatch-alarms.png` | CloudWatch アラーム |
| `phase3-cloudwatch-dashboard.png` | CloudWatch ダッシュボード |
| `phase3-dynamodb-state-tables.png` | DynamoDB ステートテーブル |
| `phase3-e2e-streaming-pipeline.png` | E2E ストリーミングパイプライン |
| `phase3-e2e-validation-complete.png` | E2E バリデーション完了 |
| `phase3-kinesis-stream-active.png` | Kinesis ストリーム (Active) |
| `phase3-s3ap-available.png` | S3 Access Point (Available) |
| `phase3-step-functions-uc11-succeeded.png` | UC11 Step Functions 成功 |
| `phase3-xray-traces.png` | X-Ray トレース |

### Phase 4: Event-Driven Architecture

| ファイル名 | 内容 |
|-----------|------|
| `phase4-cloudformation-stacks.png` | CloudFormation スタック |
| `phase4-dynamodb-task-token-store.png` | DynamoDB Task Token Store |
| `phase4-event-driven-sfn-succeeded.png` | イベント駆動 SFN 成功 |
| `phase4-eventbridge-event-rule.png` | EventBridge イベントルール |
| `phase4-sagemaker-realtime-endpoint.png` | SageMaker リアルタイムエンドポイント |
| `phase4-step-functions-routing.png` | Step Functions ルーティング |

### Phase 5: Cost Optimization & Multi-Region

| ファイル名 | 内容 |
|-----------|------|
| `phase5-cloudwatch-billing-alarms.png` | CloudWatch 課金アラーム |
| `phase5-dynamodb-global-replicas.png` | DynamoDB グローバルレプリカ |
| `phase5-dynamodb-global-table.png` | DynamoDB グローバルテーブル |
| `phase5-sagemaker-serverless-endpoint-config.png` | SageMaker Serverless エンドポイント設定 |
| `phase5-sagemaker-serverless-endpoint-creating.png` | SageMaker Serverless エンドポイント作成中 |
| `phase5-sagemaker-serverless-endpoint-settings.png` | SageMaker Serverless エンドポイント設定詳細 |

### Phase 6A: Runtime Modernization

| ファイル名 | 内容 |
|-----------|------|
| `phase6a-cfn-lint-validation.png` | cfn-lint バリデーション |
| `phase6a-cfn-stack-parameters.png` | CFN スタックパラメータ |
| `phase6a-lambda-functions-list.png` | Lambda 関数一覧 |
| `phase6a-lambda-runtime-python313.png` | Lambda Python 3.13 ランタイム |
| `phase6a-lambda-snapstart-config.png` | Lambda SnapStart 設定 |
| `phase6a-lambda-snapstart-none.png` | Lambda SnapStart なし |
| `phase6a-snapstart-enabled-verification.png` | SnapStart 有効化確認 |
| `phase6a-stepfunctions-executions.png` | Step Functions 実行一覧 |

### Phase 6B: Production Hardening

| ファイル名 | 内容 |
|-----------|------|
| `phase6b-cfn-lint-all-templates-0-errors.png` | cfn-lint 全テンプレート 0 エラー |
| `phase6b-guard-hooks-enabled.png` | Guard Hooks 有効化 |
| `phase6b-guard-hooks-resources.png` | Guard Hooks リソース一覧 |
| `phase6b-guard-hooks-s3-rules.png` | Guard Hooks S3 ルール |
| `phase6b-guard-hooks-stack-deployed.png` | Guard Hooks スタックデプロイ完了 |
| `phase6b-sagemaker-endpoint-components.png` | SageMaker Endpoint Components |
| `phase6b-sagemaker-endpoint-inservice.png` | SageMaker Endpoint InService |
| `phase6b-sagemaker-endpoint-settings.png` | SageMaker Endpoint 設定 |
| `phase6b-sagemaker-inference-component.png` | SageMaker Inference Component |

### Phase 7: Public Sector UC Expansion (UC15/UC16/UC17)

UC15 (Defense / Satellite Imagery)、UC16 (Government / FOIA)、UC17 (Smart City Geospatial) の 3 ユースケースの AWS 検証時に撮影予定のスクリーンショット。ブラウザ認証が必要な環境での手動撮影を想定。

| 期待されるファイル名 | 内容 |
|---------------------|------|
| `phase7-uc15-cfn-stack.png` | UC15 CloudFormation スタック作成完了 |
| `phase7-uc15-stepfunctions-graph.png` | UC15 Step Functions グラフ（Discovery → Tiling → ObjectDetection → ChangeDetection → GeoEnrichment → AlertGeneration） |
| `phase7-uc15-s3-output.png` | UC15 S3 出力バケット（enriched / tiles / detections プレフィックス） |
| `phase7-uc15-cloudwatch-logs.png` | UC15 CloudWatch Logs（Discovery Lambda の EMF メトリクス） |
| `phase7-uc16-cfn-stack.png` | UC16 CloudFormation スタック作成完了（OpenSearchMode=none） |
| `phase7-uc16-stepfunctions-graph.png` | UC16 Step Functions グラフ（8 段 Map 処理 + Choice state） |
| `phase7-uc16-s3-output.png` | UC16 S3 出力バケット（ocr-results / classifications / pii-entities / redacted / redaction-metadata） |
| `phase7-uc16-dynamodb-retention.png` | UC16 DynamoDB Retention Table（NARA GRS 保存スケジュール） |
| `phase7-uc17-cfn-stack.png` | UC17 CloudFormation スタック作成完了 |
| `phase7-uc17-stepfunctions-graph.png` | UC17 Step Functions グラフ（7 段 Map、Bedrock Nova Lite まで到達） |
| `phase7-uc17-s3-report.png` | UC17 Bedrock 生成の都市計画レポート（Markdown） |
| `phase7-uc17-dynamodb-landuse-history.png` | UC17 DynamoDB LandUse History（時系列変化） |

検証実施済み（2026-05-10）: 3 UC すべて Step Functions SUCCEEDED、Bedrock 実呼び出し確認、その後リソース削除。検証結果の詳細は [verification-results-phase7.md](../verification-results-phase7.md) 参照。

## 命名規則

```
{phase}-{service}-{detail}.png
```

- `phase`: `phase1`, `phase2`, `phase3`, `phase4`, `phase5`, `phase6a`, `phase6b`, `phase7`
- `service`: AWS サービス名（小文字ハイフン区切り）
- `detail`: 画面の具体的内容

## ワークフロー

1. AWS コンソールでスクリーンショットを撮影
2. `/originals/phase{N}/` に `phase{N}-{name}.png` として保存
3. `MASK_GUIDE.md` に従い機密情報をマスク
4. マスク済みファイルを `/masked/phase{N}/` に同名で保存
5. `/masked` のみ Git にコミット
