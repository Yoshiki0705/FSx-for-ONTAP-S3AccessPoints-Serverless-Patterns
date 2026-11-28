# archive-verify-delete: S3 API だけで写し、照合し、承認の後に消すアーカイブ
🌐 **Language / 言語**: 日本語 | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)
📚 **ドキュメント**: [アーキテクチャ](docs/architecture.md) | [Architecture (EN)](docs/architecture.en.md)
## 概要
Amazon FSx for NetApp ONTAP（以下 FSx for ONTAP）のボリュームにある、めったに読まれないファイルを、S3 Glacier 系のストレージクラスへ移すパターンです。ファイルの読み書きと削除には S3 Access Points の S3 API を使い、NFS のマウントは使いません。ただし、最終アクセス時刻で選ぶ `selection=ATIME` と属性の取得には ONTAP REST API（VPC 内の Lambda、ONTAP の認証情報、管理エンドポイント）が要り、戻した後の所有者・モード・更新時刻の付け直しには NFS でボリュームをマウントしたホストが要ります。
1 つのファイルは次の順に進み、途中で条件が崩れたファイルは消す対象から外れます。
1. 台帳（DynamoDB のテーブル）に、大きさ、ETag、SHA-256、CRC64NVME を記録する
2. アーカイブ用のバケットへ、ストレージクラスを指定して `CopyObject` で写す（キーは `<prefix><runId>/<元のキー>`）
3. バケットが返すチェックサムを、台帳の値と比べる
4. 一致したファイルの一覧を人が承認する。承認は台帳に `APPROVED` として記録され、起動した人と承認した人が同じなら拒否する（既定。申告された値の比較で、主体の証明ではない）
5. 台帳が `APPROVED` のファイルだけ、Access Point の ETag と大きさが台帳と同じことを確かめてから消す

