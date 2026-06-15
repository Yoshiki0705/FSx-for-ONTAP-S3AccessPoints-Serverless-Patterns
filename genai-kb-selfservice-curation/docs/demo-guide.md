# UC29: Self-Service Knowledge Base Curation — デモガイド

## Executive Summary

業務部門のメンバーが **使い慣れた Windows のファイル/フォルダー操作（ドラッグ&ドロップ）** だけで
Amazon Bedrock Knowledge Base のデータを維持できることを実演する。IT 部門の手作業（コピー・S3
アップロード・手動取り込み）を排除した **民主化された AI ナレッジ運用** を示す。

本デモは **3 つのシナリオ** で構成する。

| シナリオ | 目的 | 取り込みトリガー |
|---------|------|----------------|
| **シナリオ A: 手動メンテナンス体験** | Windows 操作で AI データを維持する体験 | 人が手動で同期（コンソール/CLI） |
| **シナリオ B: 定期自動化** | A の手動作業を Lambda + Step Functions で自動化 | EventBridge Scheduler（15分間隔） |
| **シナリオ C: FPolicy リアルタイム** | ファイル配置の瞬間に即時同期（人の操作ゼロ） | FPolicy イベント検知 → 即時 Ingestion |

**デモの核心メッセージ**: 「AI に使わせたいデータは、この Windows フォルダーに置いて、自分で
メンテナンスしてください」── 手動体験(A) → 定期自動化(B) → リアルタイム同期(C) の3段階で進化を示す。

**想定時間**: 15〜18 分（A: 5〜6 分 + B: 5〜6 分 + C: 5〜6 分）

---

## Target Audience

| 項目 | 詳細 |
|------|------|
| **役職** | IT 部門長 / 情報システム担当 / 業務部門のナレッジ管理者 / DX 推進担当 |
| **課題** | ナレッジ更新が IT 部門の手作業待ち、データの二重管理、属人化 |
| **期待する成果** | まず現場が自分で維持できることを体験し、運用が固まったら自動化する |

---

## Before / After ストーリー（マスク済み）

> **注記**: 特定顧客名・担当者名・チーム名をマスクした、一般化した運用ストーリーです。

### Before — IT 部門の手作業依存

業務部門からの典型的な依頼:

> 「新製品が出たので、この Windows チームフォルダーの資料を AI ナレッジに入れてください。
>  営業がデモで対話的に使いたいので」

これに対し IT 部門が毎回: EC2 上の Windows Server から手動でコピー → S3 アップロード →
Bedrock KB へ手動取り込み → 完了連絡。依頼ごとのボトルネック・データ二重管理・属人化。

### After — 現場主導のセルフサービス

> 「AI に使わせたいデータは、この Windows フォルダーに置いて、自分でメンテナンスして
>  ください。AI はこのデータを参照します」

業務部門は普段どおり Windows エクスプローラーで AI 専用フォルダーへドラッグ&ドロップするだけ。

---

## 事前準備（両シナリオ共通）

