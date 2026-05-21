# Dynamic FlexCache Render/EDA Workflow — PoC チェックリスト

## 事前確認

### ONTAP 環境

- [ ] FSx for ONTAP ファイルシステム ID: ___________
- [ ] ONTAP バージョン: ___________ (FlexCache 対応確認)
- [ ] 管理 IP アドレス: ___________
- [ ] Origin SVM 名: ___________
- [ ] Origin Volume 名: ___________
- [ ] Cache SVM 名: ___________
- [ ] アグリゲート名: ___________
- [ ] アグリゲート空き容量: ___________ GB
- [ ] Secrets Manager シークレット名: ___________

### ネットワーク

- [ ] Lambda → ONTAP 管理 IP の到達性確認
- [ ] Lambda → Secrets Manager の到達性確認
- [ ] Lambda → S3 の到達性確認

### データセット

- [ ] ジョブ単位のデータセットサイズ: ___________ GB
- [ ] Prepopulate 対象ディレクトリ: ___________
- [ ] Prepopulate 対象データ量: ___________ GB
- [ ] ファイル数: ___________

## 性能 KPI

### FlexCache 作成時間

- [ ] FlexCache 作成 API レスポンス時間: ___________ 秒
- [ ] FlexCache 作成ジョブ完了時間: ___________ 秒
- [ ] 目標値: < ___________ 秒

### Prepopulate 時間

- [ ] Prepopulate 有無: あり / なし
- [ ] Prepopulate 完了時間: ___________ 秒
- [ ] Prepopulate 対象データ量: ___________ GB

### ジョブ開始までの待ち時間

- [ ] FlexCache 作成 + Prepopulate + ジョブ投入: ___________ 秒
- [ ] 目標値: < ___________ 秒

### ジョブ実行時間

- [ ] FlexCache あり: ___________ 分
- [ ] FlexCache なし（Origin 直接）: ___________ 分
- [ ] 改善率: ___________%

### Cleanup 成功率

- [ ] 正常完了時の cleanup 成功率: ___________% (目標: 100%)
- [ ] 失敗時の cleanup 成功率: ___________% (目標: 100%)
- [ ] Orphan FlexCache 検出数: ___________ (目標: 0)

## セキュリティ

- [ ] IAM least privilege 確認
- [ ] Secrets Manager シークレットのローテーション設定
- [ ] ONTAP RBAC 最小権限ロール設定
- [ ] TLS 検証有効（verify_ssl=True）
- [ ] CloudTrail 監査ログ有効

## 障害テスト

- [ ] FlexCache 作成失敗時の動作確認
- [ ] ジョブ失敗時の cleanup 動作確認
- [ ] ONTAP REST API タイムアウト時のリトライ確認
- [ ] Lambda タイムアウト時の動作確認
- [ ] 二重実行時の冪等性確認

## コスト

- [ ] FlexCache ストレージコスト/ジョブ: $___________
- [ ] Lambda 実行コスト/ジョブ: $___________
- [ ] Step Functions コスト/ジョブ: $___________
- [ ] 月間総コスト見積もり: $___________
- [ ] コスト上限アラーム設定: あり / なし

## 成功条件

- [ ] ジョブ完了時間 ___% 改善
- [ ] Cleanup 成功率 100%
- [ ] Orphan FlexCache 0 件
- [ ] コスト目標内
- [ ] セキュリティ要件充足
