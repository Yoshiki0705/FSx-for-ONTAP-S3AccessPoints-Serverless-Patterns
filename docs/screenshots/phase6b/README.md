# Phase 6B スクリーンショット一覧

Phase 6B (Production Hardening) の AWS マネジメントコンソール画面キャプチャ。

## Theme C: CloudFormation Guard Hooks

| # | ファイル名 | 内容 |
|---|-----------|------|
| 1 | `guard-hooks-stack-deployed.png` | Guard Hooks スタックデプロイ完了画面 |
| 2 | `guard-hooks-resources.png` | Guard Hooks スタックのリソース一覧 |
| 3 | `guard-hooks-s3-rules.png` | S3 バケット内の cfn-guard ルールファイル |
| 4 | `guard-hooks-iam-role.png` | Hook 実行 IAM ロール |
| 5 | `guard-hooks-violation-blocked.png` | ルール違反テンプレートのデプロイブロック画面 |

## Theme D: Inference Components (scale-to-zero)

| # | ファイル名 | 内容 |
|---|-----------|------|
| 6 | `sagemaker-inference-component.png` | SageMaker Inference Component 設定画面 |
| 7 | `sagemaker-endpoint-components.png` | Endpoint に紐づく Inference Components 一覧 |
| 8 | `autoscaling-scalable-target.png` | Application Auto Scaling ScalableTarget（MinCapacity=0） |
| 9 | `cloudwatch-no-capacity-alarm.png` | CloudWatch NoCapacityInvocationFailures アラーム |
| 10 | `stepfunctions-4way-routing.png` | Step Functions 4-way ルーティングワークフロー図 |
| 11 | `stepfunctions-components-path.png` | ComponentsInference パス実行結果 |
| 12 | `lambda-components-invoke.png` | components_invoke Lambda 関数設定画面 |
| 13 | `lambda-components-invoke-env.png` | components_invoke 環境変数（scale-from-zero 設定） |
| 14 | `cloudwatch-scale-from-zero-metrics.png` | scale-from-zero メトリクス（EMF） |

## 撮影ルール

- CloudShell 等の撮影対象外要素が映り込まないようにする
- リージョンは ap-northeast-1（東京）
- アカウント ID 等の機密情報はマスク対象