| 項目 | 内容 |
|------|------|
| AI 専用ボリューム | FSx for ONTAP 上に作成し、SMB で公開（例: `\\fsxn-share\ai-knowledge\`） |
| フォルダー構成 | `sales/` `marketing/` `finance/` `information-technology/` `operations/` `legal/` `developers/` を作成し、部署ごとに NTFS ACL 設定 |
| シードデータ | [`sample-data/ai-knowledge/`](../sample-data/) を AI 専用ボリュームへコピー（7ロール分のサンプル同梱） |
| S3 Access Point | AI 専用ボリュームに対し作成（読み取りパス） |
| Bedrock Knowledge Base | `scripts/create_bedrock_kb.py` または コンソールで作成（データソース = S3 AP） |
| デモ用ファイル | 投入用の新製品資料（PDF/DOCX 等）を手元に用意 |

> **ロール構成は Amazon Quick に準拠**: Quick FAQ が対象とする sales / marketing / IT / operations / finance / legal に、専用ページのある developers を加えた7ロール。後続の Amazon Quick UC とフォルダー/テストデータを共有できる。

> **検証方法の前提（重要・正確性のため明記）**
> これまでの自動検証では、業務ユーザーの「Windows エクスプローラーのドラッグ&ドロップ」を
> **S3 Access Point の API（PutObject/DeleteObject）で代替（プロキシ）** して実施し、Bedrock KB の
> 追加・更新・削除同期が正しく動作することを確認した。**Windows EC2 への RDP/SSH や AD は使用していない。**
>
> **リテラル（文字どおりの Windows 体験）に必要なリソース**:
> 1. Active Directory（自己管理 or AWS Managed Microsoft AD）
> 2. AD 参加 + SMB 共有を持つ FSxN ボリューム（NTFS / multiprotocol セキュリティスタイル）
> 3. AD 参加の Windows クライアント（ドライブマップしてドラッグ&ドロップ）
> 4. 同一ボリュームの S3 Access Point（**Windows FileSystemIdentity**）→ Bedrock KB データソース
>
> リテラル構成の構築手順・進捗は [smb-windows-setup.md](smb-windows-setup.md) を参照。

---

## シナリオ A: 手動メンテナンス体験（Windows ファイル操作）

**ねらい**: 業務ユーザーが「使い慣れたファイル操作」だけで AI のデータを足す・直す・消すを体験する。
取り込みは人が手動でトリガーし、**Windows 操作と AI 反映の因果関係を体感**してもらう。

### ワークフロー

```
1. Windows エクスプローラーで操作（追加/更新/削除）
2. 手動で取り込みをトリガー（Bedrock コンソール「同期」/ CLI）
3. 取り込み完了を確認
4. 質問して、操作が回答に反映されたことを確認
```

### A-1. ファイル追加（新製品資料）

業務ユーザー役で、新製品資料を AI 専用フォルダーへドラッグ&ドロップ:

```
\\fsxn-share\ai-knowledge\sales\product-catalog\product-x-spec.pdf
```

→ IT 部門への依頼は不要。普段のファイルコピーと同じ操作。

> 📸 Windows エクスプローラーで SMB 共有を開いた様子（7 ロールフォルダー）:
> [`docs/screenshots/masked/windows-smb-share-roles.png`](screenshots/masked/windows-smb-share-roles.png)
>
> 📸 `sales/product-catalog/` に配置された実ファイル（KB 引用元）:
> [`docs/screenshots/masked/windows-smb-product-catalog.png`](screenshots/masked/windows-smb-product-catalog.png)
>
> これらは実機実証済み（AD 参加 SVM + Windows EC2 + Windows identity S3 AP）。詳細は [verification-results.md](verification-results.md)。

### A-2. 手動で取り込みをトリガー

Bedrock コンソールの Knowledge Base データソースで「**同期 (Sync)**」を押す。または CLI:

> 📸 [`docs/screenshots/masked/bedrock-kb-datasource-sync.png`](screenshots/masked/bedrock-kb-datasource-sync.png) — Bedrock KB データソース画面（Sync ボタン）

```bash
aws bedrock-agent start-ingestion-job \
  --knowledge-base-id <KB_ID> \
  --data-source-id <DS_ID>
```

> これが「これまで IT 部門が手作業でやっていた取り込み」に相当する。シナリオ B でこの手順を自動化する。

### A-3. 取り込み完了の確認

```bash
aws bedrock-agent get-ingestion-job \
  --knowledge-base-id <KB_ID> \
  --data-source-id <DS_ID> \
  --ingestion-job-id <JOB_ID> \
  --query 'ingestionJob.{status:status,stats:statistics}'
```

`status: COMPLETE`、`numberOfNewDocumentsIndexed` が増えたことを確認。

### A-4. 質問して反映を確認

```bash
aws lambda invoke --function-name <QueryFunctionName> \
  --payload '{"query": "新製品Xの主な仕様を教えて"}' \
  --cli-binary-format raw-in-base64-out out.json && cat out.json
