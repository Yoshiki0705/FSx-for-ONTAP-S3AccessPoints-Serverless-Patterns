# UC29: Self-Service Knowledge Base Curation — アーキテクチャ

## 概要

FSx for ONTAP 上の **AI 専用ボリューム** を SMB（Windows 共有）で各ロール・部署に公開し、
業務ユーザーがドラッグ&ドロップでナレッジを維持する。同じデータを **S3 Access Point
経由（読み取りパス）** でマネージドな Amazon Bedrock Knowledge Base に接続し、ファイル
投入を検知して自動で取り込む。

本パターンは **マネージド RAG（Pattern C）** を採用し、運用負荷を最小化する。
検索時のファイルレベル権限制御が必要な場合は UC である [FC3 genai-rag-enterprise-files](../../genai-rag-enterprise-files/)（カスタム RAG, Pattern A）を選択する。

取り込みトリガーは運用成熟度に応じて 3 段階を提供する: **A（手動）→ B（EventBridge Scheduler 定期）→ C（FPolicy イベント駆動リアルタイム）**。
業務ユーザーのファイル操作はどのシナリオでも不変で、変わるのは検知→同期の仕組みだけ。

## アーキテクチャ図

```
┌──────────────────────────────────────────────────────────────────────────┐
│                   Self-Service Knowledge Base Curation                     │
│                                                                            │
│  業務ユーザー（各ロール・部署）                                            │
│  ┌───────────────────┐                                                     │
│  │ Windows Explorer  │  ドラッグ&ドロップ（追加/更新/削除）                │
│  └─────────┬─────────┘                                                     │
│            │ SMB 書き込み                                                  │
│            ▼                                                               │
│  ┌───────────────────┐        ┌──────────────────────────────────────┐    │
│  │  FSx for ONTAP    │        │   セルフサービス自動同期             │    │
│  │  AI 専用ボリューム │        │                                      │    │
│  │  /ai-knowledge/   │        │  ┌──────────────┐  ┌──────────────┐  │    │
│  │   <部署>/         │        │  │ EventBridge  │─▶│ Auto-Sync    │  │    │
│  │  (NTFS ACL)       │        │  │ Scheduler    │  │ Lambda       │  │    │
│  └─────────┬─────────┘        │  └──────────────┘  └──────┬───────┘  │    │
│            │ 読み取りパス     │                           │          │    │
│            ▼                  │   ① ListObjectsV2 差分検知 │          │    │
│  ┌───────────────────┐◀───────────────────────────────────┘          │    │
│  │  S3 Access Point  │       │   ② StartIngestionJob                  │    │
│  │  (読み取り)       │───────────────────────┐  └─────────────────────┘    │
│  └─────────┬─────────┘                       │                             │
│            │ データ取得                      ▼                             │
│            ▼                       ┌──────────────────┐                    │
│  ┌──────────────────────┐         │ Amazon Bedrock   │                    │
│  │ Bedrock Knowledge    │◀────────│ Knowledge Base   │                    │
│  │ Base データソース    │         │ (マネージド RAG) │                    │
│  │ = S3 AP              │         └────────┬─────────┘                    │
│  └──────────────────────┘                  │                              │
│                                             ▼                              │
│                                    ┌──────────────────┐                    │
│            ┌──────────────┐        │ Query Lambda     │                    │
│            │ 利用者       │───────▶│ RetrieveAndGen.  │                    │
│            └──────────────┘        └────────┬─────────┘                    │
│                                             ▼                              │
│                                    ┌──────────────────┐                    │
│                                    │ Foundation Model │                    │
│                                    │ (Nova / Claude)  │                    │
│                                    └──────────────────┘                    │
└──────────────────────────────────────────────────────────────────────────┘
```

## コンポーネント

| コンポーネント | 役割 |
|--------------|------|
| FSx for ONTAP AI 専用ボリューム | ナレッジの正本。SMB でユーザーが直接維持 |
| S3 Access Point | AI 取り込みのための読み取りパス（書き込みは SMB/NFS のみ） |
| EventBridge Scheduler | 定期的に Step Functions を起動（シナリオ B） |
| Auto-Sync Lambda | S3 AP で差分検知 → Bedrock KB の Ingestion 起動 |
| Ingestion Status Lambda | Ingestion ジョブの完了をポーリング判定（シナリオ B） |
| Step Functions | 検知→取り込み→完了待ち→通知のオーケストレーション（シナリオ B） |
| FPolicy Server (ECS/EC2) | NFS/SMB ファイル操作のリアルタイム検知（シナリオ C） |
| FPolicy Persistent Store | サーバーダウンタイム中のイベント保全（シナリオ C） |
| SQS + Bridge Lambda | FPolicy イベントを EventBridge カスタムバスへ配信（シナリオ C） |
| EventBridge Rule (ai_knowledge) | ボリュームパス一致イベントを KB Trigger Lambda へルーティング（シナリオ C） |
| KB Trigger Lambda | FPolicy イベント → StartIngestionJob（デバウンス付き）（シナリオ C） |
| Amazon Bedrock Knowledge Base | マネージド RAG（データソース = S3 AP） |
| Query Lambda | RetrieveAndGenerate による Q&A（デモ用） |
| SNS | 同期結果の通知（投入件数・失敗） |

