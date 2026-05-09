# Changelog

本プロジェクトの全ての注目すべき変更をこのファイルに記録します。

フォーマットは [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/) に準拠し、  
バージョニングは [Semantic Versioning](https://semver.org/spec/v2.0.0.html) に従います。

---

## [Phase 6A] - 2026-05-09

### Added

#### Theme A: Lambda SnapStart for Python 3.13
- 全 15 `template-deploy.yaml` に `EnableSnapStart` パラメータ追加（デフォルト: `false`）
- 全 15 `template-deploy.yaml` に `SnapStartEnabled` Condition 追加
- 全 Lambda 関数に `SnapStart: !If [SnapStartEnabled, {ApplyOn: PublishedVersions}, !Ref AWS::NoValue]` 設定追加
- `shared/cfn/common-parameters.yaml` に `EnableSnapStart` パラメータ・Condition リファレンス追加
- `docs/snapstart-guide.md` 作成（仕組み、有効化手順、運用パターン、トラブルシューティング）
- `scripts/enable-snapstart.sh` 作成（SnapStart 有効化ワンショットスクリプト）
- `scripts/verify-snapstart.sh` 作成（SnapStart 動作検証スクリプト）

#### Theme B: SAM CLI ローカルテスト基盤
- `events/` ディレクトリ構造作成（14 UC 分の `discovery-event.json`）
- `events/env.json` 環境変数テンプレート作成
- `samconfig.toml` サンプル作成（ローカルテスト + デプロイ設定）
- `scripts/local-test.sh` 一括ローカルテストスクリプト作成
- `docs/local-testing-guide.md` 作成（SAM CLI 使い方、Finch 対応、トラブルシューティング）

#### ドキュメント
- `docs/article-phase6a-en.md` 作成（dev.to 記事ドラフト、実検証結果反映）
- `docs/verification-results-phase6a.md` 作成（AWS 実環境検証結果）
- `docs/remaining-issues-phase6a.md` 作成（Phase 6A 残課題チェックリスト）
- `CHANGELOG.md` 作成（本ファイル）
- スクリーンショット 8 枚撮影（`docs/screenshots/phase6a-*.png`）

### Changed

- **Lambda Runtime 更新**: `python3.12` → `python3.13`（SnapStart for Python の要件）
  - 対象: 全 15 `template-deploy.yaml`、全 14 `template.yaml`、`shared/cfn/auto-stop-resources.yaml`、`shared/cfn/stacksets-admin.yaml`、`shared/cfn/alert-automation.yaml`
- `shared/tests/test_auto_stop.py::TestScaleToZeroAction` テストケース修正:
  - `test_scale_to_zero_calls_update_with_zero_instances`: `MIN_INSTANCE_COUNT=0` を明示（Inference Components エンドポイント向け）
  - `test_scale_to_zero_default_uses_min_instance_count_one` 新規追加（標準エンドポイント向けデフォルト）

### Verified on AWS (ap-northeast-1)

- ✅ cfn-lint 全 15 `template-deploy.yaml` で **0 errors**
- ✅ CloudFormation スタック更新（`EnableSnapStart=true`）で UPDATE_COMPLETE
- ✅ Lambda SnapStart `ApplyOn: PublishedVersions` 設定確認
- ✅ Published Version で `OptimizationStatus: "On"` 確認
- ✅ Step Functions ワークフロー正常実行（21.977 秒）
- ✅ EventBridge Scheduler 定期実行（全 17 回 Succeeded）
- ✅ ユニットテスト **301/301 PASS**

### Known Limitations

- **SnapStart は `$LATEST` には適用されない** — Published Version を公開し、呼び出し側（Step Functions 等）の Resource ARN を Alias/Version ARN に更新する必要がある
- **Lambda Version/Alias の CloudFormation 自動管理は未対応** — コード更新毎に `scripts/enable-snapstart.sh` で再公開が必要
  - 完全自動化には SAM Transform への移行が必要（Phase 7 以降の検討事項）
- **Step Functions Resource の Alias ARN 切替は手動** — 現状では State Machine 定義の手動更新が必要

### Documentation

詳細は以下のドキュメントを参照:
- [SnapStart ガイド](docs/snapstart-guide.md)
- [ローカルテストガイド](docs/local-testing-guide.md)
- [検証結果](docs/verification-results-phase6a.md)
- [残課題チェックリスト](docs/remaining-issues-phase6a.md)

---

## [Phase 5] - 2026-04

- SageMaker Serverless Inference (3rd routing option)
- Cost Optimization Suite (Scheduled Scaling, Billing Alarms, Auto-Stop Lambda)
- CI/CD Pipeline (GitHub Actions with OIDC, 4-stage gating)
- Multi-Region Architecture (DynamoDB Global Tables, DR Tier)

## [Phase 4] - 2026-03

- Production SageMaker Patterns (Inference Components, Shadow Testing, A/B Testing)
- Multi-Account Deployment (StackSets, Delegated Administrator)
- Event-Driven Prototype (FPolicy + Kinesis Data Streams)

## [Phase 3] - 2026-02

- Near-Real-Time Processing (Kinesis Data Streams, UC11 Event-Driven)
- ML Inference Integration (SageMaker Batch Transform, Model Registry)
- Observability Stack (X-Ray, CloudWatch Logs Insights, EMF Metrics)

## [Phase 2] - 2025-12

- 9 additional industry use cases (UC6–UC14)
- Semiconductor EDA, Genomics, Energy, Autonomous Driving, etc.
- Shared module refinements (OntapClient, FsxHelper, S3ApHelper)

## [Phase 1] - 2025-11

- Initial release with 5 industry use cases (UC1–UC5)
- Legal Compliance, Financial IDP, Manufacturing Analytics, Media VFX, Healthcare DICOM
- Common modules (ONTAP REST API client, FSx/S3AP helpers)