```

→ 直前に置いた `product-x-spec.pdf` を引用して回答する（citations 表示）。

### A-5. 更新・削除も体験（ライフサイクル全体）

- **更新**: 同名ファイルを上書き保存 → 再同期 → 回答内容が新しい版に変わる
- **削除**: ファイルを Windows でゴミ箱へ → 再同期 → そのファイル由来の回答が出なくなる

> **実機検証済み（削除伝播）**: S3 AP 経由で削除 → 同期で `numberOfDocumentsDeleted=1` → 再クエリで「情報が見つかりません」。
> データソースは `dataDeletionPolicy=DELETE`。反映は次回同期まで遅延するため、緊急失効が必要なら直接 Ingestion（`DeleteKnowledgeBaseDocuments`）を併用。詳細は [verification-results.md](verification-results.md)。

### Storyboard（A）

| 時間 | セクション | 内容 |
|------|-----------|------|
| 0:00–1:00 | Problem | Before の IT 手作業フローと課題 |
| 1:00–2:30 | Drag & Drop | エクスプローラーで新製品資料を投入 |
| 2:30–4:00 | Manual Sync | コンソール/CLI で手動同期 → 完了確認 |
| 4:00–5:30 | Query | 質問 → 投入資料を引用して回答 |
| 5:30–6:00 | Lifecycle | 更新・削除も同じ操作で反映されることを提示 |

---

## シナリオ B: 自動化（Lambda + Step Functions）

**ねらい**: シナリオ A の「手動同期」を排除する。ファイルを置くだけで、検知・取り込み・完了確認・
通知までをサーバーレスで自動実行する。

### 自動化アーキテクチャ

```
EventBridge Scheduler（定期トリガー）
        ↓
Step Functions ワークフロー
  1. DetectAndStartIngestion (Auto-Sync Lambda)  … S3 AP 差分検知 → StartIngestionJob
  2. Choice: 変更あり？ → なければ Succeed
  3. Wait 30s
  4. CheckIngestionStatus (Ingestion Status Lambda) … GetIngestionJob でポーリング
  5. Choice: COMPLETE / FAILED / まだなら 3 へループ
  6. SNS 通知（成功/失敗）
```

> シナリオ A の A-2〜A-3（手動同期・完了確認）が、そのまま Step Functions の
> 「DetectAndStartIngestion → CheckIngestionStatus」に対応する。**人の手作業をステートマシンに置き換える**。

### B-1. ファイル追加（A と同じ操作）

業務ユーザーは A-1 と同じくドラッグ&ドロップするだけ。以降の取り込み操作は不要。

### B-2. 自動実行を確認

EventBridge Scheduler の次回実行を待つ（例: `rate(15 minutes)`）か、デモ用に手動起動:

```bash
aws stepfunctions start-execution \
  --state-machine-arn <KbSyncWorkflowArn> \
  --input '{}'
```

### B-3. ワークフローの可視化

Step Functions コンソールで実行を開き、各ステートの遷移を確認:

> 📸 [`docs/screenshots/masked/step-functions-execution-succeeded.png`](screenshots/masked/step-functions-execution-succeeded.png) — Step Functions 実行画面（全ステート Succeeded）

- `DetectAndStartIngestion` → `WaitForIngestion` → `CheckIngestionStatus` → `NotifySuccess`
- 変更がない実行は `NoChange (Succeed)` で即終了（無駄な取り込みを避ける）

### B-4. 通知と確認

SNS 通知（投入件数・成功/失敗）を受信。A-4 と同じ質問で、手動操作なしに回答が更新されていることを確認。

### Storyboard（B）

| 時間 | セクション | 内容 |
|------|-----------|------|
| 0:00–1:00 | Recap | A の手動同期手順を振り返る |
| 1:00–2:00 | Architecture | EventBridge + Step Functions + Lambda の自動化構成 |
| 2:00–3:30 | Drop & Wait | ファイル投入 → 自動実行（または手動起動） |
| 3:30–5:00 | Visualize | Step Functions の実行グラフ・分岐・完了待ちを確認 |
| 5:00–6:00 | Query | 手動操作ゼロで回答が更新されたことを確認 |

---

## シナリオ C: FPolicy イベント駆動（リアルタイム同期）

**ねらい**: シナリオ B の「定期ポーリング（15分間隔）」を排除する。ファイルが SMB 共有に置かれた**瞬間**に
FPolicy がイベントを検知し、KB 同期をリアルタイムでトリガーする。人の操作もスケジュール待ちもゼロ。

### イベント駆動アーキテクチャ

```
業務ユーザー → Windows ドラッグ&ドロップ → FSx ONTAP AI 専用ボリューム (S3 AP 付き)
    ↓ (即時検知)
