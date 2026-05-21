# FlexCache AnyCast / DR — PoC チェックリスト

## 事前確認

### ONTAP バージョン

- [ ] FSx for ONTAP の ONTAP バージョン確認: ___________
- [ ] FlexCache 基本機能のサポート確認
- [ ] Prepopulate サポート確認 (9.13.1+)
- [ ] Disconnected mode サポート確認 (9.12.1+)
- [ ] Global file lock サポート確認 (9.14.1+)
- [ ] Writeback サポート確認 (9.15.1+)

### FSx for ONTAP ファイルシステム構成

- [ ] ファイルシステム ID: ___________
- [ ] デプロイメントタイプ: Single-AZ / Multi-AZ
- [ ] スループットキャパシティ: ___________ MB/s
- [ ] ストレージキャパシティ: ___________ GB
- [ ] SVM 名: ___________
- [ ] Origin volume 名: ___________
- [ ] Origin volume サイズ: ___________ GB
- [ ] Origin volume セキュリティスタイル: UNIX / NTFS / Mixed

### FlexCache サポート

- [ ] FlexCache volume の作成が可能か確認
- [ ] FlexCache volume のサイズ設定（Origin の 10-20% 推奨）
- [ ] FlexCache volume の junction path 設定
- [ ] クロスクラスタ FlexCache の場合: クラスタピアリング設定確認
- [ ] クロスクラスタ FlexCache の場合: SVM ピアリング設定確認

### S3 Access Points サポート

- [ ] Origin volume に S3 AP が attach 済みか確認
- [ ] **FlexCache volume に S3 AP を attach 可能か確認**（重要: 未確認事項）
- [ ] S3 AP の NetworkOrigin 設定: Internet / VPC
- [ ] S3 AP エイリアス: ___________
- [ ] S3 AP 名（IAM ARN 用）: ___________
- [ ] IAM ポリシーの ARN 形式が正しいか確認

### NFS/SMB/S3 API 利用要件

- [ ] NFS クライアントからの FlexCache マウント確認
- [ ] SMB クライアントからの FlexCache アクセス確認（該当する場合）
- [ ] S3 API (boto3) からの S3 AP 経由アクセス確認
- [ ] Lambda からの S3 AP アクセス確認（VPC 内/外）

### ネットワーク到達性

- [ ] Lambda → S3 AP の到達性確認
- [ ] Lambda → ONTAP REST API (管理 IP) の到達性確認
- [ ] クライアント → FlexCache volume の到達性確認
- [ ] Origin ↔ Cache 間のネットワーク帯域: ___________ Gbps
- [ ] Origin ↔ Cache 間のレイテンシ: ___________ ms

### DNS/VIP/BGP/Route 53 等の方式

- [ ] FSx for ONTAP の場合: Route 53 Failover/Weighted 設定
- [ ] オンプレ ONTAP の場合: VIP/BGP 設定確認
- [ ] DNS TTL 設定: ___________ 秒
- [ ] ヘルスチェック間隔: ___________ 秒

## データセット確認

### ファイル数

- [ ] 総ファイル数: ___________
- [ ] ディレクトリ数: ___________
- [ ] 最大ディレクトリ内ファイル数: ___________

### 平均/最大ファイルサイズ

- [ ] 平均ファイルサイズ: ___________ MB
- [ ] 最大ファイルサイズ: ___________ GB
- [ ] 最小ファイルサイズ: ___________ KB

### ホット/コールド比率

- [ ] ホットデータ比率（直近 7 日アクセス）: ___________%
- [ ] ウォームデータ比率（直近 30 日アクセス）: ___________%
- [ ] コールドデータ比率: ___________%
- [ ] FlexCache サイズ推奨値（ホットデータ × 1.2）: ___________ GB

### 読み取り/書き込み比率

- [ ] 読み取り比率: ___________%
- [ ] 書き込み比率: ___________%
- [ ] メタデータアクセス比率: ___________%

### メタデータアクセス量

- [ ] ls/readdir 頻度: ___________ 回/時間
- [ ] stat/getattr 頻度: ___________ 回/時間
- [ ] ACL チェック頻度: ___________ 回/時間

## 性能 KPI

### 初回 read latency

- [ ] Origin 直接読み取り: ___________ ms
- [ ] FlexCache 初回読み取り（cache miss）: ___________ ms
- [ ] 目標値: ___________ ms

### Cache hit 後 read latency