戻すときは、台帳から探し、バケットで復元を要求し、完了を待って Access Point へ `CopyObject` で戻し、戻したファイルを読み直して台帳の SHA-256 と CRC64NVME で照合します。
このパターンは S3 Object Lock、S3 Glacier Vault Lock、AWS Backup Vault Lock、SnapLock、スナップショットのロックを使いません。テンプレートにも書いていません。保持期間は設定しないので、アーカイブ用のバケットのオブジェクトは、権限があれば消せます。
このパターンの前提と、他の方法との比較は [アーカイブ用クラスへ移す 9 種類の仕組みの比較](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/comparison/archive-tiering-library-options.md) にあります。
## 何を測り、何を測っていないか
| 区分 | 内容 |
|---|---|
| 部品を実機で 1 回ずつ確認した（上の比較資料に記録、2026-11-24 と 2026-11-26、ap-northeast-1、第 1 世代 `SINGLE_AZ_1`、ONTAP 9.19.1P4D1、UNIX スタイルのボリューム、Access Point のユーザーは UNIX root） | `CopyObject` に `ChecksumAlgorithm=SHA256` を付けると、バケットの `ChecksumSHA256` が `FULL_OBJECT` でファイルの SHA-256 と一致した（8 MiB まで）。5.5 GiB のマルチパートは SHA-256 が `COMPOSITE` になり、CRC64NVME は `FULL_OBJECT` で一致した。古い ETag の `--copy-source-if-match` は `PreconditionFailed`。Access Point の `DeleteObject` は `If-Match` 非対応。Step Functions の SDK 統合で Access Point のエイリアスを `Bucket` に渡せた |
| このリポジトリで確認した | moto を使った単体テストと、ステートマシンと IAM の構造のテスト。AWS には接続していません。下の「デプロイと運用の前提条件」の権限と設定は、テストで検査しています |
| 5.5 GiB を含む 7 ファイルの通しで 1 回ずつ確認した（2026-11-26、上と同じ環境、`selection=ATIME`、`GLACIER`、7 ファイル） | ONTAP REST API による `accessed_time` の選択と uid、gid、mode、mtime、atime の取得（ルートはボリュームのルートで、パスの先頭にスラッシュなし。`unix_permissions` は `640` の整数で返る）。Distributed Map の `ItemReader` と `ResultWriter`。Fargate による 5.5 GiB のマルチパートコピー（`CopySourceIfMatch` 付き、CRC64NVME が台帳と一致）。Lambda での 5.3 GB（約 4.94 GiB）のハッシュ計算（69.8 秒、メモリ 2048 MB、使用 152 MB）。2 つ目の写し。承認後の削除。承認待ちの間に NFS で書き換えたファイルは `CHANGED` になり消えなかった。承認の拒否で何も消えなかった。`Expedited` での戻し（5.5 GiB を含む）と、戻した 6 ファイルの SHA-256 の一致（7 ファイル中の残る 1 ファイルは書き換え済みで、削除も戻しもされていない）。`reapply.sh` による uid、gid、mode、mtime の復元 |
| 除外と承認を確かめる通しで 1 回ずつ確認した（2026-11-26、上と同じ環境、`GLACIER`、2 つ目の写しあり。dry run は `selection=ATIME`、本番は `selection=MTIME` と ONTAP REST での属性取得。64 B から 1 MiB のファイルと 51 GiB の疎ファイル） | 5.5 GiB を含む 7 ファイルの通しにない項目の確認。`maxFiles=50` の選択で、64 B の 3 ファイルと 131,071 B の 1 ファイルが最小サイズで外れ、131,073 B は残った。`*.vmdk` と保全用のプレフィックスの除外。51 GiB の疎ファイルが `SKIPPED_TOO_LARGE` として台帳に載り、写されなかった。使用済みの `runId` と、`requestedBy` のない本番の入力が入力エラーで止まった。起動した主体と同じ ARN での承認が `APPROVAL_REFUSED` になり、何も消えなかった。`delete` 関数を承認なしで直接呼ぶと `NOT_APPROVED` で消えなかった。別の主体の承認では 3 ファイルが消え、承認待ちに書き換えた 1 ファイルが `CHANGED` で残った。戻しの後の照合で 3 ファイルが `RESTORE_VERIFIED`。アラームが KMS で暗号化したトピックへ発行できた |
| 直接呼び出しを確かめる確認で 1 回ずつ確認した（2026-11-26、同じアカウントと Access Point、`selection=MTIME`、`GLACIER`、Fargate なし、256 KiB のファイル 8 つ、`MapConcurrency=1`） | 承認の直後に実行を止めると、`APPROVED` の項目が残った。その項目への `delete` 関数の直接呼び出しは、別の実行の `claim` では `NOT_APPROVED`（`approval not current`）、止めた実行自身の ARN の `claim` でも `NOT_APPROVED`（`claiming execution is not running`）で、どちらも消えなかった。`reconcile` は残った項目を `VERIFIED` に戻した。実行中の実行の通常の削除では、承認した項目がすべて `DELETED` になった。承認の後と拒否の後に、タスクトークンのパラメーターが消えていた。トークンは、スタックの KMS キーで暗号化されていた |
| 承認と戻しの経路を確かめる確認で 1 回ずつ確認した（2026-11-28、同じ環境、`GLACIER`、2 つ目の写しあり、Fargate あり、`ApprovalTimeoutHours=1`、`ApprovalValidityHours=1`、`ApprovalAlarmHours=1`） | 承認専用の一時の IAM ロールで承認すると、3 ファイル（5.5 GiB を含む）が `DELETED` になった。起動した主体と同じ主体の承認は `APPROVAL_REFUSED` だった。CloudTrail では、`SendTaskSuccess`（管理イベント）の `userIdentity` が、受理した承認では承認用のロール、拒否した承認では起動した主体だった。`DeleteObject`（`resources.type` が `AWS::S3::AccessPoint` のデータイベントのトレイル）は 11 件とも `delete` 関数のロールで、`resources` に `AWS::FSx::Volume`、`AWS::S3::AccessPoint`、`AWS::S3::Object` が入った。5.5 GiB のファイルの戻しは、Fargate のタスクがコピーと戻した後の照合を行い、`RESTORE_VERIFIED` になった（SHA-256 は事前に NFS で記録した値と一致）。実行中の実行の `claim` での削除の再試行は、既に消えたファイルを `DELETED`（`already gone on retry`）にした。`COMPLETED_WITH_ERRORS` で終わった実行を `"resume": true` で起動すると、`reconcile` が消えていた 1 件を `DELETED`、残っていた 1 件を `VERIFIED` にし、承認の後にその 1 件が消えた。承認から 1 時間を過ぎた `APPROVED` の項目は、実行中の実行の `claim` でも `NOT_APPROVED`（`approval not current`）で、承認時刻を直前にした対照は `DELETED` だった。承認待ちが約 69 分続くと `ApprovalPendingAlarm` が `ALARM` になり、通知が届いた。消えたパスに NFS で別のファイルを置いてから戻すと `EXISTS` で、NFS のファイルの SHA-256 は変わらなかった。アーカイブ用バケットの写しを別の内容の版に差し替えて戻すと `RESTORE_MISMATCH` になり、`RestoreMismatchAlarm` が `ALARM` になった。元の版を最新に戻して `"retryMismatched": true` で戻すと `RESTORE_VERIFIED` になった。`touch -d` で atime を 2020 年にした 12 秒後と約 5 分後の `selection=ATIME` の dry run は、どちらも 2 ファイルを選んだ |
### 通しの環境と手順ごとの結果
環境は ap-northeast-1、FSx for ONTAP の第 1 世代 `SINGLE_AZ_1`、ONTAP 9.19.1P4D1、UNIX セキュリティスタイルのボリューム、Access Point のファイルシステムユーザーは UNIX root です。実行日は 2026-11-26（時刻は日本時間）、各手順は 1 回だけ実行しました。構成は `selection=ATIME`、`GLACIER`、2 つ目の写しあり、Fargate は arm64 の 2 vCPU と 8 GiB です。データは小さい 6 ファイル（64 B が 3 つ、8 MiB が 3 つ。所有者 1234:5678、モード 640、mtime と atime は 2020-01-02）と、5,905,580,032 B のファイル 1 つです。
| 手順 | 結果 | 所要 |
|---|---|---|
| 1. デプロイ | 成功 | |
| 2. dry run（`dryRun=true`） | 成功。7 ファイルとも `VERIFIED`（SHA-256 一致 6、CRC64NVME 一致 1）、2 つ目の写しも `VERIFIED`。削除 0 バイトで、NFS では 7 ファイルとも残った | 244 秒（承認の待ち約 70 秒を含む） |
| 3. 承認待ちの間の書き換え | NFS で 1 ファイルを同じ大きさのまま 4 KiB 上書き（mtime は更新）。承認後に `CHANGED`（ETag または大きさの不一致）になり、消えなかった | |
| 4. 本番（`dryRun=false`）と承認 | 6 ファイルが `DELETED`、1 ファイルが `CHANGED`。`bytesDeleted` は 5,922,357,440。NFS では 6 ファイルが消え、書き換えた 1 ファイルだけが残った | 310 秒（承認要求まで 172 秒、承認から完了まで約 6 秒） |
| 5. 戻し（`tier=Expedited`、`days=1`） | 6 ファイルが `RESTORED`（5.5 GiB を含む）。SHA-256 は 6 ファイルとも手順 1 の前に NFS で記録した値と一致。`CHANGED` の 1 ファイルは対象外 | 287 秒（小さい 5 ファイルは約 2.5 分、5.5 GiB の Fargate コピーは 2 分 38 秒） |
| 6. 承認の拒否（`send-task-failure`） | 実行は `REJECTED_OR_TIMED_OUT` で終わり、3 ファイルは `VERIFIED` のまま。`deletedBy` は空で、NFS では 3 ファイルとも残った | 16 秒 |
| 追加: Lambda で 5.3 GB（約 4.94 GiB）のハッシュ | `VERIFIED`（SHA-256 が NFS の値と一致）、2 つ目の写しも `VERIFIED` | `record` 関数 69.8 秒（メモリ 2048 MB 設定、使用 152 MB） |
| 追加: 復元要求の二重投入 | 2 回目は HTTP 409 `RestoreAlreadyInProgress`。Step Functions の SDK 統合は `S3.S3Exception` で返す | |
撤去は全リソースを消し、読み戻して確認しました。
### 使用量（1 回の実行。請求額ではない）
| 実行 | ファイル数 | 所要 | 状態遷移（親 + 子 Map 実行） | Fargate タスク |
|---|---|---|---|---|
| dry run | 7 | 244 秒 | 12 + 107 = 119 | 2 回（ハッシュとコピー 96 秒、2 つ目の写し 35 秒） |
| 本番 | 7 | 310 秒 | 13 + 114 = 127 | 2 回（94 秒、35 秒） |
| 戻し | 6 | 287 秒 | 4 + 103 = 107 | 1 回（156 秒） |
| 拒否 | 3 | 16 秒 | 10 + 45 = 55 | 0 回 |
- Lambda の実行時間の合計（CloudWatch。失敗した実行を含み、4.94 GiB の実行は含まない）: `select` 13 回で 5.9 秒、`ontap_rest` 11 回で 13.4 秒（失敗 2 回）、`record` 17 回で 11.7 秒、`ledger` 34 回で 9.1 秒、`approval` 6 回で 4.3 秒、`delete` 7 回で 5.6 秒、`summarize` 5 回で 5.1 秒、`restore` 26 回で 9.2 秒
- Fargate は 5 タスクで合計約 416 秒（2 vCPU、8 GiB、arm64）。DynamoDB（オンデマンド）は読み取り 68.5 RCU、書き込み 74 WCU（全実行の合計）
- S3 のリクエスト数は測っていません（リクエストメトリクスを有効にしていません）
除外と承認を確かめる通し（2026-11-26、小さいファイル、2 つ目の写しあり、`MapConcurrency=2`）の状態遷移は次のとおりです。1 回ずつの値で、ファイルの大きさと経路で変わります。

