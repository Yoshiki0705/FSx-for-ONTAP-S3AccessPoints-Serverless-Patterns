# ONTAP Integration Notes — S3 AP と既存 NAS 運用の共存ガイド

## 概要

FSx for ONTAP S3 Access Points を使用する場合、既存の NFS/SMB 運用への影響を理解し設計することが重要です。本ドキュメントは ONTAP 管理者・NAS アーキテクト向けのガイダンスです。

## ONTAP Scope Assumptions

| 設計項目 | 本番環境での考慮事項 |
|---------|---------------------|
| SVM | UC ごとに SVM 境界を定義するか、共有 SVM ポリシーを策定 |
| Volume | UC のファイルプレフィックスを特定ボリュームにマッピング |
| Protocol | NFS/SMB/S3 AP のアクセスパスをそれぞれ独立に確認 |
| Identity | S3 AP の file system identity (UNIX/AD) マッピングを検証 |
| Snapshot | 出力書き込みが Snapshot/バックアップポリシーと競合しないことを確認 |
| Export Policy | S3 AP アクセスは Export Policy を通らない（IAM + S3 AP Policy で制御） |

## S3 AP 出力ファイルの NFS/SMB からの見え方

S3 AP 経由で PutObject した場合:
- **ファイル所有者**: S3 AP に関連付けられた file system identity（UNIX UID or Windows AD user）
- **パーミッション**: file system identity のデフォルト umask/ACL に従う
- **タイムスタンプ**: 書き込み時刻が mtime として記録
- **ファイル名**: S3 object key がそのままパスとして使用（`/` はディレクトリ区切り）

> **出典**: [Managing access point access — FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-ap-manage-access-fsxn.html) — "all S3 API operations performed through the access point are authorized using that user's permissions on the file system"

### NFS/SMB クライアントからの確認事項

| 確認項目 | 方法 |
|---------|------|
| 出力ファイルの所有者 | `ls -la` (NFS) / Properties (SMB) で確認 |
| 読み取り権限 | NFS/SMB クライアントから `cat` / `type` で検証 |
| ディレクトリ作成 | S3 AP PutObject で中間ディレクトリが自動作成されることを確認 |
| ファイル名規約 | 出力プレフィックス（例: `reports/daily/YYYY-MM-DD/`）を事前定義 |

## Trigger Mode ガイダンス

| ワークロード特性 | 推奨トリガーモード |
|---|---|
| バッチ文書処理（日次/時間次） | EventBridge Scheduler (POLLING) |
| 新規ファイル到着時の即時処理 | FPolicy event-driven |
| 大規模定期分析 | Scheduler |
| 安全点検画像のアップロード | FPolicy or HYBRID |
| 低頻度ガバナンスレポート | Scheduler |

## UC × FlexCache/FlexClone パターン組み合わせ

| UC | 推奨 FC パターン | 理由 |
|---|---|---|
| UC22 運輸点検 | FC1 (FlexCache Anycast DR) | 遠隔拠点の点検画像キャッシュ |
| UC25 電力設備点検 | FC1 / FC5 | 分散チームでのドローン画像共有 |
| UC28 化学 SDS/ラボノート | FC5 (Life Sciences) | 研究データの安全な共同利用 |
| UC19 広告クリエイティブ | FC2 / FC6 | クリエイティブ/レンダーパイプライン |
| UC18 通信 CDR 分析 | — | Athena 直接クエリ、キャッシュ不要 |

## Data Protection Notes

| 成果物 | Snapshot 対象 | SnapMirror 対象 | 保持期間 |
|--------|:---:|:---:|---|
| 入力ファイル（顧客データ） | ✅ | ✅ | 顧客既存ポリシー |
| 抽出 JSON 結果 | UC 定義 | UC 定義 | Success Metrics に基づく |
| Human Review 決定記録 | ✅ | ✅ | 監査保持期間 |
| 中間プロンプト/出力 | 通常 No | No | 短期保持（7-30日） |
| Manifest JSON | UC 定義 | UC 定義 | 実行履歴として保持 |

> **推奨**: 出力書き込み先を入力データと別プレフィックスまたは別ボリュームにすることで、Snapshot/SnapMirror ポリシーを独立管理可能。

## Security and Identity Notes

- S3 AP アクセスは S3 AP に関連付けた file system identity で認可される
- AD/UNIX マッピングの整合性を ONTAP REST API (`security login show`, `vserver name-mapping show`) で確認
- アクセス拒否シナリオのテスト: 意図しないファイルへのアクセスがブロックされることを検証
- 出力ファイル権限を NFS/SMB クライアントから確認（意図した ownership/permissions か）
- ファイルパスにセンシティブ情報が含まれる場合、ログへのパス出力に注意

## NetApp Support Diagnostic Bundle

障害発生時に NetApp/AWS サポートへ提供する情報:

```
- FSx file system ID
- SVM name
- Volume name (junction path)
- S3 AP name and NetworkOrigin (Internet/VPC)
- Failing object key (redacted if sensitive)
- NFS/SMB からの同一ファイルアクセス結果
- ONTAP REST API レスポンス (該当する場合)
- CloudWatch Lambda execution ID
- Step Functions execution ARN
- FSx CloudWatch metrics (DataReadBytes, NetworkThroughput)
```

## OT / 製造環境での注意事項

UC22 (運輸) / UC25 (電力) / UC28 (化学) は OT 近傍のワークフローですが:

> **重要**: これらのパターンは **点検分析および保守優先度付け** のためのワークフローであり、リアルタイム制御や安全作動のためのシステムではありません。

OT 環境固有の考慮事項:
- バッチ処理 vs リアルタイム要件の切り分け
- VPC-origin S3 AP の優先（閉域網要件）
- オフライン/エッジでのデータステージング
- 厳格な変更ウィンドウ管理
- 手動オーバーライドプロセスの定義

## FSx ONTAP コストに関する注記

> FSx ONTAP コストはリージョン、デプロイタイプ（Single-AZ/Multi-AZ）、SSD 容量、Capacity Pool 容量、throughput capacity、バックアップ、データ転送によって変動します。本リポジトリで記載している $194/月は Single-AZ / 128 MBps / 1 TB SSD の基本見積もりであり、普遍的な価格ではありません。

## DemoMode → Clone PoC → Production の 3 段階

| 段階 | データソース | 特徴 |
|---|---|---|
| DemoMode | 合成 S3 データ | FSx ONTAP 不要、即日開始可能 |
| Clone PoC | FlexClone (本番類似データ) | 本番データに近い検証、容量効率的 |
| Production | Live FSx ONTAP S3 AP | 完全な権限モデル + ガバナンス |

## Field Feedback Log

| 発見事項 | 影響 | 証拠 | 要望 |
|---------|------|------|------|
| Throughput 変更中に S3 AP が ServiceUnavailable | 運用リスク | Phase 14 timeline | 動作の文書化 / 可用性改善 |
| Presigned URL が動くが unsupported | 顧客混乱 | AWS Support case | ドキュメント明確化 |
| VPC-origin benchmark 未実施 | 設計ギャップ | Phase 15 Next | ガイダンス提供 |
| FlexCache × S3 AP 未対応 | 機能ギャップ | FC1 ブロッカー | ロードマップ検討 |
| ListObjectsV2 高レイテンシ (30-80x vs native S3) | 性能制約 | Benchmark data | 最適化 |

---

> **Governance Caveat**: 本ドキュメントは技術ガイダンスであり、法的・コンプライアンス・規制上の助言ではありません。