FPolicy Server (ECS Fargate / EC2)
    ↓ FPolicy 通知 (protobuf/xml)
SQS Ingestion Queue
    ↓
Bridge Lambda → EventBridge Custom Bus
    ↓ ルーティングルール: file_path prefix = "ai_knowledge"
KB Trigger Lambda → StartIngestionJob
    ↓
Bedrock Knowledge Base → Ingestion COMPLETE
    ↓
SNS 通知 + Query で即時反映
```

> シナリオ B との違い: B は EventBridge Scheduler が 15 分間隔で差分検知 → 同期。
> C は FPolicy がファイル操作を検知した時点で即座に同期を開始する。
> **レイテンシ: ファイル配置 → AI 反映が数十秒〜数分**（Ingestion 処理時間依存）。

### C-1. ファイル配置（A/B と同じ操作）

業務ユーザーは A-1 / B-1 と同じくドラッグ&ドロップするだけ。以降は全て自動。

### C-2. FPolicy によるリアルタイム検知

FPolicy が `CREATE` / `WRITE` / `DELETE` / `RENAME` 操作を検知し、SQS → EventBridge へイベントを配信:

```json
{
  "source": "fsxn.fpolicy",
  "detail-type": "FPolicy File Operation",
  "detail": {
    "event_id": "11111111-1111-4111-8111-111111111111",
    "operation_type": "create",
    "file_path": "ai_knowledge/sales/product-catalog/product-x-spec.pdf",
    "volume_name": "ai_knowledge",
    "svm_name": "uc29demosvm",
    "timestamp": "2026-06-15T23:00:00Z",
    "file_size": 2048
  }
}
```

> イベント本体は [`event-driven-fpolicy/schemas/fpolicy-event-schema.json`](../../event-driven-fpolicy/schemas/fpolicy-event-schema.json) に準拠
> （`operation_type` / `file_path` / `detail-type="FPolicy File Operation"`）。

### C-3. EventBridge ルールによる KB 同期トリガー

EventBridge ルールが `ai_knowledge`（FPolicy ボリュームパス）に一致するイベントのみをフィルタし、
KB Trigger Lambda を起動:

```json
{
  "source": ["fsxn.fpolicy"],
  "detail-type": ["FPolicy File Operation"],
  "detail": {
    "file_path": [{"prefix": "ai_knowledge"}]
  }
}
```

KB Trigger Lambda は `StartIngestionJob` を呼び出す。デバウンス: 進行中の Ingestion ジョブが
あればスキップ（`ConflictException` も同様）。予期せぬ例外は再送出され、Lambda の
`EventInvokeConfig.OnFailure`（**実行失敗**用 SQS DLQ `...-kbtrigger-dlq`）で捕捉する。
EventBridge ターゲットの `DeadLetterConfig` は EventBridge→Lambda の**配信失敗**専用。
両者で配信失敗・実行失敗の双方をカバーする。

> 📸 EventBridge ルール詳細（FPolicy イベントパターン、実機実証済み）:
> [`docs/screenshots/masked/scenario-c-eventbridge-rule.png`](screenshots/masked/scenario-c-eventbridge-rule.png)
>
> 合成 FPolicy イベント注入で `EventBridge ルール → KB Trigger Lambda → StartIngestionJob` を実証。
> 詳細は [verification-results.md](verification-results.md)。

### C-4. リアルタイム反映の確認

FPolicy 検知から数十秒〜数分で KB に反映。手動での同期操作もスケジュール待ちも不要:

```bash
# ファイル配置後、即座に質問可能（Ingestion 完了後）
aws lambda invoke --function-name <QueryFunctionName> \
  --payload '{"query": "新製品Xの主な仕様を教えて"}' \
  --cli-binary-format raw-in-base64-out out.json && cat out.json