## 3 つの運用シナリオ

本 UC は同じ基盤上で 3 段階の運用を提供する。A（手動）→ B（定期自動化）→ C（リアルタイム）と
運用成熟度に応じて段階的に進化させられる。

### シナリオ A: 手動メンテナンス（Windows ファイル操作）

```
業務ユーザー → Windows ドラッグ&ドロップ（追加/更新/削除）
            → 人が手動で同期（Bedrock コンソール「同期」/ CLI start-ingestion-job）
            → get-ingestion-job で完了確認
```

使い慣れたファイル操作で AI データを維持する体験。取り込みは人が手動でトリガーする。
サーバーレスの自動化リソース（Step Functions / Scheduler）は不要で、KB と S3 AP のみで成立する。

### シナリオ B: 自動化（Lambda + Step Functions）

```
EventBridge Scheduler
   → Step Functions
       DetectAndStartIngestion (Auto-Sync Lambda)   … 差分検知 + StartIngestionJob
       → Choice 変更あり？（なければ Succeed）
       → Wait 30s
       → CheckIngestionStatus (Ingestion Status Lambda)  … GetIngestionJob ポーリング
       → Choice COMPLETE / FAILED /（未完了なら Wait へループ）
       → SNS 通知
```

シナリオ A の「手動同期・完了確認」を Step Functions のステートに置き換え、人の手作業を排除する。
業務ユーザーの操作（ドラッグ&ドロップ）は A と同一で、取り込み以降が自動化される。

## Step Functions ステート遷移図（シナリオ B）

```
[Start]
   ▼
DetectAndStartIngestion ── status != ingestion_started ──▶ NoChange [Succeed]
   │ status == ingestion_started
   ▼
WaitForIngestion (30s) ◀───────────────┐
   ▼                                    │ ingestion_status ∉ {COMPLETE, FAILED}
CheckIngestionStatus ───────────────────┘
   │
   ├── COMPLETE ─▶ NotifySuccess [End]
   └── FAILED   ─▶ NotifyFailure [End]
```

### シナリオ C: FPolicy イベント駆動（リアルタイム同期）

```
業務ユーザー → Windows/NFS ファイル操作（追加/更新/削除）
            → FPolicy が即時検知（CREATE/WRITE/DELETE/RENAME）
            → FPolicy Server → SQS → Bridge Lambda → EventBridge カスタムバス
            → EventBridge Rule（file_path prefix = ai_knowledge）
            → KB Trigger Lambda（デバウンス）→ StartIngestionJob
            → SNS 通知 + 即座に Query 可能
```

シナリオ B の「EventBridge Scheduler による 15 分間隔ポーリング」を、FPolicy のリアルタイム検知に
置き換える。ファイルが配置された**瞬間**に同期が始まり、反映レイテンシは数十秒〜数分（Ingestion 処理時間依存）。
業務ユーザーの操作（ドラッグ&ドロップ）は A / B と同一。

## シナリオ C アーキテクチャ図（FPolicy イベント駆動）

```
┌──────────────────────────────────────────────────────────────────────────┐
│              Scenario C: FPolicy Event-Driven Real-Time Sync               │
│                                                                            │
│  業務ユーザー                                                              │
│  ┌───────────────────┐                                                     │
│  │ Windows Explorer  │  ドラッグ&ドロップ（追加/更新/削除）                │
│  └─────────┬─────────┘                                                     │
│            │ SMB / NFS 書き込み                                            │
│            ▼                                                               │
│  ┌───────────────────┐   FPolicy 通知（CREATE/WRITE/DELETE/RENAME）        │
│  │  FSx for ONTAP    │──────────────┐                                      │
│  │  ai_knowledge vol │              ▼                                      │
│  │  (NTFS, S3 AP 付) │     ┌──────────────────┐                            │
│  └─────────┬─────────┘     │ FPolicy Server   │                            │
│            │ 読み取りパス  │ (ECS Fargate/EC2)│                            │
│            │               └────────┬─────────┘                            │
│            │                        ▼ (Persistent Store でダウンタイム保全)│
│            │               ┌──────────────────┐                            │
│            │               │ SQS Ingestion Q  │                            │
│            │               └────────┬─────────┘                            │
│            │                        ▼                                      │
│            │               ┌──────────────────┐                            │
│            │               │ Bridge Lambda    │ PutEvents                  │
│            │               └────────┬─────────┘                            │
│            │                        ▼                                      │
│            │               ┌──────────────────────────┐                   │
│            │               │ EventBridge Custom Bus    │                   │
│            │               │ (fsxn-fpolicy-events)     │                   │
│            │               └────────┬─────────────────┘                   │
│            │                        ▼ Rule: file_path prefix = ai_knowledge│
│            │               ┌──────────────────┐                            │
│            │               │ KB Trigger Lambda│ デバウンス                 │
│            │               │ (進行中ならスキップ)                          │
│            │               └────────┬─────────┘                            │
│            │                        ▼ StartIngestionJob                    │
│            ▼                ┌──────────────────┐                           │
│  ┌──────────────────┐      │ Amazon Bedrock   │                           │
│  │ S3 Access Point  │─────▶│ Knowledge Base   │──▶ SNS 通知                │
│  │ (読み取り)       │ data │ (マネージド RAG) │                           │
│  └──────────────────┘      └──────────────────┘                           │
│                                                                            │
│  反映レイテンシ: ファイル配置 → AI 反映が数十秒〜数分（B の最大15分より短い）│
└──────────────────────────────────────────────────────────────────────────┘
```

