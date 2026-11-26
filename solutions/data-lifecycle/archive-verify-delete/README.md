# archive-verify-delete: S3 API だけで写し、照合し、承認の後に消すアーカイブ
🌐 **Language / 言語**: 日本語 | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)
📚 **ドキュメント**: [アーキテクチャ](docs/architecture.md) | [Architecture (EN)](docs/architecture.en.md)
## 概要
Amazon FSx for NetApp ONTAP（以下 FSx for ONTAP）のボリュームにある、めったに読まれないファイルを、S3 Glacier 系のストレージクラスへ移すパターンです。ボリュームはマウントしません。使うのは S3 Access Points の S3 API だけです。
1 つのファイルは次の順に進み、途中で条件が崩れたファイルは消す対象から外れます。
1. 台帳（DynamoDB のテーブル）に、大きさ、ETag、SHA-256、CRC64NVME を記録する
2. アーカイブ用のバケットへ、ストレージクラスを指定して `CopyObject` で写す
3. バケットが返すチェックサムを、台帳の値と比べる
4. 一致したファイルの一覧を人が承認する
5. Access Point の ETag と大きさが台帳と同じことを確かめてから、Access Point のファイルを消す

戻すときは、台帳から探し、バケットで復元を要求し、完了を待って Access Point へ `CopyObject` で戻します。
このパターンは S3 Object Lock、S3 Glacier Vault Lock、AWS Backup Vault Lock、SnapLock、スナップショットのロックを使いません。テンプレートにも書いていません。保持期間は設定しないので、アーカイブ用のバケットのオブジェクトは、権限があれば消せます。
このパターンの前提と、他の方法との比較は [アーカイブ用クラスへ移す 8 種類の仕組みの比較](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/comparison/archive-tiering-library-options.md) にあります。
## 何を測り、何を測っていないか
| 区分 | 内容 |
|---|---|
| 部品を実機で 1 回ずつ確認した（上の比較資料に記録、2026-11-24 と 2026-11-26、ap-northeast-1、第 1 世代 `SINGLE_AZ_1`、ONTAP 9.19.1P4D1、UNIX スタイルのボリューム、Access Point のユーザーは UNIX root） | `CopyObject` に `ChecksumAlgorithm=SHA256` を付けると、バケットの `ChecksumSHA256` が `FULL_OBJECT` でファイルの SHA-256 と一致した（8 MiB まで）。5.5 GiB のマルチパートは SHA-256 が `COMPOSITE` になり、CRC64NVME は `FULL_OBJECT` で一致した。古い ETag の `--copy-source-if-match` は `PreconditionFailed`。Access Point の `DeleteObject` は `If-Match` 非対応。Step Functions の SDK 統合で Access Point のエイリアスを `Bucket` に渡せた |
| このリポジトリで確認した | moto を使った単体テストと、ステートマシンと IAM の構造のテスト。AWS には接続していません。上の実機の通しで見つかった不具合 3 件（ONTAP REST 関数の呼び出し権限、TLS 検証、復元要求の重複エラー名）は、再現するテストを加えて直しました |
| 実機の通しで 1 回ずつ確認した（2026-11-26、上と同じ環境、`selection=ATIME`、`GLACIER`、7 ファイル） | ONTAP REST API による `accessed_time` の選択と uid、gid、mode、mtime、atime の取得（ルートはボリュームのルートで、パスの先頭にスラッシュなし。`unix_permissions` は `640` の整数で返る）。Distributed Map の `ItemReader` と `ResultWriter`。Fargate による 5.5 GiB のマルチパートコピー（`CopySourceIfMatch` 付き、CRC64NVME が台帳と一致）。Lambda での 5.3 GB（約 4.94 GiB）のハッシュ計算（69.8 秒、メモリ 2048 MB、使用 152 MB）。2 つ目の写し。承認後の削除。承認待ちの間に NFS で書き換えたファイルは `CHANGED` になり消えなかった。承認の拒否で何も消えなかった。`Expedited` での戻し（5.5 GiB を含む）と、戻した 6 ファイルの SHA-256 の一致（7 ファイル中の残る 1 ファイルは書き換え済みで、削除も戻しもされていない）。`reapply.sh` による uid、gid、mode、mtime の復元 |
### 通しの環境と手順ごとの結果
環境は ap-northeast-1、FSx for ONTAP の第 1 世代 `SINGLE_AZ_1`、ONTAP 9.19.1P4D1、UNIX セキュリティスタイルのボリューム、Access Point のファイルシステムユーザーは UNIX root です。実行日は 2026-11-26（時刻は日本時間）、各手順は 1 回だけ実行しました。構成は `selection=ATIME`、`GLACIER`、2 つ目の写しあり、Fargate は arm64 の 2 vCPU と 8 GiB です。データは小さい 6 ファイル（64 B が 3 つ、8 MiB が 3 つ。所有者 1234:5678、モード 640、mtime と atime は 2020-01-02）と、5,905,580,032 B のファイル 1 つです。
| 手順 | 結果 | 所要 |
|---|---|---|
| 1. デプロイ | 成功。ただし実行して見つけた不具合が 2 件あり、再デプロイで直した | 準備からデプロイまで約 30 分（16:19〜16:50） |
| 2. dry run（`dryRun=true`） | 修正後に成功。7 ファイルとも `VERIFIED`（SHA-256 一致 6、CRC64NVME 一致 1）、2 つ目の写しも `VERIFIED`。削除 0 バイトで、NFS では 7 ファイルとも残った | 244 秒（承認の待ち約 70 秒を含む） |
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
### 実機の通しで見つけて直した不具合 3 件
いずれも再現するテストを加えて直しました。
| # | 症状 | 原因と修正 |
|---|---|---|
| 1 | `selection=ATIME` の実行が選択の段階で失敗した | アーカイブのステートマシンのロールに ONTAP REST 関数の `lambda:InvokeFunction` がなかった。許可を追加 |
| 2 | ONTAP REST 関数が `CERTIFICATE_VERIFY_FAILED` で失敗した | 常に TLS を検証していたが、FSx for ONTAP の管理エンドポイントの証明書は公的な CA の署名ではない。パラメーター `OntapVerifySsl`（既定 `false`）を追加 |
| 3 | 復元要求の二重投入がファイルの失敗になった | Step Functions の SDK 統合は `RestoreAlreadyInProgress` を `S3.S3Exception` で返すため、`S3.RestoreAlreadyInProgressException` の `Catch` に一致しなかった。進行中の復元を完了待ちへ回すよう修正 |
### 実機の通しで分かった挙動
不具合として直していない挙動です。
- `selection=ATIME` では、このパターン自身の読み取りが `accessed_time` を更新します。`dryRun=true` で一度回すと、ハッシュ計算の読み取りでファイルの atime が実行時刻になり、同じ入力で `dryRun=false` を回しても選ばれません（0 件で終了。dry run の直後に本番を回したときに確認）。つまり dry run を行うと、そのファイルは最近読まれたものに見えます。dry run の直後に同じ候補で本番を回すなら `selection=MTIME` を使ってください（`LastModified` は読み取りで変わりません）
- Access Point の ETag は、内容ではなく mtime と大きさに連動します。同じ大きさと同じ mtime を持つ内容の違うファイル 3 つが、同じ ETag を返しました。したがって、消す前の ETag と大きさの確認は、大きさと mtime を変えない内容の変更を検出できません。承認待ちの間に大きさが同じまま mtime が更新された書き換えは検出されました（手順 3）
- Access Point 経由で最後のファイルを消すと、空になった親ディレクトリも消えます（`arc-e2e/large/` で確認）。戻しの `CopyObject` が親ディレクトリを作り直します
- 戻したファイルの所有者は 0:1、モードは 644、更新時刻は戻した時刻でした。NFS でボリュームをマウントしたホストで、生成された `reapply.sh` を root として実行すると、元の uid、gid、mode、mtime（1234:5678、640、2020-01-02 03:04:05）に戻り、内容の SHA-256 は変わりませんでした
- この通しでは、Access Point のポリシーに各ロール（`select`、`record`、`delete`、`restore` の各関数のロール、Fargate のタスクロール、2 つのステートマシンのロール）を許可して実行しました
- 戻しの 5.5 GiB は `Expedited` の要求が受け付けられ、完了も約 4 分以内でした
### 確認していないこと
- 多数のファイルでの所要時間と料金
- `Standard` と `Bulk` の戻しの完了待ち（実機では `Expedited` のみ）
- `S3.SlowDownException` の再試行（SDK 統合が返す名前を観測していません。不具合 3 と同じ型の食い違いが起きる恐れがあります）
- CloudTrail のデータイベントでの削除の記録（アカウントのトレイルが対象の Access Point のデータイベントを含むかを確認していません）
- NTFS ボリューム、root 以外のユーザー、第 2 世代、Multi-AZ
- Access Point にポリシーを付けない場合の動作
- 戻しで、`CHANGED` のファイルを選ばないこと以外の `EXISTS` の経路（NFS に同名のファイルがある場合）
- 候補が 0 件になった原因が 1 件あります。`touch -d` で atime を戻した約 10 秒後の実行は、候補が 0 件でした。約 17 分後の確認では 2020 年の値が返り、別の確認でも 6 件が返りました。原因は特定しておらず、再現もしていません
### 消す前の確認に残る書き込みの窓
消す前の確認には、書き込みの窓が 1 つ残ります。Access Point の `DeleteObject` は条件付きの削除に対応していないため、`HeadObject` で確かめてから消すまでの間に書き換えられても検出できません。この窓は API 呼び出し 1 往復分です。
## 処理の流れ
### アーカイブ
入力は `olderThanDays` が必須で、`dryRun` の既定は `true` です。
| 段階 | 処理 | 実装 |
|---|---|---|
| 1. 選ぶ | `MTIME`: Access Point の `ListObjectsV2` の `LastModified`。`ATIME`: ONTAP REST API の `accessed_time`（VPC 内の Lambda） | `select`、`ontap_rest` |
| 2. 記録する | 大きさ、ETag、SHA-256、CRC64NVME、取れる場合は uid、gid、mode、mtime、atime を台帳へ。5 GiB 以下は Lambda、超える分は Fargate | `record`、Fargate のタスク |
| 3. 写す | 5 GiB 以下は SDK 統合の `copyObject`（`SHA256`、台帳の ETag を `CopySourceIfMatch` に付ける）。超える分は Fargate のマルチパートコピー（`CRC64NVME`） | Step Functions、Fargate |
| 4. 照合する | バケットの `HeadObject`（`ChecksumMode=ENABLED`）の大きさとチェックサムを台帳と比べる。一致しなければ `MISMATCH` で残し、消す対象から外す | `ledger` |
| 5. 2 つ目の写し（任意） | 同じリージョンの別バケットへ Access Point から写し、同じ照合をする。不一致なら消す対象から外す | Step Functions、`ledger` |
| 6. 承認する | 一致した一覧を `manifests/<runId>.json` に書き、SNS で通知して `waitForTaskToken` で待つ | `approval` |
| 7. 消す | `dryRun=false` のときだけ。ファイルごとに ETag と大きさを確かめ、同じなら `DeleteObject`。違えば `CHANGED` で残す | `delete` |
| 8. 記録する | `manifests/<runId>-result.json` と EMF のメトリクス（件数、バイト数） | `summarize` |
`dryRun=true` でも段階 6 までは進みます。つまりコピーは行われ、アーカイブ用のクラスの保管料金（S3 Glacier Deep Archive には最小保管期間があります）が発生します。試すときは `maxFiles` を小さくしてください。削除は行われません。
台帳のステータスは `SELECTED`、`RECORDED`、`COPIED`、`VERIFIED`、`DELETED`、`RESTORED` の順に進み、途中の出口が `CHANGED`、`MISMATCH`、`FAILED` です。消せるのは `VERIFIED`（2 つ目の写しを必須にした場合は、その照合も済んだもの）だけです。
### 戻し
入力は `runId` と、`keys` または `prefix` のどちらか 1 つです。`tier`（既定 `Bulk`）と `days`（既定 7）を指定できます。
1. 台帳で `DELETED` のファイルを選ぶ
2. Access Point に同じキーが既にあれば `EXISTS` として残し、上書きしない
3. S3 Glacier Flexible Retrieval と S3 Glacier Deep Archive のオブジェクトは `RestoreObject` を要求する（S3 Glacier Instant Retrieval は不要）
4. 完了待ちはポーリングです（`RestorePollMinutes` ごとに `HeadObject` の `Restore` ヘッダーを読み、`RestoreMaxWaitHours` で打ち切る）。EventBridge の `Object Restore Completed` は使っていません。バケットの EventBridge 通知は有効にしてあるので、後から切り替えられます
5. バケットから Access Point へ `CopyObject`（5 GiB 超は Fargate）
6. 台帳を `RESTORED` にし、属性の付け直し用スクリプト `manifests/<runId>-reapply.sh` を書く