| 実行 | 対象のファイル | 所要 | 状態遷移（親 + 子 Map 実行） | 1 ファイルあたり |
|---|---|---|---|---|
| dry run | 4 | 66 秒（承認の待ち約 20 秒を含む） | 12 + 60 = 72 | 18 |
| 本番（3 件削除、1 件 `CHANGED`） | 4 | 45 秒（承認の待ちを含む） | 14 + 64 = 78 | 19.5 |
| 戻し（Expedited、照合つき、1 件は `EXISTS`） | 4 | 192 秒 | 4 + 52 = 56 | 14 |
### デプロイと運用の前提条件
テンプレートとポリシーを作るスクリプトは、次の条件を満たすように書いてあります。テンプレートを変えるときや、別の仕組みに移すときの確認項目です。
| # | 条件 | 満たさないときの症状 | パターンでの扱い |
|---|---|---|---|
| 1 | `selection=ATIME` では、アーカイブのステートマシンのロールが ONTAP REST 関数を呼べる | 選択の段階で失敗する | ロールに `lambda:InvokeFunction` を付ける |
| 2 | ONTAP REST 関数が、FSx for ONTAP の管理エンドポイントの証明書を扱える。この証明書は公的な CA の署名ではない | 常に TLS を検証すると `CERTIFICATE_VERIFY_FAILED` で失敗する | パラメーター `OntapVerifySsl`（既定 `false`）。`false` の間、ONTAP の認証情報は相手を認証しない接続で送られる（経路は VPC 内） |
| 3 | 復元要求の二重投入を、進行中の復元として扱う。二重投入は HTTP 409 `RestoreAlreadyInProgress` で、Step Functions の SDK 統合は `S3.S3Exception` で返す | `S3.RestoreAlreadyInProgressException` を指定した `Catch` には一致せず、ファイルの失敗になる | `S3.S3Exception` を受けて完了待ちへ回す |
| 4 | ステートマシンのロールが、ログの配信先を設定できる | デプロイが `The state machine IAM Role is not authorized to access the Log Destination` で失敗する | ロールに `logs:CreateLogDelivery` などを付ける |
| 5 | `delete` と `restore` の関数が `s3:ListBucket` を持つ。持たない主体には、存在しないキーへの `HeadObject` が 404 ではなく 403 で返る | 消えた後の再試行と `reconcile` が 403 で失敗する | IAM と Access Point のポリシーの両方で `s3:ListBucket` を許可する |
| 6 | CloudWatch アラームが、KMS で暗号化したトピックへ発行できる。キーのポリシーとトピックのポリシーの両方に `cloudwatch.amazonaws.com` の許可が要る | アラームの通知が `CloudWatch Alarms is not authorized to perform: SNS:Publish` で失敗する | キーとトピックの両方のポリシーに文を置く |
| 7 | ステートマシンのロールが、`ecs:runTask.sync` の状態に要る `events:PutRule` などを持つ。Fargate を使わない（`FargateImageUri` が空）ときも、定義にこの状態があるので作成時に検査される | デプロイが `is not authorized to create managed-rule` で失敗する | 許可を `UseFargate` の条件の外に置く |
### 実機の通しで確かめた挙動
パターンの設計で前提にしている挙動です。
- `selection=ATIME` では、このパターン自身の読み取りが `accessed_time` を更新します。`dryRun=true` で一度回すと、ハッシュ計算の読み取りでファイルの atime が実行時刻になり、同じ入力で `dryRun=false` を回しても選ばれません（0 件で終了。dry run の直後に本番を回したときに確認）。dry run の直後に同じ候補で本番を回すなら `selection=MTIME` を使ってください（`LastModified` は読み取りで変わりません）
- ETag について、公式の記述とこの環境の測定は次のとおりです。公式のページ（[Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)、2026-11-26 閲覧）は "The ETag reflects changes only to the contents of an object, not its metadata" と書いています。この環境の 1 回の測定では、同じ大きさと同じ mtime を持つ内容の違うファイル 3 つが、同じ ETag を返しました。したがって、消す前の ETag と大きさの確認は、大きさと mtime を変えない内容の変更を検出できない、とこのパターンは扱います。承認待ちの間に大きさが同じまま mtime が更新された書き換えは検出されました（5.5 GiB を含む 7 ファイルの通しの手順 3、除外と承認を確かめる通しの本番） [E-023]
- Access Point 経由で最後のファイルを消すと、空になった親ディレクトリも消えます（除外と承認を確かめる通しで確認）。戻しの `CopyObject` が親ディレクトリを作り直します
- 戻したファイルの所有者は 0:1、モードは 644、更新時刻は戻した時刻でした。NFS でボリュームをマウントしたホストで、生成された `reapply.sh` を root として実行すると、元の uid、gid、mode、mtime（1234:5678、640、2020-01-02 03:04:05）に戻り、内容の SHA-256 は変わりませんでした
- 戻しのステートマシンは、`CHANGED` で残ったファイルにもアーカイブ用バケットの写しがあれば対象に選びます。Access Point に同じキーがあれば `EXISTS` で上書きしません（除外と承認を確かめる通しの戻しで 1 件を確認）
- 戻しの 5.5 GiB は `Expedited` の要求が受け付けられ、完了も約 4 分以内でした
### 確認していないこと
- 多数のファイルでの所要時間と料金。並列度を変えたときのファイルシステムのスループットと、業務のクライアントのレイテンシ
- `Standard` と `Bulk` の戻しの完了待ち（実機では `Expedited` のみ）
- `S3.SlowDownException` の再試行（SDK 統合が返す名前を観測していません。前提条件の 3 と同じ型の食い違いが起きる恐れがあります）
- 50 GiB を超えるファイルの写しと戻し（選択から外す動作だけを、疎ファイルで確認）
- NTFS ボリューム、root 以外のユーザー、第 2 世代、Multi-AZ
- `touch -d` で atime を戻した約 10 秒後の実行で、候補が 0 件になった例が 1 回あります。2026-11-28 に 12 秒後と約 5 分後で試すと、どちらも選ばれ、再現しませんでした。原因は特定していません
- 承認の待ちが `ApprovalTimeoutHours` を過ぎて実行が終わることと、ウォッチドッグが残ったタスクトークンを承認のタイムアウトに 1 時間を足した後に消すこと（単体テストのみ）
### 消す前の確認に残る書き込みの窓
消す前の確認には、書き込みの窓が 1 つ残ります。Access Point の `DeleteObject` は条件付きの削除に対応していないため、`HeadObject` で確かめてから消すまでの間に書き換えられても検出できません。この窓は API 呼び出し 1 往復分です。
## 処理の流れ
### アーカイブ
入力は `olderThanDays` が必須で、`dryRun` の既定は `true` です。`dryRun=false` の実行は、`RequireSeparateApprover=true`（既定）のとき、起動する主体の ARN を `requestedBy` に入れる必要があります。
| 段階 | 処理 | 実装 |
|---|---|---|
| 1. 選ぶ | `MTIME`: Access Point の `ListObjectsV2` の `LastModified`。`ATIME`: ONTAP REST API の `accessed_time`（VPC 内の Lambda）。除外（下の表）を適用する | `select`、`ontap_rest` |
| 2. 記録する | 大きさ、ETag、SHA-256、CRC64NVME、取れる場合は uid、gid、mode、mtime、atime を台帳へ。5 GiB 以下は Lambda、超える分は Fargate | `record`、Fargate のタスク |
| 3. 写す | 5 GiB 以下は SDK 統合の `copyObject`（`SHA256`、台帳の ETag を `CopySourceIfMatch` に付ける）。超える分は Fargate のマルチパートコピー（`CRC64NVME`） | Step Functions、Fargate |
| 4. 照合する | バケットの `HeadObject`（`ChecksumMode=ENABLED`）の大きさとチェックサムを台帳と比べる。一致しなければ `MISMATCH` で残し、消す対象から外す | `ledger` |
| 5. 2 つ目の写し（任意） | 同じリージョンの別バケットへ Access Point から写し、同じ照合をする。不一致なら消す対象から外す | Step Functions、`ledger` |
| 6. 承認する | 一致した一覧を `manifests/<runId>.json` に書き、SNS で通知して `waitForTaskToken` で待つ。通知は、写しが 1 つだけのときと、戻せない大きさのファイルがあるときにそう書く | `approval` |
| 7. 承認を記録する | `dryRun=false` のときだけ。承認者が起動者と同じなら拒否する。違えば一覧の各ファイルを台帳で `VERIFIED` から `APPROVED` にし、`manifests/<runId>-approval.json` を書く | `approval` |
| 8. 消す | 台帳が `APPROVED` のファイルだけ。ファイルごとに ETag と大きさを確かめ、同じなら `DeleteObject`。違えば `CHANGED` で残す | `delete` |
| 9. 記録する | `manifests/<runId>-result.json` と EMF のメトリクス（件数、バイト数、除外の件数）。`DELETING` か `APPROVED` が残れば `COMPLETED_WITH_ERRORS` | `summarize` |
`dryRun=true` でも段階 6 までは進みます。つまりコピーは行われ、アーカイブ用のクラスの保管料金（最小保管期間あり）が発生します。試すときは `maxFiles` を小さくしてください。削除は行われません。
台帳のステータスは `SELECTED`、`RECORDED`、`COPIED`、`VERIFIED`、`APPROVED`、`DELETING`、`DELETED`、`RESTORED`、`RESTORE_VERIFIED` の順に進み、途中の出口が `CHANGED`、`MISMATCH`、`FAILED`、`SKIPPED_TOO_LARGE`、`RESTORE_MISMATCH` です。消せるのは `APPROVED`（2 つ目の写しを必須にした場合は、その照合も済んだもの）だけです。

