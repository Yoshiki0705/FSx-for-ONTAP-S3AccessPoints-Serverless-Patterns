# FlexCache AnyCast / DR — 制約・サポートマトリックス

## プラットフォーム別機能サポート

| 機能 | FSx for ONTAP | On-prem ONTAP | Cloud Volumes ONTAP | Lab/Simulator |
|------|:---:|:---:|:---:|:---:|
| FlexCache origin | ✅ | ✅ | ✅ | ✅ |
| FlexCache cache | ✅ | ✅ | ✅ | ✅ |
| S3 Access Points | ✅ | ❌ | ❌ | ❌ |
| FlexCache volume への S3 AP attach | ⚠️ 未確認 | ❌ | ❌ | ❌ |
| Virtual IP (VIP) | ❌ | ✅ | ❌ | ✅ |
| BGP peer | ❌ | ✅ | ❌ | ✅ |
| AnyCast same IP (BGP) | ❌ | ✅ | ❌ | ✅ |
| MetroCluster 連携 | ❌ | ✅ | ❌ | ⚠️ |
| SVM-DR 連携 | ✅ | ✅ | ⚠️ | ✅ |
| ONTAP REST API automation | ✅ | ✅ | ✅ | ✅ |
| CloudFormation automation | ✅ (FSx リソース) | ❌ | ❌ | ❌ |
| Step Functions orchestration | ✅ | ✅ (API 経由) | ✅ (API 経由) | ✅ |

## FSx for ONTAP 固有の制約

| 制約 | 影響 | 回避策 |
|------|------|--------|
| VIP/BGP 利用不可 | ネイティブ AnyCast 不可 | Route 53 / Global Accelerator / App routing |
| MetroCluster 不可 | サイト間同期ミラー不可 | Multi-AZ HA + SnapMirror |
| IPspace/VRF 制御不可 | ネットワーク分離制限 | VPC / サブネット分離 |
| ONTAP CLI 一部制限 | 一部コマンド実行不可 | REST API 利用 |
| ストレージ容量上限 | ファイルシステムサイズ制限 | 複数ファイルシステム分散 |

## FlexCache 固有の制約

| 制約 | 影響 | 回避策 |
|------|------|--------|
| 読み取りキャッシュ（9.15.1 未満） | 書き込みは Origin 経由 | Writeback 対応バージョンへ更新 |
| メタデータキャッシュ TTL | 古いメタデータ参照の可能性 | TTL 調整、手動 invalidate |
| Origin 障害時の新規読み取り不可 | キャッシュ済みデータのみ読み取り可 | Prepopulate で事前キャッシュ |
| FlexCache サイズ制限 | Origin 全データはキャッシュ不可 | ホットデータのみキャッシュ |
| クロスクラスタ遅延 | WAN 経由の初回読み取り遅延 | Prepopulate、Direct Connect |

## S3 Access Points 固有の制約

| 制約 | 影響 | 回避策 |
|------|------|--------|
| Event Notifications 非対応 | イベント駆動不可 | EventBridge Scheduler ポーリング |
| Lifecycle Policy 非対応 | 自動削除不可 | Lambda スイーパー |
| Versioning 非対応 | バージョン管理不可 | DynamoDB でバージョン管理 |
| 5GB アップロード上限 | 大ファイル書き込み制限 | NFS/SMB 経由で書き込み |
| SSE-FSX のみ | カスタム KMS 不可 | FSx ボリューム KMS 設定 |
| NetworkOrigin 変更不可 | 作成後のアクセス経路変更不可 | 事前に適切な設定で作成 |

## AnyCast 代替パターンの比較

| 方式 | 切替速度 | 自動化 | コスト | 適用シナリオ |
|------|---------|--------|--------|------------|
| Route 53 Failover | 60-300秒 | ✅ | 低 | DR |
| Route 53 Weighted | 即時（確率的） | ✅ | 低 | 負荷分散 |
| Route 53 Latency | 即時 | ✅ | 低 | マルチリージョン |
| Global Accelerator | 数秒 | ✅ | 中 | 高可用性 |
| NLB + Target Group | 数秒 | ✅ | 中 | VPC 内 |
| Lambda routing | 即時 | ✅ | 低 | カスタムロジック |
| BGP AnyCast (オンプレ) | <1秒 | ✅ | 低 | オンプレ限定 |

## 既知の問題と注意事項

1. **FlexCache volume への S3 AP attach**: AWS ドキュメントに明示的な記載がなく、PoC で要検証
2. **FlexCache disconnected mode**: FSx for ONTAP での動作は未確認
3. **クロスリージョン FlexCache**: FSx for ONTAP 間のクラスタピアリングは Transit Gateway / VPC Peering が必要
4. **Prepopulate の大量ファイル**: 数百万ファイルの prepopulate は時間がかかる可能性
5. **S3 AP + FlexCache writeback**: writeback 有効時の S3 AP 経由書き込みの動作は未確認

## 推奨事項

### PoC フェーズ

1. まず Origin volume + S3 AP の基本動作を確認
2. 次に FlexCache volume を作成し、NFS/SMB アクセスを確認
3. FlexCache volume に S3 AP を attach 可能か確認
4. 不可の場合は Origin volume の S3 AP を使用し、FlexCache は NFS/SMB クライアント用に限定

### 本番フェーズ

1. FlexCache サイズはホットデータの 1.2-1.5 倍を推奨
2. Prepopulate は営業時間外に実行
3. ヘルスチェックは 5 分間隔を推奨
4. Orphan FlexCache 検出は 1 時間間隔を推奨
5. DR テストは月次で実施