戻したファイルの所有者は 0:1、モードは 644、更新時刻は戻した時刻でした（上の環境の 1 回の確認）。元の値は `CopyObject` では戻りません。
## 承認の操作
承認の通知にはトークンを含めません。トークンは Systems Manager Parameter Store の SecureString（`/<stack>/approvals/<runId>`）にあります。承認する人は、そのパラメーターを読める権限と `states:SendTaskSuccess` の権限を持つ人です。
```bash
TOKEN=$(aws ssm get-parameter --name /<stack>/approvals/<runId> --with-decryption --query Parameter.Value --output text)
aws stepfunctions send-task-success --task-token "$TOKEN" \
  --task-output '{"approved": true, "approver": "<your IAM principal ARN>"}'
# 拒否:
aws stepfunctions send-task-failure --task-token "$TOKEN" --error Rejected --cause "<reason>"
```
`approver` は申告です。入力した値が台帳の `deletedBy` に入りますが、実際に承認した主体を証明するのは CloudTrail の `SendTaskSuccess` のイベントです。`approver` が空、または `approved` が `true` でなければ、削除は行われません。
## 属性の付け直し
戻しの最後に、`manifests/<runId>-reapply.sh` が書かれます。NFS でボリュームをマウントしたホストで、root として実行します。
```bash
MOUNT_ROOT=/mnt/<volume> sh reapply.sh
```
スクリプトは `chown`、`chmod`、`touch -d` だけを含み、台帳の値は厳密な形式で検査し、キーはシェルのクォートで 1 語にします。形式に合わない値はコメントになり、実行されません。ONTAP REST API による所有者、グループ、モード、更新時刻の設定は試していないため、この経路は含めていません。
## デプロイ
### 前提
- Access Point のエイリアスと ARN の両方（IAM に両方の形式が要ります。エイリアスだけのポリシーはデプロイできても、実行時に拒否されます）
- アーカイブ用バケットの名前（スタックが作成します。`DeletionPolicy: Retain`、Block Public Access、SSE-S3 が既定、KMS は任意、EventBridge 通知有効、TLS 必須）
- `selection=ATIME` と属性の記録を使うときだけ: VPC、サブネット、ONTAP の認証情報のシークレット、管理エンドポイント、ボリュームの UUID、`OntapVerifySsl`。FSx for ONTAP の管理エンドポイントの証明書は公的な CA の署名ではないため、既定は `false`（検証しない）です。この間、ONTAP の認証情報は相手を認証しない接続で送られます（経路は VPC 内）。`true` にすると検証に失敗して選択の段階で止まります（実機で確認）。VPC 内の Lambda から Secrets Manager と S3 へ届く経路（VPC エンドポイントか NAT）が要ります
- 5 GiB を超えるファイルを扱うときだけ: ECR に置いたイメージ。Access Point がインターネット起点なので、Fargate のサブネットには NAT か公開 IP が要ります
### 手順
```bash
cd solutions/data-lifecycle/archive-verify-delete
cp samconfig.toml.example samconfig.toml   # <PLACEHOLDER> を置き換える
sam build && sam deploy
```
Fargate を使う場合は、リポジトリのルートからイメージを作り、自分の ECR リポジトリへ push して `FargateImageUri` に指定します。
```bash
docker build --platform linux/arm64 \
  -f solutions/data-lifecycle/archive-verify-delete/fargate/Dockerfile -t <ecr-repo>:<tag> .
```
実行は、まず `dryRun` を省略した（つまり `true` の）入力で行います。
```bash
aws stepfunctions start-execution --state-machine-arn <ArchiveStateMachineArn> \
  --input '{"olderThanDays": 365, "prefix": "projects/", "maxFiles": 20}'
```
削除まで行うときは `"dryRun": false` を JSON の真偽値で渡します。文字列の `"false"` は入力エラーになり、削除されません。
## ディレクトリ構成
```
archive-verify-delete/
├── template.yaml                # SAM。バケット、台帳、Lambda 8 個、ステートマシン 2 個、Fargate（任意）
├── functions/{select,ontap_rest,record,ledger,approval,delete,summarize,restore}/handler.py
├── statemachine/{archive,restore}.asl.json
├── fargate/{Dockerfile,entrypoint.py,requirements.txt}
├── tests/
├── docs/architecture.md, architecture.en.md
└── samconfig.toml.example
```
ドメインのロジック（チェックサム、入力の検査、台帳）は [`shared/archive_verify/`](../../../shared/archive_verify/) にあり、`shared/tests/` でテストします。Access Point への読み書きは `shared/s3ap_helper.py` を通します。
## ローカルテスト
```bash
python3 -m pytest solutions/data-lifecycle/archive-verify-delete/tests/ -v
python3 -m pytest shared/tests/test_archive_verify_*.py shared/tests/test_s3ap_helper_copy.py -v
```
削除の判定が壊れると検出されることを確かめるため、ETag の比較を取り除いたスタブで `test_does_not_delete_when_etag_changed` と `test_does_not_delete_when_size_differs_but_etag_equal` を 1 回実行し、2 件とも `assert 'DELETED' == 'CHANGED'` で失敗することを確認しました。元に戻すと 29 件が通ります。
## Success Metrics
### Outcome
めったに読まれないファイルを、照合と人の承認を経て S3 Glacier 系のクラスへ移し、ボリュームの使用量を下げる。移したファイルは台帳から探して戻せる。
### Metrics
目標値は利用者が決めます。ここに数値は置きません。
| 区分 | 指標 | 定義 |
|---|---|---|
| Business Outcome | 解放した容量 | `bytesDeleted`（`-result.json`）。スナップショットが残る間はボリュームの使用量が下がらない |
| Technical KPI | 照合の一致率 | `VERIFIED` ÷（`VERIFIED` + `MISMATCH`） |
| Technical KPI | 消さなかった件数 | `CHANGED` と `MISMATCH` と `FAILED` の合計 |
| Quality KPI | 承認なしで消えた件数 | 0 であること。台帳の `deletedBy` が空の `DELETED` を数える |
| Cost KPI | 実行ごとの Lambda、Fargate、DynamoDB、S3 のリクエスト、アーカイブ用クラスの保管料金 | 測っていない。`dryRun=true` と小さい `maxFiles` で先に見積もる |
| Go / No-Go | 実環境の通しで、写した全件が `VERIFIED` になり、`CHANGED` を意図的に作ると消されないこと、戻して SHA-256 が一致すること | 満たすまでは本番のボリュームに `dryRun=false` を使わない |
### Measurement Method
Step Functions の実行履歴、`manifests/<runId>-result.json`、CloudWatch の EMF メトリクス（`FilesVerified`、`FilesDeleted`、`FilesMismatch`、`FilesChanged`、`FilesFailed`、`BytesVerified`、`BytesDeleted`）、台帳。
## Performance Considerations
測定していません。次は設計上の要因です。
- 元のファイルは 2 回読まれます。1 回目はハッシュ計算のために Access Point から読み、2 回目は `CopyObject` がサーバー側で読みます。読み取りのリクエスト料金がかかり、容量プールにあるデータには容量プールの読み取り料金もかかります
- 並列度は `MapConcurrency`（既定 10）です。Access Point と ONTAP の負荷に合わせて小さく始めてください
- Lambda の上限は 15 分です。Access Point からの読み取り速度が測れていないため、`LargeFileThresholdBytes` の既定の 5 GiB で足りるかは分かりません。足りなければ下げてください。Fargate が受け持つ分が増えます
- 一覧は `ListObjectsV2` の全件を 1 つの Lambda のメモリに載せます。数百万件を超える場合は、`prefix` で分けてください
- `selection=ATIME` はディレクトリを深さ優先でたどります。走査の上限は 200,000 エントリ（`ONTAP_SCAN_LIMIT`）で、超えたら途中までの結果を返します
- 戻しの待ち時間はクラスと `tier` で決まります。S3 Glacier Deep Archive は標準で 12 時間以内、大容量で 48 時間以内が AWS の記載です。`RestoreMaxWaitHours` の既定は 72 です
## Governance Note
> 本パターンは技術アーキテクチャガイダンスを提供します。法的・コンプライアンス・規制上の助言ではありません。組織は適格な専門家に相談してください。
- 照合の結果と承認は、人が最終判断をするための補助信号です。AI は使っていません
- 保持期間と不変性を満たす必要がある場合、このパターンは対応していません。Object Lock などを使っていないので、権限があれば消せます
- 出力の分類: 台帳とマニフェストにはファイルのパス、大きさ、ハッシュ、属性が入ります（`dataClassification: operational-metadata`）。ファイルの中身はアーカイブ用バケットに入るので、元のデータと同じ分類で扱ってください
- Human Review: 承認は全件に必須です。確信度による自動承認はありません
- IAM: `s3:DeleteObject` を持つのは `delete` 関数のロールだけです。Fargate のタスクは写すだけで、消す権限を持ちません。台帳の項目を消す権限は誰にも与えていません
- 監査: 承認と削除は台帳（`deletedBy`、`deletedAt`）、Step Functions の実行履歴、CloudTrail に残ります
## 制約と未確認事項
- Access Point から別リージョンのバケットへの直接のコピーは `AccessDenied` でした（1 つの Access Point で 1 回）。2 つ目の写しは同じリージョンのバケットだけを対象にしています
- UNIX スタイルのボリュームでの確認です。大きさと mtime を変えない内容の変更は ETag と大きさの確認で検出できません（上の「実機の通しで分かった挙動」）。`chown` が ETag を変えるかは確認していません
- 属性の取得は、ディレクトリの一覧を使っています。1 ファイルのために親ディレクトリ全体を読むので、大きなディレクトリでは遅くなります
- アーカイブ用バケットのバージョニングは Object Lock ではありません。版は残りますが、権限があれば版も消せます
## 関連ドキュメント
- [アーキテクチャ](docs/architecture.md)
- [S3 Access Points の互換性メモ](../../../docs/s3ap-compatibility-notes.md)
- [アーカイブ用クラスへ移す 8 種類の仕組みの比較](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/comparison/archive-tiering-library-options.md)

---

<!-- playbook-reading:start -->
## 本番に出す前に読むもの

デプロイしたあとに当たる制約を、どう設計判断に翻訳するかは [FSx for ONTAP Adoption Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook) 側にあります。同じ内容を 2 か所に置くと、更新が止まった側が更新された側より長く残るためです。

- [データ活用](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/ja/domains/data-utilization) — S3 Access Point 経由の制約（全パターン共通）
- [データ保護](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/ja/domains/data-protection) — このパターンで判断が集中するところ
- [構築](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/ja/playbooks/04-build) — 本番前に通す（全パターン共通）
<!-- playbook-reading:end -->
