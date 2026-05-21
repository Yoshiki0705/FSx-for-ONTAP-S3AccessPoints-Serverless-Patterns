# FlexCache PoC チェックリスト（共通）

本チェックリストは、FlexCache × S3 Access Points × Serverless パターンの PoC を実施する際の共通チェック項目です。業界固有の項目は各ユースケースの `docs/poc-checklist.md` を参照してください。

## Phase 1: 環境準備

- [ ] FSx for ONTAP ファイルシステム作成済み
- [ ] ONTAP バージョン確認（FlexCache 機能要件を満たすか）
- [ ] SVM 作成済み
- [ ] Origin volume 作成済み（テストデータ投入済み）
- [ ] S3 Access Point 作成済み（Origin volume）
- [ ] Secrets Manager にONTAP認証情報を保存済み
- [ ] IAM ロール/ポリシー設定済み（S3 AP ARN 形式）
- [ ] VPC/サブネット/セキュリティグループ設定済み

## Phase 2: FlexCache 基本検証

- [ ] FlexCache volume 作成成功
- [ ] NFS マウント成功
- [ ] SMB アクセス成功（該当する場合）
- [ ] 読み取りデータの整合性確認
- [ ] Prepopulate 実行成功（ONTAP 9.13.1+）
- [ ] FlexCache volume 削除成功

## Phase 3: S3 AP + FlexCache 検証

- [ ] **FlexCache volume に S3 AP attach 可能か確認**
- [ ] S3 AP 経由 ListObjectsV2 成功
- [ ] S3 AP 経由 GetObject 成功
- [ ] Lambda からの S3 AP アクセス成功
- [ ] Step Functions ワークフロー実行成功

## Phase 4: 性能測定

- [ ] Cache hit ratio 測定
- [ ] Read latency 測定（cache hit / miss）
- [ ] WAN 転送量測定
- [ ] Lambda 実行時間測定
- [ ] Step Functions 全体実行時間測定

## Phase 5: DR/障害テスト

- [ ] FlexCache offline テスト
- [ ] Origin 到達不可テスト
- [ ] Route 53 フェイルオーバーテスト
- [ ] Cleanup 失敗時の復旧テスト

## 成功基準テンプレート

| KPI | 目標値 | 実測値 | 達成 |
|-----|--------|--------|------|
| Cache hit ratio | >___% | | |
| Read latency 改善 | >___% | | |
| WAN 転送量削減 | >___% | | |
| ジョブ時間短縮 | >___% | | |
| Cleanup 成功率 | 100% | | |
