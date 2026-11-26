# archive-verify-delete アーキテクチャ
🌐 **Language / 言語**: 日本語 | [English](architecture.en.md)
## 概要
Amazon FSx for NetApp ONTAP（以下 FSx for ONTAP）の S3 Access Points と S3 API だけで、ファイルを S3 Glacier 系のクラスへ写し、照合し、承認の後に元を消します。ボリュームはマウントしません。使い方は [README](../README.md) にあります。この文書は構成、権限、失敗時の挙動を示します。
## 構成
| 構成要素 | 役割 | 置き場所 |
|---|---|---|
| `archive` ステートマシン | 選ぶ、記録する、写す、照合する、承認を待つ、消す、まとめる | Step Functions（Standard、Distributed Map） |
| `restore` ステートマシン | 台帳から選び、復元を要求し、待ち、Access Point へ戻す | 同上 |
| `select` | 入力の検査、`MTIME` での選択、`ATIME` の候補の確認 | Lambda（VPC 外） |
| `ontap_rest` | `accessed_time` による候補の列挙と、属性の取得 | Lambda（VPC 内。任意） |
| `record` | Access Point から読んでハッシュを計算し、台帳に書く | Lambda（VPC 外） |
| `ledger` | バケットの `HeadObject` を台帳と比べ、`VERIFIED` か `MISMATCH` にする。失敗を記録する | Lambda |
| `approval` | 承認用のマニフェストを書き、タスクトークンを保管し、通知する | Lambda |
| `delete` | ETag と大きさを確かめ、同じなら Access Point のファイルを消す | Lambda |
| `summarize` | 結果の JSON、EMF のメトリクス、通知、トークンの削除 | Lambda |
| `restore` | 戻しの補助（選ぶ、存在確認、復元状態の判定、確定、再付与スクリプト） | Lambda |
| Fargate のタスク | 5 GiB を超えるファイルのハッシュとマルチパートコピー | ECS Fargate（ARM64。任意） |
| 台帳 | `(runId, key)` ごとの状態、チェックサム、属性 | DynamoDB（PAY_PER_REQUEST、PITR） |
| アーカイブ用バケット | 写したオブジェクト（`data/`）とマニフェスト（`manifests/`） | S3（新規作成。Object Lock なし） |
VPC 内の Lambda は ONTAP の管理エンドポイントにだけ届き、Internet-origin の Access Point へは届かないため、機能を `ontap_rest`（VPC 内）と、それ以外（VPC 外）に分けています。
## 処理の流れ
```
archive: Plan → [MTIME: SelectMtime | ATIME: AtimeCandidates → SelectFromCandidates]
  → ProcessFiles (Distributed Map、ファイルごと):
       属性 → Record → (≤5 GiB: copyObject | >5 GiB: Fargate) → HeadArchived → CompareArchive
       → (任意) 2 つ目の写し → HeadSecond → CompareSecond
  → PrepareManifest → RequestApproval (waitForTaskToken) → ApprovalCheck → DryRunChoice
  → DeleteFiles (Distributed Map、ファイルごとに delete) → Summarize
```
削除の状態に着くには `RequestApproval`、`ApprovalCheck`、`DryRunChoice` のすべてを通る必要があります。この性質はテスト（`test_definitions.py`）で、状態の遷移図から各状態を取り除いて到達できなくなることを確かめています。
## 照合の方式
| ファイルの大きさ | 写し方 | チェックサム | 理由 |
|---|---|---|---|
| 5 GiB 以下 | `CopyObject` | `SHA256`（`FULL_OBJECT`） | バケットの値がファイルの SHA-256 と一致する（部品の確認） |
| 5 GiB 超 | マルチパートの `UploadPartCopy` | `CRC64NVME`（`FULL_OBJECT`） | マルチパートの SHA-256 は `COMPOSITE` で、ファイル全体の値と一致しない |
`COMPOSITE` を返された場合、チェックサムが無い場合は、一致とみなさず `MISMATCH` にします。
## 台帳
| 属性 | 内容 |
|---|---|
| `runId`（PK）、`key`（SK） | 実行とファイルのキー |
| `status` | `SELECTED`、`RECORDED`、`COPIED`、`VERIFIED`、`DELETING`、`DELETED`、`RESTORED`、`CHANGED`、`MISMATCH`、`FAILED` |
| `size`、`etag`、`lastModified` | 一覧の時点の値。削除の直前に再確認する |
| `sha256`、`sha256B64`、`crc64nvme` | 5 GiB 以下は Lambda、超える分は Fargate が書く |
| `archiveBucket`、`archiveKey`、`storageClass` | 写し先 |
| `attrs` | `uid`、`gid`、`mode`、`mtime`、`atime`（取れる場合） |
| `secondCopyRequired`、`secondCopy` | 2 つ目の写しの要否と照合結果 |
| `deletedBy`、`deletedAt`、`restoredAt`、`restoreRunId` | 削除と戻しの記録 |
`DELETED` への遷移は条件付きの書き込みです。`VERIFIED` から `DELETING` へ移せた実行だけが削除に進むため、同じファイルを 2 つの実行が同時に消すことはありません。削除の呼び出しが失敗したときは `VERIFIED` に戻すので、Step Functions の再試行が成功できます。
## IAM
| 主体 | 主な権限 | 持たない権限 |
|---|---|---|
| `delete` | Access Point の `s3:GetObject`、`s3:DeleteObject`、台帳の `GetItem`、`UpdateItem` | 他のバケットへの書き込み |
| `record` | Access Point の `s3:GetObject`、台帳の `PutItem` | 削除 |
| `select` | Access Point の `ListBucket`、`GetObject`、`manifests/*` の読み書き | 削除 |
| `approval` | 台帳の `Query`、`manifests/*` への書き込み、`/<stack>/approvals/*` への `PutParameter`、`sns:Publish` | 削除 |
| Fargate のタスク | Access Point の読み書き、バケットの読み書き、台帳の更新 | 削除 |
| ステートマシンのロール | Lambda の呼び出し、`CopyObject` に必要な S3 の読み書き、ECS の起動 | `s3:DeleteObject` |
Access Point への権限は、エイリアス形式（`arn:aws:s3:::<alias>/*`）と Access Point ARN 形式（`accesspoint/<name>/object/*`）の両方を書いています。片方だけだとデプロイできても、実行時に拒否されることがあります。テスト（`test_definitions.py`）は、`s3:DeleteObject` を持つリソースが `delete` 関数だけであること、Object Lock、Vault Lock、SnapLock、保持期間に当たるプロパティとアクションがテンプレートにないことを確かめます。
## 失敗の想定と影響範囲
| 失敗 | 結果 | 影響範囲 |
|---|---|---|
| 写した後にファイルが書き換えられた | ETag の不一致で `CHANGED`。消さない | そのファイル |
| 写している間に書き換えられた | `CopySourceIfMatch` が `PreconditionFailed`。`CHANGED` | そのファイル |
| バケットのチェックサムが台帳と違う、または無い | `MISMATCH`。消さない | そのファイル |
| 照合と削除の間に書き換えられた | 検出できない（Access Point の `DeleteObject` が条件付き削除に非対応） | そのファイル。窓は API 呼び出し 1 往復分 |
| 承認者が応答しない | `ApprovalTimeoutHours` で打ち切り、`REJECTED_OR_TIMED_OUT`。消さない | 実行 |
| `dryRun` を文字列で渡した | 入力エラー。何も起きない | 実行 |
| Lambda や Fargate が失敗した | Retry の後に `FAILED`。台帳に理由が残る。消さない | そのファイル |
| 削除の途中で実行が止まった | `DELETING` のまま残りうる。台帳を見て手で判断する | そのファイル |
| 戻し先に同名のファイルがある | `EXISTS` で上書きしない | そのファイル |
## ロールバック
アーカイブは、写した後であれば、承認の前に実行を止めればファイルは消えません。消した後は「戻し」のステートマシンで戻します。アーカイブ用バケットのオブジェクトと台帳は、スタックを削除しても残ります（`DeletionPolicy: Retain`）。
## 出力の分類
台帳とマニフェストは `operational-metadata`（パス、大きさ、ハッシュ、属性）です。ファイルの中身は元のデータと同じ分類で扱います。