```

### C-5. 削除のリアルタイム伝播

ファイルを Windows で削除 → FPolicy が `DELETE` を検知 → KB Ingestion がベクトルを除去:

- `dataDeletionPolicy = DELETE` により、ソースファイルが消えたチャンクは同期時に除去
- シナリオ B（15分間隔）より大幅に短い失効レイテンシ

### Storyboard（C）

| 時間 | セクション | 内容 |
|------|-----------|------|
| 0:00–1:00 | Recap | B のスケジュール駆動の制約（15分遅延）を振り返る |
| 1:00–2:30 | Architecture | FPolicy → SQS → EventBridge → KB Trigger の構成 |
| 2:30–4:00 | Real-time Demo | ファイル投入 → 数十秒後に Query で反映を確認 |
| 4:00–5:00 | Delete Demo | ファイル削除 → 再 Query で除去を確認 |
| 5:00–6:00 | Comparison | B（15分遅延） vs C（リアルタイム）のトレードオフ |

### シナリオ C の前提条件

| 項目 | 内容 |
|------|------|
| FPolicy サーバー | ECS Fargate or EC2（`event-driven-fpolicy/` テンプレートでデプロイ） |
| FPolicy ポリシー | ai_knowledge ボリュームの CREATE/WRITE/DELETE/RENAME を監視 |
| Persistent Store | FPolicy サーバーダウンタイム中のイベントを保全（ONTAP 機能） |
| EventBridge ルール | `ai_knowledge`（FPolicy パス）プレフィックスフィルタ + KB Trigger Lambda ターゲット + DLQ |
| デバウンス | 進行中ジョブ検知でスキップ（バースト時の連続起動を抑制） |
| **シナリオ B 併用（必須）** | 下記「取りこぼし対策」参照 |

> ⚠️ **取りこぼし対策（必須）**: Bedrock Ingestion はジョブ開始時点のソース全走査のため、
> **ジョブ実行中に追加されたファイルのイベントはスキップされ、その実行に含まれない**（lost-update window）。
> シナリオ C は単独で「取りこぼしゼロ」を保証しない。**必ずシナリオ B（EventBridge Scheduler の
> 定期リコンサイル同期）と併用**し、B を安全網として後追い取り込みを担保すること。
> C 単独運用は許容されない。

> **バースト**: 大量ファイルを同時投入すると FPolicy イベントが多数発火し、KB Trigger Lambda が
> 並列起動する。デバウンス（進行中スキップ）と ConflictException 処理で二重起動は防ぐが、
> 個々の起動は List/PutMetric を呼ぶため、大規模バーストでは Bedrock/CloudWatch のスロットリングに留意。

> **シナリオ B vs C のトレードオフ**: B はインフラが軽い（Scheduler + Lambda のみ）が 15 分の遅延。
> C はリアルタイムだが FPolicy サーバー（Fargate ~$35/月）と Persistent Store が必要。
> 運用要件に応じて選択する。

---

## A → B → C の対応関係（まとめ）

| シナリオ A（手動） | シナリオ B（定期自動化） | シナリオ C（リアルタイム） |
|-------------------|------------------------|--------------------------|
| ① エクスプローラーで投入 | ① エクスプローラーで投入（同じ） | ① エクスプローラーで投入（同じ） |
| ② コンソール/CLI で手動同期 | ② Scheduler が 15 分間隔で差分検知・自動同期 | ② FPolicy が即時検知・自動同期 |
| ③ get-ingestion-job で完了確認 | ③ Step Functions がポーリング完了判定 | ③ KB Trigger → Ingestion → 完了 |
| ④ 人が結果を確認 | ④ SNS が結果を自動通知 | ④ SNS + 即座に Query 可能 |
| 反映レイテンシ: 人次第 | 反映レイテンシ: 最大 15 分 | 反映レイテンシ: 数十秒〜数分 |

→ 業務ユーザーの操作（①）は全シナリオで不変。**変わるのは検知→同期の仕組みだけ**。

---

## ロール別デモ質問例（7ロール）

各ロールのフォルダーに投入したサンプルデータに対する質問例。`sample-data/ai-knowledge/<role>/` 参照。

| ロール | 質問例 | 期待する引用元 |
|--------|--------|---------------|
| sales | 製品Xの主な仕様と価格帯は？ | `sales/product-catalog/product-x-spec.md` |
| marketing | 製品X ローンチキャンペーンのKPIは？ | `marketing/campaigns/2026-q1-product-x-launch.md` |
| finance | 2026年度のAI/ML予算は前年比どれくらい増えた？ | `finance/budgets/2026-it-budget-summary.csv` |
| information-technology | Sev1インシデントの初動目標時間は？ | `information-technology/runbooks/incident-response-runbook.md` |
| operations | 受注処理の標準納期は？ | `operations/sop/order-fulfillment-sop.md` |
| legal | NDAの秘密保持義務は契約終了後どれくらい存続する？ | `legal/contracts/nda-template.md` |
| developers | Python で禁止されている日時関数は？ | `developers/standards/coding-standards.md` |

```bash
# 例: 営業ロールの質問
aws lambda invoke --function-name <QueryFunctionName> \
  --payload '{"query": "製品Xの主な仕様と価格帯を教えて"}' \
  --cli-binary-format raw-in-base64-out out.json && cat out.json
