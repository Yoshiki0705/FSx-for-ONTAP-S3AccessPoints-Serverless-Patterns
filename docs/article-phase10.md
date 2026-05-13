---
title: "FPolicy イベント駆動、マルチアカウント StackSets、コスト最適化 — FSx for ONTAP S3 Access Points, Phase 10"
published: false
description: Phase 10 は ONTAP FPolicy を活用したイベント駆動パイプライン、CloudFormation StackSets によるマルチアカウントデプロイ、UC 別アラームプロファイル、営業時間ベースのコストスケジューリングを実装する。
tags: aws, serverless, devops, fsxontap
canonical_url: null
cover_image: null
series: "FSx for ONTAP S3 Access Points"
---

## TL;DR

**Phase 10** は FSx for ONTAP S3 Access Points サーバーレスパターンライブラリの成熟フェーズ。[Phase 9](https://dev.to/yoshikifujiwara/production-rollout-vpc-endpoint-auto-detection-and-the-cdk-no-go-fsx-for-ontap-s3-access-587h) で確立した全 17 UC の運用基盤を土台に、以下を実装:

- **FPolicy イベント駆動統合**: ONTAP FPolicy → SQS → EventBridge → Step Functions のイベント駆動パイプライン。FR-2（S3AP ネイティブ通知）の代替パス
- **マルチアカウント StackSets**: 全 17 UC テンプレートの StackSets 互換性達成 + 新規バリデータ
- **UC 別アラームプロファイル**: BATCH / REALTIME / HIGH_VOLUME の 3 プロファイルで閾値を自動設定
- **コスト最適化**: 営業時間ベースのスケジュール動的変更 + 動的 MaxConcurrency 制御

**リポジトリ**: [github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)

---

## 1. FPolicy イベント駆動アーキテクチャ

### 背景: なぜ FPolicy か

Phase 9 で確認した通り、FSxN S3AP の `GetBucketNotificationConfiguration` は依然 "Not supported"（FR-2 未解決）。全 17 UC がポーリングモデル（EventBridge Scheduler → Discovery Lambda → ListObjectsV2）で動作している。

ONTAP FPolicy は NFS/SMB のファイル操作を検知・通知するフレームワーク。外部サーバーモードで AWS サービスと連携することで、S3AP ネイティブ通知の代替パスを実現できる。

本実装は NetApp 同僚 Shengyu Fang 氏の検証実装（[ontap-fpolicy-aws-integration](https://github.com/YhunerFSY/ontap-fpolicy-aws-integration)）を参考に、本プロジェクトの 17 UC パターンに適合させたものである。

### アーキテクチャ

```
FSx ONTAP SVM (ファイル操作: create/write/delete/rename)
  │
  │ TCP (port 9898, async mode)
  ▼
FPolicy External Server (ECS Fargate)
  │
  ├─ [Near-real-time] → SQS Ingestion Queue → Bridge Lambda → EventBridge Custom Bus
  │                                                                    │
  │                                                          UC 別 EventBridge Rule
  │                                                                    │
  │                                                          Step Functions (per-UC)
  │
  └─ [Batch] → JSON Lines ログ (FSxN S3AP) → Log Query Lambda → SQS → ...
```

### TriggerMode パラメータ

全 17 UC テンプレートに `TriggerMode` パラメータを追加:

| 値 | 動作 |
|---|---|
| `POLLING` (デフォルト) | 既存の EventBridge Scheduler + Discovery Lambda |
| `EVENT_DRIVEN` | FPolicy イベント駆動のみ |
| `HYBRID` | 両方有効 + Idempotency Store で重複排除 |

デフォルト `POLLING` により、既存デプロイへの影響はゼロ。

### NFSv3 Write-Complete 問題

FPolicy イベント受信時点でファイル書き込みが完了していない可能性がある（特に NFSv3）。対策として `WRITE_COMPLETE_DELAY_SEC`（デフォルト 5 秒）の遅延を挿入し、Step Functions 内でもリトライを実装。

---

## 2. マルチアカウント StackSets デプロイ

### StackSets 互換性バリデータ

新規バリデータ `check_stacksets_compatibility.py` を実装。全 17 UC テンプレートに対して:

1. ハードコード Account ID（12 桁数字列）の検出
2. リソース名の一意性検証
3. Export 名の衝突可能性チェック
4. VPC/Subnet/SecurityGroup のパラメータ化確認

結果: **全 17 UC テンプレートで 0 エラー、0 警告**。

### StackSets 実行ロール

`shared/cfn/stacksets-execution.yaml` で最小権限の実行ロールを定義。Organization ID 条件付き信頼ポリシーにより、Organization 外のアカウントからのアクセスを拒否。

---

## 3. UC 別アラームプロファイル

### 3 プロファイル

| プロファイル | 失敗率閾値 | エラー閾値 | 対象 |
|---|---|---|---|
| BATCH | 10% | 3 回/時間 | 定期バッチ処理 |
| REALTIME | 5% | 1 回/時間 | リアルタイム処理 |
| HIGH_VOLUME | 15% | 5 回/時間 | 大量ファイル処理 |

各 UC にワークロード特性に応じたデフォルトプロファイルを割り当て。`CUSTOM` プロファイルで個別閾値指定も可能。

---

## 4. コスト最適化

### 動的 MaxConcurrency

`shared/max_concurrency_controller.py` が検出ファイル数と ONTAP API レートリミットに基づいて最適な並列度を算出:

```python
optimal = min(detected_file_count, ontap_rate_limit // api_calls_per_file, upper_bound)
result = max(optimal, 1)
```

### 営業時間スケジューリング

`EnableCostScheduling=true` で営業時間帯（rate(1 hour)）と非営業時間帯（rate(6 hours)）を自動切り替え。月間コスト削減見積もりをメトリクスとして出力。

---

## 5. 検証結果

| 項目 | 結果 |
|---|---|
| Phase 10 新規テスト | 55 PASS |
| プロパティテスト (Hypothesis) | 7 properties × 100-200 iterations |
| 6 バリデータ | 全 clean |
| Sensitive leaks | 0 |
| StackSets 互換性 | 17/17 templates, 0 errors |

---

## 6. 次フェーズ展望

- **Phase 11 候補**: FPolicy E2E AWS 検証（ECS Fargate デプロイ + FSxN 接続テスト）
- FR-2 が解決された場合の S3AP ネイティブ通知への移行
- Cross-Account Observability の実環境検証
- Athena 結果の FSxN S3AP 書き込み（FR-1 解決待ち）
