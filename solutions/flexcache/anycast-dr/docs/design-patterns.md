# FlexCache AnyCast / DR — 設計パターン集

## Pattern A: Static FlexCache + S3 AP Serverless Analytics

### 適用業界
半導体 EDA、製造業、法務・コンプライアンス、金融

### 解決する課題
- 読み取り頻度の高いデータへの低レイテンシアクセス
- WAN 転送量の削減
- サーバーレス処理環境近傍へのデータ配置

### 推奨構成
```
[Origin Volume] ──(常時)── [FlexCache Volume] ──── [S3 Access Point] ──── [Lambda/Step Functions]
```

### 主要 AWS サービス
- FSx for ONTAP (Origin + FlexCache)
- S3 Access Points
- Lambda, Step Functions, EventBridge Scheduler
- Athena, Bedrock

### 主要 ONTAP 機能
- FlexCache (read cache)
- Prepopulate (9.13.1+)
- Volume snapshot

### S3 Access Points の役割
- FlexCache volume 上のデータを S3 API 経由で Lambda に提供
- NFS マウント不要でサーバーレス処理を実現

### Lambda/Step Functions の役割
- 定期的な Discovery → Processing → Report パイプライン
- AI/ML サービス（Bedrock, Athena）との連携

### セキュリティ考慮
- IAM least privilege (S3 AP ARN 形式)
- Secrets Manager (ONTAP 認証情報)
- KMS (出力暗号化)
- ONTAP RBAC (FlexCache 操作権限)

### コスト最適化ポイント
- FlexCache サイズを最小限に（ホットデータのみ）
- TTL 調整でキャッシュ効率最大化
- VPC Endpoints はオプショナル

### PoC で見るべき KPI
- Cache hit ratio (目標: >80%)
- Read latency (cache hit 時 vs origin 直接)
- WAN 転送量削減率
- Lambda 実行時間

---

## Pattern B: Dynamic FlexCache per Job / per Project

### 適用業界
メディア VFX、半導体 EDA（クラウドバースト）、自動車 CAE

### 解決する課題
- ジョブ実行時のみデータが必要（常時キャッシュは無駄）
- ジョブ完了後のストレージコスト削減
- プロジェクト/ジョブ単位のデータ分離

### 推奨構成
```
Job Request → [Create FlexCache] → [Prepopulate] → [Run Job] → [Cleanup FlexCache]
                    ↓                                              ↓
              ONTAP REST API                                 ONTAP REST API
```

### 主要 AWS サービス
- FSx for ONTAP
- Step Functions (ワークフロー制御)
- Lambda (ONTAP REST API 呼び出し)
- Secrets Manager
- SNS (通知)

### 主要 ONTAP 機能
- FlexCache create/delete (REST API)
- Prepopulate (dir_paths 指定)
- Job monitoring (async job polling)

### S3 Access Points の役割
- ジョブ実行中のデータ読み取り（Lambda 経由）
- ジョブ結果の分析・レポート生成

### Lambda/Step Functions の役割
- FlexCache ライフサイクル管理（作成→準備→ジョブ→削除）
- ONTAP REST API の非同期ジョブ監視
- 失敗時の cleanup 保証

### セキュリティ考慮
- ジョブ ID によるリソースタグ付け
- cleanup 失敗時の orphan 検出
- ONTAP RBAC 最小権限

### コスト最適化ポイント
- ジョブ実行時のみ FlexCache 存在 → ストレージコスト最小化
- Prepopulate 対象を必要ディレクトリに限定
- orphan FlexCache の定期検出・削除

### PoC で見るべき KPI
- FlexCache 作成時間 (目標: <60秒)
- Prepopulate 完了時間
- ジョブ開始までの待ち時間
- Cleanup 成功率 (目標: 100%)
- Orphan FlexCache 数 (目標: 0)

---

## Pattern C: FlexCache DR Read Locality

### 適用業界
金融、医療、政府、法務

### 解決する課題
- Origin 障害時の読み取り継続性
- DR サイトでのデータアクセス
- RTO/RPO 要件の充足

### 推奨構成
```
[Primary Origin] ──── [FlexCache (Secondary Site)]
       ↓ (障害時)                    ↓
[SnapMirror Destination] ──── [FlexCache re-peer]
```

### 主要 AWS サービス
- FSx for ONTAP (Multi-AZ HA)
- Route 53 (Failover routing)
- CloudWatch (ヘルスチェック)
- Lambda (フェイルオーバー自動化)
- Step Functions (DR ワークフロー)

### 主要 ONTAP 機能
- FlexCache disconnected mode (9.12.1+)
- SnapMirror (volume replication)
- SVM-DR
- FlexCache re-peer

### S3 Access Points の役割
- DR 時も S3 AP 経由でサーバーレス処理を継続
- Origin 切替後の新 S3 AP への自動ルーティング

### セキュリティ考慮
- DR サイトの IAM ポリシー事前設定
- Secrets Manager のクロスリージョンレプリケーション
- KMS キーのクロスリージョン設定

### コスト最適化ポイント
- DR サイトは最小構成で待機
- FlexCache disconnected mode で Origin 障害時も読み取り継続
- 定期的な DR テストの自動化

