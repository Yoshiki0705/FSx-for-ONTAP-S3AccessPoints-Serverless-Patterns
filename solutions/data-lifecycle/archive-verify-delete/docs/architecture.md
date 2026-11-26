# archive-verify-delete アーキテクチャ
🌐 **Language / 言語**: 日本語 | [English](architecture.en.md)
## 概要
Amazon FSx for NetApp ONTAP（以下 FSx for ONTAP）の S3 Access Points と S3 API を使って、ファイルを S3 Glacier 系のクラスへ写し、照合し、承認の後に元を消します。ファイルの読み書きと削除に NFS のマウントは使いません。ただし、最終アクセス時刻で選ぶ `selection=ATIME` と属性の取得は ONTAP REST API（VPC 内の Lambda）を使い、戻した後の所有者・モード・更新時刻の付け直しは NFS でボリュームをマウントしたホストが要ります。使い方は [README](../README.md) にあります。この文書は構成、権限、失敗時の挙動を示します。
## 構成
| 構成要素 | 役割 | 置き場所 |
|---|---|---|
| `archive` ステートマシン | 選ぶ、記録する、写す、照合する、承認を待つ、承認を記録する、消す、まとめる | Step Functions（Standard、Distributed Map） |
| `restore` ステートマシン | 台帳から選び、復元を要求し、待ち、Access Point へ戻し、戻したファイルを照合する | 同上 |
| `select` | 入力の検査（`runId` の再利用の拒否）、`MTIME` での選択、`ATIME` の候補の確認、除外の適用 | Lambda（VPC 外） |
| `ontap_rest` | `accessed_time` による候補の列挙と、属性の取得 | Lambda（VPC 内。任意） |
| `record` | Access Point から読んでハッシュを計算し、台帳に書く | Lambda（VPC 外） |
| `ledger` | バケットの `HeadObject` を台帳と比べ、`VERIFIED` か `MISMATCH` にする。失敗を記録する | Lambda |
| `approval` | 承認用のマニフェストを書き、タスクトークンを保管し、通知する。承認の後に承認者と起動者の分離を確かめ、台帳を `APPROVED` にする | Lambda |
| `delete` | `APPROVED` の項目だけ、ETag と大きさを確かめ、同じなら Access Point のファイルを消す。`reconcile` で中断した項目を整理する | Lambda |
| `summarize` | 結果の JSON、EMF のメトリクス、通知、トークンの削除 | Lambda |
| `restore` | 戻しの補助（選ぶ、存在確認、復元状態の判定、確定、戻した後の照合、再付与スクリプト） | Lambda |
| `watchdog` | 承認の依頼が答えを待っている時間（`ApprovalPendingHours`）を 15 分ごとに出す | Lambda（EventBridge のスケジュール） |
| Fargate のタスク（アーカイブ用と戻し用） | 5 GiB を超えるファイルのハッシュとマルチパートコピー。戻しと戻した後の照合 | ECS Fargate（ARM64。任意。タスクロールは 2 つ） |
| 台帳 | `(runId, key)` ごとの状態、チェックサム、属性 | DynamoDB（PAY_PER_REQUEST、PITR、削除保護。削除保護は UpdateTable で外せる） |
| アーカイブ用バケット | 写したオブジェクト（`<prefix><runId>/<元のキー>`）とマニフェスト（`manifests/`） | S3（新規作成。Object Lock なし） |
| アラームと通知 | 実行の失敗、承認待ちの長さ、削除の滞留、不一致 | CloudWatch アラーム、SNS（カスタマー管理キーで暗号化） |
VPC 内の Lambda は ONTAP の管理エンドポイントにだけ届き、Internet-origin の Access Point へは届かないため、機能を `ontap_rest`（VPC 内）と、それ以外（VPC 外）に分けています。
## 処理の流れ
```
archive: Plan → [resume: ResumeReconcile → ResumeDefaults → PrepareManifest へ]
  → [MTIME: SelectMtime | ATIME: AtimeCandidates → SelectFromCandidates]
  → ProcessFiles (Distributed Map、ファイルごと):
       属性 → Record → (≤5 GiB: copyObject | >5 GiB: Fargate) → HeadArchived → CompareArchive
       → (任意) 2 つ目の写し → HeadSecond → CompareSecond
  → PrepareManifest → RequestApproval (waitForTaskToken) → ApprovalCheck → DryRunChoice
  → RecordApproval (起動者と承認者の分離、台帳を APPROVED に) → ApprovalRecordedChoice
  → DeleteFiles (Distributed Map、ファイルごとに delete) → Summarize
restore: Select → RestoreFiles (Distributed Map): Prepare → (復元要求 → 待つ) → copy
  → Finalize (RESTORED) → 照合 (Lambda、5 GiB 超は Fargate) → RESTORE_VERIFIED / RESTORE_MISMATCH → ReapplyManifest
```
削除の状態に着くには `RequestApproval`、`ApprovalCheck`、`DryRunChoice`、`RecordApproval` のすべてを通る必要があります。この性質はテスト（`test_definitions.py`）で、状態の遷移図から各状態を取り除いて到達できなくなることを確かめています。さらに `delete` 関数自身が、台帳の状態が `APPROVED` でない項目を消しません。関数を直接呼び出しても、承認の記録のない項目は消えません（`test_approval_gate.py`）。
## 照合の方式
| ファイルの大きさ | 写し方 | チェックサム | 理由 |
|---|---|---|---|
| 5 GiB 以下 | `CopyObject` | `SHA256`（`FULL_OBJECT`） | バケットの値がファイルの SHA-256 と一致する（部品の確認） |
| 5 GiB 超 | マルチパートの `UploadPartCopy` | `CRC64NVME`（`FULL_OBJECT`） | マルチパートの SHA-256 は `COMPOSITE` で、ファイル全体の値と一致しない |
`COMPOSITE` を返された場合、チェックサムが無い場合は、一致とみなさず `MISMATCH` にします。戻した後は、Access Point から読み直したファイルの SHA-256、CRC64NVME、大きさを台帳の値と比べ、`RESTORE_VERIFIED` か `RESTORE_MISMATCH` にします。`RESTORED` は「コピーの呼び出しが成功した」だけを意味します。
## 台帳
| 属性 | 内容 |
|---|---|
| `runId`（PK）、`key`（SK） | 実行とファイルのキー |
| `status` | `SELECTED`、`RECORDED`、`COPIED`、`VERIFIED`、`APPROVED`、`DELETING`、`DELETED`、`RESTORED`、`RESTORE_VERIFIED`、`RESTORE_MISMATCH`、`CHANGED`、`MISMATCH`、`FAILED`、`SKIPPED_TOO_LARGE` |
| `size`、`etag`、`lastModified` | 一覧の時点の値。削除の直前に再確認する |
| `sha256`、`sha256B64`、`crc64nvme` | 5 GiB 以下は Lambda、超える分は Fargate が書く |
| `archiveBucket`、`archiveKey`、`storageClass` | 写し先（`archiveKey` は `<prefix><runId>/<元のキー>`） |
| `attrs` | `uid`、`gid`、`mode`、`mtime`、`atime`（取れる場合） |
| `secondCopyRequired`、`secondCopy` | 2 つ目の写しの要否と照合結果 |
| `approvedBy`、`approvedAt`、`approvalExecutionArn`、`requestedBy` | 承認の記録。承認の後の `approval` 関数だけが書く |
| `claimedBy` | 削除を保持している実行の ARN。削除の再試行が「自分の続き」かを判定する |
| `deletedBy`、`deletedAt`、`restoredAt`、`restoreRunId` | 削除と戻しの記録。`deletedBy` は台帳の `approvedBy` から取る |
`APPROVED` への遷移は、承認の後の `approval` 関数が `VERIFIED` の項目にだけ行う条件付きの書き込みです。`DELETING` へは、`APPROVED` から、または自分の `claimedBy` が付いた `DELETING` からだけ移れます。このため、同じファイルを 2 つの実行が同時に消すことはなく、承認の記録のない項目は消えません。削除の呼び出しが例外で終わったときは、ファイルが消えたかどうかが分からないので、`DELETING` と `claimedBy` を残します。Step Functions の再試行は、Access Point の状態から決めます。ファイルが無ければ `DELETED` にし（`already gone on retry`）、あれば消します。
## IAM
| 主体 | 主な権限 | 持たない権限 |
|---|---|---|
| `delete` | Access Point の `s3:GetObject`、`s3:DeleteObject`、台帳の `GetItem`、`UpdateItem`、`Query`、実行の状態の読み取り（`reconcile`） | 他のバケットへの書き込み |
| `approval` | 台帳の `Query`、`UpdateItem`、`manifests/*` の読み書き、`/<stack>/approvals/*` への `PutParameter`、`sns:Publish` | 削除 |
| `record` | Access Point の `s3:GetObject`、台帳の `PutItem` | 削除、Access Point への書き込み、台帳の更新 |
| `select` | Access Point の `ListBucket`、`GetObject`、`manifests/*` の読み書き、台帳の `Query`、`PutItem` | 削除、Access Point への書き込み |
| アーカイブ用 Fargate のタスクロール | Access Point の `GetObject`、`ListBucket`、アーカイブ用バケットの読み書き、台帳の `UpdateItem` | 削除、Access Point への書き込み |
| 戻し用 Fargate のタスクロール | Access Point の `GetObject`、`PutObject`、アーカイブ用バケットの読み取り、台帳の `GetItem`、`UpdateItem` | 削除 |
| `archive` ステートマシンのロール | Lambda の呼び出し、`CopyObject` に必要な S3 の読み書き、ECS の起動（アーカイブ用タスクだけ） | `s3:DeleteObject`、Access Point への書き込み |
| `restore` ステートマシンのロール | Lambda の呼び出し、Access Point への `PutObject`（`CopyObject`）、ECS の起動（戻し用タスクだけ） | `s3:DeleteObject` |
Access Point への権限は、IAM のロール側と Access Point のポリシー側の両方で許可します。ロール側は、エイリアス形式（`arn:aws:s3:::<alias>/*`）と Access Point ARN 形式（`accesspoint/<name>/object/*`）の両方を書いています。片方だけだとデプロイできても、実行時に拒否されることがあります。このスタックは Access Point を作らず（既存のものをパラメーターで受け取る）、そのポリシーも管理しないため、スタックの出力のロール ARN から `tools/render_access_point_policy.py` で作り、`aws s3control put-access-point-policy` で付けます（README の「Access Point のポリシー」）。ポリシーは `s3:DeleteObject` を `delete` 関数のロールだけに、`s3:PutObject` を戻しのロールだけに許可します。テスト（`test_definitions.py`、`test_review_followup.py`）は、`s3:DeleteObject` を持つリソースが `delete` 関数だけであること、Access Point への `s3:PutObject` を持つのが戻しの 2 つだけであること、Object Lock、Vault Lock、SnapLock、保持期間に当たるプロパティとアクションがテンプレートにないことを確かめます。このテンプレートは、台帳の項目に書き込む値を IAM で絞っていません。代わりに、項目を更新できる主体の数を減らしています。
## 失敗の想定と影響範囲
| 失敗 | 結果 | 影響範囲 |
|---|---|---|
| 写した後にファイルが書き換えられた | ETag の不一致で `CHANGED`。消さない | そのファイル |
| 写している間に書き換えられた | `CopySourceIfMatch` が `PreconditionFailed`。`CHANGED` | そのファイル |
| バケットのチェックサムが台帳と違う、または無い | `MISMATCH`。消さない | そのファイル |
| 照合と削除の間に書き換えられた | 検出できない（Access Point の `DeleteObject` が条件付き削除に非対応） | そのファイル。窓は API 呼び出し 1 往復分 |
| 承認者が応答しない | `ApprovalTimeoutHours` で打ち切り、`REJECTED_OR_TIMED_OUT`。消さない。`ApprovalPendingAlarm` が先に知らせる | 実行 |
| 起動者が自分で承認した（`RequireSeparateApprover=true`） | `RecordApproval` が拒否し、`APPROVAL_REFUSED`。何も `APPROVED` にならず、消さない | 実行 |
| `dryRun` を文字列で渡した | 入力エラー。何も起きない | 実行 |
| 使用済みの `runId` で開始した | 入力エラー（`resume` を付けた場合だけ続行） | 実行 |
| Lambda や Fargate が失敗した | Retry の後に `FAILED`。台帳に理由が残る。消さない | そのファイル |
| Fargate のタスクが終了しない | `FargateTimeoutSeconds`（既定 7200 秒）で `States.Timeout`。1 回再試行し、`FAILED` | そのファイル |
| 削除の呼び出しの後で例外（タイムアウト、台帳の書き込み失敗） | 項目は `DELETING` と `claimedBy` を残す。再試行が Access Point を見て、無ければ `DELETED`、あれば消す | そのファイル |
| 再試行が尽きた、または実行が止まって `DELETING`、`APPROVED` が残った | 結果は `COMPLETED_WITH_ERRORS`。`FilesStuckDeletingAlarm` が知らせる。`resume` で整理する（README の「中断した削除の回復」） | そのファイル |
| 戻したファイルが台帳と違う | `RESTORE_MISMATCH`。`RestoreMismatchAlarm` が知らせる。属性の付け直しの対象から外れる | そのファイル |
| 戻し先に同名のファイルがある | `EXISTS` で上書きしない | そのファイル |
## ロールバック
アーカイブは、写した後であれば、承認の前に実行を止めればファイルは消えません。消した後は「戻し」のステートマシンで戻します。`DELETING` や `CHANGED` のまま残った項目も、アーカイブ用バケットに写しがあれば戻しの対象に選ばれます。アーカイブ用バケットのオブジェクトと台帳は、スタックを削除しても残ります（`DeletionPolicy: Retain`）。
## 出力の分類
台帳とマニフェストにはファイルのパスが入り、パスには個人の名前や案件の識別子が入りうるため、`data_classification` は既定で `RESTRICTED`（`shared/data_classification.py` の「限定されたアクセス」）です。パラメーター `DataClassification` で変えられます。ファイルの中身は元のデータと同じ分類で扱います。