```

> **権限デモの補足**: 各ロールフォルダーの NTFS ACL を分けておくと、「営業は営業フォルダーを更新できるが
> 法務フォルダーは更新できない」といった**責任分界**を Windows 操作レベルで示せる。なお S3 AP のデータソース
> 境界はボリューム/プレフィックス単位であり、検索時の利用者個人ごとの可視範囲制御が必要な場合は
> カスタム RAG（FC3）を用いる。

---

## Technical Notes

| コンポーネント | 役割 | 使用シナリオ |
|--------------|------|-------------|
| FSx ONTAP AI 専用ボリューム | SMB 共有、業務ユーザーが直接維持 | A / B / C |
| S3 Access Point | AI 取り込み読み取りパス | A / B / C |
| Bedrock Knowledge Base | マネージド RAG | A / B / C |
| Query Lambda | RetrieveAndGenerate | A / B / C |
| Auto-Sync Lambda | 差分検知 + StartIngestionJob | B（A では手動の代替） |
| Ingestion Status Lambda | GetIngestionJob ポーリング | B |
| Step Functions | 検知→取り込み→完了待ち→通知のオーケストレーション | B |
| EventBridge Scheduler | 定期自動実行（15分間隔） | B |
| FPolicy Server (ECS/EC2) | NFS/SMB ファイル操作のリアルタイム検知 | C |
| FPolicy Persistent Store | サーバーダウンタイム中のイベント保全 | C |
| SQS + Bridge Lambda | FPolicy イベントの EventBridge 配信 | C |
| EventBridge Rule (ai-knowledge/) | KB Trigger Lambda へのルーティング | C |
| KB Trigger Lambda | StartIngestionJob（デバウンス付き） | C |
| SNS | 結果通知 | B / C |

---

## 出力サンプル

### シナリオ A: 手動取り込み完了（get-ingestion-job）
```json
{
  "status": "COMPLETE",
  "stats": {
    "numberOfDocumentsScanned": 12,
    "numberOfNewDocumentsIndexed": 1
  }
}
```

### シナリオ B: Step Functions 完了通知（SNS）
```json
{
  "status": "completed",
  "ingestion_status": "COMPLETE",
  "knowledge_base_id": "XXXXXXXXXX",
  "data_source_id": "YYYYYYYYYY",
  "ingestion_job_id": "ZZZZZZZZZZ",
  "documents_indexed": 1
}
```

### Query（両シナリオ共通）
```json
{
  "status": "completed",
  "query": "新製品Xの主な仕様を教えて",
  "answer": "新製品Xの主な仕様は...（投入済みドキュメントに基づく）",
  "citations": [
    {"source": "s3://.../sales/product-catalog/product-x-spec.pdf"}
  ]
}
```

> **注記**: 上記はサンプル出力であり、実際の値は環境・入力データにより異なります。
> 数値・料金は sizing reference / time-sensitive であり、service limit ではありません。

---

## Governance Note

> 本パターンは技術アーキテクチャガイダンスを提供します。法的・コンプライアンス・規制上の
> 助言ではありません。S3 AP のデータソース境界はボリューム/プレフィックス単位であり、
> 利用者個人ごとの可視範囲制御が必要な場合は本UCの適用範囲外です（カスタム RAG を検討）。