> FPolicy → SQS → Bridge Lambda → EventBridge の前段は [event-driven-fpolicy](../../event-driven-fpolicy/)
> パターンの基盤を再利用する。本 UC のシナリオ C は、その EventBridge バス上に
> **ai_knowledge ボリュームパス一致のルール**と **KB Trigger Lambda** を追加する（`EnableScenarioC=true`）。

### 名前空間の分離（重要）

| 名前空間 | 例 | 用途 |
|---------|-----|------|
| FPolicy ファイルパス（ONTAP ボリュームパス） | `ai_knowledge/sales/...` | EventBridge ルール一次フィルタ + KB Trigger Lambda 二次フィルタ |
| S3 取り込みプレフィックス（S3 AP） | `ai-knowledge/`（または S3 AP 構成依存） | Bedrock KB データソースの inclusionPrefixes |

> FPolicy のパスと S3 AP のプレフィックスは**別名前空間**。シナリオ C のルーティングは
> FPolicy パス（`FPolicyVolumePathPrefix`、既定 `ai_knowledge`）で判定する。

## シナリオ比較

| 観点 | A: 手動 | B: 定期自動化 | C: FPolicy リアルタイム |
|------|--------|--------------|------------------------|
| 検知方式 | 人手 | Scheduler ポーリング（15分） | FPolicy イベント |
| 反映レイテンシ | 人次第 | 最大 15 分 | 数十秒〜数分 |
| 追加インフラ | なし（KB + S3 AP のみ） | Scheduler + Step Functions + Lambda | FPolicy Server (Fargate ~$35/月) + Persistent Store |
| 適するケース | 体験・小規模 | 標準運用 | 即時反映が必要・大規模 |

## データフロー

```
[投入] 業務ユーザー → Windows ドラッグ&ドロップ → FSx for ONTAP AI 専用ボリューム
                                                          ↓ (読み取りパス)
[同期A] 人が手動で StartIngestionJob → KB 更新
[同期B] EventBridge Scheduler → Auto-Sync Lambda → S3 AP 差分検知 → StartIngestionJob → KB 更新
[同期C] FPolicy 検知 → SQS → Bridge → EventBridge → KB Trigger Lambda → StartIngestionJob → KB 更新
[利用] 利用者 → Query Lambda → RetrieveAndGenerate → KB + FM → 回答
```

## 差分検知ロジック

1. Auto-Sync Lambda が直近の Ingestion ジョブ開始時刻を `ListIngestionJobs` で取得
2. S3 AP の `ListObjectsV2` で対象プレフィックスを走査し、`LastModified` がジョブ開始
   時刻より新しいオブジェクト数を数える
3. 変更が 1 件以上あれば `StartIngestionJob` を起動（`force=true` で常時起動）
4. 結果を SNS に通知

> 削除されたファイルの反映は Bedrock KB の Ingestion ジョブが S3 AP の現状と差分を取り、
> ベクトルストアから除去する（マネージド側の挙動）。

## 責任分界（民主化）

| 担当 | 責務 |
|------|------|
| 業務ユーザー（各ロール・部署） | 自部署フォルダーへのファイル追加・更新・削除（Windows 操作のみ） |
| IT 部門 | フォルダー構成・NTFS ACL・自動同期スタックの維持 |
| プラットフォーム | KB / データソースの作成、ベクトルストア構成 |

## セキュリティ考慮事項

- データは FSx for ONTAP 上の正本のまま（S3 へのコピーなし）
- AI 取り込みパス（S3 AP）は読み取り利用。書き込みは SMB/NFS 経由
- フォルダー単位の NTFS ACL で部署ごとに書き込み権限を分離
- S3 AP のデータソース境界はボリューム/プレフィックス単位（利用者個人ごとの可視範囲制御は対象外）
- Lambda は対象 S3 AP の List/Get と当該 KB の Ingestion / Retrieve のみ許可（最小権限）
