# データ鮮度と RPO

[日本語](data-freshness-ja.md) | [English](data-freshness.md)

## レプリケーションモデル

このパターンでは、オンプレミス ONTAP から Amazon FSx for NetApp ONTAP への **スケジュールベースの非同期 SnapMirror レプリケーション** を使用します。AWS ドキュメントによると、レプリケーションは最短5分間隔でスケジュール可能です。

> **重要**: FSx for ONTAP はボリュームレベルの SnapMirror のみサポートします。Synchronous SnapMirror（StrictSync 含む）および SVM Disaster Recovery（SVMDR）はサポートされていません。
> 
> 参考: [AWS FSx ONTAP SnapMirror Documentation](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/scheduled-replication.html)

## データ鮮度タイムライン

```
Source file written    → SnapMirror update triggered → Transfer complete → S3 AP readable → Quick visible
     t=0                    t=0 (on-demand)              t+2-10s            t+0s (immediate)   t+sync interval
                         or t=schedule (max 5min)
```

## RPO 特性

| シナリオ | RPO | 備考 |
|---------|-----|------|
| スケジュールレプリケーション（5分） | ≤ 5分 | 標準的な継続保護 |
| オンデマンドトリガー（このツール） | 数秒 | 手動 update を即時トリガー |
| 併用（スケジュール + オンデマンド） | デモ中はほぼゼロ | オンデマンドがスケジュール間のギャップを埋める |

## 検証用の主要タイムスタンプ

| タイムスタンプ | ソース | 確認方法 |
|--------------|--------|---------|
| ソースファイル更新日時 | オンプレミス ONTAP | `stat` または NFS/SMB 属性 |
| 最後の SnapMirror 転送完了 | FSx ONTAP REST API | `GET /api/snapmirror/relationships/{uuid}?fields=transfer` |
| S3 AP オブジェクト可用性 | S3 API | S3 AP エイリアス経由の `ListObjectsV2` / `GetObject` |
| Quick データセット更新 | Amazon Quick コンソール | データソース同期ステータス |

## 整合性に関する考慮事項

- SnapMirror はソースボリュームの **クラッシュ一貫性のある** ポイントインタイム Snapshot を転送する
- 転送時に書き込み中（open for write）のファイルは、最新のインフライト書き込みを含まない場合がある
- S3 Access Point は SnapMirror 転送完了直後の Destination ボリュームの状態を反映する
- Amazon Quick のデータセット更新は、同期スケジュール設定に依存して追加のレイテンシが発生する

## 用語定義

| 用語 | この文脈での意味 |
|------|----------------|
| "Near real-time" | オンデマンドトリガーで数秒以内、またはスケジュール間隔以内に AWS でデータ利用可能 |
| "Scheduled replication" | ONTAP 管理による定期的な SnapMirror update（FSx での最短間隔は5分） |
| "On-demand sync" | このツールのワンクリックボタンでトリガーされる手動 `snapmirror update` |

## このパターンが提供しないもの

- 同期レプリケーション（FSx for ONTAP ではサポート対象外）
- サブ秒レベルの RPO 保証
- ソースとデスティネーション間のトランザクションレベルの整合性
- 双方向書き込みの自動競合解決