- [ ] FlexCache cache hit 読み取り: ___________ ms
- [ ] 目標値: ___________ ms
- [ ] 改善率: ___________%

### Cache hit ratio

- [ ] 初期（prepopulate 前）: ___________%
- [ ] Prepopulate 後: ___________%
- [ ] 定常状態（1 週間後）: ___________%
- [ ] 目標値: >___________%

### WAN 転送量削減率

- [ ] FlexCache なし（1 日あたり）: ___________ GB
- [ ] FlexCache あり（1 日あたり）: ___________ GB
- [ ] 削減率: ___________%
- [ ] 目標値: >___________%

### ジョブ完了時間

- [ ] FlexCache なし: ___________ 分
- [ ] FlexCache あり: ___________ 分
- [ ] 改善率: ___________%

### Lambda/Step Functions 実行時間

- [ ] Discovery Lambda: ___________ 秒
- [ ] Processing Lambda: ___________ 秒
- [ ] Report Lambda: ___________ 秒
- [ ] Step Functions 全体: ___________ 秒

### S3 API 処理時間

- [ ] ListObjectsV2: ___________ ms
- [ ] GetObject (小ファイル <1MB): ___________ ms
- [ ] GetObject (大ファイル >100MB): ___________ ms

## セキュリティ

- [ ] IAM least privilege ポリシー設定
- [ ] S3 AP ARN 形式の正確性確認
- [ ] Secrets Manager シークレット作成
- [ ] KMS キー設定（出力暗号化）
- [ ] ONTAP RBAC ロール設定（FlexCache 操作用）
- [ ] ファイル ACL/UNIX 権限の FlexCache 経由での保持確認
- [ ] S3 AP resource policy 設定
- [ ] VPC endpoint 設定（該当する場合）
- [ ] CloudTrail 監査ログ有効化

## DR/障害試験

### Cache node failure

- [ ] FlexCache volume のオフライン化テスト
- [ ] クライアントの自動フェイルオーバー確認
- [ ] S3 AP アクセスの代替パス確認
- [ ] 復旧時間: ___________ 秒

### Origin unreachable

- [ ] Origin volume への到達不可シミュレーション
- [ ] FlexCache disconnected mode の動作確認
- [ ] 読み取り継続性の確認
- [ ] 書き込み動作の確認（エラーハンドリング）

### Route withdrawal (BGP/DNS)

- [ ] DNS レコード変更テスト
- [ ] Route 53 ヘルスチェック失敗シミュレーション
- [ ] フェイルオーバー時間: ___________ 秒
- [ ] フェイルバック時間: ___________ 秒

### Step Functions retry

- [ ] Lambda タイムアウト時のリトライ動作確認
- [ ] ONTAP REST API エラー時のリトライ動作確認
- [ ] 最大リトライ回数の設定確認

### Cleanup 失敗時の補正

- [ ] FlexCache 削除失敗時の再試行確認
- [ ] Orphan FlexCache の検出メカニズム確認
- [ ] 手動 cleanup 手順の文書化

## 成功条件

### 性能改善

- [ ] Cache hit ratio > ___% 達成
- [ ] Read latency ___% 改善達成
- [ ] ジョブ完了時間 ___% 短縮達成
- [ ] WAN 転送量 ___% 削減達成

### コスト削減

- [ ] ストレージコスト削減: $___ /月
- [ ] データ転送コスト削減: $___ /月
- [ ] コンピュートコスト削減（ジョブ時間短縮）: $___ /月
- [ ] 総 TCO 削減率: ___%

### 運用自動化

- [ ] FlexCache ライフサイクル自動化達成
- [ ] ヘルスチェック自動化達成
- [ ] フェイルオーバー自動化達成
- [ ] レポート自動生成達成

### セキュリティ要件充足

- [ ] IAM least privilege 確認
- [ ] 暗号化要件充足
- [ ] 監査ログ要件充足
- [ ] コンプライアンス要件充足

### 既存アプリ変更最小化

- [ ] NFS/SMB クライアント設定変更: なし / 最小限
- [ ] アプリケーションコード変更: なし / 最小限
- [ ] 運用手順変更: 最小限
- [ ] 既存 UC パイプラインへの影響: なし

## 次のステップ

PoC 完了後:
1. 結果を本チェックリストに記入
2. 成功条件の達成状況を評価
3. 本番環境への移行計画を策定
4. [運用ランブック](operations-runbook.md) に基づく運用設計
5. [DR パターン](disaster-recovery-patterns.md) の選定と実装
