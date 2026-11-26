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
| このリポジトリで確認した | moto を使った単体テストと、ステートマシンと IAM の構造のテスト。AWS には接続していません |
| まだ確認していない | このパターン全体の実機での通し。多数のファイルでの所要時間と料金。Lambda での 5 GiB 近いファイルのハッシュ計算時間。Fargate のマルチパートコピーの実機。ONTAP REST API のルートディレクトリの指定方法と `unix_permissions` の表現。Distributed Map の `ItemReader` と `ResultWriter` の実機。復元が要る 2 クラスの戻し。NTFS ボリューム、root 以外のユーザー、第 2 世代、Multi-AZ |
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
スクリプトは `chown`、`chmod`、`touch -d` だけを含み、台帳の値は厳密な形式で検査し、キーはシェルのクォートで 1 語にします。形式に合わない値はコメントになり、実行されません。ONTAP REST API で所有者、グループ、モード、更新時刻を設定できるかは確認していないため、この経路は実装していません。
## デプロイ
### 前提
- Access Point のエイリアスと ARN の両方（IAM に両方の形式が要ります。エイリアスだけのポリシーはデプロイできても、実行時に拒否されます）
- アーカイブ用バケットの名前（スタックが作成します。`DeletionPolicy: Retain`、Block Public Access、SSE-S3 が既定、KMS は任意、EventBridge 通知有効、TLS 必須）
- `selection=ATIME` と属性の記録を使うときだけ: VPC、サブネット、ONTAP の認証情報のシークレット、管理エンドポイント、ボリュームの UUID。VPC 内の Lambda から Secrets Manager と S3 へ届く経路（VPC エンドポイントか NAT）が要ります
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
- UNIX スタイルのボリュームでの確認です。更新時刻を戻したうえで中身を変える操作と `chown` は、ETag で検出できるか確認していません
- 属性の取得は、ディレクトリの一覧を使っています。1 ファイルのために親ディレクトリ全体を読むので、大きなディレクトリでは遅くなります
- アーカイブ用バケットのバージョニングは Object Lock ではありません。版は残りますが、権限があれば版も消せます
## 関連ドキュメント
- [アーキテクチャ](docs/architecture.md)
- [S3 Access Points の互換性メモ](../../../docs/s3ap-compatibility-notes.md)
- [アーカイブ用クラスへ移す 8 種類の仕組みの比較](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/comparison/archive-tiering-library-options.md)