使用済みの `runId` は入力エラーになります。中断した実行を続けるときだけ、同じ `runId` に `"resume": true` を付けます（下の「中断した削除の回復」）。アーカイブ用バケットのキーに `runId` が入るので、dry run と本番、書き換えた後の再アーカイブが互いのオブジェクトを上書きしません。上書きはバージョニングがなければ前のオブジェクトの削除になり、最小保管期間のあるクラスでは早期削除の料金がかかりえます。

選択から外すもの:

| 条件 | 既定 | 理由 |
|---|---|---|
| 50 GiB を超える | 外して台帳に `SKIPPED_TOO_LARGE` を記録する。`allowOversize: true` で含められる | 公式のページ（[Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)、2026-11-26 閲覧）が "Maximum object size is 50 GiB for uploads, but you can download objects larger than that" と書いている。戻しは Access Point への書き込みなので、超えたファイルはこのパターンでは戻せない（バケットから直接ダウンロードはできる） [E-021] |
| `MinFileSizeBytes` 未満 | 131,072 バイト（128 KiB）。入力の `minSizeBytes` で変えられる | [Amazon S3 のストレージクラスの比較](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html#sc-compare)（2026-11-26 閲覧）によると、Standard-IA と Glacier Instant Retrieval は 1 オブジェクトあたり最低 128 KB で課金し、Glacier Flexible Retrieval と Deep Archive は 1 オブジェクトにつき 40 KB（32 KB はそのクラスの単価、8 KB は Standard の単価）のメタデータを加える。小さなファイルではこの分が実体より大きくなる |
| `ExcludePatterns`（glob）、`ExcludePrefixes` | `ExcludePatterns` は下の一覧、`ExcludePrefixes` は空 | スタックの値は常に適用し、入力の `excludePatterns`、`excludePrefixes` は追加だけができる。保全（リーガルホールド）の対象のプレフィックスはここに入れる |

Iceberg、Delta、Hive 形式の表のデータファイル、使用中のデータベースのファイル、VM のディスクイメージ（`*.vmdk`、`*.vhd`、`*.qcow2` など）は必ず除外してください。このパターンはファイルを 1 つずつ移し、表のメタデータやファイルを開いているプロセスを知りません。表は表の機能（パーティションの切り離し、スナップショットの期限切れ）で整理してから、切り離した後のパスだけを対象にします。保全の対象かどうかの判断は利用者の法務の判断で、このパターンは代わりをしません。
`ExcludePatterns` の既定値は、実在の事故が起きやすいファイルの型を並べた出発点で、完全な一覧ではありません。VM のディスクイメージ（`*.vmdk`、`*.vhd`、`*.vhdx`、`*.vdi`、`*.qcow2`）は、VM が開いたまま書き続けるので、1 ファイルずつ移すと壊れた写しになります。データベースのデータとログのファイル（SQL Server の `*.mdf`、`*.ndf`、`*.ldf`、MySQL InnoDB の `*.ibd`、Oracle の `*.dbf`）は、データベースが開いて書き込みます。表形式のメタデータのディレクトリ（Delta の `_delta_log/`、Hudi の `.hoodie/`、Iceberg の `metadata/`）は、データファイルの一覧を持つので、データファイルだけを移すと表が壊れます。照合は大文字小文字を区別します（`*.VMDK` は一致しません）。Iceberg でない `metadata/` という名前のディレクトリも除外されます。`*.parquet` のような表のデータファイルは既定に入れていません。自分の環境のパターンを足してください。空にできるのは、この種のファイルがボリュームに一切ない場合だけです。
### 戻し
入力は `runId` と、`keys` または `prefix` のどちらか 1 つです。`tier`（既定 `Bulk`）と `days`（既定 7）を指定できます。
1. 台帳で `DELETED` のファイルを選ぶ。`DELETING` と `CHANGED` のファイルも、アーカイブ用バケットに写しがあれば選ぶ（削除の中断で残った項目を戻せるように）
2. Access Point に同じキーが既にあれば `EXISTS` として残し、上書きしない
3. S3 Glacier Flexible Retrieval と S3 Glacier Deep Archive のオブジェクトは `RestoreObject` を要求する（S3 Glacier Instant Retrieval は不要）
4. 完了待ちはポーリングです（`RestorePollMinutes` ごとに `HeadObject` の `Restore` ヘッダーを読み、`RestoreMaxWaitHours` で打ち切る）。EventBridge の `Object Restore Completed` は使っていません。バケットの EventBridge 通知は有効にしてあるので、後から切り替えられます
5. バケットから Access Point へ `CopyObject`（5 GiB 超は Fargate）。台帳は `RESTORED`
6. 戻したファイルを Access Point から読み直してハッシュを計算し、台帳の SHA-256、CRC64NVME、大きさと比べる（5 GiB 超は Fargate）。一致すれば `RESTORE_VERIFIED`、違えば `RESTORE_MISMATCH`
7. 属性の付け直し用スクリプト `manifests/<runId>-reapply.sh` を書く。対象は `RESTORE_VERIFIED` のファイルだけ

戻したファイルの所有者は 0:1、モードは 644、更新時刻は戻した時刻でした（上の環境の確認）。元の値は `CopyObject` では戻りません。
`RESTORE_MISMATCH` のファイルは、既定では戻しの対象に選びません。Access Point にある写しが台帳と一致しなかった項目で、そのまま選ぶと `EXISTS` として残るためです。やり直すときは、戻しの入力に `"retryMismatched": true`（JSON の真偽値）を付けます。この場合に限り、その `runId` の台帳が今 `RESTORE_MISMATCH` の項目だけが対象になり、Access Point にある不一致の写しを、バケットの写しで上書きします。ほかのステータスの項目は、この指定でも既存のファイルを上書きしません。上書きの後は、これまでと同じ読み直しで `RESTORE_VERIFIED` か `RESTORE_MISMATCH` になります。
### 中断した削除の回復
削除の途中で Lambda が止まる、再試行が尽きるなどして、台帳に `DELETING` か `APPROVED` が残ることがあります。この状態は結果の `COMPLETED_WITH_ERRORS`、`stuckDeleting`、`notDeleted` と、`FilesStuckDeletingAlarm` で分かります。同じ `runId` に `"resume": true` を付けてアーカイブのステートマシンを起動すると、`reconcile` が次のように整理し、残ったファイルについて改めて承認を求めます。
| 台帳 | Access Point | 整理の結果 |
|---|---|---|
| `DELETING` | ファイルがない | `DELETED`（削除は済んでいた。`reconciled: true`） |
| `DELETING`、`APPROVED` | ファイルがあり、ETag と大きさが台帳と同じ | `VERIFIED` に戻す。消すには新しい承認が要る |
| `DELETING`、`APPROVED` | ファイルがあり、台帳と違う | `CHANGED` |
| どちらでも | その項目を持つ実行がまだ動いている | 触らない |
```bash
aws stepfunctions start-execution --state-machine-arn <ArchiveStateMachineArn> \
  --input '{"runId": "<runId>", "olderThanDays": 0, "resume": true, "dryRun": false, "requestedBy": "<your IAM principal ARN>"}'
```
`DELETING` のまま戻す必要があるときは、戻しのステートマシンがアーカイブ用バケットの写しから戻します。
## 承認の操作
承認の通知にはトークンを含めません。トークンは Systems Manager Parameter Store の SecureString（`/<stack>/approvals/<runId>`）にあります。承認する人は、そのパラメーターを読める権限と `states:SendTaskSuccess` の権限を持つ人です。
```bash
TOKEN=$(aws ssm get-parameter --name /<stack>/approvals/<runId> --with-decryption --query Parameter.Value --output text)
aws stepfunctions send-task-success --task-token "$TOKEN" \
  --task-output "{\"approved\": true, \"approver\": \"$(aws sts get-caller-identity --query Arn --output text)\"}"
# 拒否:
aws stepfunctions send-task-failure --task-token "$TOKEN" --error Rejected --cause "<reason>"
```
承認の後、`approval` 関数が `approver` を起動時の `requestedBy` と比べます（`RequireSeparateApprover=true`、既定）。同じ主体なら、何も `APPROVED` にせず `APPROVAL_REFUSED` で終えます。ロールの ARN とそのロールのセッションの ARN は同じ主体として扱います。違えば、一覧の各ファイルを台帳で `APPROVED` にし、`approvedBy`、`approvedAt`、実行の ARN を記録します。`delete` 関数が消すのは、この記録のあるファイルだけです。関数を直接呼び出しても、承認の記録のないファイルは消えません。

`approver` と `requestedBy` はどちらも呼び出す側の申告です。台帳の `deletedBy` は台帳の `approvedBy` から取ります。実際に起動した主体と承認した主体を証明するのは CloudTrail の `StartExecution` と `SendTaskSuccess` のイベントです。職務の分離を主体の単位で保証するには、起動と承認のロールを IAM で分けてください。 起動者と承認者の比較は、申告された 2 つの値の比較です。別の主体が承認したことを強制する仕組みではなく、強制しているとは主張しません。事後の統制は CloudTrail の `userIdentity` で、`StartExecution` と `SendTaskSuccess` を実行した主体を突き合わせて確かめます。
### 承認の有効範囲とトークンの扱い
`delete` 関数が消すのは、台帳が `APPROVED` で、`approvalExecutionArn` が今の実行と同じで、`approvedAt` が `ApprovalValidityHours`（既定 24 時間）以内の項目だけです。承認の後に実行を止めると `APPROVED` の項目が残りますが、別の実行の `claim` とは一致しないため、`delete` 関数を直接呼んでも `NOT_APPROVED` になります。期間を過ぎた承認も同じです。残った項目は `reconcile` が `VERIFIED` に戻します。 `claim` に停止した実行自身の ARN（台帳に載っています）を渡しても、その実行が `RUNNING` でなければ拒否します。実行の状態を読めないときも拒否します。

タスクトークンは、承認が成立したとき（`approval` 関数）、起動者と同じ主体の承認を拒否したとき、承認の拒否・タイムアウト・実行の失敗の後（`summarize`）に削除します。実行が `summarize` に届かず残ったトークンは、`watchdog` が、承認のタイムアウトに 1 時間を足した時間を過ぎたものを削除します。トークンはスタックのカスタマー管理 KMS キー（出力 `ApprovalTokenKeyArn`）で暗号化されているので、読むには `ssm:GetParameter` に加えて、そのキーの `kms:Decrypt` が要ります。

承認者のロールの IAM ポリシーの例です。`states:SendTaskSuccess` と `states:SendTaskFailure` は、IAM でリソースを指定できず（[Step Functions の認可リファレンス](https://docs.aws.amazon.com/service-authorization/latest/reference/list_awsstepfunctions.html)、2026-11-26 閲覧） [E-024]、このステートマシンの実行だけに絞れません。トークンを持つ者がその実行を承認できるので、絞れるのはトークンを読む経路です。`StartExecution` はこのロールに付けないでください。
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadApprovalToken",
      "Effect": "Allow",
      "Action": "ssm:GetParameter",
      "Resource": "arn:aws:ssm:<region>:<account>:parameter/<stack>/approvals/*"
    },
    {
      "Sid": "DecryptApprovalToken",
      "Effect": "Allow",
      "Action": "kms:Decrypt",
      "Resource": "<ApprovalTokenKeyArn>",
      "Condition": {"StringEquals": {"kms:ViaService": "ssm.<region>.amazonaws.com"}}
    },
    {
      "Sid": "ReportApproval",
      "Effect": "Allow",
      "Action": ["states:SendTaskSuccess", "states:SendTaskFailure"],
      "Resource": "*"
    }
  ]
}
```
## 属性の付け直し
戻しの最後に、`manifests/<runId>-reapply.sh` が書かれます。NFS でボリュームをマウントしたホストで、root として実行します。
```bash
MOUNT_ROOT=/mnt/<volume> sh reapply.sh
```
スクリプトは `chown`、`chmod`、`touch -d` だけを含み、台帳の値は厳密な形式で検査し、キーはシェルのクォートで 1 語にします。形式に合わない値はコメントになり、実行されません。ONTAP REST API による所有者、グループ、モード、更新時刻の設定は試していないため、この経路は含めていません。
## デプロイ
### 前提
- Access Point のエイリアスと ARN の両方（IAM に両方の形式が要ります。エイリアスだけのポリシーはデプロイできても、実行時に拒否されます）
- Access Point のポリシー。このスタックは Access Point を作らず（既存のものをパラメーターで受け取る）、そのポリシーも管理しないため、デプロイの後に下の手順で付けます。付けないと、最初の S3 の呼び出しが実行時に拒否されます
- アーカイブ用バケットの名前（スタックが作成します。`DeletionPolicy: Retain`、Block Public Access、SSE-S3 が既定、KMS は任意、EventBridge 通知有効、TLS 必須）
- `selection=ATIME` と属性の記録を使うときだけ: VPC、サブネット、ONTAP の認証情報のシークレット、管理エンドポイント、ボリュームの UUID、`OntapVerifySsl`。FSx for ONTAP の管理エンドポイントの証明書は公的な CA の署名ではないため、既定は `false`（検証しない）です。この間、ONTAP の認証情報は相手を認証しない接続で送られます（経路は VPC 内）。`true` にすると検証に失敗して選択の段階で止まります（実機で確認）。VPC 内の Lambda から Secrets Manager と S3 へ届く経路（VPC エンドポイントか NAT）が要ります
- 5 GiB を超えるファイルを扱うときだけ: ECR に置いたイメージ。Access Point がインターネット起点なので、Fargate のサブネットには NAT か公開 IP が要ります
- 通知のメールアドレスの購読の確認。SNS のメールの購読は、受信者が確認のリンクを押すまで有効になりません。届かないと、承認の依頼に誰も気づきません
### 手順
```bash
cd solutions/data-lifecycle/archive-verify-delete
cp samconfig.toml.example samconfig.toml   # <PLACEHOLDER> を置き換える
sam build && sam deploy
```
デプロイの後に Access Point のポリシーを付けます。スクリプトは、スタックの出力のロール ARN から、`s3:DeleteObject` を `delete` 関数のロールだけに、`s3:PutObject` を戻しのロールだけに許可するポリシーを作ります。
```bash
aws cloudformation describe-stacks --stack-name <stack> --query 'Stacks[0].Outputs' > outputs.json
python3 tools/render_access_point_policy.py --outputs outputs.json \
  --access-point-arn arn:aws:s3:<region>:<account>:accesspoint/<name> > ap-policy.json