### PoC で見るべき KPI
- フェイルオーバー時間 (RTO)
- データ損失量 (RPO)
- DR 時の読み取りレイテンシ
- フェイルバック時間

---

## Pattern D: EDA Cloud Burst with On-prem Origin and FSx Cache

### 適用業界
半導体 EDA、HPC

### 解決する課題
- オンプレ EDA ライセンスサーバーの制約
- ピーク時のコンピュートリソース不足
- クラウドバースト時のデータアクセス性能

### 推奨構成
```
[On-prem ONTAP (Origin)]
    ├── Tools/Libraries/PDK → FlexCache (FSx) → EDA Compute (EC2/Batch)
    ├── Scratch → FSx native volume (local)
    └── Results → S3 AP → Lambda → Athena/Bedrock
```

### 主要 AWS サービス
- FSx for ONTAP (FlexCache)
- EC2 / AWS Batch (EDA compute)
- Direct Connect / VPN
- S3 Access Points
- Lambda, Athena, Bedrock

### 主要 ONTAP 機能
- FlexCache (Tools/Libraries/PDK 用)
- Cluster peering (on-prem ↔ FSx)
- Prepopulate

### PoC で見るべき KPI
- EDA ジョブ完了時間（クラウドバースト vs オンプレのみ）
- ライセンス利用効率
- WAN 転送量
- コスト/ジョブ

---

## Pattern E: Media/VFX Render Farm with Temporary Cache

### 適用業界
メディア VFX、アニメーション

### 解決する課題
- レンダリングジョブの入力データアクセス性能
- ジョブ完了後のストレージコスト
- 複数レンダーノードからの同時読み取り

### 推奨構成
```
[Origin (Assets/Textures/Plates)]
    → [FlexCache (per render job)] → [Render Nodes (EC2/Batch)]
    → [S3 AP] → [Lambda (QC/Metadata)] → [Rekognition/Bedrock]
```

### 主要 AWS サービス
- FSx for ONTAP
- AWS Deadline Cloud / AWS Batch
- S3 Access Points
- Lambda, Rekognition, Bedrock

### PoC で見るべき KPI
- レンダリング開始までの待ち時間
- フレームあたりのレンダリング時間
- FlexCache 作成→削除のサイクルタイム
- コスト/フレーム

---

## Pattern F: GenAI/RAG over Cached Enterprise File Data

### 適用業界
全業界（特に金融、法務、医療）

### 解決する課題
- 機密ファイルを S3 にコピーしたくない
- AI 処理環境近傍にデータを配置したい
- ファイル権限（ACL）を維持したまま RAG 処理

### 推奨構成
```
[Enterprise Files (Origin)]
    → [FlexCache (AI Processing VPC)]
    → [S3 Access Point]
    → [Lambda (Embedding/Chunking)]
    → [Bedrock Knowledge Base / OpenSearch]
```

### 主要 AWS サービス
- FSx for ONTAP
- S3 Access Points
- Lambda (embedding, chunking)
- Amazon Bedrock (RAG)
- OpenSearch Serverless (vector store)

### 主要 ONTAP 機能
- FlexCache (AI 処理環境近傍配置)
- File security API (ACL 取得)
- Volume snapshot (point-in-time consistency)

### PoC で見るべき KPI
- Embedding 処理時間
- RAG 応答精度
- 権限チェックのオーバーヘッド
- データ鮮度（キャッシュ TTL vs 更新頻度）

---

## Pattern G: Manufacturing Simulation / CAE / Telemetry Analytics

### 適用業界
自動車、航空宇宙、製造業

### 解決する課題
- 設計拠点とテスト拠点間のデータ共有
- シミュレーション入力データの高速アクセス
- テレメトリデータの集約分析

### 推奨構成
```
[Design Center (Origin)]
    → [FlexCache (Test Center / Cloud)]
    → [S3 AP]
    → [Lambda/Glue (ETL)]
    → [Athena/QuickSight (Analytics)]
```

### 主要 AWS サービス
- FSx for ONTAP
- S3 Access Points
- Lambda, Glue, Athena, QuickSight
- Step Functions

### PoC で見るべき KPI
- シミュレーション入力データの読み取り時間
- ETL 処理時間
- 分析クエリ応答時間
- 拠点間データ同期遅延

---

## パターン比較サマリー

| パターン | FlexCache ライフサイクル | S3 AP 利用 | 主要 Serverless | コスト特性 |
|---------|----------------------|-----------|----------------|-----------|
| A: Static | 常時稼働 | 常時 | Lambda + Athena | 固定 |
| B: Dynamic | ジョブ単位 | ジョブ中のみ | Step Functions + Lambda | 変動 |
| C: DR | 常時（DR 待機） | DR 時 | Lambda + Route 53 | 低（待機時） |
| D: Cloud Burst | バースト時 | バースト中 | Batch + Lambda | ピーク時のみ |
| E: Render Farm | ジョブ単位 | ジョブ中 | Deadline + Lambda | 変動 |
| F: GenAI/RAG | 常時 | 常時 | Lambda + Bedrock | 固定 + API |
| G: CAE | プロジェクト単位 | 分析時 | Glue + Athena | 変動 |
