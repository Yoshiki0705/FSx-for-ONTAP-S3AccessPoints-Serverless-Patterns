# UC29: Self-Service Knowledge Base Curation — アーキテクチャ

## 概要

FSx for ONTAP 上の **AI 専用ボリューム** を SMB（Windows 共有）で各ロール・部署に公開し、
業務ユーザーがドラッグ&ドロップでナレッジを維持する。同じデータを **S3 Access Point
経由（読み取りパス）** でマネージドな Amazon Bedrock Knowledge Base に接続し、ファイル
投入を検知して自動で取り込む。

本パターンは **マネージド RAG（Pattern C）** を採用し、運用負荷を最小化する。
検索時のファイルレベル権限制御が必要な場合は UC である [FC3 genai-rag-enterprise-files](../../genai-rag-enterprise-files/)（カスタム RAG, Pattern A）を選択する。

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
| Amazon Bedrock Knowledge Base | マネージド RAG（データソース = S3 AP） |
| Query Lambda | RetrieveAndGenerate による Q&A（デモ用） |
| SNS | 同期結果の通知（投入件数・失敗） |

## 2 つの運用シナリオ

本 UC は同じ基盤上で 2 段階の運用を提供する。

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

## データフロー

```
[投入] 業務ユーザー → Windows ドラッグ&ドロップ → FSx ONTAP AI 専用ボリューム
                                                          ↓ (読み取りパス)
[同期] EventBridge → Auto-Sync Lambda → S3 AP 差分検知 → StartIngestionJob → KB 更新
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

- データは FSx ONTAP 上の正本のまま（S3 へのコピーなし）
- AI 取り込みパス（S3 AP）は読み取り利用。書き込みは SMB/NFS 経由
- フォルダー単位の NTFS ACL で部署ごとに書き込み権限を分離
- S3 AP のデータソース境界はボリューム/プレフィックス単位（利用者個人ごとの可視範囲制御は対象外）
- Lambda は対象 S3 AP の List/Get と当該 KB の Ingestion / Retrieve のみ許可（最小権限）