aws s3control put-access-point-policy --account-id <account> --name <name> --policy file://ap-policy.json
aws sns list-subscriptions-by-topic --topic-arn <NotificationTopicArn> \
  --query 'Subscriptions[].SubscriptionArn'   # PendingConfirmation が残っていないこと
```
Access Point に既にポリシーがあるときは、上書きになります。既存の文と合わせてから付けてください。
Fargate を使う場合は、リポジトリのルートからイメージを作り、自分の ECR リポジトリへ push して `FargateImageUri` に指定します。
```bash
docker build --platform linux/arm64 \
  -f solutions/data-lifecycle/archive-verify-delete/fargate/Dockerfile -t <ecr-repo>:<tag> .
```
実行は、まず `dryRun` を省略した（つまり `true` の）入力で行います。
```bash
aws stepfunctions start-execution --state-machine-arn <ArchiveStateMachineArn> \
  --input '{"olderThanDays": 365, "prefix": "projects/", "maxFiles": 20, "excludePatterns": ["*.vmdk"]}'
```
削除まで行うときは `"dryRun": false` を JSON の真偽値で渡し、起動する主体を `requestedBy` に入れます。文字列の `"false"` は入力エラーになり、削除されません。
## ディレクトリ構成
```
archive-verify-delete/
├── template.yaml                # SAM。バケット、台帳、Lambda 9 個、ステートマシン 2 個、Fargate（任意）、アラーム
├── functions/{select,ontap_rest,record,ledger,approval,delete,summarize,restore,watchdog}/handler.py
├── statemachine/{archive,restore}.asl.json
├── fargate/{Dockerfile,entrypoint.py,requirements.txt}
├── tools/render_access_point_policy.py
├── tests/
├── docs/architecture.md, architecture.en.md
└── samconfig.toml.example
```
ドメインのロジック（チェックサム、入力の検査、台帳、戻した後の照合）は [`shared/archive_verify/`](../../../shared/archive_verify/) にあり、`shared/tests/` でテストします。Access Point への読み書きは `shared/s3ap_helper.py` を通します。
## ローカルテスト
```bash
python3 -m pytest solutions/data-lifecycle/archive-verify-delete/tests/ -v
python3 -m pytest shared/tests/test_archive_verify_*.py shared/tests/test_s3ap_helper_copy.py -v
```
削除の判定が壊れると検出されることを確かめるため、ETag の比較を取り除いたスタブで `test_does_not_delete_when_etag_changed` と `test_does_not_delete_when_size_differs_but_etag_equal` を 1 回実行し、2 件とも `assert 'DELETED' == 'CHANGED'` で失敗することを確認しました。承認の記録の検査と 50 GiB の除外は、テストを先に書いて変更前のコードで実行し、`assert 'DELETED' != 'DELETED'` と `KeyError: 'skippedTooLarge'` で失敗することを確認してから実装しました。
## Success Metrics
### Outcome
めったに読まれないファイルを、照合と人の承認を経て S3 Glacier 系のクラスへ移し、ボリュームの使用量を下げる。移したファイルは台帳から探して戻せる。
### Metrics
目標値は利用者が決めます。ここに数値は置きません。
| 区分 | 指標 | 定義 |
|---|---|---|
| Business Outcome | 解放した容量 | 実行の前後のボリュームの使用量の差（スナップショットの整理の後）。`bytesDeleted`（`-result.json`）は消したファイルの大きさの合計で、空いた容量ではない。スナップショットが残る間はボリュームの使用量が下がらず、圧縮と重複排除の効いたデータでは、空く量が論理サイズより小さい |
| Business Outcome | 月の保管料金の差の見込み | （容量プールから移した GB × 単価の差）−（アーカイブ用クラスの保管、1 オブジェクトの追加分、取り出しの料金）。単価は下の「費用の見積もり」 |
| Technical KPI | 照合の一致率 | `VERIFIED` ÷（`VERIFIED` + `MISMATCH`） |
| Technical KPI | 消さなかった件数 | `CHANGED` と `MISMATCH` と `FAILED` の合計 |
| Technical KPI | 戻しの照合の一致率 | `RESTORE_VERIFIED` ÷（`RESTORE_VERIFIED` + `RESTORE_MISMATCH`） |
| Quality KPI | 承認なしで消えた件数 | 0 であること。`DELETED` で `approvedBy` か `approvedAt` が空の項目を数える |
| Cost KPI | 実行ごとの Lambda、Fargate、DynamoDB、S3 のリクエスト、状態遷移、アーカイブ用クラスの保管料金 | 下の「費用の見積もり」の式で、`dryRun=true` と小さい `maxFiles` の実測から出す |
| Go / No-Go | 技術の条件: 実環境の通しで、写した全件が `VERIFIED`、`CHANGED` を意図的に作ると消されない、起動者の自己承認が拒否される、戻して `RESTORE_VERIFIED`。事業の条件: 見込みの削減額が運用の費用（承認の工数、戻しの依頼の対応）を上回る、戻しの依頼の入口と応答の目標時間（クラスの復元時間を含む）が決まっている、利用者への案内が済んでいる | 満たすまでは本番のボリュームに `dryRun=false` を使わない。判定の担当（データの持ち主、承認する人、運用の持ち主）を先に決める |

PoC の計画と、本番前の確認の項目は、FSx for ONTAP Adoption Playbook の [本番前のレビューのチェックリスト](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/playbooks/04-build/checklists/pre-production-review.md) と [移行前の棚卸し](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/playbooks/01-assess/checklists/inventory.md) にあります。このパターンの PoC では、`maxFiles` を 20、200、2,000 と増やして、親の実行の所要、状態遷移の数、Fargate の秒数を記録すると、1 ファイルあたりの値が出せます。 PoC の計画表は、Playbook の [自環境での始め方](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/domains/data-utilization/notes/archive-use-cases-and-integrations.md#自環境での始め方) にあります。
### Measurement Method
Step Functions の実行履歴とログ（`/aws/vendedlogs/states/<stack>-archive`、`-restore`。実行のデータは含めない）、`manifests/<runId>-result.json`、`manifests/<runId>-approval.json`、CloudWatch の EMF メトリクス（`FilesVerified`、`FilesDeleted`、`FilesMismatch`、`FilesChanged`、`FilesFailed`、`FilesStuckDeleting`、`BytesVerified`、`BytesDeleted`、`RestoreVerified`、`RestoreMismatch`、`ApprovalPendingHours`）、台帳。

アラーム（すべて通知のトピックへ）:

| アラーム | 条件 |
|---|---|
| `ArchiveExecutionsFailedAlarm`、`RestoreExecutionsFailedAlarm` | 実行の失敗、タイムアウト、中断が 5 分間に 1 件以上 |
| `ApprovalPendingAlarm` | 承認の依頼が `ApprovalAlarmHours`（既定 24）より長く答えを待っている |
| `FilesStuckDeletingAlarm` | 実行の終わりに `DELETING` か `APPROVED` が残った |
| `FilesMismatchAlarm` | 写しの照合で `MISMATCH` が出た |
| `RestoreMismatchAlarm` | 戻したファイルが台帳と一致しなかった |
通知のトピックはカスタマー管理の KMS キーで暗号化します。AWS 管理キー（`alias/aws/sns`）はキーのポリシーを編集できず、EventBridge と CloudWatch アラームが暗号化したトピックへ発行するには、サービスプリンシパルに `kms:GenerateDataKey*` と `kms:Decrypt` を許可したカスタマー管理キーが要るためです（[Amazon SNS のキー管理](https://docs.aws.amazon.com/sns/latest/dg/sns-key-management.html)、2026-11-26 閲覧）。2 回目の通しで、EventBridge の失敗通知と、アラームの通知が届くことを確かめました。 [E-022]
## Performance Considerations
並列度の既定値は、次の 1 回の測定から決めています。それ以外は設計上の要因で、測っていません。
- 元のファイルは 2 回読まれます。1 回目はハッシュ計算のために Access Point から読み、2 回目は `CopyObject` がサーバー側で読みます。読み取りのリクエスト料金がかかり、容量プールにあるデータには容量プールの読み取り料金もかかります
- 並列度は `MapConcurrency`（既定 1、アーカイブと戻しの両方）です。1 回の測定で、Lambda が Access Point から 5.3 GB（約 4.94 GiB）を 69.8 秒で読みました。1 本の読み取りで約 76 MB/s で、この環境のスループット容量 128 MBps の約 6 割です。2 本にすると約 152 MB/s で容量を超える計算になり、ファイルは 2 回読まれ、同じボリュームが業務の読み書きも受けるため、既定は 1 にしています。並列での読み取りは測っていません。上げるときは実行中にファイルシステムの `DataReadBytes` と業務のクライアントのレイテンシを見てください
- `LargeFileThresholdBytes` の既定の 5 GiB は、1 回の `CopyObject` の上限で決まります。上の速度が一定なら Lambda の 15 分で約 63 GiB を読める計算ですが、1 点の測定です
- 一覧は `ListObjectsV2` の全件を 1 つの Lambda のメモリに載せます。数百万件を超える場合は、`prefix` で分けてください
- `selection=ATIME` はディレクトリを深さ優先でたどります。走査の上限は 200,000 エントリ（`ONTAP_SCAN_LIMIT`）で、超えたら途中までの結果を返します
- 戻しの待ち時間はクラスと `tier` で決まります。S3 Glacier Deep Archive は標準で 12 時間以内、大容量で 48 時間以内が AWS の記載です。`RestoreMaxWaitHours` の既定は 72 です。待ちが長いクラスでは `RestorePollMinutes` を大きくすると、ポーリングの状態遷移が減ります
- Fargate のタスクは `FargateTimeoutSeconds`（既定 7200 秒）で打ち切ります。各 Task には `TimeoutSeconds` があり、タイムアウトは再試行の対象です
## 費用の見積もり
請求額は測っていません。次は使用量の実測と、公開の単価の記載から見積もるための式です。
1 ファイルあたりの状態遷移は、2 回の通しで次のとおりでした（どちらも 1 回の値）。

| 実行 | 1 ファイルあたりの状態遷移 | 出典 |
|---|---|---|
| アーカイブの dry run | 17（119 ÷ 7）、18（72 ÷ 4） | 5.5 GiB を含む 7 ファイルの通し、除外と承認を確かめる通し |
| アーカイブの本番（削除を含む） | 18（127 ÷ 7）、19.5（78 ÷ 4） | 同上 |
| 戻し（`Expedited`。除外と承認を確かめる通しは戻した後の照合を含む） | 18（107 ÷ 6）、14（56 ÷ 4） | 同上 |
待ちの長いクラスでは、ポーリング 1 回ごとに状態遷移が増えます。
1 オブジェクトあたりの追加の保管（[Amazon S3 のストレージクラスの比較](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html#sc-compare)、2026-11-26 閲覧）:

| クラス | 最小保管期間 | 1 オブジェクトの追加分、最小の課金サイズ |
|---|---|---|
| S3 Glacier Instant Retrieval | 90 日 | 最小の課金サイズ 128 KB |
| S3 Glacier Flexible Retrieval | 90 日 | メタデータ 40 KB（32 KB はこのクラスの単価、8 KB は S3 Standard の単価） |
| S3 Glacier Deep Archive | 180 日 | メタデータ 40 KB（同上） |
見積もりの式: 月の費用 ≒ 件数 × 1 ファイルあたりの状態遷移 × 状態遷移の単価 + Lambda と Fargate の実行時間 × 単価 + 件数 ×（`CopyObject`、`HeadObject`、`DeleteObject` などのリクエストの単価）+ 保管（データ + 件数 × 追加分）× クラスの単価 + 戻すときの取り出しの料金。単価は [Amazon S3 の料金](https://aws.amazon.com/s3/pricing/) と [AWS Step Functions の料金](https://aws.amazon.com/step-functions/pricing/) で、リージョンと日付を確かめて入れてください。ここには単価を書きません。
## Governance Note
> 本パターンは技術アーキテクチャガイダンスを提供します。法的・コンプライアンス・規制上の助言ではありません。組織は適格な専門家に相談してください。
- 照合の結果と承認は、人が最終判断をするための補助信号です。AI は使っていません
- 保持期間と不変性を満たす必要がある場合、このパターンは対応していません。Object Lock などを使っていないので、権限があれば消せます
- 出力の分類: 台帳とマニフェストにはファイルのパス、大きさ、ハッシュ、属性が入ります。パスには個人の名前、患者や案件の識別子が入りうるため、出力の `data_classification` は既定で `RESTRICTED`（`shared/data_classification.py` の「限定されたアクセス」）です。元のデータの分類のほうが厳しいときは、パラメーター `DataClassification` でそちらに合わせてください。分類を決めるのは利用者です。ファイルの中身はアーカイブ用バケットに入るので、元のデータと同じ分類で扱ってください
- Human Review: 承認は全件に必須です。確信度による自動承認はありません。既定では、起動した主体と承認した主体が同じなら削除しません。この比較は申告された値の比較で、主体の証明ではありません。事後の統制は CloudTrail の `userIdentity` です
- IAM: Access Point の `s3:DeleteObject` を持つのは `delete` 関数のロールだけ、Access Point への `s3:PutObject` を持つのは戻しのステートマシンと戻し用 Fargate のタスクロールだけです。アーカイブ用の Fargate のタスクは写すだけで、元のファイルを消す権限も上書きする権限も持ちません。台帳の項目を消す権限は誰にも与えていません
- 監査: 承認と削除は台帳（`approvedBy`、`approvedAt`、`requestedBy`、`deletedBy`、`deletedAt`）、`manifests/<runId>-approval.json`、Step Functions の実行履歴とログに残ります。CloudTrail に削除が残るのは、トレイルで S3 のデータイベントを有効にしたときだけで、この通しでは確認していません
- 写しの数: 2 つ目の写しを設定しないと、削除の後はアーカイブ用バケットのオブジェクトが唯一の写しです。承認の通知はそのことを書きます
## 制約と未確認事項
- Access Point から別リージョンのバケットへの直接のコピーは `AccessDenied` でした（1 つの Access Point で 1 回）。2 つ目の写しは同じリージョンのバケットだけを対象にしています
- UNIX スタイルのボリュームでの確認です。大きさと mtime を変えない内容の変更は ETag と大きさの確認で検出できません（上の「実機の通しで確かめた挙動」）。`chown` が ETag を変えるかは確認していません
- 属性の取得は、ディレクトリの一覧を使っています。1 ファイルのために親ディレクトリ全体を読むので、大きなディレクトリでは遅くなります
- アーカイブ用バケットのバージョニングは Object Lock ではありません。版は残りますが、権限があれば版も消せます
- 50 GiB を超えるファイルは既定で選びません。`allowOversize: true` で含めた場合、戻しは Access Point へはできず、バケットから直接ダウンロードします
- `requestedBy` と `approver` は申告です。主体の単位の分離は IAM と CloudTrail で確かめてください
## 関連ドキュメント
- [アーキテクチャ](docs/architecture.md)
- [S3 Access Points の互換性メモ](../../../docs/s3ap-compatibility-notes.md)
- [アーカイブ用クラスへ移す 9 種類の仕組みの比較](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/comparison/archive-tiering-library-options.md)

---

<!-- playbook-reading:start -->
## 本番に出す前に読むもの

デプロイしたあとに当たる制約を、どう設計判断に翻訳するかは [FSx for ONTAP Adoption Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook) 側にあります。同じ内容を 2 か所に置くと、更新が止まった側が更新された側より長く残るためです。

- [データ活用](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/ja/domains/data-utilization) — S3 Access Point 経由の制約（全パターン共通）
- [データ保護](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/ja/domains/data-protection) — このパターンで判断が集中するところ
- [構築](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/ja/playbooks/04-build) — 本番前に通す（全パターン共通）
<!-- playbook-reading:end -->
